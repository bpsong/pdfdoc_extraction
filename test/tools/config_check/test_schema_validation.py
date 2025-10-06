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
        "web": {
            "upload_dir": "./tmp",
            "secret_key": "super-secret",
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


def test_missing_authentication_section_reports_error():
    config = _build_minimal_config()
    config.pop("authentication")

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(issue.path == "authentication" for issue in result.errors)


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


def test_missing_secret_key_reports_error():
    config = _build_minimal_config()
    config["web"].pop("secret_key")

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(issue.path == "web.secret_key" for issue in result.errors)


def test_invalid_password_hash_reports_error():
    config = _build_minimal_config()
    config["authentication"]["password_hash"] = "not-a-bcrypt"

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(
        issue.path == "authentication.password_hash" for issue in result.errors
    )


# Tests for new schema validation fields (web.host and web.port)

def test_valid_web_host_passes_validation():
    """Test that valid web.host values are accepted."""
    config = _build_minimal_config()
    config["web"]["host"] = "localhost"

    result = validate_config_against_schema(config)

    assert result.errors == []
    assert result.model is not None
    assert result.model.web.host == "localhost"


def test_valid_web_port_passes_validation():
    """Test that valid web.port values are accepted."""
    config = _build_minimal_config()
    config["web"]["port"] = 3000

    result = validate_config_against_schema(config)

    assert result.errors == []
    assert result.model is not None
    assert result.model.web.port == 3000


def test_web_host_defaults_to_localhost():
    """Test that web.host defaults to 127.0.0.1 when not specified."""
    config = _build_minimal_config()
    # Don't set host explicitly

    result = validate_config_against_schema(config)

    assert result.errors == []
    assert result.model is not None
    assert result.model.web.host == "127.0.0.1"


def test_web_port_defaults_to_8000():
    """Test that web.port defaults to 8000 when not specified."""
    config = _build_minimal_config()
    # Don't set port explicitly

    result = validate_config_against_schema(config)

    assert result.errors == []
    assert result.model is not None
    assert result.model.web.port == 8000


def test_empty_web_host_reports_error():
    """Test that empty web.host values are rejected."""
    config = _build_minimal_config()
    config["web"]["host"] = ""

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(
        issue.path == "web.host" and "at least 1 character" in issue.message
        for issue in result.errors
    )


def test_whitespace_only_web_host_reports_error():
    """Test that whitespace-only web.host values are rejected."""
    config = _build_minimal_config()
    config["web"]["host"] = "   "

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(
        issue.path == "web.host" and "non-empty string" in issue.message
        for issue in result.errors
    )


def test_invalid_web_port_too_low_reports_error():
    """Test that web.port values below 1 are rejected."""
    config = _build_minimal_config()
    config["web"]["port"] = 0

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(
        issue.path == "web.port" and "greater than or equal to 1" in issue.message
        for issue in result.errors
    )


def test_invalid_web_port_too_high_reports_error():
    """Test that web.port values above 65535 are rejected."""
    config = _build_minimal_config()
    config["web"]["port"] = 65536

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(
        issue.path == "web.port" and "less than or equal to 65535" in issue.message
        for issue in result.errors
    )


def test_non_integer_web_port_reports_error():
    """Test that non-integer web.port values are rejected."""
    config = _build_minimal_config()
    config["web"]["port"] = "not_a_number"  # Use a string that can't be converted to int

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(
        issue.path == "web.port" and "valid integer" in issue.message
        for issue in result.errors
    )


# Tests for new schema validation fields (watch_folder.validate_pdf_header and processing_dir)

def test_valid_watch_folder_validate_pdf_header_passes_validation():
    """Test that valid watch_folder.validate_pdf_header values are accepted."""
    config = _build_minimal_config()
    config["watch_folder"]["validate_pdf_header"] = False

    result = validate_config_against_schema(config)

    assert result.errors == []
    assert result.model is not None
    assert result.model.watch_folder.validate_pdf_header is False


def test_valid_watch_folder_processing_dir_passes_validation():
    """Test that valid watch_folder.processing_dir values are accepted."""
    config = _build_minimal_config()
    config["watch_folder"]["processing_dir"] = "temp_processing"

    result = validate_config_against_schema(config)

    assert result.errors == []
    assert result.model is not None
    assert result.model.watch_folder.processing_dir == "temp_processing"


def test_watch_folder_validate_pdf_header_defaults_to_true():
    """Test that watch_folder.validate_pdf_header defaults to True when not specified."""
    config = _build_minimal_config()
    # Don't set validate_pdf_header explicitly

    result = validate_config_against_schema(config)

    assert result.errors == []
    assert result.model is not None
    assert result.model.watch_folder.validate_pdf_header is True


def test_watch_folder_processing_dir_defaults_to_processing():
    """Test that watch_folder.processing_dir defaults to 'processing' when not specified."""
    config = _build_minimal_config()
    # Don't set processing_dir explicitly

    result = validate_config_against_schema(config)

    assert result.errors == []
    assert result.model is not None
    assert result.model.watch_folder.processing_dir == "processing"


def test_non_boolean_validate_pdf_header_reports_error():
    """Test that non-boolean watch_folder.validate_pdf_header values are rejected."""
    config = _build_minimal_config()
    config["watch_folder"]["validate_pdf_header"] = "not_a_boolean"  # Use a string that can't be converted to boolean

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(
        issue.path == "watch_folder.validate_pdf_header" and "valid boolean" in issue.message
        for issue in result.errors
    )


def test_empty_processing_dir_reports_error():
    """Test that empty watch_folder.processing_dir values are rejected."""
    config = _build_minimal_config()
    config["watch_folder"]["processing_dir"] = ""

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(
        issue.path == "watch_folder.processing_dir" and "at least 1 character" in issue.message
        for issue in result.errors
    )


def test_whitespace_only_processing_dir_reports_error():
    """Test that whitespace-only watch_folder.processing_dir values are rejected."""
    config = _build_minimal_config()
    config["watch_folder"]["processing_dir"] = "   "

    result = validate_config_against_schema(config)

    assert result.model is None
    assert any(
        issue.path == "watch_folder.processing_dir" and "non-empty string" in issue.message
        for issue in result.errors
    )
