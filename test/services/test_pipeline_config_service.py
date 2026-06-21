from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import AuditRepository, ConfigVersionRepository
from modules.services.pipeline_config_service import PipelineConfigError, PipelineConfigService
from test.helpers_sqlite import TempConfig


def _base_config(tmp_path: Path) -> dict[str, Any]:
    return {
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
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
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
                "params": {
                    "confidence_threshold": 0.9,
                    "review_scope": "low_confidence_fields",
                },
            },
            "store_json": {
                "module": "standard_step.storage.store_metadata_as_json",
                "class": "StoreMetadataAsJson",
                "params": {
                    "data_dir": str(tmp_path / "data"),
                    "filename": "{supplier}",
                },
                "on_error": "continue",
            },
        },
        "pipeline": ["split", "extract", "review", "store_json"],
    }


def _service(tmp_path: Path, values: dict[str, Any] | None = None) -> tuple[TempConfig, PipelineConfigService]:
    config = TempConfig(tmp_path / "app.sqlite3", values or _base_config(tmp_path))
    config._config_path.write_text(yaml.safe_dump(config.get_all()), encoding="utf-8")
    initialize_database(config)
    conn = connect(config)
    return config, PipelineConfigService(config, conn)


def test_pipeline_config_service_saves_draft_and_builds_diff(tmp_path: Path) -> None:
    config, service = _service(tmp_path)
    try:
        active = service.get_pipeline()["active"]
        model = active["model"]
        model["steps"][2]["enabled"] = False

        draft = service.save_draft(model, user="admin")
        overview = service.get_pipeline()
        diff = service.diff()
        validation = service.validate_draft()

        assert draft["summary"]["enabled_steps"] == 3
        assert overview["has_draft"] is True
        assert overview["draft"]["id"] == draft["id"]
        assert diff["changed"] is True
        assert "-- review" in diff["text"]
        assert validation["valid"] is True

        row = ConfigVersionRepository(service.conn).get_draft("pipeline", "default")
        assert row is not None
        metadata = json_loads(row["metadata_json"])
        assert metadata["summary"]["disabled_steps"] == 1
    finally:
        service.conn.close()


def test_pipeline_config_service_publish_writes_config_and_audit(tmp_path: Path) -> None:
    config, service = _service(tmp_path)
    try:
        model = service.get_pipeline()["active"]["model"]
        model["steps"][2]["enabled"] = False
        service.save_draft(model, user="admin")

        result = service.publish(user="admin")
        written = yaml.safe_load(config._config_path.read_text(encoding="utf-8"))
        versions = ConfigVersionRepository(service.conn).list_versions("pipeline", "default")
        audit_events = AuditRepository(service.conn).list_admin_events()

        assert result["validation"]["valid"] is True
        assert written["pipeline"] == ["split", "extract", "store_json"]
        assert config.get("pipeline") == ["split", "extract", "store_json"]
        assert [version["status"] for version in versions].count("published") == 1
        assert {event["event_type"] for event in audit_events} >= {
            "admin_pipeline_draft_saved",
            "admin_pipeline_published",
        }
    finally:
        service.conn.close()


def test_pipeline_config_service_publish_blocks_invalid_order(tmp_path: Path) -> None:
    _, service = _service(tmp_path)
    try:
        model = service.get_pipeline()["active"]["model"]
        model["steps"] = [model["steps"][2], model["steps"][0], model["steps"][1], model["steps"][3]]

        with pytest.raises(PipelineConfigError) as exc_info:
            service.publish(model, user="admin")

        codes = {finding["code"] for finding in exc_info.value.findings}
        assert "pipeline-review-before-extract" in codes
    finally:
        service.conn.close()
