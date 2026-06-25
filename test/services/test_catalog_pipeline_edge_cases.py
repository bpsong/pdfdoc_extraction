from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.base_task import BaseTask
from modules.services.pipeline_config_service import (
    PipelineConfigError,
    PipelineConfigService,
    _key_from_class,
    _label_for_key,
    _unique_key,
)
from modules.services.pipeline_validation_service import (
    PipelineValidationService,
    _duplicate_warning_type,
    _iter_tasks,
)
from modules.services.task_catalog_service import TaskCatalogService, _is_json_safe
from modules.services.task_registry_service import ApprovedTaskRegistry
from test.helpers_sqlite import TempConfig


def test_task_catalog_static_edge_cases(tmp_path, monkeypatch):
    config = TempConfig(tmp_path / "app.sqlite3", {})
    service = TaskCatalogService(config, project_root=tmp_path)
    invalid = tmp_path / "invalid.py"
    invalid.write_text("class Broken(", encoding="utf-8")

    assert service._class_names(invalid) == []
    monkeypatch.setattr(
        "modules.services.task_catalog_service.inspect.signature",
        lambda value: (_ for _ in ()).throw(ValueError("unsupported")),
    )
    assert service._signature_parameters(int) == []
    assert service._category_for("custom.module") == "configured"
    assert service._label_for("XMLTask") == "XML"
    assert service._summary(None) == ""
    assert _is_json_safe([1, {"a": True}]) is True
    assert _is_json_safe({1: "bad"}) is False
    assert _is_json_safe(object()) is False

    entry = {"configured_keys": [], "pipeline_positions": [], "configured_params": {}}
    service._merge_configured(
        entry,
        {
            "task_key": "task",
            "pipeline_index": None,
            "params": {"api_key": "secret"},
            "on_error": "stop",
        },
    )
    assert entry["is_configured"] is True
    assert entry["pipeline_positions"] == []


