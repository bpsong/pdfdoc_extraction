"""Test helpers for SQLite-backed refactor tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import bcrypt

from modules.db.connection import connect
from modules.db.repositories import UserRepository


class TempConfig:
    """Small ConfigManager stand-in supporting dot-path lookups."""

    def __init__(self, db_path: Path, values: dict[str, Any] | None = None) -> None:
        self._config_path = db_path.parent / "config.yaml"
        self._values = values or {}
        self._values.setdefault("database", {})
        self._values["database"].setdefault("path", str(db_path))

    def get(self, key: str, default: Any = None) -> Any:
        value: Any = self._values
        for part in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part, default)
        return value

    def get_all(self) -> dict[str, Any]:
        return self._values


def initialize_test_users(config: TempConfig) -> None:
    """Seed the fixed users for authenticated integration tests."""
    admin_hash = bcrypt.hashpw(b"AdminPassword1!", bcrypt.gensalt()).decode()
    operator_hash = bcrypt.hashpw(b"OperatorPass1!", bcrypt.gensalt()).decode()
    with connect(config) as conn:
        UserRepository(conn).initialize({"admin": admin_hash, "operator": operator_hash})
