import os
import io
from pathlib import Path
import pytest
import pandas as pd
import logging
from unittest.mock import patch, MagicMock, mock_open

from standard_step.rules.update_reference import UpdateReferenceTask, TaskError
from modules.utils import resolve_field, normalize_field_path

# Shared fixtures consolidated for both original files

@pytest.fixture
def sample_context():
    # Consolidated context covering both variants used by original tests
    return {
        "id": "test123",
        "data": {
            "supplier_name": "Supplier Inc with invoice and policy",
            "client_name": "Client LLC",
            "policy_number": "POL456",  # Matches second row in sample CSV
            "line_items": [
                {"sku": "ITEM001", "quantity": 5},
                {"sku": "ITEM002", "quantity": 3}
            ]
        }
    }


@pytest.fixture
def sample_csv_data():
    # Consolidated DataFrame matching structures used across tests
    data = {
        "policy_number": ["POL123", "POL456", "POL789"],
        "sku": ["ITEM999", "ITEM001", "ITEM002"],
        "status": ["old_status", "old_status", "old_status"]
    }
    return pd.DataFrame(data)


def make_task(params=None):
    params = params or {}
    # Default configuration used by most tests
    params.setdefault("reference_file", "test/data/reference_file.csv")
    params.setdefault("update_field", "status")
    params.setdefault("write_value", "MATCHED")
    params.setdefault(
        "csv_match",
        {
            "type": "column_equals_all",
            "clauses": [
                {"column": "policy_number", "from_context": "policy_number", "number": False},
            ],
        },
    )
    params.setdefault("backup", True)
    params.setdefault("task_slug", "update_csv_reference")
    return UpdateReferenceTask(config_manager=MagicMock(), **params)


# Update Reference Tests
# (From test_update_reference.py)

def test_validate_required_fields_columns_exist():
    task = make_task()
    # Header missing update_field should error
    with patch("pandas.read_csv") as mock_read_csv:
        mock_read_csv.return_value = pd.DataFrame(columns=["policy_number"])
        with pytest.raises(TaskError, match="missing required update_field column"):
            task.validate_required_fields({})

    # Header missing selection column should error
    with patch("pandas.read_csv") as mock_read_csv:
        mock_read_csv.return_value = pd.DataFrame(columns=["status"])
        with pytest.raises(TaskError, match="missing required selection column"):
            task.validate_required_fields({})


def test_column_equals_all_single_clause(sample_context, sample_csv_data):
    task = make_task()
    # Should match second row by policy_number "POL456"
    mask = task._build_selection_mask(sample_csv_data, sample_context)
    assert mask.tolist() == [False, True, False]

    # Test different policy number
    context = {"data": {"policy_number": "POL789"}}
    mask = task._build_selection_mask(sample_csv_data, context)
    assert mask.tolist() == [False, False, True]


def test_column_equals_all_clauses_mapping():
    task = make_task()
    assert len(task.clauses) == 1
    assert task.clauses[0].column == "policy_number"
    assert task.clauses[0].from_context == "data.policy_number"  # normalized from bare name
    assert task.clauses[0].number is False


@patch("pandas.read_csv")
@patch("os.replace")
@patch("builtins.open", new_callable=mock_open, read_data="policy_number,status\nPOL123,old_status\nPOL456,old_status\nPOL789,old_status\n")
def test_correct_update_and_atomic_write(mock_file, mock_replace, mock_read_csv, sample_context):
    # Setup DataFrame matching test CSV
    df = pd.DataFrame({
        "policy_number": ["POL123", "POL456", "POL789"],
        "status": ["old_status", "old_status", "old_status"]
    })
    mock_read_csv.return_value = df.copy()

    task = make_task()
    # Patch _atomic_write_df to call real method but mock file ops inside
    with patch.object(task, "_atomic_write_df", wraps=task._atomic_write_df) as atomic_write_mock:
        context_out = task.run(sample_context)

    # Check that update_col is updated correctly in the DataFrame passed to _atomic_write_df
    written_df = atomic_write_mock.call_args[0][1]
    # Should update status for matching row (POL456)
    assert written_df.loc[1, "status"] == "MATCHED"
    # Other rows remain unchanged
    assert written_df.loc[0, "status"] == "old_status"
    assert written_df.loc[2, "status"] == "old_status"

    # Check context output keys
    assert "data" in context_out
    assert "update_reference" in context_out["data"]
    assert context_out["data"]["update_reference"]["updated_rows"] == 1
    assert context_out["data"]["update_reference"]["selected_rows"] == 1


