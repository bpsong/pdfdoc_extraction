"""Approved workflow task registry and startup trust-gate validation."""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

from modules.config_manager import ConfigManager


BUILTIN_TASKS: dict[str, tuple[str, str]] = {
    "archive_pdf": ("standard_step.archiver.archive_pdf", "ArchivePdfTask"),
    "assign_nanoid": ("standard_step.context.assign_nanoid", "AssignNanoidTask"),
    "extract_pdf": ("standard_step.extraction.extract_pdf", "ExtractPdfTask"),
    "extract_pdf_v2": ("standard_step.extraction.extract_pdf_v2", "ExtractPdfV2Task"),
    "cleanup_task": ("standard_step.housekeeping.cleanup_task", "CleanupTask"),
    "review_gate": ("standard_step.review.review_gate", "ReviewGateTask"),
    "update_reference": ("standard_step.rules.update_reference", "UpdateReferenceTask"),
    "llamacloud_split": ("standard_step.split.llamacloud_split", "LlamaCloudSplitTask"),
    "store_file_to_localdrive": (
        "standard_step.storage.store_file_to_localdrive",
        "StoreFileToLocaldrive",
    ),
    "store_metadata_as_csv": (
        "standard_step.storage.store_metadata_as_csv",
        "StoreMetadataAsCsv",
    ),
    "store_metadata_as_csv_v2": (
        "standard_step.storage.store_metadata_as_csv_v2",
        "StoreMetadataAsCsvV2",
    ),
    "store_metadata_as_json": (
        "standard_step.storage.store_metadata_as_json",
        "StoreMetadataAsJson",
    ),
    "store_metadata_as_json_v2": (
        "standard_step.storage.store_metadata_as_json_v2",
        "StoreMetadataAsJsonV2",
    ),
}


@dataclass(frozen=True)
class TaskApprovalError(ValueError):
    """Raised when a configured workflow task is not approved for import."""

    module_name: str
    class_name: str
    task_key: str | None = None

    def __str__(self) -> str:
        task_label = f"task '{self.task_key}' " if self.task_key else ""
        return (
            f"Unapproved workflow {task_label}class {self.module_name}.{self.class_name}. "
            "Use an approved standard_step task or add a deployment-controlled "
            "custom_steps.registry entry using the custom_step. module prefix."
        )


