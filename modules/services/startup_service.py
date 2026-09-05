"""Process startup checks for database schema and task trust configuration."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Literal

from modules.config_protocol import ConfigProvider
from modules.db.connection import get_db_path
from modules.db.migrations import SCHEMA_VERSION, initialize_database
from modules.services.task_registry_service import validate_startup_task_registry


MigrationMode = Literal["migrate", "verify"]

REQUIRED_RUNTIME_TABLES = frozenset(
    {
        "batches",
        "documents",
        "pipeline_versions",
        "processing_jobs",
        "review_schema_versions",
        "runtime_component_health",
        "schema_migrations",
        "task_runs",
        "users",
        "watch_folder_bindings",
    }
)


class StartupReadinessError(RuntimeError):
    """Raised when a process cannot safely use the configured database."""


def _read_only_database_uri(path: Path) -> str:
    """Return a SQLite URI that cannot create or modify the database."""
    return f"{path.resolve().as_uri()}?mode=ro"


def verify_database_schema(config: ConfigProvider) -> None:
    """Verify that the configured database has the exact supported schema."""
    database_path = get_db_path(config)
    if not database_path.is_file():
        raise StartupReadinessError("The configured application database is missing.")

    try:
        with sqlite3.connect(
            _read_only_database_uri(database_path),
            uri=True,
        ) as conn:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            missing_tables = REQUIRED_RUNTIME_TABLES - tables
            if missing_tables:
                missing = ", ".join(sorted(missing_tables))
                raise StartupReadinessError(
                    f"The application database is missing required tables: {missing}."
                )
            row = conn.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()
    except StartupReadinessError:
        raise
    except sqlite3.Error as exc:
        raise StartupReadinessError(
            "The configured application database could not be verified."
        ) from exc

    version = int(row[0]) if row and row[0] is not None else None
    if version != SCHEMA_VERSION:
        raise StartupReadinessError(
            "The application database schema is incompatible with this release: "
            f"expected version {SCHEMA_VERSION}, found {version or 'none'}."
        )


def run_startup_checks(
    config: ConfigProvider,
    *,
    migration_mode: MigrationMode,
) -> None:
    """Migrate when authorized, then verify schema and task trust settings."""
    if migration_mode not in {"migrate", "verify"}:
        raise ValueError(f"Unsupported migration mode: {migration_mode}")
    if migration_mode == "migrate" and bool(
        config.get("database.run_migrations_on_startup", True)
    ):
        initialize_database(config)
    verify_database_schema(config)
    validate_startup_task_registry(config)
