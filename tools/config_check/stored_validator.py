"""Read-only validation for SQLite-backed and portable configuration sources."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping

import yaml

from modules.db.migrations import SCHEMA_VERSION
from modules.services.portable_config_service import import_pipeline_bundle
from modules.services.validation_facade import ValidationFacade
from modules.services.versioned_config_contracts import (
    PIPELINE_DEFINITION_SCHEMA_VERSION,
    PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION,
    REVIEW_SCHEMA_FORMAT_VERSION,
    ReviewSchemaCoordinate,
    ValidationSource,
    content_hash,
)

from .validator import ValidationMessage, ValidationResult


class _MappingConfig:
    """Dot-path configuration provider for shared validation services."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        self.values = dict(values)

    def get(self, key: str, default: Any = None) -> Any:
        value: Any = self.values
        for part in key.split("."):
            if not isinstance(value, Mapping) or part not in value:
                return default
            value = value[part]
        return value


def load_document(path: Path) -> dict[str, Any]:
    """Load one bounded YAML/JSON object."""
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Validation input exceeds 2 MiB.")
    with path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError("Validation input must contain an object.")
    return document


def configured_database_path(
    config_path: Path, config: Mapping[str, Any]
) -> Path | None:
    """Resolve an explicitly configured SQLite database path."""
    database = config.get("database")
    raw = database.get("path") if isinstance(database, Mapping) else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    return path if path.is_absolute() else config_path.parent / path


@contextmanager
def open_readonly_database(path: Path) -> Iterator[sqlite3.Connection]:
    """Open SQLite without creating, migrating, or writing the database."""
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Configured database does not exist: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    try:
        yield conn
    finally:
        conn.close()


