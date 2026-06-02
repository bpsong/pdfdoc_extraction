"""Admin-editable review gate and split settings service."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sqlite3
from typing import Any

import yaml

from modules.config_manager import ConfigManager
from modules.db.repositories import AppSettingsRepository, ConfigVersionRepository
from modules.services.audit_service import AuditService


REVIEW_GATE_SETTINGS_KEY = "admin.review_gate_rules"
SPLIT_SETTINGS_KEY = "admin.split_settings"
REVIEW_GATE_CONFIG_TYPE = "review_gate_rules"
SPLIT_SETTINGS_CONFIG_TYPE = "split_settings"
CONFIG_NAME = "default"

REVIEW_SCOPES = {"document", "low_confidence_fields", "schema_errors", "split_result"}
RESUME_POLICIES = {"next_task"}
UNCATEGORIZED_POLICIES = {"include", "forbid", "omit"}


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
                if lowered in {"api_key", "password", "secret", "secret_key", "token"}:
                    return True
                if AdminSettingsService._contains_secret_key(item):
                    return True
        if isinstance(value, list):
            return any(AdminSettingsService._contains_secret_key(item) for item in value)
        return False


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
