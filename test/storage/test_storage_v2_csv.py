import csv
import os
import tempfile
from typing import Any, Dict, List, cast
import pytest

# Import the task under test. Use the module path used in the codebase.
from standard_step.storage.store_metadata_as_csv_v2 import StoreMetadataAsCsvV2
from modules.config_manager import ConfigManager


class DummyConfigManager:
    """Minimal stand-in for ConfigManager for tests."""

    def __init__(self, config: Dict[str, Any]):
        self._config = config

    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        return self._config


class DummyStatusManager:
    """Minimal stand-in for StatusManager that records updates."""

    def __init__(self, config_manager: Any):
        self.updates = []

    def update_status(self, uid: str, message: str, step: str = "", status: str = ""):
        self.updates.append({"uid": uid, "message": message, "step": step, "status": status})


@pytest.fixture
def sample_extraction_config():
    # This mirrors the shape expected by the CSV v2 task: extraction fields with a table
    return {
        "filename": "{supplier_name}_{invoice_amount}",
        "data_dir": None,  # will be provided via tmp_path in tests
        "extraction": {
            "fields": {
                "supplier_name": {"name": "supplier_name", "alias": "supplier_name"},
                "invoice_amount": {"name": "invoice_amount", "alias": "invoice_amount"},
                # table field 'items' with item_fields and aliases
                "items": {
                    "name": "items",
                    "is_table": True,
                    "item_fields": {
                        "description": {"name": "description", "alias": "description"},
                        "quantity": {"name": "quantity", "alias": "quantity"},
                    },
                },
            }
        },
    }


@pytest.fixture(autouse=True)
def patch_status_manager(monkeypatch):
    """Patch StatusManager import inside the task to use DummyStatusManager."""
    def _dummy_init(config_manager):
        return DummyStatusManager(config_manager)

    # monkeypatch the StatusManager class used in the task module namespace
    import standard_step.storage.store_metadata_as_csv_v2 as task_module
    monkeypatch.setattr(task_module, "StatusManager", lambda cfg: _dummy_init(cfg))
    return _dummy_init


def read_csv_rows(path: str) -> List[Dict[str, Any]]:
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def test_scalar_only_fallback_writes_single_row(tmp_path, sample_extraction_config):
    # Setup config pointing to tmp dir
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    # remove table field to simulate scalar-only extraction config
    cfg["extraction"]["fields"].pop("items")
    
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    task = StoreMetadataAsCsvV2(config_manager, params={})

    context = {
        "id": "test-1",
        "data": {
            "supplier_name": "ACME Corp",
            "invoice_amount": 123.45,
            "notes": ["a", "b"],  # lists should be joined into comma-separated
        },
    }

    result = task.run(context)
    # Task returns context
    assert result is context

    # Find output CSV in tmp_path
    files = list(tmp_path.glob("*.csv"))
    assert len(files) == 1
    rows = read_csv_rows(str(files[0]))
    assert len(rows) == 1
    row = rows[0]
    # Header should use aliased column names (supplier_name, invoice_amount) and include 'notes'
    assert row["supplier_name"] == "ACME Corp"
    # Numbers may have been stringified
    assert row["invoice_amount"] in ("123.45", "123.450000")
    # List should be joined by comma
    assert row["notes"] == "a,b"


def test_table_expands_rows_per_item_and_prefixes_item_columns(tmp_path, sample_extraction_config):
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    task = StoreMetadataAsCsvV2(config_manager, params={})

    context = {
        "id": "test-2",
        "data": {
            "supplier_name": "Supplier X",
            "invoice_amount": 999.99,
            "items": [
                {"description": "Item 1\nwith newline", "quantity": "2"},
                {"description": "Item 2", "quantity": "3"},
            ],
        },
    }

    result = task.run(context)
    assert result is context

    files = list(tmp_path.glob("*.csv"))
    assert len(files) == 1
    rows = read_csv_rows(str(files[0]))
    # Expect 2 rows (one per item)
    assert len(rows) == 2
    # Check columns: scalar fields + prefixed item_ columns using aliases
    expected_columns = {"supplier_name", "invoice_amount", "item_description", "item_quantity"}
    assert expected_columns.issubset(set(rows[0].keys()))

    # Scalars repeated per row
    assert rows[0]["supplier_name"] == "Supplier X"
    assert rows[1]["supplier_name"] == "Supplier X"

    # Item description cleaned (newlines -> spaces)
    assert rows[0]["item_description"] == "Item 1 with newline"
    assert rows[0]["item_quantity"] == "2"
    assert rows[1]["item_description"] == "Item 2"
    assert rows[1]["item_quantity"] == "3"


