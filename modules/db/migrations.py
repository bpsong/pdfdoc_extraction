"""SQLite schema initialization and migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from modules.config_protocol import ConfigProvider
from modules.db.connection import connect, immediate_transaction, utc_now
from modules.services.legacy_versioned_config_migration import (
    LegacyVersionedConfigMigration,
)


LEGACY_SCHEMA_VERSION = 2
SCHEMA_VERSION = 3
TARGET_VERSIONED_CONFIG_SCHEMA_VERSION = 3


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Return column names for an existing table."""
    return {
        str(row[1])
        for row in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    }


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    """Add one nullable preparatory column when its table already exists."""
    columns = _table_columns(conn, table_name)
    if columns and column_name not in columns:
        conn.execute(
            f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_sql}'
        )


def _execute_schema_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute a SQLite script statement-by-statement in the caller's transaction."""
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                conn.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("Database schema contains an incomplete SQL statement.")


def upgrade_v2_to_v3_structure(conn: sqlite3.Connection) -> None:
    """Prepare target version-3 structure without performing the data cutover.

    Phase 8 owns legacy data import, assignment backfill, and recording schema
    version 3. This preparatory step is safe for the current runtime because all
    assignment columns remain nullable until that cutover.
    """
    additions = {
        "batches": {
            "pipeline_template_id": "TEXT",
            "pipeline_version_id": "TEXT",
            "pipeline_assignment_source": "TEXT",
            "ingress_binding_id": "TEXT",
        },
        "documents": {
            "pipeline_template_id": "TEXT",
            "pipeline_version_id": "TEXT",
        },
        "task_runs": {
            "pipeline_version_id": "TEXT",
        },
        "review_items": {
            "review_schema_version_id": "TEXT",
        },
    }
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with immediate_transaction(conn):
        for table_name, columns in additions.items():
            for column_name, column_sql in columns.items():
                _add_column_if_missing(
                    conn,
                    table_name,
                    column_name,
                    column_sql,
                )
        _execute_schema_script(conn, schema_sql)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "Cannot prepare schema version 3 because foreign-key violations exist."
            )


def prepare_versioned_config_schema(conn: sqlite3.Connection) -> None:
    """Backward-compatible name for the explicit version 2-to-3 preparation."""
    upgrade_v2_to_v3_structure(conn)


def initialize_database(config_manager: ConfigProvider) -> None:
    """Create the SQLite database and run idempotent schema migrations."""
    migration: LegacyVersionedConfigMigration | None = None
    with connect(config_manager) as conn:
        prepare_versioned_config_schema(conn)
        existing = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (SCHEMA_VERSION,),
        ).fetchone()
        if existing is not None:
            return
        legacy_v2_exists = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (LEGACY_SCHEMA_VERSION,),
        ).fetchone() is not None
        legacy_state_exists = conn.execute(
            "SELECT 1 FROM batches LIMIT 1"
        ).fetchone() is not None
        try:
            with immediate_transaction(conn):
                if conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?",
                    (LEGACY_SCHEMA_VERSION,),
                ).fetchone() is None:
                    conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (LEGACY_SCHEMA_VERSION, utc_now()),
                    )
                if legacy_v2_exists or legacy_state_exists:
                    migration = LegacyVersionedConfigMigration(conn, config_manager)
                    migration.run()
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )
        except Exception:
            if migration is not None:
                migration.compensate_config()
            raise
    if migration is not None:
        migration.apply_runtime_config()
