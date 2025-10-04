"""Parameter-level validation for config-check.

This module provides comprehensive parameter validation based on task classification,
ensuring that task parameters conform to expected formats and requirements for different
types of processing tasks in the PDF document extraction system.

The parameter validator performs task-specific validation based on module classification:
- Extraction tasks: Validates field definitions with type specifications
- Storage tasks: Validates required string parameters (data_dir, filename)
- Archiver tasks: Validates required string parameters (archive_dir)
- Context tasks: Validates optional length parameter with constraints

Key Features:
- Task classification-based parameter validation
- Field definition validation for extraction tasks with type checking
- Support for complex type specifications (Optional[T], List[T])
- Table field validation with nested item_fields
- Comprehensive error reporting with specific parameter paths
- Windows-compatible string validation and path handling

Classes:
    ParameterIssue: Represents a single parameter validation finding with error code
    ParameterValidationResult: Aggregated result containing all parameter validation findings

Constants:
    _ALLOWED_BASE_TYPES: Set of permitted base types for field validation

Functions:
    validate_parameters(): Main validation entry point with task classification
    _classify_task(): Classifies tasks based on module names and parameters
    _validate_extraction_params(): Validates extraction task field definitions
    _validate_field_spec(): Validates individual field specifications
    _validate_required_string(): Validates required string parameters

Type System:
    - Base types: str, int, float, bool, Any
    - Optional types: Optional[str], Optional[int], etc.
    - List types: List[str], List[Any], etc.
    - Table fields with nested item_fields for complex data structures

Windows Compatibility:
    - All string processing is Windows-compatible and encoding-aware
    - Path parameter validation handles Windows-specific formats
    - Case-sensitive type validation as per Python standards

Note:
    Parameter validation is performed after task classification and provides
    detailed feedback for configuration debugging and maintenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .pipeline_validator import MODULE_PREFIX_CLASSIFICATION

_ALLOWED_BASE_TYPES = {"str", "int", "float", "bool", "Any"}


@dataclass(slots=True)
class ParameterIssue:
    """Represents a parameter validation finding."""

    path: str
    message: str
    code: str = "parameter"
    details: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class ParameterValidationResult:
    """Aggregated parameter validation findings."""

    errors: List[ParameterIssue]
    warnings: List[ParameterIssue]


def validate_parameters(config: Dict[str, Any]) -> ParameterValidationResult:
    """Validate task parameter sections based on task classification."""

    errors: List[ParameterIssue] = []
    warnings: List[ParameterIssue] = []

    tasks = config.get("tasks")
    if not isinstance(tasks, dict):
        return ParameterValidationResult(
            errors=[
                ParameterIssue(
                    path="tasks",
                    message="tasks section must be a mapping",
                    code="tasks-not-mapping",
                    details={"config_key": "tasks"},
                )
            ],
            warnings=warnings,
        )

    for task_name, task_config in tasks.items():
        if not isinstance(task_config, dict):
            errors.append(
                ParameterIssue(
                    path=f"tasks.{task_name}",
                    message="Task definition must be a mapping",
                    code="task-definition-not-mapping",
                    details={"task_name": task_name},
                )
            )
            continue

        params = task_config.get("params", {})
        params_path = f"tasks.{task_name}.params"
        classification = _classify_task(task_config.get("module"), params)

        if classification == "extraction":
            _validate_extraction_params(params, params_path, errors)
        elif classification == "storage":
            _validate_required_string(
                params,
                params_path,
                "data_dir",
                errors,
                code="param-storage-missing-data-dir",
            )
            _validate_required_string(
                params,
                params_path,
                "filename",
                errors,
                code="param-storage-missing-filename",
            )
        elif classification == "archiver":
            _validate_required_string(
                params,
                params_path,
                "archive_dir",
                errors,
                code="param-archiver-missing-archive-dir",
            )
        elif classification == "context":
            _validate_context_params(params, params_path, errors)

    return ParameterValidationResult(errors=errors, warnings=warnings)


def _classify_task(module_name: Optional[str], params: Any) -> Optional[str]:
    if isinstance(module_name, str):
        for prefix, classification in MODULE_PREFIX_CLASSIFICATION.items():
            if module_name.startswith(prefix):
                return classification
    if isinstance(params, dict) and isinstance(params.get("fields"), dict):
        return "extraction"
    return None


def _validate_extraction_params(
    params: Any, params_path: str, errors: List[ParameterIssue]
) -> None:
    if not isinstance(params, dict):
        errors.append(
            ParameterIssue(
                path=params_path,
                message="extraction task params must be a mapping",
                code="param-extraction-not-mapping",
                details={"config_key": params_path},
            )
        )
        return

    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        errors.append(
            ParameterIssue(
                path=f"{params_path}.fields",
                message="extraction task must define fields mapping",
                code="param-extraction-missing-fields",
                details={"config_key": f"{params_path}.fields"},
            )
        )
        return

    for field_name, spec in fields.items():
        field_path = f"{params_path}.fields.{field_name}"
        _validate_field_spec(spec, field_path, errors, field_name)


def _validate_field_spec(
    spec: Any, path: str, errors: List[ParameterIssue], field_name: Optional[str] = None
) -> None:
    field = field_name or path.split('.')[-1]

    if not isinstance(spec, dict):
        errors.append(
            ParameterIssue(
                path=path,
                message="Field definition must be a mapping",
                code="param-field-invalid",
                details={"field": field},
            )
        )
        return

    alias = spec.get("alias")
    if not isinstance(alias, str) or not alias.strip():
        errors.append(
            ParameterIssue(
                path=f"{path}.alias",
                message="Field alias must be a non-empty string",
                code="param-field-missing-alias",
                details={"field": field},
            )
        )

    type_value = spec.get("type")
    if not isinstance(type_value, str) or not _is_valid_field_type(type_value.strip()):
        errors.append(
            ParameterIssue(
                path=f"{path}.type",
                message="Field type must be one of str, int, float, bool, Any, Optional[T], or List[T]",
                code="param-field-invalid-type",
                details={"field": field},
            )
        )

    is_table = spec.get("is_table", False)
    if "is_table" in spec and not isinstance(is_table, bool):
        errors.append(
            ParameterIssue(
                path=f"{path}.is_table",
                message="is_table must be a boolean",
                code="param-field-istable-bool",
                details={"field": field},
            )
        )
        is_table = bool(is_table)

    if is_table:
        item_fields = spec.get("item_fields")
        if not isinstance(item_fields, dict) or not item_fields:
            errors.append(
                ParameterIssue(
                    path=f"{path}.item_fields",
                    message="item_fields must be provided for table fields",
                    code="param-field-missing-item-fields",
                    details={"field": field},
                )
            )
        else:
            for sub_name, sub_spec in item_fields.items():
                sub_path = f"{path}.item_fields.{sub_name}"
                _validate_field_spec(sub_spec, sub_path, errors, sub_name)

def _validate_required_string(
    params: Any,
    params_path: str,
    key: str,
    errors: List[ParameterIssue],
    *,
    code: Optional[str] = None,
) -> None:
    if not isinstance(params, dict):
        errors.append(
            ParameterIssue(
                path=params_path,
                message="Task params must be a mapping",
                code="param-not-mapping",
                details={"config_key": params_path},
            )
        )
        return

    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(
            ParameterIssue(
                path=f"{params_path}.{key}",
                message=f"Parameter '{key}' is required and must be a non-empty string",
                code=code,
                details={"config_key": f"{params_path}.{key}"},
            )
        )


def _validate_context_params(
    params: Any, params_path: str, errors: List[ParameterIssue]
) -> None:
    if not isinstance(params, dict):
        errors.append(
            ParameterIssue(
                path=params_path,
                message="context task params must be a mapping",
                code="param-not-mapping",
                details={"config_key": params_path},
            )
        )
        return

    if "length" in params:
        value = params["length"]
        if not isinstance(value, int):
            errors.append(
                ParameterIssue(
                    path=f"{params_path}.length",
                    message="length must be an integer",
                    code="param-context-length-type",
                )
            )
        elif value < 5 or value > 21:
            errors.append(
                ParameterIssue(
                    path=f"{params_path}.length",
                    message="length must be between 5 and 21",
                    code="param-context-length-bounds",
                )
            )


def _iter_string_values(node: Any, base_path: str) -> Iterable[Tuple[str, str]]:
    if isinstance(node, str):
        yield base_path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            next_path = f"{base_path}.{key}" if base_path else key
            yield from _iter_string_values(value, next_path)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            next_path = f"{base_path}[{index}]" if base_path else f"[{index}]"
            yield from _iter_string_values(value, next_path)


def _is_valid_field_type(type_value: str) -> bool:
    if type_value in _ALLOWED_BASE_TYPES:
        return True

    if type_value.startswith("Optional[") and type_value.endswith("]"):
        inner = type_value[len("Optional[") : -1]
        return inner in _ALLOWED_BASE_TYPES

    if type_value.startswith("List[") and type_value.endswith("]"):
        inner = type_value[len("List[") : -1]
        return inner in _ALLOWED_BASE_TYPES or inner == "Any"

    return False
