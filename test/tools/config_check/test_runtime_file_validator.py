"""Tests for runtime file validation functionality.

This module tests the RuntimeFileValidator class and the --check-files flag functionality.
It covers file existence validation, directory permission validation, and CSV parsing validation
as specified in requirements 5.1, 5.2, 5.3, 5.4, and 5.5.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict

import pytest

from tools.config_check.__main__ import main
from tools.config_check.runtime_file_validator import RuntimeFileValidator, validate_runtime_files


def _capture_stdout_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Return captured stdout split into non-empty lines."""
    captured = capsys.readouterr()
    return [line for line in captured.out.splitlines() if line]


def _extract_json_payload(lines: list[str]) -> str:
    """Extract a JSON payload from captured stdout lines."""
    joined = "\n".join(lines)
    start = joined.find("{")
    end = joined.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AssertionError("Expected JSON payload in stdout but none was found.")
    return joined[start : end + 1]


class TestRuntimeFileValidator:
    """Unit tests for RuntimeFileValidator class."""

    def test_init_with_default_base_dir(self) -> None:
        """Test validator initialization with default base directory."""
        validator = RuntimeFileValidator()
        assert validator.base_dir == Path.cwd()

    def test_init_with_custom_base_dir(self, tmp_path: Path) -> None:
        """Test validator initialization with custom base directory."""
        validator = RuntimeFileValidator(tmp_path)
        assert validator.base_dir == tmp_path

    def test_validate_file_dependencies_empty_config(self) -> None:
        """Test validation with empty configuration."""
        validator = RuntimeFileValidator()
        result = validator.validate_file_dependencies({})
        
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_resolve_path_absolute(self, tmp_path: Path) -> None:
        """Test path resolution with absolute paths."""
        validator = RuntimeFileValidator(tmp_path)
        absolute_path = tmp_path / "test.txt"
        
        resolved = validator._resolve_path(str(absolute_path))
        assert resolved == absolute_path

    def test_resolve_path_relative(self, tmp_path: Path) -> None:
        """Test path resolution with relative paths."""
        validator = RuntimeFileValidator(tmp_path)
        
        resolved = validator._resolve_path("test.txt")
        assert resolved == tmp_path / "test.txt"


class TestReferenceFileValidation:
    """Tests for reference file validation in rules tasks."""

    def test_validate_reference_files_no_tasks(self) -> None:
        """Test validation when no tasks are defined."""
        validator = RuntimeFileValidator()
        config = {"web": {"upload_dir": "uploads"}}
        
        errors, warnings = validator._validate_reference_files(config)
        assert len(errors) == 0
        assert len(warnings) == 0

    def test_validate_reference_files_non_rules_task(self) -> None:
        """Test validation skips non-rules tasks."""
        validator = RuntimeFileValidator()
        config = {
            "tasks": {
                "extract_pdf": {
                    "module": "standard_step.extraction.extract_pdf",
                    "class": "ExtractPdf",
                    "params": {"api_key": "test"}
                }
            }
        }
        
        errors, warnings = validator._validate_reference_files(config)
        assert len(errors) == 0
        assert len(warnings) == 0

    def test_validate_reference_files_missing_file(self, tmp_path: Path) -> None:
        """Test validation reports missing reference files."""
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "class": "UpdateReference",
                    "params": {
                        "reference_file": "missing.csv"
                    }
                }
            }
        }
        
        errors, warnings = validator._validate_reference_files(config)
        assert len(errors) == 1
        assert errors[0].code == "file-not-found"
        assert "missing.csv" in errors[0].message
        assert errors[0].path == "tasks.update_reference.params.reference_file"

    def test_validate_reference_files_existing_file(self, tmp_path: Path) -> None:
        """Test validation passes for existing reference files."""
        # Create a test CSV file
        csv_file = tmp_path / "reference.csv"
        csv_file.write_text("column1,column2\nvalue1,value2\n", encoding="utf-8")
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "class": "UpdateReference",
                    "params": {
                        "reference_file": "reference.csv"
                    }
                }
            }
        }
        
        errors, warnings = validator._validate_reference_files(config)
        assert len(errors) == 0
        assert len(warnings) == 0

    def test_validate_reference_files_directory_instead_of_file(self, tmp_path: Path) -> None:
        """Test validation reports when reference path is a directory."""
        # Create a directory instead of a file
        csv_dir = tmp_path / "reference.csv"
        csv_dir.mkdir()
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "class": "UpdateReference",
                    "params": {
                        "reference_file": "reference.csv"
                    }
                }
            }
        }
        
        errors, warnings = validator._validate_reference_files(config)
        assert len(errors) == 1
        assert errors[0].code == "file-not-file"
        assert "not a file" in errors[0].message

    @pytest.mark.skipif(os.name == "nt", reason="Permission tests are complex on Windows")
    def test_validate_reference_files_permission_denied(self, tmp_path: Path) -> None:
        """Test validation reports permission denied errors."""
        # Create a file and remove read permissions
        csv_file = tmp_path / "reference.csv"
        csv_file.write_text("column1,column2\n", encoding="utf-8")
        csv_file.chmod(stat.S_IWRITE)  # Write only, no read
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "class": "UpdateReference",
                    "params": {
                        "reference_file": "reference.csv"
                    }
                }
            }
        }
        
        errors, warnings = validator._validate_reference_files(config)
        assert len(errors) == 1
        assert errors[0].code == "file-not-readable"
        assert "permission denied" in errors[0].message.lower()
        
        # Restore permissions for cleanup
        csv_file.chmod(stat.S_IREAD | stat.S_IWRITE)


