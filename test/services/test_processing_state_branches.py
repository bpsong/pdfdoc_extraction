"""Focused coverage for processing-state classification and state helpers."""

from __future__ import annotations

import json
from unittest.mock import Mock

from modules.services.processing_state_service import (
    ProcessingStateService,
    _aggregate_progress,
    _aggregate_state,
    _children_by_parent,
    _current_step,
    _document_progress,
    _document_step_state,
    _first_split_position,
    _label_for,
    _pipeline_groups,
    _review_gate_was_skipped,
    _valid_snapshot,
    build_pipeline_snapshot,
    classify_pipeline_step,
    snapshot_from_batch,
)


def test_snapshot_config_fallbacks_and_categories() -> None:
    class BareConfig:
        def get(self, key, default=None):
            return {"pipeline": ["", 1, "rule", "archive", "cleanup", "custom"], "tasks": {"rule": {}, "archive": {}, "cleanup": {}, "custom": {}}}.get(key, default)

    snapshot = build_pipeline_snapshot(BareConfig())
    assert [step["key"] for step in snapshot["steps"]] == ["rule", "archive", "cleanup", "custom"]
    assert [step["category"] for step in snapshot["steps"]] == ["rules", "archive", "housekeeping", "custom"]
    assert build_pipeline_snapshot(Mock(get_all=lambda: {"pipeline": "bad", "tasks": []}))['step_count'] == 0
    assert _label_for("InvoiceTask") == "Invoice"
    assert _label_for("") == ""
    assert classify_pipeline_step("", "", "reference_data") == "rules"
    assert classify_pipeline_step("", "", "nanoid") == "context"
    assert classify_pipeline_step("", "", "other") == "custom"


def test_snapshot_metadata_and_pinned_version_paths() -> None:
    config = Mock(get=lambda _key, default=None: default)
    valid = {"version": 1, "steps": [{"key": "x"}], "content_hash": "hash"}
    assert snapshot_from_batch({"metadata_json": json.dumps({"pipeline_snapshot": valid})}, config) == valid
    fallback = snapshot_from_batch({"metadata_json": "[]"}, config)
    assert fallback["fallback"] is True
    assert _valid_snapshot(valid)
    assert not _valid_snapshot({"version": 2, "steps": []})

    service = object.__new__(ProcessingStateService)
    service.config_manager = config
    service.conn = Mock()
    row = {
        "id": "v1", "version_number": 2, "content_hash": "hash", "display_snapshot_json": json.dumps({"version": 1, "steps": [{"key": "x", "module": "m", "class": "C"}]}),
        "template_id": "t1", "template_key": "main", "name": "Main", "status": "active",
    }
    service.conn.execute.return_value.fetchone.return_value = row
    snapshot, identity = service._pinned_snapshot({"pipeline_version_id": "v1"})
    assert snapshot["source"] == "pinned_pipeline_version"
    assert identity["historical"] is False
    service.conn.execute.return_value.fetchone.return_value = None
    _, historical = service._pinned_snapshot({"pipeline_version_id": "missing", "pipeline_template_id": "t1"})
    assert historical["historical"] is True


def test_document_and_aggregate_state_branches() -> None:
    step = {"key": "review", "position": 1, "category": "review"}
    assert _document_step_state({"status": "failed", "current_task_key": "review"}, step, [], True) == "failed"
    assert _document_step_state({"status": "review_required", "current_task_key": "review"}, step, [], True) == "paused"
    assert _document_step_state({"status": "processing", "current_task_key": "review"}, step, [], True) == "running"
    assert _document_step_state({"status": "processing", "current_task_index": 2}, step, [], True) == "completed"
    assert _document_step_state({"status": "processing"}, step, [], True) == "pending"
    assert _document_step_state({}, step, [], False) == "skipped"
    assert _document_step_state({}, step, [{"task_key": "review", "status": "paused", "task_index": 2}], True) == "paused"
    assert _document_step_state({}, step, [{"task_key": "review", "status": "running"}], True) == "running"
    assert _document_step_state({}, step, [{"task_key": "review", "status": "completed"}], True) == "completed"
    assert _document_step_state({}, step, [{"task_key": "review", "status": "paused", "task_index": 2}, {"task_key": "later", "status": "completed", "task_index": 3}], True) == "completed"
    assert _first_split_position({"steps": [{"category": "split", "position": 2}]}) == 2
    assert _first_split_position({"steps": []}) is None
    assert _children_by_parent([{"id": "root"}, {"id": "child", "parent_document_id": "root"}]) == {"root": [{"id": "child", "parent_document_id": "root"}]}

    states = [{"state": "running", "key": "x", "applicable": True}, {"state": "pending", "key": "y", "applicable": True}]
    assert _current_step(states, {})["key"] == "x"
    assert _current_step([], {}) is None
    assert _aggregate_state([]) == "pending"
    assert _aggregate_state(["skipped"]) == "skipped"
    assert _aggregate_state(["completed", "pending"]) == "running"
    assert _aggregate_state(["pending"]) == "pending"
    assert _document_progress({"status": "processing"}, [{"state": "running", "applicable": True}]) == 75
    assert _document_progress({"status": "processing"}, []) == 10
    assert _document_progress({"status": "completed"}, []) == 100
    assert _aggregate_progress([], {"total_documents": 2, "completed_documents": 1, "failed_documents": 1}) == 100
    assert _aggregate_progress([], {"total_documents": 0}) == 0


def test_review_detail_and_pipeline_group_helpers() -> None:
    assert _review_gate_was_skipped({"status": "running"}) is False
    assert _review_gate_was_skipped({"status": "completed", "output_json": json.dumps({"review_required": False})})
    assert _review_gate_was_skipped({"status": "completed", "output_json": json.dumps({"review_gate_status": "passed"})})
    assert _review_gate_was_skipped({"status": "completed", "output_json": json.dumps({"pipeline_state": None, "review_item_id": None})})
    assert not _review_gate_was_skipped({"status": "completed", "output_json": json.dumps({"review_required": True, "pipeline_state": "paused"})})
    states = [
        {"batch": {"id": "b1"}, "pipeline": {"pipeline_version_id": "v1"}, "pipeline_snapshot": {"content_hash": "h"}, "documents": [{"id": "d1"}]},
        {"batch": {"id": "b2"}, "pipeline": {"pipeline_version_id": "v1"}, "pipeline_snapshot": {"content_hash": "h"}, "documents": []},
        {"batch": {"id": "b3"}, "pipeline": {}, "pipeline_snapshot": {"content_hash": "old"}, "documents": []},
    ]
    groups = _pipeline_groups(states)
    assert groups[0]["batch_count"] == 2
    assert groups[1]["pipeline_version_id"] is None
