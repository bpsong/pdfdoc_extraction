from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import AuditRepository, ConfigVersionRepository
from test.helpers_sqlite import TempConfig


def _base_config(tmp_path: Path) -> dict[str, Any]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    return {
        "auth": {"roles_enabled": True, "default_admin_users": ["admin"]},
        "authentication": {"username": "admin"},
        "tasks": {
            "split": {
                "module": "standard_step.split.llamacloud_split",
                "class": "LlamaCloudSplitTask",
                "params": {
                    "enabled": True,
                    "adapter": "mock",
                    "categories": [{"name": "invoice"}],
                    "split_dir": str(tmp_path / "split"),
                },
            },
            "extract": {
                "module": "standard_step.extraction.extract_pdf_v2",
                "class": "ExtractPdfV2Task",
                "params": {
                    "fields": {
                        "supplier": {"alias": "Supplier", "type": "str"},
                    }
                },
                "on_error": "stop",
            },
            "review": {
                "module": "standard_step.review.review_gate",
                "class": "ReviewGateTask",
                "params": {"confidence_threshold": 0.9},
            },
            "store_json": {
                "module": "standard_step.storage.store_metadata_as_json_v2",
                "class": "StoreMetadataAsJsonV2",
                "params": {"data_dir": str(data_dir), "filename": "{supplier}"},
                "on_error": "continue",
            },
        },
        "pipeline": ["split", "extract", "review", "store_json"],
    }


def _client(monkeypatch, config: TempConfig, *, username: str = "admin") -> TestClient:
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: username
    return TestClient(app)


def _config(tmp_path: Path) -> TempConfig:
    config = TempConfig(tmp_path / "app.sqlite3", _base_config(tmp_path))
    config._config_path.write_text(yaml.safe_dump(config.get_all()), encoding="utf-8")
    initialize_database(config)
    return config


def _draft_model(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["draft"]["model"] if payload.get("draft") else payload["active"]["model"]


def test_admin_pipeline_api_requires_admin(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config, username="operator")

    response = client.get("/api/admin/pipeline")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_admin_pipeline_api_draft_diff_validate_and_publish(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config)

    overview = client.get("/api/admin/pipeline")
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["active"]["summary"]["enabled_steps"] == 4
    assert any(task["class_name"] == "ReviewGateTask" for task in payload["catalog"]["tasks"])

    model = _draft_model(payload)
    model["steps"][2]["enabled"] = False
    draft_response = client.put("/api/admin/pipeline/draft", json={"model": model})
    assert draft_response.status_code == 200
    assert draft_response.json()["draft"]["summary"]["enabled_steps"] == 3

    diff_response = client.post("/api/admin/pipeline/diff", json={"model": model})
    assert diff_response.status_code == 200
    assert diff_response.json()["changed"] is True

    validation_response = client.post("/api/admin/pipeline/validate", json={"model": model})
    assert validation_response.status_code == 200
    assert validation_response.json()["valid"] is True

    publish_response = client.post("/api/admin/pipeline/publish", json={"model": model})
    assert publish_response.status_code == 200
    written = yaml.safe_load(config._config_path.read_text(encoding="utf-8"))
    assert written["pipeline"] == ["split", "extract", "store_json"]

    with connect(config) as conn:
        active = ConfigVersionRepository(conn).get_active("pipeline", "default")
        events = AuditRepository(conn).list_admin_events()
    assert active is not None
    metadata = json_loads(active["metadata_json"])
    assert metadata["summary"]["enabled_steps"] == 3
    assert {event["event_type"] for event in events} >= {
        "admin_pipeline_draft_saved",
        "admin_pipeline_validated",
        "admin_pipeline_published",
    }


def test_admin_pipeline_publish_rejects_blocking_findings(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config)
    model = client.get("/api/admin/pipeline").json()["active"]["model"]
    model["steps"] = [model["steps"][2], model["steps"][0], model["steps"][1], model["steps"][3]]

    response = client.post("/api/admin/pipeline/publish", json={"model": model})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["message"] == "Pipeline draft has blocking validation findings."
    assert "pipeline-review-before-extract" in {finding["code"] for finding in detail["findings"]}
