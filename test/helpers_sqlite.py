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


def seed_pipeline(config: TempConfig, definition: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist an exact definition for runner tests that stub task implementations.

    Publication-policy tests use PipelineTemplateService directly. This helper
    seeds repository records so execution tests retain real hash, attribution,
    schema dependency, and foreign-key checks, including deliberately bad tasks.
    """
    from copy import deepcopy
    import uuid
    from modules.db.connection import json_dumps
    from modules.db.repositories import PipelineTemplateRepository, PipelineVersionRepository, PipelineSchemaDependencyRepository
    from modules.services.versioned_config_contracts import content_hash

    definition = deepcopy(definition if definition is not None else {
        "schema_version": 1,
        "pipeline": config.get("pipeline", []),
        "tasks": config.get("tasks", {}),
    })
    for task_key, task in definition.get("tasks", {}).items():
        if task.get("module") == "tests":
            task["module"] = "custom_step.testing"
            custom = config._values.setdefault("custom_steps", {"enabled": True, "registry": {}})
            custom["registry"][task_key] = {"module": task["module"], "class": task["class"]}
    key = f"test-{uuid.uuid4()}"
    with connect(config) as conn:
        template = PipelineTemplateRepository(conn).create(
            template_key=key, name="Test pipeline", description="Synthetic fixture",
            document_type=None, operator_instructions="", status="active",
            operator_selectable=True, user="admin",
        )
        version = PipelineVersionRepository(conn).create(
            template_id=template["id"], version_number=1, schema_version=1,
            definition_json=json_dumps(definition), content_hash=content_hash(definition),
            display_snapshot_json=json_dumps({"pipeline": definition["pipeline"], "steps": []}),
            validation_summary_json="{}", user="admin",
        )
        for task_key, task in definition.get("tasks", {}).items():
            schema_id = task.get("params", {}).get("schema_version_id")
            if schema_id:
                PipelineSchemaDependencyRepository(conn).create(
                    pipeline_version_id=version["id"], task_key=task_key, schema_version_id=schema_id,
                )
        conn.commit()
    return version


def assign_pipeline(config: TempConfig, document_id: str, version: dict[str, Any]) -> None:
    """Pin an existing synthetic document and its batch to the same version."""
    with connect(config) as conn:
        row = conn.execute("SELECT batch_id FROM documents WHERE id = ?", (document_id,)).fetchone()
        assert row is not None
        conn.execute(
            "UPDATE batches SET pipeline_template_id = ?, pipeline_version_id = ? WHERE id = ?",
            (version["template_id"], version["id"], row["batch_id"]),
        )
        conn.execute(
            "UPDATE documents SET pipeline_template_id = ?, pipeline_version_id = ? WHERE batch_id = ?",
            (version["template_id"], version["id"], row["batch_id"]),
        )
        conn.commit()