@patch("pandas.read_csv")
@patch("builtins.open", new_callable=mock_open, read_data="policy_number,status\nPOL123,old_status\n")
def test_backup_file_creation_and_atomic_write(mock_file, mock_read_csv):
    df = pd.DataFrame({
        "policy_number": ["POL123"],
        "status": ["old_status"]
    })
    mock_read_csv.return_value = df.copy()

    task = make_task()
    task.backup = True

    # Patch open to track calls for backup creation
    with patch("builtins.open", mock_open()) as m_open:
        with patch("os.replace") as m_replace:
            task._atomic_write_df(Path("test/data/reference_file.csv"), df)
            # Check that backup file was attempted to be created
            m_open.assert_any_call(Path("test/data/reference_file.csv"), "r", encoding="utf-8", newline="")
            m_open.assert_any_call(Path("test/data/reference_file.csv.backup"), "w", encoding="utf-8", newline="")
            m_replace.assert_called_once()


def test_error_handling_missing_file():
    task = make_task({"reference_file": "test/data/missing.csv"})
    with pytest.raises(TaskError, match="does not exist"):
        task.validate_required_fields({})


def test_error_handling_missing_columns():
    task = make_task()
    # Mock read_csv to return header missing status column
    with patch("pandas.read_csv") as mock_read_csv:
        mock_read_csv.return_value = pd.DataFrame(columns=["policy_number"])
        with pytest.raises(TaskError, match="missing required update_field column"):
            task.validate_required_fields({})

    # Mock read_csv to return header missing selection column(s)
    with patch("pandas.read_csv") as mock_read_csv:
        mock_read_csv.return_value = pd.DataFrame(columns=["status"])
        with pytest.raises(TaskError, match="missing required selection column"):
            task.validate_required_fields({})


@patch("pandas.read_csv")
def test_status_manager_integration(mock_read_csv):
    # Provide minimal valid DF so run() reaches success path
    mock_read_csv.return_value = pd.DataFrame({
        "policy_number": ["POL123"],
        "status": ["old_status"]
    })
    task = make_task()
    mock_status_manager = MagicMock()
    # Replace the instance's status_manager directly
    task.status_manager = mock_status_manager

    context = {"id": "uid123", "data": {"policy_number": "POL123"}}
    # Patch validate_required_fields to pass and avoid file writes
    with patch.object(task, "validate_required_fields", return_value=None):
        with patch.object(task, "_atomic_write_df", return_value=None):
            _ = task.run(context)

    # Check status_manager.update_status called for started and success
    assert mock_status_manager.update_status.call_count >= 2
    calls = [call.kwargs.get("status") for call in mock_status_manager.update_status.call_args_list]
    assert "Task Started: update_csv_reference" in calls
    assert "Task Completed: update_csv_reference" in calls


@patch("pandas.read_csv")
def test_status_manager_failure(mock_read_csv):
    mock_read_csv.return_value = pd.DataFrame({
        "policy_number": ["POL123"],
        "status": ["old_status"]
    })
    task = make_task()
    mock_status_manager = MagicMock()
    # Replace the instance's status_manager directly
    task.status_manager = mock_status_manager

    # Force validate_required_fields to raise TaskError
    with patch.object(task, "validate_required_fields", side_effect=TaskError("fail")):
        context = {"id": "uid123"}
        _ = task.run(context)

    # Check status_manager.update_status called for started and failed
    assert mock_status_manager.update_status.call_count >= 2
    calls = [call.kwargs.get("status") for call in mock_status_manager.update_status.call_args_list]
    assert "Task Started: update_csv_reference" in calls
    assert "Task Failed: update_csv_reference" in calls


