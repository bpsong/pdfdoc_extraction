from pathlib import Path
import builtins
from typing import Any, cast
from unittest.mock import Mock

import pytest

from modules.exceptions import TaskError
from standard_step.storage.store_file_to_localdrive import StoreFileToLocaldrive
from standard_step.storage.store_metadata_as_csv import StoreMetadataAsCsv
from standard_step.storage.store_metadata_as_json import StoreMetadataAsJson
import standard_step.storage.store_metadata_as_json as json_module
import standard_step.storage.store_metadata_as_csv as csv_module


class Config:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def get_all(self):
        return self.values


def test_storage_constructors_reject_missing_parameters(tmp_path):
    config = Config()
    with pytest.raises(TaskError, match="data_dir"):
        StoreMetadataAsJson(config, filename="name.json")
    with pytest.raises(TaskError, match="filename"):
        StoreMetadataAsJson(config, data_dir=str(tmp_path))
    with pytest.raises(TaskError, match="files_dir"):
        StoreFileToLocaldrive(config, filename="name.pdf")
    with pytest.raises(TaskError, match="filename"):
        StoreFileToLocaldrive(config, files_dir=str(tmp_path))

    csv_task = StoreMetadataAsCsv(config)
    with pytest.raises(TaskError, match="data_dir"):
        csv_task.validate_required_fields({"data": {}})
    csv_task.data_dir_template = str(tmp_path)
    with pytest.raises(TaskError, match="filename"):
        csv_task.validate_required_fields({"data": {}})


def test_csv_helpers_cover_detection_cleaning_and_aliases(tmp_path):
    task = StoreMetadataAsCsv(
        Config({"data_dir": str(tmp_path), "filename": "{id}"}),
    )
    task.extraction_fields = {}
    context = {"data": {"items": [{"value": 1}]}}
    assert task._detect_table_field(context) == "items"
    assert task._detect_table_field({"data": {"items": []}}) is None
    assert task._clean_value(None) == ""
    assert task._clean_value([None, {"a": 1}, [2], 3]) == "{'a': 1},[2],3"
    assert task._clean_value({"a": 1}) == "{'a': 1}"
    assert task._clean_value("a\r\nb\rc\nd") == "a b c d"

    task.extraction_fields = {"field": {"name": "Field Name"}}
    assert task._map_alias("field") == "Field Name"
    assert task._map_alias("missing") == "missing"


def test_csv_run_handles_missing_invalid_and_irregular_table_data(tmp_path, monkeypatch):
    config = Config({"data_dir": str(tmp_path), "filename": "{missing}"})
    task = StoreMetadataAsCsv(config)

    context = {"id": "doc", "data": None}
    assert task.run(context) is context

    result = task.run({"id": "doc", "data": ["invalid"]})
    assert result["error_step"] == "StoreMetadataAsCsv"

    task.filename_template = "{id}"
    task.extraction_fields = {
        "items": {
            "is_table": True,
            "item_fields": {"name": {"alias": "Name"}},
        }
    }
    context = {
        "id": "doc",
        "data": {
            "scalar": {"nested": True},
            "list": ["a"],
            "empty_list": [],
            "items": ["bad", {"Name": "ok"}, {"Other": "value"}],
        },
    }
    result = task.run(context)
    assert Path(result["output_path"]).exists()

    original_dict_writer = __import__("csv").DictWriter
    monkeypatch.setattr(
        "standard_step.storage.store_metadata_as_csv.csv.DictWriter",
        Mock(side_effect=OSError("disk full")),
    )
    failed = task.run({"id": "failed", "data": {"value": 1}})
    assert failed["error_step"] == "StoreMetadataAsCsv"
    monkeypatch.setattr("standard_step.storage.store_metadata_as_csv.csv.DictWriter", original_dict_writer)

    scalar_task = StoreMetadataAsCsv(Config({"data_dir": str(tmp_path), "filename": "{empty}"}))
    scalar_task.filename_template = "{empty}"
    scalar_task._detect_table_field = Mock(return_value=None)
    monkeypatch.setattr(csv_module, "sanitize_filename", lambda _value: "")
    scalar_result = scalar_task.run({"id": "blank", "data": {"empty": "", "rows": [{"x": 1}], "empty_list": []}})
    assert Path(scalar_result["output_path"]).exists()
    empty_list_result = scalar_task.run({"id": "empty-list", "data": {"empty_list": []}})
    assert Path(empty_list_result["output_path"]).exists()

    table_task = StoreMetadataAsCsv(Config({"data_dir": str(tmp_path), "filename": "{id}"}))
    table_task.extraction_fields = {"items": {"is_table": True}}
    empty_table = table_task.run({"id": "empty", "data": {"items": [], "value": 1}})
    assert Path(empty_table["output_path"]).exists()


