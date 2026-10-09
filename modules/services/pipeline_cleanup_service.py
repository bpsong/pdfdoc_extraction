"""Previewed archival and whole-batch retention for versioned pipelines."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any

from modules.db.connection import immediate_transaction, json_dumps, utc_now
from modules.db.repositories import (
    AuditRepository, PipelineTemplateRepository, ProcessingHistoryRepository,
)
from modules.services.pipeline_template_service import PipelineTemplateService


class PipelineCleanupConflictError(ValueError):
    """A cleanup preview expired or no longer matches the processing state."""


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


class PipelineCleanupService:
    """Keep definitions/audits/files while removing confirmed idle histories."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.history = ProcessingHistoryRepository(conn)
        self.templates = PipelineTemplateRepository(conn)

    def _template(self, template_id: str) -> dict[str, Any]:
        template = self.templates.get(template_id)
        if template is None:
            raise KeyError("Pipeline template does not exist.")
        return template

    def archive_preview(self, template_id: str) -> dict[str, Any]:
        """Explain lifecycle and binding blockers; existing work is retained."""
        template = self._template(template_id)
        impact = self.history.pipeline_impact(template_id)
        blockers = []
        if template["status"] != "inactive":
            blockers.append("Set this pipeline to inactive before archiving.")
        if any(binding["enabled"] for binding in impact["bindings"]):
            blockers.append("Pause, reassign, unbind, or retire enabled watch folders first.")
        return {"template": template, **impact, "blockers": blockers, "can_archive": not blockers}

    def archive(self, template_id: str, *, confirmation_name: str, user: str) -> dict[str, Any]:
        """Confirm and archive with the existing lifecycle guards under a lock."""
        with immediate_transaction(self.conn):
            template = self._template(template_id)
            if confirmation_name != template["name"]:
                raise ValueError("Pipeline name confirmation does not match.")
            updated = PipelineTemplateService(self.conn).update_template(
                template_id, status="archived", user=user,
            )
            AuditRepository(self.conn).append_uncommitted(
                event_type="admin_pipeline_archived", user=user,
                event={"template_id": template_id, "name": template["name"]},
            )
        return {"template": updated}

    @staticmethod
    def _cutoff(value: str) -> datetime:
        try:
            parsed = date.fromisoformat(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("Choose a valid cutoff date (YYYY-MM-DD).") from exc
        if parsed.isoformat() != value or parsed > datetime.now(timezone.utc).date():
            raise ValueError("Cutoff must be today or an earlier UTC date.")
        return datetime.combine(parsed, datetime.min.time(), tzinfo=timezone.utc)

    def _plan(self, template: dict[str, Any], cutoff: datetime) -> dict[str, Any]:
        rows = self.history.candidate_rows(template["id"])
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
            batch["id"]: {table: [] for table in rows if table != "batches"}
            for batch in rows["batches"]
        }
        for table, entries in rows.items():
            if table == "batches":
                continue
            for entry in entries:
                grouped[entry["batch_id"]][table].append(entry)
        selected: list[str] = []
        excluded = {key: {"batches": 0, "documents": 0} for key in (
            "pending_review", "active_work", "recent_activity", "inconsistent_history",
        )}
        now = datetime.now(timezone.utc)
        for batch in rows["batches"]:
            group = grouped[batch["id"]]
            docs = group["documents"]
            child_parents = {doc["parent_document_id"] for doc in docs}
            reason = None
            if (not docs or group["external_children"] or group["external_parents"] or any(
                doc["pipeline_template_id"] != template["id"] for doc in docs
            )):
                reason = "inconsistent_history"
            elif any(review["status"] != "completed" for review in group["review_items"]) or any(
                (_timestamp(lock["expires_at"]) or now) >= now for lock in group["review_locks"]
            ):
                reason = "pending_review"
            elif any(
                doc["status"] not in {"completed", "completed_with_errors", "failed", "cancelled"}
                and not (doc["status"] == "split_completed" and doc["id"] in child_parents)
                for doc in docs
            ) or any(job["status"] not in {"completed", "failed"} for job in group["processing_jobs"]) or any(
                run["status"] not in {"completed", "failed", "skipped", "cancelled"}
                for run in group["task_runs"]
            ) or any(decision["phase"] not in {"applied", "failed"} for decision in group["manual_split_decisions"]):
                reason = "active_work"
            else:
                activity = [batch["updated_at"]]
                for table in ("documents", "processing_jobs", "task_runs", "review_items", "manual_split_decisions", "artifact_activity", "extraction_activity", "field_activity"):
                    for entry in group[table]:
                        activity.extend(entry[key] for key in ("updated_at", "started_at", "ended_at", "created_at", "completed_at") if entry.get(key))
                timestamps = [_timestamp(value) for value in activity]
                if any(value is None for value in timestamps):
                    reason = "inconsistent_history"
                elif any(value >= cutoff for value in timestamps if value is not None):
                    reason = "recent_activity"
            if reason:
                excluded[reason]["batches"] += 1
                excluded[reason]["documents"] += len(docs)
            else:
                selected.append(batch["id"])
        self.history.select_batches(selected)
        counts, digest = self.history.selected_summary()
        fingerprint = hashlib.sha256(json_dumps({
            "template": template, "cutoff": cutoff.isoformat(), "digest": digest,
        }).encode("utf-8")).hexdigest()
        return {"counts": counts, "excluded": excluded, "fingerprint": fingerprint}

    def preview(self, template_id: str, *, cutoff_date: str, user: str) -> dict[str, Any]:
        """Store a 15-minute preview of the exact eligible processing records."""
        cutoff = self._cutoff(cutoff_date)
        with immediate_transaction(self.conn):
            template = self._template(template_id)
            plan = self._plan(template, cutoff)
            preview = self.history.record_preview(
                template_id=template_id, user=user, cutoff=cutoff_date,
                fingerprint=plan.pop("fingerprint"),
                expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            )
        return {"preview_id": preview["id"], "expires_at": preview["expires_at"],
                "template_name": template["name"], "cutoff_date": cutoff_date, **plan}

    def cleanup(self, template_id: str, *, preview_id: str, confirmation_name: str, user: str) -> dict[str, Any]:
        """Recheck and remove the exact preview atomically, preserving audits/files."""
        try:
            with immediate_transaction(self.conn):
                template = self._template(template_id)
                preview = self.history.get_preview(preview_id)
                if not preview or preview["template_id"] != template_id or preview["created_by"] != user:
                    raise PipelineCleanupConflictError("Preview is unavailable. Run Preview cleanup again.")
                if preview["expires_at"] <= utc_now():
                    raise PipelineCleanupConflictError("Preview expired. Run Preview cleanup again.")
                if confirmation_name != template["name"]:
                    raise ValueError("Pipeline name confirmation does not match.")
                plan = self._plan(template, self._cutoff(preview["cutoff_date"]))
                if plan.pop("fingerprint") != preview["fingerprint"]:
                    raise PipelineCleanupConflictError("Processing data changed. Run Preview cleanup again.")
                if not plan["counts"]["batches"]:
                    raise PipelineCleanupConflictError("No eligible processing data to delete.")
                receipts = self.history.tombstone_selected_receipts()
                deleted = {}
                for table in self.history.SCOPES:
                    if table != "upload_submissions":
                        deleted[table] = self.history.delete_selected_table(table)
                self.history.consume_preview(preview_id)
                event = AuditRepository(self.conn).append_uncommitted(
                    event_type="admin_pipeline_processing_cleaned", user=user,
                    event={"template_id": template_id, "name": template["name"],
                           "cutoff_date": preview["cutoff_date"], "preview_id": preview_id,
                           "deleted": deleted, "receipts_tombstoned": receipts},
                )
            return {"deleted": deleted, "excluded": plan["excluded"],
                    "audit_event_id": event["id"], "receipts_tombstoned": receipts,
                    "files_deleted": 0, "compacted": False}
        except sqlite3.IntegrityError as exc:
            raise PipelineCleanupConflictError(
                "Retained records reference this history. No records were deleted."
            ) from exc
