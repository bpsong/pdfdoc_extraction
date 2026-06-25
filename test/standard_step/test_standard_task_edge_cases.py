from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from modules.exceptions import TaskError
from standard_step.review.review_gate import ReviewGateTask
from standard_step.rules.update_reference import (
    UpdateReferenceTask,
    _coerce_to_float,
    _keywords_all_match,
    _normalize_string,
)
from standard_step.split.llamacloud_split import (
    LlamaCloudSplitTask,
    create_split_pdf,
)
from standard_step.split.llamacloud_split_adapter import (
    LlamaCloudSplitAdapter,
    _get_attr,
    _json_safe,
)
from test.helpers_sqlite import TempConfig


def test_review_gate_no_document_and_validation_edges(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3", {})
    task = ReviewGateTask(config)
    context = {}

    assert task.run(context)["review_gate_status"] == "passed"

    task.confidence_threshold = 2
    with pytest.raises(TaskError, match="between 0 and 1"):
        task.validate_required_fields({})
    task.confidence_threshold = 0.8
    task.field_threshold_overrides = {"field": -1}
    with pytest.raises(TaskError, match="field"):
        task.validate_required_fields({})


def test_review_gate_reason_metadata_and_nested_confidence_edges(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "review.yaml").write_text(
        "fields:\n  required:\n    type: string\n    required: true\n",
        encoding="utf-8",
    )
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"schema": {"directories": [str(schema_dir)]}},
    )
    task = ReviewGateTask(
        config,
        always_review=True,
        split_confidence_levels_requiring_review=["low"],
        require_review_for_missing_required_fields=False,
        require_review_when_missing_confidence=True,
        schema_file="review.yaml",
        review_scope="low_confidence_fields",
        allow_operator_to_edit_high_confidence_fields=False,
        per_document_type_thresholds={"invoice": 0.9},
    )
    fields = [
        {
            "field_key": "required",
            "confidence": None,
            "final_value_json": "null",
            "source_json": "{}",
        },
        {
            "field_key": "optional",
            "confidence": 0.95,
            "final_value_json": '"value"',
            "source_json": "{}",
        },
    ]
    context = {
        "split_confidence": "low",
        "review_flags": {"business": True, "ignored": False},
        "data": {},
        "document_type": "invoice",
    }

    reasons, highlights = task._review_reasons(context, fields, {})
    metadata = task._review_metadata(context, fields, reasons, highlights, {})

    assert {reason["reason"] for reason in reasons} >= {
        "always_review",
        "split_confidence",
        "missing_confidence",
        "business_rule",
    }
    assert metadata["editable_fields"] == highlights
    assert ReviewGateTask._threshold_map([]) == {}
    assert ReviewGateTask._required_schema_fields({"fields": []}) == set()
    assert task._threshold_for_field("required", context, {}) == 0.9

    nested_fields = [
        {
            "field_key": "items",
            "source_json": (
                '{"confidence_details":{"nested_confidences":'
                '{"0.a":{"confidence":0.2},"0.b":{"confidence":null},'
                '"0.c":{"confidence":"bad"},"0.d":"bad"}}}'
            ),
        }
    ]
    paths = ReviewGateTask._low_confidence_paths(
        nested_fields,
        [{"reason": "low_confidence", "field_key": "items", "threshold": 0.5}],
    )
    assert paths == ["items.0.a"]


def test_update_reference_helper_and_validation_edges(tmp_path, monkeypatch):
    assert _normalize_string(123) == "123"
    assert _coerce_to_float(None) is None
    assert _coerce_to_float("1,000") == 1000.0
    assert _coerce_to_float("bad") is None
    assert _keywords_all_match("Alpha Beta", ["alpha", "beta"]) is True
    assert _keywords_all_match("Alpha", ["alpha", "beta"]) is False

    base = {
        "reference_file": str(tmp_path / "reference.csv"),
        "update_field": "status",
        "csv_match": {
            "type": "column_equals_all",
            "clauses": [{"column": "id", "from_context": "id"}],
        },
    }
    with pytest.raises(TaskError, match="number must be boolean"):
        UpdateReferenceTask(
            Mock(),
            **{
                **base,
                "csv_match": {
                    "type": "column_equals_all",
                    "clauses": [
                        {"column": "id", "from_context": "id", "number": "yes"}
                    ],
                },
            },
        )
    missing_reference = UpdateReferenceTask(
        Mock(),
        update_field="status",
        csv_match=base["csv_match"],
    )
    with pytest.raises(TaskError, match="reference_file"):
        missing_reference.validate_required_fields({})
    Path(base["reference_file"]).write_text("id,status\n1,\n", encoding="utf-8")
    missing_field = UpdateReferenceTask(
        Mock(),
        reference_file=base["reference_file"],
        csv_match=base["csv_match"],
    )
    with pytest.raises(TaskError, match="update_field"):
        missing_field.validate_required_fields({})

    task = UpdateReferenceTask(Mock(), **base)
    assert task._build_selection_mask(pd.DataFrame(), {"data": {}}).empty
    frame = pd.DataFrame({"id": ["1,000", "2"], "status": ["", ""]})
    task.clauses[0].number = True
    assert task._build_selection_mask(frame, {"data": {"id": 1000}}).tolist() == [
        True,
        False,
    ]

    monkeypatch.setattr(task, "validate_required_fields", lambda context: None)
    monkeypatch.setattr(
        "standard_step.rules.update_reference.pd.read_csv",
        Mock(side_effect=RuntimeError("read failed")),
    )
    result = task.run({"id": "doc", "data": {"id": 1}})
    assert result["error_step"] == "UpdateReferenceTask"