def validate_database_schema(conn: sqlite3.Connection) -> ValidationResult:
    """Return a blocking finding when the database is not schema version 3."""
    try:
        row = conn.execute(
            "SELECT MAX(version) AS version FROM schema_migrations"
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        return _error(
            "database.schema",
            f"Unable to read schema migrations: {exc}",
            "database-schema-unavailable",
        )
    version = int(row["version"] or 0)
    if version < SCHEMA_VERSION:
        return _error(
            "database.schema",
            f"Database schema version {version} is older than required version {SCHEMA_VERSION}.",
            "database-schema-outdated",
        )
    required = {
        "pipeline_templates",
        "pipeline_drafts",
        "pipeline_versions",
        "review_schema_templates",
        "review_schema_drafts",
        "review_schema_versions",
        "pipeline_version_schema_dependencies",
        "watch_folder_bindings",
    }
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    missing = sorted(required - {str(row["name"]) for row in rows})
    if missing:
        return _error(
            "database.schema",
            f"Database is missing required versioned configuration tables: {', '.join(missing)}",
            "database-schema-incomplete",
        )
    return ValidationResult()


class StoredSourceValidator:
    """Validate stored drafts, versions, active state, and bindings read-only."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        runtime_config: Mapping[str, Any],
    ) -> None:
        self.conn = conn
        self.runtime_config = dict(runtime_config)
        self.facade = ValidationFacade(_MappingConfig(runtime_config))
        raw_secrets = runtime_config.get("pipeline_secrets")
        self.secret_aliases = (
            set(raw_secrets) if isinstance(raw_secrets, Mapping) else set()
        )

    def validate_default(self) -> ValidationResult:
        """Validate all active eligible versions and enabled bindings."""
        result = ValidationResult()
        rows = self.conn.execute(
            """
            SELECT v.id
            FROM pipeline_versions v
            JOIN pipeline_templates t ON t.id = v.template_id
            WHERE t.status = 'active'
            ORDER BY t.template_key, v.version_number
            """
        ).fetchall()
        if not rows:
            result.errors.append(
                ValidationMessage(
                    path="stored.active_pipelines",
                    message="No active published pipeline version is available.",
                    code="stored-active-pipeline-missing",
                )
            )
        for row in rows:
            _merge(result, self.validate_pipeline_version_id(str(row["id"])))
        _merge(result, self.validate_bindings())
        return result

    def validate_all(self) -> ValidationResult:
        """Validate every stored draft and published version."""
        result = ValidationResult()
        for row in self.conn.execute(
            "SELECT template_key FROM pipeline_templates ORDER BY template_key"
        ):
            _merge(result, self.validate_pipeline(str(row["template_key"]), draft=True))
            versions = self.conn.execute(
                """
                SELECT v.id FROM pipeline_versions v
                JOIN pipeline_templates t ON t.id = v.template_id
                WHERE t.template_key = ? ORDER BY v.version_number
                """,
                (row["template_key"],),
            ).fetchall()
            for version in versions:
                _merge(
                    result,
                    self.validate_pipeline_version_id(str(version["id"])),
                )
        for row in self.conn.execute(
            "SELECT schema_key FROM review_schema_templates ORDER BY schema_key"
        ):
            _merge(
                result,
                self.validate_review_schema(str(row["schema_key"]), draft=True),
            )
            versions = self.conn.execute(
                """
                SELECT v.version_number FROM review_schema_versions v
                JOIN review_schema_templates t ON t.id = v.schema_template_id
                WHERE t.schema_key = ? ORDER BY v.version_number
                """,
                (row["schema_key"],),
            ).fetchall()
            for version in versions:
                _merge(
                    result,
                    self.validate_review_schema(
                        str(row["schema_key"]),
                        version_number=int(version["version_number"]),
                    ),
                )
        _merge(result, self.validate_bindings())
        return result

    def validate_pipeline(
        self,
        key: str,
        *,
        draft: bool = False,
        version_number: int | None = None,
    ) -> ValidationResult:
        """Validate one pipeline draft or stable numbered version."""
        if draft == (version_number is not None):
            return _error(
                f"stored.pipeline[{key}]",
                "Select exactly one of draft or version.",
                "stored-selector-invalid",
            )
        if draft:
            row = self.conn.execute(
                """
                SELECT d.definition_json, d.revision, t.template_key
                FROM pipeline_drafts d
                JOIN pipeline_templates t ON t.id = d.template_id
                WHERE t.template_key = ?
                """,
                (key,),
            ).fetchone()
            if row is None:
                return _error(
                    f"pipeline_draft[{key}]",
                    "Stored pipeline draft was not found.",
                    "stored-pipeline-not-found",
                )
            definition = _json_object(row["definition_json"])
            dependencies = self._dependencies_from_definition(definition)
            source = ValidationSource(
                "pipeline_draft", key=key, revision=int(row["revision"])
            )
            return self._facade_result(
                self.facade.validate_pipeline(
                    definition,
                    source=source,
                    schema_dependencies=dependencies,
                ),
                definition=definition,
            )
        row = self.conn.execute(
            """
            SELECT v.id
            FROM pipeline_versions v
            JOIN pipeline_templates t ON t.id = v.template_id
            WHERE t.template_key = ? AND v.version_number = ?
            """,
            (key, version_number),
        ).fetchone()
        if row is None:
            return _error(
                f"pipeline_version[{key}@{version_number}]",
                "Stored pipeline version was not found.",
                "stored-pipeline-not-found",
            )
        return self.validate_pipeline_version_id(str(row["id"]))

    def validate_pipeline_version_id(self, version_id: str) -> ValidationResult:
        row = self.conn.execute(
            """
            SELECT v.*, t.template_key
            FROM pipeline_versions v
            JOIN pipeline_templates t ON t.id = v.template_id
            WHERE v.id = ?
            """,
            (version_id,),
        ).fetchone()
        if row is None:
            return _error(
                f"pipeline_version[{version_id}]",
                "Stored pipeline version was not found.",
                "stored-pipeline-not-found",
            )
        definition = _json_object(row["definition_json"])
        if content_hash(definition) != row["content_hash"]:
            return _error(
                f"pipeline_version[{row['template_key']}@{row['version_number']}].content_hash",
                "Stored pipeline content hash does not match its definition.",
                "stored-pipeline-hash-mismatch",
            )
        dependencies: dict[str, dict[str, Any]] = {}
        dep_rows = self.conn.execute(
            """
            SELECT d.task_key, v.*
            FROM pipeline_version_schema_dependencies d
            JOIN review_schema_versions v ON v.id = d.schema_version_id
            WHERE d.pipeline_version_id = ?
            """,
            (version_id,),
        ).fetchall()
        for dependency in dep_rows:
            dependencies[str(dependency["task_key"])] = dict(dependency)
        source = ValidationSource(
            "pipeline_version",
            key=str(row["template_key"]),
            version_number=int(row["version_number"]),
        )
        return self._facade_result(
            self.facade.validate_pipeline(
                definition,
                source=source,
                schema_dependencies=dependencies,
            ),
            definition=definition,
        )

    def validate_review_schema(
        self,
        key: str,
        *,
        draft: bool = False,
        version_number: int | None = None,
    ) -> ValidationResult:
        """Validate one review-schema draft or stable numbered version."""
        if draft == (version_number is not None):
            return _error(
                f"stored.review_schema[{key}]",
                "Select exactly one of draft or version.",
                "stored-selector-invalid",
            )
        if draft:
            row = self.conn.execute(
                """
                SELECT d.schema_json, d.revision, t.schema_key
                FROM review_schema_drafts d
                JOIN review_schema_templates t ON t.id = d.schema_template_id
                WHERE t.schema_key = ?
                """,
                (key,),
            ).fetchone()
            source = (
                ValidationSource(
                    "review_schema_draft",
                    key=key,
                    revision=int(row["revision"]),
                )
                if row
                else None
            )
        else:
            row = self.conn.execute(
                """
                SELECT v.schema_json, v.version_number, v.content_hash,
                       t.schema_key
                FROM review_schema_versions v
                JOIN review_schema_templates t ON t.id = v.schema_template_id
                WHERE t.schema_key = ? AND v.version_number = ?
                """,
                (key, version_number),
            ).fetchone()
            source = (
                ValidationSource(
                    "review_schema_version",
                    key=key,
                    version_number=int(row["version_number"]),
                )
                if row
                else None
            )
        if row is None or source is None:
            return _error(
                f"review_schema[{key}]",
                "Stored review schema source was not found.",
                "stored-review-schema-not-found",
            )
        schema = _json_object(row["schema_json"])
        if not draft and content_hash(schema) != row["content_hash"]:
            return _error(
                f"{source.prefix}.content_hash",
                "Stored review schema hash does not match its content.",
                "stored-review-schema-hash-mismatch",
            )
        return self._facade_result(
            self.facade.validate_review_schema(schema, source=source)
        )

    def validate_bindings(self) -> ValidationResult:
        result = ValidationResult()
        rows = self.conn.execute(
            """
            SELECT b.id, b.folder_path, b.enabled, v.id AS version_id,
                   t.status, t.template_key
            FROM watch_folder_bindings b
            JOIN pipeline_versions v ON v.id = b.pipeline_version_id
            JOIN pipeline_templates t ON t.id = v.template_id
            WHERE b.enabled = 1
            ORDER BY b.folder_path
            """
        ).fetchall()
        normalized: list[tuple[str, str]] = []
        for row in rows:
            prefix = f"watch_binding[{row['id']}]"
            if row["status"] != "active":
                result.errors.append(
                    ValidationMessage(
                        path=f"{prefix}.pipeline_version",
                        message="Enabled binding references an inactive pipeline template.",
                        code="binding-pipeline-inactive",
                    )
                )
            path = Path(str(row["folder_path"]))
            if not path.exists() or not path.is_dir():
                result.errors.append(
                    ValidationMessage(
                        path=f"{prefix}.folder_path",
                        message="Enabled binding folder is not an accessible directory.",
                        code="binding-folder-unavailable",
                    )
                )
            marker = str(path.resolve()).casefold()
            for other_marker, other_id in normalized:
                if (
                    marker == other_marker
                    or marker.startswith(f"{other_marker}\\")
                    or other_marker.startswith(f"{marker}\\")
                ):
                    result.errors.append(
                        ValidationMessage(
                            path=f"{prefix}.folder_path",
                            message=f"Enabled binding overlaps binding {other_id}.",
                            code="binding-folder-overlap",
                        )
                    )
            normalized.append((marker, str(row["id"])))
        return result

    def _dependencies_from_definition(
        self, definition: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        dependencies: dict[str, dict[str, Any]] = {}
        tasks = definition.get("tasks")
        if not isinstance(tasks, Mapping):
            return dependencies
        for task_key, task in tasks.items():
            params = task.get("params") if isinstance(task, Mapping) else None
            version_id = (
                params.get("schema_version_id")
                if isinstance(params, Mapping)
                else None
            )
            if not isinstance(version_id, str):
                continue
            row = self.conn.execute(
                "SELECT * FROM review_schema_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
            if row is not None:
                dependencies[str(task_key)] = dict(row)
        return dependencies

    def _facade_result(
        self,
        facade_result: Mapping[str, Any],
        *,
        definition: Mapping[str, Any] | None = None,
    ) -> ValidationResult:
        result = _from_findings(facade_result.get("findings", []))
        if definition is not None:
            for path, alias in _secret_references(definition):
                if alias not in self.secret_aliases:
                    result.errors.append(
                        ValidationMessage(
                            path=f"{facade_result['source']}.{path}",
                            message=f"Secret alias is not configured: {alias}",
                            code="pipeline-secret-alias-unconfigured",
                        )
                    )
        return result


def validate_portable_file(
    path: Path,
    *,
    kind: str,
    runtime_config: Mapping[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> ValidationResult:
    """Validate a portable file without importing or mutating any state."""
    try:
        document = load_document(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return _error("file", str(exc), "portable-file-invalid")
    if kind == "runtime":
        from .validator import ConfigValidator

        return ConfigValidator(base_dir=path.parent).validate_config_data(document)
    facade = ValidationFacade(_MappingConfig(runtime_config or {}))
    if kind == "review-schema":
        schema = document.get("schema", document)
        if not isinstance(schema, dict):
            return _error(
                "review_schema_file.schema",
                "Portable review schema content must be an object.",
                "portable-review-schema-invalid",
            )
        source = ValidationSource(
            "review_schema_file",
            key=str(document.get("schema_key") or path.stem),
            version_number=document.get("version")
            if isinstance(document.get("version"), int)
            else None,
        )
        return _from_findings(
            facade.validate_review_schema(
                schema,
                source=source,
                format_version=int(
                    document.get("format_version", REVIEW_SCHEMA_FORMAT_VERSION)
                ),
            )["findings"]
        )
    if kind != "pipeline":
        return _error("file.kind", "Unsupported portable file kind.", "portable-kind")

    def resolve_coordinate(coordinate: ReviewSchemaCoordinate) -> str | None:
        if conn is None:
            return None
        row = conn.execute(
            """
            SELECT v.id, v.content_hash
            FROM review_schema_versions v
            JOIN review_schema_templates t ON t.id = v.schema_template_id
            WHERE t.schema_key = ? AND v.version_number = ?
            """,
            (coordinate.key, coordinate.version_number),
        ).fetchone()
        if row is None or row["content_hash"] != coordinate.content_hash:
            return None
        return str(row["id"])

    try:
        definition, _ = import_pipeline_bundle(
            document,
            resolve_coordinate=resolve_coordinate if conn is not None else None,
        )
    except ValueError as exc:
        return _error(
            "pipeline_file",
            str(exc),
            "portable-pipeline-invalid",
        )
    dependencies: dict[str, dict[str, Any]] = {}
    tasks = definition.get("tasks", {})
    if isinstance(tasks, dict):
        for task_key, task in tasks.items():
            params = task.get("params") if isinstance(task, dict) else None
            version_id = (
                params.get("schema_version_id")
                if isinstance(params, dict)
                else None
            )
            if isinstance(version_id, str):
                dependencies[str(task_key)] = {"id": version_id}
    findings = facade.validate_pipeline(
        definition,
        source=ValidationSource("pipeline_file", key=path.stem),
        schema_dependencies=dependencies,
    )["findings"]
    return _from_findings(findings)


def portable_contract_schema(kind: str) -> dict[str, Any]:
    """Return deterministic machine-readable schemas for CLI automation."""
    if kind == "runtime":
        from .schema import load_config_schema

        return load_config_schema()
    if kind == "review-schema":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": True,
            "properties": {
                "kind": {"enum": ["review-schema", "review-schema-draft"]},
                "format_version": {"const": REVIEW_SCHEMA_FORMAT_VERSION},
                "schema_key": {"type": "string"},
                "schema": {"type": "object"},
            },
            "required": ["kind", "format_version", "schema_key", "schema"],
            "title": "Portable review schema",
            "type": "object",
        }
    pipeline_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {
            "kind": {"const": "pipeline-bundle"},
            "format_version": {
                "const": PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION
            },
            "template": {"type": "object"},
            "definition": {
                "type": "object",
                "properties": {
                    "schema_version": {
                        "const": PIPELINE_DEFINITION_SCHEMA_VERSION
                    },
                    "pipeline": {"type": "array", "items": {"type": "string"}},
                    "tasks": {"type": "object"},
                },
                "required": ["schema_version", "pipeline", "tasks"],
            },
            "dependencies": {"type": "object"},
        },
        "required": [
            "kind",
            "format_version",
            "template",
            "definition",
            "dependencies",
        ],
        "title": "Portable pipeline bundle",
        "type": "object",
    }
    if kind in {"pipeline", "pipeline-bundle"}:
        return pipeline_schema
    raise ValueError("Unsupported schema kind.")


def _json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Stored configuration content must be an object.")
    return parsed


def _from_findings(findings: Any) -> ValidationResult:
    result = ValidationResult()
    for finding in findings or []:
        message = ValidationMessage(
            path=str(finding.get("path") or "$"),
            message=str(finding.get("message") or "Invalid configuration."),
            code=str(finding.get("code") or "validation"),
        )
        if finding.get("severity") == "warning":
            result.warnings.append(message)
        else:
            result.errors.append(message)
    return result


def _error(path: str, message: str, code: str) -> ValidationResult:
    return ValidationResult(
        errors=[ValidationMessage(path=path, message=message, code=code)]
    )


def _merge(target: ValidationResult, source: ValidationResult) -> None:
    target.errors.extend(source.errors)
    target.warnings.extend(source.warnings)


def _secret_references(
    value: Any, path: str = "$"
) -> list[tuple[str, str]]:
    if (
        isinstance(value, dict)
        and set(value) == {"$secret"}
        and isinstance(value["$secret"], str)
    ):
        return [(path, value["$secret"])]
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(_secret_references(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_secret_references(item, f"{path}[{index}]"))
    return found
