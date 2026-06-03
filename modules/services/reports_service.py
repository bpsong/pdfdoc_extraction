"""Basic SQLite-backed processing reports."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from modules.services.batch_service import BatchService


COMPLETED_DOCUMENT_STATUSES = {"completed", "review_completed"}
FAILED_DOCUMENT_STATUSES = {"failed", "completed_with_errors"}


class ReportsService:
    """Build operator-facing processing report summaries from SQLite state."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the reports service.

        Args:
            conn: SQLite connection with row factory enabled.
        """
        self.conn = conn

    def summary(self) -> dict[str, Any]:
        """Return basic processing report metrics and recent batches."""
        status_counts = self._document_status_counts()
        source_counts = self._batch_source_counts()
        review_counts = self._review_counts()
        average_seconds = self._average_processing_seconds()
        total_documents = sum(status_counts.values())
        documents_completed = sum(
            count for status, count in status_counts.items() if status in COMPLETED_DOCUMENT_STATUSES
        )
        documents_failed = sum(
            count for status, count in status_counts.items() if status in FAILED_DOCUMENT_STATUSES
        )
        documents_reviewed = self._documents_reviewed()
        return {
            "summary": {
                "total_batches": self._count("batches"),
                "total_documents": total_documents,
                "documents_completed": documents_completed,
                "documents_failed": documents_failed,
                "documents_reviewed": documents_reviewed,
                "average_processing_seconds": average_seconds,
                "average_processing_display": _duration_display(average_seconds),
            },
            "document_statuses": [
                {"status": status, "count": count}
                for status, count in sorted(status_counts.items())
            ],
            "batch_sources": [
                {"source": source, "count": count}
                for source, count in sorted(source_counts.items())
            ],
            "review": {
                "total": sum(review_counts.values()),
                "by_status": [
                    {"status": status, "count": count}
                    for status, count in sorted(review_counts.items())
                ],
            },
            "recent_batches": BatchService(self.conn).list_batches(limit=10),
        }

    def _count(self, table_name: str) -> int:
        """Return row count for a known report table."""
        if table_name not in {"batches", "documents", "review_items", "task_runs"}:
            raise ValueError(f"Unsupported report table: {table_name}")
        row = self.conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"] if row else 0)

    def _document_status_counts(self) -> dict[str, int]:
        """Return document counts grouped by status."""
        rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM documents
            GROUP BY status
            """
        ).fetchall()
        return {str(row["status"] or "unknown"): int(row["count"] or 0) for row in rows}

    def _batch_source_counts(self) -> dict[str, int]:
        """Return batch counts grouped by source."""
        rows = self.conn.execute(
            """
            SELECT source, COUNT(*) AS count
            FROM batches
            GROUP BY source
            """
        ).fetchall()
        return {str(row["source"] or "unknown"): int(row["count"] or 0) for row in rows}

    def _review_counts(self) -> dict[str, int]:
        """Return review item counts grouped by status."""
        rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM review_items
            GROUP BY status
            """
        ).fetchall()
        return {str(row["status"] or "unknown"): int(row["count"] or 0) for row in rows}

    def _documents_reviewed(self) -> int:
        """Return number of documents with completed reviews."""
        row = self.conn.execute(
            """
            SELECT COUNT(DISTINCT document_id) AS count
            FROM review_items
            WHERE status = 'completed'
            """
        ).fetchone()
        return int(row["count"] if row else 0)

    def _average_processing_seconds(self) -> float | None:
        """Return average task-run span per document when timing is available."""
        rows = self.conn.execute(
            """
            SELECT document_id, MIN(started_at) AS started_at, MAX(ended_at) AS ended_at
            FROM task_runs
            WHERE started_at IS NOT NULL AND ended_at IS NOT NULL
            GROUP BY document_id
            """
        ).fetchall()
        durations: list[float] = []
        for row in rows:
            started_at = _parse_iso_datetime(row["started_at"])
            ended_at = _parse_iso_datetime(row["ended_at"])
            if started_at is None or ended_at is None:
                continue
            seconds = (ended_at - started_at).total_seconds()
            if seconds >= 0:
                durations.append(seconds)
        if not durations:
            return None
        return round(sum(durations) / len(durations), 2)


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO datetime value from SQLite."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_display(seconds: float | None) -> str:
    """Format a duration for report cards."""
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{round(seconds, 1)}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{round(minutes, 1)}m"
    return f"{round(minutes / 60, 1)}h"
