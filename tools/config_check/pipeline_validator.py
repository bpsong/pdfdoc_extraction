"""Pipeline dependency validation for config-check.

This module provides comprehensive validation for pipeline ordering, dependencies, and token
usage in configuration files, ensuring proper execution flow and data dependency management
across different types of processing tasks.

The pipeline validator performs several key validations:
1. Pipeline structure validation (proper list format and task references)
2. Task classification and categorization based on module prefixes
3. Template token extraction and validation against known fields
4. Dependency order validation (extraction before storage, context before nanoid usage)
5. Housekeeping task placement validation (must be final step)

Key Features:
- Advanced token extraction using regex pattern matching
- Task classification based on module naming conventions
- Dependency order validation for proper data flow
- Template token validation against extraction fields
- Comprehensive error reporting with specific pipeline positions
- Support for multiple task categories (extraction, storage, context, etc.)

Classes:
    PipelineIssue: Represents a single pipeline validation finding with error code
    PipelineValidationResult: Aggregated result containing all pipeline validation findings

Constants:
    TOKEN_PATTERN: Regex pattern for extracting template tokens from strings
    KNOWN_CONTEXT_TOKENS: Set of predefined context tokens available to all tasks
    MODULE_PREFIX_CLASSIFICATION: Mapping of module prefixes to task categories

Functions:
    validate_pipeline(): Main validation entry point with comprehensive dependency checking
    _build_task_metadata(): Extracts and analyzes task metadata for validation
    _classify_task(): Classifies tasks based on module naming conventions

Token System:
    - Template tokens use {token_name} format (e.g., {filename}, {nanoid})
    - Context tokens are available globally (id, nanoid, filename, etc.)
    - Field tokens are extracted from extraction task field definitions
    - Token validation ensures all referenced tokens are properly defined

Windows Compatibility:
    - All string processing is Windows-compatible and encoding-aware
    - Token extraction handles Windows-specific path formats
    - Case-sensitive token matching as per template requirements

Note:
    Pipeline validation assumes tasks are executed in the order specified.
    The validator enforces best practices for data flow and cleanup operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

TOKEN_PATTERN = re.compile(r"(?<!\{)\{([A-Za-z0-9_]+)\}(?!\})")

KNOWN_CONTEXT_TOKENS: Set[str] = {
    "id",
    "nanoid",
    "filename",
    "source",
    "original_filename",
    "file_path",
}

MODULE_PREFIX_CLASSIFICATION = {
    "standard_step.extraction.": "extraction",
    "custom_step.extraction.": "extraction",
    "standard_step.storage.": "storage",
    "custom_step.storage.": "storage",
    "standard_step.context.": "context",
    "custom_step.context.": "context",
    "standard_step.archiver.": "archiver",
    "custom_step.archiver.": "archiver",
    "standard_step.housekeeping.": "housekeeping",
    "custom_step.housekeeping.": "housekeeping",
    "standard_step.rules.": "rules",
    "custom_step.rules.": "rules",
}

V2_STORAGE_SUFFIXES: Set[str] = {
    "store_metadata_as_json_v2",
    "store_metadata_as_csv_v2",
}


@dataclass(slots=True)
class TokenUsage:
    """Capture template token usage for a specific parameter string."""

    task_name: str
    path: str
    tokens: Set[str]


@dataclass(slots=True)
class PipelineIssue:
    """Represents a pipeline validation finding."""

    path: str
    message: str
    code: str = "pipeline"
    details: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class PipelineValidationResult:
    """Aggregated pipeline validation findings."""

    errors: List[PipelineIssue]
    warnings: List[PipelineIssue]



def validate_pipeline(config: Dict[str, Any]) -> PipelineValidationResult:
    """Validate pipeline ordering, dependencies, and token usage."""

    errors: List[PipelineIssue] = []
    warnings: List[PipelineIssue] = []

    tasks = config.get("tasks")
    pipeline = config.get("pipeline")

    if not isinstance(tasks, dict):
        errors.append(
            PipelineIssue(
                path="tasks",
                message="tasks section must be a mapping",
                code="tasks-not-mapping",
                details={"config_key": "tasks"},
            )
        )
        tasks = {}

    if not isinstance(pipeline, list):
        errors.append(
            PipelineIssue(
                path="pipeline",
                message="pipeline section must be a list of task identifiers",
                code="pipeline-not-list",
                details={"config_key": "pipeline"},
            )
        )
        return PipelineValidationResult(errors=errors, warnings=warnings)

    metadata = _build_task_metadata(tasks)
    known_field_tokens: Set[str] = metadata["known_fields"]
    token_usages = metadata["tokens_by_path"]
    per_task_tokens = metadata["per_task_tokens"]
    classifications = metadata["classifications"]
    metadata_producers = metadata.get("metadata_producers", set())
    module_names = metadata.get("module_names", {})
    scalar_field_tokens: Set[str] = metadata.get("scalar_fields", set())
    table_field_tokens: Set[str] = metadata.get("table_fields", set())

    allowed_tokens = known_field_tokens | KNOWN_CONTEXT_TOKENS

    for usage in token_usages:
        for token in usage.tokens:
            if token not in allowed_tokens:
                errors.append(
                    PipelineIssue(
                        path=usage.path,
                        message=(
                            f"Unknown template token '{token}'. Add an extraction field or update the template."
                        ),
                        code="pipeline-unknown-token",
                        details={"token": token, "config_key": usage.path},
                    )
                )

    reported_non_scalar: Set[Tuple[str, str]] = set()
    for usage in token_usages:
        classification = classifications.get(usage.task_name)
        if classification != "storage":
            continue
        if not _is_storage_filename_path(usage.task_name, usage.path):
            continue
        for token in usage.tokens:
            if token in known_field_tokens and token not in scalar_field_tokens:
                marker = (usage.path, token)
                if marker in reported_non_scalar:
                    continue
                reported_non_scalar.add(marker)
                details = {
                    "token": token,
                    "field": token,
                    "task_name": usage.task_name,
                    "config_key": usage.path,
                }
                if token in table_field_tokens:
                    details["field_type"] = "table"
                warnings.append(
                    PipelineIssue(
                        path=usage.path,
                        message=(
                            f"Filename token '{{{token}}}' in storage task '{usage.task_name}' references non-scalar extraction field '{token}'. Use a scalar field or update the template."
                        ),
                        code="pipeline-storage-filename-non-scalar",
                        details=details,
                    )
                )

    seen_counts: Dict[str, int] = {}
    extraction_seen = False
    metadata_ready = False
    context_seen = False

    for index, entry in enumerate(pipeline):
        path = f"pipeline[{index}]"

        if not isinstance(entry, str) or not entry.strip():
            errors.append(
                PipelineIssue(
                    path=path,
                    message="Pipeline entries must be non-empty strings referencing task ids",
                    code="pipeline-entry-invalid",
                    details={"entry": entry},
                )
            )
            continue

        task_name = entry.strip()
        seen_counts[task_name] = seen_counts.get(task_name, 0) + 1
        if seen_counts[task_name] > 1:
            warnings.append(
                PipelineIssue(
                    path=path,
                    message=f"Task '{task_name}' appears multiple times in pipeline",
                    code="pipeline-duplicate-task",
                    details={"task_name": task_name},
                )
            )

        classification = classifications.get(task_name)
        module_name = module_names.get(task_name)
        task_tokens = per_task_tokens.get(task_name, set())

        if classification == "extraction":
            extraction_seen = True
            if task_name in metadata_producers:
                metadata_ready = True
        elif classification == "context":
            context_seen = True
        if (
            classification == "storage"
            and (task_tokens & known_field_tokens)
            and not extraction_seen
        ):
            errors.append(
                PipelineIssue(
                    path=path,
                    message=(
                        f"Storage task '{task_name}' uses extracted data tokens but no extraction task runs earlier."
                    ),
                    code="pipeline-storage-before-extraction",
                    details={"task_name": task_name},
                )
            )

        if (
            classification == "storage"
            and _is_v2_storage_module(module_name)
            and not metadata_ready
        ):
            warnings.append(
                PipelineIssue(
                    path=path,
                    message=(
                        f"Storage task '{task_name}' expects extraction metadata but no metadata-producing extraction task runs earlier."
                    ),
                    code="pipeline-storage-metadata-missing",
                    details={"task_name": task_name},
                )
            )

        if classification != "context" and "nanoid" in task_tokens and not context_seen:
            errors.append(
                PipelineIssue(
                    path=path,
                    message=(
                        f"Task '{task_name}' references {{nanoid}} but no context initializer task precedes it."
                    ),
                    code="pipeline-nanoid-before-context",
                    details={"task_name": task_name},
                )
            )

    if not extraction_seen:
        errors.append(
            PipelineIssue(
                path="pipeline",
                message="Pipeline must include at least one extraction task to produce metadata for downstream steps",
                code="pipeline-missing-extraction",
            )
        )

    return PipelineValidationResult(errors=errors, warnings=warnings)




def _build_task_metadata(tasks: Dict[str, Any]) -> Dict[str, Any]:
    known_fields: Set[str] = set()
    token_usages: List[TokenUsage] = []
    per_task_tokens: Dict[str, Set[str]] = {}
    classifications: Dict[str, Optional[str]] = {}
    metadata_producers: Set[str] = set()
    module_names: Dict[str, Optional[str]] = {}
    scalar_fields: Set[str] = set()
    table_fields: Set[str] = set()

    for task_name, task_config in tasks.items():
        if not isinstance(task_config, dict):
            continue

        params = task_config.get("params", {})
        module_name = task_config.get("module")
        classification = _classify_task(module_name)

        if (
            classification is None
            and isinstance(params, dict)
            and isinstance(params.get("fields"), dict)
        ):
            classification = "extraction"

        classifications[task_name] = classification
        module_names[task_name] = module_name if isinstance(module_name, str) else None

        if classification == "extraction" and isinstance(params, dict):
            fields = params.get("fields")
            if isinstance(fields, dict):
                if fields:
                    metadata_producers.add(task_name)
                for field_name, spec in fields.items():
                    known_fields.add(field_name)
                    if _is_table_field(spec):
                        table_fields.add(field_name)
                    else:
                        scalar_fields.add(field_name)

        task_tokens: Set[str] = set()
        for string_path, value in _iter_string_values(params, f"tasks.{task_name}.params"):
            tokens = _extract_tokens(value)
            if tokens:
                token_usages.append(
                    TokenUsage(
                        task_name=task_name,
                        path=string_path,
                        tokens=tokens,
                    )
                )
                task_tokens.update(tokens)

        per_task_tokens[task_name] = task_tokens

    return {
        "known_fields": known_fields,
        "tokens_by_path": token_usages,
        "per_task_tokens": per_task_tokens,
        "classifications": classifications,
        "metadata_producers": metadata_producers,
        "module_names": module_names,
        "scalar_fields": scalar_fields,
        "table_fields": table_fields,
    }


def _classify_task(module_name: Optional[str]) -> Optional[str]:
    if not isinstance(module_name, str):
        return None
    for prefix, classification in MODULE_PREFIX_CLASSIFICATION.items():
        if module_name.startswith(prefix):
            return classification
    return None


def _is_storage_filename_path(task_name: str, path: str) -> bool:
    if not path:
        return False
    targets = (
        f"tasks.{task_name}.params.filename",
        f"tasks.{task_name}.params.storage.filename",
    )
    return path in targets


def _is_table_field(spec: Any) -> bool:
    return isinstance(spec, dict) and spec.get("is_table") is True


def _is_v2_storage_module(module_name: Optional[str]) -> bool:
    if not isinstance(module_name, str):
        return False
    return module_name.split('.')[-1] in V2_STORAGE_SUFFIXES


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


def _extract_tokens(value: str) -> Set[str]:
    return {match.group(1) for match in TOKEN_PATTERN.finditer(value)}
