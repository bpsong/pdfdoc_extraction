from __future__ import annotations

import ast
import io
from pathlib import Path
from unittest.mock import Mock

import pytest

from modules.services.task_registry_service import (
    ApprovedTaskRegistry,
    BUILTIN_TASKS,
    TaskApprovalError,
    validate_startup_task_registry,
)
import modules.services.task_registry_service as registry_module
from test.helpers_sqlite import TempConfig


def _config(tmp_path: Path, values: dict | None = None) -> TempConfig:
    return TempConfig(tmp_path / "app.sqlite3", values or {})


def test_builtin_standard_tasks_are_approved(tmp_path: Path) -> None:
    registry = ApprovedTaskRegistry(_config(tmp_path))

    assert registry.is_approved("standard_step.extraction.extract_pdf", "ExtractPdfTask")
    assert registry.is_approved("standard_step.review.review_gate", "ReviewGateTask")
    assert registry.is_approved("standard_step.storage.store_metadata_as_json", "StoreMetadataAsJson")
    assert registry.is_approved(
        "standard_step.extraction.glm_ocr_extract", "GlmOcrExtractTask"
    )


def test_builtin_registry_covers_all_standard_step_base_tasks() -> None:
    project_root = Path(__file__).resolve().parents[2]
    standard_step_dir = project_root / "standard_step"
    discovered: set[tuple[str, str]] = set()

    for path in standard_step_dir.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        module_name = ".".join(path.relative_to(project_root).with_suffix("").parts)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and any(_base_name(base) == "BaseTask" for base in node.bases):
                discovered.add((module_name, node.name))

    assert discovered
    assert discovered <= set(BUILTIN_TASKS.values())


def test_unknown_task_pair_is_rejected(tmp_path: Path) -> None:
    registry = ApprovedTaskRegistry(_config(tmp_path))

    with pytest.raises(TaskApprovalError):
        registry.assert_approved("os", "PathLike", task_key="bad")


def test_custom_task_is_approved_only_when_enabled(tmp_path: Path) -> None:
    values = {
        "custom_steps": {
            "enabled": False,
            "registry": {
                "customer_validation": {
                    "module": "custom_step.customer_validation",
                    "class": "CustomerValidationTask",
                }
            },
        }
    }
    registry = ApprovedTaskRegistry(_config(tmp_path, values))

    assert not registry.is_approved("custom_step.customer_validation", "CustomerValidationTask")

    values["custom_steps"]["enabled"] = True
    registry = ApprovedTaskRegistry(_config(tmp_path, values))

    assert registry.is_approved("custom_step.customer_validation", "CustomerValidationTask")


def test_custom_task_with_non_custom_step_prefix_is_rejected(tmp_path: Path) -> None:
    values = {
        "custom_steps": {
            "enabled": True,
            "registry": {
                "bad": {
                    "module": "standard_step.customer_validation",
                    "class": "CustomerValidationTask",
                }
            },
        }
    }
    registry = ApprovedTaskRegistry(_config(tmp_path, values))

    assert not registry.is_approved("standard_step.customer_validation", "CustomerValidationTask")
    findings = registry.validate_custom_registry()
    assert findings[0]["code"] == "custom-task-registry-invalid-module"


def test_startup_validation_allows_valid_active_pipeline(tmp_path: Path) -> None:
    values = {
        "logging": {"log_file": str(tmp_path / "app.log")},
        "tasks": {
            "extract": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
            }
        },
        "pipeline": ["extract"],
    }
    sleeper = Mock()
    exit_func = Mock()

    assert validate_startup_task_registry(
        _config(tmp_path, values),
        sleeper=sleeper,
        exit_func=exit_func,
        stream=io.StringIO(),
    )

    sleeper.assert_not_called()
    exit_func.assert_not_called()


def test_startup_validation_logs_prints_waits_and_exits_for_unapproved_task(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    values = {
        "logging": {"log_file": str(log_file)},
        "tasks": {
            "bad": {
                "module": "untrusted.module",
                "class": "BadTask",
            }
        },
        "pipeline": ["bad"],
    }
    sleeper = Mock()
    output = io.StringIO()

    def exit_func(code: int) -> None:
        raise SystemExit(code)

    with pytest.raises(SystemExit) as excinfo:
        validate_startup_task_registry(
            _config(tmp_path, values),
            sleeper=sleeper,
            exit_func=exit_func,
            stream=output,
        )

    assert excinfo.value.code == 1
    sleeper.assert_called_once_with(15)
    assert "STARTUP BLOCKED" in output.getvalue()
    assert "untrusted.module.BadTask" in output.getvalue()
    assert "CRITICAL" in log_file.read_text(encoding="utf-8")
    assert "untrusted.module.BadTask" in log_file.read_text(encoding="utf-8")


def test_registry_malformed_custom_config_and_relative_log_fallbacks(tmp_path: Path, monkeypatch) -> None:
    registry = ApprovedTaskRegistry(_config(tmp_path, {"custom_steps": {"enabled": True, "registry": []}}))
    assert registry.approved_pairs()
    assert registry.validate_custom_registry()[0]["code"] == "custom-task-registry-not-mapping"
    registry = ApprovedTaskRegistry(_config(tmp_path, {"custom_steps": {"enabled": True, "registry": {"bad": None, "wrong": {"module": 1, "class": 2}}}}))
    assert registry.approved_pairs()

    config = _config(tmp_path, {"logging": {"log_file": "relative.log"}})
    config._config_path = tmp_path / "config.yaml"
    registry_module._append_startup_failure_log(config, "message")
    assert (tmp_path / "relative.log").exists()

    class BrokenPath:
        def __init__(self, *_args):
            pass
        def is_absolute(self):
            return True
        @property
        def parent(self):
            return self
        def mkdir(self, **_kwargs):
            pass
        def open(self, **_kwargs):
            raise OSError("cannot log")

    monkeypatch.setattr(registry_module, "Path", BrokenPath)
    registry_module._append_startup_failure_log(config, "message")

    registry = ApprovedTaskRegistry(
        _config(tmp_path, {"custom_steps": {"enabled": True, "registry": None}})
    )
    assert registry.validate_custom_registry() == []
    registry = ApprovedTaskRegistry(
        _config(
            tmp_path,
            {
                "pipeline": [None, "missing", "bad-types"],
                "tasks": {"missing": None, "bad-types": {"module": 1, "class": 2}},
            },
        )
    )
    assert registry.validate_pipeline_config() == []
    assert validate_startup_task_registry(
        _config(
            tmp_path,
            {"pipeline": ["bad"], "tasks": {"bad": {"module": "os", "class": "Path"}}},
        ),
        wait_seconds=0,
        sleeper=Mock(),
        exit_func=Mock(),
        stream=io.StringIO(),
    ) is False


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None