# Additional tests for full coverage
def test_numeric_comparison_matching():
    # Numeric comparison: CSV value "3,000" matches context 3000 (float)
    df = pd.DataFrame({
        "policy_number": ["1000", "3,000", "2000"],
        "status": ["old", "old", "old"]
    })
    task = make_task({
        "csv_match": {
            "type": "column_equals_all",
            "clauses": [
                {"column": "policy_number", "from_context": "policy_number", "number": True},
            ],
        }
    })
    # Context numeric match for 3000
    context = {"data": {"policy_number": "3000"}}
    mask = task._build_selection_mask(df, context)
    assert mask.tolist() == [False, True, False]

    # Now force string mode: "3000" vs "3,000" should not match
    task = make_task({
        "csv_match": {
            "type": "column_equals_all",
            "clauses": [
                {"column": "policy_number", "from_context": "policy_number", "number": False},
            ],
        }
    })
    mask_str = task._build_selection_mask(df, context)
    assert mask_str.tolist() == [False, False, False]


def test_init_invalid_csv_match_type():
    with pytest.raises(TaskError, match="csv_match.type must be 'column_equals_all'"):
        make_task({"csv_match": {"type": "invalid"}})


def test_init_missing_csv_match_params():
    with pytest.raises(TaskError, match="csv_match.clauses must be a list with 1 to 5 items"):
        make_task({"csv_match": {"type": "column_equals_all"}})
    with pytest.raises(TaskError, match=r"requires 'column' and 'from_context'"):
        make_task({"csv_match": {"type": "column_equals_all", "clauses": [{}]}})


@patch("pandas.read_csv")
@patch("builtins.open", new_callable=mock_open, read_data="policy_number,status\nPOL123,old_status\n")
@patch("os.replace")
def test_run_write_value_applied_to_matches(mock_replace, mock_file, mock_read_csv):
    # Single-row CSV where policy_number matches context; should write write_value
    df = pd.DataFrame({"policy_number": ["POL123"], "status": ["old_status"]})
    mock_read_csv.return_value = df.copy()
    task = make_task({"write_value": "UPDATED"})
    context = {"id": "uid", "data": {"policy_number": "POL123"}}
    with patch.object(task, "_atomic_write_df", wraps=task._atomic_write_df) as atomic_mock:
        context_out = task.run(context)
    # selected_rows 1, updated_rows 1 (old_status->UPDATED)
    result = context_out["data"]["update_reference"]
    assert result["selected_rows"] == 1
    assert result["updated_rows"] == 1
    # Verify written DataFrame set UPDATED
    written_df = atomic_mock.call_args[0][1]
    assert written_df.loc[0, "status"] == "UPDATED"


@patch("pandas.read_csv")
def test_logs_warning_on_missing_context_value(mock_read_csv, caplog):
    # CSV has the selection column but context is missing the key -> should log a warning
    df = pd.DataFrame({"policy_number": ["POL123"], "status": ["old_status"]})
    mock_read_csv.return_value = df.copy()
    task = make_task()
    # Context 'data' exists but policy_number is missing
    context = {"id": "uid_warn", "data": {}}
    caplog.set_level(logging.WARNING)
    # Prevent actual file writes
    with patch.object(task, "_atomic_write_df", return_value=None):
        task.run(context)
    # Check that a warning about missing context value was emitted
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Missing context value for clause" in r.message for r in warnings)


def test_deprecation_warning_for_data_prefix(caplog):
    """Test that a deprecation warning is emitted when using 'data.' prefix in from_context."""
    # Create task with data. prefixed field
    params = {
        "csv_match": {
            "type": "column_equals_all",
            "clauses": [
                {"column": "policy_number", "from_context": "data.policy_number", "number": False},
            ],
        }
    }
    caplog.set_level(logging.WARNING)

    # This should trigger the deprecation warning during initialization
    task = make_task(params)

    # Check that a deprecation warning was emitted with the new format
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any('DeprecationWarning: "data."prefixed field paths are deprecated' in r.message for r in warnings)
    assert any('Provided: "data.policy_number"' in r.message for r in warnings)

    # Ensure the functionality still works - clause should be created normally
    assert len(task.clauses) == 1
    assert task.clauses[0].from_context == "data.policy_number"


