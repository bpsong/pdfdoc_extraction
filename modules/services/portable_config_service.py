"""Portable import/export helpers for versioned configuration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from modules.services.versioned_config_contracts import (
    PIPELINE_DEFINITION_SCHEMA_VERSION,
    PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION,
    ReviewSchemaCoordinate,
    VersionedConfigError,
    canonicalize_json,
    content_hash,
    normalize_key,
)


class PortableConfigError(VersionedConfigError):
    """Raised when a portable configuration bundle is invalid."""


CoordinateResolver = Callable[[ReviewSchemaCoordinate], str | None]
VersionCoordinateResolver = Callable[[str], ReviewSchemaCoordinate | None]


def parse_schema_coordinate(value: Any) -> ReviewSchemaCoordinate:
    """Parse and validate one portable review-schema coordinate."""
    if not isinstance(value, dict):
        raise PortableConfigError("Schema coordinate must be an object.")
    key = normalize_key(str(value.get("key") or ""), label="schema key")
    version_number = value.get("version")
    if isinstance(version_number, bool) or not isinstance(version_number, int) or version_number <= 0:
        raise PortableConfigError("Schema coordinate version must be a positive integer.")
    raw_hash = value.get("content_hash")
    if not isinstance(raw_hash, str) or len(raw_hash) != 64:
        raise PortableConfigError("Schema coordinate content_hash must be a SHA-256 hex string.")
    try:
        int(raw_hash, 16)
    except ValueError as exc:
        raise PortableConfigError("Schema coordinate content_hash must be hexadecimal.") from exc
    return ReviewSchemaCoordinate(
        key=key,
        version_number=version_number,
        content_hash=raw_hash.lower(),
    )


def import_pipeline_bundle(
    bundle: Mapping[str, Any],
    *,
    resolve_coordinate: CoordinateResolver | None = None,
) -> tuple[dict[str, Any], dict[str, ReviewSchemaCoordinate]]:
    """Convert a portable bundle into a local draft definition."""
    if bundle.get("kind") != "pipeline-bundle":
        raise PortableConfigError("Portable pipeline kind must be pipeline-bundle.")
    if bundle.get("format_version") != PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION:
        raise PortableConfigError("Unsupported portable pipeline format_version.")
    raw_definition = bundle.get("definition")
    if not isinstance(raw_definition, dict):
        raise PortableConfigError("Portable pipeline definition must be an object.")
    definition = deepcopy(raw_definition)
    definition.setdefault("schema_version", PIPELINE_DEFINITION_SCHEMA_VERSION)
    tasks = definition.get("tasks")
    if not isinstance(tasks, dict):
        raise PortableConfigError("Portable pipeline tasks must be an object.")

    embedded: dict[tuple[str, int, str], dict[str, Any]] = {}
    raw_dependencies = bundle.get("dependencies", {})
    if not isinstance(raw_dependencies, dict):
        raise PortableConfigError("Portable dependencies must be an object.")
    seen_coordinates: set[tuple[str, int, str]] = set()
    for entry in raw_dependencies.get("review_schemas", []) or []:
        if not isinstance(entry, dict):
            raise PortableConfigError("Review-schema dependency must be an object.")
        coordinate = parse_schema_coordinate(entry)
        marker = (
            coordinate.key,
            coordinate.version_number,
            coordinate.content_hash,
        )
        if marker in seen_coordinates:
            raise PortableConfigError("Duplicate review schema dependency.")
        seen_coordinates.add(marker)
        schema = entry.get("schema")
        if isinstance(schema, dict) and schema:
            if content_hash(schema) != coordinate.content_hash:
                raise PortableConfigError("Embedded review schema hash does not match its coordinate.")
            embedded[marker] = schema

    dependencies: dict[str, ReviewSchemaCoordinate] = {}
    for task_key, raw_task in tasks.items():
        if not isinstance(raw_task, dict):
            continue
        params = raw_task.get("params")
        if not isinstance(params, dict) or "schema" not in params:
            continue
        coordinate = parse_schema_coordinate(params["schema"])
        marker = (coordinate.key, coordinate.version_number, coordinate.content_hash)
        version_id = resolve_coordinate(coordinate) if resolve_coordinate else None
        if version_id is None and marker not in embedded:
            raise PortableConfigError(
                f"Unresolved review schema dependency for task {task_key}."
            )
        if version_id is None:
            version_id = f"embedded:{coordinate.key}:{coordinate.version_number}:{coordinate.content_hash}"
        params.pop("schema")
        params["schema_version_id"] = version_id
        dependencies[str(task_key)] = coordinate
    return canonicalize_json(definition), dependencies


def export_pipeline_bundle(
    definition: Mapping[str, Any],
    *,
    template_key: str,
    template_name: str,
    resolve_version: VersionCoordinateResolver,
    embedded_schemas: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert a local draft/version into a portable pipeline bundle."""
    portable_definition = deepcopy(dict(definition))
    tasks = portable_definition.get("tasks")
    if not isinstance(tasks, dict):
        raise PortableConfigError("Pipeline tasks must be an object.")
    dependency_entries: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for task_key, raw_task in tasks.items():
        if not isinstance(raw_task, dict):
            continue
        params = raw_task.get("params")
        if not isinstance(params, dict) or "schema_version_id" not in params:
            continue
        version_id = str(params.pop("schema_version_id"))
        coordinate = resolve_version(version_id)
        if coordinate is None:
            raise PortableConfigError(
                f"Unknown review schema version for task {task_key}."
            )
        params["schema"] = {
            "key": coordinate.key,
            "version": coordinate.version_number,
            "content_hash": coordinate.content_hash,
        }
        marker = (coordinate.key, coordinate.version_number, coordinate.content_hash)
        if marker in seen:
            continue
        seen.add(marker)
        entry: dict[str, Any] = dict(params["schema"])
        if embedded_schemas and version_id in embedded_schemas:
            schema = canonicalize_json(dict(embedded_schemas[version_id]))
            if content_hash(schema) != coordinate.content_hash:
                raise PortableConfigError("Embedded review schema hash mismatch during export.")
            entry["schema"] = schema
        dependency_entries.append(entry)
    return canonicalize_json(
        {
            "kind": "pipeline-bundle",
            "format_version": PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION,
            "template": {
                "key": normalize_key(template_key, label="template key"),
                "name": str(template_name).strip(),
            },
            "definition": portable_definition,
            "dependencies": {"review_schemas": dependency_entries},
        }
    )
