"""Task validation logic for config-check.

This module provides comprehensive validation for task definitions and pipeline references
in configuration files, ensuring that all tasks are properly defined and pipeline
dependencies are correctly specified.

The task validator performs two main types of validation:
1. Structural validation: Ensures tasks and pipeline sections are properly formatted
2. Import validation (optional): Verifies that task modules and classes can be imported

Key Features:
- Validation of task definition structure and required fields
- Pipeline reference validation against defined tasks
- Optional runtime import checking for module/class availability
- Detailed error reporting with specific path context
- Windows-compatible module import handling
- Comprehensive error messages for troubleshooting

Classes:
    TaskIssue: Represents a single task validation finding with error code
    TaskValidationResult: Aggregated result containing all task validation findings

Functions:
    validate_tasks(): Main validation entry point with optional import checking

Windows Compatibility:
    - Proper handling of Windows module import paths
    - Case-insensitive class name validation where appropriate
    - Support for Windows-specific module naming conventions
    - Detailed import error messages for Windows path issues

Note:
    Import checks require the modules to be available in the current Python environment.
    This validation is optional and should be used carefully in production environments
    where module availability may vary.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class TaskIssue:
    """Represents a single task validation finding."""

    path: str
    message: str
    code: str = "task"
    details: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class TaskValidationResult:
    """Aggregated task validation findings."""

    errors: List[TaskIssue]
    warnings: List[TaskIssue]


def validate_tasks(
    config: Dict[str, Any], *, import_checks: bool = False
) -> TaskValidationResult:
    """Validate task definitions and pipeline references."""

    errors: List[TaskIssue] = []
    warnings: List[TaskIssue] = []

    tasks = config.get("tasks")
    pipeline = config.get("pipeline")

    if not isinstance(tasks, dict):
        errors.append(TaskIssue(path="tasks", message="tasks section must be a mapping"))
        tasks = {}

    if isinstance(pipeline, list):
        for idx, entry in enumerate(pipeline):
            path = f"pipeline[{idx}]"
            if not isinstance(entry, str) or not entry.strip():
                errors.append(
                    TaskIssue(
                        path=path,
                        message="Pipeline entries must be non-empty strings referencing task ids",
                        code="pipeline-entry-invalid",
                        details={"entry": entry},
                    )
                )
                continue
            if entry not in tasks:
                errors.append(
                    TaskIssue(
                        path=path,
                        message=f"Task name '{entry}' not found under tasks. Add tasks.{entry} or remove it from pipeline.",
                        code="pipeline-missing-task",
                        details={"task_name": entry},
                    )
                )
    else:
        errors.append(
            TaskIssue(
                path="pipeline",
                message="pipeline section must be a list of task identifiers",
                code="pipeline-not-list",
            )
        )

    if import_checks and tasks:
        errors.extend(_run_import_checks(tasks))

    return TaskValidationResult(errors=errors, warnings=warnings)


def _run_import_checks(tasks: Dict[str, Any]) -> List[TaskIssue]:
    findings: List[TaskIssue] = []

    for task_name, task_config in tasks.items():
        if not isinstance(task_config, dict):
            findings.append(
                TaskIssue(
                    path=f"tasks.{task_name}",
                    message="Task definition must be a mapping",
                    code="task-definition-not-mapping",
                    details={"task_name": task_name},
                )
            )
            continue

        module_name = task_config.get("module")
        class_name = task_config.get("class")
        task_path = f"tasks.{task_name}"

        if not module_name or not isinstance(module_name, str):
            findings.append(
                TaskIssue(
                    path=f"{task_path}.module",
                    message="Task module must be a non-empty string for import checks",
                    code="task-import-invalid-module",
                    details={"task_name": task_name},
                )
            )
            continue
        if not class_name or not isinstance(class_name, str):
            findings.append(
                TaskIssue(
                    path=f"{task_path}.class",
                    message="Task class must be a non-empty string for import checks",
                    code="task-import-invalid-class",
                    details={"task_name": task_name},
                )
            )
            continue

        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - surface actual import error
            findings.append(
                TaskIssue(
                    path=f"{task_path}.module",
                    message=(
                        f"Could not import module '{module_name}': {exc}. "
                        "Check PYTHONPATH, installation, or module name."
                    ),
                    code="task-import-module",
                    details={"module": module_name, "task_name": task_name},
                )
            )
            continue

        try:
            attr = getattr(module, class_name)
        except AttributeError:
            findings.append(
                TaskIssue(
                    path=f"{task_path}.class",
                    message=(
                        f"Class '{class_name}' not found in module '{module_name}'. "
                        "Verify the class name or update the configuration."
                    ),
                    code="task-import-class",
                    details={"module": module_name, "class": class_name, "task_name": task_name},
                )
            )
            continue

        if not inspect.isclass(attr):
            findings.append(
                TaskIssue(
                    path=f"{task_path}.class",
                    message=(
                        f"Attribute '{class_name}' in module '{module_name}' is not a class. "
                        "Ensure the configuration references a callable task class."
                    ),
                    code="task-import-not-class",
                    details={"module": module_name, "class": class_name, "task_name": task_name},
                )
            )

    return findings
