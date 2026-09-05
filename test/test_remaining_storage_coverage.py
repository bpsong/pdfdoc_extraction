"""Additional coverage for JSON and CSV storage edge paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from modules.exceptions import TaskError
from standard_step.storage import store_metadata_as_csv as csv_module
from standard_step.storage import store_metadata_as_json as json_module
from standard_step.storage.store_metadata_as_csv import StoreMetadataAsCsv
from standard_step.storage.store_metadata_as_json import StoreMetadataAsJson


class Config:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def get_all(self):
        return self.values


def test_json_storage_filename_table_alias_directory_and_write_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = StoreMetadataAsJson(
        Config(),
        data_dir=str(tmp_path / "json"),
        filename="{items}",
        extraction={"fields": {"items": {"alias": "", "is_table": True}}},
    )
    monkeypatch.setattr(json_module, "preprocess_filename_value", Mock(side_effect=RuntimeError("format")))
    assert task._build_safe_filename({"items": [1]}) == "unknown.json"

    context = {"id": "doc", "data": {"items": [1, {"name": "x"}]}}
    result = task.run(context)
    assert result["output_path"].endswith(".json")

    task.filename_template = "{bad["
    assert task._build_safe_filename({"items": []}) == "metadata.json"

    task.filename_template = "output"
    monkeypatch.setattr(json_module.Path, "mkdir", Mock(side_effect=OSError("mkdir")))
    failed = task.run({"id": "doc2", "data": {"value": 1}})
    assert "error_step" in failed

    task = StoreMetadataAsJson(Config(), data_dir=str(tmp_path), filename="output")
    monkeypatch.setattr(json_module, "reserve_unique_filepath", Mock(return_value=tmp_path / "output.json"))
    monkeypatch.setattr(json_module, "windows_long_path", lambda value: value)
    monkeypatch.setattr("builtins.open", Mock(side_effect=OSError("write")))
    monkeypatch.setattr(json_module, "release_reserved_filepath", lambda _path: False)
    failed = task.run({"id": "doc3", "data": {"value": 1}})
    assert failed["error_step"] == "StoreMetadataAsJson"


def test_csv_storage_table_shapes_fallbacks_and_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = StoreMetadataAsCsv(
        Config(),
        data_dir=str(tmp_path),
        filename="{missing}",
        extraction={
            "fields": {
                "amount": {"alias": "Amount"},
                "items": {"is_table": True, "item_fields": {"name": {"alias": "Name"}}},
            }
        },
    )
    assert task._clean_value([None, 1, {"x": 2}]) == "1,{'x': 2}"
    assert task._detect_table_field({"data": {"items": [{"name": "x"}]}}) == "items"
    context = {"id": "doc", "data": {"amount": 4, "items": [{"name": "x"}, "scalar", None]}}
    result = task.run(context)
    assert result["rows_written"] == 3

    task.filename_template = ""
    monkeypatch.setattr(csv_module, "reserve_unique_filepath", Mock(side_effect=OSError("reserve")))
    failed = task.run({"id": "doc2", "data": {"x": 1}})
    assert "error_step" in failed

    task.filename_template = "output"
    monkeypatch.setattr(task, "_generate_unique_filepath", lambda *_args, **_kwargs: tmp_path / "failed.csv")
    monkeypatch.setattr("builtins.open", Mock(side_effect=OSError("write")))
    monkeypatch.setattr(csv_module, "release_reserved_filepath", lambda _path: False)
    failed = task.run({"id": "doc3", "data": {"x": 1}})
    assert failed["error"] == "write"


def test_csv_detect_table_ignores_bad_field_config() -> None:
    class BadConfig(dict):
        def get(self, *_args, **_kwargs):
            raise RuntimeError("bad config")

    task = StoreMetadataAsCsv.__new__(StoreMetadataAsCsv)
    task.extraction_fields = {"items": BadConfig()}
    assert task._detect_table_field({"data": {}}) is None
