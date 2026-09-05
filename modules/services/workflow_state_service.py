"""Workflow task-run state coordination."""

from __future__ import annotations

import sqlite3
from typing import Any

from modules.db.connection import transaction, utc_now
from modules.db.repositories import AuditRepository, DocumentRepository, TaskRunRepository


DOCUMENT_STATUS_VALUES = {
    "pending",
    "received",
    "queued",
    "processing",
    "in_review",
    "review_required",
    "review_completed",
    "split_completed",
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
}


class WorkflowStateService:
    """Records task run lifecycle and current document pipeline position."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        pipeline: list[str] | None = None,
        pipeline_version_id: str | None = None,
    ) -> None:
        self.conn = conn
        self.pipeline = pipeline or []
        self.pipeline_version_id = pipeline_version_id
        self.documents = DocumentRepository(conn)
        self.task_runs = TaskRunRepository(conn)
        self.audit = AuditRepository(conn)

    def transition_document(
        self,
        document_id: str,
        status: str,
        *,
        reason: str | None = None,
        user: str | None = None,
    ) -> dict[str, Any]:
        """Persist one document transition and its audit event atomically."""
        normalized = str(status or "").strip().lower()
        if normalized not in DOCUMENT_STATUS_VALUES:
            raise ValueError(f"Unsupported document status: {status}")
        document = self.documents.get(document_id)
        if document is None:
            raise ValueError("Document does not exist.")
        previous = str(document.get("status") or "").lower()
        if previous == normalized:
            return document
        with transaction(self.conn):
            cursor = self.conn.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE id = ?",
                (normalized, utc_now(), document_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Document status update failed.")
            self.audit.append_uncommitted(
                event_type="document.status_changed",
                event={
                    "from": previous or None,
                    "to": normalized,
                    "reason": reason,
                },
                batch_id=str(document.get("batch_id")) if document.get("batch_id") else None,
                document_id=document_id,
                user=user,
            )
        updated = self.documents.get(document_id)
        return updated or {**document, "status": normalized}

    def status_history(self, document_id: str) -> list[dict[str, Any]]:
        """Return the persisted document status transition history."""
        return [
            event
            for event in self.audit.list_for_document(document_id)
            if event.get("event_type") == "document.status_changed"
        ]

    def start_task(
        self,
        *,
        batch_id: str,
        document_id: str,
        task_key: str,
        task_index: int,
        module_name: str,
        class_name: str,
        input_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record task start and update document current task pointer."""
        document = self.documents.get(document_id)
        if document is None:
            raise ValueError("Document does not exist.")
        assigned_version = document.get("pipeline_version_id")
        if self.pipeline_version_id is not None and assigned_version != self.pipeline_version_id:
            raise ValueError("Task run pipeline version does not match document assignment.")
        self.documents.update_current_task(document_id, task_index, task_key)
        return self.task_runs.create_started(
            batch_id=batch_id,
            document_id=document_id,
            task_key=task_key,
            task_index=task_index,
            module_name=module_name,
            class_name=class_name,
            input_data=input_data,
            pipeline_version_id=self.pipeline_version_id,
        )

    def start_internal_task(
        self,
        *,
        batch_id: str,
        document_id: str,
        task_key: str,
        task_index: int,
        module_name: str,
        class_name: str,
        input_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an internal task without moving the configured pipeline cursor."""
        document = self.documents.get(document_id)
        if document is None:
            raise ValueError("Document does not exist.")
        assigned_version = document.get("pipeline_version_id")
        if self.pipeline_version_id is not None and assigned_version != self.pipeline_version_id:
            raise ValueError("Internal task pipeline version does not match document assignment.")
        return self.task_runs.create_started(
            batch_id=batch_id,
            document_id=document_id,
            task_key=task_key,
            task_index=task_index,
            module_name=module_name,
            class_name=class_name,
            input_data=input_data,
            pipeline_version_id=self.pipeline_version_id,
        )

    def complete_task(self, task_run_id: str, output_data: dict[str, Any] | None = None) -> None:
        """Mark a task run completed."""
        self.task_runs.mark_completed(task_run_id, output_data)

    def fail_task(self, task_run_id: str, error: str, output_data: dict[str, Any] | None = None) -> None:
        """Mark a task run failed."""
        self.task_runs.mark_failed(task_run_id, error, output_data)

    def pause_task(self, task_run_id: str, output_data: dict[str, Any] | None = None) -> None:
        """Mark a task run paused."""
        self.task_runs.mark_paused(task_run_id, output_data)

    def pause_document(self, document_id: str, *, status: str = "review_required") -> None:
        """Pause a document for app-level human review."""
        self.transition_document(document_id, status, reason="human_review")

    def is_paused(self, document_id: str) -> bool:
        """Return True when document is in a paused review state."""
        document = self.documents.get(document_id)
        return bool(document and document.get("status") in {"review_required", "in_review"})

    def next_task_after_current(self, document_id: str) -> tuple[int, str] | None:
        """Return the next pipeline task after the document current pointer."""
        document = self.documents.get(document_id)
        if not document:
            return None
        next_index = int(document.get("current_task_index") or 0) + 1
        if next_index >= len(self.pipeline):
            return None
        return next_index, self.pipeline[next_index]

    def has_completed_at_or_after(self, document_id: str, task_index: int) -> bool:
        """Return True when resume would duplicate completed downstream work."""
        return self.task_runs.has_completed_at_or_after(
            document_id,
            task_index,
            pipeline_version_id=self.pipeline_version_id,
        )
