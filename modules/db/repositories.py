"""Repository classes for SQLite-backed application state."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from modules.db.connection import json_dumps, json_loads, transaction, utc_now


TERMINAL_STATUSES = {"completed", "Pipeline Completed Successfully", "review_completed"}
FAILED_STATUSES = {"failed", "Workflow Trigger Failed", "Pipeline Completed with Errors"}
FIXED_USERS = {"admin": "admin", "operator": "operator"}


def _new_id() -> str:
    """Create a UUID string for database primary keys."""
    return str(uuid.uuid4())


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a SQLite row to a plain dictionary."""
    return dict(row) if row is not None else None


class UserRepository:
    """Persistence for the two fixed application users."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self, username: str) -> dict[str, Any] | None:
        return _row_to_dict(
            self.conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        )

    def list(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT username, role, token_version, created_at, password_updated_at "
            "FROM users ORDER BY CASE username WHEN 'admin' THEN 0 ELSE 1 END"
        ).fetchall()
        return [dict(row) for row in rows]

    def initialize(self, password_hashes: dict[str, str], *, overwrite: bool = False) -> None:
        if set(password_hashes) != set(FIXED_USERS):
            raise ValueError("Exactly admin and operator credentials are required")
        existing = int(self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        if existing and not overwrite:
            raise ValueError("Users are already initialized")
        now = utc_now()
        with transaction(self.conn):
            if overwrite:
                self.conn.execute("DELETE FROM users")
            for username, role in FIXED_USERS.items():
                self.conn.execute(
                    "INSERT INTO users(username, role, password_hash, token_version, created_at, password_updated_at) "
                    "VALUES (?, ?, ?, 1, ?, ?)",
                    (username, role, password_hashes[username], now, now),
                )

    def update_password(self, username: str, password_hash: str) -> None:
        if username not in FIXED_USERS:
            raise ValueError("Unknown fixed user")
        with transaction(self.conn):
            cursor = self.conn.execute(
                "UPDATE users SET password_hash = ?, token_version = token_version + 1, "
                "password_updated_at = ? WHERE username = ?",
                (password_hash, utc_now(), username),
            )
            if cursor.rowcount != 1:
                raise ValueError("User accounts are not initialized")


class BatchRepository:
    """CRUD helpers for ingestion batches."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(
        self,
        *,
        source: str,
        original_filename: str | None = None,
        status: str = "pending",
        metadata: dict[str, Any] | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        batch_id = batch_id or _new_id()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO batches(
                    id, source, original_filename, status, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (batch_id, source, original_filename, status, now, now, json_dumps(metadata)),
            )
        return self.get(batch_id) or {}

    def get(self, batch_id: str) -> dict[str, Any] | None:
        return _row_to_dict(self.conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone())

    def list(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM batches ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_status(self, batch_id: str, status: str) -> None:
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE batches SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), batch_id),
            )

    def recompute_counts(self, batch_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status IN ('completed', 'review_completed') THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status IN ('failed') THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status IN ('queued', 'received') THEN 1 ELSE 0 END) AS queued
            FROM documents
            WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()
        total = int(row["total"] or 0)
        completed = int(row["completed"] or 0)
        failed = int(row["failed"] or 0)
        queued = int(row["queued"] or 0)
        if failed:
            status = "failed"
        elif total and completed == total:
            status = "completed"
        elif total and queued == total:
            status = "queued"
        elif total:
            status = "processing"
        else:
            status = "pending"
        with transaction(self.conn):
            self.conn.execute(
                """
                UPDATE batches
                SET total_documents = ?, completed_documents = ?, failed_documents = ?,
                    status = ?, updated_at = ?
                WHERE id = ?
                """,
                (total, completed, failed, status, utc_now(), batch_id),
            )
        return self.get(batch_id)


