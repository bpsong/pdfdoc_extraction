"""Tests for the config_check CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.config_check.__main__ import main, resolve_config_path, validate_format_choice


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


class TestUtilityFunctions:
    """Unit tests for helper utilities exposed by the CLI."""

    def test_validate_format_choice_accepts_supported_values(self) -> None:
        assert validate_format_choice("text", ["text", "json"]) == "text"
        assert validate_format_choice("json", ["text", "json"]) == "json"

    def test_validate_format_choice_rejects_invalid_value(self) -> None:
        with pytest.raises(ValueError) as exc:
            validate_format_choice("yaml", ["text", "json"])
        assert "Invalid format 'yaml'" in str(exc.value)

    def test_resolve_config_path_existing_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("web: {}", encoding="utf-8")

        resolved, exists = resolve_config_path(str(config_file))

        assert exists is True
        assert Path(resolved) == config_file.resolve()

    def test_resolve_config_path_missing_file_emits_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        missing = "does-not-exist.yaml"
        resolved, exists = resolve_config_path(missing)

        assert exists is False
        assert resolved.endswith(missing)

        lines = _capture_stdout_lines(capsys)
        assert any("does not exist" in line for line in lines)


class TestValidateCommand:
    """Functional tests targeting the validate subcommand."""

    def test_validate_success_with_text_output(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        config_path = config_factory.write()

        exit_code = main(["validate", "--config", str(config_path)])

        assert exit_code == 0
        lines = _capture_stdout_lines(capsys)
        assert any("config_path=" in line for line in lines)
        assert any("Validation passed" in line for line in lines)

    def test_validate_supports_json_output(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        config_path = config_factory.write(name="config.json.yaml")

        exit_code = main(["validate", "--config", str(config_path), "--format", "json"])

        assert exit_code == 0
        lines = _capture_stdout_lines(capsys)
        json_payload = json.loads(_extract_json_payload(lines))
        assert json_payload["status"] == "valid"
        assert json_payload["exit_code"] == 0

    def test_validate_with_strict_mode_reports_unknown_key(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        config_data = config_factory.with_overrides({"web": {"unexpected": True}})
        config_path = config_factory.write(config=config_data)

        exit_code = main(["validate", "--config", str(config_path), "--strict"])

        assert exit_code == 1
        lines = _capture_stdout_lines(capsys)
        assert any("[ERROR] web.unexpected" in line for line in lines)

    def test_validate_with_base_dir_allows_relative_paths(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        overrides = {
            "web": {"upload_dir": "uploads"},
            "watch_folder": {"dir": "watch"},
            "tasks": {
                "store_json": {
                    "params": {"data_dir": "data"}
                },
                "archive_pdf": {
                    "params": {"archive_dir": "archive"}
                },
            },
        }
        config_data = config_factory.with_overrides(overrides)
        config_path = config_factory.write(config=config_data)

        exit_code = main(
            [
                "validate",
                "--config",
                str(config_path),
                "--base-dir",
                str(config_factory.paths.base_dir),
            ]
        )

        assert exit_code == 0
        lines = _capture_stdout_lines(capsys)
        assert any("base_dir=" in line for line in lines)
        assert any("Validation passed" in line for line in lines)

    def test_validate_reports_import_errors_when_enabled(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        overrides = {
            "tasks": {
                "store_json": {
                    "module": "nonexistent.module",
                }
            }
        }
        config_data = config_factory.with_overrides(overrides)
        config_path = config_factory.write(config=config_data)

        exit_code = main(
            [
                "validate",
                "--config",
                str(config_path),
                "--import-checks",
            ]
        )

        assert exit_code == 1
        lines = _capture_stdout_lines(capsys)
        assert any("store_json" in line and "Module" in line and "not found" in line for line in lines)

    def test_validate_reports_yaml_parse_error(
        self,
        config_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        config_path = config_factory.write_text(
            """
            web:
              upload_dir: "./uploads
            """,
            name="broken.yaml",
        )

        exit_code = main(["validate", "--config", str(config_path)])

        assert exit_code == 1
        lines = _capture_stdout_lines(capsys)
        assert any("[ERROR] config" in line for line in lines)
        assert any("yaml" in line.lower() or "parsing" in line.lower() for line in lines)

    def test_validate_missing_file_returns_usage_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([
            "validate",
            "--config",
            "missing.yaml",
        ])

        assert exit_code == 64
        lines = _capture_stdout_lines(capsys)
        assert any("Configuration file not found" in line for line in lines)


class TestSchemaCommand:
    """Tests for schema subcommand semantics."""

    def test_schema_command_outputs_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["schema", "--format", "json"])

        assert exit_code == 0
        lines = _capture_stdout_lines(capsys)
        schema_json = json.loads(_extract_json_payload(lines))
        assert "$defs" in schema_json

    def test_schema_command_rejects_text_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["schema", "--format", "text"])

        assert exit_code == 64
        captured = capsys.readouterr()
        assert "invalid choice" in captured.err.lower()


class TestArgumentValidation:
    """Assorted argument validation cases that return usage errors."""

    def test_missing_subcommand_returns_usage_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([])

        assert exit_code == 64
        stderr_output = capsys.readouterr().err
        assert "arguments are required" in stderr_output

    def test_invalid_format_exits_with_usage_code(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["validate", "--format", "xml"])

        assert exit_code == 64
        captured = capsys.readouterr()
        assert "invalid choice" in captured.err.lower()
