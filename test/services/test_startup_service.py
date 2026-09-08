"""Tests for process startup migration ownership and schema verification."""

from __future__ import annotations

import sqlite3
from unittest.mock import Mock

import pytest

from modules.db.migrations import initialize_database
from modules.services import startup_service
from test.helpers_sqlite import TempConfig


def test_migration_owner_runs_checks_in_order(monkeypatch, tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")
    events: list[str] = []
    monkeypatch.setattr(
        startup_service,
        "initialize_database",
        lambda cfg: events.append("migrate"),
    )
    monkeypatch.setattr(
        startup_service,
        "verify_database_schema",
        lambda cfg: events.append("verify"),
    )
    monkeypatch.setattr(
        startup_service,
        "validate_startup_task_registry",
        lambda cfg: events.append("registry"),
    )

    startup_service.run_startup_checks(config, migration_mode="migrate")

    assert events == ["migrate", "verify", "registry"]


def test_verify_mode_never_runs_migrations(monkeypatch, tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")
    migration = Mock()
    verify = Mock()
    registry = Mock()
    monkeypatch.setattr(startup_service, "initialize_database", migration)
    monkeypatch.setattr(startup_service, "verify_database_schema", verify)
    monkeypatch.setattr(startup_service, "validate_startup_task_registry", registry)

    startup_service.run_startup_checks(config, migration_mode="verify")

    migration.assert_not_called()
    verify.assert_called_once_with(config)
    registry.assert_called_once_with(config)


def test_disabled_migrations_still_require_schema_verification(monkeypatch, tmp_path):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"database": {"run_migrations_on_startup": False}},
    )
    migration = Mock()
    verify = Mock()
    monkeypatch.setattr(startup_service, "initialize_database", migration)
    monkeypatch.setattr(startup_service, "verify_database_schema", verify)
    monkeypatch.setattr(startup_service, "validate_startup_task_registry", Mock())

    startup_service.run_startup_checks(config, migration_mode="migrate")

    migration.assert_not_called()
    verify.assert_called_once_with(config)


def test_schema_verification_accepts_initialized_database(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)

    startup_service.verify_database_schema(config)


def test_schema_verification_does_not_create_missing_database(tmp_path):
    database_path = tmp_path / "missing" / "app.sqlite3"
    config = TempConfig(database_path)

    with pytest.raises(
        startup_service.StartupReadinessError,
        match="database is missing",
    ):
        startup_service.verify_database_schema(config)

    assert not database_path.exists()


def test_schema_verification_rejects_newer_database(tmp_path):
    database_path = tmp_path / "app.sqlite3"
    config = TempConfig(database_path)
    initialize_database(config)
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (999, "synthetic"),
        )

    with pytest.raises(
        startup_service.StartupReadinessError,
        match="expected version 7, found 999",
    ):
        startup_service.verify_database_schema(config)


def test_schema_verification_rejects_missing_required_table(tmp_path):
    database_path = tmp_path / "app.sqlite3"
    config = TempConfig(database_path)
    initialize_database(config)
    with sqlite3.connect(database_path) as conn:
        conn.execute("DROP TABLE processing_jobs")

    with pytest.raises(
        startup_service.StartupReadinessError,
        match="processing_jobs",
    ):
        startup_service.verify_database_schema(config)


def test_schema_verification_rejects_older_database_marker(tmp_path):
    database_path = tmp_path / "app.sqlite3"
    config = TempConfig(database_path)
    initialize_database(config)
    with sqlite3.connect(database_path) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = 7")

    with pytest.raises(
        startup_service.StartupReadinessError,
        match="expected version 7, found 4",
    ):
        startup_service.verify_database_schema(config)


def test_unknown_migration_mode_is_rejected(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")

    with pytest.raises(ValueError, match="Unsupported migration mode"):
        startup_service.run_startup_checks(config, migration_mode="invalid")
# pyright: reportArgumentType=false
