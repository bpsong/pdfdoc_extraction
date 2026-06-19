"""Structural typing contracts for configuration providers."""

from __future__ import annotations

from typing import Any, Protocol


class ConfigProvider(Protocol):
    """Provide dot-delimited application configuration values.

    Runtime ``ConfigManager`` instances and lightweight test configuration
    objects both satisfy this contract.
    """

    def get(self, key: str, default: Any = None) -> Any:
        """Return the configured value for ``key`` or ``default``."""


def get_all_config(provider: ConfigProvider) -> dict[str, Any]:
    """Return a provider's complete mapping when that capability exists."""
    getter = getattr(provider, "get_all", None)
    if not callable(getter):
        return {}
    config = getter()
    return config if isinstance(config, dict) else {}
