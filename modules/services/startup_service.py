"""Process startup checks for database schema, published rules, and task trust."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import json
import sqlite3
from typing import Literal

from modules.config_protocol import ConfigProvider
from modules.db.connection import get_db_path
from modules.services.startup_migration_service import initialize_database
from modules.db.schema_version import SCHEMA_VERSION
from modules.services.task_registry_service import validate_startup_task_registry
from modules.services.business_validation_schema import validate_business_validation_schema
from modules.services.versioned_config_contracts import SUPPORTED_REVIEW_SCHEMA_FORMAT_VERSIONS


MigrationMode = Literal["migrate", "verify"]

REQUIRED_RUNTIME_TABLES = frozenset(
    {
        "batches",
        "documents",
        "pipeline_versions",
        "processing_jobs",
        "pipeline_cleanup_previews",
        "review_schema_versions",
        "manual_split_decisions",
        "runtime_component_health",
        "schema_migrations",
        "task_runs",
        "users",
        "upload_submissions",
        "watch_folder_bindings",
        "watch_folder_health",
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


def verify_business_validation_compatibility(config: ConfigProvider) -> None:
    """Fail startup if published rules require an unavailable implementation."""
    try:
        with closing(sqlite3.connect(
            _read_only_database_uri(get_db_path(config)), uri=True,
        )) as conn:
            for row in conn.execute("SELECT schema_json, format_version FROM review_schema_versions"):
                schema = json.loads(row[0])
                if (row[1] not in SUPPORTED_REVIEW_SCHEMA_FORMAT_VERSIONS
                        or not isinstance(schema, dict) or validate_business_validation_schema(schema)):
                    raise StartupReadinessError(
                        "Published business-validation rules are unsupported or invalid."
                    )
    except (sqlite3.Error, ValueError, TypeError) as exc:
        raise StartupReadinessError(
            "Published review-rule compatibility could not be verified."
        ) from exc


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
    verify_business_validation_compatibility(config)
    validate_startup_task_registry(config)
