"""Keep test collection and import-time application startup isolated."""

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from modules.config_manager import ConfigManager
from modules.services.startup_migration_service import initialize_database

os.environ.setdefault('PREFECT_LOGGING_TO_API_ENABLED', 'false')
server_logger = logging.getLogger('prefect.server.api.server')
server_logger.disabled = True
server_logger.handlers.clear()
server_logger.propagate = False


def pytest_configure(config: pytest.Config) -> None:
    """Provide synthetic configuration before test modules import the web app."""
    temporary = TemporaryDirectory(prefix="docflow-pytest-", ignore_cleanup_errors=True)
    config.add_cleanup(temporary.cleanup)
    root = Path(temporary.name)
    for name in ("uploads", "watch", "processing"):
        (root / name).mkdir()
    log_path = root / "app.log"
    log_path.touch()
    config_path = root / "config.yaml"
    config_path.write_text(yaml.safe_dump({
        "database": {"path": str(root / "state.sqlite3")},
        "web": {
            "upload_dir": str(root / "uploads"),
            "secret_key": "synthetic-pytest-signing-key-for-isolated-startup",
            "allowed_hosts": ["localhost", "127.0.0.1", "testserver"],
        },
        "watch_folder": {
            "dir": str(root / "watch"),
            "processing_dir": str(root / "processing"),
        },
        "logging": {"log_file": str(log_path)},
        "pipeline": [], "tasks": {},
    }), encoding="utf-8")
    initialize_database(ConfigManager(config_path))
    environment = pytest.MonkeyPatch()
    environment.setenv("CONFIG_PATH", str(config_path))
    config.add_cleanup(environment.undo)
