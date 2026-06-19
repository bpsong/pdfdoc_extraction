"""SQLite connection and serialization helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from modules.config_protocol import ConfigProvider


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for persisted state."""
    return datetime.now(timezone.utc).isoformat()


def json_dumps(value: Any) -> str:
    """Serialize a value to JSON text for SQLite storage."""
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any = None) -> Any:
    """Deserialize JSON text, returning default for empty or invalid values."""
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def get_db_path(config_manager: ConfigProvider) -> Path:
    """Resolve the configured SQLite database path."""
    raw_path = config_manager.get("database.path", "data/app_state.sqlite3")
    path = Path(str(raw_path))
    if not path.is_absolute():
        config_path = getattr(config_manager, "_config_path", None)
        base_dir = Path(config_path).parent if config_path else Path.cwd()
        path = base_dir / path
    return path


def connect(config_manager: ConfigProvider) -> sqlite3.Connection:
    """Open a SQLite connection with row access and FK enforcement enabled."""
    db_path = get_db_path(config_manager)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run operations in a commit/rollback transaction."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
