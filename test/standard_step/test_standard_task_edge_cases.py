from datetime import date
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from pypdf import PdfWriter

from modules.exceptions import TaskError
from standard_step.review.review_gate import ReviewGateTask
import standard_step.review.review_gate as review_module
import standard_step.rules.update_reference as update_module
from standard_step.rules.update_reference import (
    UpdateReferenceTask,
    _coerce_to_float,
    _keywords_all_match,
    _normalize_string,
)
from standard_step.split.llamacloud_split import (
    LlamaCloudSplitTask,
    SplitResult,
    SplitSegment,
    create_split_pdf,
)
import standard_step.split.llamacloud_split as split_module
from standard_step.split.llamacloud_split_adapter import (
    LlamaCloudSplitAdapter,
    _get_attr,
    _json_safe,
)
from standard_step.split.llamacloud_split_adapter import _json_safe as split_json_safe
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
    task.field_threshold_overrides = {"field": -1.0}
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
    assert ReviewGateTask._low_confidence_paths(
        [{"field_key": "other", "source_json": "{}"}],
        [{"reason": "low_confidence", "field_key": "items", "threshold": 0.5}],
    ) == []


def test_review_gate_schema_and_business_flag_normalization(tmp_path, monkeypatch):
    task = ReviewGateTask(
        TempConfig(tmp_path / "state.sqlite3", {}),
        _review_schema={"fields": {"name": {"type": "str"}}},
        _review_schema_hash="hash",
        schema_version_id="v1",
        require_review_for_missing_required_fields=False,
    )
    monkeypatch.setattr(
        review_module.SchemaService,
        "validate_payload",
        lambda *_args, **_kwargs: [
            {"path": "name", "message": "Required field is missing"},
            {"path": "name.detail", "message": "Invalid value"},
        ],
    )
    reasons, highlights = task._review_reasons(
        {"data": ["not-a-map"], "review_flags": [{"flag": "rule", "field_keys": ["name", "", 2], "reason": "check"}, {"nested": True}, "legacy"]},
        [],
        {},
    )
    assert any(reason["reason"] == "schema_error" for reason in reasons)
    assert "name" in highlights
    assert ReviewGateTask._business_rule_reasons({"rule": {"reason": "x", "field_keys": ["name"]}, "off": False})[0]
    assert ReviewGateTask._business_rule_reasons("invalid") == ([], [])
    task.review_schema = None
    task.review_schema_hash = ""
    with pytest.raises(TaskError, match="Pinned review schema"):
        task._schema()


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


def test_update_reference_remaining_numeric_atomic_and_missing_column_branches(
    tmp_path, monkeypatch
):
    assert _coerce_to_float("") is None
    reference = tmp_path / "reference.csv"
    reference.write_text("id,status,name\n1,old,Alpha\n", encoding="utf-8")
    task = UpdateReferenceTask(
        Mock(),
        reference_file=str(reference),
        update_field="status",
        csv_match={"clauses": [{"column": "id", "from_context": "id"}]},
        backup=True,
    )
    frame = pd.DataFrame({"id": ["1", "bad"], "status": ["old", "old"]})
    task.clauses[0].number = None
    assert task._build_selection_mask(frame, {"data": {"id": "1"}}).tolist() == [True, False]
    task.clauses[0].number = False
    assert task._build_selection_mask(frame, {"data": {"id": 1}}).tolist() == [True, False]
    task.clauses[0].number = True
    assert task._build_selection_mask(frame, {"data": {"id": "not-a-number"}}).tolist() == [False, False]

    original_read_csv = update_module.pd.read_csv
    monkeypatch.setattr(update_module.pd, "read_csv", Mock(side_effect=OSError("header")))
    with pytest.raises(TaskError, match="Failed to read CSV header"):
        task.validate_required_fields({})

    monkeypatch.setattr(update_module.pd, "read_csv", original_read_csv)
    original_open = open
    calls = 0

    def fail_backup_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("backup locked")
        return original_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", fail_backup_once)
    task._atomic_write_df(reference, pd.DataFrame({"id": ["1"]}))
    monkeypatch.setattr("builtins.open", original_open)
    monkeypatch.setattr(update_module.os, "replace", lambda source, target: None)
    original_unlink = Path.unlink

    def failing_unlink(path):
        if str(path).endswith(".tmp"):
            raise OSError("locked")
        return original_unlink(path)

    monkeypatch.setattr(update_module.Path, "unlink", failing_unlink)
    task._atomic_write_df(reference, pd.DataFrame({"id": ["1"]}))

    missing = UpdateReferenceTask(
        Mock(),
        reference_file=str(reference),
        update_field="new_status",
        csv_match={"clauses": [{"column": "id", "from_context": "id"}]},
    )
    monkeypatch.setattr(missing, "validate_required_fields", lambda context: None)
    monkeypatch.setattr(
        update_module.pd,
        "read_csv",
        lambda *args, **kwargs: pd.DataFrame({"id": ["1"]}),
    )
    result = missing.run({"id": "1", "data": {"id": "1"}})
    assert result["data"]["update_reference"]["selected_rows"] == 1