class DocumentRepository:
    """CRUD helpers for source and child documents."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_root(
        self,
        *,
        batch_id: str,
        file_path: str,
        original_filename: str | None,
        status: str = "pending",
        document_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._create(
            batch_id=batch_id,
            parent_document_id=None,
            file_path=file_path,
            original_filename=original_filename,
            status=status,
            document_id=document_id,
            metadata=metadata,
        )

    def create_child(
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
        status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._create(
            batch_id=batch_id,
            parent_document_id=parent_document_id,
            file_path=file_path,
            original_filename=original_filename,
            document_type=document_type,
            page_start=page_start,
            page_end=page_end,
            split_category=split_category,
            split_confidence=split_confidence,
            status=status,
            metadata=metadata,
        )

    def _create(self, **kwargs: Any) -> dict[str, Any]:
        now = utc_now()
        document_id = kwargs.get("document_id") or _new_id()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO documents(
                    id, batch_id, parent_document_id, original_filename, document_type, status,
                    current_task_index, current_task_key, file_path, page_start, page_end,
                    split_category, split_confidence, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    kwargs["batch_id"],
                    kwargs.get("parent_document_id"),
                    kwargs.get("original_filename"),
                    kwargs.get("document_type"),
                    kwargs.get("status", "pending"),
                    0,
                    None,
                    kwargs["file_path"],
                    kwargs.get("page_start"),
                    kwargs.get("page_end"),
                    kwargs.get("split_category"),
                    kwargs.get("split_confidence"),
                    now,
                    now,
                    json_dumps(kwargs.get("metadata")),
                ),
            )
        return self.get(document_id) or {}

    def add_file(
        self,
        *,
        document_id: str,
        file_type: str,
        file_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        file_id = _new_id()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO document_files(id, document_id, file_type, file_path, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (file_id, document_id, file_type, file_path, utc_now(), json_dumps(metadata)),
            )
        return dict(self.conn.execute("SELECT * FROM document_files WHERE id = ?", (file_id,)).fetchone())

    def find_file(self, *, document_id: str, file_type: str, file_path: str) -> dict[str, Any] | None:
        """Return an existing document file by document, role, and path."""
        return _row_to_dict(
            self.conn.execute(
                """
                SELECT * FROM document_files
                WHERE document_id = ? AND file_type = ? AND file_path = ?
                LIMIT 1
                """,
                (document_id, file_type, file_path),
            ).fetchone()
        )

    def list_files(self, document_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM document_files WHERE document_id = ? ORDER BY created_at",
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_all(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Return all documents for legacy list/status compatibility views."""
        rows = self.conn.execute(
            "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_children(self, parent_document_id: str) -> list[dict[str, Any]]:
        """Return child documents for a split/source document."""
        rows = self.conn.execute(
            """
            SELECT * FROM documents
            WHERE parent_document_id = ?
            ORDER BY page_start, created_at
            """,
            (parent_document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, document_id: str) -> dict[str, Any] | None:
        return _row_to_dict(self.conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone())

    def list_by_batch(self, batch_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM documents WHERE batch_id = ? ORDER BY created_at",
            (batch_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_status(self, document_id: str, status: str) -> None:
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), document_id),
            )

    def update_current_task(self, document_id: str, task_index: int, task_key: str | None) -> None:
        with transaction(self.conn):
            self.conn.execute(
                """
                UPDATE documents
                SET current_task_index = ?, current_task_key = ?, updated_at = ?
                WHERE id = ?
                """,
                (task_index, task_key, utc_now(), document_id),
            )

    def update_metadata(self, document_id: str, metadata: dict[str, Any]) -> None:
        """Replace a document's metadata JSON."""
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE documents SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (json_dumps(metadata), utc_now(), document_id),
            )


