"""Batch creation and summary operations."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from modules.db.repositories import BatchRepository, DocumentRepository


class BatchService:
    """Coordinates batch and root document creation for ingestion paths."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.batches = BatchRepository(conn)
        self.documents = DocumentRepository(conn)

    def create_ingestion_batch(
        self,
        *,
        source: str,
        file_path: str,
        original_filename: str,
        batch_id: str | None = None,
        document_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a batch with one root document for an ingested PDF."""
        created = self.create_ingestion_batch_with_documents(
            source=source,
            files=[
                {
                    "file_path": file_path,
                    "original_filename": original_filename,
                    "document_id": document_id,
                    "metadata": metadata,
                    "status": "processing",
                }
            ],
            batch_id=batch_id,
            metadata=metadata,
            status="processing",
        )
        return {"batch": created["batch"], "document": created["documents"][0]}

    def create_ingestion_batch_with_documents(
        self,
        *,
        source: str,
        files: list[dict[str, Any]],
        batch_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "queued",
    ) -> dict[str, Any]:
        """Create one ingestion batch with one root document per PDF file.

        Args:
            source: Input source label, such as ``web`` or ``watch_folder``.
            files: File descriptors containing ``file_path``, ``original_filename``,
                and optional ``document_id``, ``metadata``, and ``status``.
            batch_id: Optional caller-provided batch identifier.
            metadata: Batch-level metadata.
            status: Initial batch status.

        Returns:
            A dictionary containing the created batch and document rows.
        """
        if not files:
            raise ValueError("At least one file is required to create a batch.")

        batch_metadata = dict(metadata or {})
        batch_metadata.setdefault("file_count", len(files))
        first_filename = str(files[0].get("original_filename") or "uploaded.pdf")
        batch = self.batches.create(
            source=source,
            original_filename=first_filename if len(files) == 1 else f"{len(files)} files",
            status=status,
            metadata=batch_metadata,
            batch_id=batch_id,
        )

        documents: list[dict[str, Any]] = []
        for index, file_info in enumerate(files):
            path = str(Path(str(file_info["file_path"])).resolve())
            original_filename = str(file_info.get("original_filename") or Path(path).name)
            document_metadata = dict(file_info.get("metadata") or {})
            document_metadata.setdefault("source_path", path)
            document_metadata.setdefault("ingestion_source", source)
            document_metadata.setdefault("batch_upload_index", index)
            document = self.documents.create_root(
                batch_id=batch["id"],
                document_id=file_info.get("document_id"),
                file_path=path,
                original_filename=original_filename,
                status=str(file_info.get("status") or status),
                metadata=document_metadata,
            )
            self.documents.add_file(
                document_id=document["id"],
                file_type="source_original",
                file_path=path,
                metadata={"source": source, "original_filename": original_filename},
            )
            documents.append(document)

        batch = self.batches.recompute_counts(batch["id"]) or batch
        return {"batch": batch, "documents": documents}

    def list_batches(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Return batches with persisted aggregate counts."""
        return [self._with_progress(batch) for batch in self.batches.list(limit=limit, offset=offset)]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        """Return one batch by id."""
        batch = self.batches.get(batch_id)
        return self._with_progress(batch) if batch else None

    def list_documents(self, batch_id: str) -> list[dict[str, Any]]:
        """Return documents in a batch."""
        return [self._document_with_progress(document) for document in self.documents.list_by_batch(batch_id)]

    def recompute(self, batch_id: str) -> dict[str, Any] | None:
        """Refresh and return aggregate batch counts."""
        batch = self.batches.recompute_counts(batch_id)
        return self._with_progress(batch) if batch else None

    @staticmethod
    def _with_progress(batch: dict[str, Any]) -> dict[str, Any]:
        """Add a UI-ready progress percentage to a batch row."""
        total = int(batch.get("total_documents") or 0)
        completed = int(batch.get("completed_documents") or 0)
        failed = int(batch.get("failed_documents") or 0)
        if total <= 0:
            progress = 0
        else:
            progress = round(((completed + failed) / total) * 100)
        return {**batch, "progress_percent": progress}

    @staticmethod
    def _document_with_progress(document: dict[str, Any]) -> dict[str, Any]:
        """Add a coarse UI progress percentage to a document row."""
        status = str(document.get("status") or "").lower()
        progress_by_status = {
            "received": 5,
            "queued": 10,
            "processing": 35,
            "split_pending": 25,
            "split_completed": 45,
            "extraction_pending": 50,
            "extraction_completed": 70,
            "review_required": 80,
            "in_review": 80,
            "review_completed": 90,
            "resuming": 90,
            "completed": 100,
            "completed_with_errors": 100,
            "failed": 100,
            "cancelled": 100,
        }
        return {**document, "progress_percent": progress_by_status.get(status, 30 if status else 0)}
