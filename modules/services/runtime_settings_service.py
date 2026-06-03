"""Read-only non-secret runtime settings for operators and admins."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from modules.config_manager import ConfigManager
from modules.services.task_catalog_service import TaskCatalogService


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


class RuntimeSettingsService:
    """Expose safe read-only runtime settings to authenticated users."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """Initialize the service.

        Args:
            config_manager: Active configuration provider.
        """
        self.config_manager = config_manager
        self.config = self._active_config()

    def settings(self) -> dict[str, Any]:
        """Return non-secret runtime settings for the operator settings page."""
        review_task = self._first_task_by_class("ReviewGateTask")
        split_task = self._first_task_by_class("LlamaCloudSplitTask")
        split_params = split_task.get("params", {}) if split_task else {}
        review_params = review_task.get("params", {}) if review_task else {}
        return {
            "application": {
                "app_name": self._get("ui.app_name", "DocFlow AI"),
                "page_size": self._get("ui.page_size", 25),
                "admin_enabled": bool(self._get("ui.admin_enabled", True)),
            },
            "paths": {
                "watch_folder_dir": self._get("watch_folder.dir"),
                "processing_dir": self._get("watch_folder.processing_dir"),
                "upload_dir": self._get("web.upload_dir"),
                "database_path": self._get("database.path"),
                "app_storage": _redact_secrets(self._get("app_storage", {})),
            },
            "review": {
                "lock_timeout_minutes": self._get("review.lock_timeout_minutes", 60),
                "default_queue_name": self._get("review.default_queue_name", "default_review"),
                "review_gate": {
                    "configured": bool(review_task),
                    "task_key": review_task.get("key") if review_task else None,
                    "confidence_threshold": review_params.get("confidence_threshold", 0.8),
                    "review_scope": review_params.get("review_scope", "low_confidence_fields"),
                    "always_review": bool(review_params.get("always_review", False)),
                    "field_threshold_overrides": review_params.get("field_threshold_overrides", {}),
                    "per_document_type_thresholds": review_params.get("per_document_type_thresholds", {}),
                    "schema_file": review_params.get("schema_file"),
                },
            },
            "split": {
                "configured": bool(split_task),
                "task_key": split_task.get("key") if split_task else None,
                "enabled": bool(split_params.get("enabled", False)) if split_task else False,
                "categories_count": len(split_params.get("categories", []))
                if isinstance(split_params.get("categories"), list)
                else 0,
                "allow_uncategorized": split_params.get("allow_uncategorized", "include"),
                "split_dir": split_params.get("split_dir") or self._get("app_storage.split_dir"),
                "api_key_configured": bool(split_params.get("api_key")),
            },
            "pipeline": self._pipeline_steps(),
            "secrets_redacted": True,
        }

    def _active_config(self) -> dict[str, Any]:
        """Return a copy of the active configuration mapping."""
        if hasattr(self.config_manager, "get_all"):
            config = self.config_manager.get_all()
        else:
            config = {}
        return deepcopy(config) if isinstance(config, dict) else {}

    def _get(self, key_path: str, default: Any = None) -> Any:
        """Read a dotted config key from config manager or active mapping."""
        if hasattr(self.config_manager, "get"):
            value = self.config_manager.get(key_path, default)
            if value is not default:
                return value
        value: Any = self.config
        for part in key_path.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part, default)
        return value

    def _pipeline_steps(self) -> list[dict[str, Any]]:
        """Return configured pipeline steps without secret params."""
        tasks = self._get("tasks", {})
        pipeline = self._get("pipeline", [])
        if not isinstance(tasks, dict) or not isinstance(pipeline, list):
            return []
        steps: list[dict[str, Any]] = []
        for index, task_key in enumerate(pipeline):
            if not isinstance(task_key, str):
                continue
            task_config = tasks.get(task_key)
            if not isinstance(task_config, dict):
                steps.append(
                    {
                        "index": index,
                        "key": task_key,
                        "label": task_key.replace("_", " ").title(),
                        "module": "",
                        "class": "",
                        "configured": False,
                        "params": {},
                    }
                )
                continue
            class_name = str(task_config.get("class") or "")
            steps.append(
                {
                    "index": index,
                    "key": task_key,
                    "label": TaskCatalogService._label_for(class_name) if class_name else task_key.replace("_", " ").title(),
                    "module": str(task_config.get("module") or ""),
                    "class": class_name,
                    "configured": True,
                    "on_error": task_config.get("on_error"),
                    "params": _redact_secrets(task_config.get("params") if isinstance(task_config.get("params"), dict) else {}),
                }
            )
        return steps

    def _first_task_by_class(self, class_name: str) -> dict[str, Any]:
        """Return the first configured task matching a class name."""
        tasks = self._get("tasks", {})
        if not isinstance(tasks, dict):
            return {}
        for task_key, task_config in tasks.items():
            if not isinstance(task_config, dict) or task_config.get("class") != class_name:
                continue
            return {
                "key": str(task_key),
                "module": str(task_config.get("module") or ""),
                "class": str(task_config.get("class") or ""),
                "params": _redact_secrets(task_config.get("params") if isinstance(task_config.get("params"), dict) else {}),
            }
        return {}


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
