"""Legacy YAML and review-schema cutover into immutable SQLite versions."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import logging
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping

import yaml

from modules.config_protocol import ConfigProvider
from modules.db.connection import json_dumps, json_loads, utc_now
from modules.services.pipeline_template_service import (
    PipelineTemplateConflictError,
    PipelineTemplateService,
)
from modules.services.review_schema_version_service import (
    ReviewSchemaVersionService,
)
from modules.services.schema_service import SCHEMA_SUFFIXES, SchemaService
from modules.services.validation_facade import ValidationFacade
from modules.services.versioned_config_contracts import (
    PIPELINE_DEFINITION_SCHEMA_VERSION,
    ValidationSource,
    canonicalize_json,
    content_hash,
    is_secret_key,
    is_secret_reference,
)


logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_KEY = "default-processing"
TERMINAL_MIGRATION_STATUSES = {
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
}


class LegacyVersionedConfigMigrationError(RuntimeError):
    """Raised when legacy state cannot be pinned without changing its meaning."""


def _safe_failure(message: str) -> LegacyVersionedConfigMigrationError:
    return LegacyVersionedConfigMigrationError(
        f"{message} Finish or cancel legacy work, restore the matching legacy "
        "configuration, or re-ingest it under an explicit pipeline version."
    )


def _terminal_status(value: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip(
        "_"
    )
    aliases = {
        "pipeline_completed_successfully": "completed",
        "pipeline_completed_with_errors": "completed_with_errors",
        "completed_with_error": "completed_with_errors",
    }
    return aliases.get(normalized, normalized) in TERMINAL_MIGRATION_STATUSES


def _slug(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug or not slug[0].isalpha():
        slug = f"{fallback}-{slug}" if slug else fallback
    return slug


def _canonical_path(path: Path) -> tuple[Path, str]:
    resolved = path.expanduser().resolve(strict=True)
    return resolved, os.path.normcase(str(resolved))


def _load_schema_file(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        import json

        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Review schema root must be an object.")
    return canonicalize_json(value)


def _raw_config(config: ConfigProvider) -> dict[str, Any]:
    config_path = getattr(config, "_config_path", None)
    path = Path(config_path) if config_path else None
    if path is not None and path.is_file():
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise LegacyVersionedConfigMigrationError(
                "Runtime configuration root must be an object."
            )
        return value
    get_all = getattr(config, "get_all", None)
    if callable(get_all):
        value = get_all()
        if isinstance(value, dict):
            return deepcopy(value)
    pipeline = config.get("pipeline")
    tasks = config.get("tasks")
    result: dict[str, Any] = {}
    if pipeline is not None:
        result["pipeline"] = deepcopy(pipeline)
    if tasks is not None:
        result["tasks"] = deepcopy(tasks)
    secrets = config.get("pipeline_secrets")
    if secrets is not None:
        result["pipeline_secrets"] = deepcopy(secrets)
    return result


def _write_atomic(path: Path, data: bytes, mode: int | None) -> None:
    """Atomically replace one file through a same-directory temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


