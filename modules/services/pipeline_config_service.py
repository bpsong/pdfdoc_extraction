"""Pipeline draft, diff, validation, and publish service for admin UI."""

from __future__ import annotations

from copy import deepcopy
import difflib
from pathlib import Path
import re
import sqlite3
from typing import Any

import yaml

from modules.config_manager import ConfigManager
from modules.db.connection import json_loads
from modules.db.repositories import ConfigVersionRepository
from modules.services.audit_service import AuditService
from modules.services.pipeline_validation_service import PipelineValidationService
from modules.services.task_catalog_service import TaskCatalogService


CONFIG_TYPE = "pipeline"
CONFIG_NAME = "default"


class PipelineConfigError(ValueError):
    """Raised when a pipeline draft cannot be saved or published."""

    def __init__(self, message: str, *, findings: list[dict[str, Any]] | None = None) -> None:
        """Initialize the error with optional validation findings."""
        super().__init__(message)
        self.findings = findings or []


class PipelineConfigService:
    """Coordinate admin pipeline drafts, validation, diffs, and publishing."""

    def __init__(self, config_manager: ConfigManager, conn: sqlite3.Connection) -> None:
        """Initialize the service.

        Args:
            config_manager: Active application configuration provider.
            conn: SQLite connection used for draft versions and audit events.
        """
        self.config_manager = config_manager
        self.conn = conn
        self.versions = ConfigVersionRepository(conn)
        self.audit = AuditService(conn)

    def get_pipeline(self) -> dict[str, Any]:
        """Return active pipeline configuration and the latest draft, if present."""
        active_config = self._active_config()
        active = self._pipeline_payload(active_config)
        draft_row = self.versions.get_draft(CONFIG_TYPE, CONFIG_NAME)
        draft = self._draft_payload(draft_row) if draft_row else None
        return {
            "active": active,
            "draft": draft,
            "has_draft": draft is not None,
        }

    def create_draft(self, *, user: str | None = None) -> dict[str, Any]:
        """Create a new draft from the active pipeline."""
        return self.save_draft(self._model_from_config(self._active_config()), user=user)

    def save_draft(self, model: dict[str, Any], *, user: str | None = None) -> dict[str, Any]:
        """Normalize and persist a pipeline draft model."""
        normalized = self._normalize_model(model)
        draft_config = self._config_from_model(normalized)
        yaml_preview = self._dump_yaml(draft_config)
        draft_row = self.versions.create_draft(
            config_type=CONFIG_TYPE,
            name=CONFIG_NAME,
            content_text=yaml_preview,
            created_by=user,
            metadata={
                "model": normalized,
                "summary": self._summary(normalized),
            },
        )
        self.audit.append_event(
            event_type="admin_pipeline_draft_saved",
            user=user,
            before=self._model_from_config(self._active_config()),
            after=normalized,
            metadata={"config_version_id": draft_row["id"], "summary": self._summary(normalized)},
        )
        return self._draft_payload(draft_row)

    def diff(self, model: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return an active-vs-draft unified diff."""
        active_yaml = self._dump_yaml(self._active_config())
        draft_config = self._draft_config(model)
        draft_yaml = self._dump_yaml(draft_config)
        lines = list(
            difflib.unified_diff(
                active_yaml.splitlines(),
                draft_yaml.splitlines(),
                fromfile="active config",
                tofile="draft config",
                lineterm="",
            )
        )
        return {
            "changed": active_yaml != draft_yaml,
            "lines": lines,
            "text": "\n".join(lines),
        }

    def validate_draft(
        self,
        model: dict[str, Any] | None = None,
        *,
        user: str | None = None,
        audit: bool = False,
    ) -> dict[str, Any]:
        """Validate the provided draft model, or the latest stored draft."""
        draft_config = self._draft_config(model)
        result = PipelineValidationService(self.config_manager).validate(draft_config)
        result["summary"] = {
            "errors": sum(1 for finding in result["findings"] if finding["severity"] == "error"),
            "warnings": sum(1 for finding in result["findings"] if finding["severity"] == "warning"),
        }
        result["yaml_preview"] = self._dump_yaml(draft_config)
        if audit:
            self.audit.append_event(
                event_type="admin_pipeline_validated",
                user=user,
                after={"valid": result["valid"], "summary": result["summary"]},
                metadata={"finding_codes": [finding["code"] for finding in result["findings"]]},
            )
        return result

    def publish(
        self,
        model: dict[str, Any] | None = None,
        *,
        user: str | None = None,
    ) -> dict[str, Any]:
        """Publish a validated draft by writing config YAML and recording a version."""
        normalized = self._normalize_model(model) if model is not None else self._stored_or_active_model()
        draft_config = self._config_from_model(normalized)
        validation = self.validate_draft(normalized)
        blocking = [finding for finding in validation["findings"] if finding["severity"] == "error"]
        if blocking:
            raise PipelineConfigError("Pipeline draft has blocking validation findings.", findings=blocking)

        before_model = self._model_from_config(self._active_config())
        yaml_preview = self._dump_yaml(draft_config)
        draft_row = self._matching_or_new_draft(
            yaml_preview=yaml_preview,
            model=normalized,
            user=user,
        )
        self._write_active_config(draft_config, yaml_preview)
        published = self.versions.publish(draft_row["id"])
        self._archive_stale_drafts(published["id"] if published else draft_row["id"])
        self._replace_in_memory_config(draft_config)
        self.audit.append_event(
            event_type="admin_pipeline_published",
            user=user,
            before=before_model,
            after=normalized,
            metadata={
                "config_version_id": draft_row["id"],
                "validation_summary": validation["summary"],
            },
        )
        return {
            "published": published,
            "active": self._pipeline_payload(draft_config),
            "validation": validation,
        }

    def yaml_preview(self, model: dict[str, Any]) -> str:
        """Return generated YAML for a draft model without saving it."""
        return self._dump_yaml(self._config_from_model(self._normalize_model(model)))

    def _pipeline_payload(self, config: dict[str, Any]) -> dict[str, Any]:
        """Build an API/UI-ready pipeline payload from config data."""
        model = self._model_from_config(config)
        return {
            "model": model,
            "yaml_preview": self._dump_yaml(config),
            "summary": self._summary(model),
        }

    def _draft_payload(self, draft_row: dict[str, Any]) -> dict[str, Any]:
        """Build an API/UI-ready draft payload from a config version row."""
        metadata = json_loads(draft_row.get("metadata_json"), {})
        model = metadata.get("model") if isinstance(metadata, dict) else None
        if not isinstance(model, dict):
            model = self._model_from_config(self._config_from_yaml(draft_row["content_text"]))
        normalized = self._normalize_model(model)
        return {
            "id": draft_row["id"],
            "created_by": draft_row.get("created_by"),
            "created_at": draft_row.get("created_at"),
            "content_hash": draft_row.get("content_hash"),
            "model": normalized,
            "yaml_preview": draft_row["content_text"],
            "summary": self._summary(normalized),
        }

    def _draft_config(self, model: dict[str, Any] | None) -> dict[str, Any]:
        """Return full config data for a provided, stored, or active draft."""
        if model is not None:
            return self._config_from_model(self._normalize_model(model))
        draft_row = self.versions.get_draft(CONFIG_TYPE, CONFIG_NAME)
        if draft_row:
            return self._config_from_yaml(draft_row["content_text"])
        return self._active_config()

    def _stored_or_active_model(self) -> dict[str, Any]:
        """Return the latest stored draft model, or active model when no draft exists."""
        draft_row = self.versions.get_draft(CONFIG_TYPE, CONFIG_NAME)
        if not draft_row:
            return self._model_from_config(self._active_config())
        return self._draft_payload(draft_row)["model"]

    def _matching_or_new_draft(
        self,
        *,
        yaml_preview: str,
        model: dict[str, Any],
        user: str | None,
    ) -> dict[str, Any]:
        """Return an existing matching draft row or persist a new draft row."""
        draft_row = self.versions.get_draft(CONFIG_TYPE, CONFIG_NAME)
        if draft_row and draft_row["content_text"] == yaml_preview:
            return draft_row
        return self.versions.create_draft(
            config_type=CONFIG_TYPE,
            name=CONFIG_NAME,
            content_text=yaml_preview,
            created_by=user,
            metadata={"model": model, "summary": self._summary(model)},
        )

    def _active_config(self) -> dict[str, Any]:
        """Return a copy of the active config mapping."""
        config = self.config_manager.get_all() if hasattr(self.config_manager, "get_all") else {}
        if not isinstance(config, dict):
            return {}
        return deepcopy(config)

    def _config_from_model(self, model: dict[str, Any]) -> dict[str, Any]:
        """Merge a normalized draft model into the active config shape."""
        config = self._active_config()
        tasks = deepcopy(config.get("tasks")) if isinstance(config.get("tasks"), dict) else {}
        pipeline: list[str] = []
        for step in model["steps"]:
            key = step["key"]
            tasks[key] = {
                "module": step["module"],
                "class": step["class"],
                "params": deepcopy(step.get("params", {})),
            }
            if step.get("on_error") is not None:
                tasks[key]["on_error"] = step["on_error"]
            if step.get("enabled", True):
                pipeline.append(key)
        config["tasks"] = tasks
        config["pipeline"] = pipeline
        return config

    def _model_from_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Convert config pipeline/tasks data into an ordered step model."""
        tasks = config.get("tasks") if isinstance(config.get("tasks"), dict) else {}
        pipeline = config.get("pipeline") if isinstance(config.get("pipeline"), list) else []
        steps: list[dict[str, Any]] = []
        for entry in pipeline:
            if not isinstance(entry, str):
                continue
            task_cfg = tasks.get(entry)
            if not isinstance(task_cfg, dict):
                steps.append(
                    {
                        "key": entry,
                        "label": _label_for_key(entry),
                        "module": "",
                        "class": "",
                        "enabled": True,
                        "params": {},
                        "on_error": None,
                    }
                )
                continue
            steps.append(self._step_from_task(entry, task_cfg, enabled=True))
        return {"steps": steps}

    def _normalize_model(self, model: dict[str, Any]) -> dict[str, Any]:
        """Normalize a draft step model for persistence and validation."""
        if not isinstance(model, dict):
            raise PipelineConfigError("Pipeline draft model must be an object.")
        raw_steps = model.get("steps")
        if not isinstance(raw_steps, list):
            raise PipelineConfigError("Pipeline draft model must include a steps list.")

        normalized_steps: list[dict[str, Any]] = []
        used_keys: set[str] = set()
        for index, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                raise PipelineConfigError(f"Pipeline step at index {index} must be an object.")
            module_name = str(raw_step.get("module") or "").strip()
            class_name = str(raw_step.get("class") or raw_step.get("class_name") or "").strip()
            if not module_name or not class_name:
                raise PipelineConfigError(f"Pipeline step at index {index} requires module and class.")
            key = str(raw_step.get("key") or "").strip() or _key_from_class(class_name)
            key = _unique_key(_slugify(key), used_keys)
            used_keys.add(key)
            params = raw_step.get("params", {})
            if params is None:
                params = {}
            if not isinstance(params, dict):
                raise PipelineConfigError(f"Pipeline step '{key}' params must be an object.")
            normalized_steps.append(
                {
                    "key": key,
                    "label": str(raw_step.get("label") or TaskCatalogService._label_for(class_name)),
                    "module": module_name,
                    "class": class_name,
                    "enabled": bool(raw_step.get("enabled", True)),
                    "params": deepcopy(params),
                    "on_error": raw_step.get("on_error"),
                }
            )
        return {"steps": normalized_steps}

    @staticmethod
    def _step_from_task(task_key: str, task_cfg: dict[str, Any], *, enabled: bool) -> dict[str, Any]:
        """Build a step model from one configured task definition."""
        class_name = str(task_cfg.get("class") or "")
        return {
            "key": task_key,
            "label": TaskCatalogService._label_for(class_name) if class_name else _label_for_key(task_key),
            "module": str(task_cfg.get("module") or ""),
            "class": class_name,
            "enabled": enabled,
            "params": deepcopy(task_cfg.get("params") if isinstance(task_cfg.get("params"), dict) else {}),
            "on_error": task_cfg.get("on_error"),
        }

    @staticmethod
    def _summary(model: dict[str, Any]) -> dict[str, int]:
        """Return counts for the draft model."""
        steps = model.get("steps") if isinstance(model.get("steps"), list) else []
        return {
            "total_steps": len(steps),
            "enabled_steps": sum(1 for step in steps if isinstance(step, dict) and step.get("enabled", True)),
            "disabled_steps": sum(1 for step in steps if isinstance(step, dict) and not step.get("enabled", True)),
        }

    @staticmethod
    def _dump_yaml(config: dict[str, Any]) -> str:
        """Serialize config data as deterministic YAML."""
        return yaml.safe_dump(config, sort_keys=False, allow_unicode=False)

    @staticmethod
    def _config_from_yaml(yaml_text: str) -> dict[str, Any]:
        """Parse YAML text into a config mapping."""
        data = yaml.safe_load(yaml_text) or {}
        if not isinstance(data, dict):
            raise PipelineConfigError("Stored pipeline draft YAML root must be an object.")
        return data

    def _write_active_config(self, config: dict[str, Any], yaml_text: str) -> None:
        """Atomically write generated YAML to the active config path."""
        config_path = Path(getattr(self.config_manager, "_config_path", "config.yaml"))
        config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = config_path.with_name(f"{config_path.name}.tmp")
        temp_path.write_text(yaml_text, encoding="utf-8")
        temp_path.replace(config_path)

    def _replace_in_memory_config(self, config: dict[str, Any]) -> None:
        """Keep the current config provider aligned after publish."""
        if hasattr(self.config_manager, "config"):
            self.config_manager.config = deepcopy(config)
        if hasattr(self.config_manager, "_values"):
            self.config_manager._values = deepcopy(config)

    def _archive_stale_drafts(self, published_id: str) -> None:
        """Archive older draft rows after a publish."""
        self.conn.execute(
            """
            UPDATE config_versions
            SET status = 'archived'
            WHERE config_type = ? AND name = ? AND status = 'draft' AND id != ?
            """,
            (CONFIG_TYPE, CONFIG_NAME, published_id),
        )
        self.conn.commit()


def _slugify(value: str) -> str:
    """Return a config-key-safe slug."""
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_").lower()
    return slug or "task"


def _key_from_class(class_name: str) -> str:
    """Generate a task key from a class name."""
    name = class_name
    for suffix in ("Task", "V2"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return _slugify(re.sub(r"(?<!^)(?=[A-Z])", "_", name))


def _unique_key(base_key: str, used_keys: set[str]) -> str:
    """Return a unique task key for a draft model."""
    key = base_key
    suffix = 2
    while key in used_keys:
        key = f"{base_key}_{suffix}"
        suffix += 1
    return key


def _label_for_key(task_key: str) -> str:
    """Build a readable label from a task key."""
    return task_key.replace("_", " ").strip().title() or task_key
