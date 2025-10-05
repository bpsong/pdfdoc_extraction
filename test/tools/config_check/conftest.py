"""Shared pytest fixtures for config_check test suite."""

from __future__ import annotations

import copy
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOLS_PATH = PROJECT_ROOT / "tools"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TOOLS_PATH) not in sys.path:
    sys.path.insert(0, str(TOOLS_PATH))


@dataclass(slots=True)
class SamplePaths:
    """Convenience container for commonly used filesystem locations."""

    base_dir: Path
    upload_dir: Path
    watch_dir: Path
    data_dir: Path
    archive_dir: Path


class ConfigFactory:
    """Helper for building and writing configuration files in tests."""

    def __init__(self, root: Path) -> None:
        self.paths = SamplePaths(
            base_dir=root,
            upload_dir=root / "uploads",
            watch_dir=root / "watch",
            data_dir=root / "data",
            archive_dir=root / "archive",
        )
        for directory in (
            self.paths.upload_dir,
            self.paths.watch_dir,
            self.paths.data_dir,
            self.paths.archive_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def build_valid(self) -> Dict[str, Any]:
        """Return a known-good configuration structure."""

        return {
            "web": {
                "upload_dir": str(self.paths.upload_dir),
                "secret_key": "testing-secret-key",
            },
            "watch_folder": {
                "dir": str(self.paths.watch_dir),
                "recursive": False,
            },
            "authentication": {
                "username": "admin",
                "password_hash": "$2b$12$eImiTXuWVxfM37uY4JANj.QlsWu1PErG3e1hYzWdG2ZHB5QoLGj7W",
            },
            "tasks": {
                "extract_metadata": {
                    "module": "standard_step.extraction.extract_metadata",
                    "class": "ExtractMetadata",
                    "params": {
                        "api_key": "llx-test-key",
                        "agent_id": "agent-001",
                        "fields": {
                            "supplier_name": {
                                "alias": "Supplier",
                                "type": "str",
                            }
                        }
                    },
                },
                "store_json": {
                    "module": "standard_step.storage.store_metadata_as_json",
                    "class": "StoreMetadataAsJsonTask",
                    "params": {
                        "data_dir": str(self.paths.data_dir),
                        "filename": "{supplier_name}_metadata.json",
                    },
                },
                "archive_pdf": {
                    "module": "standard_step.housekeeping.archive_pdf",
                    "class": "ArchivePdf",
                    "params": {
                        "archive_dir": str(self.paths.archive_dir),
                    },
                },
            },
            "pipeline": [
                "extract_metadata",
                "store_json",
                "archive_pdf",
            ],
        }

    def with_overrides(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Return a configuration dict with overrides applied."""

        base = copy.deepcopy(self.build_valid())
        return _deep_update(base, overrides)

    def write(self, *, name: str = "config.yaml", config: Optional[Dict[str, Any]] = None) -> Path:
        """Write configuration data to disk and return the file path."""

        content = config if config is not None else self.build_valid()
        target = self.paths.base_dir / name
        with target.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(content, handle, sort_keys=False)
        return target

    def write_text(self, text: str, *, name: str = "config.yaml") -> Path:
        """Write raw YAML text to disk and return the file path."""

        target = self.paths.base_dir / name
        target.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
        return target


def _deep_update(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in overrides.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            base[key] = _deep_update(base[key], value)
        else:
            base[key] = value
    return base


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the repository root path."""

    return PROJECT_ROOT


@pytest.fixture
def config_factory(tmp_path: Path) -> ConfigFactory:
    """Provide a ConfigFactory scoped to the temporary directory."""

    return ConfigFactory(tmp_path)
