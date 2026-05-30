"""Human review queue, locking, correction, and completion services."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any

from modules.config_manager import ConfigManager
from modules.db.connection import json_loads
from modules.db.repositories import AuditRepository, DocumentRepository, ExtractionRepository, ReviewRepository
from modules.services.schema_service import SchemaService


class ReviewServiceError(ValueError):
    """Raised when a review operation violates lock or validation rules."""


class ReviewService:
    """Coordinate review item lifecycle with lock enforcement."""

    def __init__(self, conn: sqlite3.Connection, config_manager: ConfigManager | None = None) -> None:
        self.conn = conn
        self.config_manager = config_manager
        self.reviews = ReviewRepository(conn)
        self.documents = DocumentRepository(conn)
        self.extractions = ExtractionRepository(conn)
        self.audit = AuditRepository(conn)

    def list_items(self, *, status: str | None = None, queue_name: str | None = None) -> list[dict[str, Any]]:
        """List review queue items."""
        return self.reviews.list_queue(status=status, queue_name=queue_name)

    def get_detail(self, review_item_id: str) -> dict[str, Any] | None:
        """Return review item with document, fields, and lock state."""
        item = self.reviews.get(review_item_id)
        if item is None:
            return None
        document_id = str(item["document_id"])
        metadata = json_loads(item.get("metadata_json"), {})
        return {
            "review_item": item,
            "metadata": metadata,
            "document": self.documents.get(document_id),
            "fields": self.extractions.get_fields(document_id),
            "lock": self.reviews.get_lock(review_item_id),
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
    ) -> dict[str, Any]:
        """Create a review item unless the same task already has one open."""
        existing = self.reviews.find_open_for_document(
            document_id,
            created_by_task_run_id=created_by_task_run_id,
        )
        if existing:
            return existing
        return self.reviews.create_review_item(
            batch_id=batch_id,
            document_id=document_id,
            queue_name=queue_name,
            reason=reason,
            scope=scope,
            created_by_task_run_id=created_by_task_run_id,
            metadata=metadata,
        )

    def claim(self, review_item_id: str, user: str, *, timeout_minutes: int | None = None) -> dict[str, Any]:
        """Claim a review item if unlocked or locked by the same user/expired."""
        item = self._require_item(review_item_id)
        self._release_expired_lock(review_item_id)
        lock = self.reviews.get_lock(review_item_id)
        if lock and lock.get("locked_by") != user:
            raise ReviewServiceError("Review item is locked by another operator.")
        timeout = timeout_minutes or self._lock_timeout_minutes()
        claimed = self.reviews.claim(review_item_id, user, timeout_minutes=timeout)
        self.documents.update_status(str(item["document_id"]), "in_review")
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
        lock = self.reviews.get_lock(review_item_id)
        if lock and lock.get("locked_by") != user:
            raise ReviewServiceError("Review item is locked by another operator.")
        self.reviews.release(review_item_id)
        self.documents.update_status(str(item["document_id"]), "review_required")
        self.audit.append(
            event_type="review_released",
            event={"released_by": user},
            batch_id=item.get("batch_id"),
            document_id=item.get("document_id"),
            review_item_id=review_item_id,
            user=user,
        )

    def save_draft(self, review_item_id: str, user: str, corrections: dict[str, Any]) -> dict[str, Any]:
        """Save draft corrections without resuming the workflow."""
        item = self._require_item(review_item_id)
        self._require_lock_owner(review_item_id, user)
        metadata = json_loads(item.get("metadata_json"), {})
        metadata["draft"] = {"user": user, "corrections": corrections, "saved_at": datetime.now(timezone.utc).isoformat()}
        self.reviews.update_metadata(review_item_id, metadata)
        self.audit.append(
            event_type="review_draft_saved",
            event={"field_keys": sorted(corrections.keys())},
            batch_id=item.get("batch_id"),
            document_id=item.get("document_id"),
            review_item_id=review_item_id,
            user=user,
        )
        return self.get_detail(review_item_id) or {}

    def diff_preview(self, review_item_id: str, corrections: dict[str, Any]) -> dict[str, Any]:
        """Return a simple field-level difference preview for corrections."""
        item = self._require_item(review_item_id)
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
    ) -> dict[str, Any]:
        """Validate and persist corrections, complete review, and optionally resume."""
        item = self._require_item(review_item_id)
        self._require_lock_owner(review_item_id, user)
        document_id = str(item["document_id"])
        metadata = json_loads(item.get("metadata_json"), {})
        schema_name = metadata.get("schema_file")
        validation_errors: list[dict[str, str]] = []
        if schema_name and self.config_manager is not None:
            validation_errors = SchemaService(self.config_manager).validate_payload(
                {**self._final_values(document_id), **corrections},
                schema_name=str(schema_name),
            )
        if validation_errors:
            raise ReviewServiceError(f"Corrections failed schema validation: {validation_errors}")

        diff = self.diff_preview(review_item_id, corrections)
        self.extractions.apply_corrections(document_id, corrections)
        metadata.pop("draft", None)
        metadata["completed_by"] = user
        metadata["completed_corrections"] = corrections
        self.reviews.update_metadata(review_item_id, metadata)
        self.reviews.complete(review_item_id, user)
        self.documents.update_status(document_id, "review_completed")
        self.audit.append(
            event_type="review_completed",
            event={"field_keys": sorted(corrections.keys()), "diff": diff},
            batch_id=item.get("batch_id"),
            document_id=document_id,
            review_item_id=review_item_id,
            user=user,
        )

        resume_triggered = False
        if trigger_resume and self.config_manager is not None:
            from modules.resume_manager import ResumeManager

            resume_triggered = ResumeManager(self.config_manager).resume_document(document_id, user=user)
        return {"review_item_id": review_item_id, "status": "completed", "resume_triggered": resume_triggered}

    def _require_item(self, review_item_id: str) -> dict[str, Any]:
        item = self.reviews.get(review_item_id)
        if item is None:
            raise ReviewServiceError("Review item not found.")
        return item

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
