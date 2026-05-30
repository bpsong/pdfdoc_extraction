"""Test helpers for SQLite-backed refactor tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any


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
