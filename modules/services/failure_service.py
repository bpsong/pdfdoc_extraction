"""Operator-facing fatal failure summaries and notifications."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from modules.db.connection import json_loads, utc_now
from modules.db.repositories import AppSettingsRepository, AuditRepository, DocumentRepository, TaskRunRepository


FAILURE_NOTIFICATION_SETTING = "fatal_failure_notifications"
SECRET_KEY_PATTERN = re.compile(r"(api[_-]?key|token|secret|password|credential)", re.IGNORECASE)
SECRET_VALUE_PATTERN = re.compile(r"\b(llx-[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]+)\b")


class FailureService:
    """Build failure queue payloads from failed task runs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.documents = DocumentRepository(conn)
        self.task_runs = TaskRunRepository(conn)
        self.settings = AppSettingsRepository(conn)
        self.audit = AuditRepository(conn)

    def list_failures(self, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """Return failed documents with their latest failed task run."""
        rows = self._failure_rows()
        total = len(rows)
        selected = rows[offset : offset + limit]
        return {
            "total": total,
            "failures": [self._failure_row_payload(row) for row in selected],
            "limit": limit,
            "offset": offset,
        }

    def get_failure(self, document_id: str) -> dict[str, Any] | None:
        """Return detailed failure payload for one document."""
        document = self.documents.get(document_id)
        if document is None:
            return None
        runs = self.task_runs.list_by_document(document_id)
        failed_runs = [run for run in runs if str(run.get("status") or "").lower() == "failed"]
        if not failed_runs:
            return None
        failed_run = self._latest_run(failed_runs)
        files = [self._file_payload(item) for item in self.documents.list_files(document_id)]
        metadata = json_loads(document.get("metadata_json"), {})
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "document": self._document_payload(document),
            "latest_failed_task": self._task_run_payload(failed_run),
            "failure": self._failure_detail(document, failed_run),
            "task_runs": [self._task_run_payload(run) for run in runs],
            "files": files,
            "preview_url": f"/api/documents/{document_id}/file/pdf",
            "metadata": _redact(metadata),
        }

    def notification_status(self) -> dict[str, Any]:
        """Return global fatal-failure notification count after the clear watermark."""
        clear_state = self.settings.get(FAILURE_NOTIFICATION_SETTING, {})
        cleared_at = clear_state.get("cleared_at") if isinstance(clear_state, dict) else None
        rows = [
            row for row in self._failure_rows()
            if not cleared_at or str(row.get("failure_at") or "") > str(cleared_at)
        ]
        latest = self._failure_row_payload(rows[0]) if rows else None
        return {
            "count": len(rows),
            "cleared_at": cleared_at,
            "latest": latest,
        }

    def clear_notifications(self, *, user: str | None = None) -> dict[str, Any]:
        """Globally clear current fatal-failure notifications."""
        state = {"cleared_at": utc_now()}
        before = self.notification_status()
        self.settings.set(FAILURE_NOTIFICATION_SETTING, state)
        after = self.notification_status()
        self.audit.append(
            event_type="fatal_failure_notifications_cleared",
            event={"before": before, "after": after},
            user=user,
        )
        return after

    def _failure_rows(self) -> list[dict[str, Any]]:
        """Return one row per document with at least one failed task run."""
        rows = self.conn.execute(
            """
            SELECT
                documents.*,
                batches.original_filename AS batch_original_filename,
                batches.source AS batch_source,
                task_runs.id AS failed_task_run_id,
                task_runs.task_key AS failed_task_key,
                task_runs.task_index AS failed_task_index,
                task_runs.module_name AS failed_module_name,
                task_runs.class_name AS failed_class_name,
                task_runs.error AS failed_error,
                task_runs.started_at AS failed_started_at,
                task_runs.ended_at AS failed_ended_at,
                task_runs.output_json AS failed_output_json
            FROM task_runs
            JOIN documents ON documents.id = task_runs.document_id
            JOIN batches ON batches.id = documents.batch_id
            WHERE task_runs.status = 'failed'
            ORDER BY COALESCE(task_runs.ended_at, task_runs.started_at, documents.updated_at) DESC
            """
        ).fetchall()
        by_document: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = dict(row)
            document_id = str(payload["id"])
            if document_id not in by_document:
                payload["failure_at"] = (
                    payload.get("failed_ended_at")
                    or payload.get("failed_started_at")
                    or payload.get("updated_at")
                )
                by_document[document_id] = payload
        return list(by_document.values())

    def _failure_row_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        failure = self._failure_detail(row, row)
        return {
            "document": self._document_payload(row),
            "batch": {
                "id": row.get("batch_id"),
                "source": row.get("batch_source"),
                "original_filename": row.get("batch_original_filename"),
            },
            "failed_task": {
                "id": row.get("failed_task_run_id"),
                "task_key": row.get("failed_task_key"),
                "task_index": row.get("failed_task_index"),
                "class_name": row.get("failed_class_name"),
                "module_name": row.get("failed_module_name"),
                "error": _redact_text(str(row.get("failed_error") or "")),
                "ended_at": row.get("failed_ended_at"),
            },
            "failure": failure,
            "failure_at": row.get("failure_at"),
            "preview_url": f"/api/documents/{row['id']}/file/pdf",
        }

    @staticmethod
    def _document_payload(document: dict[str, Any]) -> dict[str, Any]:
        filename = document.get("original_filename") or Path(str(document.get("file_path") or "")).name
        return {
            "id": document.get("id"),
            "batch_id": document.get("batch_id"),
            "parent_document_id": document.get("parent_document_id"),
            "filename": filename,
            "status": document.get("status"),
            "file_path": document.get("file_path"),
            "document_type": document.get("document_type"),
            "split_category": document.get("split_category"),
            "split_confidence": document.get("split_confidence"),
            "page_start": document.get("page_start"),
            "page_end": document.get("page_end"),
        }

    def _task_run_payload(self, run: dict[str, Any]) -> dict[str, Any]:
        payload = dict(run)
        payload["error"] = _redact_text(str(payload.get("error") or ""))
        payload["input"] = _redact(json_loads(payload.get("input_json"), {}))
        payload["output"] = _redact(json_loads(payload.get("output_json"), {}))
        payload.pop("input_json", None)
        payload.pop("output_json", None)
        return payload

    @staticmethod
    def _file_payload(file_record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": file_record.get("id"),
            "file_type": file_record.get("file_type"),
            "file_path": file_record.get("file_path"),
            "filename": Path(str(file_record.get("file_path") or "")).name,
            "created_at": file_record.get("created_at"),
            "metadata": _redact(json_loads(file_record.get("metadata_json"), {})),
        }

    def _failure_detail(self, document: dict[str, Any], failed_run: dict[str, Any]) -> dict[str, Any]:
        output = json_loads(
            failed_run.get("output_json") or failed_run.get("failed_output_json"),
            {},
        )
        metadata = json_loads(document.get("metadata_json"), {})
        fatal = output.get("fatal_failure") if isinstance(output, dict) else None
        if not isinstance(fatal, dict) and isinstance(metadata, dict):
            fatal = metadata.get("fatal_failure")
        if not isinstance(fatal, dict):
            fatal = {
                "failure_type": "task_failed",
                "message": failed_run.get("error") or failed_run.get("failed_error") or "Task failed",
            }
        fatal = _redact(fatal)
        return {
            "failure_type": fatal.get("failure_type") or "task_failed",
            "message": fatal.get("message") or _redact_text(str(failed_run.get("error") or failed_run.get("failed_error") or "")),
            "provider": fatal.get("provider"),
            "provider_job_id": fatal.get("provider_job_id"),
            "segments": fatal.get("segments") or [],
            "policy": fatal.get("policy") or {},
            "operator_action": fatal.get(
                "operator_action",
                "Inspect/correct the source PDF or configuration outside this failed workflow, then re-ingest as a new document if appropriate.",
            ),
        }

    @staticmethod
    def _latest_run(runs: list[dict[str, Any]]) -> dict[str, Any]:
        return sorted(
            runs,
            key=lambda run: str(run.get("ended_at") or run.get("started_at") or ""),
            reverse=True,
        )[0]


def _redact(value: Any) -> Any:
    """Redact secret-looking keys and values from payloads."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if SECRET_KEY_PATTERN.search(text_key):
                redacted[text_key] = "[REDACTED]"
            else:
                redacted[text_key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    """Redact secret-looking tokens in text."""
    return SECRET_VALUE_PATTERN.sub("[REDACTED]", value)
