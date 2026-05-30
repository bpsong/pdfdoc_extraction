"""Workflow task-run state coordination."""

from __future__ import annotations

import sqlite3
from typing import Any

from modules.db.repositories import DocumentRepository, TaskRunRepository


class WorkflowStateService:
    """Records task run lifecycle and current document pipeline position."""

    def __init__(self, conn: sqlite3.Connection, pipeline: list[str] | None = None) -> None:
        self.conn = conn
        self.pipeline = pipeline or []
        self.documents = DocumentRepository(conn)
        self.task_runs = TaskRunRepository(conn)

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
        self.documents.update_current_task(document_id, task_index, task_key)
        return self.task_runs.create_started(
            batch_id=batch_id,
            document_id=document_id,
            task_key=task_key,
            task_index=task_index,
            module_name=module_name,
            class_name=class_name,
            input_data=input_data,
        )

    def complete_task(self, task_run_id: str, output_data: dict[str, Any] | None = None) -> None:
        """Mark a task run completed."""
        self.task_runs.mark_completed(task_run_id, output_data)

    def fail_task(self, task_run_id: str, error: str, output_data: dict[str, Any] | None = None) -> None:
        """Mark a task run failed."""
        self.task_runs.mark_failed(task_run_id, error, output_data)

    def pause_document(self, document_id: str, *, status: str = "review_required") -> None:
        """Pause a document for app-level human review."""
        self.documents.update_status(document_id, status)

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