class LegacyVersionedConfigMigration:
    """Perform the version-3 data cutover inside the caller's transaction."""

    def __init__(self, conn, config: ConfigProvider) -> None:
        self.conn = conn
        self.config = config
        self.validation = ValidationFacade(config)
        self.schema_service = SchemaService(config)
        self.original_config = _raw_config(config)
        self.updated_config = deepcopy(self.original_config)
        self.config_path = (
            Path(getattr(config, "_config_path")).resolve()
            if getattr(config, "_config_path", None)
            else None
        )
        self.original_bytes: bytes | None = None
        self.original_mode: int | None = None
        self.config_replaced = False
        self.schema_sources: dict[str, dict[str, Any]] = {}
        self.skipped_schema_files: list[str] = []

    def run(self) -> dict[str, Any]:
        """Import legacy definitions, gate state, backfill, and update YAML."""
        config_versions_before = self._config_versions_fingerprint()
        definition = self._legacy_definition()
        referenced_paths = self._referenced_schema_paths(definition)
        self._import_schemas(referenced_paths)
        definition = self._transform_definition(definition)

        pipeline: dict[str, Any] | None = None
        if definition is not None:
            pipeline = self._ensure_default_pipeline(definition)
        elif self._has_unassigned_work():
            raise _safe_failure(
                "Legacy work exists but the active pipeline definition is missing."
            )

        if pipeline is not None:
            self._gate_and_backfill(pipeline)
        self._verify_invariants()
        if config_versions_before != self._config_versions_fingerprint():
            raise LegacyVersionedConfigMigrationError(
                "Legacy configuration history changed during migration."
            )
        self._replace_config_if_needed()
        self.conn.execute(
            """
            INSERT INTO audit_events(
                id, user, event_type, event_json, created_at
            ) VALUES (lower(hex(randomblob(16))), NULL, ?, ?, ?)
            """,
            (
                "versioned_config.legacy_migration.completed",
                json_dumps(
                    {
                        "pipeline_version_id": (
                            pipeline["version_id"] if pipeline else None
                        ),
                        "imported_schema_count": len(self.schema_sources),
                        "skipped_schema_files": self.skipped_schema_files,
                    }
                ),
                utc_now(),
            ),
        )
        return {
            "pipeline": pipeline,
            "schema_count": len(self.schema_sources),
            "skipped_schema_files": list(self.skipped_schema_files),
        }

    def compensate_config(self) -> None:
        """Restore the original YAML after a database/config coordination failure."""
        if (
            not self.config_replaced
            or self.config_path is None
            or self.original_bytes is None
        ):
            return
        try:
            _write_atomic(
                self.config_path, self.original_bytes, self.original_mode
            )
            self.config_replaced = False
        except OSError as exc:
            raise LegacyVersionedConfigMigrationError(
                "Configuration compensation failed; startup remains blocked."
            ) from exc

    def apply_runtime_config(self) -> None:
        """Refresh the current provider only after DB and YAML commit succeed."""
        if hasattr(self.config, "config") and isinstance(
            getattr(self.config, "config"), dict
        ):
            runtime = getattr(self.config, "config")
            for key in ("pipeline", "tasks", "pipeline_secrets"):
                if key in self.updated_config:
                    runtime[key] = deepcopy(self.updated_config[key])
        values = getattr(self.config, "_values", None)
        if isinstance(values, dict):
            for key in ("pipeline", "tasks", "pipeline_secrets"):
                if key in self.updated_config:
                    values[key] = deepcopy(self.updated_config[key])

    def _legacy_definition(self) -> dict[str, Any] | None:
        pipeline = self.original_config.get("pipeline")
        tasks = self.original_config.get("tasks")
        if pipeline in (None, []):
            return None
        if not isinstance(pipeline, list) or not isinstance(tasks, dict):
            raise LegacyVersionedConfigMigrationError(
                "Legacy pipeline and tasks must be a list and object."
            )
        normalized_pipeline: list[str] = []
        for item in pipeline:
            if not isinstance(item, str) or not item.strip():
                raise LegacyVersionedConfigMigrationError(
                    "Legacy pipeline contains an invalid task key."
                )
            normalized_pipeline.append(item.strip())
        normalized_tasks = {
            str(key).strip(): canonicalize_json(value)
            for key, value in tasks.items()
            if isinstance(key, str) and isinstance(value, dict)
        }
        if any(key not in normalized_tasks for key in normalized_pipeline):
            raise LegacyVersionedConfigMigrationError(
                "Legacy pipeline references a missing task definition."
            )
        return {
            "schema_version": PIPELINE_DEFINITION_SCHEMA_VERSION,
            "pipeline": normalized_pipeline,
            "tasks": normalized_tasks,
        }

    def _referenced_schema_paths(
        self, definition: dict[str, Any] | None
    ) -> set[str]:
        if definition is None:
            return set()
        referenced: set[str] = set()
        for task_key in definition["pipeline"]:
            task = definition["tasks"][task_key]
            if task.get("class") != "ReviewGateTask":
                continue
            params = task.get("params")
            schema_file = params.get("schema_file") if isinstance(params, dict) else None
            schema_version_id = (
                params.get("schema_version_id") if isinstance(params, dict) else None
            )
            if not schema_file and isinstance(schema_version_id, str):
                row = self.conn.execute(
                    "SELECT 1 FROM review_schema_versions WHERE id = ?",
                    (schema_version_id,),
                ).fetchone()
                if row is None:
                    raise _safe_failure(
                        "An active review task references a missing schema version."
                    )
                continue
            if not isinstance(schema_file, str) or not schema_file.strip():
                raise _safe_failure(
                    "An active review task has no legacy schema file."
                )
            try:
                path = self.schema_service._resolve_schema_path(schema_file)
            except (OSError, ValueError):
                path = None
            if path is None or not path.is_file():
                raise _safe_failure(
                    "An active review task references a missing schema file."
                )
            _, key = _canonical_path(path)
            referenced.add(key)
        return referenced

    def _discover_schema_files(self) -> list[tuple[str, Path]]:
        discovered: dict[str, Path] = {}
        for directory in self.schema_service.schema_directories():
            if not directory.is_dir():
                continue
            try:
                candidates = sorted(
                    directory.iterdir(), key=lambda item: item.name.casefold()
                )
            except OSError:
                continue
            for path in candidates:
                if path.suffix.lower() not in SCHEMA_SUFFIXES or not path.is_file():
                    continue
                try:
                    resolved, key = _canonical_path(path)
                except OSError:
                    continue
                discovered.setdefault(key, resolved)
        return sorted(discovered.items(), key=lambda item: item[0])

    def _import_schemas(self, referenced_paths: set[str]) -> None:
        schema_service = ReviewSchemaVersionService(self.conn)
        used_keys = {
            str(row["schema_key"]).casefold()
            for row in self.conn.execute(
                "SELECT schema_key FROM review_schema_templates"
            ).fetchall()
        }
        base_occurrences: dict[str, int] = {}
        for path_key, path in self._discover_schema_files():
            is_referenced = path_key in referenced_paths
            try:
                schema = _load_schema_file(path)
                validation = self.validation.validate_review_schema(
                    schema,
                    source=ValidationSource("legacy_review_schema", key=path.name),
                )
                if not validation["valid"]:
                    raise ValueError("Schema validation failed.")
            except Exception as exc:
                if is_referenced:
                    raise _safe_failure(
                        "An active review task references an invalid schema file."
                    ) from exc
                self.skipped_schema_files.append(path.name)
                logger.warning(
                    "Skipped invalid unreferenced legacy schema: %s", path.name
                )
                continue

            base_key = _slug(path.stem, fallback="schema")
            occurrence = base_occurrences.get(base_key, 0) + 1
            base_occurrences[base_key] = occurrence
            key = base_key if occurrence == 1 else f"{base_key}-{occurrence}"
            suffix = occurrence + 1
            while key.casefold() in used_keys:
                existing = schema_service.templates.get_by_key(key)
                versions = (
                    schema_service.versions.list_for_owner(existing["id"])
                    if existing
                    else []
                )
                if (
                    existing
                    and len(versions) == 1
                    and versions[0]["content_hash"] == content_hash(schema)
                ):
                    break
                key = f"{base_key}-{suffix}"
                suffix += 1

            existing = schema_service.templates.get_by_key(key)
            if existing:
                versions = schema_service.versions.list_for_owner(existing["id"])
                if len(versions) != 1 or versions[0]["content_hash"] != content_hash(
                    schema
                ):
                    raise LegacyVersionedConfigMigrationError(
                        "A partial schema import conflicts with legacy content."
                    )
                version = schema_service.load_version(versions[0]["id"])
                draft = schema_service.drafts.get(existing["id"])
                if (
                    draft is None
                    or draft["base_version_id"] != version["id"]
                    or draft["content_hash"] != version["content_hash"]
                ):
                    raise LegacyVersionedConfigMigrationError(
                        "A partial schema import has an inconsistent draft."
                    )
                template = existing
            else:
                created = schema_service.create_template(
                    schema_key=key,
                    name=str(schema.get("title") or path.stem),
                    description=str(schema.get("description") or ""),
                    initial_schema=schema,
                    user=None,
                )
                published = schema_service.publish(
                    created["template"]["id"], expected_revision=1, user=None
                )
                template = created["template"]
                version = published["version"]
                used_keys.add(key.casefold())
            if is_referenced and template["status"] != "active":
                template = schema_service.update_template(
                    template["id"], status="active", user=None
                )
            self.schema_sources[path_key] = {
                "path": path,
                "template": template,
                "version": version,
                "legacy_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
            }

        missing = referenced_paths - set(self.schema_sources)
        if missing:
            raise _safe_failure(
                "An active review task schema could not be imported."
            )

    def _transform_definition(
        self, definition: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if definition is None:
            return None
        transformed = deepcopy(definition)
        for task_key in transformed["pipeline"]:
            task = transformed["tasks"][task_key]
            if task.get("class") != "ReviewGateTask":
                continue
            params = task.setdefault("params", {})
            schema_file = params.pop("schema_file", None)
            if schema_file is None and isinstance(
                params.get("schema_version_id"), str
            ):
                continue
            path = self.schema_service._resolve_schema_path(str(schema_file))
            if path is None:
                raise _safe_failure("A review schema dependency is missing.")
            _, path_key = _canonical_path(path)
            params["schema_version_id"] = self.schema_sources[path_key]["version"]["id"]

        raw_secrets = self.updated_config.get("pipeline_secrets")
        secrets: dict[str, Any] = (
            deepcopy(raw_secrets) if isinstance(raw_secrets, dict) else {}
        )
        transformed["tasks"] = self._extract_task_secrets(
            transformed["tasks"], secrets
        )
        self.updated_config["pipeline"] = deepcopy(transformed["pipeline"])
        self.updated_config["tasks"] = deepcopy(transformed["tasks"])
        self.updated_config["pipeline_secrets"] = secrets
        return canonicalize_json(transformed)

    def _extract_task_secrets(
        self, tasks: dict[str, Any], secrets: dict[str, Any]
    ) -> dict[str, Any]:
        def visit(value: Any, *, task_key: str, path: list[str]) -> Any:
            if isinstance(value, dict):
                result: dict[str, Any] = {}
                for key, item in value.items():
                    if is_secret_key(str(key)):
                        if is_secret_reference(item):
                            alias = str(item["$secret"])
                            if alias not in secrets:
                                raise LegacyVersionedConfigMigrationError(
                                    "A legacy secret reference has no deployment value."
                                )
                            result[str(key)] = {"$secret": alias}
                        else:
                            alias_base = _slug(
                                "-".join(
                                    [DEFAULT_TEMPLATE_KEY, task_key, *path, str(key)]
                                ),
                                fallback="pipeline-secret",
                            )
                            alias = alias_base
                            suffix = 2
                            while alias in secrets and secrets[alias] != item:
                                alias = f"{alias_base}-{suffix}"
                                suffix += 1
                            secrets.setdefault(alias, deepcopy(item))
                            result[str(key)] = {"$secret": alias}
                    else:
                        result[str(key)] = visit(
                            item,
                            task_key=task_key,
                            path=[*path, str(key)],
                        )
                return result
            if isinstance(value, list):
                return [
                    visit(item, task_key=task_key, path=[*path, str(index)])
                    for index, item in enumerate(value)
                ]
            return deepcopy(value)

        return {
            key: visit(value, task_key=key, path=[])
            for key, value in tasks.items()
        }

    def _ensure_default_pipeline(self, definition: dict[str, Any]) -> dict[str, Any]:
        service = PipelineTemplateService(
            self.conn,
            configured_secret_aliases=set(
                (self.updated_config.get("pipeline_secrets") or {}).keys()
            ),
        )
        expected_hash = content_hash(definition)
        template = service.templates.get_by_key(DEFAULT_TEMPLATE_KEY)
        if template is None:
            created = service.create_template(
                template_key=DEFAULT_TEMPLATE_KEY,
                name="Default Processing",
                operator_selectable=True,
                initial_definition=definition,
                user=None,
            )
            published = service.publish(
                created["template"]["id"], expected_revision=1, user=None
            )
            template = created["template"]
            version = published["version"]
        else:
            versions = service.versions.list_for_owner(template["id"])
            draft = service.drafts.get(template["id"])
            if versions:
                if len(versions) != 1 or versions[0]["content_hash"] != expected_hash:
                    raise LegacyVersionedConfigMigrationError(
                        "The partial default pipeline import conflicts with active YAML."
                    )
                version = service.load_version(versions[0]["id"])
                if (
                    draft is None
                    or draft["base_version_id"] != version["id"]
                    or draft["content_hash"] != expected_hash
                ):
                    raise LegacyVersionedConfigMigrationError(
                        "The partial default pipeline draft is inconsistent."
                    )
            else:
                if draft is None or draft["content_hash"] != expected_hash:
                    raise LegacyVersionedConfigMigrationError(
                        "The partial default pipeline draft conflicts with active YAML."
                    )
                version = service.publish(
                    template["id"],
                    expected_revision=int(draft["revision"]),
                    user=None,
                )["version"]
        if template["status"] != "active":
            try:
                template = service.update_template(
                    template["id"], status="active", user=None
                )
            except PipelineTemplateConflictError as exc:
                raise LegacyVersionedConfigMigrationError(
                    "The default pipeline template cannot be activated."
                ) from exc
        return {
            "template_id": template["id"],
            "version_id": version["id"],
            "content_hash": version["content_hash"],
            "display_snapshot": version["display_snapshot"],
            "definition": definition,
        }

    def _gate_and_backfill(self, pipeline: dict[str, Any]) -> None:
        batches = [
            dict(row)
            for row in self.conn.execute("SELECT * FROM batches ORDER BY created_at")
        ]
        dependency_rows = self.conn.execute(
            """
            SELECT task_key, schema_version_id
            FROM pipeline_version_schema_dependencies
            WHERE pipeline_version_id = ?
            """,
            (pipeline["version_id"],),
        ).fetchall()
        dependencies = {row["task_key"]: row["schema_version_id"] for row in dependency_rows}
        expected_signature = self._snapshot_signature(pipeline["display_snapshot"])

        for batch in batches:
            if batch.get("pipeline_version_id"):
                continue
            terminal = _terminal_status(batch["status"])
            metadata = json_loads(batch.get("metadata_json"), {})
            metadata = metadata if isinstance(metadata, dict) else {}
            if not terminal:
                snapshot = metadata.get("pipeline_snapshot")
                if not self._valid_legacy_snapshot(snapshot, expected_signature):
                    raise _safe_failure(
                        "A non-terminal legacy batch has a missing or mismatched pipeline snapshot."
                    )
            self._verify_task_run_schema_hashes(
                batch_id=str(batch["id"]),
                terminal=terminal,
                dependencies=dependencies,
            )
            metadata["pipeline_migration"] = {
                "source": "legacy_migration",
                "reproducibility": (
                    "display_snapshot_matched" if not terminal else "migration_derived"
                ),
            }
            self.conn.execute(
                """
                UPDATE batches
                SET pipeline_template_id = ?, pipeline_version_id = ?,
                    pipeline_assignment_source = 'legacy_migration',
                    metadata_json = ?, updated_at = ?
                WHERE id = ? AND pipeline_version_id IS NULL
                """,
                (
                    pipeline["template_id"],
                    pipeline["version_id"],
                    json_dumps(metadata),
                    utc_now(),
                    batch["id"],
                ),
            )
            self.conn.execute(
                """
                UPDATE documents
                SET pipeline_template_id = ?, pipeline_version_id = ?, updated_at = ?
                WHERE batch_id = ? AND pipeline_version_id IS NULL
                """,
                (
                    pipeline["template_id"],
                    pipeline["version_id"],
                    utc_now(),
                    batch["id"],
                ),
            )
            self.conn.execute(
                """
                UPDATE task_runs SET pipeline_version_id = ?
                WHERE batch_id = ? AND pipeline_version_id IS NULL
                """,
                (pipeline["version_id"], batch["id"]),
            )
            self._backfill_review_items(
                batch_id=str(batch["id"]),
                terminal=terminal,
                dependencies=dependencies,
            )
            self.conn.execute(
                """
                INSERT INTO audit_events(
                    id, batch_id, user, event_type, event_json, created_at
                ) VALUES (lower(hex(randomblob(16))), ?, NULL, ?, ?, ?)
                """,
                (
                    batch["id"],
                    "ingestion.pipeline.legacy_migrated",
                    json_dumps(
                        {
                            "pipeline_template_id": pipeline["template_id"],
                            "pipeline_version_id": pipeline["version_id"],
                            "template_key": DEFAULT_TEMPLATE_KEY,
                            "assignment_source": "legacy_migration",
                            "provenance": (
                                "display_snapshot_matched"
                                if not terminal
                                else "migration_derived"
                            ),
                        }
                    ),
                    utc_now(),
                ),
            )

    def _verify_task_run_schema_hashes(
        self,
        *,
        batch_id: str,
        terminal: bool,
        dependencies: dict[str, str],
    ) -> None:
        if terminal:
            return
        rows = self.conn.execute(
            """
            SELECT task_key, output_json
            FROM task_runs
            WHERE batch_id = ? AND task_key IN (
                SELECT task_key
                FROM pipeline_version_schema_dependencies
                WHERE pipeline_version_id = (
                    SELECT pipeline_version_id
                    FROM batches WHERE id = ?
                )
            )
            """,
            (batch_id, batch_id),
        ).fetchall()
        # The batch assignment is still NULL at this point, so also inspect
        # review task keys from the pending migrated dependency map.
        if not rows:
            placeholders = ",".join("?" for _ in dependencies)
            if placeholders:
                rows = self.conn.execute(
                    f"""
                    SELECT task_key, output_json FROM task_runs
                    WHERE batch_id = ? AND task_key IN ({placeholders})
                    """,
                    (batch_id, *dependencies.keys()),
                ).fetchall()
        for row in rows:
            version_id = dependencies.get(str(row["task_key"]))
            source = next(
                (
                    value
                    for value in self.schema_sources.values()
                    if value["version"]["id"] == version_id
                ),
                None,
            )
            if source is None:
                continue
            output = json_loads(row["output_json"], {})
            recorded = self._find_schema_hashes(output)
            allowed = {
                source["legacy_hash"],
                source["version"]["content_hash"],
            }
            if any(value not in allowed for value in recorded):
                raise _safe_failure(
                    "A non-terminal review task schema hash does not match."
                )

    @classmethod
    def _find_schema_hashes(cls, value: Any) -> set[str]:
        if isinstance(value, dict):
            result: set[str] = set()
            for key, item in value.items():
                if key in {"schema_hash", "schema_version"} and isinstance(
                    item, str
                ):
                    result.add(item)
                else:
                    result.update(cls._find_schema_hashes(item))
            return result
        if isinstance(value, list):
            result: set[str] = set()
            for item in value:
                result.update(cls._find_schema_hashes(item))
            return result
        return set()

    def _backfill_review_items(
        self,
        *,
        batch_id: str,
        terminal: bool,
        dependencies: dict[str, str],
    ) -> None:
        rows = self.conn.execute(
            """
            SELECT r.*, tr.task_key
            FROM review_items r
            LEFT JOIN task_runs tr ON tr.id = r.created_by_task_run_id
            WHERE r.batch_id = ? AND r.review_schema_version_id IS NULL
            """,
            (batch_id,),
        ).fetchall()
        for raw in rows:
            item = dict(raw)
            metadata = json_loads(item.get("metadata_json"), {})
            metadata = metadata if isinstance(metadata, dict) else {}
            candidates: set[str] = set()
            task_key = item.get("task_key")
            if task_key in dependencies:
                candidates.add(dependencies[str(task_key)])
            schema_file = metadata.get("schema_file")
            if isinstance(schema_file, str):
                path = self.schema_service._resolve_schema_path(schema_file)
                if path is not None:
                    _, path_key = _canonical_path(path)
                    source = self.schema_sources.get(path_key)
                    if source:
                        candidates.add(source["version"]["id"])
            if not candidates and len(set(dependencies.values())) == 1:
                candidates = set(dependencies.values())
            if len(candidates) != 1:
                if not terminal:
                    raise _safe_failure(
                        "A non-terminal review item has an ambiguous schema dependency."
                    )
                continue
            version_id = next(iter(candidates))
            source = next(
                (
                    value
                    for value in self.schema_sources.values()
                    if value["version"]["id"] == version_id
                ),
                None,
            )
            recorded_hash = metadata.get("schema_hash") or metadata.get(
                "schema_version"
            )
            if recorded_hash and source and recorded_hash not in {
                source["legacy_hash"],
                source["version"]["content_hash"],
            }:
                if not terminal:
                    raise _safe_failure(
                        "A non-terminal review item schema hash does not match."
                    )
                continue
            if source:
                if recorded_hash:
                    metadata["legacy_schema_hash"] = recorded_hash
                metadata["schema_hash"] = source["version"]["content_hash"]
                metadata["schema_version"] = source["version"]["content_hash"]
                metadata["schema_version_id"] = version_id
            self.conn.execute(
                """
                UPDATE review_items
                SET review_schema_version_id = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (version_id, json_dumps(metadata), utc_now(), item["id"]),
            )

    @staticmethod
    def _snapshot_signature(snapshot: Mapping[str, Any]) -> list[tuple[Any, ...]]:
        steps = snapshot.get("steps")
        if not isinstance(steps, list):
            return []
        return [
            (
                item.get("key"),
                item.get("module"),
                item.get("class"),
                item.get("on_error"),
            )
            for item in steps
            if isinstance(item, dict)
        ]

    def _valid_legacy_snapshot(
        self, snapshot: Any, expected_signature: list[tuple[Any, ...]]
    ) -> bool:
        if not isinstance(snapshot, dict) or not isinstance(
            snapshot.get("content_hash"), str
        ):
            return False
        if self._snapshot_signature(snapshot) != expected_signature:
            return False
        steps = snapshot.get("steps")
        if not isinstance(steps, list):
            return False
        legacy_basis = "|".join(
            f"{step.get('position')}:{step.get('key')}:{step.get('module')}:"
            f"{step.get('class')}:{step.get('on_error') or ''}"
            for step in steps
            if isinstance(step, dict)
        )
        legacy_hash = hashlib.sha256(legacy_basis.encode("utf-8")).hexdigest()
        current_hash = content_hash(
            {
                "version": 1,
                "steps": [
                    {
                        "key": step.get("key"),
                        "label": step.get("label"),
                        "module": step.get("module"),
                        "class": step.get("class"),
                        "position": step.get("position"),
                        "on_error": step.get("on_error"),
                    }
                    for step in steps
                    if isinstance(step, dict)
                ],
            }
        )
        return snapshot["content_hash"] in {legacy_hash, current_hash}

    def _verify_invariants(self) -> None:
        if self.conn.execute(
            """
            SELECT 1 FROM documents d
            JOIN batches b ON b.id = d.batch_id
            WHERE d.pipeline_version_id IS NOT b.pipeline_version_id
               OR d.pipeline_template_id IS NOT b.pipeline_template_id
            LIMIT 1
            """
        ).fetchone():
            raise LegacyVersionedConfigMigrationError(
                "Batch and document pipeline assignments are inconsistent."
            )
        if self.conn.execute(
            """
            SELECT 1 FROM task_runs tr
            JOIN documents d ON d.id = tr.document_id
            WHERE tr.pipeline_version_id IS NOT d.pipeline_version_id
            LIMIT 1
            """
        ).fetchone():
            raise LegacyVersionedConfigMigrationError(
                "Task-run pipeline attribution is inconsistent."
            )
        if self.conn.execute(
            """
            SELECT 1 FROM documents child
            JOIN documents parent ON parent.id = child.parent_document_id
            WHERE child.pipeline_version_id IS NOT parent.pipeline_version_id
               OR child.pipeline_template_id IS NOT parent.pipeline_template_id
            LIMIT 1
            """
        ).fetchone():
            raise LegacyVersionedConfigMigrationError(
                "Split-child pipeline attribution is inconsistent."
            )
        if self.conn.execute(
            """
            SELECT 1
            FROM review_items r
            JOIN documents d ON d.id = r.document_id
            LEFT JOIN task_runs tr ON tr.id = r.created_by_task_run_id
            WHERE r.review_schema_version_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM pipeline_version_schema_dependencies dep
                  WHERE dep.pipeline_version_id = d.pipeline_version_id
                    AND dep.schema_version_id = r.review_schema_version_id
                    AND (tr.task_key IS NULL OR dep.task_key = tr.task_key)
              )
            LIMIT 1
            """
        ).fetchone():
            raise LegacyVersionedConfigMigrationError(
                "Review-item schema attribution is inconsistent."
            )
        violations = self.conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise LegacyVersionedConfigMigrationError(
                "Foreign-key verification failed during migration."
            )

    def _replace_config_if_needed(self) -> None:
        if self.config_path is None or not self.config_path.is_file():
            return
        new_bytes = yaml.safe_dump(
            self.updated_config, sort_keys=False, allow_unicode=True
        ).encode("utf-8")
        original = self.config_path.read_bytes()
        if new_bytes == original:
            return
        self.original_bytes = original
        self.original_mode = stat.S_IMODE(self.config_path.stat().st_mode)
        _write_atomic(self.config_path, new_bytes, self.original_mode)
        self.config_replaced = True

    def _has_unassigned_work(self) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM batches WHERE pipeline_version_id IS NULL LIMIT 1"
            ).fetchone()
            is not None
        )

    def _config_versions_fingerprint(self) -> list[tuple[Any, ...]]:
        columns = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(config_versions)")
        }
        if not columns:
            return []
        ordered = sorted(columns)
        rows = self.conn.execute(
            f"SELECT {', '.join(ordered)} FROM config_versions ORDER BY id"
        ).fetchall()
        return [tuple(row[column] for column in ordered) for row in rows]