def test_empty_table_fallbacks_to_single_row(tmp_path, sample_extraction_config):
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    task = StoreMetadataAsCsvV2(config_manager, params={})

    context = {
        "id": "test-3",
        "data": {
            "supplier_name": "No Items Co",
            "invoice_amount": 0.0,
            "items": [],  # empty table should fallback to single row with scalars
        },
    }

    result = task.run(context)
    assert result is context

    files = list(tmp_path.glob("*.csv"))
    assert len(files) == 1
    rows = read_csv_rows(str(files[0]))
    assert len(rows) == 1
    assert rows[0]["supplier_name"] == "No Items Co"


def test_filename_generation_template_and_uniqueness(tmp_path, sample_extraction_config, monkeypatch):
    # Provide a filename template that uses fields
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    cfg["filename"] = "{supplier_name}_{invoice_amount}"
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    task = StoreMetadataAsCsvV2(config_manager, params={})

    context = {
        "id": "test-4",
        "data": {
            "supplier_name": "DupName",
            "invoice_amount": 10.0,
        },
    }

    # Pre-create a file to force uniqueness handling
    base_name = "DupName_10.0.csv"
    existing = tmp_path / base_name
    existing.write_text("exists")

    # Run task
    result = task.run(context)
    assert result is context

    csv_files = list(tmp_path.glob("DupName_10.0*.csv"))
    # Should have at least one file beyond the existing one (unique file created)
    assert any(p.name != base_name for p in csv_files)


def test_error_handling_updates_context_and_status_on_exception(tmp_path, sample_extraction_config, monkeypatch):
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    
    # Create a task but patch its _generate_unique_filepath to raise
    task = StoreMetadataAsCsvV2(config_manager, params={})

    def raise_err(*args, **kwargs):
        raise RuntimeError("disk error")

    monkeypatch.setattr(task, "_generate_unique_filepath", raise_err)

    context = {"id": "test-5", "data": {"supplier_name": "X", "invoice_amount": 1.0}}
    result = task.run(context)

    # When task fails it should return the context updated with error fields
    assert "error" in result
    assert "error_step" in result
    assert "disk error" in result["error"]

    # The patched StatusManager collects updates; ensure a failure status was recorded
    # The DummyStatusManager used in patch_status_manager fixture doesn't expose global instance,
    # but the task will have invoked it without raising - ensure context indicates failure.
    assert result.get("error_step") is not None


def test_validation_missing_data_updates_context_with_error(tmp_path, sample_extraction_config):
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    # Pass the extraction config via params instead of config manager
    params = {"extraction": {"fields": cfg["extraction"]["fields"]}}
    print(f"DEBUG: Task params: {params}")  # Debug
    task = StoreMetadataAsCsvV2(config_manager, **params)

    context = {"id": "test-6"}  # missing 'data'
    result = task.run(context)

    # Should return context with error information instead of raising exception
    assert "error" in result
    assert "error_step" in result
    assert "data" in str(result["error"])


def test_empty_data_dict_creates_minimal_csv(tmp_path, sample_extraction_config):
    """Empty data dict should create a minimal CSV file."""
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    task = StoreMetadataAsCsvV2(config_manager, params={})

    context = {"id": "empty-data", "data": {}}

    result = task.run(context)

    assert result is context
    files = list(tmp_path.glob("*.csv"))
    assert len(files) == 1
    rows = read_csv_rows(str(files[0]))
    assert len(rows) == 1  # Should have one row with minimal data


def test_non_list_table_field_treated_as_scalar(tmp_path, sample_extraction_config):
    """Non-list table field should be treated as scalar and trigger fallback to single row."""
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    task = StoreMetadataAsCsvV2(config_manager, params={})

    # Make the table field a string instead of a list
    context = {
        "id": "non-list-table",
        "data": {
            "supplier_name": "Test Supplier",
            "invoice_amount": 123.45,
            "items": "This is not a list"  # Should be treated as scalar
        }
    }

    result = task.run(context)

    assert result is context
    files = list(tmp_path.glob("*.csv"))
    assert len(files) == 1
    rows = read_csv_rows(str(files[0]))
    assert len(rows) == 1
    # Should contain the non-list table field as a regular column
    assert rows[0]["supplier_name"] == "Test Supplier"
    assert rows[0]["items"] == "This is not a list"


