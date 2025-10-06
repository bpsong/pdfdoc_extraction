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

    assert any("not found" in issue.message for issue in result.errors)


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


# Enhanced import validation tests for comprehensive coverage

def test_import_checks_module_not_found_detailed_error():
    """Test detailed error reporting for module not found scenarios."""
    config = _base_config()
    config["tasks"]["step_one"]["module"] = "nonexistent.module"

    result = validate_tasks(config, import_checks=True)

    # Should have a specific error for module not found
    module_errors = [
        issue for issue in result.errors 
        if issue.code == "task-import-module-not-found" and "nonexistent.module" in issue.message
    ]
    assert len(module_errors) == 1
    assert "Check PYTHONPATH and module installation" in module_errors[0].message
    assert module_errors[0].path == "tasks.step_one.module"


def test_import_checks_syntax_error_handling():
    """Test handling of modules with syntax errors."""
    config = _base_config()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        module_path = temp_path / "syntax_error_module.py"
        # Create a module with syntax errors
        module_path.write_text(
            "class InvalidTask\n    # Missing colon causes syntax error\n    pass\n",
            encoding="utf-8",
        )

        sys.path.insert(0, str(temp_path))
        config["tasks"]["step_one"]["module"] = "syntax_error_module"
        config["tasks"]["step_one"]["class"] = "InvalidTask"

        try:
            importlib.invalidate_caches()
            result = validate_tasks(config, import_checks=True)
        finally:
            sys.path.remove(str(temp_path))
            sys.modules.pop("syntax_error_module", None)

    # Should have a specific error for syntax error
    syntax_errors = [
        issue for issue in result.errors 
        if issue.code == "task-import-module-syntax-error"
    ]
    assert len(syntax_errors) == 1
    assert "syntax errors" in syntax_errors[0].message
    assert syntax_errors[0].path == "tasks.step_one.module"


def test_import_checks_class_not_found_with_suggestions():
    """Test detailed error reporting when class is not found in module."""
    config = _base_config()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        module_path = temp_path / "empty_module.py"
        # Create a module with some attributes but not the requested class
        module_path.write_text(
            "class ExistingTask:\n    pass\n\ndef some_function():\n    pass\n\nVARIABLE = 'value'\n",
            encoding="utf-8",
        )

        sys.path.insert(0, str(temp_path))
        config["tasks"]["step_one"]["module"] = "empty_module"
        config["tasks"]["step_one"]["class"] = "MissingTask"

        try:
            importlib.invalidate_caches()
            result = validate_tasks(config, import_checks=True)
        finally:
            sys.path.remove(str(temp_path))
            sys.modules.pop("empty_module", None)

    # Should have a specific error for class not found with suggestions
    class_errors = [
        issue for issue in result.errors 
        if issue.code == "task-import-class-not-found"
    ]
    assert len(class_errors) == 1
    assert "MissingTask" in class_errors[0].message
    assert "Available attributes:" in class_errors[0].message
    assert "ExistingTask" in class_errors[0].message
    assert class_errors[0].path == "tasks.step_one.class"


def test_import_checks_non_class_attribute_detailed_error():
    """Test detailed error reporting when attribute is not a class."""
    config = _base_config()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        module_path = temp_path / "non_class_module.py"
        # Create a module with non-class attributes
        module_path.write_text(
            "def not_a_class():\n    pass\n\nNOT_A_CLASS_VAR = 'value'\n",
            encoding="utf-8",
        )

        sys.path.insert(0, str(temp_path))
        config["tasks"]["step_one"]["module"] = "non_class_module"
        config["tasks"]["step_one"]["class"] = "not_a_class"

        try:
            importlib.invalidate_caches()
            result = validate_tasks(config, import_checks=True)
        finally:
            sys.path.remove(str(temp_path))
            sys.modules.pop("non_class_module", None)

    # Should have a specific error for non-class attribute
    type_errors = [
        issue for issue in result.errors 
        if issue.code == "task-import-not-callable"
    ]
    assert len(type_errors) == 1
    assert "not a class" in type_errors[0].message
    assert "function" in type_errors[0].message  # Should identify the actual type
    assert type_errors[0].path == "tasks.step_one.class"


