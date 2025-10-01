import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, cast
from modules.config_manager import ConfigManager

import pytest

from standard_step.storage.store_metadata_as_json_v2 import StoreMetadataAsJsonV2
from modules.exceptions import TaskError

# Helper clickable reference to the file created by these tests for reviewers:
# [`test/storage/test_storage_v2_json.py`](test/storage/test_storage_v2_json.py:1)


class DummyConfigManager:
    """Minimal stand-in for ConfigManager used by the task in tests."""

    def __init__(self, tasks_conf: Dict[str, Any]):
        self._tasks_conf = {"tasks": tasks_conf}

    def get_all(self) -> Dict[str, Any]:
        return self._tasks_conf


class DummyStatus:
    def __init__(self):
        self.calls = []

    def update_status(self, unique_id: str, message: str, **kwargs):
        # record calls for assertions
        self.calls.append({"id": unique_id, "message": message, "kwargs": kwargs})


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def basic_fields_config():
    # Simulate extraction.fields mapping used by store task
    return {
        # top-level scalar field with alias
        "supplier_name": {"alias": "supplier_name"},
        # table field (array-of-objects)
        "items": {"alias": "items", "is_table": True, "item_fields": [
            {"name": "Description", "alias": "description"},
            {"name": "Quantity", "alias": "quantity"},
        ]},
    }


@pytest.fixture
def config_manager(basic_fields_config):
    # Put the extract task configuration where the store task expects it
    tasks_conf = {
        "extract_document_data_v2": {
            "params": {"fields": basic_fields_config}
        }
    }
    return DummyConfigManager(tasks_conf)


@pytest.fixture(autouse=True)
def patch_status_manager(monkeypatch):
    """Replace StatusManager to avoid touching real external systems."""
    dummy = DummyStatus()

    def fake_status_manager(cm):
        return dummy

    # Monkeypatch the StatusManager class in the module under test
    monkeypatch.setattr("standard_step.storage.store_metadata_as_json_v2.StatusManager", lambda cm: dummy)
    return dummy