def _finding(
    *,
    severity: str,
    path: str,
    message: str,
    code: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a normalized validation finding."""
    return {
        "severity": severity,
        "path": path,
        "message": message,
        "code": code,
        "details": details or {},
    }


class ApprovedTaskRegistry:
    """Validate task module/class pairs against built-in and custom registries."""

    CUSTOM_MODULE_PREFIX = "custom_step."

    def __init__(
        self,
        config_manager: ConfigManager | None = None,
        *,
        config_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the registry from active config or supplied config data."""
        self.config_manager = config_manager
        self.config_data = config_data if isinstance(config_data, dict) else self._config_from_manager()

    def approved_pairs(self) -> set[tuple[str, str]]:
        """Return exact module/class pairs approved for import."""
        approved = set(BUILTIN_TASKS.values())
        custom_steps = self._custom_steps()
        if not bool(custom_steps.get("enabled", False)):
            return approved

        registry = custom_steps.get("registry")
        if not isinstance(registry, dict):
            return approved

        for entry in registry.values():
            if not isinstance(entry, dict):
                continue
            module_name = entry.get("module")
            class_name = entry.get("class")
            if not isinstance(module_name, str) or not isinstance(class_name, str):
                continue
            if not module_name.startswith(self.CUSTOM_MODULE_PREFIX):
                continue
            approved.add((module_name, class_name))
        return approved

    def is_approved(self, module_name: str, class_name: str) -> bool:
        """Return whether the exact task pair is approved."""
        return (module_name, class_name) in self.approved_pairs()

    def assert_approved(
        self,
        module_name: str,
        class_name: str,
        *,
        task_key: str | None = None,
    ) -> None:
        """Raise TaskApprovalError unless the exact task pair is approved."""
        if not self.is_approved(module_name, class_name):
            raise TaskApprovalError(
                module_name=module_name,
                class_name=class_name,
                task_key=task_key,
            )

    def validate_pipeline_config(self, config_data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return blocking findings for unapproved active pipeline task pairs."""
        data = config_data if isinstance(config_data, dict) else self.config_data
        findings = self.validate_custom_registry(data)
        pipeline = data.get("pipeline") if isinstance(data.get("pipeline"), list) else []
        tasks = data.get("tasks") if isinstance(data.get("tasks"), dict) else {}

        for index, task_key in enumerate(pipeline):
            if not isinstance(task_key, str):
                continue
            task_cfg = tasks.get(task_key)
            if not isinstance(task_cfg, dict):
                continue
            module_name = task_cfg.get("module")
            class_name = task_cfg.get("class")
            if not isinstance(module_name, str) or not isinstance(class_name, str):
                continue
            if self.is_approved(module_name, class_name):
                continue
            findings.append(
                _finding(
                    severity="error",
                    path=f"tasks.{task_key}",
                    message=(
                        f"Pipeline task '{task_key}' uses unapproved task class "
                        f"{module_name}.{class_name}. Add a deployment-controlled "
                        "custom_steps.registry entry or use an approved standard_step task."
                    ),
                    code="pipeline-task-not-approved",
                    details={
                        "task_key": task_key,
                        "pipeline_index": index,
                        "module": module_name,
                        "class": class_name,
                    },
                )
            )
        return findings

    def validate_custom_registry(self, config_data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return findings for malformed or untrusted custom registry entries."""
        data = config_data if isinstance(config_data, dict) else self.config_data
        custom_steps = self._custom_steps(data)
        if not isinstance(custom_steps, dict) or not bool(custom_steps.get("enabled", False)):
            return []

        registry = custom_steps.get("registry")
        if registry is None:
            return []
        if not isinstance(registry, dict):
            return [
                _finding(
                    severity="error",
                    path="custom_steps.registry",
                    message="custom_steps.registry must be a mapping of approved custom task entries.",
                    code="custom-task-registry-not-mapping",
                )
            ]

        findings: list[dict[str, Any]] = []
        for registry_key, entry in registry.items():
            path = f"custom_steps.registry.{registry_key}"
            if not isinstance(entry, dict):
                findings.append(
                    _finding(
                        severity="error",
                        path=path,
                        message="Custom task registry entry must be a mapping with module and class.",
                        code="custom-task-registry-entry-invalid",
                    )
                )
                continue
            module_name = entry.get("module")
            class_name = entry.get("class")
            if not isinstance(module_name, str) or not module_name.strip():
                findings.append(
                    _finding(
                        severity="error",
                        path=f"{path}.module",
                        message="Custom task registry entry must include a module.",
                        code="custom-task-registry-missing-module",
                    )
                )
                continue
            if not isinstance(class_name, str) or not class_name.strip():
                findings.append(
                    _finding(
                        severity="error",
                        path=f"{path}.class",
                        message="Custom task registry entry must include a class.",
                        code="custom-task-registry-missing-class",
                    )
                )
                continue
            if not module_name.startswith(self.CUSTOM_MODULE_PREFIX):
                findings.append(
                    _finding(
                        severity="error",
                        path=f"{path}.module",
                        message="Custom task registry modules must use the custom_step. prefix.",
                        code="custom-task-registry-invalid-module",
                        details={
                            "registry_key": str(registry_key),
                            "module": module_name,
                            "class": class_name,
                        },
                    )
                )
        return findings

    def _custom_steps(self, config_data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = config_data if isinstance(config_data, dict) else self.config_data
        custom_steps = data.get("custom_steps") if isinstance(data, dict) else {}
        if custom_steps is None and self.config_manager is not None and hasattr(self.config_manager, "get"):
            custom_steps = self.config_manager.get("custom_steps", {})
        return custom_steps if isinstance(custom_steps, dict) else {}

    def _config_from_manager(self) -> dict[str, Any]:
        if self.config_manager is not None and hasattr(self.config_manager, "get_all"):
            data = self.config_manager.get_all()
            if isinstance(data, dict):
                return data
        return {}


def validate_startup_task_registry(
    config_manager: ConfigManager,
    *,
    wait_seconds: int = 15,
    sleeper: Callable[[float], None] = time.sleep,
    exit_func: Callable[[int], None] = sys.exit,
    stream: TextIO | None = None,
) -> bool:
    """Validate active startup tasks and exit after a readable delay on failure."""
    registry = ApprovedTaskRegistry(config_manager)
    findings = [
        finding
        for finding in registry.validate_pipeline_config()
        if finding.get("severity") == "error"
    ]
    if not findings:
        return True

    message = _startup_failure_message(findings, wait_seconds=wait_seconds)
    logger = logging.getLogger(__name__)
    logger.critical(message)
    _append_startup_failure_log(config_manager, message)

    output_stream = stream or sys.stderr
    print(message, file=output_stream)
    sleeper(wait_seconds)
    exit_func(1)
    return False


def _startup_failure_message(findings: list[dict[str, Any]], *, wait_seconds: int) -> str:
    lines = [
        "STARTUP BLOCKED: Unapproved workflow task classes were found in the active pipeline.",
        "",
    ]
    for finding in findings:
        details = finding.get("details") if isinstance(finding.get("details"), dict) else {}
        task_key = details.get("task_key", "unknown")
        module_name = details.get("module", "unknown")
        class_name = details.get("class", "unknown")
        lines.append(f"- task: {task_key}; class: {module_name}.{class_name}")
    lines.extend(
        [
            "",
            "Fix: use an approved standard_step task, or add the exact custom module/class pair",
            "to deployment YAML under custom_steps.registry with a custom_step. module prefix.",
            f"The application will shut down in {wait_seconds} seconds.",
        ]
    )
    return "\n".join(lines)


def _append_startup_failure_log(config_manager: ConfigManager, message: str) -> None:
    """Append startup trust-gate failures even if logging is not fully configured."""
    try:
        configured_path = config_manager.get("logging.log_file", "app.log")
        log_path = Path(str(configured_path or "app.log"))
        if not log_path.is_absolute():
            config_path = getattr(config_manager, "_config_path", None)
            base_dir = Path(config_path).parent if config_path else Path.cwd()
            log_path = base_dir / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"CRITICAL {message}\n")
    except Exception:
        logging.getLogger(__name__).exception("Failed to append startup trust-gate failure log")
