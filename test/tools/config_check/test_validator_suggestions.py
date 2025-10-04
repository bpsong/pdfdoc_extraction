"""Integration tests for suggestion generation in ConfigValidator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from tools.config_check.validator import ConfigValidator  # noqa: E402


def _build_config(upload_dir, watch_dir, storage_data_dir, pipeline_order):
    tasks = {
        "extract_metadata": {
            "module": "standard_step.extraction.extract_metadata",
            "class": "ExtractMetadata",
            "params": {
                "fields": {
                    "supplier_name": {
                        "alias": "Supplier",
                        "type": "str",
                    },
                    "invoice_total": {
                        "alias": "Total",
                        "type": "float",
                    },
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
        "cleanup": {
            "module": "standard_step.housekeeping.cleanup",
            "class": "CleanupTask",
            "params": {},
        },
    }

    if storage_data_dir is not None:
        tasks["store_json"]["params"]["data_dir"] = str(storage_data_dir)

    return {
        "web": {"upload_dir": str(upload_dir)},
        "watch_folder": {"dir": str(watch_dir)},
        "tasks": tasks,
        "pipeline": pipeline_order,
    }


def test_validator_provides_watch_folder_suggestion(tmp_path):
    config = _build_config(
        upload_dir=tmp_path / "uploads_missing",
        watch_dir=tmp_path / "watch_missing",
        storage_data_dir=tmp_path / "data_missing",
        pipeline_order=["extract_metadata", "store_json", "cleanup"],
    )

    validator = ConfigValidator(base_dir=tmp_path)
    result = validator.validate_config_data(config)

    suggestions = {
        message.code: message.suggestion
        for message in result.errors
        if message.code and message.suggestion
    }

    assert "watch-folder-missing-dir" in suggestions
    assert "Create the watch folder" in suggestions["watch-folder-missing-dir"]


def test_validator_provides_pipeline_order_suggestion(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    watch = tmp_path / "watch"
    watch.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    config = _build_config(
        upload_dir=uploads,
        watch_dir=watch,
        storage_data_dir=data_dir,
        pipeline_order=["store_json", "extract_metadata", "cleanup"],
    )

    validator = ConfigValidator(base_dir=tmp_path)
    result = validator.validate_config_data(config)

    storage_issue = next(
        message for message in result.errors if message.code == "pipeline-storage-before-extraction"
    )

    assert storage_issue.suggestion is not None
    assert "Move an extraction task before" in storage_issue.suggestion


def test_validator_provides_parameter_suggestion(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    watch = tmp_path / "watch"
    watch.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    config = _build_config(
        upload_dir=uploads,
        watch_dir=watch,
        storage_data_dir=data_dir,
        pipeline_order=["extract_metadata", "store_json", "cleanup"],
    )
    del config["tasks"]["store_json"]["params"]["data_dir"]

    validator = ConfigValidator(base_dir=tmp_path)
    result = validator.validate_config_data(config)

    param_issue = next(
        message for message in result.errors if message.code == "param-storage-missing-data-dir"
    )

    assert param_issue.suggestion is not None
    assert "Set data_dir" in param_issue.suggestion
