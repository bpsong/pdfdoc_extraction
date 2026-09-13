"""Coordinate structural upgrades, legacy data import, and YAML compensation."""

from __future__ import annotations

from contextlib import closing
from typing import TYPE_CHECKING

from modules.config_protocol import ConfigProvider
from modules.db.connection import connect, immediate_transaction, utc_now
from modules.db.migrations import (
    prepare_versioned_config_schema,
    upgrade_watch_folder_management,
)
from modules.db.schema_version import (
    LEGACY_SCHEMA_VERSION,
    PROCESSING_QUEUE_SCHEMA_VERSION,
    SCHEMA_VERSION,
    TARGET_VERSIONED_CONFIG_SCHEMA_VERSION,
)

if TYPE_CHECKING:
    from modules.services.legacy_versioned_config_migration import (
        LegacyVersionedConfigMigration,
    )


def initialize_database(config_manager: ConfigProvider) -> None:
    """Create the SQLite database and run idempotent schema migrations."""
    migration: LegacyVersionedConfigMigration | None = None
    with closing(connect(config_manager)) as conn, conn:
        prepare_versioned_config_schema(conn)
        upgrade_watch_folder_management(conn)
        existing = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (SCHEMA_VERSION,),
        ).fetchone()
        if existing is not None:
            return
        processing_queue_schema_exists = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (PROCESSING_QUEUE_SCHEMA_VERSION,),
        ).fetchone() is not None
        if processing_queue_schema_exists:
            with immediate_transaction(conn):
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )
            return
        versioned_schema_exists = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (TARGET_VERSIONED_CONFIG_SCHEMA_VERSION,),
        ).fetchone() is not None
        if versioned_schema_exists:
            with immediate_transaction(conn):
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (PROCESSING_QUEUE_SCHEMA_VERSION, utc_now()),
                )
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )
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
                    from modules.services.legacy_versioned_config_migration import (
                        LegacyVersionedConfigMigration,
                    )

                    migration = LegacyVersionedConfigMigration(conn, config_manager)
                    migration.run()
                if conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?",
                    (TARGET_VERSIONED_CONFIG_SCHEMA_VERSION,),
                ).fetchone() is None:
                    conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (TARGET_VERSIONED_CONFIG_SCHEMA_VERSION, utc_now()),
                    )
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (PROCESSING_QUEUE_SCHEMA_VERSION, utc_now()),
                )
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
