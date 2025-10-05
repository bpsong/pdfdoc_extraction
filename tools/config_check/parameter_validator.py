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
_RULES_REQUIRED_KEYS = ("reference_file", "update_field")
_RULES_MIN_CLAUSES = 1
_RULES_MAX_CLAUSES = 5
_EXTRACTION_CREDENTIAL_PREFIXES = (
    'standard_step.extraction.',
    'custom_step.extraction.',
)

_LOCALDRIVE_MODULE_SUFFIX = 'store_file_to_localdrive'
_STORAGE_OVERRIDE_KEYS = {"data_dir", "filename"}



def _is_localdrive_storage(module_name: Optional[str]) -> bool:
    """Return True when module refers to the local drive storage task."""

    return isinstance(module_name, str) and module_name.split('.')[-1] == _LOCALDRIVE_MODULE_SUFFIX


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
        module_name = task_config.get("module")
        classification = _classify_task(module_name, params)

        if classification == "extraction":
            _validate_extraction_params(
                params,
                params_path,
                errors,
                warnings,
                module_name=module_name,
            )
        elif classification == "storage":
            if _is_localdrive_storage(module_name):
                _validate_required_string(
                    params,
                    params_path,
                    "files_dir",
                    errors,
                    code="param-localdrive-missing-files-dir",
                )
                _validate_required_string(
                    params,
                    params_path,
                    "filename",
                    errors,
                    code="param-localdrive-missing-filename",
                )
            else:
                _validate_standard_storage_params(
                    params,
                    params_path,
                    errors,
                    warnings,
                )
        elif classification == "archiver":
            _validate_required_string(
                params,
                params_path,
                "archive_dir",
                errors,
                code="param-archiver-missing-archive-dir",
            )
        elif classification == "rules":
            _validate_rules_params(params, params_path, errors)
        elif classification == "context":
            _validate_context_params(params, params_path, errors)
        elif classification == "housekeeping":
            _validate_housekeeping_params(params, params_path, errors)

    return ParameterValidationResult(errors=errors, warnings=warnings)


def _validate_standard_storage_params(
    params: Any,
    params_path: str,
    errors: List[ParameterIssue],
    warnings: List[ParameterIssue],
) -> None:
    """Validate storage task parameters with optional nested overrides."""

    if not isinstance(params, dict):
        errors.append(
            ParameterIssue(
                path=params_path,
                message="storage task params must be a mapping",
                code="param-not-mapping",
                details={"config_key": params_path},
            )
        )
        return

    storage_block = params.get("storage")
    storage_path = f"{params_path}.storage"
    storage_dict: Optional[Dict[str, Any]] = None

    if storage_block is not None:
        if isinstance(storage_block, dict):
            storage_dict = storage_block
            allowed_keys = ', '.join(sorted(_STORAGE_OVERRIDE_KEYS))
            for key in storage_dict:
                if key not in _STORAGE_OVERRIDE_KEYS:
                    warnings.append(
                        ParameterIssue(
                            path=f"{storage_path}.{key}",
                            message=(
                                f"storage overrides do not support key '{key}'; "
                                f"allowed keys are {allowed_keys}."
                            ),
                            code="param-storage-unknown-storage-key",
                            details={"config_key": f"{storage_path}.{key}", "key": key},
                        )
                    )
        else:
            errors.append(
                ParameterIssue(
                    path=storage_path,
                    message="storage overrides must be provided as a mapping",
                    code="param-storage-storage-block-type",
                    details={"config_key": storage_path},
                )
            )

    if storage_dict and "data_dir" in storage_dict:
        _validate_required_string(
            storage_dict,
            storage_path,
            "data_dir",
            errors,
            code="param-storage-missing-data-dir",
        )
    else:
        _validate_required_string(
            params,
            params_path,
            "data_dir",
            errors,
            code="param-storage-missing-data-dir",
        )

    if storage_dict and "filename" in storage_dict:
        _validate_required_string(
            storage_dict,
            storage_path,
            "filename",
            errors,
            code="param-storage-missing-filename",
        )
    else:
        _validate_required_string(
            params,
            params_path,
            "filename",
            errors,
            code="param-storage-missing-filename",
        )



