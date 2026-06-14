"""Split fan-in and leaf-derived aggregate finalization."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any
import uuid

from modules.db.connection import json_dumps, json_loads, transaction, utc_now
from modules.db.repositories import DocumentRepository


SUCCESS_STATUS = "completed"
FAILURE_STATUS = "failed"
AGGREGATE_FAILURE_STATUS = "completed_with_errors"
REVIEW_STATUSES = {"review_required", "in_review"}


@dataclass(frozen=True)
class FanInResult:
    """Result of one fan-in finalization pass."""

    leaf_document_id: str
    root_document_id: str
    batch_id: str
    leaf_status: str
    root_status: str
    batch_status: str
    all_leaves_terminal: bool
    completed_leaves: int
    failed_leaves: int
    total_leaves: int


class FanInService:
    """Finalize leaf workflow state and recompute root/batch aggregates."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the service with an existing SQLite connection."""
        self.conn = conn
        self.documents = DocumentRepository(conn)

    def finalize_leaf(self, context: dict[str, Any]) -> FanInResult | None:
        """Finalize a leaf document and recompute root and batch state.

        Args:
            context: Workflow context after mandatory housekeeping.

        Returns:
            FanInResult when a document was finalized; otherwise None for
            fan-out parent contexts, paused contexts, or missing document ids.
        """
        if context.get("pipeline_state") == "fan_out":
            return None

        document_id = context.get("document_id") or context.get("id")
        if not document_id:
            return None

        with transaction(self.conn):
            document = self._get_document(str(document_id))
            if document is None:
                return None
            if self._has_children(str(document["id"])):
                return None

            if context.get("pipeline_state") == "paused":
                leaf_status = str(document.get("status") or "review_required")
            else:
                leaf_status = self._leaf_status_from_context(context)
                self._update_document_status(str(document["id"]), leaf_status)
                self._update_failure_metadata(str(document["id"]), context)
                document["status"] = leaf_status

            root = self._root_document(document)
            if root is None:
                root = document

            root_leaves = self._leaf_descendants(str(root["id"]))
            if not root_leaves:
                root_leaves = [document]
            root_summary = self._summarize_leaves(root_leaves)
            root_status = root_summary["status"]
            self._update_document_status(str(root["id"]), root_status)

            batch_leaves = self._batch_leaves(str(document["batch_id"]))
            batch_summary = self._summarize_leaves(batch_leaves)
            self._update_batch_counts(
                batch_id=str(document["batch_id"]),
                summary=batch_summary,
            )

            if root_summary["all_terminal"] and root_status in {SUCCESS_STATUS, AGGREGATE_FAILURE_STATUS}:
                self._append_fan_in_completed_once(
                    batch_id=str(document["batch_id"]),
                    root_document_id=str(root["id"]),
                    summary=root_summary,
                )

            return FanInResult(
                leaf_document_id=str(document["id"]),
                root_document_id=str(root["id"]),
                batch_id=str(document["batch_id"]),
                leaf_status=leaf_status,
                root_status=root_status,
                batch_status=batch_summary["status"],
                all_leaves_terminal=bool(root_summary["all_terminal"]),
                completed_leaves=int(root_summary["completed"]),
                failed_leaves=int(root_summary["failed"]),
                total_leaves=int(root_summary["total"]),
            )

    @staticmethod
    def _leaf_status_from_context(context: dict[str, Any]) -> str:
        """Return the persisted terminal status for a completed leaf workflow."""
        if context.get("error"):
            return FAILURE_STATUS
        return SUCCESS_STATUS

    def _get_document(self, document_id: str) -> dict[str, Any] | None:
        """Return one document row by id."""
        row = self.conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return dict(row) if row else None

    def _has_children(self, document_id: str) -> bool:
        """Return True when a document is a parent/source container."""
        row = self.conn.execute(
            "SELECT 1 FROM documents WHERE parent_document_id = ? LIMIT 1",
            (document_id,),
        ).fetchone()
        return row is not None

    def _root_document(self, document: dict[str, Any]) -> dict[str, Any] | None:
        """Walk parent links until the root/source document is found."""
        current = document
        seen: set[str] = set()
        while current.get("parent_document_id"):
            parent_id = str(current["parent_document_id"])
            if parent_id in seen:
                break
            seen.add(parent_id)
            parent = self._get_document(parent_id)
            if parent is None:
                break
            current = parent
        return current

    def _leaf_descendants(self, root_document_id: str) -> list[dict[str, Any]]:
        """Return leaf descendants for one root, or the root when unsplit."""
        rows = self.conn.execute(
            """
            WITH RECURSIVE descendants AS (
                SELECT * FROM documents WHERE id = ?
                UNION ALL
                SELECT child.*
                FROM documents child
                JOIN descendants parent ON child.parent_document_id = parent.id
            )
            SELECT *
            FROM descendants candidate
            WHERE NOT EXISTS (
                SELECT 1 FROM documents child WHERE child.parent_document_id = candidate.id
            )
            ORDER BY candidate.created_at
            """,
            (root_document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _batch_leaves(self, batch_id: str) -> list[dict[str, Any]]:
        """Return all leaf documents in a batch without double-counting roots."""
        rows = self.conn.execute(
            """
            SELECT *
            FROM documents candidate
            WHERE candidate.batch_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM documents child WHERE child.parent_document_id = candidate.id
              )
            ORDER BY candidate.created_at
            """,
            (batch_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _summarize_leaves(leaves: list[dict[str, Any]]) -> dict[str, Any]:
        """Summarize leaf statuses into aggregate counts and status."""
        total = len(leaves)
        completed = sum(1 for leaf in leaves if leaf.get("status") == SUCCESS_STATUS)
        failed = sum(1 for leaf in leaves if leaf.get("status") == FAILURE_STATUS)
        review = sum(1 for leaf in leaves if leaf.get("status") in REVIEW_STATUSES)
        terminal = completed + failed
        all_terminal = total > 0 and terminal == total

        if review:
            status = "review_required"
        elif total and not all_terminal:
            status = "processing"
        elif failed:
            status = AGGREGATE_FAILURE_STATUS
        elif total:
            status = SUCCESS_STATUS
        else:
            status = "pending"

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "review": review,
            "all_terminal": all_terminal,
            "status": status,
        }

    def _update_document_status(self, document_id: str, status: str) -> None:
        """Persist a document status without opening another transaction."""
        self.conn.execute(
            "UPDATE documents SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), document_id),
        )

    def _update_failure_metadata(self, document_id: str, context: dict[str, Any]) -> None:
        """Persist structured fatal failure context on failed documents."""
        if not context.get("error"):
            return
        document = self._get_document(document_id)
        if document is None:
            return
        metadata = json_loads(document.get("metadata_json"), {})
        if not isinstance(metadata, dict):
            metadata = {}
        fatal_failure = context.get("fatal_failure")
        if not isinstance(fatal_failure, dict):
            fatal_failure = {
                "failure_type": "task_failed",
                "message": str(context.get("error") or ""),
            }
        metadata["fatal_failure"] = fatal_failure
        metadata["fatal_error"] = str(context.get("error") or "")
        metadata["fatal_error_step"] = context.get("error_step") or context.get("current_task_key")
        self.conn.execute(
            "UPDATE documents SET metadata_json = ?, updated_at = ? WHERE id = ?",
            (json_dumps(metadata), utc_now(), document_id),
        )

    def _update_batch_counts(self, *, batch_id: str, summary: dict[str, Any]) -> None:
        """Persist leaf-derived batch counts and aggregate status."""
        self.conn.execute(
            """
            UPDATE batches
            SET total_documents = ?, completed_documents = ?, failed_documents = ?,
                status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                int(summary["total"]),
                int(summary["completed"]),
                int(summary["failed"]),
                str(summary["status"]),
                utc_now(),
                batch_id,
            ),
        )

    def _append_fan_in_completed_once(
        self,
        *,
        batch_id: str,
        root_document_id: str,
        summary: dict[str, Any],
    ) -> None:
        """Append one root fan-in completion audit event."""
        existing = self.conn.execute(
            """
            SELECT 1 FROM audit_events
            WHERE document_id = ? AND event_type = 'fan_in_completed'
            LIMIT 1
            """,
            (root_document_id,),
        ).fetchone()
        if existing:
            return

        self.conn.execute(
            """
            INSERT INTO audit_events(
                id, batch_id, document_id, review_item_id, user, event_type, event_json, created_at
            ) VALUES (?, ?, ?, NULL, NULL, 'fan_in_completed', ?, ?)
            """,
            (
                str(uuid.uuid4()),
                batch_id,
                root_document_id,
                json_dumps(
                    {
                        "root_status": summary["status"],
                        "total_leaves": summary["total"],
                        "completed_leaves": summary["completed"],
                        "failed_leaves": summary["failed"],
                    }
                ),
                utc_now(),
            ),
        )
