"""Admin-facing settings, summary, audit, and dry-run services."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sqlite3
from typing import Any

import yaml

from modules.config_manager import ConfigManager
from modules.db.connection import json_loads
from modules.db.repositories import (
    AppSettingsRepository,
    AuditRepository,
    ConfigVersionRepository,
    DocumentRepository,
)
from modules.services.config_validation_service import ConfigValidationService
from modules.services.audit_service import AuditService
from modules.services.pipeline_config_service import PipelineConfigError, PipelineConfigService


ADMIN_SETTINGS_KEY = "admin.non_secret_settings"
REVIEW_GATE_SETTINGS_KEY = "admin.review_gate_rules"
SPLIT_SETTINGS_KEY = "admin.split_settings"
ADMIN_SETTINGS_CONFIG_TYPE = "admin_settings"
REVIEW_GATE_CONFIG_TYPE = "review_gate_rules"
SPLIT_SETTINGS_CONFIG_TYPE = "split_settings"
CONFIG_NAME = "default"

REVIEW_SCOPES = {"document", "low_confidence_fields", "schema_errors", "split_result"}
RESUME_POLICIES = {"next_task"}
UNCATEGORIZED_POLICIES = {"include", "forbid", "omit"}
SECRET_KEYS = {
    "api_key",
    "apikey",
    "password",
    "password_hash",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
}
EDITABLE_SETTINGS: dict[str, dict[str, Any]] = {
    "ui.app_name": {"group": "ui", "label": "Application Name", "type": "string", "default": "DocFlow AI"},
    "ui.page_size": {"group": "ui", "label": "Default Page Size", "type": "positive_int", "default": 25},
    "validation.config_validation_enabled": {
        "group": "validation",
        "label": "Configuration Validation",
        "type": "bool",
        "default": True,
    },
    "validation.strict_mode_default": {
        "group": "validation",
        "label": "Strict Mode Default",
        "type": "bool",
        "default": False,
    },
    "validation.allow_ui_config_save": {
        "group": "validation",
        "label": "Allow UI Config Save",
        "type": "bool",
        "default": False,
    },
    "review.default_queue_name": {
        "group": "review",
        "label": "Default Review Queue",
        "type": "string",
        "default": "default_review",
    },
    "review.lock_timeout_minutes": {
        "group": "review",
        "label": "Review Lock Timeout",
        "type": "positive_int",
        "default": 60,
    },
    "app_storage.root_dir": {"group": "storage", "label": "Storage Root", "type": "path", "default": "data/app"},
    "app_storage.originals_dir": {
        "group": "storage",
        "label": "Originals Directory",
        "type": "path",
        "default": "data/app/originals",
    },
    "app_storage.working_dir": {
        "group": "storage",
        "label": "Working Directory",
        "type": "path",
        "default": "data/app/working",
    },
    "app_storage.split_dir": {"group": "storage", "label": "Split Directory", "type": "path", "default": "data/app/split"},
    "app_storage.exports_dir": {
        "group": "storage",
        "label": "Exports Directory",
        "type": "path",
        "default": "data/app/exports",
    },
    "app_storage.archive_dir": {
        "group": "storage",
        "label": "Archive Directory",
        "type": "path",
        "default": "data/app/archive",
    },
}


class AdminSettingsError(ValueError):
    """Raised when an admin settings payload is invalid."""


class AdminSettingsService:
    """Read and persist non-secret admin configuration settings."""

    def __init__(self, config_manager: ConfigManager, conn: sqlite3.Connection) -> None:
        """Initialize the service.

        Args:
            config_manager: Active application configuration.
            conn: SQLite connection for settings, versions, and audit events.
        """
        self.config_manager = config_manager
        self.conn = conn
        self.settings = AppSettingsRepository(conn)
        self.versions = ConfigVersionRepository(conn)
        self.audit = AuditService(conn)

    def get_review_gate_rules(self) -> dict[str, Any]:
        """Return normalized review-gate settings for the admin UI."""
        config = self._active_config()
        task_key, task_params, all_task_keys = self._task_params(config, "ReviewGateTask")
        stored = self.settings.get(REVIEW_GATE_SETTINGS_KEY, {})
        current = self._normalize_review_gate_rules(
            {
                **self._review_gate_defaults(config),
                **task_params,
                **(stored if isinstance(stored, dict) else {}),
            }
        )
        return {
            "settings": current,
            "task_key": task_key,
            "task_keys": all_task_keys,
            "source": "task_params" if task_key else "app_settings",
            "pass_through_behavior": {
                "status": "passed",
                "review_required": False,
                "description": "When all fields meet or exceed the confidence threshold, no review item is created.",
            },
        }

    def update_review_gate_rules(self, payload: dict[str, Any], *, user: str | None = None) -> dict[str, Any]:
        """Persist normalized review-gate settings and audit the change."""
        before = self.get_review_gate_rules()["settings"]
        incoming = self._payload_settings(payload)
        after = self._normalize_review_gate_rules({**before, **incoming})

        config = self._active_config()
        self._apply_review_gate_to_config(config, after)
        self.settings.set(REVIEW_GATE_SETTINGS_KEY, after)
        published = self._record_config_version(
            config_type=REVIEW_GATE_CONFIG_TYPE,
            settings=after,
            user=user,
        )
        self._write_active_config(config)
        self._replace_in_memory_config(config)
        self.audit.append_event(
            event_type="admin_review_gate_rules_updated",
            user=user,
            before=before,
            after=after,
            metadata={"config_version_id": published.get("id") if published else None},
        )
        return self.get_review_gate_rules()

    def get_split_settings(self) -> dict[str, Any]:
        """Return normalized non-secret split settings for the admin UI."""
        config = self._active_config()
        task_key, task_params, all_task_keys = self._task_params(config, "LlamaCloudSplitTask")
        stored = self.settings.get(SPLIT_SETTINGS_KEY, {})
        current = self._normalize_split_settings(
            {
                **self._split_defaults(config),
                **task_params,
                **(stored if isinstance(stored, dict) else {}),
            }
        )
        api_key = str(task_params.get("api_key") or stored.get("api_key") or "") if isinstance(stored, dict) else str(task_params.get("api_key") or "")
        return {
            "settings": self._redact_split_settings(current, api_key_configured=bool(api_key)),
            "task_key": task_key,
            "task_keys": all_task_keys,
            "source": "task_params" if task_key else "app_settings",
            "adapter_status": self._split_adapter_status(current, api_key_configured=bool(api_key)),
        }

    def update_split_settings(self, payload: dict[str, Any], *, user: str | None = None) -> dict[str, Any]:
        """Persist non-secret split settings and audit the change."""
        before = self.get_split_settings()["settings"]
        incoming = self._payload_settings(payload)
        if self._contains_secret_key(incoming):
            raise AdminSettingsError("Secret split settings such as api_key cannot be saved through this endpoint.")
        after = self._normalize_split_settings({**before, **incoming})

        config = self._active_config()
        self._apply_split_to_config(config, after)
        self.settings.set(SPLIT_SETTINGS_KEY, after)
        published = self._record_config_version(
            config_type=SPLIT_SETTINGS_CONFIG_TYPE,
            settings=after,
            user=user,
        )
        self._write_active_config(config)
        self._replace_in_memory_config(config)
        self.audit.append_event(
            event_type="admin_split_settings_updated",
            user=user,
            before=before,
            after=after,
            metadata={"config_version_id": published.get("id") if published else None},
        )
        return self.get_split_settings()

    def test_split_connection(self, *, user: str | None = None) -> dict[str, Any]:
        """Return a non-invasive Split adapter readiness check."""
        payload = self.get_split_settings()
        settings = payload["settings"]
        status = payload["adapter_status"]
        self.audit.append_event(
            event_type="admin_split_connection_tested",
            user=user,
            after=status,
            metadata={"enabled": settings["enabled"], "network_checked": False},
        )
        return status

    def get_admin_settings(self) -> dict[str, Any]:
        """Return editable non-secret runtime settings."""
        config = self._active_config()
        stored = self.settings.get(ADMIN_SETTINGS_KEY, {})
        values = {
            key: _get_nested(config, key, _default_for_setting(schema))
            for key, schema in EDITABLE_SETTINGS.items()
        }
        if isinstance(stored, dict):
            values.update(
                {
                    key: stored[key]
                    for key in EDITABLE_SETTINGS
                    if key in stored
                }
            )
        normalized = {
            key: self._normalize_admin_setting(key, value)
            for key, value in values.items()
        }
        return {
            "settings": normalized,
            "groups": _settings_groups(normalized),
            "editable_keys": [
                {"key": key, **schema}
                for key, schema in EDITABLE_SETTINGS.items()
            ],
        }

    def update_admin_settings(self, payload: dict[str, Any], *, user: str | None = None) -> dict[str, Any]:
        """Persist allow-listed non-secret runtime settings and audit the change."""
        incoming = self._payload_settings(payload)
        if self._contains_secret_key(incoming):
            raise AdminSettingsError("Secret settings cannot be saved through this endpoint.")
        unknown = sorted(set(incoming) - set(EDITABLE_SETTINGS))
        if unknown:
            raise AdminSettingsError(f"Unsupported admin setting key: {unknown[0]}.")

        before = self.get_admin_settings()["settings"]
        after = deepcopy(before)
        for key, value in incoming.items():
            after[key] = self._normalize_admin_setting(key, value)

        config = self._active_config()
        for key, value in after.items():
            _set_nested(config, key, value)
        self.settings.set(ADMIN_SETTINGS_KEY, after)
        published = self._record_config_version(
            config_type=ADMIN_SETTINGS_CONFIG_TYPE,
            settings=after,
            user=user,
        )
        self._write_active_config(config)
        self._replace_in_memory_config(config)
        self.audit.append_event(
            event_type="admin_settings_updated",
            user=user,
            before=before,
            after=after,
            metadata={"config_version_id": published.get("id") if published else None},
        )
        return self.get_admin_settings()

    def _active_config(self) -> dict[str, Any]:
        """Return a deep copy of the active config mapping."""
        config = self.config_manager.get_all() if hasattr(self.config_manager, "get_all") else {}
        return deepcopy(config) if isinstance(config, dict) else {}

    @staticmethod
    def _payload_settings(payload: dict[str, Any]) -> dict[str, Any]:
        """Return the settings object from supported API payload shapes."""
        settings = payload.get("settings", payload)
        if not isinstance(settings, dict):
            raise AdminSettingsError("Settings payload must be an object.")
        return settings

    @staticmethod
    def _normalize_admin_setting(key: str, value: Any) -> Any:
        """Normalize one allow-listed admin setting."""
        schema = EDITABLE_SETTINGS[key]
        setting_type = schema["type"]
        if setting_type == "bool":
            return bool(value)
        if setting_type == "positive_int":
            return _positive_int(value, key)
        text = str(value or "").strip()
        if setting_type in {"string", "path"} and not text:
            raise AdminSettingsError(f"{key} cannot be empty.")
        return text

    @staticmethod
    def _task_params(config: dict[str, Any], class_name: str) -> tuple[str | None, dict[str, Any], list[str]]:
        """Return the first task params and all task keys matching a class."""
        tasks = config.get("tasks") if isinstance(config.get("tasks"), dict) else {}
        matches: list[tuple[str, dict[str, Any]]] = []
        for task_key, task_config in tasks.items():
            if not isinstance(task_config, dict) or str(task_config.get("class") or "") != class_name:
                continue
            params = task_config.get("params") if isinstance(task_config.get("params"), dict) else {}
            matches.append((str(task_key), deepcopy(params)))
        if not matches:
            return None, {}, []
        return matches[0][0], matches[0][1], [match[0] for match in matches]

    def _review_gate_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return review-gate defaults derived from runtime config."""
        review = config.get("review") if isinstance(config.get("review"), dict) else {}
        return {
            "confidence_threshold": 0.8,
            "per_document_type_thresholds": {},
            "field_threshold_overrides": {},
            "review_scope": "low_confidence_fields",
            "queue_name": str(review.get("default_queue_name") or "default_review"),
            "always_review": False,
            "split_confidence_levels_requiring_review": [],
            "business_rule_flag_names": [],
            "require_review_when_missing_confidence": True,
            "require_review_for_missing_required_fields": True,
            "allow_operator_to_edit_high_confidence_fields": True,
            "schema_file": "",
            "resume_policy": "next_task",
            "lock_timeout_minutes": int(review.get("lock_timeout_minutes") or 60),
        }

    @staticmethod
    def _normalize_review_gate_rules(raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize and validate review-gate settings."""
        threshold = _float_between(raw.get("confidence_threshold", 0.8), "confidence_threshold")
        per_document = _threshold_map(raw.get("per_document_type_thresholds", {}), "per_document_type_thresholds")
        per_field = _threshold_map(raw.get("field_threshold_overrides", {}), "field_threshold_overrides")
        review_scope = str(raw.get("review_scope") or "low_confidence_fields")
        if review_scope not in REVIEW_SCOPES:
            raise AdminSettingsError(f"review_scope must be one of: {', '.join(sorted(REVIEW_SCOPES))}.")
        resume_policy = str(raw.get("resume_policy") or "next_task")
        if resume_policy not in RESUME_POLICIES:
            raise AdminSettingsError(f"resume_policy must be one of: {', '.join(sorted(RESUME_POLICIES))}.")
        lock_timeout = _positive_int(raw.get("lock_timeout_minutes", 60), "lock_timeout_minutes")
        return {
            "confidence_threshold": threshold,
            "per_document_type_thresholds": per_document,
            "field_threshold_overrides": per_field,
            "review_scope": review_scope,
            "queue_name": str(raw.get("queue_name") or "default_review"),
            "always_review": bool(raw.get("always_review", False)),
            "split_confidence_levels_requiring_review": _string_list(
                raw.get("split_confidence_levels_requiring_review", [])
            ),
            "business_rule_flag_names": _string_list(raw.get("business_rule_flag_names", [])),
            "require_review_when_missing_confidence": bool(raw.get("require_review_when_missing_confidence", True)),
            "require_review_for_missing_required_fields": bool(
                raw.get("require_review_for_missing_required_fields", True)
            ),
            "allow_operator_to_edit_high_confidence_fields": bool(
                raw.get("allow_operator_to_edit_high_confidence_fields", True)
            ),
            "schema_file": str(raw.get("schema_file") or ""),
            "resume_policy": resume_policy,
            "lock_timeout_minutes": lock_timeout,
        }

    def _apply_review_gate_to_config(self, config: dict[str, Any], settings: dict[str, Any]) -> None:
        """Apply review settings to configured ReviewGateTask params."""
        review = config.setdefault("review", {})
        if isinstance(review, dict):
            review["lock_timeout_minutes"] = settings["lock_timeout_minutes"]
            review.setdefault("default_queue_name", settings["queue_name"])

        params = {
            "confidence_threshold": settings["confidence_threshold"],
            "per_document_type_thresholds": settings["per_document_type_thresholds"],
            "field_threshold_overrides": settings["field_threshold_overrides"],
            "split_confidence_levels_requiring_review": settings["split_confidence_levels_requiring_review"],
            "require_review_when_missing_confidence": settings["require_review_when_missing_confidence"],
            "require_review_for_missing_required_fields": settings["require_review_for_missing_required_fields"],
            "always_review": settings["always_review"],
            "schema_file": settings["schema_file"] or None,
            "queue_name": settings["queue_name"],
            "review_scope": settings["review_scope"],
            "allow_operator_to_edit_high_confidence_fields": settings[
                "allow_operator_to_edit_high_confidence_fields"
            ],
            "resume_policy": settings["resume_policy"],
        }
        self._update_task_params(config, "ReviewGateTask", params)

    def _split_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return split defaults derived from runtime config."""
        app_storage = config.get("app_storage") if isinstance(config.get("app_storage"), dict) else {}
        return {
            "enabled": False,
            "categories": [],
            "allow_uncategorized": "include",
            "split_dir": str(app_storage.get("split_dir") or "data/app/split"),
            "configuration_id": "",
            "project_id": "",
            "organization_id": "",
            "poll_interval_seconds": 1.0,
            "timeout_seconds": 7200.0,
        }

    @staticmethod
    def _normalize_split_settings(raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize and validate non-secret split settings."""
        allow_uncategorized = str(raw.get("allow_uncategorized") or "include")
        if allow_uncategorized not in UNCATEGORIZED_POLICIES:
            raise AdminSettingsError(
                f"allow_uncategorized must be one of: {', '.join(sorted(UNCATEGORIZED_POLICIES))}."
            )
        categories = _normalize_categories(raw.get("categories", []))
        return {
            "enabled": bool(raw.get("enabled", False)),
            "categories": categories,
            "allow_uncategorized": allow_uncategorized,
            "split_dir": str(raw.get("split_dir") or "data/app/split"),
            "configuration_id": str(raw.get("configuration_id") or ""),
            "project_id": str(raw.get("project_id") or ""),
            "organization_id": str(raw.get("organization_id") or ""),
            "poll_interval_seconds": _positive_float(raw.get("poll_interval_seconds", 1.0), "poll_interval_seconds"),
            "timeout_seconds": _positive_float(raw.get("timeout_seconds", 7200.0), "timeout_seconds"),
        }

    @staticmethod
    def _redact_split_settings(settings: dict[str, Any], *, api_key_configured: bool) -> dict[str, Any]:
        """Return split settings with secret state only, not secret values."""
        redacted = deepcopy(settings)
        redacted["api_key_configured"] = api_key_configured
        return redacted

    def _apply_split_to_config(self, config: dict[str, Any], settings: dict[str, Any]) -> None:
        """Apply split settings to configured LlamaCloudSplitTask params."""
        params = {
            "enabled": settings["enabled"],
            "categories": settings["categories"],
            "allow_uncategorized": settings["allow_uncategorized"],
            "split_dir": settings["split_dir"],
            "configuration_id": settings["configuration_id"] or None,
            "project_id": settings["project_id"] or None,
            "organization_id": settings["organization_id"] or None,
            "poll_interval_seconds": settings["poll_interval_seconds"],
            "timeout_seconds": settings["timeout_seconds"],
        }
        self._update_task_params(config, "LlamaCloudSplitTask", params)

    @staticmethod
    def _update_task_params(config: dict[str, Any], class_name: str, params: dict[str, Any]) -> None:
        """Merge params into every configured task matching class_name."""
        tasks = config.get("tasks") if isinstance(config.get("tasks"), dict) else {}
        for task_config in tasks.values():
            if not isinstance(task_config, dict) or str(task_config.get("class") or "") != class_name:
                continue
            task_params = task_config.setdefault("params", {})
            if isinstance(task_params, dict):
                for key, value in params.items():
                    if value is None:
                        task_params.pop(key, None)
                    else:
                        task_params[key] = value

    def _record_config_version(
        self,
        *,
        config_type: str,
        settings: dict[str, Any],
        user: str | None,
    ) -> dict[str, Any] | None:
        """Persist a published config version row for audit and rollback."""
        draft = self.versions.create_draft(
            config_type=config_type,
            name=CONFIG_NAME,
            content_text=yaml.safe_dump(settings, sort_keys=False, allow_unicode=False),
            created_by=user,
            metadata={"settings": settings},
        )
        return self.versions.publish(draft["id"])

    def _write_active_config(self, config: dict[str, Any]) -> None:
        """Write active config YAML when a config path is available."""
        config_path = getattr(self.config_manager, "_config_path", None)
        if not config_path:
            return
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        yaml_text = yaml.safe_dump(config, sort_keys=False, allow_unicode=False)
        temp_path = path.with_name(f"{path.name}.tmp")
        temp_path.write_text(yaml_text, encoding="utf-8")
        temp_path.replace(path)

    def _replace_in_memory_config(self, config: dict[str, Any]) -> None:
        """Keep test and runtime config objects aligned after saving."""
        if hasattr(self.config_manager, "config"):
            self.config_manager.config = deepcopy(config)
        if hasattr(self.config_manager, "_values"):
            self.config_manager._values = deepcopy(config)
        if hasattr(self.config_manager, "values"):
            self.config_manager.values = deepcopy(config)

    def _split_adapter_status(self, settings: dict[str, Any], *, api_key_configured: bool) -> dict[str, Any]:
        """Build a non-invasive Split adapter status payload."""
        if not settings.get("enabled"):
            return {
                "ok": False,
                "status": "disabled",
                "message": "LlamaCloud Split is disabled.",
                "api_key_configured": api_key_configured,
                "network_checked": False,
            }
        if not api_key_configured:
            return {
                "ok": False,
                "status": "missing_api_key",
                "message": "Set LLAMA_CLOUD_API_KEY or configure an api_key in the active pipeline task.",
                "api_key_configured": False,
                "network_checked": False,
            }
        if not settings.get("configuration_id") and not settings.get("categories"):
            return {
                "ok": False,
                "status": "missing_configuration",
                "message": "Configure split categories or a LlamaCloud Split configuration ID.",
                "api_key_configured": True,
                "network_checked": False,
            }
        try:
            import llama_cloud  # noqa: F401
        except ImportError:
            return {
                "ok": False,
                "status": "package_missing",
                "message": "The llama-cloud package is not installed.",
                "api_key_configured": True,
                "network_checked": False,
            }
        return {
            "ok": True,
            "status": "ready",
            "message": "Split adapter dependency is available and non-secret settings are valid.",
            "api_key_configured": True,
            "network_checked": False,
        }

    @staticmethod
    def _contains_secret_key(value: Any) -> bool:
        """Return True when the payload attempts to save a secret key."""
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = str(key).lower()
                if lowered in SECRET_KEYS:
                    return True
                if AdminSettingsService._contains_secret_key(item):
                    return True
        if isinstance(value, list):
            return any(AdminSettingsService._contains_secret_key(item) for item in value)
        return False


class AdminAuditService:
    """Read admin-scoped audit events from the immutable audit stream."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.audit = AuditRepository(conn)

    def list_events(
        self,
        *,
        event_type: str | None = None,
        user: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return filtered admin audit events with parsed JSON payloads."""
        safe_limit = min(max(int(limit), 1), 500)
        safe_offset = max(int(offset), 0)
        events = self.audit.list_admin_events(
            event_type=event_type or None,
            user=user or None,
            created_from=created_from or None,
            created_to=created_to or None,
            limit=safe_limit,
            offset=safe_offset,
        )
        total = self.audit.count_admin_events(
            event_type=event_type or None,
            user=user or None,
            created_from=created_from or None,
            created_to=created_to or None,
        )
        return {
            "events": [_audit_event_payload(event) for event in events],
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "filters": {
                "event_type": event_type,
                "user": user,
                "created_from": created_from,
                "created_to": created_to,
            },
        }


class AdminSummaryService:
    """Build the admin dashboard summary from existing admin services."""

    def __init__(self, config_manager: ConfigManager, conn: sqlite3.Connection) -> None:
        self.config_manager = config_manager
        self.conn = conn
        self.settings = AdminSettingsService(config_manager, conn)
        self.audit = AdminAuditService(conn)

    def summary(self) -> dict[str, Any]:
        """Return configuration, pipeline, settings, split, and audit health."""
        config_health = self._safe_active_config_validation()
        schema_validation = self._safe_schema_validation()
        pipeline = PipelineConfigService(self.config_manager, self.conn).get_pipeline()
        review_gate = self.settings.get_review_gate_rules()
        split = self.settings.get_split_settings()
        recent_audit = self.audit.list_events(limit=5)
        versions = ConfigVersionRepository(self.conn).list_versions()

        return {
            "config_health": {
                "valid": bool(config_health.get("valid", False)),
                "summary": config_health.get("summary", {}),
                "source": config_health.get("source"),
            },
            "schema_validation": {
                "valid": bool(schema_validation.get("valid", False)),
                "summary": _summary_for_findings(schema_validation.get("findings", [])),
            },
            "pipeline": {
                "active": pipeline["active"]["summary"],
                "draft": pipeline["draft"]["summary"] if pipeline.get("draft") else None,
                "has_draft": bool(pipeline.get("has_draft")),
            },
            "review_gate": {
                "task_key": review_gate.get("task_key"),
                "confidence_threshold": review_gate["settings"]["confidence_threshold"],
                "review_scope": review_gate["settings"]["review_scope"],
                "always_review": review_gate["settings"]["always_review"],
            },
            "split": {
                "enabled": bool(split["settings"].get("enabled")),
                "categories": len(split["settings"].get("categories") or []),
                "adapter_status": split.get("adapter_status", {}),
            },
            "audit": {
                "total_admin_events": recent_audit["total"],
                "recent_events": recent_audit["events"],
            },
            "config_versions": {
                "total": len(versions),
                "drafts": sum(1 for version in versions if version.get("status") == "draft"),
                "published": sum(1 for version in versions if version.get("status") == "published"),
            },
        }

    def _safe_active_config_validation(self) -> dict[str, Any]:
        try:
            return ConfigValidationService(self.config_manager).validate_active_config()
        except (OSError, ValueError, TypeError) as exc:
            return {
                "valid": False,
                "source": "active config",
                "summary": {"errors": 1, "warnings": 0},
                "findings": [
                    {
                        "severity": "error",
                        "path": "config",
                        "message": str(exc),
                        "code": "admin-summary-config-validation-failed",
                    }
                ],
            }

    def _safe_schema_validation(self) -> dict[str, Any]:
        try:
            return ConfigValidationService(self.config_manager).validate_all_schemas()
        except (OSError, ValueError, TypeError) as exc:
            return {
                "valid": False,
                "findings": [
                    {
                        "severity": "error",
                        "path": "schemas",
                        "message": str(exc),
                        "code": "admin-summary-schema-validation-failed",
                    }
                ],
            }


class PipelineDryRunService:
    """Preview draft pipeline decisions without writing final exports."""

    def __init__(self, config_manager: ConfigManager, conn: sqlite3.Connection) -> None:
        self.config_manager = config_manager
        self.conn = conn
        self.audit = AuditService(conn)

    def run(self, payload: dict[str, Any], *, user: str | None = None) -> dict[str, Any]:
        """Run a non-mutating pipeline decision preview and audit the result."""
        model = payload.get("model")
        if model is not None and not isinstance(model, dict):
            raise PipelineConfigError("Dry-run model must be an object.")

        pipeline_service = PipelineConfigService(self.config_manager, self.conn)
        overview = pipeline_service.get_pipeline()
        selected_model = model or (
            overview["draft"]["model"] if overview.get("draft") else overview["active"]["model"]
        )
        validation = pipeline_service.validate_draft(selected_model)
        mock_results = payload.get("mock_results") if isinstance(payload.get("mock_results"), dict) else {}
        sample = self._sample_payload(payload)
        steps = selected_model.get("steps") if isinstance(selected_model.get("steps"), list) else []
        result = {
            "dry_run_id": f"dry-run-{len(steps)}-{len(mock_results)}",
            "mode": "draft" if overview.get("draft") and model is None else "submitted",
            "sample": sample,
            "pipeline": {
                "summary": PipelineConfigService._summary(selected_model),
                "steps": [
                    {
                        "key": step.get("key"),
                        "label": step.get("label"),
                        "class": step.get("class"),
                        "enabled": bool(step.get("enabled", True)),
                    }
                    for step in steps
                    if isinstance(step, dict)
                ],
            },
            "split": self._split_summary(steps, mock_results),
            "extraction": self._extraction_summary(steps, mock_results),
            "review_gate": self._review_gate_summary(steps, mock_results),
            "exports": self._export_summary(steps),
            "validation": validation,
            "writes": {
                "final_exports_written": False,
                "workflow_state_written": False,
                "audit_event_written": True,
            },
        }
        event = self.audit.append_event(
            event_type="admin_pipeline_dry_run",
            user=user,
            after=result,
            metadata={
                "request": _redact_secrets(payload),
                "validation_summary": validation.get("summary", {}),
                "sample": sample,
            },
        )
        result["audit_event_id"] = event["id"]
        return result

    def _sample_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        document_id = str(payload.get("document_id") or "").strip()
        if document_id:
            document = DocumentRepository(self.conn).get(document_id)
            if document:
                return {
                    "source": "document",
                    "document_id": document["id"],
                    "filename": document.get("original_filename"),
                    "status": document.get("status"),
                }
        sample = payload.get("sample") if isinstance(payload.get("sample"), dict) else {}
        filename = str(payload.get("sample_filename") or sample.get("filename") or "").strip()
        return {
            "source": "uploaded_sample" if filename else "none",
            "filename": filename or None,
            "size_bytes": sample.get("size_bytes"),
        }

    @staticmethod
    def _split_summary(steps: list[Any], mock_results: dict[str, Any]) -> dict[str, Any]:
        step = _first_step(steps, "LlamaCloudSplitTask")
        decisions = mock_results.get("split_decisions")
        if not isinstance(decisions, list):
            decisions = []
        if not step:
            return {"status": "not_configured", "decisions": []}
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        enabled = bool(step.get("enabled", True)) and bool(params.get("enabled", False))
        return {
            "status": "would_run" if enabled else "disabled",
            "task_key": step.get("key"),
            "categories": params.get("categories") if isinstance(params.get("categories"), list) else [],
            "decisions": decisions,
        }

    @staticmethod
    def _extraction_summary(steps: list[Any], mock_results: dict[str, Any]) -> dict[str, Any]:
        step = _first_matching_step(steps, lambda item: _is_extraction_step(item))
        fields = mock_results.get("extraction_fields")
        if not isinstance(fields, list):
            fields = []
        if not step:
            return {"status": "not_configured", "configured_fields": [], "mock_fields": fields}
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        configured_fields = params.get("fields") if isinstance(params.get("fields"), dict) else {}
        return {
            "status": "would_extract" if step.get("enabled", True) else "disabled",
            "task_key": step.get("key"),
            "provider": step.get("class"),
            "configured_fields": sorted(configured_fields),
            "mock_fields": fields,
            "mock_field_count": len(fields),
        }

    @staticmethod
    def _review_gate_summary(steps: list[Any], mock_results: dict[str, Any]) -> dict[str, Any]:
        step = _first_step(steps, "ReviewGateTask")
        if not step:
            return {"status": "not_configured", "review_required": False, "reasons": []}
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        threshold = float(params.get("confidence_threshold", 0.8))
        fields = mock_results.get("extraction_fields")
        fields = fields if isinstance(fields, list) else []
        reasons: list[str] = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            confidence = field.get("confidence")
            field_key = str(field.get("field_key") or field.get("key") or "field")
            if confidence is None and params.get("require_review_when_missing_confidence", True):
                reasons.append(f"{field_key}: missing confidence")
                continue
            try:
                if confidence is not None and float(confidence) < threshold:
                    reasons.append(f"{field_key}: below threshold")
            except (TypeError, ValueError):
                reasons.append(f"{field_key}: invalid confidence")
        explicit_required = mock_results.get("review_required")
        review_required = bool(params.get("always_review")) or bool(reasons)
        if explicit_required is not None:
            review_required = bool(explicit_required)
        return {
            "status": "would_evaluate" if step.get("enabled", True) else "disabled",
            "task_key": step.get("key"),
            "confidence_threshold": threshold,
            "review_required": review_required,
            "reasons": reasons,
        }

    @staticmethod
    def _export_summary(steps: list[Any]) -> dict[str, Any]:
        export_steps = [
            {
                "key": step.get("key"),
                "class": step.get("class"),
                "status": "skipped_in_dry_run",
            }
            for step in steps
            if isinstance(step, dict) and _is_export_step(step)
        ]
        return {"final_exports_written": False, "steps": export_steps}


def _float_between(value: Any, field_name: str) -> float:
    """Return a float between 0 and 1 inclusive."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AdminSettingsError(f"{field_name} must be a number between 0 and 1.") from exc
    if number < 0 or number > 1:
        raise AdminSettingsError(f"{field_name} must be between 0 and 1.")
    return number


def _positive_float(value: Any, field_name: str) -> float:
    """Return a positive float."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AdminSettingsError(f"{field_name} must be a positive number.") from exc
    if number <= 0:
        raise AdminSettingsError(f"{field_name} must be a positive number.")
    return number


def _positive_int(value: Any, field_name: str) -> int:
    """Return a positive integer."""
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise AdminSettingsError(f"{field_name} must be a positive integer.") from exc
    if number <= 0:
        raise AdminSettingsError(f"{field_name} must be a positive integer.")
    return number


def _threshold_map(value: Any, field_name: str) -> dict[str, float]:
    """Normalize a string-keyed map of confidence thresholds."""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise AdminSettingsError(f"{field_name} must be an object.")
    return {str(key): _float_between(item, field_name) for key, item in value.items() if str(key)}


def _string_list(value: Any) -> list[str]:
    """Normalize list-like settings into sorted unique strings."""
    if value in (None, ""):
        return []
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        raise AdminSettingsError("Expected a list of strings.")
    return sorted({item for item in items if item})


def _normalize_categories(value: Any) -> list[dict[str, str]]:
    """Normalize Split category definitions."""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise AdminSettingsError("categories must be a list.")
    categories: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            name = item.strip()
            description = ""
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
        else:
            raise AdminSettingsError(f"categories[{index}] must be an object or string.")
        if not name:
            raise AdminSettingsError(f"categories[{index}].name is required.")
        categories.append({"name": name, "description": description})
    return categories


def _default_for_setting(schema: dict[str, Any]) -> Any:
    """Return a sensible default for an editable setting schema."""
    if "default" in schema:
        return schema["default"]
    setting_type = schema["type"]
    if setting_type == "bool":
        return False
    if setting_type == "positive_int":
        return 1
    return ""


def _get_nested(config: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Read a dotted key path from a nested mapping."""
    value: Any = config
    for part in key_path.split("."):
        if not isinstance(value, dict):
            return default
        value = value.get(part, default)
    return value


def _set_nested(config: dict[str, Any], key_path: str, value: Any) -> None:
    """Set a dotted key path on a nested mapping."""
    target = config
    parts = key_path.split(".")
    for part in parts[:-1]:
        next_value = target.setdefault(part, {})
        if not isinstance(next_value, dict):
            next_value = {}
            target[part] = next_value
        target = next_value
    target[parts[-1]] = value


def _settings_groups(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Group editable settings for the admin settings API/UI."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for key, schema in EDITABLE_SETTINGS.items():
        group = schema["group"]
        groups.setdefault(group, []).append(
            {
                "key": key,
                "label": schema["label"],
                "type": schema["type"],
                "value": settings.get(key),
            }
        )
    return [
        {
            "name": group,
            "settings": rows,
        }
        for group, rows in groups.items()
    ]


def _audit_event_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Parse one audit row for API consumers."""
    event = json_loads(row.get("event_json"), {})
    if not isinstance(event, dict):
        event = {"value": event}
    return {
        "id": row.get("id"),
        "batch_id": row.get("batch_id"),
        "document_id": row.get("document_id"),
        "review_item_id": row.get("review_item_id"),
        "user": row.get("user"),
        "event_type": row.get("event_type"),
        "created_at": row.get("created_at"),
        "event": event,
        "before": event.get("before"),
        "after": event.get("after"),
        "metadata": event.get("metadata") if isinstance(event.get("metadata"), dict) else {},
    }


def _summary_for_findings(findings: Any) -> dict[str, int]:
    """Build validation summary counts from finding payloads."""
    if not isinstance(findings, list):
        return {"errors": 0, "warnings": 0}
    return {
        "errors": sum(1 for finding in findings if isinstance(finding, dict) and finding.get("severity") == "error"),
        "warnings": sum(
            1 for finding in findings if isinstance(finding, dict) and finding.get("severity") == "warning"
        ),
    }


def _first_step(steps: list[Any], class_name: str) -> dict[str, Any] | None:
    """Return the first step matching a class name."""
    return _first_matching_step(steps, lambda step: step.get("class") == class_name)


def _first_matching_step(steps: list[Any], predicate: Any) -> dict[str, Any] | None:
    """Return the first step matching a predicate."""
    for step in steps:
        if isinstance(step, dict) and predicate(step):
            return step
    return None


def _is_extraction_step(step: dict[str, Any]) -> bool:
    """Return whether a pipeline step represents extraction."""
    module_name = str(step.get("module") or "")
    class_name = str(step.get("class") or "")
    return ".extraction." in module_name or class_name in {"ExtractPdfTask", "ExtractPdfV2Task"}


def _is_export_step(step: dict[str, Any]) -> bool:
    """Return whether a pipeline step writes final output artifacts."""
    module_name = str(step.get("module") or "")
    class_name = str(step.get("class") or "")
    return (
        ".storage." in module_name
        or ".archiver." in module_name
        or class_name.startswith("Store")
        or class_name.startswith("Archive")
    )


def _secret_key(key: str) -> bool:
    """Return whether a key name should be treated as secret."""
    lowered = str(key or "").lower()
    return lowered in SECRET_KEYS or any(lowered.endswith(f"_{secret}") for secret in SECRET_KEYS)


def _redact_secrets(value: Any) -> Any:
    """Return a copy with secret-looking keys redacted."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _secret_key(str(key)) else _redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value
