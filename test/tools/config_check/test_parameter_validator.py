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
                "api_key": "llx-test-key",
                "agent_id": "agent-001",
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

def test_extraction_requires_api_key():
    tasks = _base_tasks()
    tasks["extract_metadata"]["params"].pop("api_key")

    result = validate_parameters({"tasks": tasks})

    assert any(issue.code == "param-extraction-missing-api-key" for issue in result.errors)

def test_extraction_requires_agent_id():
    tasks = _base_tasks()
    tasks["extract_metadata"]["params"]["agent_id"] = "   "

    result = validate_parameters({"tasks": tasks})

    assert any(issue.code == "param-extraction-missing-agent-id" for issue in result.errors)

def test_extraction_rejects_blank_api_key():
    tasks = _base_tasks()
    tasks["extract_metadata"]["params"]["api_key"] = "   "

    result = validate_parameters({"tasks": tasks})

    assert any(issue.code == "param-extraction-missing-api-key" for issue in result.errors)

def test_custom_extraction_requires_credentials():
    tasks = _base_tasks()
    tasks["custom_extract"] = {
        "module": "custom_step.extraction.invoice_task",
        "class": "CustomExtract",
        "params": {
            "api_key": "llx-test-key",
            "fields": {
                "invoice_number": {
                    "alias": "Invoice",
                    "type": "str",
                }
            },
        },
    }

    result = validate_parameters({"tasks": tasks})

    assert any(
        issue.code == "param-extraction-missing-agent-id"
        and issue.path == "tasks.custom_extract.params.agent_id"
        for issue in result.errors
    )


def test_multiple_table_fields_emit_warning():
    tasks = _base_tasks()
    fields = tasks["extract_metadata"]["params"]["fields"]
    fields["line_items"] = {
        "alias": "Line Items",
        "type": "List[Any]",
        "is_table": True,
        "item_fields": {
            "sku": {
                "alias": "SKU",
                "type": "str",
            }
        },
    }
    fields["charges"] = {
        "alias": "Charges",
        "type": "List[Any]",
        "is_table": True,
        "item_fields": {
            "code": {
                "alias": "Code",
                "type": "str",
            }
        },
    }

    result = validate_parameters({"tasks": tasks})

    assert result.errors == []
    assert any(issue.code == "param-extraction-multiple-tables" for issue in result.warnings)


def test_storage_requires_data_dir_and_filename():
    tasks = _base_tasks()
    tasks["store_json"]["params"].pop("data_dir")

    result = validate_parameters({"tasks": tasks})

    assert any("data_dir" in issue.path for issue in result.errors)



def test_storage_accepts_nested_overrides():
    tasks = _base_tasks()
    tasks["store_json"]["params"]["storage"] = {
        "data_dir": "./override",
        "filename": "{supplier_name}.jsonl",
    }

    result = validate_parameters({"tasks": tasks})

    assert result.errors == []
    assert all(issue.code != "param-storage-unknown-storage-key" for issue in result.warnings)



def test_storage_nested_missing_key_uses_top_level():
    tasks = _base_tasks()
    tasks["store_json"]["params"]["storage"] = {
        "filename": "{supplier_name}.json",
    }

    result = validate_parameters({"tasks": tasks})

    assert result.errors == []



def test_storage_nested_overrides_replace_top_level():
    tasks = _base_tasks()
    tasks["store_json"]["params"].pop("data_dir")
    tasks["store_json"]["params"]["storage"] = {
        "data_dir": "./override",
        "filename": "{supplier_name}.json",
    }

    result = validate_parameters({"tasks": tasks})

    assert result.errors == []



def test_storage_unknown_storage_key_emits_warning():
    tasks = _base_tasks()
    tasks["store_json"]["params"]["storage"] = {
        "data_dir": "./out",
        "filename": "{supplier_name}.json",
        "mode": "append",
    }

    result = validate_parameters({"tasks": tasks})

    warning = next(
        (issue for issue in result.warnings if issue.code == "param-storage-unknown-storage-key"),
        None,
    )

    assert warning is not None
    assert warning.path.endswith("storage.mode")



def test_storage_storage_block_must_be_mapping():
    tasks = _base_tasks()
    tasks["store_json"]["params"]["storage"] = "append"

    result = validate_parameters({"tasks": tasks})

    assert any(issue.code == "param-storage-storage-block-type" for issue in result.errors)



def test_storage_nested_missing_filename_uses_top_level():
    tasks = _base_tasks()
    tasks["store_json"]["params"]["storage"] = {
        "data_dir": "./override",
    }

    result = validate_parameters({"tasks": tasks})

    assert result.errors == []




