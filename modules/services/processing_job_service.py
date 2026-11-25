"""Durable document-processing queue coordination."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any

from modules.db.connection import immediate_transaction
from modules.db.repositories import DocumentRepository, ProcessingJobRepository
from modules.services.fan_in_service import FanInService
from modules.services.workflow_state_service import WorkflowStateService


class ProcessingJobService:
    """Coordinate durable queue records without executing workflow code."""

    def __init__(self, conn: sqlite3.Connection, *, max_attempts: int = 3) -> None:
        self.conn = conn
        self.max_attempts = max(1, int(max_attempts))
        self.jobs = ProcessingJobRepository(conn)

    def enqueue_documents(
        self, *, batch_id: str, document_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Create idempotent queued jobs for assigned root documents."""
        return [
            self.jobs.enqueue(
                batch_id=batch_id,
                document_id=document_id,
                max_attempts=self.max_attempts,
            )
            for document_id in document_ids
        ]

    def recover_expired(self) -> None:
        """Close exhausted jobs and reconcile unfinished documents before requeueing."""
        with immediate_transaction(self.conn):
            batches: set[str] = set()
            for row in self.jobs.fail_exhausted():
                document = DocumentRepository(self.conn).get(row["document_id"])
                if document and document["status"] in {"pending", "received", "queued", "processing"}:
                    WorkflowStateService(self.conn).transition_document(
                        row["document_id"], "failed", reason="lease_expired_attempts_exhausted",
                    )
                    batches.add(row["batch_id"])
            for batch_id in batches:
                FanInService(self.conn).recompute_batch(batch_id)
            self.jobs.requeue_expired()

    @staticmethod
    def retry_at(delay_seconds: float) -> str:
        """Return an ISO timestamp for the next retry attempt."""
        return (datetime.now(timezone.utc) + timedelta(seconds=max(0, delay_seconds))).isoformat()