class TaskRunRepository:
    """CRUD helpers for pipeline task runs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_started(
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
        task_run_id = _new_id()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO task_runs(
                    id, batch_id, document_id, task_key, task_index, module_name, class_name,
                    status, started_at, input_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    task_run_id,
                    batch_id,
                    document_id,
                    task_key,
                    task_index,
                    module_name,
                    class_name,
                    utc_now(),
                    json_dumps(input_data),
                ),
            )
        return self.get(task_run_id) or {}

    def get(self, task_run_id: str) -> dict[str, Any] | None:
        return _row_to_dict(self.conn.execute("SELECT * FROM task_runs WHERE id = ?", (task_run_id,)).fetchone())

    def mark_completed(self, task_run_id: str, output_data: dict[str, Any] | None = None) -> None:
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE task_runs SET status = 'completed', ended_at = ?, output_json = ? WHERE id = ?",
                (utc_now(), json_dumps(output_data), task_run_id),
            )

    def mark_failed(self, task_run_id: str, error: str, output_data: dict[str, Any] | None = None) -> None:
        with transaction(self.conn):
            self.conn.execute(
                """
                UPDATE task_runs
                SET status = 'failed', ended_at = ?, error = ?, output_json = ?
                WHERE id = ?
                """,
                (utc_now(), error, json_dumps(output_data), task_run_id),
            )

    def mark_paused(self, task_run_id: str, output_data: dict[str, Any] | None = None) -> None:
        """Mark a task run paused after app-level workflow pause."""
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE task_runs SET status = 'paused', ended_at = ?, output_json = ? WHERE id = ?",
                (utc_now(), json_dumps(output_data), task_run_id),
            )

    def list_by_document(self, document_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM task_runs WHERE document_id = ? ORDER BY task_index, started_at",
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def has_completed_at_or_after(self, document_id: str, task_index: int) -> bool:
        """Return True when a downstream task has already completed."""
        row = self.conn.execute(
            """
            SELECT 1 FROM task_runs
            WHERE document_id = ? AND task_index >= ? AND status = 'completed'
            LIMIT 1
            """,
            (document_id, task_index),
        ).fetchone()
        return row is not None


class ExtractionRepository:
    """Persistence helpers for extraction results and normalized fields."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save_result(
        self,
        *,
        document_id: str,
        provider: str,
        data: Any,
        task_run_id: str | None = None,
        provider_job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result_id = _new_id()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO extraction_results(
                    id, document_id, task_run_id, provider, provider_job_id,
                    data_json, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    document_id,
                    task_run_id,
                    provider,
                    provider_job_id,
                    json_dumps(data),
                    json_dumps(metadata),
                    utc_now(),
                ),
            )
        return self.get_result(result_id) or {}

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        return _row_to_dict(self.conn.execute("SELECT * FROM extraction_results WHERE id = ?", (result_id,)).fetchone())

    def save_fields(self, *, document_id: str, extraction_result_id: str | None, fields: list[dict[str, Any]]) -> None:
        now = utc_now()
        with transaction(self.conn):
            for field in fields:
                value = field.get("extracted_value", field.get("value"))
                final_value = field.get("final_value", value)
                self.conn.execute(
                    """
                    INSERT INTO extracted_fields(
                        id, document_id, extraction_result_id, field_key, field_alias,
                        extracted_value_json, corrected_value_json, final_value_json,
                        confidence, confidence_label, requires_review, review_status,
                        source_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _new_id(),
                        document_id,
                        extraction_result_id,
                        field["field_key"],
                        field.get("field_alias"),
                        json_dumps(value),
                        json_dumps(field.get("corrected_value")) if "corrected_value" in field else None,
                        json_dumps(final_value),
                        field.get("confidence"),
                        field.get("confidence_label"),
                        1 if field.get("requires_review") else 0,
                        field.get("review_status", "not_required"),
                        json_dumps(field.get("source")),
                        now,
                        now,
                    ),
                )

    def get_latest_result(self, document_id: str) -> dict[str, Any] | None:
        return _row_to_dict(
            self.conn.execute(
                """
                SELECT * FROM extraction_results
                WHERE document_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        )

    def get_fields(self, document_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM extracted_fields WHERE document_id = ? ORDER BY created_at",
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def apply_corrections(self, document_id: str, corrections: dict[str, Any]) -> None:
        now = utc_now()
        with transaction(self.conn):
            for field_key, corrected_value in corrections.items():
                self.conn.execute(
                    """
                    UPDATE extracted_fields
                    SET corrected_value_json = ?, final_value_json = ?,
                        review_status = 'corrected', updated_at = ?
                    WHERE document_id = ? AND field_key = ?
                    """,
                    (json_dumps(corrected_value), json_dumps(corrected_value), now, document_id, field_key),
                )

    def set_review_requirements(self, document_id: str, required_field_keys: list[str]) -> None:
        """Mark which extracted fields require human review for the current gate run."""
        now = utc_now()
        required = set(required_field_keys)
        with transaction(self.conn):
            rows = self.conn.execute(
                "SELECT field_key FROM extracted_fields WHERE document_id = ?",
                (document_id,),
            ).fetchall()
            for row in rows:
                field_key = str(row["field_key"])
                requires_review = field_key in required
                self.conn.execute(
                    """
                    UPDATE extracted_fields
                    SET requires_review = ?, review_status = ?, updated_at = ?
                    WHERE document_id = ? AND field_key = ?
                    """,
                    (
                        1 if requires_review else 0,
                        "required" if requires_review else "not_required",
                        now,
                        document_id,
                        field_key,
                    ),
                )


class ReviewRepository:
    """Persistence helpers for review queue items and locks."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_review_item(
        self,
        *,
        batch_id: str,
        document_id: str,
        queue_name: str,
        reason: str,
        scope: str,
        status: str = "pending",
        created_by_task_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item_id = _new_id()
        now = utc_now()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO review_items(
                    id, batch_id, document_id, queue_name, status, reason, scope,
                    created_by_task_run_id, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    batch_id,
                    document_id,
                    queue_name,
                    status,
                    reason,
                    scope,
                    created_by_task_run_id,
                    now,
                    now,
                    json_dumps(metadata),
                ),
            )
        return self.get(item_id) or {}

    def get(self, review_item_id: str) -> dict[str, Any] | None:
        return _row_to_dict(self.conn.execute("SELECT * FROM review_items WHERE id = ?", (review_item_id,)).fetchone())

    def list_queue(self, *, status: str | None = None, queue_name: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM review_items WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if queue_name:
            sql += " AND queue_name = ?"
            params.append(queue_name)
        sql += " ORDER BY created_at"
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def find_open_for_document(
        self,
        document_id: str,
        *,
        created_by_task_run_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Find a non-completed review item for a document and optional task run."""
        sql = """
            SELECT * FROM review_items
            WHERE document_id = ? AND status IN ('pending', 'in_review')
        """
        params: list[Any] = [document_id]
        if created_by_task_run_id:
            sql += " AND created_by_task_run_id = ?"
            params.append(created_by_task_run_id)
        sql += " ORDER BY created_at DESC LIMIT 1"
        return _row_to_dict(self.conn.execute(sql, params).fetchone())

    def update_metadata(self, review_item_id: str, metadata: dict[str, Any]) -> None:
        """Replace review item metadata JSON."""
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE review_items SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (json_dumps(metadata), utc_now(), review_item_id),
            )

    def claim(self, review_item_id: str, locked_by: str, *, timeout_minutes: int = 60) -> dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        expires_at = (now_dt + timedelta(minutes=timeout_minutes)).isoformat()
        now = now_dt.isoformat()
        with transaction(self.conn):
            self.conn.execute("DELETE FROM review_locks WHERE review_item_id = ?", (review_item_id,))
            self.conn.execute(
                """
                INSERT INTO review_locks(id, review_item_id, locked_by, locked_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_new_id(), review_item_id, locked_by, now, expires_at),
            )
            self.conn.execute(
                """
                UPDATE review_items
                SET status = 'in_review', assigned_to = ?, updated_at = ?
                WHERE id = ?
                """,
                (locked_by, now, review_item_id),
            )
        return self.get(review_item_id) or {}

    def release(self, review_item_id: str) -> None:
        with transaction(self.conn):
            self.conn.execute("DELETE FROM review_locks WHERE review_item_id = ?", (review_item_id,))
            self.conn.execute(
                "UPDATE review_items SET status = 'pending', assigned_to = NULL, updated_at = ? WHERE id = ?",
                (utc_now(), review_item_id),
            )

    def delete_lock(self, review_item_id: str) -> None:
        """Delete a review lock without changing review item status."""
        with transaction(self.conn):
            self.conn.execute("DELETE FROM review_locks WHERE review_item_id = ?", (review_item_id,))

    def complete(self, review_item_id: str, assigned_to: str | None = None) -> None:
        now = utc_now()
        with transaction(self.conn):
            self.conn.execute("DELETE FROM review_locks WHERE review_item_id = ?", (review_item_id,))
            self.conn.execute(
                """
                UPDATE review_items
                SET status = 'completed', assigned_to = COALESCE(?, assigned_to),
                    completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (assigned_to, now, now, review_item_id),
            )

    def get_lock(self, review_item_id: str) -> dict[str, Any] | None:
        return _row_to_dict(self.conn.execute("SELECT * FROM review_locks WHERE review_item_id = ?", (review_item_id,)).fetchone())


