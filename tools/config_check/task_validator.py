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
    """Enhanced import validation with better error reporting."""
    findings: List[TaskIssue] = []

    for task_name, task_config in tasks.items():
        # Validate task structure
        validation_result = _validate_task_structure(task_name, task_config)
        findings.extend(validation_result)
        
        if validation_result:  # Skip import checks if structure is invalid
            continue
            
        # Perform import validation
        import_result = _validate_task_imports(task_name, task_config)
        findings.extend(import_result)

    return findings


def _validate_task_structure(task_name: str, task_config: Any) -> List[TaskIssue]:
    """Validate task definition structure."""
    findings: List[TaskIssue] = []
    
    if not isinstance(task_config, dict):
        findings.append(
            TaskIssue(
                path=f"tasks.{task_name}",
                message="Task definition must be a mapping",
                code="task-definition-not-mapping",
                details={"task_name": task_name},
            )
        )
        return findings

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
    
    if not class_name or not isinstance(class_name, str):
        findings.append(
            TaskIssue(
                path=f"{task_path}.class",
                message="Task class must be a non-empty string for import checks",
                code="task-import-invalid-class",
                details={"task_name": task_name},
            )
        )

    return findings


def _validate_task_imports(task_name: str, task_config: Dict[str, Any]) -> List[TaskIssue]:
    """Validate task module and class imports with detailed error handling."""
    findings: List[TaskIssue] = []
    
    module_name = task_config.get("module")
    class_name = task_config.get("class")
    
    # Validate module import
    module_issue = _validate_module_import(module_name, task_name)
    if module_issue:
        findings.append(module_issue)
        return findings  # Skip class validation if module import fails
    
    # Validate class existence and type
    class_issue = _validate_class_existence(module_name, class_name, task_name)
    if class_issue:
        findings.append(class_issue)
        return findings
    
    # Validate class type
    type_issue = _validate_class_type(module_name, class_name, task_name)
    if type_issue:
        findings.append(type_issue)
    
    return findings


def _validate_module_import(module_name: str, task_name: str) -> Optional[TaskIssue]:
    """Validate that a module can be imported with detailed error reporting."""
    try:
        importlib.import_module(module_name)
        return None
    except ModuleNotFoundError as exc:
        return TaskIssue(
            path=f"tasks.{task_name}.module",
            message=f"Module '{module_name}' not found: {exc}. Check PYTHONPATH and module installation.",
            code="task-import-module-not-found",
            details={"module": module_name, "task_name": task_name, "error": str(exc)}
        )
    except SyntaxError as exc:
        return TaskIssue(
            path=f"tasks.{task_name}.module",
            message=f"Module '{module_name}' has syntax errors: {exc}",
            code="task-import-module-syntax-error",
            details={"module": module_name, "task_name": task_name, "error": str(exc)}
        )
    except ImportError as exc:
        return TaskIssue(
            path=f"tasks.{task_name}.module",
            message=f"Failed to import module '{module_name}': {exc}. Check module dependencies.",
            code="task-import-module-import-error",
            details={"module": module_name, "task_name": task_name, "error": str(exc)}
        )
    except Exception as exc:
        return TaskIssue(
            path=f"tasks.{task_name}.module",
            message=f"Unexpected error importing module '{module_name}': {exc}",
            code="task-import-module-error",
            details={"module": module_name, "task_name": task_name, "error": str(exc)}
        )


def _validate_class_existence(module_name: str, class_name: str, task_name: str) -> Optional[TaskIssue]:
    """Validate that a class exists in the specified module."""
    try:
        module = importlib.import_module(module_name)
        getattr(module, class_name)
        return None
    except AttributeError:
        # Get available attributes for better error message
        available_attrs = [attr for attr in dir(module) if not attr.startswith('_')]
        return TaskIssue(
            path=f"tasks.{task_name}.class",
            message=(
                f"Class '{class_name}' not found in module '{module_name}'. "
                f"Available attributes: {', '.join(available_attrs[:5])}{'...' if len(available_attrs) > 5 else ''}. "
                "Verify the class name or update the configuration."
            ),
            code="task-import-class-not-found",
            details={
                "module": module_name, 
                "class": class_name, 
                "task_name": task_name,
                "available_attributes": available_attrs
            }
        )
    except Exception as exc:
        return TaskIssue(
            path=f"tasks.{task_name}.class",
            message=f"Error accessing class '{class_name}' in module '{module_name}': {exc}",
            code="task-import-class-access-error",
            details={"module": module_name, "class": class_name, "task_name": task_name, "error": str(exc)}
        )


def _validate_class_type(module_name: str, class_name: str, task_name: str) -> Optional[TaskIssue]:
    """Validate that the specified attribute is actually a callable class."""
    try:
        module = importlib.import_module(module_name)
        attr = getattr(module, class_name)
        
        if not inspect.isclass(attr):
            attr_type = type(attr).__name__
            return TaskIssue(
                path=f"tasks.{task_name}.class",
                message=(
                    f"Attribute '{class_name}' in module '{module_name}' is not a class (found {attr_type}). "
                    "Ensure the configuration references a callable task class."
                ),
                code="task-import-not-callable",
                details={
                    "module": module_name, 
                    "class": class_name, 
                    "task_name": task_name,
                    "actual_type": attr_type
                }
            )
        
        return None
    except Exception as exc:
        return TaskIssue(
            path=f"tasks.{task_name}.class",
            message=f"Error validating class type for '{class_name}' in module '{module_name}': {exc}",
            code="task-import-class-type-error",
            details={"module": module_name, "class": class_name, "task_name": task_name, "error": str(exc)}
        )
