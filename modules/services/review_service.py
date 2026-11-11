"""Human review queue, locking, correction, and completion services."""

from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
from pathlib import Path
import sqlite3
from typing import Any

from modules.config_protocol import ConfigProvider as ConfigManager
from modules.db.connection import atomic_transaction, json_loads
from modules.db.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    ReviewLockConflictError,
    ReviewRepository,
    TaskRunRepository,
)
from modules.services.schema_service import SchemaService
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.workflow_state_service import WorkflowStateService
from modules.services.review_business_validation import (
    build_business_report, business_report_summary, snapshot_hash,
)
from modules.services.business_validation_schema import require_business_rule_capability
from modules.services.versioned_config_contracts import canonicalize_json, content_hash


class ReviewServiceError(ValueError):
    """Raised when a review operation violates lock or validation rules."""


class ReviewBusinessError(ReviewServiceError):
    """Structured validation/conflict response without exception or secret leakage."""

    def __init__(
        self, message: str, code: str, *, status_code: int = 409,
        report: dict[str, Any] | None = None, current_revision: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail: dict[str, Any] = {"message": message, "code": code}
        if report is not None:
            self.detail["business_validation"] = report
        if current_revision is not None:
            self.detail["current_revision"] = current_revision


class _NullConfig:
    def get(self, key: str, default: Any = None) -> Any:
        return default


class ReviewService:
    """Coordinate review item lifecycle with lock enforcement."""

    def __init__(self, conn: sqlite3.Connection, config_manager: ConfigManager | None = None) -> None:
        self.conn = conn
        self.config_manager = config_manager
        self.reviews = ReviewRepository(conn)
        self.documents = DocumentRepository(conn)
        self.extractions = ExtractionRepository(conn)
        self.task_runs = TaskRunRepository(conn)
        self.audit = AuditRepository(conn)
        self.state = WorkflowStateService(conn)

    def list_items(self, *, status: str | None = None, queue_name: str | None = None) -> list[dict[str, Any]]:
        """List review queue items."""
        return [
            self._queue_item_payload(item)
            for item in self.reviews.list_queue(status=status, queue_name=queue_name)
        ]

    def list_items_page(
        self,
        *,
        limit: int = 25,
        offset: int = 0,
        filter_name: str = "all",
        queue_name: str | None = None,
        operator: str = "",
        pipeline_id: str | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        """Return a filtered and sorted review page with queue counts."""
        safe_limit = min(max(int(limit), 1), 100)
        safe_offset = max(int(offset), 0)
        safe_filter = filter_name if filter_name in {"all", "active", "unclaimed", "mine", "others", "low_confidence", "in_review", "completed"} else "all"
        safe_sort_by = sort_by if sort_by in {"document", "type", "fields", "confidence", "queue", "status", "created_at", "pipeline", "completed_at"} else "created_at"
        safe_sort_dir = "asc" if str(sort_dir).lower() == "asc" else "desc"
        status = safe_filter if safe_filter in {"in_review", "completed"} else None
        low_confidence = safe_filter == "low_confidence"
        ownership = safe_filter if safe_filter in {"active", "unclaimed", "mine", "others"} else None
        items = self.reviews.list_queue_page(
            limit=safe_limit,
            offset=safe_offset,
            status=status,
            queue_name=queue_name,
            low_confidence=low_confidence,
            search=search,
            ownership=ownership,
            operator=operator,
            pipeline_id=pipeline_id,
            sort_by=safe_sort_by,
            sort_dir=safe_sort_dir,
        )
        total = self.reviews.count_queue_page(
            status=status,
            queue_name=queue_name,
            low_confidence=low_confidence,
            search=search,
            ownership=ownership,
            operator=operator,
            pipeline_id=pipeline_id,
        )
        counts = {
            "all": self.reviews.count_queue_page(queue_name=queue_name, search=search),
            "low_confidence": self.reviews.count_queue_page(
                queue_name=queue_name, low_confidence=True, search=search
            ),
            "in_review": self.reviews.count_queue_page(
                status="in_review", queue_name=queue_name, search=search
            ),
            "completed": self.reviews.count_queue_page(
                status="completed", queue_name=queue_name, search=search
            ),
        }
        for name in ("active", "unclaimed", "mine", "others"):
            counts[name] = self.reviews.count_queue_page(
                ownership=name, operator=operator, search=search,
                queue_name=queue_name, pipeline_id=pipeline_id,
            )
        counts["completed"] = self.reviews.count_queue_page(
            status="completed", search=search, queue_name=queue_name, pipeline_id=pipeline_id,
        )
        if total and safe_offset >= total:
            return self.list_items_page(
                limit=safe_limit, offset=((total - 1) // safe_limit) * safe_limit,
                filter_name=safe_filter, queue_name=queue_name, operator=operator,
                pipeline_id=pipeline_id, search=search, sort_by=safe_sort_by, sort_dir=safe_sort_dir,
            )
        return {
            "items": [self._queue_item_payload(item) for item in items],
            "total": total,
            "counts": counts,
            "limit": safe_limit,
            "offset": safe_offset if total else 0,
            "pipelines": self.reviews.queue_pipelines(),
            "filter": safe_filter,
            "sort_by": safe_sort_by,
            "sort_dir": safe_sort_dir,
        }

    def get_detail(self, review_item_id: str) -> dict[str, Any] | None:
        """Return review item with document, fields, and lock state."""
        with atomic_transaction(self.conn):
            return self._get_detail(review_item_id)

    def _get_detail(self, review_item_id: str) -> dict[str, Any] | None:
        item = self.reviews.get(review_item_id)
        if item is None:
            return None
        document_id = str(item["document_id"])
        metadata = json_loads(item.get("metadata_json"), {})
        document = self.documents.get(document_id)
        latest_result = self.extractions.get_latest_result(document_id)
        if item.get("review_kind") == "manual_split":
            from modules.services.manual_split_service import ManualSplitReviewService
            return {"review_item": self._review_item_payload(item), "document": self._document_payload(document),
                    "metadata": metadata, "fields": [], "schema": None, "extraction": None,
                    "lock": self.reviews.get_lock(review_item_id),
                    "manual_split": ManualSplitReviewService(self.conn, self.config_manager).detail(review_item_id)}
        snapshot = self._snapshot(item)
        values = self._display_values(snapshot)
        draft = metadata.get("draft", {}).get("corrections", {})
        if isinstance(draft, dict):
            values.update(draft)
        accepted = metadata.get("business_validation", {}).get("accepted")
        report = (accepted if item.get("status") == "completed" and accepted is not None
                  else self._business_report(snapshot, values))
        return {
            "review_item": self._review_item_payload(item),
            "metadata": metadata,
            "document": self._document_payload(document),
            "extraction": {
                "provider": latest_result.get("provider"),
                "provider_job_id": latest_result.get("provider_job_id"),
                "created_at": latest_result.get("created_at"),
            }
            if latest_result
            else None,
            "fields": [self._field_payload(field) for field in self.extractions.get_fields(document_id)],
            "lock": self.reviews.get_lock(review_item_id),
            "schema": self._schema_payload(
                metadata.get("schema_file"),
                item.get("review_schema_version_id"),
            ),
            "review_revision": snapshot["revision"],
            "business_validation": report,
        }

    def create_review_item(
        self,
        *,
        batch_id: str,
        document_id: str,
        queue_name: str,
        reason: str,
        scope: str,
        created_by_task_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        review_schema_version_id: str | None = None,
        review_kind: str = "extraction",
    ) -> dict[str, Any]:
        """Create a review item unless the same task already has one open."""
        existing = self.reviews.find_open_for_document(
            document_id,
            created_by_task_run_id=created_by_task_run_id,
        )
        if existing:
            if existing.get("review_kind", "extraction") != review_kind:
                raise ReviewServiceError("Existing review type does not match the task.")
            if existing.get("review_schema_version_id") != review_schema_version_id:
                raise ReviewServiceError(
                    "Existing review item schema identity does not match the task."
                )
            return existing
        document = self.documents.get(document_id)
        task_run = (
            self.task_runs.get(str(created_by_task_run_id))
            if created_by_task_run_id
            else None
        )
        if document is None or str(document.get("batch_id")) != batch_id:
            raise ReviewServiceError(
                "Review item document identity does not match its batch."
            )
        if (
            task_run is not None
            and (
                task_run.get("document_id") != document_id
                or task_run.get("pipeline_version_id")
                != document.get("pipeline_version_id")
            )
        ):
            raise ReviewServiceError(
                "Review task run does not match the document pipeline assignment."
            )
        pipeline_version_id = document.get("pipeline_version_id")
        if review_kind not in {"extraction", "manual_split"}:
            raise ReviewServiceError("Unsupported review type.")
        if review_kind == "manual_split":
            if task_run is None or task_run.get("module_name") != "standard_step.split.manual_split" or task_run.get("class_name") != "ManualSplitTask":
                raise ReviewServiceError("Manual review requires an approved manual split task run.")
            if review_schema_version_id is not None:
                raise ReviewServiceError("Manual splitting does not use an extraction review schema.")
        if pipeline_version_id and review_kind == "extraction":
            if task_run is None or not review_schema_version_id:
                raise ReviewServiceError(
                    "Versioned review requires exact task and schema identity."
                )
            dependency = self.conn.execute(
                """
                SELECT schema_version_id
                FROM pipeline_version_schema_dependencies
                WHERE pipeline_version_id = ? AND task_key = ?
                """,
                (pipeline_version_id, task_run["task_key"]),
            ).fetchone()
            if (
                dependency is None
                or dependency["schema_version_id"]
                != review_schema_version_id
            ):
                raise ReviewServiceError(
                    "Review task schema does not match the pinned pipeline dependency."
                )
            schema_version = ReviewSchemaVersionService(self.conn).load_version(
                review_schema_version_id
            )
            if (metadata or {}).get("schema_hash") != schema_version["content_hash"]:
                raise ReviewServiceError(
                    "Review item schema hash does not match the pinned dependency."
                )
        return self.reviews.create_review_item(
            batch_id=batch_id,
            document_id=document_id,
            queue_name=queue_name,
            reason=reason,
            scope=scope,
            created_by_task_run_id=created_by_task_run_id,
            metadata=metadata,
            review_schema_version_id=review_schema_version_id,
            review_kind=review_kind,
        )

    def claim(self, review_item_id: str, user: str, *, timeout_minutes: int | None = None) -> dict[str, Any]:
        """Claim a review item if unlocked or locked by the same user/expired."""
        item = self._require_item(review_item_id)
        self._require_open_status(item)
        timeout = timeout_minutes or self._lock_timeout_minutes()
        try:
            claimed = self.reviews.claim(
                review_item_id,
                user,
                timeout_minutes=timeout,
            )
        except ReviewLockConflictError as exc:
            raise ReviewServiceError(str(exc)) from exc
        self.state.transition_document(
            str(item["document_id"]), "in_review", reason="review_claimed", user=user
        )
        self.audit.append(
            event_type="review_claimed",
            event={"locked_by": user},
            batch_id=item.get("batch_id"),
            document_id=item.get("document_id"),
            review_item_id=review_item_id,
            user=user,
        )
        return claimed

    def release(self, review_item_id: str, user: str) -> None:
        """Release a review lock held by the requesting user."""
        item = self._require_item(review_item_id)
        self._require_open_status(item)
        lock = self.reviews.get_lock(review_item_id)
        if lock and lock.get("locked_by") != user:
            raise ReviewServiceError("Review item is locked by another operator.")
        self.reviews.release(review_item_id)
        self.state.transition_document(
            str(item["document_id"]), "review_required", reason="review_released", user=user
        )
        self.audit.append(
            event_type="review_released",
            event={"released_by": user},
            batch_id=item.get("batch_id"),
            document_id=item.get("document_id"),
            review_item_id=review_item_id,
            user=user,
        )

    def save_draft(
        self, review_item_id: str, user: str, corrections: dict[str, Any], *,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """Save draft corrections without resuming the workflow."""
        with atomic_transaction(self.conn, immediate=True):
            snapshot = self._editable_snapshot(review_item_id, user)
            self._check_revision(snapshot, expected_revision)
            corrections = self._checked_corrections(snapshot, corrections)
            item = snapshot["item"]
            metadata = snapshot["metadata"]
            metadata["draft"] = {"user": user, "corrections": corrections,
                                 "saved_at": datetime.now(timezone.utc).isoformat()}
            metadata["edit_revision"] = int(metadata.get("edit_revision", 0)) + 1
            self.reviews.update_metadata(review_item_id, metadata)
            self.audit.append(
                event_type="review_draft_saved", event={"field_keys": sorted(corrections)},
                batch_id=item.get("batch_id"), document_id=item.get("document_id"),
                review_item_id=review_item_id, user=user,
            )
        return self.get_detail(review_item_id) or {}

    def revalidate(
        self, review_item_id: str, user: str, corrections: dict[str, Any], *,
        expected_revision: str | None = None, request_revision: str | int | None = None,
    ) -> dict[str, Any]:
        """Check unsaved values without saving, extending locks, or resuming work."""
        if (request_revision is not None and (
            type(request_revision) not in {str, int} or len(str(request_revision)) > 128
        )):
            raise ReviewServiceError("Invalid revalidation request revision.")
        with atomic_transaction(self.conn):
            snapshot = self._editable_snapshot(review_item_id, user)
            self._check_revision(snapshot, expected_revision)
            corrections = self._checked_corrections(snapshot, corrections)
            values = {**self._display_values(snapshot), **corrections}
        return {
            "review_revision": snapshot["revision"], "request_revision": request_revision,
            "business_validation": self._business_report(snapshot, values),
            "schema_errors": self._schema_errors(snapshot, values),
        }

    def diff_preview(self, review_item_id: str, corrections: dict[str, Any]) -> dict[str, Any]:
        """Return a simple field-level difference preview for corrections."""
        item = self._require_item(review_item_id)
        if item.get("review_kind") == "manual_split":
            raise ReviewServiceError("Use the manual split decision endpoint.")
        original = self._final_values(str(item["document_id"]))
        modified = dict(original)
        modified.update(corrections)
        changes = []
        for key in sorted(set(original) | set(modified)):
            if original.get(key) != modified.get(key):
                changes.append({"field": key, "old_value": original.get(key), "new_value": modified.get(key)})
        return {"has_changes": bool(changes), "changes": changes, "change_count": len(changes)}

    def complete(
        self,
        review_item_id: str,
        user: str,
        corrections: dict[str, Any],
        *,
        trigger_resume: bool = True,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """Validate and persist corrections, complete review, and optionally resume."""
        if trigger_resume and self.conn.in_transaction:
            raise ReviewServiceError("Commit the caller transaction before requesting workflow resume.")
        with atomic_transaction(self.conn):
            snapshot = self._editable_snapshot(review_item_id, user)
            self._check_revision(snapshot, expected_revision)
            corrections = self._checked_corrections(snapshot, corrections)
            values = {**self._display_values(snapshot), **corrections}
        # Calculate outside the write transaction, then recheck the exact source.
        report = self._business_report(snapshot, values)
        validation_errors = self._schema_errors(snapshot, values)
        if validation_errors:
            if report is not None:
                report["schema_errors"] = validation_errors
                raise ReviewBusinessError("Corrections failed schema validation.", "schema_validation_failed",
                                          status_code=422, report=report)
            raise ReviewServiceError(f"Corrections failed schema validation: {validation_errors}")
        if report is not None and report["has_blocking_findings"]:
            raise ReviewBusinessError("Resolve blocking business-validation findings before completion.",
                                      "business_validation_blocked", status_code=422, report=report)

        with atomic_transaction(self.conn, immediate=True):
            current = self._editable_snapshot(review_item_id, user)
            self._check_revision(current, snapshot["revision"])
            item = current["item"]
            document_id = str(item["document_id"])
            metadata = current["metadata"]
            diff = self.diff_preview(review_item_id, corrections)
            accepted = dict(corrections)
            if report is not None:
                # Materialize configured defaults/missing fields only when accepted.
                accepted.update({key: value for key, value in values.items()
                                 if key not in current["values"]})
            self.extractions.apply_corrections(document_id, accepted, create_missing=report is not None)
            metadata.pop("draft", None)
            metadata["completed_by"] = user
            metadata["completed_corrections"] = accepted
            if report is not None:
                metadata.setdefault("business_validation", {})["accepted"] = report
            self.reviews.update_metadata(review_item_id, metadata)
            self.reviews.complete(review_item_id, user)
            self._complete_review_task_run(item, metadata)
            self.state.transition_document(document_id, "review_completed", reason="review_completed", user=user)
            event: dict[str, Any] = {"field_keys": sorted(accepted)}
            if report is not None:
                event["business_validation"] = business_report_summary(report)
            else:
                event["diff"] = diff
            self.audit.append(event_type="review_completed", event=event, batch_id=item.get("batch_id"),
                              document_id=document_id, review_item_id=review_item_id, user=user)

        resume_triggered = False
        if trigger_resume and self.config_manager is not None:
            from modules.resume_manager import ResumeManager

            resume_triggered = ResumeManager(self.config_manager).resume_document(document_id, user=user)
        return {"review_item_id": review_item_id, "status": "completed", "resume_triggered": resume_triggered}

    def _snapshot(self, item: dict[str, Any]) -> dict[str, Any]:
        document_id = str(item["document_id"])
        fields = self.extractions.get_fields(document_id)
        latest = self.extractions.get_latest_result(document_id)
        metadata = json_loads(item.get("metadata_json"), {})
        schema: dict[str, Any] | None = None
        schema_hash = None
        schema_format = 1
        version_id = item.get("review_schema_version_id")
        if version_id:
            try:
                version = ReviewSchemaVersionService(self.conn).load_version(str(version_id))
                schema = version["schema"]
                if not isinstance(schema, dict):
                    raise ValueError("Published review form must be an object.")
                schema_hash = version["content_hash"]
                schema_format = version["format_version"]
                if metadata.get("schema_hash") != schema_hash:
                    raise ReviewServiceError("Review item schema identity is inconsistent.")
                require_business_rule_capability(schema, schema_format)
            except ReviewServiceError:
                raise
            except (KeyError, RuntimeError, ValueError) as exc:
                raise ReviewBusinessError(
                    "Pinned review form is unavailable or incompatible; verify its published version.",
                    "review_schema_unavailable", status_code=422,
                ) from exc
        elif metadata.get("schema_file") and self.config_manager is not None:
            schema = SchemaService(self.config_manager).load_schema(str(metadata["schema_file"]))
            if schema and "business_validation" in schema:
                raise ReviewBusinessError("Publish and select an exact form version to use business rules.",
                                          "review_schema_version_required", status_code=422)
        lock = self.reviews.get_lock(str(item["id"]))
        document = self.documents.get(document_id) or {}
        source_ids = [file["id"] for file in self.documents.list_files(document_id)
                      if file.get("file_type") in {"source_original", "original_pdf", "split_pdf"}]
        revision = snapshot_hash({
            "review": item, "lock": lock,
            "fields": sorted(fields, key=lambda field: field["id"]),
            "extraction_result_id": latest["id"] if latest else None,
            "pipeline_version_id": document.get("pipeline_version_id"), "source_artifact_ids": sorted(source_ids),
        })
        return {"item": item, "metadata": metadata, "schema": schema,
                "schema_hash": schema_hash, "schema_format": schema_format,
                "version_id": version_id, "revision": revision, "lock": lock,
                "source_artifact_ids": source_ids,
                "extraction_result_id": latest["id"] if latest else None,
                "values": {str(field["field_key"]): json_loads(
                    field.get("final_value_json") if field.get("final_value_json") is not None
                    else field.get("extracted_value_json")
                ) for field in fields}}

    def _editable_snapshot(self, review_item_id: str, user: str) -> dict[str, Any]:
        item = self._require_item(review_item_id)
        if item.get("review_kind") == "manual_split":
            raise ReviewServiceError("Use the manual split decision endpoint.")
        self._require_open_status(item)
        snapshot = self._snapshot(item)
        lock = snapshot["lock"]
        if lock is None or datetime.fromisoformat(str(lock["expires_at"])) <= datetime.now(timezone.utc):
            raise ReviewServiceError("Review item must be claimed before editing.")
        if lock.get("locked_by") != user:
            raise ReviewServiceError("Review item is locked by another operator.")
        return snapshot

    @staticmethod
    def _check_revision(snapshot: dict[str, Any], expected_revision: str | None) -> None:
        required = snapshot["schema"] is not None and "business_validation" in snapshot["schema"]
        if expected_revision is None and required:
            raise ReviewBusinessError("Reload the review and provide its current revision.", "review_revision_required",
                                      current_revision=snapshot["revision"])
        if expected_revision is not None and expected_revision != snapshot["revision"]:
            raise ReviewBusinessError("The review changed. Reload before saving or completing.", "stale_review",
                                      current_revision=snapshot["revision"])

    @staticmethod
    def _display_values(snapshot: dict[str, Any]) -> dict[str, Any]:
        values = deepcopy(snapshot["values"])
        schema = snapshot["schema"]
        if not schema or "business_validation" not in schema:
            return values
        for key, field in schema.get("fields", {}).items():
            if key in values:
                continue
            if field.get("default") is not None:
                value = field["default"]
            elif field.get("type") == "object":
                value = {}
            elif field.get("type") == "array":
                value = []
            elif field.get("type") == "boolean":
                value = None if field.get("required") else False
            elif field.get("type") in {"number", "integer", "float"}:
                value = None if field.get("required") else ""
            else:
                value = ""
            values[key] = deepcopy(value)
        return values

    @staticmethod
    def _checked_corrections(snapshot: dict[str, Any], corrections: Any) -> dict[str, Any]:
        if not isinstance(corrections, dict):
            raise ReviewServiceError("Corrections must be an object.")
        try:
            corrections = canonicalize_json(corrections)
        except ValueError as exc:
            raise ReviewServiceError("Corrections must contain finite JSON values.") from exc
        schema = snapshot["schema"]
        if schema and "business_validation" in schema:
            fields = schema.get("fields", {})
            allowed = set(fields) | set(snapshot["values"])
            editable = snapshot["metadata"].get("editable_fields")
            for key, value in corrections.items():
                if key not in allowed:
                    raise ReviewServiceError("Corrections contain an unavailable field.")
                if value == snapshot["values"].get(key):
                    continue
                if (isinstance(editable, list) and key not in editable) or fields.get(key, {}).get("readonly"):
                    raise ReviewServiceError("Corrections contain a field that is not editable.")
        return corrections

    def _schema_errors(self, snapshot: dict[str, Any], values: dict[str, Any]) -> list[dict[str, str]]:
        if snapshot["schema"] is not None:
            return SchemaService(self.config_manager or _NullConfig()).validate_payload(values, schema=snapshot["schema"])
        name = snapshot["metadata"].get("schema_file")
        if name and self.config_manager is not None:
            return [{"path": str(name), "message": "Schema file could not be loaded."}]
        return []

    def _business_report(self, snapshot: dict[str, Any], values: dict[str, Any]) -> dict[str, Any] | None:
        if snapshot["schema"] is None:
            return None
        document_id = str(snapshot["item"]["document_id"])
        return build_business_report(
            values, snapshot["schema"], schema_version_id=str(snapshot["version_id"] or ""),
            schema_hash=str(snapshot["schema_hash"] or ""), format_version=snapshot["schema_format"],
            document_id=document_id, extraction_result_id=snapshot["extraction_result_id"],
            review_revision=snapshot["revision"], source_artifact_ids=snapshot["source_artifact_ids"],
        )

    def evaluate_gate_rules(
        self, document_id: str, *, schema_version_id: str | None,
        schema: dict[str, Any], schema_hash: str | None, task_run_id: str | None,
    ) -> dict[str, Any] | None:
        """Evaluate/persist a gate report from authoritative extracted fields."""
        if "business_validation" not in schema:
            return None
        if not schema_version_id:
            raise ReviewServiceError("Business rules require an exact published review form.")
        with atomic_transaction(self.conn):
            version = ReviewSchemaVersionService(self.conn).load_version(schema_version_id)
            require_business_rule_capability(version["schema"], version["format_version"])
            if schema_hash != version["content_hash"] or content_hash(schema) != schema_hash:
                raise ReviewServiceError("Review gate schema identity is inconsistent.")
            fields = self.extractions.get_fields(document_id)
            latest = self.extractions.get_latest_result(document_id)
            values = {field["field_key"]: json_loads(field.get("final_value_json")) for field in fields}
            source_ids = [file["id"] for file in self.documents.list_files(document_id)
                          if file.get("file_type") in {"source_original", "original_pdf", "split_pdf"}]
            revision = self._gate_source_revision(document_id, fields, latest, source_ids)
        report = build_business_report(
            values, schema, schema_version_id=schema_version_id,
            schema_hash=str(schema_hash), format_version=version["format_version"],
            document_id=document_id, extraction_result_id=latest["id"] if latest else None,
            source_artifact_ids=source_ids,
        )
        if report is None:
            return None
        report.update(task_run_id=task_run_id, source_revision=revision)
        with atomic_transaction(self.conn, immediate=True):
            current_sources = [file["id"] for file in self.documents.list_files(document_id)
                               if file.get("file_type") in {"source_original", "original_pdf", "split_pdf"}]
            if self._gate_source_revision(
                document_id, self.extractions.get_fields(document_id),
                self.extractions.get_latest_result(document_id), current_sources,
            ) != revision:
                raise ReviewServiceError("Extracted values changed during gate validation.")
            document = self.documents.get(document_id)
            if document is None:
                raise ReviewServiceError("Document is unavailable for validation.")
            metadata = json_loads(document.get("metadata_json"), {})
            metadata["business_validation"] = {"gate": report}
            self.documents.update_metadata(document_id, metadata)
        return report

    def _gate_source_revision(
        self, document_id: str, fields: list[dict[str, Any]],
        latest: dict[str, Any] | None, source_ids: list[str],
    ) -> str:
        """Fingerprint values and their source identities before report persistence."""
        document = self.documents.get(document_id) or {}
        return snapshot_hash({
            "fields": sorted(fields, key=lambda field: field["id"]),
            "extraction_result_id": latest["id"] if latest else None,
            "source_artifact_ids": sorted(source_ids),
            "pipeline_version_id": document.get("pipeline_version_id"),
        })

    def _complete_review_task_run(self, item: dict[str, Any], metadata: dict[str, Any]) -> None:
        """Mark the paused review-gate task run completed after human approval."""
        task_run_id = item.get("created_by_task_run_id")
        if not task_run_id:
            return
        task_run = self.task_runs.get(str(task_run_id))
        if task_run is None or str(task_run.get("status") or "").lower() == "completed":
            return
        output = json_loads(task_run.get("output_json"), {})
        output.update(
            {
                "review_required": True,
                "review_gate_status": "completed",
                "review_item_id": item.get("id"),
                "review_completed_by": metadata.get("completed_by"),
            }
        )
        if metadata.get("business_validation"):
            output["business_validation"] = metadata["business_validation"]["accepted"]
        self.task_runs.mark_completed(str(task_run_id), output)

    def _require_item(self, review_item_id: str) -> dict[str, Any]:
        item = self.reviews.get(review_item_id)
        if item is None:
            raise ReviewServiceError("Review item not found.")
        return item

    @staticmethod
    def _require_open_status(item: dict[str, Any]) -> None:
        """Reject review operations after an item reaches a terminal state."""
        if item.get("status") not in {"pending", "in_review"}:
            raise ReviewServiceError("Review item is no longer available for review.")

    def _require_lock_owner(self, review_item_id: str, user: str) -> None:
        self._release_expired_lock(review_item_id)
        lock = self.reviews.get_lock(review_item_id)
        if lock is None:
            raise ReviewServiceError("Review item must be claimed before editing.")
        if lock.get("locked_by") != user:
            raise ReviewServiceError("Review item is locked by another operator.")

    def _release_expired_lock(self, review_item_id: str) -> None:
        lock = self.reviews.get_lock(review_item_id)
        if lock is None:
            return
        expires_at = datetime.fromisoformat(str(lock["expires_at"]))
        if expires_at <= datetime.now(timezone.utc):
            self.reviews.delete_lock(review_item_id)

    def _lock_timeout_minutes(self) -> int:
        if self.config_manager is None:
            return 60
        return int(self.config_manager.get("review.lock_timeout_minutes", 60))

    def _final_values(self, document_id: str) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field in self.extractions.get_fields(document_id):
            values[str(field["field_key"])] = json_loads(field.get("final_value_json"))
        return values

    def _queue_item_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        """Return a UI-ready queue item with document and confidence summary."""
        review_item = self._review_item_payload(item)
        document = self.documents.get(str(item["document_id"]))
        fields = [self._field_payload(field) for field in self.extractions.get_fields(str(item["document_id"]))]
        metadata = review_item["metadata"]

        highlighted = {
            str(key)
            for key in metadata.get("highlight_fields") or metadata.get("low_confidence_fields") or []
        }
        review_fields = [
            field for field in fields if field["field_key"] in highlighted or field.get("requires_review")
        ]
        if not review_fields and fields:
            review_fields = fields

        numeric_confidences = [
            float(field["confidence"])
            for field in review_fields
            if isinstance(field.get("confidence"), (int, float))
        ]
        field_labels = [
            str(field.get("field_alias") or field.get("field_key"))
            for field in review_fields
            if field.get("field_key")
        ]

        if item.get("review_kind") == "manual_split":
            return {**review_item, "document": self._document_payload(document), "review_field_labels": [],
                    "review_field_count": 0, "lowest_confidence": None, "lock": self.reviews.get_lock(str(item["id"]))}
        return {
            **review_item,
            "document": self._document_payload(document),
            "review_field_labels": field_labels,
            "review_field_count": len(review_fields),
            "lowest_confidence": min(numeric_confidences) if numeric_confidences else None,
            "lock": self.reviews.get_lock(str(item["id"])),
        }

    @staticmethod
    def _review_item_payload(item: dict[str, Any]) -> dict[str, Any]:
        """Return a review item row with parsed metadata."""
        payload = dict(item)
        payload["metadata"] = json_loads(item.get("metadata_json"), {})
        return payload

    @staticmethod
    def _document_payload(document: dict[str, Any] | None) -> dict[str, Any] | None:
        """Return a compact document payload for review UI screens."""
        if document is None:
            return None
        filename = document.get("original_filename") or Path(str(document.get("file_path") or "")).name
        payload = dict(document)
        payload["filename"] = filename
        payload["metadata"] = json_loads(document.get("metadata_json"), {})
        payload["preview_url"] = f"/api/documents/{document['id']}/file/pdf"
        return payload

    @staticmethod
    def _field_payload(field: dict[str, Any]) -> dict[str, Any]:
        """Return a normalized field payload for schema-driven review editing."""
        payload = dict(field)
        source = json_loads(field.get("source_json"), {})
        payload["extracted_value"] = json_loads(field.get("extracted_value_json"))
        payload["corrected_value"] = json_loads(field.get("corrected_value_json"))
        payload["has_correction"] = field.get("corrected_value_json") is not None
        payload["final_value"] = json_loads(field.get("final_value_json"))
        payload["source"] = source
        payload["confidence_details"] = source.get("confidence_details", {}) if isinstance(source, dict) else {}
        payload["requires_review"] = bool(field.get("requires_review"))
        payload["confidence_band"] = ReviewService._confidence_band(field.get("confidence"))
        return payload

    def _schema_payload(
        self,
        schema_name: Any,
        schema_version_id: Any = None,
    ) -> dict[str, Any] | None:
        """Load the normalized review schema referenced by the review metadata."""
        if schema_version_id:
            version = ReviewSchemaVersionService(self.conn).load_version(
                str(schema_version_id)
            )
            schema = version["schema"]
            return {
                "name": str(schema_version_id),
                "title": schema.get("title", "Review"),
                "description": schema.get("description", ""),
                "version": version["version_number"],
                "hash": version["content_hash"],
                "format_version": version["format_version"],
                **({"business_validation": schema["business_validation"]}
                   if "business_validation" in schema else {}),
                "fields": SchemaService(
                    self.config_manager or _NullConfig()
                )._normalize_fields(schema.get("fields", {})),
            }
        if not schema_name or self.config_manager is None:
            return None
        service = SchemaService(self.config_manager)
        schema = service.normalize_schema(str(schema_name))
        if schema is None:
            schema_path_name = Path(str(schema_name)).name
            if schema_path_name != str(schema_name):
                schema = service.normalize_schema(schema_path_name)
        return schema
    @staticmethod
    def _confidence_band(confidence: Any) -> str:
        """Map numeric confidence values to UI bands."""
        if confidence is None:
            return "missing"
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            return "missing"
        if value >= 0.9:
            return "high"
        if value >= 0.7:
            return "medium"
        return "low"
