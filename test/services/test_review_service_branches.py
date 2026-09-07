"""Focused coverage for review-service defensive and payload branches."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import modules.services.review_service as review_module
from modules.db.repositories import ReviewLockConflictError
from modules.services.review_service import ReviewService, ReviewServiceError, _NullConfig


def _service() -> ReviewService:
    service = object.__new__(ReviewService)
    service.conn = Mock()
    service.config_manager = None
    service.reviews = Mock()
    service.documents = Mock()
    service.extractions = Mock()
    service.task_runs = Mock()
    service.audit = Mock()
    service.state = Mock()
    return service


def test_detail_create_and_claim_release_error_paths(monkeypatch) -> None:
    service = _service()
    service._require_item = ReviewService._require_item.__get__(service)
    service._require_item = ReviewService._require_item.__get__(service)
    service.reviews.get.return_value = None
    assert service.get_detail("missing") is None

    item = {
        "id": "r1", "document_id": "d1", "batch_id": "b1",
        "status": "pending", "metadata_json": json.dumps({"schema_file": "x.yaml"}),
        "review_schema_version_id": None,
    }
    service.reviews.get.return_value = item
    service.documents.get.return_value = {"id": "d1", "file_path": "doc.pdf", "metadata_json": "{}"}
    service.extractions.get_latest_result.return_value = {"provider": "test", "provider_job_id": "job", "created_at": "now"}
    service.extractions.get_fields.return_value = []
    service.reviews.get_lock.return_value = None
    service._schema_payload = Mock(return_value=None)
    detail = service.get_detail("r1")
    assert detail["extraction"]["provider"] == "test"

    service.reviews.find_open_for_document.return_value = {"review_schema_version_id": "other"}
    with pytest.raises(ReviewServiceError, match="schema identity"):
        service.create_review_item(batch_id="b1", document_id="d1", queue_name="q", reason="r", scope="s", review_schema_version_id="v1")
    service.reviews.find_open_for_document.return_value = {"review_schema_version_id": "v1"}
    assert service.create_review_item(batch_id="b1", document_id="d1", queue_name="q", reason="r", scope="s", review_schema_version_id="v1")["review_schema_version_id"] == "v1"

    service.reviews.find_open_for_document.return_value = None
    service.documents.get.return_value = None
    with pytest.raises(ReviewServiceError, match="batch"):
        service.create_review_item(batch_id="b1", document_id="d1", queue_name="q", reason="r", scope="s")
    service.documents.get.return_value = {"id": "d1", "batch_id": "b1", "pipeline_version_id": None}
    service.task_runs.get.return_value = {"document_id": "other", "pipeline_version_id": "p", "task_key": "review"}
    with pytest.raises(ReviewServiceError, match="task run"):
        service.create_review_item(batch_id="b1", document_id="d1", queue_name="q", reason="r", scope="s", created_by_task_run_id="tr")

    service.documents.get.return_value = {"id": "d1", "batch_id": "b1", "pipeline_version_id": "p"}
    service.task_runs.get.return_value = None
    with pytest.raises(ReviewServiceError, match="exact task"):
        service.create_review_item(batch_id="b1", document_id="d1", queue_name="q", reason="r", scope="s")
    service.task_runs.get.return_value = {"document_id": "d1", "pipeline_version_id": "p", "task_key": "review"}
    service.conn.execute.return_value.fetchone.return_value = None
    with pytest.raises(ReviewServiceError, match="pinned pipeline"):
        service.create_review_item(batch_id="b1", document_id="d1", queue_name="q", reason="r", scope="s", created_by_task_run_id="tr", review_schema_version_id="v1")

    service.conn.execute.return_value.fetchone.return_value = {"schema_version_id": "v1"}
    monkeypatch.setattr(
        review_module,
        "ReviewSchemaVersionService",
        lambda _conn: SimpleNamespace(load_version=lambda _version_id: {"content_hash": "hash"}),
    )
    service.reviews.create_review_item.return_value = {"id": "created"}
    assert service.create_review_item(
        batch_id="b1", document_id="d1", queue_name="q", reason="r", scope="s",
        created_by_task_run_id="tr", review_schema_version_id="v1", metadata={"schema_hash": "hash"},
    ) == {"id": "created"}
    with pytest.raises(ReviewServiceError, match="schema hash"):
        service.create_review_item(
            batch_id="b1", document_id="d1", queue_name="q", reason="r", scope="s",
            created_by_task_run_id="tr", review_schema_version_id="v1", metadata={"schema_hash": "wrong"},
        )
    service.conn.execute.return_value.fetchone.return_value = {"schema_version_id": "v2"}
    with pytest.raises(ReviewServiceError, match="pinned pipeline"):
        service.create_review_item(batch_id="b1", document_id="d1", queue_name="q", reason="r", scope="s", created_by_task_run_id="tr", review_schema_version_id="v1")

    service._require_item = Mock(return_value=item)
    service.reviews.claim.side_effect = ReviewLockConflictError("busy")
    with pytest.raises(ReviewServiceError, match="busy"):
        service.claim("r1", "alice")
    service.reviews.claim.side_effect = None
    service.reviews.get_lock.return_value = {"locked_by": "bob", "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}
    with pytest.raises(ReviewServiceError, match="another operator"):
        service.release("r1", "alice")


def test_review_completion_validation_task_run_and_lock_helpers(monkeypatch) -> None:
    service = _service()
    item = {"id": "r1", "document_id": "d1", "batch_id": "b1", "status": "in_review", "metadata_json": "{}", "created_by_task_run_id": None}
    service._require_item = Mock(return_value=item)
    service._require_lock_owner = Mock()
    service._final_values = Mock(return_value={"name": "old"})
    monkeypatch.setattr(review_module.SchemaService, "validate_payload", lambda *_args, **_kwargs: [{"path": "name", "message": "bad"}])
    item["metadata_json"] = json.dumps({"schema_file": "schema.yaml"})
    service.config_manager = Mock()
    with pytest.raises(ReviewServiceError, match="Corrections failed"):
        service.complete("r1", "alice", {"name": "new"}, trigger_resume=False)

    item["metadata_json"] = "{}"
    service.config_manager = None
    service.diff_preview = Mock(return_value={"has_changes": False, "changes": [], "change_count": 0})
    service.extractions.apply_corrections = Mock()
    service.reviews.update_metadata = Mock()
    service.reviews.complete = Mock()
    service.documents.update_status = Mock()
    service.audit.append = Mock()
    result = service.complete("r1", "alice", {}, trigger_resume=False)
    assert result["resume_triggered"] is False

    item["metadata_json"] = json.dumps({"schema_version_id": "v1", "schema_hash": "wrong"})
    item["review_schema_version_id"] = "v1"
    monkeypatch.setattr(
        review_module,
        "ReviewSchemaVersionService",
        lambda _conn: SimpleNamespace(load_version=lambda _version_id: {"content_hash": "right", "schema": {}}),
    )
    with pytest.raises(ReviewServiceError, match="identity"):
        service.complete("r1", "alice", {}, trigger_resume=False)
    item["review_schema_version_id"] = None
    item["metadata_json"] = "{}"
    monkeypatch.setattr(review_module.SchemaService, "validate_payload", lambda *_args, **_kwargs: [])
    item["review_schema_version_id"] = "v1"
    item["metadata_json"] = json.dumps({"schema_hash": "right"})
    assert service.complete("r1", "alice", {}, trigger_resume=False)["status"] == "completed"
    item["review_schema_version_id"] = None
    item["metadata_json"] = "{}"

    class Resume:
        def __init__(self, _config):
            pass

        def resume_document(self, _document_id, *, user):
            return user == "alice"

    monkeypatch.setattr("modules.resume_manager.ResumeManager", Resume)
    service.config_manager = Mock()
    service.task_runs.get.return_value = None
    assert service.complete("r1", "alice", {}, trigger_resume=True)["resume_triggered"] is True

    service._complete_review_task_run(item, {})
    item["created_by_task_run_id"] = "tr1"
    service.task_runs.get.return_value = None
    service._complete_review_task_run(item, {})
    service.task_runs.get.return_value = {"status": "completed"}
    service._complete_review_task_run(item, {})
    service.task_runs.get.return_value = {"status": "paused", "output_json": json.dumps({"old": True})}
    service._complete_review_task_run(item, {"completed_by": "alice"})
    service.task_runs.mark_completed.assert_called_once()

    service._require_item = ReviewService._require_item.__get__(service)
    service.reviews.get.return_value = None
    with pytest.raises(ReviewServiceError, match="not found"):
        service._require_item("missing")
    service.reviews.get.return_value = {"id": "r1"}
    assert service._require_item("r1")["id"] == "r1"
    with pytest.raises(ReviewServiceError, match="no longer"):
        service._require_open_status({"status": "completed"})
    service.reviews.get_lock.return_value = None
    service._release_expired_lock("r1")
    with pytest.raises(ReviewServiceError, match="claimed"):
        ReviewService._require_lock_owner(service, "r1", "alice")
    service.reviews.get_lock.return_value = {"locked_by": "bob", "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}
    with pytest.raises(ReviewServiceError, match="another"):
        ReviewService._require_lock_owner(service, "r1", "alice")
    service.reviews.get_lock.return_value = {"locked_by": "alice", "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
    service._release_expired_lock("r1")
    service.reviews.delete_lock.assert_called_with("r1")
    service.config_manager = None
    assert service._lock_timeout_minutes() == 60
    service.config_manager = Mock()
    service.config_manager.get.return_value = 15
    assert service._lock_timeout_minutes() == 15
    service.extractions.get_fields.return_value = [{"field_key": "x", "final_value_json": "1"}]
    assert ReviewService._final_values(service, "d1") == {"x": 1}
    assert _NullConfig().get("anything", "fallback") == "fallback"


def test_review_payload_schema_and_confidence_branches(monkeypatch) -> None:
    service = _service()
    service.reviews.list_queue.return_value = []
    assert service.list_items() == []
    assert service._review_item_payload({"metadata_json": "{}"})["metadata"] == {}
    assert service._document_payload(None) is None
    document = {"id": "d1", "file_path": r"C:\docs\invoice.pdf", "metadata_json": "{}"}
    assert service._document_payload(document)["filename"] == "invoice.pdf"
    field = {"field_key": "x", "source_json": json.dumps({"confidence_details": {"model": 1}}), "extracted_value_json": "1", "corrected_value_json": "null", "final_value_json": "1", "requires_review": 1, "confidence": 0.95}
    assert service._field_payload(field)["confidence_band"] == "high"
    assert ReviewService._field_payload({"field_key": "x", "source_json": "null", "confidence": "not-number"})["confidence_band"] == "missing"
    assert [ReviewService._confidence_band(value) for value in (None, "bad", 0.5, 0.8, 0.95)] == ["missing", "missing", "low", "medium", "high"]

    service.documents.get.return_value = document
    service.extractions.get_fields.return_value = [
        {"field_key": "a", "field_alias": "Alias", "confidence": 0.4, "requires_review": False, "source_json": "{}"},
        {"field_key": "b", "confidence": "unknown", "requires_review": False, "source_json": "{}"},
    ]
    service.reviews.get_lock.return_value = None
    queue_item = {"id": "r1", "document_id": "d1", "metadata_json": json.dumps({"low_confidence_fields": ["a"]})}
    payload = service._queue_item_payload(queue_item)
    assert payload["review_field_count"] == 1
    service.extractions.get_fields.return_value = [{"field_key": "a", "confidence": 0.8, "requires_review": False, "source_json": "{}"}]
    queue_item["metadata_json"] = "{}"
    assert service._queue_item_payload(queue_item)["lowest_confidence"] == 0.8

    monkeypatch.setattr(review_module.ReviewSchemaVersionService, "load_version", lambda *_args: {"schema": {"title": "Invoice", "fields": {}}, "version_number": 2, "content_hash": "hash"})
    monkeypatch.setattr(review_module.SchemaService, "_normalize_fields", lambda *_args: [{"name": "x"}])
    assert service._schema_payload("ignored", "v2")["version"] == 2
    service.config_manager = None
    assert service._schema_payload(None) is None
    service.config_manager = Mock()
    fake_schema = Mock()
    fake_schema.normalize_schema.side_effect = [None, {"title": "Fallback"}]
    monkeypatch.setattr(review_module, "SchemaService", lambda *_args: fake_schema)
    assert service._schema_payload("folder/schema.yaml")["title"] == "Fallback"


def test_save_draft_and_diff_preview_use_normalized_fields() -> None:
    service = _service()
    item = {"id": "r1", "document_id": "d1", "batch_id": "b1", "metadata_json": json.dumps({"existing": True})}
    service._require_item = Mock(return_value=item)
    service._require_lock_owner = Mock()
    service.reviews.update_metadata = Mock()
    service.audit.append = Mock()
    service.get_detail = Mock(return_value={"ok": True})
    assert service.save_draft("r1", "alice", {"name": "new"}) == {"ok": True}
    saved = service.reviews.update_metadata.call_args.args[1]
    assert saved["draft"]["corrections"] == {"name": "new"}

    service._final_values = Mock(return_value={"a": 1, "b": 2})
    preview = service.diff_preview("r1", {"a": 3, "c": 4})
    assert preview["change_count"] == 2
# pyright: reportOptionalSubscript=false
