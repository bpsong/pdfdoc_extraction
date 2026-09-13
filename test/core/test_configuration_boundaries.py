"""Regression tests for configuration ownership and path boundaries."""

from pathlib import Path
import os
import subprocess
import sys
import pytest
import yaml

from modules.config_manager import ConfigManager, ConfigurationError
from modules.db.connection import get_db_path
from tools.config_check.stored_validator import configured_database_path
from tools.config_check.validator import ConfigValidator


def test_paths_agree_outside_working_directory(tmp_path: Path, monkeypatch) -> None:
    deployment = tmp_path / "deployment"
    deployment.mkdir()
    for name in ("uploads", "watch"):
        (deployment / name).mkdir()
    config_path = deployment / "config.yaml"
    values = {
        "web": {"upload_dir": "uploads"},
        "watch_folder": {"dir": "watch"},
        "database": {"path": "state.sqlite3"},
    }
    config_path.write_text(yaml.safe_dump(values), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    manager = ConfigManager(Path("deployment/config.yaml"))
    checker = ConfigValidator()
    checker.validate(config_path)
    assert checker.path_validator._resolve_path("uploads")[0] == deployment / "uploads"
    assert get_db_path(manager) == configured_database_path(config_path, values)
    monkeypatch.chdir(deployment)
    assert get_db_path(manager) == deployment / "state.sqlite3"
    assert manager._resolve_path("uploads") == deployment / "uploads"


def test_explicit_validation_base_does_not_redirect_database(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    override = tmp_path / "override"
    checker = ConfigValidator(base_dir=override)
    checker.validate(config_path)
    assert checker.path_validator._resolve_path("uploads")[0] == override / "uploads"
    assert configured_database_path(config_path, {"database": {"path": "db"}}) == tmp_path / "db"


def test_validation_failure_does_not_create_directories_or_expose_yaml(
    tmp_path: Path, monkeypatch, caplog,
) -> None:
    for name in ("uploads", "watch"):
        (tmp_path / name).mkdir()
    path = tmp_path / "config.yaml"
    path.write_text(
        "web: {upload_dir: uploads}\nwatch_folder: {dir: watch}\noutput_dir: missing\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError):
        ConfigManager(path, prepare_directories=False)
    assert not (tmp_path / "missing").exists()
    # Failed initialization must not poison the next attempt.
    manager = ConfigManager(path)
    assert manager.get("output_dir") == "missing"
    assert (tmp_path / "missing").is_dir()
    path.write_text("secret: [synthetic-private-value\n", encoding="utf-8")
    with pytest.raises(ConfigurationError) as error:
        ConfigManager(path)
    assert "synthetic-private-value" not in str(error.value)
    assert "synthetic-private-value" not in caplog.text


def test_independent_snapshots_and_atomic_replacement(tmp_path: Path) -> None:
    for name in ("uploads", "watch"):
        (tmp_path / name).mkdir()
    path = tmp_path / "config.yaml"
    values = {"web": {"upload_dir": "uploads"}, "watch_folder": {"dir": "watch"},
              "items": ["original"]}
    path.write_text(yaml.safe_dump(values), encoding="utf-8")
    first = ConfigManager(path)
    other_path = tmp_path / "other.yaml"
    other_path.write_text(yaml.safe_dump(values), encoding="utf-8")
    second = ConfigManager(other_path)
    assert first._config_path != second._config_path
    first.get("items").append("changed")
    first.get_all()["web"]["upload_dir"] = "missing"
    first.config["items"].clear()
    assert first.get("items") == second.get("items") == ["original"]
    values["items"] = ["replacement"]
    first.replace_config(values)
    values["items"].clear()
    assert first.get("items") == ["replacement"]
    assert second.get("items") == ["original"]
    with pytest.raises(ConfigurationError):
        first.replace_config({"web": {"upload_dir": "missing"}})
    assert first.get("items") == ["replacement"]


def test_environment_paths_are_consistent(tmp_path: Path, monkeypatch) -> None:
    from modules.config_paths import resolve_config_path
    from tools.config_check.path_validator import PathValidator
    from tools.config_check.runtime_file_validator import RuntimeFileValidator

    monkeypatch.setenv("DOCFLOW_TEST_BASE", str(tmp_path))
    raw = "%DOCFLOW_TEST_BASE%/state.sqlite3"
    assert resolve_config_path(raw) == tmp_path / "state.sqlite3"
    assert PathValidator()._resolve_path(raw)[0] == tmp_path / "state.sqlite3"
    assert RuntimeFileValidator()._resolve_path(raw) == tmp_path / "state.sqlite3"


@pytest.mark.parametrize("command", [
    ["main.py"],
    ["-m", "tools.processing_worker"],
    ["-m", "uvicorn", "web.server:app"],
])
def test_process_entry_rejects_invalid_config_without_source_values(
    tmp_path: Path, command: list[str],
) -> None:
    path = tmp_path / "invalid.yaml"
    sentinel = "synthetic-private-yaml-value"
    path.write_text(f"secret: [{sentinel}\n", encoding="utf-8")
    env = {**os.environ, "CONFIG_PATH": str(path)}
    args = command if "uvicorn" in command else [*command, "--config-path", str(path)]
    result = subprocess.run(
        [sys.executable, *args], env=env, capture_output=True,
        text=True, timeout=30, check=False,
    )
    assert result.returncode != 0
    assert "Invalid YAML" in result.stdout + result.stderr
    assert sentinel not in result.stdout + result.stderr
