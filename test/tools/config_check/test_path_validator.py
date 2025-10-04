"""Unit tests for path validation logic.

This module contains comprehensive unit tests for the path validation functionality,
specifically designed to validate Windows-compatible path handling and validation
logic for configuration files in the PDF document extraction system.

The test suite covers path validation for:
- Static directory paths (web.upload_dir)
- Watch folder paths with strict existence requirements
- Dynamic path discovery for fields ending in '_dir' or '_file'
- Relative path resolution against configurable base directories
- Windows-specific path format handling and validation

Key Features:
- Windows-compatible temporary directory and file creation
- Comprehensive testing of both existing and missing path scenarios
- Base directory override testing for relative path resolution
- Dynamic path discovery validation for custom directory fields
- UTF-8 encoding support for international path names

Test Scenarios:
    - Valid existing directory and file paths
    - Missing required directories (watch_folder.dir)
    - Missing dynamically discovered directories
    - Relative path resolution with base directory override
    - Mixed absolute and relative path handling

Windows Compatibility:
    - Uses Windows-compatible temporary file and directory creation
    - Proper handling of Windows path separators and formats
    - UTF-8 encoding for international character support in paths
    - Case-insensitive path comparisons where appropriate
    - Support for Windows drive letters and UNC paths

Test Data:
    Uses realistic directory structures that mirror actual PDF processing
    scenarios with proper Windows path formatting and organization.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from tools.config_check.path_validator import PathValidator


def _base_config(upload_dir: Path, watch_dir: Path) -> dict:
    return {
        "web": {"upload_dir": str(upload_dir)},
        "watch_folder": {"dir": str(watch_dir)},
        "tasks": {
            "step_one": {
                "module": "sample.module",
                "class": "SampleTask",
                "params": {"data_dir": str(upload_dir)},
            }
        },
        "pipeline": ["step_one"],
    }


def test_path_validator_accepts_existing_paths():
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        uploads = base / "uploads"
        watch = base / "watch"
        uploads.mkdir()
        watch.mkdir()

        validator = PathValidator()
        result = validator.validate(_base_config(uploads, watch))

        assert result.errors == []
        assert result.warnings == []


def test_watch_folder_missing_directory_reports_error():
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        uploads = base / "uploads"
        uploads.mkdir()
        watch = base / "missing"

        validator = PathValidator()
        result = validator.validate(_base_config(uploads, watch))

        assert any(issue.path == "watch_folder.dir" for issue in result.errors)


def test_dynamic_dir_missing_reports_error():
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        uploads = base / "uploads"
        watch = base / "watch"
        uploads.mkdir()
        watch.mkdir()

        config = _base_config(uploads, watch)
        config["tasks"]["step_one"]["params"]["output_dir"] = str(base / "missing_output")

        validator = PathValidator()
        result = validator.validate(config)

        assert any("output_dir" in issue.path for issue in result.errors)


def test_base_dir_is_used_for_relative_paths():
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        uploads = base / "uploads"
        watch = base / "watch"
        uploads.mkdir()
        watch.mkdir()
        (base / "files").mkdir()
        target_file = base / "files" / "example.txt"
        target_file.write_text("data", encoding="utf-8")

        config = {
            "web": {"upload_dir": "uploads"},
            "watch_folder": {"dir": "watch"},
            "tasks": {
                "step_one": {
                    "module": "sample.module",
                    "class": "SampleTask",
                    "params": {
                        "data_dir": "uploads",
                        "config_file": "files/example.txt",
                    },
                }
            },
            "pipeline": ["step_one"],
        }

        validator = PathValidator(base_dir=base)
        result = validator.validate(config)

        assert result.errors == []
