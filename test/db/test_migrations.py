from pathlib import Path

from modules.db.connection import connect
from modules.db.schema_version import SCHEMA_VERSION
from modules.services.startup_service import verify_database_schema
from modules.services.startup_migration_service import initialize_database


class TempConfig:
    def __init__(self, config_path: Path, db_path: Path) -> None:
        self._config_path = config_path
        self._values = {"database.path": str(db_path)}

    def get(self, key, default=None):
        return self._values.get(key, default)


def test_initialize_database_creates_schema_and_is_idempotent(tmp_path):
    config = TempConfig(tmp_path / "config.yaml", tmp_path / "state" / "app.sqlite3")

    initialize_database(config)
    initialize_database(config)

    with connect(config) as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        migration_versions = {
            row["version"]
            for row in conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }

    assert "batches" in tables
    assert "documents" in tables
    assert "task_runs" in tables
    assert "runtime_component_health" in tables
    assert "pending_upload_files" in tables
    assert migration_versions == {2, 3, 4, SCHEMA_VERSION}


def test_v9_upgrade_starts_with_empty_pending_upload_journal(tmp_path: Path) -> None:
    config = TempConfig(tmp_path / "config.yaml", tmp_path / "state.sqlite3")
    initialize_database(config)
    with connect(config) as conn:
        conn.execute("DROP TABLE pending_upload_files")
        conn.execute("UPDATE schema_migrations SET version=9 WHERE version=?", (SCHEMA_VERSION,))
    initialize_database(config)
    verify_database_schema(config)
    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_upload_files").fetchone()[0] == 0
        conn.execute("INSERT INTO pending_upload_files VALUES ('pending.pdf')")
    initialize_database(config)
    with connect(config) as conn:
        assert conn.execute("SELECT file_path FROM pending_upload_files").fetchone()[0] == "pending.pdf"
