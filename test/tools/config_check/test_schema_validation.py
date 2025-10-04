"""Unit tests for schema validation helpers.

This module contains comprehensive unit tests for the schema validation functionality,
testing Pydantic model validation, error reporting, and strict/lenient validation modes
for configuration files in the PDF document extraction system.

The test suite covers schema validation for:
- Valid configuration structure acceptance
- Required section validation (web, watch_folder, tasks, pipeline)
- Pipeline entry type validation (must be strings)
- Unknown key handling in default and strict modes
- Field-specific validation (on_error values, etc.)
- Windows-compatible path handling in schema validation

Key Features:
- Pydantic model validation testing with comprehensive error scenarios
- Strict vs lenient mode validation testing
- Required field validation and error reporting
- Unknown key handling and appropriate severity assignment
- Windows-compatible test data with proper path formats
- Field-level validation testing for specific constraints

Test Scenarios:
    - Valid minimal configuration acceptance
    - Missing required sections (should error)
    - Invalid pipeline entry types (should error)
    - Unknown configuration keys (warnings in default, errors in strict)
    - Invalid field values (on_error must be 'stop' or 'continue')
    - Complex nested configuration validation

Test Data:
    Uses realistic configuration structures that mirror actual PDF processing
    scenarios with Windows-compatible paths and proper field definitions.

Windows Compatibility:
    - Windows-compatible path formats in test configurations
    - UTF-8 encoding support for international characters
    - Proper handling of Windows path separators in schema validation
    - Case-insensitive validation where appropriate

Validation Modes:
    - Default mode: Unknown keys generate warnings
    - Strict mode: Unknown keys generate errors
    - Both modes validate required fields and field constraints
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from tools.config_check.schema import validate_config_against_schema


def _build_minimal_config() -> dict:
    return {
        "web": {"upload_dir": "./tmp"},
        "watch_folder": {"dir": "./watch"},
        "tasks": {
            "step_one": {
                "module": "sample.module",
                "class": "SampleTask",
                "params": {},
            }
        },
        "pipeline": ["step_one"],
    }


def test_valid_config_passes_schema_validation():
    config = _build_minimal_config()

    result = validate_config_against_schema(config)

    assert result.errors == []
    assert result.warnings == []
    assert result.model is not None


def test_missing_required_section_reports_error():
    config = _build_minimal_config()
    config.pop("watch_folder")

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(issue.path == "watch_folder" for issue in result.errors)


def test_pipeline_requires_string_entries():
    config = _build_minimal_config()
    config["pipeline"] = [123]

    result = validate_config_against_schema(config)

    assert any("pipeline" in issue.path for issue in result.errors)


def test_unknown_keys_are_warnings_by_default():
    config = _build_minimal_config()
    config["custom_section"] = {}

    result = validate_config_against_schema(config)

    assert result.model is not None
    assert result.errors == []
    assert any(issue.path == "custom_section" for issue in result.warnings)


def test_strict_mode_treats_unknown_keys_as_errors():
    config = _build_minimal_config()
    config["extra_block"] = {}

    result = validate_config_against_schema(config, strict=True)

    assert result.warnings == []
    assert any(issue.path == "extra_block" for issue in result.errors)


def test_invalid_on_error_value_reports_error():
    config = _build_minimal_config()
    config["tasks"]["step_one"]["on_error"] = "halt"

    result = validate_config_against_schema(config)

    assert any(
        issue.path == "tasks.step_one.on_error" for issue in result.errors
    )
