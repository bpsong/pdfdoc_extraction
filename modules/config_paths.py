"""Shared resolution rules for deployment configuration paths."""

import os
from pathlib import Path


def config_directory(config_path: str | Path | None) -> Path:
    """Return the absolute configuration directory, or the current directory."""
    if config_path is None:
        return Path.cwd()
    return Path(config_path).expanduser().resolve().parent


def resolve_config_path(
    raw_path: str | Path,
    *,
    config_path: str | Path | None = None,
    base_dir: str | Path | None = None,
) -> Path:
    """Resolve a deployment path with an optional explicit validation base."""
    path = Path(os.path.expandvars(str(raw_path))).expanduser()
    base = (
        Path(base_dir).resolve()
        if base_dir is not None else config_directory(config_path)
    )
    return (path if path.is_absolute() else base / path).resolve()
