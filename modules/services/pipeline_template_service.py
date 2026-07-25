"""Lifecycle service for named, immutable pipeline template versions."""

from __future__ import annotations

import difflib
import json
from typing import Any, Mapping

from modules.db.connection import immediate_transaction, json_dumps, json_loads, transaction, utc_now
from modules.db.repositories import (
    AuditRepository,
    PipelineDraftRepository,
    PipelineSchemaDependencyRepository,
    PipelineTemplateRepository,
    PipelineVersionRepository,
)
from modules.services.validation_facade import ValidationFacade
from modules.services.versioned_config_contracts import (
    PIPELINE_DEFINITION_SCHEMA_VERSION,
    ValidationSource,
    build_display_snapshot,
    canonical_json_text,
    canonicalize_json,
    content_hash,
    is_secret_reference,
    normalize_key,
    redact_sensitive,
)


class PipelineTemplateConflictError(ValueError):
    """Raised when a pipeline draft or lifecycle precondition is stale."""

    def __init__(self, message: str, *, current: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.current = current


class PipelineTemplateValidationError(ValueError):
    """Raised when an invalid pipeline draft is published."""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__("Pipeline validation failed.")
        self.result = result


class PipelineTemplateService:
    """Coordinate pipeline templates, exact dependencies, and publication."""

    def __init__(
        self,
        conn,
        *,
        validation: ValidationFacade | None = None,
        configured_secret_aliases: set[str] | None = None,
    ) -> None:
        self.conn = conn
        self.templates = PipelineTemplateRepository(conn)
        self.drafts = PipelineDraftRepository(conn)
        self.versions = PipelineVersionRepository(conn)
        self.dependencies = PipelineSchemaDependencyRepository(conn)
        self.audit = AuditRepository(conn)
        self.validation = validation or ValidationFacade()
        self.configured_secret_aliases = configured_secret_aliases or set()

    def create_template(
        self,
        *,
        template_key: str,
        name: str,
        description: str = "",
        document_type: str | None = None,
        operator_instructions: str = "",
        operator_selectable: bool = True,
        initial_definition: Mapping[str, Any] | None = None,
        user: str | None,
    ) -> dict[str, Any]:
        key = normalize_key(template_key, label="template key")
        definition = canonicalize_json(
            dict(
                initial_definition
                or {
                    "schema_version": PIPELINE_DEFINITION_SCHEMA_VERSION,
                    "pipeline": [],
                    "tasks": {},
                }
            )
        )
        encoded = canonical_json_text(definition)
        with immediate_transaction(self.conn):
            template = self.templates.create(
                template_key=key,
                name=name.strip() or key,
                description=description,
                document_type=document_type,
                operator_instructions=operator_instructions,
                status="inactive",
                operator_selectable=operator_selectable,
                user=user,
            )
            draft = self.drafts.create(
                template_id=template["id"],
                definition_json=encoded,
                content_hash=content_hash(definition),
                user=user,
            )
            self._audit(
                "pipeline.template.created",
                template,
                user=user,
                extra={"operator_selectable": operator_selectable},
            )
        return {"template": template, "draft": self._decode_draft(draft)}

    def save_draft(
        self,
        template_id: str,
        *,
        expected_revision: int,
        definition: Mapping[str, Any],
        user: str | None,
    ) -> dict[str, Any]:
        normalized = canonicalize_json(dict(definition))
        with transaction(self.conn):
            draft = self.drafts.update_if_revision(
                template_id=template_id,
                expected_revision=expected_revision,
                definition_json=canonical_json_text(normalized),
                content_hash=content_hash(normalized),
                user=user,
            )
            if draft is None:
                raise PipelineTemplateConflictError(
                    "Draft revision is stale; reload before saving.",
                    current=self._decode_draft(self._require_draft(template_id)),
                )
            template = self._require_template(template_id)
            self._audit(
                "pipeline.draft.saved",
                template,
                user=user,
                extra={"revision": draft["revision"], "content_hash": draft["content_hash"]},
            )
        return self._decode_draft(draft)

    def validate_draft(
        self, template_id: str, *, user: str | None = None
    ) -> dict[str, Any]:
        template = self._require_template(template_id)
        draft = self._require_draft(template_id)
        definition = json_loads(draft["definition_json"], {})
        resolved = self._resolve_dependencies(definition, require_active=True)
        result = self.validation.validate_pipeline(
            definition,
            source=ValidationSource(
                "pipeline_draft",
                key=template["template_key"],
                revision=draft["revision"],
            ),
            schema_dependencies=resolved,
        )
        self._append_dependency_findings(result, definition, resolved)
        self._append_secret_findings(result, definition)
        self.audit.append(
            event_type="pipeline.draft.validated",
            event={
                "template_id": template_id,
                "template_key": template["template_key"],
                "revision": draft["revision"],
                "valid": result["valid"],
                "finding_count": len(result["findings"]),
            },
            user=user,
        )
        return result

    def import_draft(
        self,
        template_id: str,
        *,
        expected_revision: int,
        definition: Mapping[str, Any],
        user: str | None,
    ) -> dict[str, Any]:
        """Save already-parsed portable content as a draft without publishing."""
        draft = self.save_draft(
            template_id,
            expected_revision=expected_revision,
            definition=definition,
            user=user,
        )
        template = self._require_template(template_id)
        self.audit.append(
            event_type="pipeline.draft.imported",
            event={
                "template_id": template_id,
                "template_key": template["template_key"],
                "revision": draft["revision"],
                "content_hash": draft["content_hash"],
            },
            user=user,
        )
        return draft

    def publish(
        self,
        template_id: str,
        *,
        expected_revision: int,
        user: str | None,
    ) -> dict[str, Any]:
        template = self._require_template(template_id)
        initial_draft = self._require_draft(template_id)
        definition = json_loads(initial_draft["definition_json"], {})
        dependencies = self._resolve_dependencies(definition, require_active=True)
        validation = self.validation.validate_pipeline(
            definition,
            source=ValidationSource(
                "pipeline_draft",
                key=template["template_key"],
                revision=initial_draft["revision"],
            ),
            schema_dependencies=dependencies,
        )
        self._append_dependency_findings(validation, definition, dependencies)
        self._append_secret_findings(validation, definition)
        if not validation["valid"]:
            raise PipelineTemplateValidationError(validation)

        with immediate_transaction(self.conn):
            template = self._require_template(template_id)
            if template["status"] == "archived":
                raise PipelineTemplateConflictError(
                    "Archived templates cannot be published."
                )
            draft = self._require_draft(template_id)
            if (
                int(draft["revision"]) != expected_revision
                or draft["content_hash"] != initial_draft["content_hash"]
            ):
                raise PipelineTemplateConflictError(
                    "Draft revision is stale; reload before publishing.",
                    current=self._decode_draft(draft),
                )
            dependencies = self._resolve_dependencies(definition, require_active=True)
            validation = self.validation.validate_pipeline(
                definition,
                source=ValidationSource(
                    "pipeline_draft",
                    key=template["template_key"],
                    revision=draft["revision"],
                ),
                schema_dependencies=dependencies,
            )
            self._append_dependency_findings(validation, definition, dependencies)
            self._append_secret_findings(validation, definition)
            if not validation["valid"]:
                raise PipelineTemplateValidationError(validation)
            if draft["base_version_id"]:
                base = self.versions.get(draft["base_version_id"])
                if base and base["content_hash"] == draft["content_hash"]:
                    raise PipelineTemplateConflictError(
                        "Draft has no changes from its published base."
                    )
            version = self.versions.create(
                template_id=template_id,
                version_number=self.versions.next_version_number(template_id),
                schema_version=PIPELINE_DEFINITION_SCHEMA_VERSION,
                definition_json=draft["definition_json"],
                content_hash=draft["content_hash"],
                display_snapshot_json=canonical_json_text(
                    build_display_snapshot(definition)
                ),
                validation_summary_json=json_dumps(validation),
                user=user,
            )
            for task_key, schema_version in dependencies.items():
                self.dependencies.create(
                    pipeline_version_id=version["id"],
                    task_key=task_key,
                    schema_version_id=schema_version["id"],
                )
            updated_draft = self.drafts.reset_to_version(
                template_id=template_id,
                version_id=version["id"],
                definition_json=draft["definition_json"],
                content_hash=draft["content_hash"],
                user=user,
            )
            self._audit(
                "pipeline.version.published",
                template,
                user=user,
                extra={
                    "version_id": version["id"],
                    "version_number": version["version_number"],
                    "content_hash": version["content_hash"],
                    "dependency_count": len(dependencies),
                },
            )
        return {
            "version": self.load_version(version["id"]),
            "draft": self._decode_draft(updated_draft),
        }

    def update_template(
        self,
        template_id: str,
        *,
        template_key: str | None = None,
        name: str | None = None,
        description: str | None = None,
        document_type: str | None = None,
        operator_instructions: str | None = None,
        operator_selectable: bool | None = None,
        status: str | None = None,
        user: str | None,
    ) -> dict[str, Any]:
        with immediate_transaction(self.conn):
            current = self._require_template(template_id)
            target_status = status or current["status"]
            if target_status not in {"active", "inactive", "archived"}:
                raise ValueError("Unsupported pipeline template status.")
            if current["status"] == "archived" and target_status != "archived":
                raise PipelineTemplateConflictError(
                    "Archived templates cannot be restored."
                )
            if target_status == "active" and not self.versions.list_for_owner(template_id):
                raise PipelineTemplateConflictError(
                    "A template must have a published version before activation."
                )
            if target_status == "archived":
                if current["status"] != "inactive":
                    raise PipelineTemplateConflictError(
                        "Only inactive templates can be archived."
                    )
                binding = self.conn.execute(
                    """
                    SELECT 1 FROM watch_folder_bindings
                    WHERE pipeline_template_id = ? AND enabled = 1 LIMIT 1
                    """,
                    (template_id,),
                ).fetchone()
                if binding:
                    raise PipelineTemplateConflictError(
                        "Disable watch-folder bindings before archiving."
                    )
            updated = self.templates.update(
                template_id,
                template_key=normalize_key(
                    template_key or current["template_key"], label="template key"
                ),
                name=(name if name is not None else current["name"]).strip(),
                description=(
                    description if description is not None else current["description"]
                ),
                document_type=(
                    document_type
                    if document_type is not None
                    else current["document_type"]
                ),
                operator_instructions=(
                    operator_instructions
                    if operator_instructions is not None
                    else current["operator_instructions"]
                ),
                operator_selectable=(
                    operator_selectable
                    if operator_selectable is not None
                    else bool(current["operator_selectable"])
                ),
                status=target_status,
                updated_by=user,
                archived_at=utc_now() if target_status == "archived" else None,
            )
            self._audit(
                "pipeline.template.updated",
                updated,
                user=user,
                extra={
                    "before_status": current["status"],
                    "after_status": target_status,
                },
            )
        return updated

    def list_operator_selectable(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT t.*, v.id AS pipeline_version_id, v.version_number,
                   v.content_hash
            FROM pipeline_templates t
            JOIN pipeline_versions v ON v.template_id = t.id
            WHERE t.status = 'active' AND t.operator_selectable = 1
            ORDER BY t.name, t.template_key, v.version_number DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def clone(
        self,
        source_template_id: str,
        *,
        template_key: str,
        name: str,
        user: str | None,
    ) -> dict[str, Any]:
        source = self._require_template(source_template_id)
        versions = self.versions.list_for_owner(source_template_id)
        if not versions:
            raise PipelineTemplateConflictError(
                "Only a published template can be cloned."
            )
        definition = json_loads(versions[0]["definition_json"], {})
        created = self.create_template(
            template_key=template_key,
            name=name,
            description=source["description"],
            document_type=source["document_type"],
            operator_instructions=source["operator_instructions"],
            operator_selectable=bool(source["operator_selectable"]),
            initial_definition=definition,
            user=user,
        )
        self.audit.append(
            event_type="pipeline.template.cloned",
            event={
                "source_template_id": source_template_id,
                "source_version_id": versions[0]["id"],
                "target_template_id": created["template"]["id"],
                "target_template_key": created["template"]["template_key"],
            },
            user=user,
        )
        return created

    def diff(self, template_id: str, *, version_id: str | None = None) -> dict[str, Any]:
        template = self._require_template(template_id)
        draft = self._require_draft(template_id)
        target_id = version_id or draft["base_version_id"]
        before: dict[str, Any] = {}
        if target_id:
            version = self.versions.get(target_id)
            if version is None or version["template_id"] != template_id:
                raise KeyError(f"Unknown pipeline version: {target_id}")
            before = json_loads(version["definition_json"], {})
        after = json_loads(draft["definition_json"], {})
        before_lines = json.dumps(
            redact_sensitive(before), indent=2, sort_keys=True
        ).splitlines()
        after_lines = json.dumps(
            redact_sensitive(after), indent=2, sort_keys=True
        ).splitlines()
        text = "\n".join(
            difflib.unified_diff(
                before_lines, after_lines, fromfile="published", tofile="draft"
            )
        )
        self.audit.append(
            event_type="pipeline.diff.viewed",
            event={"template_id": template_id, "template_key": template["template_key"]},
        )
        return {"changed": before_lines != after_lines, "text": text}

    def load_version(self, version_id: str) -> dict[str, Any]:
        version = self.versions.get(version_id)
        if version is None:
            raise KeyError(f"Unknown pipeline version: {version_id}")
        definition = json_loads(version["definition_json"], {})
        if content_hash(definition) != version["content_hash"]:
            raise RuntimeError("Published pipeline content hash mismatch.")
        rows = self.dependencies.list_for_pipeline(version_id)
        expected = self._dependency_ids(definition)
        actual = {row["task_key"]: row["schema_version_id"] for row in rows}
        if actual != expected:
            raise RuntimeError(
                "Published pipeline definition and dependency rows disagree."
            )
        return {
            **version,
            "definition": definition,
            "display_snapshot": json_loads(version["display_snapshot_json"], {}),
            "validation_summary": json_loads(
                version["validation_summary_json"], {}
            ),
            "schema_dependencies": actual,
        }

    def export_version(self, version_id: str, *, user: str | None = None) -> str:
        version = self.load_version(version_id)
        safe = {
            "kind": "pipeline-version",
            "schema_version": version["schema_version"],
            "content_hash": version["content_hash"],
            "definition": redact_sensitive(version["definition"]),
        }
        self.audit.append(
            event_type="pipeline.version.exported",
            event={
                "version_id": version_id,
                "content_hash": version["content_hash"],
            },
            user=user,
        )
        return json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True)

    def _resolve_dependencies(
        self, definition: Mapping[str, Any], *, require_active: bool
    ) -> dict[str, dict[str, Any]]:
        resolved: dict[str, dict[str, Any]] = {}
        for task_key, schema_version_id in self._dependency_ids(definition).items():
            row = self.conn.execute(
                """
                SELECT v.*, t.status AS template_status, t.schema_key
                FROM review_schema_versions v
                JOIN review_schema_templates t ON t.id = v.schema_template_id
                WHERE v.id = ?
                """,
                (schema_version_id,),
            ).fetchone()
            if row is None:
                continue
            item = dict(row)
            schema = json_loads(item["schema_json"], {})
            if content_hash(schema) != item["content_hash"]:
                continue
            if require_active and item["template_status"] != "active":
                continue
            resolved[task_key] = item
        return resolved

    @staticmethod
    def _dependency_ids(definition: Mapping[str, Any]) -> dict[str, str]:
        result: dict[str, str] = {}
        tasks = definition.get("tasks")
        if not isinstance(tasks, dict):
            return result
        for task_key, task in tasks.items():
            if not isinstance(task, dict) or task.get("class") != "ReviewGateTask":
                continue
            params = task.get("params")
            if isinstance(params, dict) and isinstance(
                params.get("schema_version_id"), str
            ):
                result[str(task_key)] = params["schema_version_id"]
        return result

    @staticmethod
    def _append_dependency_findings(
        result: dict[str, Any],
        definition: Mapping[str, Any],
        resolved: Mapping[str, Mapping[str, Any]],
    ) -> None:
        expected = PipelineTemplateService._dependency_ids(definition)
        for task_key, version_id in expected.items():
            if task_key in resolved:
                continue
            result["findings"].append(
                {
                    "severity": "error",
                    "path": f"{result['source']}.tasks.{task_key}.params.schema_version_id",
                    "message": (
                        "Review schema version is missing, corrupt, or its template "
                        "is not active."
                    ),
                    "code": "pipeline-schema-dependency-ineligible",
                    "details": {"schema_version_id": version_id},
                }
            )
        extraction_fields: set[str] = set()
        tasks = definition.get("tasks")
        if isinstance(tasks, dict):
            for task in tasks.values():
                if not isinstance(task, dict) or task.get("class") != "ExtractPdfTask":
                    continue
                params = task.get("params")
                fields = params.get("fields") if isinstance(params, dict) else None
                if isinstance(fields, dict):
                    extraction_fields.update(str(key) for key in fields)
        for task_key, schema_version in resolved.items():
            schema = json_loads(str(schema_version.get("schema_json") or "{}"), {})
            fields = schema.get("fields") if isinstance(schema, dict) else None
            if not isinstance(fields, dict) or not extraction_fields:
                continue
            incompatible = sorted(set(str(key) for key in fields) - extraction_fields)
            if incompatible:
                result["findings"].append(
                    {
                        "severity": "error",
                        "path": f"{result['source']}.tasks.{task_key}.params.schema_version_id",
                        "message": (
                            "Review schema fields are not produced by an extraction "
                            f"task: {', '.join(incompatible)}"
                        ),
                        "code": "pipeline-schema-extraction-mismatch",
                        "details": {"fields": incompatible},
                    }
                )
        result["valid"] = not any(
            item.get("severity") == "error" for item in result["findings"]
        )

    def _append_secret_findings(
        self, result: dict[str, Any], definition: Mapping[str, Any]
    ) -> None:
        for path, alias in self._secret_references(definition):
            if alias in self.configured_secret_aliases:
                continue
            result["findings"].append(
                {
                    "severity": "error",
                    "path": f"{result['source']}.{path}",
                    "message": f"Secret alias is not configured: {alias}",
                    "code": "pipeline-secret-alias-unconfigured",
                    "details": {"alias": alias},
                }
            )
        result["valid"] = not any(
            item.get("severity") == "error" for item in result["findings"]
        )

    @staticmethod
    def _secret_references(
        value: Any, path: str = "$"
    ) -> list[tuple[str, str]]:
        if is_secret_reference(value):
            return [(path, value["$secret"])]
        found: list[tuple[str, str]] = []
        if isinstance(value, dict):
            for key, item in value.items():
                found.extend(
                    PipelineTemplateService._secret_references(
                        item, f"{path}.{key}"
                    )
                )
        elif isinstance(value, list):
            for index, item in enumerate(value):
                found.extend(
                    PipelineTemplateService._secret_references(
                        item, f"{path}[{index}]"
                    )
                )
        return found

    def _require_template(self, template_id: str) -> dict[str, Any]:
        template = self.templates.get(template_id)
        if template is None:
            raise KeyError(f"Unknown pipeline template: {template_id}")
        return template

    def _require_draft(self, template_id: str) -> dict[str, Any]:
        draft = self.drafts.get(template_id)
        if draft is None:
            raise KeyError(f"Pipeline draft is missing: {template_id}")
        return draft

    def _audit(
        self,
        event_type: str,
        template: Mapping[str, Any],
        *,
        user: str | None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        self.audit.append_uncommitted(
            event_type=event_type,
            event={
                "template_id": template["id"],
                "template_key": template["template_key"],
                "name": template["name"],
                **dict(extra or {}),
            },
            user=user,
        )

    @staticmethod
    def _decode_draft(row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "definition": json_loads(row["definition_json"], {})}
