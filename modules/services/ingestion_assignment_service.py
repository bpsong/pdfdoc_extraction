"""Atomic ingestion assignment to one exact published pipeline version."""

from __future__ import annotations

import sqlite3
from typing import Any

from modules.config_protocol import ConfigProvider
from modules.db.connection import immediate_transaction
from modules.db.repositories import AuditRepository
from modules.services.batch_service import BatchService
from modules.services.pipeline_definition_service import (
    PipelineDefinitionError,
    PipelineDefinitionService,
)


class IngestionAssignmentError(ValueError):
    """Raised when an ingestion pipeline selection is invalid or unauthorized."""


class IngestionAssignmentService:
    """Validate a selection and atomically persist batch/document attribution."""

    def __init__(self, conn: sqlite3.Connection, config: ConfigProvider) -> None:
        self.conn = conn
        self.config = config

    def available_versions(self, *, role: str) -> list[dict[str, Any]]:
        """Return safe active versions available to the current role."""
        where_selectable = "" if role == "admin" else " AND t.operator_selectable = 1"
        rows = self.conn.execute(
            f"""
            SELECT v.id, v.template_id, v.version_number, v.content_hash,
                   v.published_at,
                   v.display_snapshot_json, t.template_key, t.name,
                   t.description, t.document_type, t.operator_instructions,
                   t.operator_selectable
            FROM pipeline_versions v
            JOIN pipeline_templates t ON t.id = v.template_id
            WHERE t.status = 'active'{where_selectable}
            ORDER BY t.name, t.template_key, v.version_number DESC
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                executable = PipelineDefinitionService(
                    self.conn, self.config
                ).load_version(str(row["id"]))
            except PipelineDefinitionError:
                continue
            result.append(
                {
                    "pipeline_version_id": row["id"],
                    "pipeline_template_id": row["template_id"],
                    "template_key": row["template_key"],
                    "name": row["name"],
                    "description": row["description"],
                    "document_type": row["document_type"],
                    "operator_instructions": row["operator_instructions"],
                    "version_number": row["version_number"],
                    "content_hash": row["content_hash"],
                    "published_at": row["published_at"],
                    "step_count": int(
                        executable.display_snapshot.get("step_count", 0)
                    ),
                }
            )
        return result

    def resolve_selection(
        self, pipeline_version_id: str, *, role: str
    ) -> dict[str, Any]:
        """Verify exact version integrity, secrets, lifecycle, and role policy."""
        if not pipeline_version_id or not isinstance(pipeline_version_id, str):
            raise IngestionAssignmentError("A pipeline version must be selected.")
        row = self.conn.execute(
            """
            SELECT v.*, t.template_key, t.name, t.status AS template_status,
                   t.operator_selectable, t.document_type,
                   t.operator_instructions
            FROM pipeline_versions v
            JOIN pipeline_templates t ON t.id = v.template_id
            WHERE v.id = ?
            """,
            (pipeline_version_id,),
        ).fetchone()
        if row is None:
            raise IngestionAssignmentError("Selected pipeline version is unavailable.")
        item = dict(row)
        if item["template_status"] != "active":
            raise IngestionAssignmentError("Selected pipeline template is not active.")
        if role == "operator" and not bool(item["operator_selectable"]):
            raise IngestionAssignmentError(
                "Selected pipeline version is not available to operators."
            )
        if role not in {"admin", "operator", "system"}:
            raise IngestionAssignmentError("Unknown ingestion role.")
        try:
            executable = PipelineDefinitionService(
                self.conn, self.config
            ).load_version(pipeline_version_id)
        except PipelineDefinitionError as exc:
            raise IngestionAssignmentError(
                "Selected pipeline version is unavailable or invalid."
            ) from exc
        return {
            "pipeline_version_id": executable.version_id,
            "pipeline_template_id": executable.template_id,
            "template_key": executable.template_key,
            "name": item["name"],
            "document_type": item["document_type"],
            "operator_instructions": item["operator_instructions"],
            "version_number": executable.version_number,
            "content_hash": executable.content_hash,
            "step_count": int(executable.display_snapshot.get("step_count", 0)),
        }

    def create_batch(
        self,
        *,
        pipeline_version_id: str,
        role: str,
        source: str,
        assignment_source: str,
        files: list[dict[str, Any]],
        user: str | None,
        metadata: dict[str, Any] | None = None,
        ingress_binding_id: str | None = None,
        status: str = "queued",
    ) -> dict[str, Any]:
        """Create one assigned batch, its roots/artifacts, and audit atomically."""
        summary = self.resolve_selection(pipeline_version_id, role=role)
        with immediate_transaction(self.conn):
            summary = self.resolve_selection(pipeline_version_id, role=role)
            created = BatchService(self.conn).create_ingestion_batch_with_documents(
                source=source,
                files=files,
                metadata=metadata,
                status=status,
                pipeline_template_id=summary["pipeline_template_id"],
                pipeline_version_id=summary["pipeline_version_id"],
                pipeline_assignment_source=assignment_source,
                ingress_binding_id=ingress_binding_id,
            )
            for document in created["documents"]:
                if (
                    document.get("pipeline_template_id")
                    != created["batch"].get("pipeline_template_id")
                    or document.get("pipeline_version_id")
                    != created["batch"].get("pipeline_version_id")
                ):
                    raise IngestionAssignmentError(
                        "Root document assignment does not match its batch."
                    )
            AuditRepository(self.conn).append_uncommitted(
                event_type="ingestion.pipeline.assigned",
                event={
                    "batch_id": created["batch"]["id"],
                    "document_ids": [
                        document["id"] for document in created["documents"]
                    ],
                    "pipeline_template_id": summary["pipeline_template_id"],
                    "pipeline_version_id": summary["pipeline_version_id"],
                    "template_key": summary["template_key"],
                    "name": summary["name"],
                    "version_number": summary["version_number"],
                    "assignment_source": assignment_source,
                    "ingress_binding_id": ingress_binding_id,
                },
                batch_id=created["batch"]["id"],
                user=user,
            )
        return {**created, "pipeline": summary}
