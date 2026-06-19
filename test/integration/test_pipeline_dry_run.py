from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import AuditRepository
from test.helpers_sqlite import TempConfig, initialize_test_users


def _base_config(tmp_path: Path) -> dict[str, Any]:
    export_dir = tmp_path / "exports"
    split_dir = tmp_path / "split"
    export_dir.mkdir(exist_ok=True)
    split_dir.mkdir(exist_ok=True)
    return {
        "auth": {"roles_enabled": True, "default_admin_users": ["admin"]},
        "authentication": {"username": "admin"},
        "ui": {"app_name": "DocFlow AI", "page_size": 25},
        "validation": {
            "config_validation_enabled": True,
            "allow_ui_config_save": False,
            "strict_mode_default": False,
        },
        "review": {"lock_timeout_minutes": 60, "default_queue_name": "default_review"},
        "tasks": {
            "split": {
                "module": "standard_step.split.llamacloud_split",
                "class": "LlamaCloudSplitTask",
                "params": {
                    "enabled": True,
                    "adapter": "mock",
                    "categories": [{"name": "invoice"}],
                    "split_dir": str(split_dir),
                },
            },
            "extract": {
                "module": "standard_step.extraction.extract_pdf_v2",
                "class": "ExtractPdfV2Task",
                "params": {"fields": {"supplier": {"alias": "Supplier", "type": "str"}}},
            },
            "review": {
                "module": "standard_step.review.review_gate",
                "class": "ReviewGateTask",
                "params": {"confidence_threshold": 0.9},
            },
            "store_json": {
                "module": "standard_step.storage.store_metadata_as_json_v2",
                "class": "StoreMetadataAsJsonV2",
                "params": {"data_dir": str(export_dir), "filename": "{supplier}"},
            },
        },
        "pipeline": ["split", "extract", "review", "store_json"],
    }


def _config(tmp_path: Path) -> TempConfig:
    config = TempConfig(tmp_path / "app.sqlite3", _base_config(tmp_path))
    config._config_path.write_text(yaml.safe_dump(config.get_all(), sort_keys=False), encoding="utf-8")
    initialize_database(config)
    initialize_test_users(config)
    return config


def _client(monkeypatch, config: TempConfig, *, username: str = "admin") -> TestClient:
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: username
    return TestClient(app)


def test_admin_dry_run_requires_admin(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config, username="operator")

    response = client.post("/api/admin/dry-run", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_admin_summary_settings_audit_and_dry_run_api(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config)

    summary = client.get("/api/admin/summary")
    assert summary.status_code == 200
    assert summary.json()["pipeline"]["active"]["enabled_steps"] == 4

    settings = client.put(
        "/api/admin/settings",
        json={"settings": {"ui.page_size": 40, "review.default_queue_name": "priority"}},
    )
    assert settings.status_code == 200
    assert settings.json()["settings"]["ui.page_size"] == 40

    dry_run = client.post(
        "/api/admin/dry-run",
        json={
            "sample_filename": "sample.pdf",
            "mock_results": {
                "extraction_fields": [{"field_key": "supplier", "confidence": 0.72}],
                "review_required": True,
            },
        },
    )
    assert dry_run.status_code == 200
    payload = dry_run.json()
    assert payload["writes"]["final_exports_written"] is False
    assert payload["review_gate"]["review_required"] is True
    assert payload["exports"]["steps"][0]["status"] == "skipped_in_dry_run"

    audit = client.get("/api/admin/audit", params={"event_type": "admin_pipeline_dry_run", "user": "admin"})
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    assert audit.json()["events"][0]["id"] == payload["audit_event_id"]

    with connect(config) as conn:
        event_types = {event["event_type"] for event in AuditRepository(conn).list_admin_events()}
    assert {"admin_settings_updated", "admin_pipeline_dry_run"}.issubset(event_types)