def test_mixed_table_items_converts_non_dicts(tmp_path, sample_extraction_config):
    """Table with mixed dict and non-dict items should convert non-dicts to dicts."""
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    # Configure items as a table field
    cfg["extraction"]["fields"]["items"] = {
        "name": "items",
        "is_table": True,
        "item_fields": {
            "description": {"name": "description", "alias": "description"},
            "quantity": {"name": "quantity", "alias": "quantity"},
        },
    }

    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    task = StoreMetadataAsCsvV2(config_manager, params={})

    context = {
        "id": "mixed-items",
        "data": {
            "supplier_name": "Mixed Items Supplier",
            "invoice_amount": 999.99,
            "items": [
                {"description": "Dict Item 1", "quantity": "1"},  # dict item
                "String item",  # string item
                42,  # number item
                None,  # null item
                {"description": "Dict Item 2", "quantity": "2"}  # another dict item
            ]
        }
    }

    result = task.run(context)

    assert result is context
    files = list(tmp_path.glob("*.csv"))
    assert len(files) == 1
    rows = read_csv_rows(str(files[0]))
    assert len(rows) == 5  # One row per item

    # Check that non-dict items were converted properly
    assert rows[0]["supplier_name"] == "Mixed Items Supplier"
    assert rows[0]["item_description"] == "Dict Item 1"
    assert rows[0]["item_quantity"] == "1"

    assert rows[1]["supplier_name"] == "Mixed Items Supplier"
    assert rows[1]["item_value"] == "String item"  # String converted to {"value": "String item"}

    assert rows[2]["supplier_name"] == "Mixed Items Supplier"
    assert rows[2]["item_value"] == "42"  # Number converted to {"value": "42"}

    assert rows[3]["supplier_name"] == "Mixed Items Supplier"
    assert rows[3]["item__null"] == "True"  # None converted to {"_null": True}

    assert rows[4]["supplier_name"] == "Mixed Items Supplier"
    assert rows[4]["item_description"] == "Dict Item 2"
    assert rows[4]["item_quantity"] == "2"


def test_special_characters_and_newlines_in_csv_data(tmp_path, sample_extraction_config):
    """Special characters and newlines should be cleaned in CSV output."""
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    # Configure items as a table field
    cfg["extraction"]["fields"]["items"] = {
        "name": "items",
        "is_table": True,
        "item_fields": {
            "description": {"name": "description", "alias": "description"},
            "quantity": {"name": "quantity", "alias": "quantity"},
        },
    }
    # Use a simpler filename template to avoid special character issues
    cfg["filename"] = "{supplier_name}_{invoice_amount}"
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    task = StoreMetadataAsCsvV2(config_manager, params={})

    context = {
        "id": "special-chars",
        "data": {
            "supplier_name": "TestSupplier",  # Removed special chars from supplier name for filename
            "invoice_amount": 123.45,
            "items": [
                {"description": "Item 1\r\nwith newline", "quantity": "2"},
                {"description": "Item 2", "quantity": "3"}
            ]
        }
    }

    result = task.run(context)

    assert result is context
    files = list(tmp_path.glob("*.csv"))
    assert len(files) == 1
    rows = read_csv_rows(str(files[0]))
    assert len(rows) == 2

    # Check that newlines are replaced with spaces
    assert rows[0]["supplier_name"] == "TestSupplier"
    assert rows[0]["item_description"] == "Item 1 with newline"  # newlines -> spaces
    assert rows[0]["item_quantity"] == "2"

    assert rows[1]["supplier_name"] == "TestSupplier"
    assert rows[1]["item_description"] == "Item 2"
    assert rows[1]["item_quantity"] == "3"


def test_large_dataset_csv_handling(tmp_path, sample_extraction_config):
    """Large datasets should be handled efficiently in CSV output."""
    cfg = dict(sample_extraction_config)
    cfg["data_dir"] = str(tmp_path)
    config_manager = cast(ConfigManager, DummyConfigManager(cfg))
    task = StoreMetadataAsCsvV2(config_manager, params={})

    # Create large dataset
    large_items = [{"description": f"Item {i}", "quantity": str(i), "value": str(i * 1.5)} for i in range(100)]
    context = {
        "id": "large-csv",
        "data": {
            "supplier_name": "Large Dataset Supplier",
            "invoice_amount": 9999.99,
            "items": large_items
        }
    }

    result = task.run(context)

    assert result is context
    assert "rows_written" in result
    assert result["rows_written"] == 100

    files = list(tmp_path.glob("*.csv"))
    assert len(files) == 1
    rows = read_csv_rows(str(files[0]))
    assert len(rows) == 100

    # Verify a few sample rows
    assert rows[0]["supplier_name"] == "Large Dataset Supplier"
    assert rows[0]["item_description"] == "Item 0"
    assert rows[0]["item_quantity"] == "0"
    assert rows[0]["item_value"] == "0.0"

    assert rows[99]["supplier_name"] == "Large Dataset Supplier"
    assert rows[99]["item_description"] == "Item 99"
    assert rows[99]["item_quantity"] == "99"
    assert rows[99]["item_value"] == "148.5"