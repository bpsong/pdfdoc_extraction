"""Connection lifetime and transaction behavior for managed SQLite access."""

import sqlite3

import pytest

from modules.db.connection import managed_connect


class _Config:
    def __init__(self, path):
        self.path = path

    def get(self, key, default=None):
        return str(self.path) if key == "database.path" else default


def test_managed_connection_commits_and_closes(tmp_path):
    config = _Config(tmp_path / "state.sqlite3")
    with managed_connect(config) as conn:
        conn.execute("CREATE TABLE item (value TEXT)")
        conn.execute("INSERT INTO item VALUES ('saved')")

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT * FROM item")
    with sqlite3.connect(config.path) as verify:
        assert verify.execute("SELECT value FROM item").fetchone() == ("saved",)


def test_managed_connection_rolls_back_and_closes(tmp_path):
    config = _Config(tmp_path / "state.sqlite3")
    with managed_connect(config) as conn:
        conn.execute("CREATE TABLE item (value TEXT)")

    with pytest.raises(ValueError, match="abort"):
        with managed_connect(config) as conn:
            conn.execute("INSERT INTO item VALUES ('discarded')")
            raise ValueError("abort")

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT * FROM item")
    with sqlite3.connect(config.path) as verify:
        assert verify.execute("SELECT COUNT(*) FROM item").fetchone() == (0,)
