"""Unit tests for parameter validation logic.

This module contains comprehensive unit tests for the parameter validation functionality,
testing various parameter validation scenarios across different task types in the
PDF document extraction system.

The test suite covers parameter validation for:
- Extraction tasks: Field definitions with type specifications and table validation
- Storage tasks: Required string parameters (data_dir, filename)
- Archiver tasks: Required string parameters (archive_dir)
- Context tasks: Optional length parameter with constraint validation

Key Features:
- Task classification-based parameter validation testing
- Field definition validation with comprehensive type checking
- Table field validation with nested item_fields requirements
- Boundary testing for numeric constraints (context length)
- Error condition testing for missing required parameters
- Windows-compatible test data and path handling

Test Scenarios:
    - Missing required field properties (alias, type)
    - Invalid field type specifications
    - Table fields without required item_fields
    - Missing required parameters for storage and archiver tasks
    - Context length parameter boundary validation
    - Invalid parameter structure validation

Test Data:
    Uses realistic task configurations with Windows-compatible paths
    and field definitions that mirror actual PDF processing scenarios.

Note:
    All tests are designed to run in the Windows environment and
    validate both success and failure scenarios for parameter validation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from tools.config_check.parameter_validator import validate_parameters  # noqa: E402


def _base_tasks():
    return {
        "extract_metadata": {
            "module": "standard_step.extraction.extract_metadata",
            "class": "ExtractMetadata",
            "params": {
                "fields": {
                    "supplier_name": {
                        "alias": "Supplier",
                        "type": "str",
                    }
                }
            },
        },
        "store_json": {
            "module": "standard_step.storage.store_metadata",
            "class": "StoreMetadata",
            "params": {
                "data_dir": "./out",
                "filename": "{supplier_name}.json",
            },
        },
        "archive": {
            "module": "standard_step.archiver.archive_output",
            "class": "ArchiveOutput",
            "params": {
                "archive_dir": "./archive",
            },
        },
        "context_ids": {
            "module": "standard_step.context.generate_ids",
            "class": "GenerateIds",
            "params": {},
        },
    }


def _rules_task():
    return {
        "module": "standard_step.rules.update_reference",
        "class": "UpdateReferenceTask",
        "params": {
            "reference_file": "C:/data/reference.csv",
            "update_field": "status",
            "write_value": "Processed",
            "csv_match": {
                "type": "column_equals_all",
                "clauses": [
                    {
                        "column": "id",
                        "from_context": "id",
                    }
                ],
            },
        },
    }


def test_extraction_fields_require_alias_and_type():
    tasks = _base_tasks()
    tasks["extract_metadata"]["params"]["fields"]["supplier_name"].pop("alias")

    result = validate_parameters({"tasks": tasks})

    assert any(issue.path.endswith("alias") for issue in result.errors)


def test_extraction_table_requires_item_fields():
    tasks = _base_tasks()
    tasks["extract_metadata"]["params"]["fields"]["supplier_name"]["is_table"] = True

    result = validate_parameters({"tasks": tasks})

    assert any("item_fields" in issue.path for issue in result.errors)


def test_invalid_field_type_reports_error():
    tasks = _base_tasks()
    tasks["extract_metadata"]["params"]["fields"]["supplier_name"]["type"] = "InvalidType"

    result = validate_parameters({"tasks": tasks})

    assert any("Field type" in issue.message for issue in result.errors)


def test_storage_requires_data_dir_and_filename():
    tasks = _base_tasks()
    tasks["store_json"]["params"].pop("data_dir")

    result = validate_parameters({"tasks": tasks})

    assert any("data_dir" in issue.path for issue in result.errors)


def test_archiver_requires_archive_dir():
    tasks = _base_tasks()
    tasks["archive"]["params"].pop("archive_dir")

    result = validate_parameters({"tasks": tasks})

    assert any("archive_dir" in issue.path for issue in result.errors)


def test_context_length_bounds():
    tasks = _base_tasks()
    tasks["context_ids"]["params"]["length"] = 30

    result = validate_parameters({"tasks": tasks})

    assert any("length" in issue.path for issue in result.errors)

    tasks["context_ids"]["params"]["length"] = 10
    result_ok = validate_parameters({"tasks": tasks})

    assert all("length" not in issue.path for issue in result_ok.errors)


def test_params_must_be_mapping():
    tasks = _base_tasks()
    tasks["store_json"]["params"] = "invalid"

    result = validate_parameters({"tasks": tasks})

    assert any("must be a mapping" in issue.message for issue in result.errors)

def test_rules_task_requires_core_parameters():
    tasks = _base_tasks()
    rules_task = _rules_task()
    rules_task["params"].pop("reference_file")
    rules_task["params"].pop("update_field")
    tasks["update_reference"] = rules_task

    result = validate_parameters({"tasks": tasks})
    codes = {issue.code for issue in result.errors}

    assert "param-rules-missing-reference-file" in codes
    assert "param-rules-missing-update-field" in codes


def test_rules_task_enforces_clause_bounds():
    tasks = _base_tasks()
    rules_task = _rules_task()
    rules_task["params"]["csv_match"]["clauses"] = []
    tasks["update_reference"] = rules_task

    result = validate_parameters({"tasks": tasks})
    assert any(issue.code == "param-rules-clauses-count" for issue in result.errors)

    tasks = _base_tasks()
    rules_task = _rules_task()
    rules_task["params"]["csv_match"]["clauses"] = [
        {"column": f"col{i}", "from_context": "value"} for i in range(6)
    ]
    tasks["update_reference"] = rules_task

    result = validate_parameters({"tasks": tasks})
    assert any(issue.code == "param-rules-clauses-count" for issue in result.errors)


def test_rules_task_validates_csv_match_mapping():
    tasks = _base_tasks()
    rules_task = _rules_task()
    rules_task["params"]["csv_match"] = "invalid"
    tasks["update_reference"] = rules_task

    result = validate_parameters({"tasks": tasks})

    assert any(issue.code == "param-rules-csv-match-mapping" for issue in result.errors)


def test_rules_task_validates_clause_structure():
    tasks = _base_tasks()
    rules_task = _rules_task()
    rules_task["params"]["csv_match"]["clauses"] = [
        {"column": "", "from_context": ""},
        {"column": "status", "from_context": "status", "number": "yes"},
    ]
    tasks["update_reference"] = rules_task

    result = validate_parameters({"tasks": tasks})
    codes = {issue.code for issue in result.errors}

    assert "param-rules-clause-column" in codes
    assert "param-rules-clause-context" in codes
    assert "param-rules-clause-number-type" in codes