def read_json_file(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_write_scalar_only_json(temp_dir, config_manager, patch_status_manager):
    """Scalar-only data should be written as JSON and preserve aliases."""
    params = {"data_dir": str(temp_dir), "filename": "{supplier_name}.json"}
    task = StoreMetadataAsJsonV2(cast(ConfigManager, config_manager), **params)

    context = {"id": "abc-1", "data": {"supplier_name": "ACME Corp", "invoice_no": "INV-001"}}

    result = task.run(context)

    # Output path put into context
    assert "output_path" in result
    out_path = Path(result["output_path"])
    assert out_path.exists(), "Expected JSON file to be created"

    content = read_json_file(out_path)
    # supplier_name should be present using alias (alias same as key here)
    assert content["supplier_name"] == "ACME Corp"
    # invoice_no was not in extraction.fields config so should be preserved under same key
    assert content["invoice_no"] == "INV-001"
    # items shouldn't be present for scalar-only data
    assert "items" not in content


def test_write_with_table_preserves_list_of_objects(temp_dir, config_manager, patch_status_manager):
    """When a field is configured as is_table, the list-of-objects must be preserved."""
    params = {"data_dir": str(temp_dir), "filename": "{supplier_name}.json"}
    task = StoreMetadataAsJsonV2(cast(ConfigManager, config_manager), **params)

    items = [{"description": "Item1", "quantity": "2"}, {"description": "Item2", "quantity": "5"}]
    context = {"id": "abc-2", "data": {"supplier_name": "Beta Ltd", "items": items, "note": "sample"}}

    result = task.run(context)

    assert "output_path" in result
    out_path = Path(result["output_path"])
    assert out_path.exists()

    content = read_json_file(out_path)
    # top-level alias mapping preserved
    assert content["supplier_name"] == "Beta Ltd"
    # items preserved as list-of-objects unchanged
    assert isinstance(content["items"], list)
    assert content["items"] == items
    # additional scalar preserved
    assert content["note"] == "sample"


def test_filename_generation_and_uniqueness(temp_dir, config_manager, patch_status_manager):
    """Filename template should be formatted and uniqueness handled by appending suffixes."""
    # filename template pulls supplier_name into filename
    params = {"data_dir": str(temp_dir), "filename": "{supplier_name}.json"}
    task = StoreMetadataAsJsonV2(cast(ConfigManager, config_manager), **params)

    context1 = {"id": "u1", "data": {"supplier_name": "Gamma Co"}}
    result1 = task.run(context1)
    out1 = Path(result1["output_path"])
    assert out1.exists()
    # Create a file with the same base name to simulate existing file for next run
    duplicate_base = temp_dir / out1.name
    assert duplicate_base.exists()

    # Now run a second time with same supplier; generated name should not overwrite first file
    context2 = {"id": "u2", "data": {"supplier_name": "Gamma Co"}}
    result2 = task.run(context2)
    out2 = Path(result2["output_path"])
    assert out2.exists()
    # The second filename must be different from the first
    assert out2.name != out1.name


def test_error_handling_on_write_failure(temp_dir, config_manager, monkeypatch, patch_status_manager):
    """If writing fails, context must include error and error_step and status updated to failed."""
    params = {"data_dir": str(temp_dir), "filename": "{supplier_name}.json"}
    task = StoreMetadataAsJsonV2(cast(ConfigManager, config_manager), **params)

    # Prepare normal context
    context = {"id": "err-1", "data": {"supplier_name": "Failing Co", "items": []}}

    # Monkeypatch open to raise an IOError when attempting to write
    def fake_open(*args, **kwargs):
        raise IOError("disk full")

    monkeypatch.setattr("builtins.open", fake_open)

    result = task.run(context)

    # On failure the task returns context with error info
    assert "error" in result
    assert "error_step" in result
    assert result["error_step"] == "StoreMetadataAsJsonV2"
    assert "disk full" in result["error"]


def test_validation_missing_data_returns_context(temp_dir, config_manager, patch_status_manager):
    """If context lacks 'data', the task should skip writing and return context unchanged."""
    params = {"data_dir": str(temp_dir), "filename": "{supplier_name}.json"}
    task = StoreMetadataAsJsonV2(cast(ConfigManager, config_manager), **params)

    context = {"id": "no-data"}  # no 'data' key

    result = task.run(context)

    # As per implementation, it should simply return the context without adding output_path
    assert result is context
    assert "output_path" not in result


def test_empty_data_dict_creates_minimal_json(temp_dir, config_manager, patch_status_manager):
    """Empty data dict should create a minimal JSON file with warning."""
    params = {"data_dir": str(temp_dir), "filename": "{supplier_name}.json"}
    task = StoreMetadataAsJsonV2(cast(ConfigManager, config_manager), **params)

    context = {"id": "empty-data", "data": {}}

    result = task.run(context)

    assert "output_path" in result
    out_path = Path(result["output_path"])
    assert out_path.exists()

    content = read_json_file(out_path)
    assert "_empty" in content or len(content) > 0  # Should have some content


def test_non_dict_items_in_table_converts_to_string(temp_dir, config_manager, patch_status_manager):
    """Non-dict items in table should be converted to string representation."""
    # Update config to include a table field
    config_with_table = {
        "extract_document_data_v2": {
            "params": {"fields": {
                "supplier_name": {"alias": "supplier_name"},
                "items": {"alias": "items", "is_table": True}
            }}
        }
    }
    config_manager_with_table = DummyConfigManager(config_with_table)

    params = {"data_dir": str(temp_dir), "filename": "{supplier_name}.json"}
    task = StoreMetadataAsJsonV2(cast(ConfigManager, config_manager_with_table), **params)

    # Include non-dict items in the table
    context = {
        "id": "mixed-table",
        "data": {
            "supplier_name": "Test Supplier",
            "items": [
                {"description": "Item 1", "quantity": "2"},  # dict item
                "string item",  # string item
                42,  # number item
                None,  # null item
                {"description": "Item 2", "quantity": "1"}  # another dict item
            ]
        }
    }

    result = task.run(context)

    assert "output_path" in result
    out_path = Path(result["output_path"])
    assert out_path.exists()

    content = read_json_file(out_path)
    assert "supplier_name" in content
    assert "items" in content
    assert isinstance(content["items"], list)
    assert len(content["items"]) == 5

    # Check that non-dict items were converted to dicts with "value" key
    assert content["items"][0] == {"description": "Item 1", "quantity": "2"}
    assert content["items"][1] == {"value": "string item"}
    assert content["items"][2] == {"value": "42"}
    assert content["items"][3] == {"value": "None"}
    assert content["items"][4] == {"description": "Item 2", "quantity": "1"}


def test_special_characters_in_data_handled_safely(temp_dir, config_manager, patch_status_manager):
    """Special characters and newlines in data should be preserved in JSON."""
    params = {"data_dir": str(temp_dir), "filename": "{supplier_name}.json"}
    task = StoreMetadataAsJsonV2(cast(ConfigManager, config_manager), **params)

    # Data with special characters and newlines
    context = {
        "id": "special-chars",
        "data": {
            "supplier_name": "Test\nSupplier\tWith\"Special\"Chars",
            "description": "Line 1\r\nLine 2\nLine 3\tTabbed",
            "notes": "Unicode: ñáéíóú, Emojis: 🚀💡, Symbols: ©®™"
        }
    }

    result = task.run(context)

    assert "output_path" in result
    out_path = Path(result["output_path"])
    assert out_path.exists()

    content = read_json_file(out_path)
    assert content["supplier_name"] == "Test\nSupplier\tWith\"Special\"Chars"
    assert content["description"] == "Line 1\r\nLine 2\nLine 3\tTabbed"
    assert content["notes"] == "Unicode: ñáéíóú, Emojis: 🚀💡, Symbols: ©®™"


def test_large_data_handling(temp_dir, config_manager, patch_status_manager):
    """Large datasets should be handled without issues."""
    params = {"data_dir": str(temp_dir), "filename": "{supplier_name}.json"}
    task = StoreMetadataAsJsonV2(cast(ConfigManager, config_manager), **params)

    # Create large dataset
    large_items = [{"id": i, "description": f"Item {i}", "value": i * 1.5} for i in range(1000)]
    context = {
        "id": "large-data",
        "data": {
            "supplier_name": "Large Data Supplier",
            "items": large_items,
            "metadata": {"count": len(large_items), "total_value": sum(i * 1.5 for i in range(1000))}
        }
    }

    result = task.run(context)

    assert "output_path" in result
    out_path = Path(result["output_path"])
    assert out_path.exists()

    content = read_json_file(out_path)
    assert len(content["items"]) == 1000
    assert content["metadata"]["count"] == 1000
    assert content["metadata"]["total_value"] == 749250.0  # sum of 1.5 * i for i in 0..999 = 1.5 * sum(0..999) = 1.5 * 499500 = 749250