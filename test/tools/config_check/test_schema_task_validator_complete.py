"""Direct contract coverage for config-check schema and import validators."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import BaseModel

from tools.config_check.schema import (
    ConfigModel,
    CustomTaskRegistryEntry,
    TaskDefinition,
    WebConfig,
    _collect_extra_fields,
    _format_location,
    validate_config_against_schema,
)
from tools.config_check.task_validator import (
    _validate_class_existence,
    _validate_class_type,
    _validate_module_import,
    _validate_task_imports,
    validate_tasks,
)


def _valid_config() -> dict:
    return {"web": {"upload_dir": "uploads", "secret_key": "secret"}, "watch_folder": {"dir": "watch"}}


def test_schema_models_normalize_and_reject_values() -> None:
    web = WebConfig(upload_dir="u", secret_key="s", cors_allowed_origins="https://a, https://b", allowed_hosts="a,b")
    assert web.cors_allowed_origins == ["https://a", "https://b"]
    assert web.allowed_hosts == ["a", "b"]
    assert WebConfig(upload_dir="u", secret_key="s", cors_allowed_origins=None, allowed_hosts=None).allowed_hosts == []
    with pytest.raises(ValueError):
        WebConfig(upload_dir="u", secret_key="s", cors_allowed_origins="*")
    with pytest.raises(ValueError):
        WebConfig(upload_dir="u", secret_key="s", allowed_hosts="*")
    upload_web = WebConfig(upload_dir="u", secret_key="s")
    assert upload_web.max_upload_request_mb == 200
    with pytest.raises(ValueError):
        WebConfig(upload_dir="u", secret_key="s", max_concurrent_uploads=0)
    assert TaskDefinition(module="m", **{"class": "C"}, params=None, on_error=" CONTINUE ").on_error == "continue"


def test_schema_validator_direct_edge_branches() -> None:
    assert WebConfig.validate_port(8000) == 8000
    with pytest.raises(ValueError):
        WebConfig.validate_port(0)
    with pytest.raises(ValueError):
        WebConfig.validate_cors_allowed_origins({"origin": "x"})
    with pytest.raises(ValueError):
        WebConfig.validate_allowed_hosts({"host": "x"})
    assert TaskDefinition._validate_on_error(None) is None
    with pytest.raises(ValueError):
        TaskDefinition._validate_on_error(1)
    with pytest.raises(ValueError):
        CustomTaskRegistryEntry._validate_custom_module_prefix("standard_step.x")
    assert CustomTaskRegistryEntry._validate_custom_module_prefix("custom_step.x") == "custom_step.x"
    assert ConfigModel._ensure_tasks_not_empty(None) is None
    assert ConfigModel._validate_pipeline_entries(None) is None
    with pytest.raises(TypeError):
        ConfigModel._validate_pipeline_entries([1])
    with pytest.raises(ValueError):
        ConfigModel._validate_pipeline_entries([""])
    with pytest.raises(TypeError):
        TaskDefinition._coerce_params("bad")
    assert TaskDefinition._coerce_params(None) == {}

    nested = TaskDefinition(module="m", **{"class": "C"})
    assert list(_collect_extra_fields({"tasks": [nested]}, "")) == []
    class ListContainer(BaseModel):
        items: list[TaskDefinition]
    nested_extra = TaskDefinition(module="m", **{"class": "C", "extra": 1})
    assert list(_collect_extra_fields(ListContainer(items=[nested_extra]))) == ["items[0].extra"]
    with pytest.raises((ValueError, TypeError)):
        TaskDefinition(module="m", **{"class": "C"}, params=[])
    with pytest.raises(ValueError):
        TaskDefinition(module="m", **{"class": "C"}, on_error="bad")
    with pytest.raises(ValueError):
        CustomTaskRegistryEntry(module="standard_step.bad", **{"class": "C"})
    model = ConfigModel(**_valid_config(), tasks={"x": {"module": "m", "class": "C"}}, pipeline=[" x "])
    assert model.pipeline == ["x"]
    with pytest.raises(ValueError):
        ConfigModel(**_valid_config(), tasks={})
    with pytest.raises(ValueError):
        ConfigModel(**_valid_config(), pipeline=[])
    with pytest.raises((ValueError, TypeError)):
        ConfigModel(**_valid_config(), pipeline=[1])


def test_schema_validation_and_location_helpers() -> None:
    good = validate_config_against_schema(_valid_config())
    assert good.model is not None
    extra = validate_config_against_schema({**_valid_config(), "unknown": {"nested": 1}})
    assert extra.warnings
    strict = validate_config_against_schema({**_valid_config(), "unknown": 1}, strict=True)
    assert strict.errors
    invalid = validate_config_against_schema({"web": {"upload_dir": ""}})
    assert invalid.model is None
    assert any(item.path == "web.secret_key" for item in invalid.errors)
    assert _format_location(("items", 0, "name", 1)) == "items[0].name[1]"
    assert _format_location((0,)) == "[0]"
    assert list(_collect_extra_fields(ConfigModel(**_valid_config(), extra={"x": 1}))) == ["extra"]


def test_task_validator_structure_pipeline_and_import_exception_paths() -> None:
    result = validate_tasks({"tasks": {"good": {}}, "pipeline": ["", None, "missing"]})
    assert len(result.errors) == 3
    assert validate_tasks({"tasks": {}, "pipeline": "bad"}).errors[-1].code == "pipeline-not-list"
    assert validate_tasks({"tasks": {}, "pipeline": []}, import_checks=True).errors == []
    for exc, code in [(ModuleNotFoundError("x"), "task-import-module-not-found"), (SyntaxError("x"), "task-import-module-syntax-error"), (ImportError("x"), "task-import-module-import-error"), (RuntimeError("x"), "task-import-module-error")]:
        with patch("importlib.import_module", side_effect=exc):
            assert _validate_module_import("bad", "task").code == code
    with patch("importlib.import_module", side_effect=RuntimeError("x")):
        assert _validate_class_existence("bad", "C", "task").code == "task-import-class-access-error"
    with patch("importlib.import_module", return_value=type("M", (), {})()):
        assert _validate_class_existence("m", "Missing", "task").code == "task-import-class-not-found"
    with patch("importlib.import_module", return_value=type("M", (), {"value": 1})()):
        assert _validate_class_type("m", "value", "task").code == "task-import-not-callable"
    with patch("importlib.import_module", side_effect=RuntimeError("x")):
        assert _validate_class_type("m", "C", "task").code == "task-import-class-type-error"
    assert _validate_task_imports("task", {"module": "m", "class": "C"})
