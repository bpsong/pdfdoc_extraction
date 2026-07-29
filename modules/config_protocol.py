"""Structural typing contracts for configuration providers."""

from __future__ import annotations

from copy import deepcopy
from os import PathLike
from typing import Any, Protocol


class ConfigProvider(Protocol):
    """Provide dot-delimited application configuration values.

    Runtime ``ConfigManager`` instances and lightweight test configuration
    objects both satisfy this contract.
    """

    def get(self, key: str, default: Any = None) -> Any:
        """Return the configured value for ``key`` or ``default``."""


class VersionedTaskConfig:
    """Expose deployment infrastructure, but not YAML workflow settings.

    Published task parameters are loaded from an immutable SQLite pipeline
    version. The injected configuration provider remains necessary for shared
    infrastructure such as the SQLite database path, but workflow definitions
    and task-owned settings must not fall back to deployment YAML.
    """

    def __init__(self, provider: ConfigProvider) -> None:
        self._provider = provider
        config_path = getattr(provider, "_config_path", None)
        self._config_path = (
            config_path
            if isinstance(config_path, (str, PathLike))
            else None
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Return database configuration and hide workflow-owned settings."""
        if key == "database" or key.startswith("database."):
            return deepcopy(self._provider.get(key, default))
        return default

    def get_all(self) -> dict[str, Any]:
        """Return the deployment subset available to versioned tasks."""
        database = self._provider.get("database", {})
        return {"database": deepcopy(database)} if isinstance(database, dict) else {}


def get_all_config(provider: ConfigProvider) -> dict[str, Any]:
    """Return a provider's complete mapping when that capability exists."""
    getter = getattr(provider, "get_all", None)
    if not callable(getter):
        return {}
    config = getter()
    return config if isinstance(config, dict) else {}