def test_json_helpers_and_error_paths(tmp_path, monkeypatch):
    config = Config({"tasks": {}})
    task = StoreMetadataAsJson(
        config,
        data_dir=str(tmp_path),
        filename="{values}_{missing}.json",
    )

    assert task._build_safe_filename({"values": [1, {"a": 1}]}) == "1,list_unknown.json"
    task.filename_template = "{broken"
    assert task._build_safe_filename({}) == "metadata.json"

    task.data_dir = cast(Any, None)
    with pytest.raises(TaskError, match="data_dir"):
        task.validate_required_fields({})
    task.data_dir = tmp_path
    task.filename_template = ""
    with pytest.raises(TaskError, match="filename"):
        task.validate_required_fields({})

    valid = StoreMetadataAsJson(
        config,
        data_dir=str(tmp_path),
        filename="{id}.json",
    )
    result = valid.run({"id": "doc", "data": ["invalid"]})
    assert result["error_step"] == "StoreMetadataAsJson"

    original_reserve = json_module.reserve_unique_filepath

    monkeypatch.setattr(
        "standard_step.storage.store_metadata_as_json.reserve_unique_filepath",
        Mock(side_effect=OSError("path failure")),
    )
    result = valid.run({"id": "doc", "data": {"id": "doc"}})
    assert result["error_step"] == "StoreMetadataAsJson"
    monkeypatch.setattr(json_module, "reserve_unique_filepath", original_reserve)

    valid._build_safe_filename = Mock(side_effect=ValueError("bad filename"))
    result = valid.run({"id": "doc", "data": {"id": "doc"}})
    assert result["error_step"] == "StoreMetadataAsJson"

    valid._build_safe_filename = StoreMetadataAsJson._build_safe_filename.__get__(valid)
    valid.extraction_fields_config = {"value": {"alias": "", "is_table": True}}
    result = valid.run({"id": "doc", "data": {"value": "scalar"}})
    assert result["output_path"]

    original_open = open
    monkeypatch.setattr("builtins.open", Mock(side_effect=OSError("write failed")))
    monkeypatch.setattr(
        "standard_step.storage.store_metadata_as_json.release_reserved_filepath",
        Mock(return_value=False),
    )
    failed = valid.run({"id": "failed", "data": {"value": 1}})
    assert failed["error_step"] == "StoreMetadataAsJson"

    valid._build_safe_filename = Mock(side_effect=RuntimeError("unexpected"))
    unexpected = valid.run({"id": "unexpected", "data": {"value": 1}})
    assert unexpected["error_step"] == "StoreMetadataAsJson"

    monkeypatch.setattr("builtins.open", original_open)
    valid._build_safe_filename = StoreMetadataAsJson._build_safe_filename.__get__(valid)
    valid.extraction_fields_config = {"": {"alias": ""}}
    alias_fallback = valid.run({"id": "alias", "data": {"": "value"}})
    assert alias_fallback["output_path"]
    valid.validate_required_fields = Mock(side_effect=RuntimeError("unexpected validation"))
    outer_failure = valid.run({"id": "outer", "data": {"value": 1}})
    assert outer_failure["error_step"] == "StoreMetadataAsJson"


