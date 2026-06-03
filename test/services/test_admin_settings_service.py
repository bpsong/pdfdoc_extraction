from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import AuditRepository, ConfigVersionRepository
from modules.services.admin_settings_service import (
    AdminAuditService,
    AdminSettingsError,
    AdminSettingsService,
    PipelineDryRunService,
)
from test.helpers_sqlite import TempConfig


def _base_config(tmp_path: Path) -> dict[str, Any]:
    export_dir = tmp_path / "exports"
    split_dir = tmp_path / "split"
    export_dir.mkdir(exist_ok=True)
    split_dir.mkdir(exist_ok=True)
    return {
        "ui": {"app_name": "DocFlow AI", "page_size": 25},
        "validation": {
            "config_validation_enabled": True,
            "allow_ui_config_save": False,
            "strict_mode_default": False,
        },
        "review": {"lock_timeout_minutes": 60, "default_queue_name": "default_review"},
        "app_storage": {
            "root_dir": str(tmp_path / "data"),
            "originals_dir": str(tmp_path / "data" / "originals"),
            "working_dir": str(tmp_path / "data" / "working"),
            "split_dir": str(split_dir),
            "exports_dir": str(export_dir),
            "archive_dir": str(tmp_path / "data" / "archive"),
        },
        "tasks": {
            "split": {
                "module": "standard_step.split.llamacloud_split",
                "class": "LlamaCloudSplitTask",
                "params": {
                    "enabled": True,
                    "adapter": "mock",
                    "categories": [{"name": "invoice"}],
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
    return config


def test_admin_settings_service_updates_allowed_settings_and_audits(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with connect(config) as conn:
        service = AdminSettingsService(config, conn)
        before = service.get_admin_settings()

        result = service.update_admin_settings(
            {
                "settings": {
                    "ui.app_name": "Invoice Ops",
                    "ui.page_size": 50,
                    "review.lock_timeout_minutes": 30,
                }
            },
            user="admin",
        )
        active = ConfigVersionRepository(conn).get_active("admin_settings", "default")
        events = AuditRepository(conn).list_admin_events()

    written = yaml.safe_load(config._config_path.read_text(encoding="utf-8"))

    assert before["settings"]["ui.app_name"] == "DocFlow AI"
    assert result["settings"]["ui.app_name"] == "Invoice Ops"
    assert result["settings"]["ui.page_size"] == 50
    assert config.get("review.lock_timeout_minutes") == 30
    assert written["ui"]["app_name"] == "Invoice Ops"
    assert active is not None
    assert "admin_settings_updated" in {event["event_type"] for event in events}


def test_admin_settings_service_rejects_secret_and_unknown_settings(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with connect(config) as conn:
        service = AdminSettingsService(config, conn)
        with pytest.raises(AdminSettingsError):
            service.update_admin_settings({"settings": {"api_key": "secret"}}, user="admin")
        with pytest.raises(AdminSettingsError):
            service.update_admin_settings({"settings": {"ui.admin_enabled": False}}, user="admin")


def test_admin_audit_service_filters_admin_events_only(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with connect(config) as conn:
        audits = AuditRepository(conn)
        audits.append(event_type="document_paused", event={"metadata": {"reason": "review"}})
        admin_event = audits.append(event_type="admin_pipeline_published", event={"after": {"ok": True}}, user="admin")

        result = AdminAuditService(conn).list_events(user="admin")

    assert result["total"] == 1
    assert result["events"][0]["id"] == admin_event["id"]
    assert result["events"][0]["event_type"] == "admin_pipeline_published"


def test_pipeline_dry_run_records_audit_and_redacts_request(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with connect(config) as conn:
        result = PipelineDryRunService(config, conn).run(
            {
                "sample_filename": "sample.pdf",
                "api_key": "llx-secret",
                "mock_results": {
                    "extraction_fields": [{"field_key": "supplier", "confidence": 0.72}],
                    "review_required": True,
                },
            },
            user="admin",
        )
        events = AuditRepository(conn).list_admin_events(event_type="admin_pipeline_dry_run")

    event_payload = json_loads(events[0]["event_json"])

    assert result["writes"]["final_exports_written"] is False
    assert result["review_gate"]["review_required"] is True
    assert result["exports"]["steps"][0]["status"] == "skipped_in_dry_run"
    assert events[0]["id"] == result["audit_event_id"]
    assert event_payload["metadata"]["request"]["api_key"] == "[REDACTED]"
