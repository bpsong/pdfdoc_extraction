from pathlib import Path
from typing import Any

from modules.config_protocol import VersionedTaskConfig, get_all_config


class Config:
    def __init__(self, values: dict[str, Any], config_path: Path) -> None:
        self.values = values
        self._config_path = config_path

    def get(self, key: str, default: Any = None) -> Any:
        current: Any = self.values
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current


def test_versioned_task_config_exposes_only_database_settings(tmp_path):
    source = Config(
        {
            "database": {"path": "state.sqlite3"},
            "pipeline": ["legacy_extract"],
            "tasks": {"legacy_extract": {"params": {"field": "legacy"}}},
            "extraction": {"fields": {"legacy": {"alias": "Legacy"}}},
            "assign_nanoid": {"length": 5},
            "pipeline_secrets": {"provider": "do-not-expose"},
        },
        tmp_path / "config.yaml",
    )

    config = VersionedTaskConfig(source)

    assert config.get("database.path") == "state.sqlite3"
    assert config.get("pipeline") is None
    assert config.get("tasks.legacy_extract") is None
    assert config.get("extraction.fields") is None
    assert config.get("assign_nanoid.length", 10) == 10
    assert config.get("pipeline_secrets") is None
    assert get_all_config(config) == {"database": {"path": "state.sqlite3"}}
    assert config._config_path == tmp_path / "config.yaml"


def test_versioned_task_config_returns_database_copies(tmp_path):
    source = Config(
        {"database": {"path": "state.sqlite3"}},
        tmp_path / "config.yaml",
    )
    config = VersionedTaskConfig(source)

    database = config.get("database")
    database["path"] = "changed.sqlite3"

    assert config.get("database.path") == "state.sqlite3"
