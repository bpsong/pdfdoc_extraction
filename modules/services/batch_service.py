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
        path = str(Path(file_path).resolve())
        combined_metadata = dict(metadata or {})
        combined_metadata.setdefault("source_path", path)
        batch = self.batches.create(
            source=source,
            original_filename=original_filename,
            status="processing",
            metadata=combined_metadata,
            batch_id=batch_id,
        )
        document = self.documents.create_root(
            batch_id=batch["id"],
            document_id=document_id,
            file_path=path,
            original_filename=original_filename,
            status="processing",
            metadata=combined_metadata,
        )
        self.documents.add_file(
            document_id=document["id"],
            file_type="original_pdf",
            file_path=path,
            metadata={"source": source, "original_filename": original_filename},
        )
        batch = self.batches.recompute_counts(batch["id"]) or batch
        return {"batch": batch, "document": document}

    def list_batches(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Return batches with persisted aggregate counts."""
        return self.batches.list(limit=limit, offset=offset)

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        """Return one batch by id."""
        return self.batches.get(batch_id)

    def list_documents(self, batch_id: str) -> list[dict[str, Any]]:
        """Return documents in a batch."""
        return self.documents.list_by_batch(batch_id)

    def recompute(self, batch_id: str) -> dict[str, Any] | None:
        """Refresh and return aggregate batch counts."""
        return self.batches.recompute_counts(batch_id)