def test_task_catalog_handles_discovery_and_configured_import_failures(
    tmp_path,
    monkeypatch,
):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline": ["invalid", "missing"],
            "tasks": {
                "ignored": "not-a-mapping",
                "invalid": {"module": "", "class": "Task"},
                "missing": {
                    "module": "standard_step.missing",
                    "class": "MissingTask",
                    "params": "not-a-mapping",
                },
            },
        },
    )
    service = TaskCatalogService(config, project_root=tmp_path)
    standard_dir = tmp_path / "standard_step"
    standard_dir.mkdir()
    source = standard_dir / "missing.py"
    source.write_text("class MissingTask:\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(service.task_registry, "is_approved", lambda *args: True)
    monkeypatch.setattr(
        "modules.services.task_catalog_service.importlib.import_module",
        lambda name: (_ for _ in ()).throw(ImportError(f"cannot import {name}")),
    )

    configured = service._configured_entries()
    discovered = service._discover_standard_step_entries()
    catalog = service.catalog()

    assert configured == [
        {
            "task_key": "missing",
            "module": "standard_step.missing",
            "class_name": "MissingTask",
            "params": {},
            "on_error": None,
            "pipeline_index": 1,
        }
    ]
    assert discovered["standard_step.missing.MissingTask"]["import_status"] == "failed"
    assert catalog["summary"]["failed"] == 1
    assert catalog["tasks"][0]["configured_keys"] == ["missing"]


def test_task_catalog_configured_only_entries_cover_all_import_states(
    tmp_path,
    monkeypatch,
):
    service = TaskCatalogService(
        TempConfig(tmp_path / "app.sqlite3", {}),
        project_root=tmp_path,
    )
    configured = {
        "task_key": "task",
        "module": "custom_step.example",
        "class_name": "ExampleTask",
        "params": {"token": "secret"},
        "on_error": "stop",
        "pipeline_index": 2,
    }

    monkeypatch.setattr(service.task_registry, "is_approved", lambda *args: False)
    unapproved = service._configured_only_entry(configured)
    assert unapproved["import_status"] == "failed"
    assert unapproved["is_configured"] is True

    class ExampleTask(BaseTask):
        """Example catalog task."""

        def __init__(self, config_manager, count=1):
            super().__init__(config_manager, count=count)

        def on_start(self, context):
            return None

        def run(self, context):
            return context

        def validate_required_fields(self, context):
            return None

    monkeypatch.setattr(service.task_registry, "is_approved", lambda *args: True)
    monkeypatch.setattr(
        "modules.services.task_catalog_service.importlib.import_module",
        lambda name: SimpleNamespace(ExampleTask=ExampleTask),
    )
    available = service._configured_only_entry(configured)
    assert available["import_status"] == "ok"
    assert available["docstring_summary"] == "Example catalog task."
    assert available["parameters"][0]["name"] == "count"

    monkeypatch.setattr(
        "modules.services.task_catalog_service.importlib.import_module",
        lambda name: (_ for _ in ()).throw(ImportError("missing")),
    )
    failed = service._configured_only_entry(configured)
    assert failed["import_status"] == "failed"


def test_task_catalog_discovery_skips_non_task_classes(tmp_path, monkeypatch):
    service = TaskCatalogService(
        TempConfig(tmp_path / "app.sqlite3", {}),
        project_root=tmp_path,
    )
    assert service._discover_standard_step_entries() == {}

    standard_dir = tmp_path / "standard_step"
    standard_dir.mkdir()
    source = standard_dir / "candidate.py"
    source.write_text(
        "class NotAClass:\n    pass\n\nclass NotATask:\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(service.task_registry, "is_approved", lambda *args: True)
    monkeypatch.setattr(
        "modules.services.task_catalog_service.importlib.import_module",
        lambda name: SimpleNamespace(NotAClass=object(), NotATask=object),
    )
    assert service._discover_standard_step_entries() == {}

    monkeypatch.setattr(
        "modules.services.task_catalog_service.issubclass",
        lambda *args: (_ for _ in ()).throw(TypeError("invalid class")),
        raising=False,
    )
    monkeypatch.setattr(
        "modules.services.task_catalog_service.importlib.import_module",
        lambda name: SimpleNamespace(NotAClass=object, NotATask=object),
    )
    assert service._discover_standard_step_entries() == {}


def test_task_registry_reports_all_malformed_custom_entries(tmp_path):
    data = {
        "custom_steps": {
            "enabled": True,
            "registry": {
                "not_mapping": "bad",
                "missing_module": {"class": "Task"},
                "missing_class": {"module": "custom_step.task"},
                "bad_prefix": {"module": "other.task", "class": "Task"},
            },
        },
        "pipeline": [1, "missing", "bad", "approved"],
        "tasks": {
            "missing": "bad",
            "bad": {"module": "untrusted.module", "class": "BadTask"},
            "approved": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
            },
        },
    }
    registry = ApprovedTaskRegistry(config_data=data)

    codes = {finding["code"] for finding in registry.validate_pipeline_config()}

    assert {
        "custom-task-registry-entry-invalid",
        "custom-task-registry-missing-module",
        "custom-task-registry-missing-class",
        "custom-task-registry-invalid-module",
        "pipeline-task-not-approved",
    } <= codes

    not_mapping = {
        "custom_steps": {"enabled": True, "registry": []},
    }
    findings = ApprovedTaskRegistry(config_data=not_mapping).validate_custom_registry()
    assert findings[0]["code"] == "custom-task-registry-not-mapping"


def test_pipeline_validation_reports_task_specific_and_ordering_errors(tmp_path):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"schema": {"directories": [str(tmp_path / "schemas")]}},
    )
    data = {
        "pipeline": [
            "review",
            "extract1",
            "split1",
            "extract2",
            "split2",
            "review2",
            "store1",
            "store2",
        ],
        "tasks": {
            "review": {
                "module": "standard_step.review.review_gate",
                "class": "ReviewGateTask",
                "params": {
                    "confidence_threshold": True,
                    "resume_policy": "restart",
                    "split_confidence_levels_requiring_review": ["invalid"],
                    "schema_file": "missing.yaml",
                },
            },
            "review2": {
                "module": "standard_step.review.review_gate",
                "class": "ReviewGateTask",
                "params": {},
            },
            "extract1": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
            },
            "extract2": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
            },
            "split1": {
                "module": "standard_step.split.llamacloud_split",
                "class": "LlamaCloudSplitTask",
                "params": {
                    "enabled": True,
                    "split_dir": "",
                    "allow_uncategorized": "bad",
                    "fail_on_confidence_levels": [1],
                    "fail_on_unknown_category": "yes",
                    "allowed_categories": [""],
                    "categories": ["bad"],
                },
            },
            "split2": {
                "module": "standard_step.split.llamacloud_split",
                "class": "LlamaCloudSplitTask",
                "params": "bad",
            },
            "split3": {
                "module": "standard_step.split.llamacloud_split",
                "class": "LlamaCloudSplitTask",
                "params": {"enabled": True, "split_dir": "split"},
            },
            "store1": {"module": "custom.store", "class": "StoreTask"},
            "store2": {"module": "custom.store", "class": "StoreTask"},
        },
    }
    service = PipelineValidationService(config)

    findings = (
        service._validate_review_gate(data)
        + service._validate_split(data)
        + service._validate_pipeline_task_cardinality(data)
        + service._validate_schema_references(data)
    )
    codes = {finding["code"] for finding in findings}

    assert {
        "review-gate-invalid-confidence-threshold",
        "review-gate-invalid-resume-policy",
        "review-gate-invalid-split-confidence-levels",
        "split-missing-split-dir",
        "split-missing-categories-or-configuration",
        "split-missing-runtime-api-key",
        "split-invalid-allow-uncategorized",
        "split-invalid-fail-on-confidence-levels",
        "split-invalid-fail-on-unknown-category",
        "split-invalid-allowed-categories",
        "split-invalid-categories",
        "split-params-not-mapping",
        "pipeline-multiple-extract-tasks",
        "pipeline-multiple-split-tasks",
        "pipeline-multiple-review-gate-tasks",
        "pipeline-split-after-extract",
        "pipeline-review-before-extract",
        "pipeline-duplicate-task-type",
        "review-gate-schema-not-found",
    } <= codes

    assert _iter_tasks({"tasks": []}) == []
    assert _duplicate_warning_type({}) == "unknown"


def test_pipeline_config_normalization_and_helper_edges():
    service = object.__new__(PipelineConfigService)

    for model, message in [
        ([], "must be an object"),
        ({}, "steps list"),
        ({"steps": ["bad"]}, "index 0"),
        ({"steps": [{"key": "x"}]}, "requires module and class"),
        (
            {
                "steps": [
                    {
                        "key": "x",
                        "module": "module",
                        "class": "Task",
                        "params": [],
                    }
                ]
            },
            "params must be an object",
        ),
    ]:
        with pytest.raises(PipelineConfigError, match=message):
            service._normalize_model(model)

    with pytest.raises(PipelineConfigError, match="YAML root"):
        service._config_from_yaml("[1]")

    assert _key_from_class("ExtractPdfTask") == "extract_pdf"
    used = {"task", "task_2"}
    assert _unique_key("task", used) == "task_3"
    assert _label_for_key("") == ""