def test_data_prefix_deprecation_warning_with_new_format(caplog):
    """Test that the new deprecation warning format is used for data. prefixed fields."""
    # Create task with data. prefixed field
    params = {
        "csv_match": {
            "type": "column_equals_all",
            "clauses": [
                {"column": "policy_number", "from_context": "data.policy_number", "number": False},
            ],
        }
    }
    caplog.set_level(logging.WARNING)

    # This should trigger the deprecation warning during initialization
    task = make_task(params)

    # Check that the new format deprecation warning was emitted
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    deprecation_warnings = [r for r in warnings if 'DeprecationWarning: "data."prefixed field paths are deprecated' in r.message]
    assert len(deprecation_warnings) == 1
    assert 'Provided: "data.policy_number"' in deprecation_warnings[0].message

    # Ensure the functionality still works - clause should be created normally
    assert len(task.clauses) == 1
    assert task.clauses[0].from_context == "data.policy_number"


def test_bare_name_vs_explicit_path_equivalence(sample_context, sample_csv_data):
    """Test that bare names and explicit data. paths resolve to the same values."""
    # Test with bare name
    task_bare = make_task({
        "csv_match": {
            "type": "column_equals_all",
            "clauses": [
                {"column": "policy_number", "from_context": "policy_number", "number": False},
            ],
        }
    })

    # Test with explicit data. path
    task_explicit = make_task({
        "csv_match": {
            "type": "column_equals_all",
            "clauses": [
                {"column": "policy_number", "from_context": "data.policy_number", "number": False},
            ],
        }
    })

    # Both should normalize to the same path
    assert task_bare.clauses[0].from_context == task_explicit.clauses[0].from_context == "data.policy_number"

    # Both should produce the same selection mask
    mask_bare = task_bare._build_selection_mask(sample_csv_data, sample_context)
    mask_explicit = task_explicit._build_selection_mask(sample_csv_data, sample_context)

    # Masks should be identical
    assert mask_bare.equals(mask_explicit)
    assert mask_bare.tolist() == [False, True, False]


# Update Reference Edge Cases Tests
# (From test_update_reference_edge_cases.py)


def test_both_formats_resolve_equivalently(sample_context, sample_csv_data, caplog):
    """Test that bare and 'data.' prefixed from_context resolve to the same selection mask."""
    # Bare name task
    task_bare = make_task({
        "csv_match": {
            "type": "column_equals_all",
            "clauses": [{"column": "policy_number", "from_context": "policy_number", "number": False}],
        }
    })

    # Explicit 'data.' prefixed task (should trigger deprecation but function equivalently)
    task_explicit = UpdateReferenceTask(
        config_manager=MagicMock(),
        reference_file="test/data/reference_file.csv",
        update_field="status",
        write_value="MATCHED",
        backup=True,
        task_slug="update_csv_reference",
        csv_match={
            "type": "column_equals_all",
            "clauses": [{"column": "policy_number", "from_context": "data.policy_number", "number": False}],
        }
    )

    # Both should produce the same mask (matching second row)
    mask_bare = task_bare._build_selection_mask(sample_csv_data, sample_context)
    mask_explicit = task_explicit._build_selection_mask(sample_csv_data, sample_context)

    assert mask_bare.equals(mask_explicit)
    assert mask_bare.tolist() == [False, True, False]

    # Verify deprecation warning only for explicit
    caplog.set_level("WARNING")
    _ = task_bare  # No warning for bare
    _ = task_explicit  # Warning for explicit
    warnings = [r for r in caplog.records if "DeprecationWarning" in r.message]
    assert len(warnings) == 1
    assert "data.policy_number" in warnings[0].message


