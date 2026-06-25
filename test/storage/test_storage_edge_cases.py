from pathlib import Path
from unittest.mock import Mock

import pytest

from modules.exceptions import TaskError
from standard_step.storage.store_file_to_localdrive import StoreFileToLocaldrive
from standard_step.storage.store_metadata_as_csv import StoreMetadataAsCsv
from standard_step.storage.store_metadata_as_json import StoreMetadataAsJson


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
            "items": ["bad", {"Name": "ok"}, {"Other": "value"}],
        },
    }
    result = task.run(context)
    assert Path(result["output_path"]).exists()

    monkeypatch.setattr(
        "standard_step.storage.store_metadata_as_csv.csv.DictWriter",
        Mock(side_effect=OSError("disk full")),
    )
    failed = task.run({"id": "failed", "data": {"value": 1}})
    assert failed["error_step"] == "StoreMetadataAsCsv"


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

    task.data_dir = None
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

    monkeypatch.setattr(
        "standard_step.storage.store_metadata_as_json.generate_unique_filepath",
        Mock(side_effect=OSError("path failure")),
    )
    result = valid.run({"id": "doc", "data": {"id": "doc"}})
    assert result["error_step"] == "StoreMetadataAsJson"


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
