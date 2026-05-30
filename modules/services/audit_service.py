"""Audit event service."""

from __future__ import annotations

import sqlite3
from typing import Any

from modules.db.repositories import AuditRepository


class AuditService:
    """Append immutable audit events with normalized event payloads."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.audit = AuditRepository(conn)

    def append_event(
        self,
        *,
        event_type: str,
        user: str | None = None,
        batch_id: str | None = None,
        document_id: str | None = None,
        review_item_id: str | None = None,
        before: Any = None,
        after: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a structured audit event."""
        event = {
            "before": before,
            "after": after,
            "metadata": metadata or {},
        }
        return self.audit.append(
            event_type=event_type,
            event=event,
            batch_id=batch_id,
            document_id=document_id,
            review_item_id=review_item_id,
            user=user,
        )

    def list_for_document(self, document_id: str) -> list[dict[str, Any]]:
        """Return audit events for a document."""
        return self.audit.list_for_document(document_id)
