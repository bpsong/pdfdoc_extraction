"""SQLite schema initialization and migration runner."""

from __future__ import annotations

from pathlib import Path

from modules.config_manager import ConfigManager
from modules.db.connection import connect, transaction, utc_now


SCHEMA_VERSION = 1


def initialize_database(config_manager: ConfigManager) -> None:
    """Create the SQLite database and run idempotent schema migrations."""
    with connect(config_manager) as conn:
        schema_path = Path(__file__).with_name("schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")
        with transaction(conn):
            conn.executescript(schema_sql)
            existing = conn.execute(
                "SELECT version FROM schema_migrations WHERE version = ?",
                (SCHEMA_VERSION,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )
