"""Local manual splitting and immutable operator boundary decisions."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import sqlite3
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from modules.config_protocol import ConfigProvider
from modules.db.connection import immediate_transaction, json_dumps, json_loads, managed_connect
from modules.db.repositories import AuditRepository, DocumentRepository, ManualSplitRepository, ReviewRepository, TaskRunRepository
from modules.exceptions import TaskError
from modules.services.artifact_service import register_document_artifact
from modules.services.review_service import ReviewService, ReviewServiceError
from modules.services.split_execution_service import SplitExecutionService, create_split_pdf
from modules.services.workflow_state_service import WorkflowStateService
from modules.split_models import SplitResult, SplitSegment


def validate_boundaries(value: Any, page_count: int) -> list[int]:
    """Reject non-integral, duplicate, unordered, or out-of-range boundaries."""
    if not isinstance(value, list) or any(type(page) is not int or not 1 <= page < page_count for page in value):
        raise ReviewServiceError("Boundaries must be integer page numbers between 1 and the penultimate page.")
    if value != sorted(set(value)):
        raise ReviewServiceError("Boundaries must be unique and in page order.")
    return value


def split_ranges(boundaries: list[int], page_count: int) -> list[dict[str, int]]:
    """Derive an ordered, exhaustive contiguous partition of the source PDF."""
    points = [0, *boundaries, page_count]
    return [{"start": start + 1, "end": end} for start, end in zip(points, points[1:])]


def source_identity(file_path: str) -> tuple[str, int]:
    """Read the local source fingerprint and verified PDF page count."""
    with Path(file_path).open("rb") as source:
        fingerprint = hashlib.file_digest(source, "sha256").hexdigest()
        source.seek(0)
        reader = PdfReader(source)
        if reader.is_encrypted:
            raise TaskError("Manual splitting requires an unencrypted PDF.")
        page_count = len(reader.pages)
    if not page_count:
        raise TaskError("Cannot split an empty PDF.")
    return fingerprint, page_count


def _review_source_identity(file_path: str) -> tuple[str, int]:
    try:
        return source_identity(file_path)
    except (OSError, ValueError, TaskError, PdfReadError) as exc:
        raise ReviewServiceError("Unable to verify the source PDF. Restore or re-ingest it before continuing.") from exc


def is_completed_cleanup(run: dict[str, Any]) -> bool:
    """Identify successful runner housekeeping, which does not start business work."""
    return (
        run.get("task_key") == "cleanup_task"
        and run.get("module_name") == "standard_step.housekeeping.cleanup_task"
        and run.get("class_name") == "CleanupTask"
        and run.get("status") == "completed"
    )


class ManualSplitService:
    """Coordinate local skip, human pause, and approved split application."""

    def __init__(self, conn: sqlite3.Connection, config: ConfigProvider) -> None:
        self.conn = conn
        self.config = config
        self.decisions = ManualSplitRepository(conn)
        self.documents = DocumentRepository(conn)

    def execute(self, context: dict[str, Any], *, enabled: bool, split_dir: Path, queue_name: str) -> dict[str, Any]:
        """Apply a version-pinned decision, or create one durable review pause."""
        document = self.documents.get(str(context["document_id"]))
        if document is None or document.get("pipeline_version_id") != context["pipeline_version_id"]:
            raise TaskError("Manual split document pipeline identity does not match.")
        if document.get("parent_document_id"):
            context.setdefault("data", {})["split_result"] = {"status": "skipped", "reason": "child_document", "children": []}
            return context
        fingerprint, page_count = source_identity(str(context["file_path"]))
        with immediate_transaction(self.conn):
            decision = self.decisions.get_for_task(str(document["id"]), str(document["pipeline_version_id"]), str(context["current_task_key"]))
            if decision is None:
                checkpoint = {"data": context.get("data", {}), "metadata": {"inherited_context": context.get("metadata", {}).get("inherited_context")}}
                if len(json_dumps(checkpoint).encode("utf-8")) > 1_000_000:
                    raise TaskError("Manual split business context exceeds the checkpoint limit.")
                decision = self.decisions.create(context=context, source_sha256=fingerprint, page_count=page_count, checkpoint=checkpoint)
            if decision["source_sha256"] != fingerprint or decision["page_count"] != page_count:
                raise TaskError("The source PDF changed after the manual split request. Re-ingest the correct source.")
            if not enabled or page_count == 1:
                if decision["action"] is None:
                    self.decisions.save(decision["id"], [], decision["revision"], action="skip", reason="single_page" if enabled else "disabled")
                    decision = self.decisions.get_for_task(document["id"], document["pipeline_version_id"], context["current_task_key"]) or decision
            source_artifact = register_document_artifact(self.config, context, connection=self.conn, file_type="source_original", file_path=context["file_path"])
            if decision["action"] is None:
                review = ReviewService(self.conn, self.config).create_review_item(
                    batch_id=str(document["batch_id"]), document_id=str(document["id"]),
                    queue_name=queue_name, reason="manual_split", scope="document",
                    review_kind="manual_split", created_by_task_run_id=str(decision["task_run_id"]),
                    metadata={"decision_id": decision["id"], "page_count": page_count, "contract_version": 1},
                )
                self.decisions.attach_review(decision["id"], review["id"])
                metadata = json_loads(document.get("metadata_json"), {})
                metadata["split_result"] = {"outcome": "manual_review_pending", "provider": "manual", "decision_id": decision["id"]}
                self.documents.update_metadata(document["id"], metadata)
                WorkflowStateService(self.conn).transition_document(document["id"], "review_required", reason="manual_split")
                context.update(pipeline_state="paused", review_required=True, review_item_id=review["id"])
                return context
            context["manual_split_decision_id"] = decision["id"]
            if decision["action"] == "skip":
                result = {"status": "skipped", "reason": decision["skip_reason"], "children": [], "decision_id": decision["id"]}
                self._save_outcome(document, decision, result)
                context.setdefault("data", {})["split_result"] = result
                return context
            boundaries = validate_boundaries(json_loads(decision["boundaries_json"], []), page_count)
            if not boundaries:
                raise TaskError("An approved split must contain at least one boundary.")
            ranges = split_ranges(boundaries, page_count)
            children = self.documents.list_children(document["id"])
            if children:
                if len(children) != len(ranges) or any(
                    json_loads(child.get("metadata_json"), {}).get("manual_split_decision_id") != decision["id"]
                    or child.get("pipeline_version_id") != document["pipeline_version_id"]
                    for child in children
                ):
                    raise TaskError("Existing split children do not match the approved decision; recovery is required.")
                child_ids = [child["id"] for child in children]
            else:
                self.decisions.set_phase(decision["id"], "applying")
                segments = [SplitSegment(document.get("document_type"), None, list(range(r["start"], r["end"] + 1)), r["start"], r["end"], {}) for r in ranges]
                context.setdefault("metadata", {})["inherited_context"] = json_loads(decision["checkpoint_json"], {}).get("data", {})
                child_ids = SplitExecutionService(self.config, split_dir, context["current_task_key"], create_split_pdf)._create_children(
                    documents=self.documents, document=document, context=context,
                    split_result=SplitResult(None, "completed", segments, {}), source_artifact=source_artifact or {},
                )
            result = {"status": "split_completed", "children": child_ids, "decision_id": decision["id"], "provider": "manual"}
            self._save_outcome(document, decision, result)
            WorkflowStateService(self.conn).transition_document(document["id"], "split_completed", reason="manual_split_completed")
        context.update(split_children=child_ids, fan_out_start_task_index=int(context["current_task_index"]) + 1, pipeline_state="fan_out")
        context.setdefault("data", {})["split_result"] = result
        return context

    def _save_outcome(self, document: dict[str, Any], decision: dict[str, Any], result: dict[str, Any]) -> None:
        metadata = json_loads(document.get("metadata_json"), {})
        previous = metadata.get("split_result")
        metadata["split_result"] = {**result, "outcome": result["status"], "task_key": decision["task_key"], "provider": "manual"}
        self.documents.update_metadata(document["id"], metadata)
        self.decisions.set_phase(decision["id"], "applied")
        if previous != metadata["split_result"]:
            AuditRepository(self.conn).append(event_type="manual_split_applied", event={"decision_id": decision["id"], "outcome": result["status"], "reason": result.get("reason"), "child_count": len(result["children"])}, batch_id=document["batch_id"], document_id=document["id"])


class ManualSplitReviewService:
    """Validate locked draft/approval writes without touching extracted fields."""

    def __init__(self, conn: sqlite3.Connection, config: ConfigProvider | None = None) -> None:
        self.conn, self.config = conn, config
        self.decisions = ManualSplitRepository(conn)
        self.review = ReviewService(conn, config)

    def detail(self, review_id: str) -> dict[str, Any]:
        decision = self.decisions.get_for_review(review_id)
        if decision is None:
            raise ReviewServiceError("Manual split decision not found.")
        boundaries = json_loads(decision["boundaries_json"], [])
        pending_child = self.conn.execute(
            """SELECT 1 FROM documents child WHERE child.parent_document_id=?
            AND child.status='queued' AND NOT EXISTS
            (SELECT 1 FROM task_runs WHERE document_id=child.id) LIMIT 1""",
            (decision["document_id"],),
        ).fetchone()
        document = self.review.documents.get(decision["document_id"])
        active_attempt = bool(document and document["status"] == "resuming") or any(
            run["status"] in {"started", "running"}
            for run in self.review.task_runs.list_by_document(decision["document_id"])
        )
        can_retry = bool(not active_attempt and decision["action"] and (decision["phase"] != "applied" or pending_child))
        return {"decision_id": decision["id"], "page_count": decision["page_count"], "boundaries": boundaries, "segments": split_ranges(boundaries, decision["page_count"]), "revision": decision["revision"], "action": decision["action"], "phase": decision["phase"], "skip_reason": decision["skip_reason"], "can_retry": can_retry}

    def save(self, review_id: str, user: str, payload: dict[str, Any], *, complete: bool = False) -> dict[str, Any]:
        with immediate_transaction(self.conn):
            item = self.review._require_item(review_id)
            if item.get("review_kind") != "manual_split":
                raise ReviewServiceError("This item is not a manual split review.")
            decision = self.decisions.get_for_review(review_id)
            if decision is None:
                raise ReviewServiceError("Manual split decision not found.")
            boundaries = validate_boundaries(payload.get("boundaries"), decision["page_count"])
            action = payload.get("action") if complete else None
            if complete and (not isinstance(action, str) or action not in {"split", "skip"} or (action == "split") != bool(boundaries)):
                raise ReviewServiceError("Choose split with boundaries, or skip with an empty boundary list.")
            if decision["action"] is not None:
                if complete and decision["decided_by"] == user and action == decision["action"] and boundaries == json_loads(decision["boundaries_json"], []):
                    return {"review_item_id": review_id, "document_id": item["document_id"], "status": "completed", "manual_split": self.detail(review_id)}
                raise ReviewServiceError("This decision is already final.")
            self.review._require_open_status(item)
            self.review._require_lock_owner(review_id, user)
            document = self.review.documents.get(item["document_id"])
            task_run = self.review.task_runs.get(decision["task_run_id"])
            if (document is None or task_run is None
                    or document.get("pipeline_version_id") != decision["pipeline_version_id"]
                    or task_run.get("pipeline_version_id") != decision["pipeline_version_id"]
                    or task_run.get("document_id") != document["id"]
                    or task_run.get("task_key") != decision["task_key"]
                    or task_run.get("task_index") != decision["task_index"]
                    or task_run.get("module_name") != "standard_step.split.manual_split"
                    or task_run.get("class_name") != "ManualSplitTask"):
                raise ReviewServiceError("Manual split task identity is inconsistent.")
            if complete:
                fingerprint, count = _review_source_identity(document["file_path"])
                if fingerprint != decision["source_sha256"] or count != decision["page_count"]:
                    raise ReviewServiceError("The PDF changed after review started; re-ingest it.")
            revision = payload.get("expected_revision")
            if type(revision) is not int or not self.decisions.save(decision["id"], boundaries, revision, action=action, reason="operator_no_split" if action == "skip" else None, user=user if complete else None):
                raise ReviewServiceError("This draft changed. Reload before saving or completing.")
            if complete:
                self.review.reviews.complete(review_id, user)
                self.review.task_runs.mark_completed(decision["task_run_id"], {"phase": "decision_accepted", "manual_split_decision_id": decision["id"], "review_item_id": review_id})
                self.review.state.transition_document(item["document_id"], "review_completed", reason="manual_split_decision", user=user)
            self.review.audit.append(event_type="manual_split_approved" if complete else "manual_split_draft_saved", event={"decision_id": decision["id"], "boundaries": boundaries, "action": action}, batch_id=item["batch_id"], document_id=item["document_id"], review_item_id=review_id, user=user)
        return {"review_item_id": review_id, "document_id": item["document_id"], "status": "completed" if complete else item["status"], "manual_split": self.detail(review_id)}


def continue_manual_split(config: ConfigProvider, document_id: str, user: str) -> None:
    """Run an accepted continuation after its HTTP acknowledgment is sent."""
    from modules.resume_manager import ResumeManager

    try:
        ResumeManager(config).resume_document(document_id, user=user)
    except Exception as exc:
        # The decision is already committed. Preserve it for recovery and do
        # not expose provider messages or make approval appear to have failed.
        logging.getLogger(__name__).error(
            "Manual split continuation failed for document %s (%s)",
            document_id, type(exc).__name__,
        )


def recover_manual_split(config: ConfigProvider, review_id: str, user: str) -> dict[str, Any]:
    """Retry accepted application or undispatched children, never started work."""
    with managed_connect(config) as conn, immediate_transaction(conn):
        item = ReviewRepository(conn).get(review_id)
        decision = ManualSplitRepository(conn).get_for_review(review_id)
        if not item or not decision or item["status"] != "completed" or not decision["action"]:
            raise ReviewServiceError("An accepted manual split decision is required.")
        documents = DocumentRepository(conn)
        document = documents.get(decision["document_id"])
        if not document:
            raise ReviewServiceError("Source document is missing.")
        fingerprint, count = _review_source_identity(document["file_path"])
        if fingerprint != decision["source_sha256"] or count != decision["page_count"]:
            raise ReviewServiceError("The source PDF changed. Re-ingest the correct source.")
        runs = TaskRunRepository(conn).list_by_document(document["id"])
        if any(run["status"] in {"started", "running"} for run in runs):
            raise ReviewServiceError("An application attempt may still be active. Operator repair is required before retrying.")
        children = documents.list_children(document["id"])
        if not children:
            if decision["phase"] == "applied":
                return {"resumed": False, "message": "The original document already continued."}
            if document["status"] == "resuming":
                raise ReviewServiceError("A continuation has already been claimed. Operator repair is required before retrying.")
            if any(int(run.get("task_index") or 0) > decision["task_index"] and not is_completed_cleanup(run) for run in runs):
                raise ReviewServiceError("Downstream work has already started; it cannot be replayed here.")
            WorkflowStateService(conn).transition_document(document["id"], "review_completed", reason="manual_split_recovery", user=user)
            pending_ids = None
        else:
            if decision["phase"] != "applied":
                raise ReviewServiceError("Partial or in-progress application needs operator repair.")
            expected = split_ranges(json_loads(decision["boundaries_json"], []), count)
            children.sort(key=lambda child: child["page_start"])
            if len(children) != len(expected):
                raise ReviewServiceError("The persisted child set is incomplete; operator repair is required.")
            pending_ids = []
            for child, segment in zip(children, expected):
                metadata = json_loads(child.get("metadata_json"), {})
                if (metadata.get("manual_split_decision_id") != decision["id"]
                        or child["pipeline_version_id"] != decision["pipeline_version_id"]
                        or child["page_start"] != segment["start"] or child["page_end"] != segment["end"]
                        or not Path(child["file_path"]).is_file()):
                    raise ReviewServiceError("The child manifest is inconsistent; operator repair is required.")
                child_runs = TaskRunRepository(conn).list_by_document(child["id"])
                if child["status"] == "queued" and not child_runs:
                    pending_ids.append(child["id"])
            if not pending_ids:
                return {"resumed": False, "message": "No unstarted child workflows remain."}
        AuditRepository(conn).append(event_type="manual_split_recovery_requested", event={"decision_id": decision["id"], "pending_child_count": len(pending_ids or [])}, document_id=document["id"], batch_id=document["batch_id"], review_item_id=review_id, user=user)
    if pending_ids is None:
        from modules.resume_manager import ResumeManager
        resumed = ResumeManager(config).resume_document(document["id"], user=user)
    else:
        from modules.workflow_manager import WorkflowManager
        WorkflowManager(config)._trigger_child_workflows({
            "id": document["id"], "document_id": document["id"],
            "batch_id": document["batch_id"],
            "split_children": pending_ids,
            "fan_out_start_task_index": decision["task_index"] + 1,
            "manual_split_decision_id": decision["id"],
        })
        resumed = True
    return {"resumed": resumed}
