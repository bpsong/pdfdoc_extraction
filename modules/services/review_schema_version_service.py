"""Lifecycle service for named, immutable review-schema versions."""

from __future__ import annotations

import json
from typing import Any, Mapping

import yaml

from modules.db.connection import immediate_transaction, json_dumps, json_loads, transaction, utc_now
from modules.db.repositories import (
    AuditRepository,
    ReviewSchemaDraftRepository,
    ReviewSchemaTemplateRepository,
    ReviewSchemaVersionRepository,
)
from modules.services.validation_facade import ValidationFacade
from modules.services.schema_service import SchemaService
from modules.services.versioned_config_contracts import (
    REVIEW_SCHEMA_FORMAT_VERSION,
    ValidationSource,
    canonical_json_text,
    canonicalize_json,
    content_hash,
    normalize_key,
)


class ReviewSchemaConflictError(ValueError):
    """Raised when a draft revision or lifecycle precondition is stale."""

    def __init__(self, message: str, *, current: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.current = current


class ReviewSchemaValidationError(ValueError):
    """Raised when an invalid schema is published."""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__("Review schema validation failed.")
        self.result = result


class _NullConfig:
    def get(self, key: str, default: Any = None) -> Any:
        return default


class ReviewSchemaVersionService:
    """Coordinate schema templates, drafts, publication, and audit history."""

    def __init__(self, conn, *, validation: ValidationFacade | None = None) -> None:
        self.conn = conn
        self.templates = ReviewSchemaTemplateRepository(conn)
        self.drafts = ReviewSchemaDraftRepository(conn)
        self.versions = ReviewSchemaVersionRepository(conn)
        self.audit = AuditRepository(conn)
        self.validation = validation or ValidationFacade()

    def create_template(
        self,
        *,
        schema_key: str,
        name: str,
        description: str = "",
        initial_schema: Mapping[str, Any] | None = None,
        user: str | None,
    ) -> dict[str, Any]:
        key = normalize_key(schema_key, label="schema key")
        schema = canonicalize_json(dict(initial_schema or {"fields": {}}))
        encoded = canonical_json_text(schema)
        with immediate_transaction(self.conn):
            template = self.templates.create(
                schema_key=key,
                name=name.strip() or key,
                description=description,
                status="inactive",
                user=user,
            )
            draft = self.drafts.create(
                template_id=template["id"],
                schema_json=encoded,
                content_hash=content_hash(schema),
                user=user,
            )
            self.audit.append_uncommitted(
                event_type="review_schema.template.created",
                event={"template_id": template["id"], "schema_key": key},
                user=user,
            )
        return {"template": template, "draft": self._decode_draft(draft)}

    def save_draft(
        self,
        template_id: str,
        *,
        expected_revision: int,
        schema: Mapping[str, Any],
        user: str | None,
    ) -> dict[str, Any]:
        normalized = canonicalize_json(dict(schema))
        with transaction(self.conn):
            draft = self.drafts.update_if_revision(
                template_id=template_id,
                expected_revision=expected_revision,
                schema_json=canonical_json_text(normalized),
                content_hash=content_hash(normalized),
                user=user,
            )
            if draft is None:
                raise ReviewSchemaConflictError(
                    "Draft revision is stale; reload before saving.",
                    current=self._decode_draft(self._require_draft(template_id)),
                )
            template = self._require_template(template_id)
            self.audit.append_uncommitted(
                event_type="review_schema.draft.saved",
                event={
                    "template_id": template_id,
                    "schema_key": template["schema_key"],
                    "revision": draft["revision"],
                    "content_hash": draft["content_hash"],
                },
                user=user,
            )
        return self._decode_draft(draft)

    def validate_draft(
        self, template_id: str, *, user: str | None = None
    ) -> dict[str, Any]:
        template = self._require_template(template_id)
        draft = self._require_draft(template_id)
        result = self.validation.validate_review_schema(
            json_loads(draft["schema_json"], {}),
            source=ValidationSource(
                "review_schema_draft",
                key=template["schema_key"],
                revision=draft["revision"],
            ),
        )
        self.audit.append(
            event_type="review_schema.draft.validated",
            event={
                "template_id": template_id,
                "schema_key": template["schema_key"],
                "revision": draft["revision"],
                "valid": result["valid"],
                "finding_count": len(result["findings"]),
            },
            user=user,
        )
        return result

    def publish(
        self,
        template_id: str,
        *,
        expected_revision: int,
        user: str | None,
    ) -> dict[str, Any]:
        with immediate_transaction(self.conn):
            template = self._require_template(template_id)
            if template["status"] == "archived":
                raise ReviewSchemaConflictError("Archived schemas cannot be published.")
            draft = self._require_draft(template_id)
            if int(draft["revision"]) != expected_revision:
                raise ReviewSchemaConflictError(
                    "Draft revision is stale; reload before publishing.",
                    current=self._decode_draft(draft),
                )
            schema = json_loads(draft["schema_json"], {})
            validation = self.validation.validate_review_schema(
                schema,
                source=ValidationSource(
                    "review_schema_draft",
                    key=template["schema_key"],
                    revision=draft["revision"],
                ),
            )
            if not validation["valid"]:
                raise ReviewSchemaValidationError(validation)
            if draft["base_version_id"]:
                base = self.versions.get(draft["base_version_id"])
                if base and base["content_hash"] == draft["content_hash"]:
                    raise ReviewSchemaConflictError(
                        "Draft has no changes from its published base."
                    )
            version = self.versions.create(
                template_id=template_id,
                version_number=self.versions.next_version_number(template_id),
                format_version=REVIEW_SCHEMA_FORMAT_VERSION,
                schema_json=draft["schema_json"],
                content_hash=draft["content_hash"],
                validation_summary_json=json_dumps(validation),
                user=user,
            )
            updated_draft = self.drafts.reset_to_version(
                template_id=template_id,
                version_id=version["id"],
                schema_json=draft["schema_json"],
                content_hash=draft["content_hash"],
                user=user,
            )
            self.audit.append_uncommitted(
                event_type="review_schema.version.published",
                event={
                    "template_id": template_id,
                    "version_id": version["id"],
                    "version_number": version["version_number"],
                    "content_hash": version["content_hash"],
                },
                user=user,
            )
        return {
            "version": self._decode_version(version),
            "draft": self._decode_draft(updated_draft),
        }

    def update_template(
        self,
        template_id: str,
        *,
        schema_key: str | None = None,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        user: str | None,
    ) -> dict[str, Any]:
        with immediate_transaction(self.conn):
            current = self._require_template(template_id)
            target_status = status or current["status"]
            if target_status not in {"active", "inactive", "archived"}:
                raise ValueError("Unsupported review schema status.")
            if current["status"] == "archived" and target_status != "archived":
                raise ReviewSchemaConflictError("Archived schemas cannot be restored.")
            if target_status == "active" and not self.versions.list_for_owner(template_id):
                raise ReviewSchemaConflictError(
                    "A schema must have a published version before activation."
                )
            if target_status == "archived" and current["status"] != "inactive":
                raise ReviewSchemaConflictError(
                    "Only inactive schemas can be archived."
                )
            updated = self.templates.update(
                template_id,
                schema_key=normalize_key(
                    schema_key or current["schema_key"], label="schema key"
                ),
                name=(name if name is not None else current["name"]).strip(),
                description=(
                    description if description is not None else current["description"]
                ),
                status=target_status,
                user=user,
                archived_at=utc_now() if target_status == "archived" else None,
            )
            self.audit.append_uncommitted(
                event_type="review_schema.template.updated",
                event={
                    "template_id": template_id,
                    "before_status": current["status"],
                    "after_status": target_status,
                },
                user=user,
            )
        return updated

    def load_version(self, version_id: str) -> dict[str, Any]:
        version = self.versions.get(version_id)
        if version is None:
            raise KeyError(f"Unknown review schema version: {version_id}")
        schema = json_loads(version["schema_json"], {})
        if int(version["format_version"]) != REVIEW_SCHEMA_FORMAT_VERSION:
            raise RuntimeError("Unsupported published review schema format version.")
        if content_hash(schema) != version["content_hash"]:
            raise RuntimeError("Published review schema content hash mismatch.")
        return self._decode_version(version)

    def list_selectable_versions(self) -> list[dict[str, Any]]:
        """List published versions eligible for a new pipeline draft."""
        rows = self.conn.execute(
            """
            SELECT v.*, t.schema_key, t.name AS template_name
            FROM review_schema_versions v
            JOIN review_schema_templates t ON t.id = v.schema_template_id
            WHERE t.status = 'active'
            ORDER BY t.name, t.schema_key, v.version_number DESC
            """
        ).fetchall()
        return [self._decode_version(dict(row)) for row in rows]

    def export_version(
        self, version_id: str, *, format: str = "yaml", user: str | None = None
    ) -> str:
        payload = self.load_version(version_id)
        template = self._require_template(payload["schema_template_id"])
        document = {
            "kind": "review-schema",
            "format_version": payload["format_version"],
            "schema_key": template["schema_key"],
            "version": payload["version_number"],
            "content_hash": payload["content_hash"],
            "schema": payload["schema"],
        }
        self.audit.append(
            event_type="review_schema.version.exported",
            event={
                "template_id": template["id"],
                "schema_key": template["schema_key"],
                "version_id": version_id,
                "version_number": payload["version_number"],
                "content_hash": payload["content_hash"],
            },
            user=user,
        )
        if format == "json":
            return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        if format != "yaml":
            raise ValueError("Export format must be yaml or json.")
        return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)

    def import_draft(
        self,
        template_id: str,
        *,
        expected_revision: int,
        text: str,
        user: str | None,
    ) -> dict[str, Any]:
        """Parse a portable YAML/JSON document and save it as a draft only."""
        schema = self.import_document(text)
        result = self.save_draft(
            template_id,
            expected_revision=expected_revision,
            schema=schema,
            user=user,
        )
        template = self._require_template(template_id)
        self.audit.append(
            event_type="review_schema.draft.imported",
            event={
                "template_id": template_id,
                "schema_key": template["schema_key"],
                "revision": result["revision"],
                "content_hash": result["content_hash"],
            },
            user=user,
        )
        return result

    def export_draft(
        self, template_id: str, *, format: str = "yaml", user: str | None = None
    ) -> str:
        """Export the current draft with stable portable metadata."""
        template = self._require_template(template_id)
        draft = self._decode_draft(self._require_draft(template_id))
        document = {
            "kind": "review-schema-draft",
            "format_version": REVIEW_SCHEMA_FORMAT_VERSION,
            "schema_key": template["schema_key"],
            "revision": draft["revision"],
            "content_hash": draft["content_hash"],
            "schema": draft["schema"],
        }
        self.audit.append(
            event_type="review_schema.draft.exported",
            event={
                "template_id": template_id,
                "schema_key": template["schema_key"],
                "revision": draft["revision"],
                "content_hash": draft["content_hash"],
            },
            user=user,
        )
        if format == "json":
            return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        if format != "yaml":
            raise ValueError("Export format must be yaml or json.")
        return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)

    def validate_payload(
        self, version_id: str, payload: Mapping[str, Any]
    ) -> list[dict[str, str]]:
        """Validate review data against one exact immutable schema version."""
        version = self.load_version(version_id)
        return SchemaService(_NullConfig()).validate_payload(
            dict(payload), schema=version["schema"]
        )

    @staticmethod
    def import_document(text: str) -> dict[str, Any]:
        if len(text.encode("utf-8")) > 1_048_576:
            raise ValueError("Review schema import exceeds 1 MiB.")
        document = yaml.safe_load(text)
        if not isinstance(document, dict):
            raise ValueError("Review schema import must contain an object.")
        kind = document.get("kind")
        if kind is not None and kind not in {"review-schema", "review-schema-draft"}:
            raise ValueError("Unsupported review schema import kind.")
        format_version = document.get("format_version")
        if (
            format_version is not None
            and format_version != REVIEW_SCHEMA_FORMAT_VERSION
        ):
            raise ValueError("Unsupported review schema import format version.")
        schema = document.get("schema", document)
        if not isinstance(schema, dict):
            raise ValueError("Imported review schema must be an object.")
        return canonicalize_json(schema)

    def _require_template(self, template_id: str) -> dict[str, Any]:
        template = self.templates.get(template_id)
        if template is None:
            raise KeyError(f"Unknown review schema template: {template_id}")
        return template

    def _require_draft(self, template_id: str) -> dict[str, Any]:
        draft = self.drafts.get(template_id)
        if draft is None:
            raise KeyError(f"Review schema draft is missing: {template_id}")
        return draft

    @staticmethod
    def _decode_draft(row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "schema": json_loads(row["schema_json"], {})}

    @staticmethod
    def _decode_version(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **row,
            "schema": json_loads(row["schema_json"], {}),
            "validation_summary": json_loads(row["validation_summary_json"], {}),
        }