class AuditRepository:
    """Append-only audit event storage."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def append(
        self,
        *,
        event_type: str,
        event: dict[str, Any],
        batch_id: str | None = None,
        document_id: str | None = None,
        review_item_id: str | None = None,
        user: str | None = None,
    ) -> dict[str, Any]:
        event_id = _new_id()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO audit_events(
                    id, batch_id, document_id, review_item_id, user, event_type, event_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, batch_id, document_id, review_item_id, user, event_type, json_dumps(event), utc_now()),
            )
        return dict(self.conn.execute("SELECT * FROM audit_events WHERE id = ?", (event_id,)).fetchone())

    def list_for_document(self, document_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM audit_events WHERE document_id = ? ORDER BY created_at",
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_admin_events(
        self,
        *,
        event_type: str | None = None,
        user: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sql, params = self._admin_event_query(
            event_type=event_type,
            user=user,
            created_from=created_from,
            created_to=created_to,
        )
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def count_admin_events(
        self,
        *,
        event_type: str | None = None,
        user: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> int:
        """Return the number of admin-scoped audit events matching filters."""
        sql, params = self._admin_event_query(
            event_type=event_type,
            user=user,
            created_from=created_from,
            created_to=created_to,
            select_clause="SELECT COUNT(*) AS count",
        )
        row = self.conn.execute(sql, params).fetchone()
        return int(row["count"] if row else 0)

    @staticmethod
    def _admin_event_query(
        *,
        event_type: str | None = None,
        user: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        select_clause: str = "SELECT *",
    ) -> tuple[str, list[Any]]:
        """Build an admin-audit query over immutable audit events."""
        sql = f"{select_clause} FROM audit_events WHERE event_type LIKE 'admin_%'"
        params: list[Any] = []
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if user:
            sql += " AND user = ?"
            params.append(user)
        if created_from:
            sql += " AND created_at >= ?"
            params.append(created_from)
        if created_to:
            sql += " AND created_at <= ?"
            params.append(created_to)
        return sql, params


class AppSettingsRepository:
    """Key-value JSON settings storage."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def set(self, key: str, value: Any) -> None:
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO app_settings(key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json_dumps(value), utc_now()),
            )

    def get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value_json FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json_loads(row["value_json"], default)


