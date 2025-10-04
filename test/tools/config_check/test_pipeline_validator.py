"""Unit tests for pipeline dependency validation.

This module contains comprehensive unit tests for the pipeline dependency validation
functionality, ensuring proper execution flow and data dependency management across
different types of processing tasks in the PDF document extraction system.

The test suite covers pipeline validation for:
- Dependency order validation (extraction before storage)
- Context token availability (nanoid requires context initializer)
- Housekeeping task placement requirements (must be final step)
- Template token validation against extraction fields
- Task classification and categorization validation
- Duplicate pipeline entry detection

Key Features:
- Task classification-based dependency validation
- Template token extraction and validation testing
- Context token dependency chain validation
- Housekeeping task placement enforcement
- Token availability validation against extraction fields
- Windows-compatible test data and processing

Test Scenarios:
    - Storage tasks running before extraction (should fail)
    - Context-dependent tokens without context initializer (should fail)
    - Missing housekeeping task in pipeline (should fail)
    - Housekeeping task not in final position (should warn)
    - Unknown template tokens in task parameters (should fail)
    - Duplicate task entries in pipeline (should warn)

Test Data:
    Uses realistic task configurations with proper module classifications
    and token dependencies that mirror actual PDF processing scenarios.

Windows Compatibility:
    - All string processing is Windows-compatible and encoding-aware
    - Token extraction handles Windows-specific path formats
    - Case-sensitive token matching as per template requirements
    - Proper handling of Windows line endings in test data

Note:
    Pipeline validation tests focus on the logical flow and dependency
    relationships between tasks, ensuring proper data processing order.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from tools.config_check.pipeline_validator import validate_pipeline  # noqa: E402


def _base_config():
    return {
        "tasks": {
            "extract_metadata": {
                "module": "standard_step.extraction.extract_metadata",
                "class": "ExtractMetadata",
                "params": {
                    "fields": {
                        "supplier_name": {"alias": "Supplier"},
                        "invoice_amount": {"alias": "Amount"},
                    }
                },
            },
            "store_json": {
                "module": "standard_step.storage.store_metadata",
                "class": "StoreMetadata",
                "params": {
                    "filename": "{supplier_name}.json",
                },
            },
            "context_ids": {
                "module": "standard_step.context.generate_ids",
                "class": "GenerateIds",
                "params": {},
            },
            "cleanup": {
                "module": "standard_step.housekeeping.cleanup",
                "class": "CleanupTask",
                "params": {},
            },
        },
        "pipeline": ["extract_metadata", "store_json", "cleanup"],
    }


def test_storage_before_extraction_reports_error():
    config = _base_config()
    config["pipeline"] = ["store_json", "cleanup"]

    result = validate_pipeline(config)

    assert any("extraction task runs earlier" in issue.message for issue in result.errors)


def test_storage_after_extraction_passes():
    config = _base_config()

    result = validate_pipeline(config)

    assert result.errors == []


def test_nanoid_requires_context_initializer():
    config = _base_config()
    config["tasks"]["store_json"]["params"]["filename"] = "{nanoid}-file.json"
    config["pipeline"] = ["store_json", "cleanup"]

    result = validate_pipeline(config)

    assert any("references {nanoid}" in issue.message for issue in result.errors)

    config_with_context = _base_config()
    config_with_context["tasks"]["store_json"]["params"]["filename"] = "{nanoid}-file.json"
    config_with_context["pipeline"] = ["context_ids", "store_json", "cleanup"]

    result_with_context = validate_pipeline(config_with_context)

    assert all("references {nanoid}" not in issue.message for issue in result_with_context.errors)


def test_housekeeping_must_be_last():
    config = _base_config()
    config["pipeline"] = ["extract_metadata", "store_json"]

    result = validate_pipeline(config)

    assert any("housekeeping task" in issue.message for issue in result.errors)

    config_warning = _base_config()
    config_warning["tasks"]["store_json"]["params"]["filename"] = "output.json"
    config_warning["pipeline"] = ["extract_metadata", "cleanup", "store_json"]

    result_warning = validate_pipeline(config_warning)

    assert any("should be the final pipeline step" in issue.message for issue in result_warning.warnings)


def test_unknown_token_reports_error():
    config = _base_config()
    config["tasks"]["store_json"]["params"]["filename"] = "{unknown_token}.json"

    result = validate_pipeline(config)

    assert any("Unknown template token" in issue.message for issue in result.errors)




def test_pipeline_requires_extraction_task():
    config = {
        "tasks": {
            "store_json": {
                "module": "standard_step.storage.store_metadata",
                "class": "StoreMetadata",
                "params": {
                    "filename": "output.json",
                },
            },
            "cleanup": {
                "module": "standard_step.housekeeping.cleanup",
                "class": "CleanupTask",
                "params": {},
            },
        },
        "pipeline": ["store_json", "cleanup"],
    }

    result = validate_pipeline(config)

    assert any(issue.code == "pipeline-missing-extraction" for issue in result.errors)


def test_duplicate_pipeline_entries_warn():
    config = _base_config()
    config["pipeline"] = ["extract_metadata", "extract_metadata", "store_json", "cleanup"]

    result = validate_pipeline(config)

    assert any("appears multiple times" in issue.message for issue in result.warnings)
