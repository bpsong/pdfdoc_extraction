from pathlib import Path

from modules.db.connection import connect
from modules.db.migrations import initialize_database


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
        migration_count = conn.execute("SELECT COUNT(*) AS count FROM schema_migrations").fetchone()["count"]

    assert "batches" in tables
    assert "documents" in tables
    assert "task_runs" in tables
    assert migration_count == 1
