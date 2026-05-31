from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from test.helpers_sqlite import TempConfig


BCRYPT_HASH = "$2b$12$eImiTXuWVxfM37uY4JANj.QlsWu1PErG3e1hYzWdG2ZHB5QoLGj7W"


def _base_config(tmp_path: Path) -> dict[str, Any]:
    upload_dir = tmp_path / "uploads"
    watch_dir = tmp_path / "watch"
    schema_dir = tmp_path / "schemas"
    upload_dir.mkdir(exist_ok=True)
    watch_dir.mkdir(exist_ok=True)
    schema_dir.mkdir(exist_ok=True)
    return {
        "web": {"upload_dir": str(upload_dir), "secret_key": "test-secret"},
        "watch_folder": {
            "dir": str(watch_dir),
            "processing_dir": str(tmp_path / "processing"),
        },
        "authentication": {"username": "admin", "password_hash": BCRYPT_HASH},
        "schema": {"directories": [str(schema_dir)]},
        "tasks": {
            "extract": {
                "module": "custom_step.extraction.fake_extract",
                "class": "FakeExtractTask",
                "params": {
                    "api_key": "llx-test-key",
                    "fields": {
                        "invoice_number": {
                            "alias": "Invoice number",
                            "type": "str",
                        }
                    },
                },
                "on_error": "stop",
            }
        },
        "pipeline": ["extract"],
    }


def _client(monkeypatch, config: TempConfig) -> TestClient:
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    return TestClient(app)


def _codes(payload: dict[str, Any]) -> set[str]:
    return {str(finding.get("code")) for finding in payload["findings"]}


def test_get_config_validation_validates_active_config_file(tmp_path: Path, monkeypatch) -> None:
    values = _base_config(tmp_path)
    config = TempConfig(tmp_path / "app.sqlite3", values)
    config._config_path.write_text(yaml.safe_dump(values), encoding="utf-8")
    client = _client(monkeypatch, config)

    response = client.get("/api/config/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["source"] == str(config._config_path)


def test_post_config_validation_validates_submitted_payload(tmp_path: Path, monkeypatch) -> None:
    values = _base_config(tmp_path)
    values["tasks"]["review"] = {
        "module": "standard_step.review.review_gate",
        "class": "ReviewGateTask",
        "params": {"confidence_threshold": -0.1},
        "on_error": "stop",
    }
    values["pipeline"] = ["extract", "review"]
    config = TempConfig(tmp_path / "app.sqlite3", values)
    client = _client(monkeypatch, config)

    response = client.post("/api/config/validation", json={"config": values})

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert "review-gate-invalid-confidence-threshold" in _codes(payload)


def test_post_pipeline_validate_reports_split_findings(tmp_path: Path, monkeypatch) -> None:
    values = _base_config(tmp_path)
    values["tasks"]["split"] = {
        "module": "standard_step.split.llamacloud_split",
        "class": "LlamaCloudSplitTask",
        "params": {"enabled": True, "categories": [{"name": "invoice"}]},
        "on_error": "stop",
    }
    values["pipeline"] = ["extract", "split"]
    config = TempConfig(tmp_path / "app.sqlite3", values)
    client = _client(monkeypatch, config)

    response = client.post("/api/pipeline/validate", json={"config": values})

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert "split-missing-runtime-api-key" in _codes(payload)
    assert "split-final-pipeline-step" in _codes(payload)


def test_validation_endpoints_reject_invalid_payload_shape(tmp_path: Path, monkeypatch) -> None:
    config = TempConfig(tmp_path / "app.sqlite3", _base_config(tmp_path))
    client = _client(monkeypatch, config)

    response = client.post("/api/config/validation", json={"config": "not-a-mapping"})

    assert response.status_code == 400
    assert response.json()["detail"] == "payload.config must be an object"
