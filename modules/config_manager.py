"""Load deployment configuration and report failures without exiting the process."""

from __future__ import annotations

from copy import deepcopy
import logging
from pathlib import Path
from typing import Any, Iterator, NoReturn

import yaml

from modules.config_paths import resolve_config_path


DEFAULT_CONFIG: dict[str, Any] = {
    "database": {
        "path": "data/app_state.sqlite3",
        "run_migrations_on_startup": True,
    },
    "review": {
        "lock_timeout_minutes": 60,
        "default_queue_name": "default_review",
    },
    "validation": {
        "config_validation_enabled": True,
        "allow_ui_config_save": False,
        "strict_mode_default": False,
    },
    "ui": {
        "app_name": "DocFlow AI",
        "page_size": 25,
        "admin_enabled": True,
        "operator_sidebar": ["upload", "review", "reports", "settings"],
    },
    "web": {
        "max_upload_mb": 50,
        "max_upload_files": 20,
        "max_upload_request_mb": 200,
        "max_concurrent_uploads": 2,
        "upload_idle_timeout_seconds": 30,
        "upload_timeout_seconds": 600,
    },
    "custom_steps": {
        "enabled": False,
        "registry": {},
    },
    "processing_queue": {
        "poll_interval": 1,
        "lease_seconds": 3600,
        "max_attempts": 3,
        "retry_delay": 5,
    },
}


def _merge_defaults(
    config: dict[str, Any], defaults: dict[str, Any]
) -> dict[str, Any]:
    """Return config with missing nested default keys filled in."""
    merged = deepcopy(defaults)
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(value, merged[key])
        else:
            merged[key] = value
    return merged


class ConfigurationError(ValueError):
    """Invalid deployment configuration, safe to report without source values."""


class ConfigManager:
    """Load and validate deployment settings for the current process."""

    def __init__(self, config_path: Path, *, prepare_directories: bool = True) -> None:
        self.logger = logging.getLogger("ConfigManager")
        try:
            self._config_path = Path(config_path).expanduser().resolve()
        except (OSError, ValueError, RuntimeError):
            self._fail("Configuration file path could not be resolved.")
        self._load_config()
        self._validate_static_paths()
        self._validate_watch_folder()
        if prepare_directories:
            self.prepare_directories()
        self._validate_dynamic_paths()

    @property
    def config(self) -> dict[str, Any]:
        """Return a defensive snapshot for compatibility with read-only callers."""
        return self.get_all()

    def get(self, key: str, default: Any = None) -> Any:
        """Return a dot-delimited configuration value."""
        value = self._config
        for part in key.split("."):
            if not isinstance(value, dict):
                return deepcopy(default)
            value = value.get(part, default)
        return deepcopy(value)

    def get_all(self) -> dict[str, Any]:
        """Return the deployment configuration."""
        return deepcopy(self._config)

    def replace_config(self, values: dict[str, Any]) -> None:
        """Validate and replace this process's snapshot without filesystem writes.

        Startup migration is the owner of this operation. Other processes load
        their snapshots after migration; live YAML changes require a restart.
        """
        candidate = object.__new__(ConfigManager)
        candidate._config_path = self._config_path
        candidate.logger = self.logger
        candidate._config = _merge_defaults(deepcopy(values), DEFAULT_CONFIG)
        candidate._validate_static_paths()
        candidate._validate_watch_folder()
        candidate._validate_dynamic_paths()
        self._config = candidate._config

    def _fail(self, message: str) -> NoReturn:
        self.logger.critical(message)
        raise ConfigurationError(message) from None

    def _load_config(self) -> None:
        try:
            with self._config_path.open(encoding="utf-8") as handle:
                values = yaml.safe_load(handle)
        except yaml.YAMLError:
            self._fail("Invalid YAML in configuration file.")
        except (OSError, UnicodeError):
            self._fail("Error reading configuration file.")
        if not isinstance(values, dict):
            self._fail("Configuration file root must be a dictionary")
        self._config = _merge_defaults(values, DEFAULT_CONFIG)

    def _validate_static_paths(self) -> None:
        self._validate_required_directory("web.upload_dir")

    def _validate_watch_folder(self) -> None:
        self._validate_required_directory("watch_folder.dir")

    def _validate_required_directory(self, key: str) -> None:
        value = self.get(key)
        if not isinstance(value, str) or not value:
            self._fail(f"Missing required static path in config: '{key}'")
        try:
            valid = self._resolve_path(value).is_dir()
        except (OSError, ValueError, RuntimeError):
            valid = False
        if not valid:
            self._fail(f"Static path invalid: '{key}'")

    def _paths(self, value: Any, prefix: str = "root") -> Iterator[tuple[str, str, str]]:
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    self._fail("Configuration keys must be strings.")
                location = f"{prefix}.{key}"
                if key.endswith(("_dir", "_file")) and isinstance(child, str):
                    yield location, key, child
                else:
                    yield from self._paths(child, location)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from self._paths(child, f"{prefix}[{index}]")

    def prepare_directories(self) -> None:
        """Create configured *_dir paths; required upload/watch roots must exist."""
        for _location, key, value in self._paths(self.config):
            if key.endswith("_dir"):
                try:
                    self._resolve_path(value).mkdir(parents=True, exist_ok=True)
                except (OSError, ValueError, RuntimeError):
                    self._fail("Could not create directory configured by a *_dir key.")

    def _validate_dynamic_paths(self) -> None:
        for _location, key, value in self._paths(self.config):
            directory = key.endswith("_dir")
            try:
                path = self._resolve_path(value)
                valid = path.is_dir() if directory else path.is_file()
            except (OSError, ValueError, RuntimeError):
                valid = False
            if not valid:
                kind = "directory" if directory else "file"
                self._fail(f"Configured path does not exist or isn’t a {kind}.")

    def _resolve_path(self, raw_path: str | Path) -> Path:
        return resolve_config_path(raw_path, config_path=self._config_path)