def test_import_checks_multiple_tasks_mixed_results():
    """Test import validation with multiple tasks having mixed success/failure."""
    config = _base_config()
    
    # Add multiple tasks with different scenarios
    config["tasks"]["valid_task"] = {
        "module": "os",  # Built-in module that exists
        "class": "path",  # This is not a class, it's a module
        "params": {}
    }
    config["tasks"]["invalid_module"] = {
        "module": "nonexistent.module",
        "class": "SomeClass",
        "params": {}
    }
    config["pipeline"] = ["step_one", "valid_task", "invalid_module"]

    result = validate_tasks(config, import_checks=True)

    # Should have errors for both the original task and the new ones
    assert len(result.errors) >= 2
    
    # Check for module not found error
    module_errors = [
        issue for issue in result.errors 
        if issue.code == "task-import-module-not-found"
    ]
    assert len(module_errors) >= 1
    
    # Check for non-class attribute error
    type_errors = [
        issue for issue in result.errors 
        if issue.code == "task-import-not-callable"
    ]
    assert len(type_errors) >= 1


def test_import_checks_successful_multiple_tasks():
    """Test successful import validation with multiple valid tasks."""
    config = _base_config()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create first valid module
        module1_path = temp_path / "valid_module1.py"
        module1_path.write_text(
            "class ValidTask1:\n    pass\n",
            encoding="utf-8",
        )
        
        # Create second valid module
        module2_path = temp_path / "valid_module2.py"
        module2_path.write_text(
            "class ValidTask2:\n    pass\n\nclass AnotherTask:\n    pass\n",
            encoding="utf-8",
        )

        sys.path.insert(0, str(temp_path))
        
        # Update config with multiple valid tasks
        config["tasks"]["step_one"]["module"] = "valid_module1"
        config["tasks"]["step_one"]["class"] = "ValidTask1"
        config["tasks"]["step_two"] = {
            "module": "valid_module2",
            "class": "ValidTask2",
            "params": {}
        }
        config["tasks"]["step_three"] = {
            "module": "valid_module2",
            "class": "AnotherTask",
            "params": {}
        }
        config["pipeline"] = ["step_one", "step_two", "step_three"]

        try:
            importlib.invalidate_caches()
            result = validate_tasks(config, import_checks=True)
        finally:
            sys.path.remove(str(temp_path))
            for module_name in ["valid_module1", "valid_module2"]:
                sys.modules.pop(module_name, None)

    # Should have no errors for valid tasks
    assert result.errors == []


def test_import_checks_invalid_task_structure_skips_import():
    """Test that tasks with invalid structure skip import validation."""
    config = _base_config()
    
    # Create task with invalid structure (missing module)
    config["tasks"]["invalid_structure"] = {
        "class": "SomeClass",
        "params": {}
        # Missing "module" field
    }
    config["pipeline"] = ["step_one", "invalid_structure"]

    result = validate_tasks(config, import_checks=True)

    # Should have structure validation errors but not import errors for the invalid task
    structure_errors = [
        issue for issue in result.errors 
        if issue.code == "task-import-invalid-module" and "invalid_structure" in issue.path
    ]
    assert len(structure_errors) == 1
    
    # Should still have import errors for the original task (which has valid structure)
    import_errors = [
        issue for issue in result.errors 
        if "step_one" in issue.path and issue.code.startswith("task-import-")
    ]
    assert len(import_errors) >= 1


def test_import_checks_disabled_by_default():
    """Test that import checks are disabled by default."""
    config = _base_config()
    config["tasks"]["step_one"]["module"] = "nonexistent.module"

    result = validate_tasks(config)  # import_checks=False by default

    # Should not have import-related errors when import checks are disabled
    import_errors = [
        issue for issue in result.errors 
        if issue.code.startswith("task-import-")
    ]
    assert len(import_errors) == 0
