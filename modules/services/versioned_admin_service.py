"""Read models and portable conversions for versioned administration APIs."""

from __future__ import annotations

import json
from typing import Any, Mapping

import yaml

from modules.db.connection import json_loads
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.portable_config_service import (
    import_pipeline_bundle,
    export_pipeline_bundle,
)
from modules.services.review_schema_version_service import (
    ReviewSchemaVersionService,
)
from modules.services.versioned_config_contracts import (
    ReviewSchemaCoordinate,
    redact_sensitive,
)


class VersionedAdminService:
    """Provide redacted, template-scoped administration read models."""

    def __init__(
        self,
        conn,
        *,
        configured_secret_aliases: set[str] | None = None,
    ) -> None:
        self.conn = conn
        self.schemas = ReviewSchemaVersionService(conn)
        self.pipelines = PipelineTemplateService(
            conn,
            configured_secret_aliases=configured_secret_aliases,
        )

    def list_schema_templates(
        self, *, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """Return schema template summaries without schema bodies."""
        return [
            self._schema_template_summary(template)
            for template in self.schemas.templates.list(
                include_archived=include_archived
            )
        ]

    def get_schema_template(self, template_id: str) -> dict[str, Any]:
        """Return one schema template, its draft metadata, and versions."""
        template = self.schemas._require_template(template_id)
        draft = self.schemas._decode_draft(
            self.schemas._require_draft(template_id)
        )
        return {
            "template": self._schema_template_summary(template),
            "draft": draft,
            "versions": self.list_schema_versions(template_id),
            "usage": self.schema_usage(template_id),
        }

    def list_schema_versions(self, template_id: str) -> list[dict[str, Any]]:
        """Return immutable schema-version summaries."""
        self.schemas._require_template(template_id)
        return [
            self._schema_version_summary(row)
            for row in self.schemas.versions.list_for_owner(template_id)
        ]

    def get_schema_version(
        self, template_id: str, version_id: str
    ) -> dict[str, Any]:
        """Return one exact schema version after ownership verification."""
        version = self.schemas.load_version(version_id)
        if version["schema_template_id"] != template_id:
            raise KeyError(f"Unknown review schema version: {version_id}")
        return version

    def schema_usage(self, template_id: str) -> dict[str, Any]:
        """Summarize exact pipeline dependencies on a schema template."""
        self.schemas._require_template(template_id)
        rows = self.conn.execute(
            """
            SELECT d.schema_version_id, sv.version_number AS schema_version_number,
                   d.pipeline_version_id, pv.version_number AS pipeline_version_number,
                   d.task_key, pt.id AS pipeline_template_id,
                   pt.template_key, pt.name AS pipeline_name, pt.status
            FROM pipeline_version_schema_dependencies d
            JOIN review_schema_versions sv ON sv.id = d.schema_version_id
            JOIN pipeline_versions pv ON pv.id = d.pipeline_version_id
            JOIN pipeline_templates pt ON pt.id = pv.template_id
            WHERE sv.schema_template_id = ?
            ORDER BY pt.name, pv.version_number DESC, d.task_key
            """,
            (template_id,),
        ).fetchall()
        dependencies = [dict(row) for row in rows]
        return {
            "dependency_count": len(dependencies),
            "pipeline_template_count": len(
                {row["pipeline_template_id"] for row in dependencies}
            ),
            "dependencies": dependencies,
        }

    def list_pipeline_templates(
        self, *, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """Return pipeline template summaries without definitions."""
        return [
            self._pipeline_template_summary(template)
            for template in self.pipelines.templates.list(
                include_archived=include_archived
            )
        ]

    def get_pipeline_template(self, template_id: str) -> dict[str, Any]:
        """Return one pipeline template and its redacted draft workspace."""
        template = self.pipelines._require_template(template_id)
        draft = self.pipelines._decode_draft(
            self.pipelines._require_draft(template_id)
        )
        draft["definition"] = redact_sensitive(draft["definition"])
        return {
            "template": self._pipeline_template_summary(template),
            "draft": draft,
            "versions": self.list_pipeline_versions(template_id),
            "schema_versions": self.schema_selector_options(),
        }

    def list_pipeline_versions(self, template_id: str) -> list[dict[str, Any]]:
        """Return immutable pipeline-version summaries."""
        self.pipelines._require_template(template_id)
        return [
            self._pipeline_version_summary(row)
            for row in self.pipelines.versions.list_for_owner(template_id)
        ]

    def get_pipeline_version(
        self, template_id: str, version_id: str
    ) -> dict[str, Any]:
        """Return one exact redacted pipeline version."""
        version = self.pipelines.load_version(version_id)
        if version["template_id"] != template_id:
            raise KeyError(f"Unknown pipeline version: {version_id}")
        version["definition"] = redact_sensitive(version["definition"])
        version["schema_dependency_summaries"] = (
            self._pipeline_dependency_summaries(version_id)
        )
        return version

    def schema_selector_options(self) -> list[dict[str, Any]]:
        """Return active exact schema versions for pipeline draft selectors."""
        return [
            self._schema_version_summary(version)
            for version in self.schemas.list_selectable_versions()
        ]

    def import_pipeline_document(
        self, document: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Convert a portable pipeline bundle to local exact version IDs."""
        definition, _ = import_pipeline_bundle(
            document,
            resolve_coordinate=self._resolve_schema_coordinate,
        )
        return definition

    def export_pipeline_draft(
        self, template_id: str, *, format: str = "yaml"
    ) -> str:
        """Export a draft as a portable, redacted pipeline bundle."""
        template = self.pipelines._require_template(template_id)
        draft = self.pipelines._decode_draft(
            self.pipelines._require_draft(template_id)
        )
        return self._dump_pipeline_bundle(
            template,
            redact_sensitive(draft["definition"]),
            format=format,
        )

    def export_pipeline_version(
        self, template_id: str, version_id: str, *, format: str = "yaml"
    ) -> str:
        """Export an immutable version as a portable pipeline bundle."""
        template = self.pipelines._require_template(template_id)
        version = self.pipelines.load_version(version_id)
        if version["template_id"] != template_id:
            raise KeyError(f"Unknown pipeline version: {version_id}")
        return self._dump_pipeline_bundle(
            template,
            redact_sensitive(version["definition"]),
            format=format,
        )

    def _dump_pipeline_bundle(
        self,
        template: Mapping[str, Any],
        definition: Mapping[str, Any],
        *,
        format: str,
    ) -> str:
        bundle = export_pipeline_bundle(
            definition,
            template_key=str(template["template_key"]),
            template_name=str(template["name"]),
            resolve_version=self._coordinate_for_version,
        )
        if format == "json":
            return json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True)
        if format != "yaml":
            raise ValueError("Export format must be yaml or json.")
        return yaml.safe_dump(bundle, sort_keys=False, allow_unicode=True)

    def _resolve_schema_coordinate(
        self, coordinate: ReviewSchemaCoordinate
    ) -> str | None:
        row = self.conn.execute(
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

    def _coordinate_for_version(
        self, version_id: str
    ) -> ReviewSchemaCoordinate | None:
        row = self.conn.execute(
            """
            SELECT t.schema_key, v.version_number, v.content_hash
            FROM review_schema_versions v
            JOIN review_schema_templates t ON t.id = v.schema_template_id
            WHERE v.id = ?
            """,
            (version_id,),
        ).fetchone()
        if row is None:
            return None
        return ReviewSchemaCoordinate(
            key=str(row["schema_key"]),
            version_number=int(row["version_number"]),
            content_hash=str(row["content_hash"]),
        )

    def _schema_template_summary(
        self, template: Mapping[str, Any]
    ) -> dict[str, Any]:
        draft = self.schemas.drafts.get(str(template["id"]))
        versions = self.schemas.versions.list_for_owner(str(template["id"]))
        usage = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM pipeline_version_schema_dependencies d
            JOIN review_schema_versions v ON v.id = d.schema_version_id
            WHERE v.schema_template_id = ?
            """,
            (template["id"],),
        ).fetchone()[0]
        return {
            **dict(template),
            "draft_revision": draft["revision"] if draft else None,
            "draft_content_hash": draft["content_hash"] if draft else None,
            "latest_version": versions[0]["version_number"] if versions else None,
            "latest_content_hash": versions[0]["content_hash"] if versions else None,
            "usage_count": int(usage),
        }

    @staticmethod
    def _schema_version_summary(version: Mapping[str, Any]) -> dict[str, Any]:
        schema = json_loads(version.get("schema_json"), {})
        fields = schema.get("fields") if isinstance(schema, dict) else {}
        return {
            "id": version.get("id"),
            "schema_template_id": version.get("schema_template_id"),
            "schema_key": version.get("schema_key"),
            "template_name": version.get("template_name"),
            "version_number": version.get("version_number"),
            "format_version": version.get("format_version"),
            "content_hash": version.get("content_hash"),
            "published_by": version.get("published_by"),
            "published_at": version.get("published_at"),
            "field_count": len(fields) if isinstance(fields, (dict, list)) else 0,
        }

    def _pipeline_template_summary(
        self, template: Mapping[str, Any]
    ) -> dict[str, Any]:
        draft = self.pipelines.drafts.get(str(template["id"]))
        versions = self.pipelines.versions.list_for_owner(str(template["id"]))
        return {
            **dict(template),
            "operator_selectable": bool(template.get("operator_selectable")),
            "draft_revision": draft["revision"] if draft else None,
            "draft_content_hash": draft["content_hash"] if draft else None,
            "latest_version": versions[0]["version_number"] if versions else None,
            "latest_content_hash": versions[0]["content_hash"] if versions else None,
        }

    @staticmethod
    def _pipeline_version_summary(version: Mapping[str, Any]) -> dict[str, Any]:
        snapshot = json_loads(version.get("display_snapshot_json"), {})
        return {
            "id": version.get("id"),
            "template_id": version.get("template_id"),
            "version_number": version.get("version_number"),
            "schema_version": version.get("schema_version"),
            "content_hash": version.get("content_hash"),
            "published_by": version.get("published_by"),
            "published_at": version.get("published_at"),
            "step_count": int(snapshot.get("step_count", 0)),
            "display_snapshot": snapshot,
        }

    def _pipeline_dependency_summaries(
        self, pipeline_version_id: str
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT d.task_key, d.schema_version_id, v.version_number,
                   v.content_hash, t.id AS schema_template_id,
                   t.schema_key, t.name AS schema_name, t.status
            FROM pipeline_version_schema_dependencies d
            JOIN review_schema_versions v ON v.id = d.schema_version_id
            JOIN review_schema_templates t ON t.id = v.schema_template_id
            WHERE d.pipeline_version_id = ?
            ORDER BY d.task_key
            """,
            (pipeline_version_id,),
        ).fetchall()
        return [dict(row) for row in rows]
