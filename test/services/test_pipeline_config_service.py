from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
import yaml

import modules.services.pipeline_config_service as pipeline_module
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
                    "api_key": "split-secret",
                    "adapter": "mock",
                    "categories": [{"name": "invoice"}],
                    "split_dir": str(tmp_path / "split"),
                },
            },
            "extract": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
                "params": {
                    "api_key": "extract-secret",
                    "fields": {
                        "supplier": {"alias": "Supplier", "type": "str"},
                    },
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


def test_pipeline_config_service_preserves_field_order_after_draft_reload(tmp_path: Path) -> None:
    _, service = _service(tmp_path)
    try:
        model = service.get_pipeline()["active"]["model"]
        extract_params = model["steps"][1]["params"]
        extract_params["fields"] = {
            "zeta": {"alias": "Zeta", "type": "str"},
            "alpha": {"alias": "Alpha", "type": "str"},
            "middle": {"alias": "Middle", "type": "str"},
        }

        service.save_draft(model, user="admin")
        reloaded = service.get_pipeline()["draft"]["model"]

        assert list(reloaded["steps"][1]["params"]["fields"]) == [
            "zeta",
            "alpha",
            "middle",
        ]
    finally:
        service.conn.close()


def test_pipeline_config_service_diff_ignores_mapping_and_integer_float_noise(tmp_path: Path) -> None:
    values = _base_config(tmp_path)
    values["tasks"]["split"]["params"]["poll_interval_seconds"] = 1.0
    _, service = _service(tmp_path, values)
    try:
        model = service.get_pipeline()["active"]["model"]
        split_params = model["steps"][0]["params"]
        model["steps"][0]["params"] = {
            key: split_params[key]
            for key in reversed(list(split_params))
        }
        model["steps"][0]["params"]["poll_interval_seconds"] = 1

        diff = service.diff(model)

        assert diff["changed"] is False
        assert diff["text"] == ""
    finally:
        service.conn.close()


def test_pipeline_config_service_redacts_and_preserves_secret_params(tmp_path: Path) -> None:
    config, service = _service(tmp_path)
    try:
        overview = service.get_pipeline()
        model = overview["active"]["model"]

        split_params = model["steps"][0]["params"]
        extract_params = model["steps"][1]["params"]
        assert split_params["api_key"] == "[REDACTED]"
        assert extract_params["api_key"] == "[REDACTED]"
        assert "split-secret" not in overview["active"]["yaml_preview"]
        assert "extract-secret" not in overview["active"]["yaml_preview"]

        split_params["split_dir"] = str(tmp_path / "new-split")
        draft = service.save_draft(model, user="admin")
        stored_draft = ConfigVersionRepository(service.conn).get_draft("pipeline", "default")
        assert stored_draft is not None
        draft_yaml = yaml.safe_load(stored_draft["content_text"])

        assert draft["model"]["steps"][0]["params"]["api_key"] == "[REDACTED]"
        assert draft_yaml["tasks"]["split"]["params"]["api_key"] == "split-secret"
        assert draft_yaml["tasks"]["extract"]["params"]["api_key"] == "extract-secret"
        assert draft_yaml["tasks"]["split"]["params"]["split_dir"] == str(tmp_path / "new-split")

        replacement_model = draft["model"]
        replacement_model["steps"][1]["params"]["api_key"] = "replacement-secret"
        service.save_draft(replacement_model, user="admin")
        stored_replacement = ConfigVersionRepository(service.conn).get_draft(
            "pipeline", "default"
        )
        assert stored_replacement is not None
        replacement_yaml = yaml.safe_load(stored_replacement["content_text"])
        assert replacement_yaml["tasks"]["split"]["params"]["api_key"] == "split-secret"
        assert replacement_yaml["tasks"]["extract"]["params"]["api_key"] == "replacement-secret"
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


def test_pipeline_config_service_hides_and_strips_runtime_housekeeping(tmp_path: Path) -> None:
    values = _base_config(tmp_path)
    values["tasks"]["cleanup"] = {
        "module": "standard_step.housekeeping.cleanup_task",
        "class": "CleanupTask",
        "params": {"processing_dir": "processing"},
    }
    values["pipeline"].append("cleanup")
    config, service = _service(tmp_path, values)
    try:
        model = service.get_pipeline()["active"]["model"]
        assert all(step["class"] != "CleanupTask" for step in model["steps"])

        service.save_draft(model, user="admin")
        service.publish(model, user="admin")
        written = yaml.safe_load(config._config_path.read_text(encoding="utf-8"))

        assert "cleanup" not in written["pipeline"]
        assert "cleanup" not in written["tasks"]
    finally:
        service.conn.close()


def test_pipeline_config_service_remaining_model_and_storage_branches(monkeypatch) -> None:
    service = object.__new__(PipelineConfigService)
    service.config_manager = SimpleNamespace(_config_path=None)
    service.conn = Mock()
    service.versions = Mock()
    service.audit = Mock()

    service._active_config = Mock(return_value={"tasks": {}, "pipeline": []})
    service._model_from_config = Mock(return_value={"steps": []})
    service.save_draft = Mock(return_value={"id": "draft"})
    assert service.create_draft(user="alice") == {"id": "draft"}
    service.save_draft.assert_called_once_with({"steps": []}, user="alice")

    service._normalize_model = Mock(return_value={"steps": []})
    service._secret_source_config = Mock(return_value={})
    service._config_from_model = Mock(return_value={"tasks": {}})
    service._dump_yaml = Mock(return_value="preview")
    assert service.yaml_preview({"steps": []}) == "preview"

    service._config_from_yaml = Mock(return_value={"tasks": {}, "pipeline": []})
    service._model_from_config = Mock(return_value={"steps": []})
    service._normalize_model = Mock(side_effect=lambda model: model)
    assert service._draft_payload({"id": "d1", "content_text": "{}", "metadata_json": "null"})["id"] == "d1"

    service.versions.get_draft.return_value = None
    service._model_from_config.return_value = {"steps": []}
    assert service._stored_or_active_model() == {"steps": []}
    service.versions.get_draft.return_value = {"content_text": "{}", "metadata_json": "{}", "id": "d1"}
    service._draft_payload = Mock(return_value={"model": {"steps": [{"key": "x"}]}})
    assert service._stored_or_active_model() == {"steps": [{"key": "x"}]}

    row = {"content_text": "same", "id": "d1"}
    service.versions.get_draft.return_value = row
    assert service._matching_or_new_draft(yaml_preview="same", model={}, user=None) is row
    service.versions.get_draft.return_value = None
    service.versions.create_draft.return_value = {"id": "new"}
    assert service._matching_or_new_draft(yaml_preview="new", model={}, user="a")["id"] == "new"

    monkeypatch.setattr(pipeline_module, "get_all_config", lambda _manager: [])
    service._active_config = PipelineConfigService._active_config.__get__(service)
    assert service._active_config() == {}

    service._active_config = Mock(return_value={"tasks": {"cleanup": {"module": "standard_step.housekeeping.cleanup_task", "class": "CleanupTask"}, "keep": {"class": "Keep"}}})
    service._config_from_model = PipelineConfigService._config_from_model.__get__(service)
    model = {"steps": [None, {"key": "keep", "module": "m", "class": "C", "params": None, "enabled": True}]}
    assert service._config_from_model(model)["pipeline"] == ["keep"]
    assert service._config_from_model({"steps": []})["pipeline"] == []

    config = {"tasks": {"known": {"class": "Known", "module": "m"}, "clean": {"module": "standard_step.housekeeping.cleanup_task", "class": "CleanupTask"}}, "pipeline": ["known", "missing", 4, "clean"]}
    service._model_from_config = PipelineConfigService._model_from_config.__get__(service)
    service._step_from_task = Mock()
    service._step_from_task.return_value = {"key": "known"}
    model = service._model_from_config(config)
    assert [step["key"] for step in model["steps"]] == ["known", "missing"]

    service._normalize_model = PipelineConfigService._normalize_model.__get__(service)
    normalized = service._normalize_model({"steps": [{"module": "standard_step.housekeeping.cleanup_task", "class": "CleanupTask"}, {"module": "m", "class": "C", "params": None}]})
    assert len(normalized["steps"]) == 1 and normalized["steps"][0]["params"] == {}

    service.config_manager = SimpleNamespace(config={}, _values={})
    service._replace_in_memory_config({"pipeline": []})
    assert service.config_manager.config == {"pipeline": []}

    service.versions.get_draft.return_value = None
    service._active_config = Mock(return_value={"pipeline": []})
    assert service._draft_config(None) == {"pipeline": []}
# pyright: reportAttributeAccessIssue=false