class ConfigVersionRepository:
    """Draft and published configuration version storage."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_draft(
        self,
        *,
        config_type: str,
        name: str,
        content_text: str,
        created_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._create(
            config_type=config_type,
            name=name,
            status="draft",
            content_text=content_text,
            created_by=created_by,
            metadata=metadata,
        )

    def _create(self, **kwargs: Any) -> dict[str, Any]:
        version_id = _new_id()
        content_hash = hashlib.sha256(kwargs["content_text"].encode("utf-8")).hexdigest()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO config_versions(
                    id, config_type, name, status, content_text, content_hash,
                    created_by, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    kwargs["config_type"],
                    kwargs["name"],
                    kwargs["status"],
                    kwargs["content_text"],
                    content_hash,
                    kwargs.get("created_by"),
                    utc_now(),
                    json_dumps(kwargs.get("metadata")),
                ),
            )
        return dict(self.conn.execute("SELECT * FROM config_versions WHERE id = ?", (version_id,)).fetchone())

    def get_active(self, config_type: str, name: str) -> dict[str, Any] | None:
        return self._get_by_status(config_type, name, "published")

    def get_draft(self, config_type: str, name: str) -> dict[str, Any] | None:
        return self._get_by_status(config_type, name, "draft")

    def _get_by_status(self, config_type: str, name: str, status: str) -> dict[str, Any] | None:
        return _row_to_dict(
            self.conn.execute(
                """
                SELECT * FROM config_versions
                WHERE config_type = ? AND name = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (config_type, name, status),
            ).fetchone()
        )

    def publish(self, version_id: str) -> dict[str, Any] | None:
        now = utc_now()
        row = self.conn.execute("SELECT * FROM config_versions WHERE id = ?", (version_id,)).fetchone()
        if row is None:
            return None
        with transaction(self.conn):
            self.conn.execute(
                """
                UPDATE config_versions
                SET status = 'archived'
                WHERE config_type = ? AND name = ? AND status = 'published'
                """,
                (row["config_type"], row["name"]),
            )
            self.conn.execute(
                "UPDATE config_versions SET status = 'published', published_at = ? WHERE id = ?",
                (now, version_id),
            )
        return _row_to_dict(self.conn.execute("SELECT * FROM config_versions WHERE id = ?", (version_id,)).fetchone())

    def list_versions(self, config_type: str | None = None, name: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM config_versions WHERE 1=1"
        params: list[Any] = []
        if config_type:
            sql += " AND config_type = ?"
            params.append(config_type)
        if name:
            sql += " AND name = ?"
            params.append(name)
        sql += " ORDER BY created_at DESC"
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]
