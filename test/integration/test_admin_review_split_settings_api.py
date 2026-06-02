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


def _base_config(tmp_path: Path, *, split_api_key: str = "llx-secret") -> dict[str, Any]:
    split_dir = tmp_path / "split"
    split_dir.mkdir(exist_ok=True)
    return {
        "auth": {"roles_enabled": True, "default_admin_users": ["admin"]},
        "authentication": {"username": "admin"},
        "review": {"lock_timeout_minutes": 60, "default_queue_name": "default_review"},
        "app_storage": {"split_dir": str(split_dir)},
        "tasks": {
            "split": {
                "module": "standard_step.split.llamacloud_split",
                "class": "LlamaCloudSplitTask",
                "params": {
                    "enabled": True,
                    "api_key": split_api_key,
                    "categories": [{"name": "invoice", "description": "Invoices"}],
                    "allow_uncategorized": "include",
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
                "params": {
                    "confidence_threshold": 0.9,
                    "queue_name": "invoice_review",
                    "review_scope": "low_confidence_fields",
                },
            },
        },
        "pipeline": ["split", "extract", "review"],
    }


def _config(tmp_path: Path, *, split_api_key: str = "llx-secret") -> TempConfig:
    config = TempConfig(tmp_path / "app.sqlite3", _base_config(tmp_path, split_api_key=split_api_key))
    config._config_path.write_text(yaml.safe_dump(config.get_all(), sort_keys=False), encoding="utf-8")
    initialize_database(config)
    return config


def _client(monkeypatch, config: TempConfig, *, username: str = "admin") -> TestClient:
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: username
    return TestClient(app)


def test_review_gate_rules_api_requires_admin(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config, username="operator")

    response = client.get("/api/admin/review-gate-rules")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_review_gate_rules_api_updates_task_params_and_audit(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config)

    overview = client.get("/api/admin/review-gate-rules")
    assert overview.status_code == 200
    assert overview.json()["settings"]["confidence_threshold"] == 0.9
    assert overview.json()["pass_through_behavior"]["review_required"] is False

    update = client.put(
        "/api/admin/review-gate-rules",
        json={
            "settings": {
                "confidence_threshold": 0.92,
                "per_document_type_thresholds": {"invoice": 0.88},
                "field_threshold_overrides": {"supplier": 0.95},
                "review_scope": "document",
                "queue_name": "priority_review",
                "always_review": False,
                "split_confidence_levels_requiring_review": ["low", "medium"],
                "business_rule_flag_names": ["amount_mismatch"],
                "require_review_when_missing_confidence": False,
                "require_review_for_missing_required_fields": True,
                "allow_operator_to_edit_high_confidence_fields": False,
                "schema_file": "invoice.yaml",
                "resume_policy": "next_task",
                "lock_timeout_minutes": 45,
            }
        },
    )

    assert update.status_code == 200
    settings = update.json()["settings"]
    assert settings["confidence_threshold"] == 0.92
    assert settings["field_threshold_overrides"] == {"supplier": 0.95}
    assert config.get("tasks.review.params.confidence_threshold") == 0.92
    assert config.get("tasks.review.params.queue_name") == "priority_review"
    assert config.get("review.lock_timeout_minutes") == 45

    written = yaml.safe_load(config._config_path.read_text(encoding="utf-8"))
    assert written["tasks"]["review"]["params"]["field_threshold_overrides"] == {"supplier": 0.95}

    with connect(config) as conn:
        active = ConfigVersionRepository(conn).get_active("review_gate_rules", "default")
        events = AuditRepository(conn).list_admin_events()
    assert active is not None
    assert json_loads(active["metadata_json"])["settings"]["queue_name"] == "priority_review"
    assert "admin_review_gate_rules_updated" in {event["event_type"] for event in events}


def test_split_settings_api_redacts_secret_and_updates_non_secret_params(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config)

    overview = client.get("/api/admin/split-settings")
    assert overview.status_code == 200
    settings = overview.json()["settings"]
    assert settings["api_key_configured"] is True
    assert "api_key" not in settings

    update = client.put(
        "/api/admin/split-settings",
        json={
            "settings": {
                "enabled": True,
                "categories": [
                    {"name": "invoice", "description": "Invoices"},
                    {"name": "delivery_order", "description": "Delivery orders"},
                ],
                "allow_uncategorized": "omit",
                "split_dir": str(tmp_path / "split"),
                "configuration_id": "cfg-split",
                "project_id": "project-1",
                "organization_id": "org-1",
                "poll_interval_seconds": 2,
                "timeout_seconds": 120,
            }
        },
    )

    assert update.status_code == 200
    settings = update.json()["settings"]
    assert settings["categories"][1]["name"] == "delivery_order"
    assert settings["api_key_configured"] is True
    assert config.get("tasks.split.params.api_key") == "llx-secret"
    assert config.get("tasks.split.params.allow_uncategorized") == "omit"
    assert config.get("tasks.split.params.timeout_seconds") == 120

    connection = client.post("/api/admin/split-settings/test-connection", json={})
    assert connection.status_code == 200
    assert connection.json()["api_key_configured"] is True
    assert connection.json()["network_checked"] is False

    with connect(config) as conn:
        active = ConfigVersionRepository(conn).get_active("split_settings", "default")
        events = AuditRepository(conn).list_admin_events()
    assert active is not None
    assert "admin_split_settings_updated" in {event["event_type"] for event in events}
    assert "admin_split_connection_tested" in {event["event_type"] for event in events}


def test_split_settings_api_rejects_secret_updates(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config)

    response = client.put(
        "/api/admin/split-settings",
        json={"settings": {"enabled": True, "api_key": "new-secret"}},
    )

    assert response.status_code == 400
    assert "cannot be saved" in response.json()["detail"]


def test_review_gate_rules_api_validates_threshold(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config)

    response = client.put(
        "/api/admin/review-gate-rules",
        json={"settings": {"confidence_threshold": 1.5}},
    )

    assert response.status_code == 400
    assert "confidence_threshold" in response.json()["detail"]