class TestDirectoryPermissionValidation:
    """Tests for directory permission validation."""

    def test_validate_directory_permissions_web_upload_dir(self, tmp_path: Path) -> None:
        """Test validation of web upload directory."""
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "web": {
                "upload_dir": "uploads"
            }
        }
        
        errors, warnings = validator._validate_directory_permissions(config)
        assert len(errors) == 0

    def test_validate_directory_permissions_missing_web_upload_dir(self, tmp_path: Path) -> None:
        """Test validation reports missing web upload directory."""
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "web": {
                "upload_dir": "missing_uploads"
            }
        }
        
        errors, warnings = validator._validate_directory_permissions(config)
        assert len(errors) == 1
        assert errors[0].code == "directory-not-found"
        assert "Web upload directory does not exist" in errors[0].message
        assert errors[0].path == "web.upload_dir"

    def test_validate_directory_permissions_watch_folder_dir(self, tmp_path: Path) -> None:
        """Test validation of watch folder directory."""
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "watch_folder": {
                "dir": "watch"
            }
        }
        
        errors, warnings = validator._validate_directory_permissions(config)
        assert len(errors) == 0

    def test_validate_directory_permissions_processing_dir(self, tmp_path: Path) -> None:
        """Test validation of processing directory."""
        processing_dir = tmp_path / "processing"
        processing_dir.mkdir()
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "watch_folder": {
                "processing_dir": "processing"
            }
        }
        
        errors, warnings = validator._validate_directory_permissions(config)
        assert len(errors) == 0

    def test_validate_directory_permissions_task_directories(self, tmp_path: Path) -> None:
        """Test validation of task-specific directories."""
        data_dir = tmp_path / "data"
        files_dir = tmp_path / "files"
        archive_dir = tmp_path / "archive"
        
        data_dir.mkdir()
        files_dir.mkdir()
        archive_dir.mkdir()
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "store_json": {
                    "params": {
                        "data_dir": "data",
                        "files_dir": "files"
                    }
                },
                "archive_pdf": {
                    "params": {
                        "archive_dir": "archive"
                    }
                }
            }
        }
        
        errors, warnings = validator._validate_directory_permissions(config)
        assert len(errors) == 0

    def test_validate_directory_access_file_instead_of_directory(self, tmp_path: Path) -> None:
        """Test validation reports when path is a file instead of directory."""
        # Create a file instead of directory
        fake_dir = tmp_path / "fake_dir"
        fake_dir.write_text("not a directory", encoding="utf-8")
        
        validator = RuntimeFileValidator(tmp_path)
        
        errors = validator._validate_directory_access(
            fake_dir, "test.path", "Test directory"
        )
        assert len(errors) == 1
        assert errors[0].code == "path-not-directory"
        assert "not a directory" in errors[0].message

    @pytest.mark.skipif(os.name == "nt", reason="Permission tests are complex on Windows")
    def test_validate_directory_access_no_read_permission(self, tmp_path: Path) -> None:
        """Test validation reports directories without read permission."""
        test_dir = tmp_path / "no_read"
        test_dir.mkdir()
        test_dir.chmod(stat.S_IWRITE)  # Write only, no read
        
        validator = RuntimeFileValidator(tmp_path)
        
        errors = validator._validate_directory_access(
            test_dir, "test.path", "Test directory"
        )
        assert len(errors) == 1
        assert errors[0].code == "directory-not-readable"
        assert "not readable" in errors[0].message
        
        # Restore permissions for cleanup
        test_dir.chmod(stat.S_IREAD | stat.S_IWRITE)

    @pytest.mark.skipif(os.name == "nt", reason="Permission tests are complex on Windows")
    def test_validate_directory_access_no_write_permission(self, tmp_path: Path) -> None:
        """Test validation reports directories without write permission."""
        test_dir = tmp_path / "no_write"
        test_dir.mkdir()
        test_dir.chmod(stat.S_IREAD)  # Read only, no write
        
        validator = RuntimeFileValidator(tmp_path)
        
        errors = validator._validate_directory_access(
            test_dir, "test.path", "Test directory"
        )
        assert len(errors) == 1
        assert errors[0].code == "directory-not-writable"
        assert "not writable" in errors[0].message
        
        # Restore permissions for cleanup
        test_dir.chmod(stat.S_IREAD | stat.S_IWRITE)