def _classify_task(module_name: Optional[str], params: Any) -> Optional[str]:
    if isinstance(module_name, str):
        for prefix, classification in MODULE_PREFIX_CLASSIFICATION.items():
            if module_name.startswith(prefix):
                return classification
    if isinstance(params, dict) and isinstance(params.get("fields"), dict):
        return "extraction"
    return None


def _validate_extraction_params(
    params: Any,
    params_path: str,
    errors: List[ParameterIssue],
    warnings: List[ParameterIssue],
    *,
    module_name: Optional[str] = None,
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

    if _requires_extraction_credentials(module_name) or 'fields' in params:
        _validate_extraction_credential(
            params,
            params_path,
            'api_key',
            errors,
            code='param-extraction-missing-api-key',
        )
        _validate_extraction_credential(
            params,
            params_path,
            'agent_id',
            errors,
            code='param-extraction-missing-agent-id',
        )

    fields = params.get('fields')
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

    table_fields: List[str] = []

    for field_name, spec in fields.items():
        if isinstance(spec, dict) and spec.get('is_table') is True:
            table_fields.append(field_name)

        field_path = f"{params_path}.fields.{field_name}"
        _validate_field_spec(spec, field_path, errors, field_name)

    if len(table_fields) > 1:
        warnings.append(
            ParameterIssue(
                path=f"{params_path}.fields",
                message=(
                    "Multiple extraction fields are marked is_table: true; v2 storage tasks currently "
                    "support only a single table payload."
                ),
                code="param-extraction-multiple-tables",
                details={
                    "config_key": f"{params_path}.fields",
                    "fields": table_fields,
                },
            )
        )


def _requires_extraction_credentials(module_name: Optional[str]) -> bool:
    if not isinstance(module_name, str):
        return False
    return any(module_name.startswith(prefix) for prefix in _EXTRACTION_CREDENTIAL_PREFIXES)


def _validate_extraction_credential(
    params: Dict[str, Any],
    params_path: str,
    key: str,
    errors: List[ParameterIssue],
    *,
    code: str,
) -> None:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(
            ParameterIssue(
                path=f"{params_path}.{key}",
                message=f"Extraction tasks require '{key}' to be provided as a non-empty string.",
                code=code,
                details={
                    'config_key': f"{params_path}.{key}",
                    'credential': key,
                },
            )
        )


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

def _validate_rules_params(
    params: Any, params_path: str, errors: List[ParameterIssue]
) -> None:
    if not isinstance(params, dict):
        errors.append(
            ParameterIssue(
                path=params_path,
                message="rules task params must be a mapping",
                code="param-rules-not-mapping",
                details={"config_key": params_path},
            )
        )
        return

    for key in _RULES_REQUIRED_KEYS:
        _validate_required_string(
            params,
            params_path,
            key,
            errors,
            code=f"param-rules-missing-{key.replace('_', '-')}",
        )

    # Validate optional knobs as per Task 18 requirements
    _validate_optional_string_param(
        params,
        params_path,
        "write_value",
        errors,
        code="param-rules-invalid-write-value",
    )

    _validate_optional_bool_param(
        params,
        params_path,
        "backup",
        errors,
        code="param-rules-invalid-backup",
    )

    _validate_optional_string_param(
        params,
        params_path,
        "task_slug",
        errors,
        code="param-rules-invalid-task-slug",
    )

    csv_match = params.get("csv_match")
    csv_path = f"{params_path}.csv_match"

    if not isinstance(csv_match, dict):
        errors.append(
            ParameterIssue(
                path=csv_path,
                message="csv_match must be a mapping with type and clauses",
                code="param-rules-csv-match-mapping",
                details={"config_key": csv_path},
            )
        )
        return

    match_type = csv_match.get("type", "column_equals_all")
    if not isinstance(match_type, str) or not match_type.strip():
        errors.append(
            ParameterIssue(
                path=f"{csv_path}.type",
                message="csv_match.type must be a non-empty string",
                code="param-rules-csv-type",
            )
        )
    elif match_type != "column_equals_all":
        errors.append(
            ParameterIssue(
                path=f"{csv_path}.type",
                message="csv_match.type must be 'column_equals_all'",
                code="param-rules-csv-type",
            )
        )

    clauses = csv_match.get("clauses")
    clauses_path = f"{csv_path}.clauses"

    if not isinstance(clauses, list):
        errors.append(
            ParameterIssue(
                path=clauses_path,
                message="csv_match.clauses must be a list of clause definitions",
                code="param-rules-clauses-type",
            )
        )
        return

    clause_count = len(clauses)
    if clause_count < _RULES_MIN_CLAUSES or clause_count > _RULES_MAX_CLAUSES:
        errors.append(
            ParameterIssue(
                path=clauses_path,
                message=(
                    f"csv_match.clauses must define between {_RULES_MIN_CLAUSES} and {_RULES_MAX_CLAUSES} entries"
                ),
                code="param-rules-clauses-count",
                details={"count": clause_count},
            )
        )
        return

    for index, clause in enumerate(clauses):
        clause_path = f"{clauses_path}[{index}]"

        if not isinstance(clause, dict):
            errors.append(
                ParameterIssue(
                    path=clause_path,
                    message="Each csv_match clause must be a mapping",
                    code="param-rules-clause-not-mapping",
                    details={"index": index},
                )
            )
            continue

        column = clause.get("column")
        if not isinstance(column, str) or not column.strip():
            errors.append(
                ParameterIssue(
                    path=f"{clause_path}.column",
                    message="Clause column must be a non-empty string",
                    code="param-rules-clause-column",
                    details={"index": index},
                )
            )

        from_context = clause.get("from_context")
        if not isinstance(from_context, str) or not from_context.strip():
            errors.append(
                ParameterIssue(
                    path=f"{clause_path}.from_context",
                    message="Clause from_context must be a non-empty string",
                    code="param-rules-clause-context",
                    details={"index": index},
                )
            )

        if "number" in clause and not isinstance(clause.get("number"), bool):
            errors.append(
                ParameterIssue(
                    path=f"{clause_path}.number",
                    message="Clause number flag must be boolean when provided",
                    code="param-rules-clause-number-type",
                    details={"index": index},
                )
            )


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
                code=code or "param-required-string",
                details={"config_key": f"{params_path}.{key}"},
            )
        )


