"""Startup ordering and safe migration-failure tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import main
from test.core.test_runtime_orchestration import DictConfig


def _patch_common(monkeypatch, config):
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: SimpleNamespace(config_path=None, no_web=True),
    )
    monkeypatch.setattr(
        main, "resolve_config_path", lambda args: Path("synthetic-config.yaml")
    )
    monkeypatch.setattr(main, "ConfigManager", lambda config_path: config)
    monkeypatch.setattr(main, "setup_logging", Mock())
    monkeypatch.setattr(main, "validate_startup_task_registry", Mock())
    monkeypatch.setattr(main, "ShutdownManager", lambda: Mock())


def test_startup_refuses_web_watch_and_ingestion_after_migration_failure(
    monkeypatch, caplog
):
    config = DictConfig({"database.run_migrations_on_startup": True})
    _patch_common(monkeypatch, config)
    sensitive = "synthetic-secret-at-C:/customer/config.yaml"
    monkeypatch.setattr(
        main,
        "initialize_database",
        Mock(side_effect=RuntimeError(sensitive)),
    )
    workflow = Mock()
    processor = Mock()
    coordinator = Mock()
    web = Mock()
    monkeypatch.setattr(main, "WorkflowManager", workflow)
    monkeypatch.setattr(main, "FileProcessor", processor)
    monkeypatch.setattr(main, "WatchFolderCoordinator", coordinator)
    monkeypatch.setattr(main, "start_web_server", web)

    with pytest.raises(SystemExit) as error:
        main.main()

    assert error.value.code == 1
    workflow.assert_not_called()
    processor.assert_not_called()
    coordinator.assert_not_called()
    web.assert_not_called()
    assert sensitive not in caplog.text
    assert "startup is blocked" in caplog.text


def test_successful_migration_precedes_runtime_construction(monkeypatch):
    config = DictConfig({"database.run_migrations_on_startup": True})
    _patch_common(monkeypatch, config)
    events = []
    monkeypatch.setattr(
        main, "initialize_database", lambda cfg: events.append("migration")
    )
    monkeypatch.setattr(
        main, "WorkflowManager", lambda cfg: events.append("workflow") or Mock()
    )
    monkeypatch.setattr(
        main,
        "FileProcessor",
        lambda *args: events.append("processor") or Mock(),
    )

    class Coordinator:
        def __init__(self, config_manager, processor):
            events.append("coordinator")

        def start(self):
            events.append("watch-start")

        def stop(self):
            events.append("watch-stop")

    monkeypatch.setattr(main, "WatchFolderCoordinator", Coordinator)

    with pytest.raises(SystemExit) as error:
        main.main()

    assert error.value.code == 0
    assert events[:5] == [
        "migration",
        "workflow",
        "processor",
        "coordinator",
        "watch-start",
    ]