def test_split_task_validation_and_disabled_run(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3", {})
    task = LlamaCloudSplitTask(config, enabled=False)
    with pytest.raises(TaskError, match="split_dir"):
        task.validate_required_fields({})

    task.split_dir = tmp_path
    assert task.run({})["data"]["split_result"]["status"] == "skipped"

    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-")
    enabled = LlamaCloudSplitTask(
        config,
        enabled=True,
        split_dir=str(tmp_path),
        allow_uncategorized="bad",
    )
    with pytest.raises(TaskError, match="allow_uncategorized"):
        enabled.validate_required_fields({})
    enabled.allow_uncategorized = "include"
    with pytest.raises(TaskError, match="batch_id"):
        enabled.validate_required_fields({})
    with pytest.raises(TaskError, match="file_path"):
        enabled.validate_required_fields({"batch_id": "b", "document_id": "d"})
    with pytest.raises(TaskError, match="does not exist"):
        enabled.validate_required_fields(
            {"batch_id": "b", "document_id": "d", "file_path": "missing.pdf"}
        )
    with pytest.raises(TaskError, match="api_key"):
        enabled.validate_required_fields(
            {"batch_id": "b", "document_id": "d", "file_path": str(source)}
        )
    enabled.api_key = "key"
    with pytest.raises(TaskError, match="categories"):
        enabled.validate_required_fields(
            {"batch_id": "b", "document_id": "d", "file_path": str(source)}
        )

    with pytest.raises(TaskError, match="without pages"):
        create_split_pdf(str(source), str(tmp_path / "out.pdf"), [])


def test_split_adapter_errors_normalization_and_json_helpers(monkeypatch):
    with pytest.raises(TaskError, match="api_key"):
        LlamaCloudSplitAdapter(api_key="").split_pdf("file.pdf", [{"name": "x"}])
    with pytest.raises(TaskError, match="categories"):
        LlamaCloudSplitAdapter(api_key="key").split_pdf("file.pdf", [])

    adapter = LlamaCloudSplitAdapter(
        api_key="key",
        project_id="project",
        organization_id="organization",
        configuration_id="config",
        timeout_seconds=0,
    )
    assert adapter._request_scope() == {
        "project_id": "project",
        "organization_id": "organization",
    }

    failed = SimpleNamespace(id="job", status="failed", error="bad")
    with pytest.raises(TaskError, match="status failed"):
        adapter._wait_for_completion(None, failed, {})
    timed = SimpleNamespace(id="job", status="processing")
    with pytest.raises(TaskError, match="timed out"):
        adapter._wait_for_completion(None, timed, {})
    missing_id = LlamaCloudSplitAdapter(api_key="key", timeout_seconds=100)
    monkeypatch.setattr(
        "standard_step.split.llamacloud_split_adapter.time.monotonic",
        Mock(side_effect=[0, 0]),
    )
    with pytest.raises(TaskError, match="job id"):
        missing_id._wait_for_completion(
            None,
            SimpleNamespace(status="processing"),
            {},
        )

    response = {
        "id": "job",
        "status": "completed",
        "result": {
            "segments": [
                {"pages": []},
                {"pages": [1], "category": None, "confidence_category": None},
            ]
        },
    }
    result = adapter._normalize_response(response)
    assert len(result.segments) == 1
    with pytest.raises(TaskError, match="non-positive"):
        adapter._normalize_response(
            {"result": {"segments": [{"pages": [0]}]}}
        )

    assert _get_attr(None, "x", "default") == "default"
    assert _get_attr({"x": 1}, "x") == 1
    assert _json_safe(date(2026, 1, 1)) == "2026-01-01"

    class Legacy:
        __slots__ = ()

        def dict(self):
            raise TypeError

        def __str__(self):
            return "legacy"

    assert _json_safe(Legacy()) == "legacy"