def test_csv_defensive_table_and_header_shape_branches(tmp_path, monkeypatch):
    task = StoreMetadataAsCsv(Config({"data_dir": str(tmp_path), "filename": "{id}"}))
    task.extraction_fields = {
        "items": {"is_table": True, "item_fields": {"value": {"type": "str"}}},
        "scalar": {"alias": "Scalar"},
    }

    class OddItem:
        def get(self, _key, _default=None):
            return "odd"

    original_isinstance = builtins.isinstance

    def preserve_odd_item_once(value, class_or_tuple):
        if class_or_tuple is dict and type(value) is OddItem:
            preserve_odd_item_once.seen += 1
            return preserve_odd_item_once.seen == 1
        return original_isinstance(value, class_or_tuple)

    preserve_odd_item_once.seen = 0
    monkeypatch.setattr(builtins, "isinstance", preserve_odd_item_once)
    first_odd = task.run({"id": "odd", "data": {"items": [OddItem()]}})
    assert first_odd["output_path"]

    preserve_odd_item_once.seen = 0
    later_odd = task.run({"id": "odd-later", "data": {"items": [{"foo": "first"}, OddItem()]}})
    assert later_odd["output_path"]

    monkeypatch.setattr(builtins, "isinstance", original_isinstance)
    empty_row = task.run({"id": "empty-row", "data": {"items": [{}]}})
    assert empty_row["output_path"]

    class FlakyHeader(str):
        def __new__(cls, value):
            instance = super().__new__(cls, value)
            instance.hash_calls = 0
            return instance

        def __hash__(self):
            self.hash_calls += 1
            offset = 0 if self.hash_calls == 1 else 1
            return str.__hash__(self) + offset

    flaky_header = FlakyHeader("flaky")
    task.extraction_fields["scalar"]["alias"] = flaky_header

    class RecordingWriter:
        def __init__(self, _file_handle, fieldnames):
            self.fieldnames = fieldnames
            self.rows = []

        def writeheader(self):
            return None

        def writerows(self, rows):
            self.rows.extend(rows)

    monkeypatch.setattr(csv_module.csv, "DictWriter", RecordingWriter)
    mismatched_header = task.run(
        {"id": "mismatched-header", "data": {"scalar": "value", "items": [{"value": "item"}]}}
    )
    assert mismatched_header["output_path"]


def test_local_file_storage_validation_format_and_copy_errors(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-")
    task = StoreFileToLocaldrive(
        Config({"tasks": {}}),
        files_dir=str(tmp_path / "out"),
        filename="{missing}",
    )

    context = {"id": "doc", "original_filename": "source.pdf"}
    assert task.run(context) is context

    task.files_dir = None
    with pytest.raises(TaskError, match="files_dir"):
        task.validate_required_fields({})
    task.files_dir = tmp_path / "out"
    task.filename = None
    with pytest.raises(TaskError, match="filename"):
        task.validate_required_fields({})

    task.filename = "{missing}"
    with pytest.raises(TaskError, match="missing key"):
        task.run(
            {
                "id": "doc",
                "file_path": str(source),
                "original_filename": "source.pdf",
                "data": {},
            }
        )

    task.filename = "{id}"
    monkeypatch.setattr(
        "standard_step.storage.store_file_to_localdrive.shutil.copy",
        Mock(side_effect=OSError("copy failed")),
    )
    with pytest.raises(TaskError, match="copy failed"):
        task.run(
            {
                "id": "doc",
                "file_path": str(source),
                "original_filename": "source.pdf",
                "data": {},
            }
        )

    task.filename = None
    task.validate_required_fields = Mock()
    with pytest.raises(TaskError, match="Filename pattern"):
        task.run({"id": "doc", "file_path": str(source), "original_filename": "source.pdf"})
    task.filename = "{id}"
    task.files_dir = None
    with pytest.raises(TaskError, match="Files directory"):
        task.run({"id": "doc", "file_path": str(source), "original_filename": "source.pdf"})

    task.files_dir = tmp_path / "out"
    task.filename = "{id"
    with pytest.raises(TaskError, match="Failed to format filename"):
        task.run({"id": "doc", "file_path": str(source), "original_filename": "source.pdf"})