def test_localdrive_requires_files_dir(tmp_path):
    tasks = {
        "store_file_to_localdrive": {
            "module": "standard_step.storage.store_file_to_localdrive",
            "class": "StoreFileToLocaldrive",
            "params": {
                "filename": "{id}.pdf",
            },
        }
    }

    result = validate_parameters({"tasks": tasks})

    assert any(
        issue.code == "param-localdrive-missing-files-dir"
        for issue in result.errors
    )

def test_localdrive_requires_filename(tmp_path):
    tasks = {
        "store_file_to_localdrive": {
            "module": "standard_step.storage.store_file_to_localdrive",
            "class": "StoreFileToLocaldrive",
            "params": {
                "files_dir": str(tmp_path),
            },
        }
    }

    result = validate_parameters({"tasks": tasks})

    assert any(
        issue.code == "param-localdrive-missing-filename"
        for issue in result.errors
    )

def test_localdrive_files_dir_must_be_string():
    tasks = {
        "store_file_to_localdrive": {
            "module": "standard_step.storage.store_file_to_localdrive",
            "class": "StoreFileToLocaldrive",
            "params": {
                "files_dir": 123,
                "filename": "{id}.pdf",
            },
        }
    }

    result = validate_parameters({"tasks": tasks})

    assert any(
        issue.code == "param-localdrive-missing-files-dir"
        for issue in result.errors
    )

def test_localdrive_valid_configuration(tmp_path):
    tasks = {
        "store_file_to_localdrive": {
            "module": "standard_step.storage.store_file_to_localdrive",
            "class": "StoreFileToLocaldrive",
            "params": {
                "files_dir": str(tmp_path),
                "filename": "{id}.pdf",
            },
        }
    }

    result = validate_parameters({"tasks": tasks})

    assert result.errors == []

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


def test_rules_task_optional_knobs_validation():
    """Test validation of optional rules task knobs (Task 18)."""
    tasks = _base_tasks()

    # Test invalid write_value type
    rules_task = _rules_task()
    rules_task["params"]["write_value"] = 123  # Should be string
    tasks["update_reference"] = rules_task

    result = validate_parameters({"tasks": tasks})
    assert any(issue.code == "param-rules-invalid-write-value" for issue in result.errors)

    # Test invalid backup type
    rules_task = _rules_task()
    rules_task["params"]["backup"] = "true"  # Should be boolean
    tasks["update_reference"] = rules_task

    result = validate_parameters({"tasks": tasks})
    assert any(issue.code == "param-rules-invalid-backup" for issue in result.errors)

    # Test invalid task_slug type
    rules_task = _rules_task()
    rules_task["params"]["task_slug"] = 123  # Should be string
    tasks["update_reference"] = rules_task

    result = validate_parameters({"tasks": tasks})
    assert any(issue.code == "param-rules-invalid-task-slug" for issue in result.errors)

    # Test valid optional knobs
    rules_task = _rules_task()
    rules_task["params"]["write_value"] = "Updated"
    rules_task["params"]["backup"] = False
    rules_task["params"]["task_slug"] = "custom_rules_task"
    tasks["update_reference"] = rules_task

    result = validate_parameters({"tasks": tasks})
    # Should not have errors for the optional knobs
    knob_errors = [issue for issue in result.errors if "invalid" in issue.code and any(
        knob in issue.path for knob in ["write_value", "backup", "task_slug"]
    )]
    assert len(knob_errors) == 0


def test_housekeeping_processing_dir_validation():
    """Test CleanupTask processing_dir validation (Task 18)."""
    tasks = _base_tasks()

    # Test invalid processing_dir type
    tasks["cleanup_task"] = {
        "module": "standard_step.housekeeping.cleanup_task",
        "class": "CleanupTask",
        "params": {
            "processing_dir": 123  # Should be string
        }
    }

    result = validate_parameters({"tasks": tasks})
    assert any(issue.code == "param-housekeeping-processing-dir-invalid" for issue in result.errors)

    # Test empty processing_dir
    tasks["cleanup_task"]["params"]["processing_dir"] = ""
    result = validate_parameters({"tasks": tasks})
    assert any(issue.code == "param-housekeeping-processing-dir-invalid" for issue in result.errors)

    # Test valid processing_dir
    tasks["cleanup_task"]["params"]["processing_dir"] = "processing"
    result = validate_parameters({"tasks": tasks})
    # Should not have processing_dir errors
    processing_dir_errors = [
        issue for issue in result.errors
        if issue.code == "param-housekeeping-processing-dir-invalid"
    ]
    assert len(processing_dir_errors) == 0


def test_housekeeping_params_must_be_mapping():
    """Test that housekeeping task params must be a mapping."""
    tasks = _base_tasks()

    tasks["cleanup_task"] = {
        "module": "standard_step.housekeeping.cleanup_task",
        "class": "CleanupTask",
        "params": "invalid"  # Should be dict
    }

    result = validate_parameters({"tasks": tasks})
    assert any(issue.code == "param-housekeeping-not-mapping" for issue in result.errors)