def test_split_task_validation_and_disabled_run(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3", {})
    task = LlamaCloudSplitTask(config, enabled=False)
    with pytest.raises(TaskError, match="split_dir"):
        task.validate_required_fields({})

    task.split_dir = tmp_path
    assert task.run({})["data"]["split_result"]["status"] == "skipped"

    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source.open("wb") as output:
        writer.write(output)
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
    with pytest.raises(TaskError, match="outside source"):
        create_split_pdf(str(source), str(tmp_path / "out.pdf"), [2])
    with pytest.raises(TaskError, match="outside source"):
        LlamaCloudSplitTask._validate_all_segment_pages(
            str(source), [SplitSegment("invoice", "high", [2], 2, 2, {})]
        )


def test_split_task_document_policy_and_adapter_branches(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source.open("wb") as output:
        writer.write(output)
    config = TempConfig(tmp_path / "state.sqlite3", {})
    result = SplitResult(
        provider_job_id="job",
        status="completed",
        segments=[],
        raw_response={},
    )
    task = LlamaCloudSplitTask(
        config, enabled=True, split_dir=str(tmp_path), adapter=Mock(), categories=["invoice"]
    )
    docs = Mock()
    monkeypatch.setattr(split_module, "connect", lambda _config: nullcontext(object()))
    monkeypatch.setattr(split_module, "DocumentRepository", lambda _conn: docs)
    context = {"batch_id": "b", "document_id": "d", "file_path": str(source), "data": {}}

    docs.get.return_value = None
    assert task.run(context.copy())["fatal_failure"]["failure_type"] == "split_task_failed"
    docs.get.return_value = {"id": "d", "parent_document_id": "p", "status": "queued"}
    assert task.run(context.copy())["data"]["split_result"]["status"] == "skipped_child"
    docs.get.return_value = {"id": "d", "status": "split_completed", "metadata_json": "{}"}
    docs.list_children.return_value = []
    assert task.run(context.copy())["error_step"] == "LlamaCloudSplitTask"
    docs.list_children.return_value = [{"id": "c", "pipeline_template_id": "other", "pipeline_version_id": "v"}]
    docs.get.return_value.update({"pipeline_template_id": "t", "pipeline_version_id": "v"})
    assert task.run(context.copy())["error_step"] == "LlamaCloudSplitTask"
    task.adapter.split_pdf.return_value = result
    docs.get.return_value = {"id": "d", "status": "queued", "parent_document_id": None}
    docs.list_children.return_value = []
    assert task.run(context.copy())["data"]["split_result"]["status"] == "no_segments"

    policy_task = LlamaCloudSplitTask(
        config, enabled=True, split_dir=str(tmp_path), adapter=Mock(),
        categories=["invoice"], allowed_categories=["invoice"],
    )
    with pytest.raises(TaskError, match="manual source"):
        policy_task._validate_split_policy(
            {}, SplitResult("job", "completed", [SplitSegment("", "low", [1], 1, 1, {})], {})
        )
    with pytest.raises(TaskError, match="not in allowed"):
        policy_task._validate_split_policy(
            {}, SplitResult("job", "completed", [SplitSegment("receipt", "high", [1], 1, 1, {})], {})
        )
    assert LlamaCloudSplitTask._normalize_allowed_categories("bad") == set()
    assert LlamaCloudSplitTask._normalize_allowed_categories([{"name": " Invoice "}, "Receipt", None]) == {"invoice", "receipt"}
    task.adapter = None
    task.api_key = "key"
    assert isinstance(task._get_adapter(), split_module.LlamaCloudSplitAdapter)


def test_split_child_creation_and_rollback_compensation(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source.open("wb") as output:
        writer.write(output)
    task = LlamaCloudSplitTask(
        TempConfig(tmp_path / "state.sqlite3", {}), enabled=True, split_dir=str(tmp_path / "split"), adapter=Mock()
    )
    segment = SplitSegment("invoice", "high", [1], 1, 1, {})
    split_result = SplitResult("job", "completed", [segment], {})
    documents = Mock()
    documents.conn = object()
    documents.create_child.return_value = {"id": "child"}
    monkeypatch.setattr(split_module, "transaction", lambda _conn: nullcontext())
    monkeypatch.setattr(split_module, "reserve_unique_filepath", lambda directory, base, suffix: Path(directory) / f"{base}{suffix}")
    monkeypatch.setattr(split_module, "create_split_pdf", Mock())
    child_ids = task._create_children(
        documents=documents,
        document={"id": "root", "batch_id": "batch", "original_filename": "bundle.pdf"},
        context={"file_path": str(source), "original_filename": "bundle.pdf", "metadata": {"inherited_context": {"x": 1}}, "continued_failures": [{"error": "x"}]},
        split_result=split_result,
        source_artifact={"id": "artifact"},
    )
    assert child_ids == ["child"]
    assert documents.create_child.call_args.kwargs["metadata"]["inherited_context"] == {"x": 1}

    documents.list_files.return_value = []
    documents.add_file.return_value = {"id": "source-artifact"}
    assert LlamaCloudSplitTask._ensure_source_artifact(
        documents, {"id": "root"}, {"file_path": str(source)}
    )["id"] == "source-artifact"

    task.split_dir = None
    documents.list_children.return_value = []
    with pytest.raises(TaskError, match="split_dir"):
        task._create_children(
            documents=documents, document={"id": "root", "batch_id": "batch"},
            context={"file_path": str(source)}, split_result=split_result, source_artifact={},
        )

    documents.delete_pending_child.side_effect = RuntimeError("delete")
    documents.list_children.return_value = [{"id": "remaining", "status": "queued"}, {"id": "done", "status": "completed"}]
    monkeypatch.setattr(split_module, "release_reserved_filepath", lambda _path: False)
    monkeypatch.setattr(split_module, "BatchRepository", lambda _conn: Mock(recompute_counts=Mock()))
    state = Mock()
    monkeypatch.setattr(split_module, "WorkflowStateService", lambda _conn: state)
    task._rollback_partial_children(
        documents=documents, document={"id": "root", "batch_id": "batch"},
        child_ids=["child"], reserved_paths=[tmp_path / "reserved.pdf"],
    )
    state.transition_document.assert_any_call("remaining", "failed", reason="split_failed")
    state.transition_document.assert_any_call("root", "failed", reason="split_failed")


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
    class DumpModel:
        def model_dump(self):
            return {"created": date(2026, 1, 1)}

    assert split_json_safe(DumpModel()) == {"created": "2026-01-01"}

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

    class FakeClient:
        def __init__(self, **_kwargs):
            self.files = Mock()
            self.files.create.return_value = SimpleNamespace(id="file-1")
            self.beta = SimpleNamespace(split=Mock())
            self.beta.split.create.return_value = SimpleNamespace(id="job-1")

    monkeypatch.setitem(__import__("sys").modules, "llama_cloud", SimpleNamespace(LlamaCloud=FakeClient))
    adapter._wait_for_completion = Mock(return_value={"id": "job-1", "status": "completed", "result": {"segments": [{"pages": [1]}]}})
    split_result = adapter.split_pdf("file.pdf", [])
    assert split_result.segments[0].pages == [1]

    class Legacy:
        __slots__ = ()

        def dict(self):
            raise TypeError

        def __str__(self):
            return "legacy"

    assert _json_safe(Legacy()) == "legacy"
