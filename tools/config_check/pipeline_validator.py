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
    tokens_by_path = metadata["tokens_by_path"]
    per_task_tokens = metadata["per_task_tokens"]
    classifications = metadata["classifications"]

    allowed_tokens = known_field_tokens | KNOWN_CONTEXT_TOKENS

    for token_path, tokens in tokens_by_path:
        for token in tokens:
            if token not in allowed_tokens:
                errors.append(
                    PipelineIssue(
                        path=token_path,
                        message=(
                            f"Unknown template token '{token}'. Add an extraction field or update the template."
                        ),
                        code="pipeline-unknown-token",
                        details={"token": token, "config_key": token_path},
                    )
                )

    seen_counts: Dict[str, int] = {}
    extraction_seen = False
    context_seen = False
    housekeeping_indices: List[int] = []

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
        task_tokens = per_task_tokens.get(task_name, set())

        if classification == "extraction":
            extraction_seen = True
        elif classification == "context":
            context_seen = True
        elif classification == "housekeeping":
            housekeeping_indices.append(index)

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

    if not housekeeping_indices:
        errors.append(
            PipelineIssue(
                path="pipeline",
                message="Pipeline must include a housekeeping task as the final step",
                code="pipeline-missing-housekeeping",
            )
        )
    else:
        last_housekeeping_index = housekeeping_indices[-1]
        if last_housekeeping_index != len(pipeline) - 1:
            task_name = pipeline[last_housekeeping_index] if last_housekeeping_index < len(pipeline) else None
            details = {"task_name": task_name} if isinstance(task_name, str) else None
            warnings.append(
                PipelineIssue(
                    path=f"pipeline[{last_housekeeping_index}]",
                    message="Housekeeping task should be the final pipeline step",
                    code="pipeline-housekeeping-not-last",
                    details=details,
                )
            )

    return PipelineValidationResult(errors=errors, warnings=warnings)


def _build_task_metadata(tasks: Dict[str, Any]) -> Dict[str, Any]:
    known_fields: Set[str] = set()
    tokens_by_path: List[Tuple[str, Set[str]]] = []
    per_task_tokens: Dict[str, Set[str]] = {}
    classifications: Dict[str, Optional[str]] = {}

    for task_name, task_config in tasks.items():
        if not isinstance(task_config, dict):
            continue

        params = task_config.get("params", {})
        classification = _classify_task(task_config.get("module"))

        if (
            classification is None
            and isinstance(params, dict)
            and isinstance(params.get("fields"), dict)
        ):
            classification = "extraction"

        classifications[task_name] = classification

        if classification == "extraction" and isinstance(params, dict):
            fields = params.get("fields")
            if isinstance(fields, dict):
                known_fields.update(fields.keys())

        task_tokens: Set[str] = set()
        for string_path, value in _iter_string_values(params, f"tasks.{task_name}.params"):
            tokens = _extract_tokens(value)
            if tokens:
                tokens_by_path.append((string_path, tokens))
                task_tokens.update(tokens)

        per_task_tokens[task_name] = task_tokens

    return {
        "known_fields": known_fields,
        "tokens_by_path": tokens_by_path,
        "per_task_tokens": per_task_tokens,
        "classifications": classifications,
    }


def _classify_task(module_name: Optional[str]) -> Optional[str]:
    if not isinstance(module_name, str):
        return None
    for prefix, classification in MODULE_PREFIX_CLASSIFICATION.items():
        if module_name.startswith(prefix):
            return classification
    return None


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
