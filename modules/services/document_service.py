"""Document state and detail operations."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from modules.db.repositories import DocumentRepository, ExtractionRepository, ReviewRepository, TaskRunRepository


class DocumentService:
    """Coordinates document records and related detail views."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.documents = DocumentRepository(conn)
        self.task_runs = TaskRunRepository(conn)
        self.extractions = ExtractionRepository(conn)
        self.reviews = ReviewRepository(conn)

    def create_child_document(
        self,
        *,
        batch_id: str,
        parent_document_id: str,
        file_path: str,
        original_filename: str | None = None,
        document_type: str | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
        split_category: str | None = None,
        split_confidence: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a child document produced by splitting a source PDF."""
        return self.documents.create_child(
            batch_id=batch_id,
            parent_document_id=parent_document_id,
            file_path=str(Path(file_path).resolve()),
            original_filename=original_filename,
            document_type=document_type,
            page_start=page_start,
            page_end=page_end,
            split_category=split_category,
            split_confidence=split_confidence,
            metadata=metadata,
        )

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Return one document by id."""
        return self.documents.get(document_id)

    def update_status(self, document_id: str, status: str) -> None:
        """Update a document status."""
        self.documents.update_status(document_id, status)

    def get_details(self, document_id: str) -> dict[str, Any] | None:
        """Return a UI-ready document detail payload."""
        document = self.documents.get(document_id)
        if document is None:
            return None
        return {
            "document": document,
            "files": self.documents.list_files(document_id),
            "task_runs": self.task_runs.list_by_document(document_id),
            "latest_extraction": self.extractions.get_latest_result(document_id),
            "fields": self.extractions.get_fields(document_id),
            "review_items": self.reviews.list_queue(),
        }
