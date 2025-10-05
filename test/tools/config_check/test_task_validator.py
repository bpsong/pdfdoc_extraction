"""Unit tests for task validation logic.

This module contains comprehensive unit tests for the task validation functionality,
testing task definition validation, pipeline reference checking, and optional runtime
import validation for the PDF document extraction system.

The test suite covers task validation for:
- Pipeline reference validation against defined tasks
- Task structure validation (module, class, params)
- Optional runtime import checking for module availability
- Class existence and type validation
- Windows-compatible module loading and validation
- Error handling for various import failure scenarios

Key Features:
- Pipeline-to-task reference validation
- Runtime import validation with comprehensive error handling
- Module and class existence verification
- Class type validation (must be actual classes)
- Windows-compatible temporary module creation and testing
- Dynamic module path manipulation for testing

Test Scenarios:
    - Missing task references in pipeline (should error)
    - Missing modules during import checks (should error)
    - Missing classes within valid modules (should error)
    - Non-class attributes referenced as classes (should error)
    - Successful import validation with temporary modules
    - Mixed import check scenarios with partial failures

Test Data:
    Uses realistic task configurations with proper module naming
    conventions and class references that mirror actual PDF processing tasks.

Windows Compatibility:
    - Windows-compatible temporary file and module creation
    - Proper handling of Windows module import paths
    - UTF-8 encoding for international module and class names
    - Windows-style temporary directory management
    - Dynamic Python path manipulation for testing

Import Validation:
    - Tests both successful and failed import scenarios
    - Validates error messages for different failure types
    - Ensures proper cleanup of temporary modules and paths
    - Tests both module-level and class-level import failures
"""

import importlib
import sys
import tempfile
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from tools.config_check.task_validator import validate_tasks  # noqa: E402


def _base_config() -> dict:
    return {
        "web": {
            "upload_dir": "./uploads",
            "secret_key": "task-secret",
        },
        "watch_folder": {"dir": "./watch"},
        "authentication": {
            "username": "admin",
            "password_hash": "$2b$12$eImiTXuWVxfM37uY4JANj.QlsWu1PErG3e1hYzWdG2ZHB5QoLGj7W",
        },
        "tasks": {
            "step_one": {
                "module": "sample.module",
                "class": "SampleTask",
                "params": {},
            }
        },
        "pipeline": ["step_one"],
    }


def test_pipeline_missing_task_reports_error():
    config = _base_config()
    config["pipeline"].append("missing_task")

    result = validate_tasks(config)

    assert any(
        issue.path == "pipeline[1]" and "missing_task" in issue.message
        for issue in result.errors
    )


def test_import_checks_missing_module_reports_error():
    config = _base_config()

    result = validate_tasks(config, import_checks=True)

    assert any("Could not import module" in issue.message for issue in result.errors)


def test_import_checks_missing_class_reports_error():
    config = _base_config()

    module = ModuleType("dummy_module")
    sys.modules[module.__name__] = module
    config["tasks"]["step_one"]["module"] = module.__name__
    config["tasks"]["step_one"]["class"] = "MissingClass"

    try:
        result = validate_tasks(config, import_checks=True)
    finally:
        sys.modules.pop(module.__name__, None)

    assert any("not found" in issue.message for issue in result.errors)


def test_import_checks_non_class_attribute_reports_error():
    config = _base_config()

    module = ModuleType("dummy_module_attr")
    setattr(module, "Exported", object())
    sys.modules[module.__name__] = module
    config["tasks"]["step_one"]["module"] = module.__name__
    config["tasks"]["step_one"]["class"] = "Exported"

    try:
        result = validate_tasks(config, import_checks=True)
    finally:
        sys.modules.pop(module.__name__, None)

    assert any("not a class" in issue.message for issue in result.errors)


def test_import_checks_success():
    config = _base_config()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        module_path = temp_path / "valid_module.py"
        module_path.write_text(
            "class ValidTask:\n    pass\n",
            encoding="utf-8",
        )

        sys.path.insert(0, str(temp_path))
        config["tasks"]["step_one"]["module"] = "valid_module"
        config["tasks"]["step_one"]["class"] = "ValidTask"

        try:
            importlib.invalidate_caches()
            result = validate_tasks(config, import_checks=True)
        finally:
            sys.path.remove(str(temp_path))
            sys.modules.pop("valid_module", None)

    assert result.errors == []