def _validate_optional_string_param(
    params: Any,
    params_path: str,
    key: str,
    errors: List[ParameterIssue],
    *,
    code: Optional[str] = None,
) -> None:
    """Validate optional string parameter."""
    if not isinstance(params, dict):
        return

    value = params.get(key)
    if value is not None and not isinstance(value, str):
        errors.append(
            ParameterIssue(
                path=f"{params_path}.{key}",
                message=f"Parameter '{key}' must be a string when provided",
                code=code or "param-optional-invalid-type",
                details={"config_key": f"{params_path}.{key}", "expected_type": "str"},
            )
        )


def _validate_optional_bool_param(
    params: Any,
    params_path: str,
    key: str,
    errors: List[ParameterIssue],
    *,
    code: Optional[str] = None,
) -> None:
    """Validate optional boolean parameter."""
    if not isinstance(params, dict):
        return

    value = params.get(key)
    if value is not None and not isinstance(value, bool):
        errors.append(
            ParameterIssue(
                path=f"{params_path}.{key}",
                message=f"Parameter '{key}' must be a boolean when provided",
                code=code or "param-optional-invalid-type",
                details={"config_key": f"{params_path}.{key}", "expected_type": "bool"},
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


def _validate_housekeeping_params(
    params: Any, params_path: str, errors: List[ParameterIssue]
) -> None:
    """Validate housekeeping task parameters, specifically CleanupTask processing_dir."""
    if not isinstance(params, dict):
        errors.append(
            ParameterIssue(
                path=params_path,
                message="housekeeping task params must be a mapping",
                code="param-housekeeping-not-mapping",
                details={"config_key": params_path},
            )
        )
        return

    # Task 18: Validate CleanupTask processing_dir if provided
    if "processing_dir" in params:
        processing_dir = params["processing_dir"]
        if not isinstance(processing_dir, str) or not processing_dir.strip():
            errors.append(
                ParameterIssue(
                    path=f"{params_path}.processing_dir",
                    message="CleanupTask processing_dir must be a non-empty string when provided",
                    code="param-housekeeping-processing-dir-invalid",
                    details={"config_key": f"{params_path}.processing_dir"},
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