def test_nested_array_field_resolution(sample_context, sample_csv_data):
    """Test resolution of nested array fields like 'line_items.0.sku'."""
    # sample_csv_data already has sku column per fixture

    task = UpdateReferenceTask(
        config_manager=MagicMock(),
        reference_file="test/data/reference_file.csv",
        update_field="status",
        write_value="MATCHED",
        backup=True,
        task_slug="update_csv_reference",
        csv_match={
            "type": "column_equals_all",
            "clauses": [{"column": "sku", "from_context": "data.line_items.0.sku", "number": False}],
        }
    )

    # Should match second row where sku == "ITEM001"
    mask = task._build_selection_mask(sample_csv_data, sample_context)
    assert mask.tolist() == [False, True, False]

    # Verify the field resolution works via utils
    resolved_sku, exists = resolve_field(sample_context, "data.line_items.0.sku")
    assert exists
    assert resolved_sku == "ITEM001"


def test_invalid_format_rejected():
    """Test that invalid from_context (empty or non-string) raises TaskError during init."""
    # Empty string
    with pytest.raises(TaskError, match="requires 'column' and 'from_context'"):
        UpdateReferenceTask(
            config_manager=MagicMock(),
            reference_file="test/data/reference_file.csv",
            update_field="status",
            write_value="MATCHED",
            csv_match={
                "type": "column_equals_all",
                "clauses": [{"column": "policy_number", "from_context": ""}],
            }
        )

    # Non-string in clause (None) - should raise TaskError as falsy
    with pytest.raises(TaskError, match="requires 'column' and 'from_context'"):
        UpdateReferenceTask(
            config_manager=MagicMock(),
            reference_file="test/data/reference_file.csv",
            update_field="status",
            write_value="MATCHED",
            csv_match={
                "type": "column_equals_all",
                "clauses": [{"column": "policy_number", "from_context": None}],
            }
        )

    # Non-string in clause (int) - should raise ValueError from normalize_field_path
    with pytest.raises(ValueError, match="Field must be a string"):
        UpdateReferenceTask(
            config_manager=MagicMock(),
            reference_file="test/data/reference_file.csv",
            update_field="status",
            write_value="MATCHED",
            csv_match={
                "type": "column_equals_all",
                "clauses": [{"column": "policy_number", "from_context": 123}],
            }
        )


def test_deprecation_log_emitted_only_for_data_prefix(caplog):
    """Ensure deprecation warning only for explicit 'data.' prefix, not other roots."""
    caplog.set_level("WARNING")

    # Case 1: Bare name - no warning, normalizes to data.
    task_bare = UpdateReferenceTask(
        config_manager=MagicMock(),
        reference_file="test/data/reference_file.csv",
        update_field="status",
        write_value="MATCHED",
        csv_match={
            "type": "column_equals_all",
            "clauses": [{"column": "owner", "from_context": "owner", "number": False}],
        }
    )
    assert task_bare.clauses[0].from_context == "data.owner"
    warnings = [r for r in caplog.records if "DeprecationWarning" in r.message]
    assert len(warnings) == 0

    # Case 2: Explicit 'data.' - warning emitted
    task_data = UpdateReferenceTask(
        config_manager=MagicMock(),
        reference_file="test/data/reference_file.csv",
        update_field="status",
        write_value="MATCHED",
        csv_match={
            "type": "column_equals_all",
            "clauses": [{"column": "owner", "from_context": "data.owner", "number": False}],
        }
    )
    assert task_data.clauses[0].from_context == "data.owner"
    warnings_data = [r for r in caplog.records if "DeprecationWarning" in r.message]
    assert len(warnings_data) == 1
    assert "data.owner" in warnings_data[0].message

    # Case 3: Explicit other root like 'metadata.' - no warning
    task_other = UpdateReferenceTask(
        config_manager=MagicMock(),
        reference_file="test/data/reference_file.csv",
        update_field="status",
        write_value="MATCHED",
        csv_match={
            "type": "column_equals_all",
            "clauses": [{"column": "owner", "from_context": "metadata.owner", "number": False}],
        }
    )
    assert task_other.clauses[0].from_context == "metadata.owner"
    warnings_other = [r for r in caplog.records if "DeprecationWarning" in r.message]
    # Total warnings should still be 1 (only from data. case)
    assert len(warnings_other) == 1  # No additional warning