class TestCSVFileValidation:
    """Tests for CSV file structure validation."""

    def test_validate_csv_files_no_pandas(self, tmp_path: Path, monkeypatch) -> None:
        """Test validation when pandas is not available."""
        # Mock pandas as unavailable
        monkeypatch.setattr("tools.config_check.runtime_file_validator.PANDAS_AVAILABLE", False)
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "params": {"reference_file": "test.csv"}
                }
            }
        }
        
        errors, warnings = validator._validate_csv_files(config)
        assert len(errors) == 0
        assert len(warnings) == 1
        assert warnings[0].code == "csv-validation-unavailable"
        assert "pandas is not available" in warnings[0].message

    def test_validate_csv_files_valid_csv(self, tmp_path: Path) -> None:
        """Test validation of valid CSV file."""
        csv_file = tmp_path / "reference.csv"
        csv_file.write_text("column1,column2,update_field\nvalue1,value2,value3\n", encoding="utf-8")
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "params": {
                        "reference_file": "reference.csv",
                        "update_field": "update_field",
                        "csv_match": {
                            "clauses": [
                                {"column": "column1", "from_context": "field1"}
                            ]
                        }
                    }
                }
            }
        }
        
        errors, warnings = validator._validate_csv_files(config)
        assert len(errors) == 0
        assert len(warnings) == 0

    def test_validate_csv_files_empty_csv(self, tmp_path: Path) -> None:
        """Test validation reports empty CSV files."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("", encoding="utf-8")
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "params": {"reference_file": "empty.csv"}
                }
            }
        }
        
        errors, warnings = validator._validate_csv_files(config)
        assert len(errors) == 1
        assert errors[0].code == "csv-invalid-format"
        assert "no data or invalid format" in errors[0].message

    def test_validate_csv_files_missing_update_field(self, tmp_path: Path) -> None:
        """Test validation reports missing update field in CSV."""
        csv_file = tmp_path / "reference.csv"
        csv_file.write_text("column1,column2\nvalue1,value2\n", encoding="utf-8")
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "params": {
                        "reference_file": "reference.csv",
                        "update_field": "missing_field"
                    }
                }
            }
        }
        
        errors, warnings = validator._validate_csv_files(config)
        assert len(errors) == 1
        assert errors[0].code == "csv-missing-column"
        assert "Update field 'missing_field' not found" in errors[0].message
        assert errors[0].path == "tasks.update_reference.params.update_field"

    def test_validate_csv_files_missing_clause_column(self, tmp_path: Path) -> None:
        """Test validation reports missing clause columns in CSV."""
        csv_file = tmp_path / "reference.csv"
        csv_file.write_text("column1,column2\nvalue1,value2\n", encoding="utf-8")
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "params": {
                        "reference_file": "reference.csv",
                        "csv_match": {
                            "clauses": [
                                {"column": "missing_column", "from_context": "field1"}
                            ]
                        }
                    }
                }
            }
        }
        
        errors, warnings = validator._validate_csv_files(config)
        assert len(errors) == 1
        assert errors[0].code == "csv-missing-column"
        assert "Clause column 'missing_column' not found" in errors[0].message
        assert errors[0].path == "tasks.update_reference.params.csv_match.clauses[0].column"

    def test_validate_csv_files_invalid_csv_format(self, tmp_path: Path) -> None:
        """Test validation reports invalid CSV format."""
        csv_file = tmp_path / "invalid.csv"
        csv_file.write_text("invalid,csv,format\n\"unclosed quote\n", encoding="utf-8")
        
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "params": {"reference_file": "invalid.csv"}
                }
            }
        }
        
        errors, warnings = validator._validate_csv_files(config)
        assert len(errors) == 1
        assert errors[0].code == "csv-parse-error"
        assert "Cannot parse CSV file" in errors[0].message

    def test_validate_csv_files_skips_missing_files(self, tmp_path: Path) -> None:
        """Test validation skips CSV validation for missing files."""
        validator = RuntimeFileValidator(tmp_path)
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "params": {"reference_file": "missing.csv"}
                }
            }
        }
        
        errors, warnings = validator._validate_csv_files(config)
        # Should not report CSV validation errors for missing files
        # (file existence is handled by reference file validation)
        assert len(errors) == 0
        assert len(warnings) == 0


class TestValidateRuntimeFilesFunction:
    """Tests for the validate_runtime_files convenience function."""

    def test_validate_runtime_files_function(self, tmp_path: Path) -> None:
        """Test the validate_runtime_files convenience function."""
        # Create test directories
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        
        config = {
            "web": {"upload_dir": "uploads"}
        }
        
        result = validate_runtime_files(config, tmp_path)
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_validate_runtime_files_function_default_base_dir(self) -> None:
        """Test the validate_runtime_files function with default base directory."""
        config = {}
        result = validate_runtime_files(config)
        assert len(result.errors) == 0
        assert len(result.warnings) == 0


class TestCheckFilesFlagIntegration:
    """Integration tests for --check-files flag functionality."""

    def test_check_files_flag_disabled_by_default(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that file validation is disabled by default."""
        config_path = config_factory.write()

        exit_code = main(["validate", "--config", str(config_path)])

        assert exit_code == 0
        lines = _capture_stdout_lines(capsys)
        # Should not show check_files=True in the arguments summary
        assert any("check_files=False" in line for line in lines)

    def test_check_files_flag_enabled(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that --check-files flag enables file validation."""
        config_path = config_factory.write()

        exit_code = main(["validate", "--config", str(config_path), "--check-files"])

        assert exit_code == 0
        lines = _capture_stdout_lines(capsys)
        # Should show check_files=True in the arguments summary
        assert any("check_files=True" in line for line in lines)

    def test_check_files_flag_reports_missing_reference_file(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that --check-files flag reports missing reference files."""
        # Create config with rules task referencing missing file
        overrides = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "class": "UpdateReference",
                    "params": {
                        "reference_file": "missing.csv"
                    }
                }
            }
        }
        config_data = config_factory.with_overrides(overrides)
        config_path = config_factory.write(config=config_data)

        exit_code = main(["validate", "--config", str(config_path), "--check-files"])

        assert exit_code == 1
        lines = _capture_stdout_lines(capsys)
        assert any("missing.csv" in line and "not found" in line for line in lines)

    def test_check_files_flag_reports_missing_directory(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that --check-files flag reports missing directories."""
        # Create config with missing upload directory
        overrides = {
            "web": {
                "upload_dir": "missing_uploads"
            }
        }
        config_data = config_factory.with_overrides(overrides)
        config_path = config_factory.write(config=config_data)

        exit_code = main(["validate", "--config", str(config_path), "--check-files"])

        assert exit_code == 1
        lines = _capture_stdout_lines(capsys)
        assert any("missing_uploads" in line and "does not exist" in line for line in lines)

    def test_check_files_flag_validates_csv_structure(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that --check-files flag validates CSV file structure."""
        # Create a CSV file with missing columns
        csv_file = config_factory.paths.base_dir / "reference.csv"
        csv_file.write_text("column1,column2\nvalue1,value2\n", encoding="utf-8")
        
        overrides = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "class": "UpdateReference",
                    "params": {
                        "reference_file": "reference.csv",
                        "update_field": "missing_field",
                        "write_value": "processed",
                        "csv_match": {
                            "clauses": [
                                {"column": "column1", "from_context": "field1"}
                            ]
                        }
                    }
                }
            }
        }
        config_data = config_factory.with_overrides(overrides)
        config_path = config_factory.write(config=config_data)

        exit_code = main([
            "validate", 
            "--config", str(config_path), 
            "--check-files",
            "--base-dir", str(config_factory.paths.base_dir)
        ])

        assert exit_code == 1
        lines = _capture_stdout_lines(capsys)
        assert any("missing_field" in line and "not found" in line for line in lines)

    def test_check_files_flag_json_output(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test --check-files flag with JSON output format."""
        # Create config with missing reference file
        overrides = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "class": "UpdateReference",
                    "params": {
                        "reference_file": "missing.csv",
                        "update_field": "status",
                        "write_value": "processed",
                        "csv_match": {
                            "clauses": [
                                {"column": "supplier_name", "from_context": "supplier_name"}
                            ]
                        }
                    }
                }
            }
        }
        config_data = config_factory.with_overrides(overrides)
        config_path = config_factory.write(config=config_data)

        exit_code = main([
            "validate", 
            "--config", str(config_path), 
            "--check-files", 
            "--format", "json",
            "--base-dir", str(config_factory.paths.base_dir)
        ])

        assert exit_code == 1
        lines = _capture_stdout_lines(capsys)
        json_payload = json.loads(_extract_json_payload(lines))
        
        assert json_payload["status"] == "invalid"
        assert json_payload["exit_code"] == 1
        assert len(json_payload["findings"]) > 0
        
        # Check that file validation error is included
        error_messages = [finding["message"] for finding in json_payload["findings"]]
        assert any("missing.csv" in msg for msg in error_messages)

    def test_check_files_flag_with_base_dir(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test --check-files flag with custom base directory."""
        # Create a CSV file in the base directory
        csv_file = config_factory.paths.base_dir / "reference.csv"
        csv_file.write_text("column1,column2,status\nvalue1,value2,pending\n", encoding="utf-8")
        
        # Create the processing directory that's expected
        processing_dir = config_factory.paths.base_dir / "processing"
        processing_dir.mkdir(exist_ok=True)
        
        overrides = {
            "tasks": {
                "extract_metadata": {
                    "module": "standard_step.extraction.extract_metadata",
                    "class": "ExtractMetadata",
                    "params": {
                        "api_key": "llx-test-key",
                        "agent_id": "agent-001",
                        "fields": {
                            "field1": {
                                "alias": "Field1",
                                "type": "str",
                            }
                        }
                    },
                },
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "class": "UpdateReference",
                    "params": {
                        "reference_file": str(csv_file),
                        "update_field": "status",
                        "write_value": "processed",
                        "csv_match": {
                            "clauses": [
                                {"column": "column1", "from_context": "field1"}
                            ]
                        }
                    }
                }
            },
            "pipeline": [
                "extract_metadata",
                "update_reference"
            ]
        }
        config_data = config_factory.with_overrides(overrides)
        config_path = config_factory.write(config=config_data)

        exit_code = main([
            "validate", 
            "--config", str(config_path), 
            "--check-files",
            "--base-dir", str(config_factory.paths.base_dir)
        ])

        assert exit_code == 0
        lines = _capture_stdout_lines(capsys)
        assert any("Validation passed" in line for line in lines)