from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules.base_task import BaseTask
from modules.exceptions import TaskError
from modules.workflow_loader import WorkflowLoader
from modules.workflow_manager import WorkflowManager
from test.helpers_sqlite import TempConfig


class SuccessfulTask:
    def __init__(self, config_manager, **params):
        self.params = params

    def on_start(self, context):
        context["started"] = True

    def run(self, context):
        context["ran"] = True
        return context


class SuccessfulCleanup(SuccessfulTask):
    def run(self, context):
        context["cleaned"] = True
        return context


def _patch_prefect(monkeypatch, *, future=False):
    def fake_flow(*args, **kwargs):
        return lambda fn: fn

    def fake_task(*args, **kwargs):
        def decorator(fn):
            def wrapped(*wrapped_args, **wrapped_kwargs):
                result = fn(*wrapped_args, **wrapped_kwargs)
                if future:
                    return SimpleNamespace(result=lambda: result)
                return {"result": result}

            return wrapped

        return decorator

    monkeypatch.setattr("modules.workflow_loader.flow", fake_flow)
    monkeypatch.setattr("modules.workflow_loader.task", fake_task)
    monkeypatch.setattr(
        "modules.workflow_loader.get_run_logger",
        lambda: SimpleNamespace(info=lambda *args, **kwargs: None),
    )


def _loader(tmp_path: Path, values: dict) -> WorkflowLoader:
    WorkflowLoader._instance = None
    return WorkflowLoader(TempConfig(tmp_path / "workflow.sqlite3", values))


def test_import_task_class_rejects_non_task_and_import_errors(tmp_path, monkeypatch):
    loader = _loader(tmp_path, {})
    monkeypatch.setattr(
        "modules.workflow_loader.ApprovedTaskRegistry.assert_approved",
        lambda *args: None,
    )
    monkeypatch.setattr(
        "modules.workflow_loader.importlib.import_module",
        lambda name: SimpleNamespace(NotATask=object),
    )

    with pytest.raises(SystemExit):
        loader._import_task_class("approved.module", "NotATask")

    monkeypatch.setattr(
        "modules.workflow_loader.importlib.import_module",
        Mock(side_effect=ImportError("missing")),
    )
    with pytest.raises(SystemExit):
        loader._import_task_class("approved.module", "Missing")


def test_context_summary_and_existing_fatal_failure_are_normalized():
    context = {
        "id": "document",
        "data": "not-a-dict",
        "metadata": None,
        "error": "secret-token",
        "fatal_failure": {"message": "failed"},
    }

    summary = WorkflowLoader._context_summary(context)
    WorkflowLoader._ensure_fatal_failure(
        context,
        task_key="extract",
        task_index=2,
        module_name="standard_step.extraction",
        class_name="Extract",
        error="failed",
    )

    assert summary["data_keys"] == []
    assert summary["metadata_keys"] == []
    assert context["fatal_failure"]["task_key"] == "extract"
    assert context["fatal_failure"]["task_index"] == 2


def test_load_workflow_rejects_invalid_unknown_and_incomplete_steps(tmp_path, monkeypatch):
    invalid = _loader(tmp_path, {"pipeline": "bad", "tasks": {}})
    assert invalid.load_workflow() is None

    _patch_prefect(monkeypatch)
    unknown = _loader(tmp_path, {"pipeline": ["missing"], "tasks": {}})
    flow = unknown.load_workflow()
    assert flow is not None
    assert flow({"id": "doc"})["id"] == "doc"

    incomplete = _loader(
        tmp_path,
        {"pipeline": ["step"], "tasks": {"step": {"module": "x"}}},
    )
    flow = incomplete.load_workflow()
    assert flow is not None
    assert flow({"id": "doc"})["id"] == "doc"

    reserved = _loader(
        tmp_path,
        {
            "pipeline": ["cleanup_task"],
            "tasks": {
                "cleanup_task": {
                    "module": "standard_step.housekeeping.cleanup_task",
                    "class": "CleanupTask",
                }
            },
        },
    )
    assert reserved.load_workflow() is None


def test_workflow_handles_future_results_and_housekeeping_failure(tmp_path, monkeypatch):
    _patch_prefect(monkeypatch, future=True)
    loader = _loader(
        tmp_path,
        {
            "pipeline": ["step"],
            "tasks": {
                "step": {
                    "module": "test.module",
                    "class": "SuccessfulTask",
                    "params": {"value": 1},
                }
            },
        },
    )
    monkeypatch.setattr(loader, "_import_task_class", lambda *args: SuccessfulTask)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", SuccessfulCleanup)
    monkeypatch.setattr(loader, "_finalize_leaf", Mock())

    flow = loader.load_workflow()
    assert flow is not None
    result = flow({"id": "doc"})

    assert result["ran"] is True
    assert result["cleaned"] is True
    loader._finalize_leaf.assert_called_once_with(result)

    class FailingCleanup(SuccessfulCleanup):
        def run(self, context):
            raise RuntimeError("cleanup failed")

    monkeypatch.setattr("modules.workflow_loader.CleanupTask", FailingCleanup)
    flow = loader.load_workflow()
    assert flow is not None
    result = flow({"id": "doc"})
    assert result["error"] == "cleanup failed"
    assert result["error_step"] == "cleanup_task"
    assert result["fatal_failure"]["task_key"] == "cleanup_task"


@pytest.mark.parametrize(
    ("error", "on_error", "expected_prefix"),
    [
        (TaskError("task failed"), "stop", "TaskError"),
        (RuntimeError("unexpected"), "stop", "Unexpected error"),
    ],
)
def test_workflow_records_task_exceptions(
    tmp_path,
    monkeypatch,
    error,
    on_error,
    expected_prefix,
):
    _patch_prefect(monkeypatch)
    loader = _loader(
        tmp_path,
        {
            "pipeline": ["broken"],
            "tasks": {
                "broken": {
                    "module": "test.module",
                    "class": "BrokenTask",
                    "on_error": on_error,
                }
            },
        },
    )

    class BrokenTask(SuccessfulTask):
        def run(self, context):
            raise error

    monkeypatch.setattr(loader, "_import_task_class", lambda *args: BrokenTask)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", SuccessfulCleanup)

    flow = loader.load_workflow()
    assert flow is not None
    result = flow({"id": "doc"})

    assert expected_prefix in result["error"]
    assert result["error_step"] == "broken"
    assert result["fatal_failure"]["task_key"] == "broken"
    assert result["cleaned"] is True


def test_finalize_leaf_skip_and_failure_paths(tmp_path, monkeypatch):
    loader = _loader(tmp_path, {})
    connect_mock = Mock(side_effect=OSError("database unavailable"))
    monkeypatch.setattr("modules.workflow_loader.connect", connect_mock)

    loader._finalize_leaf({"pipeline_state": "fan_out", "document_id": "doc"})
    loader._finalize_leaf({})
    loader._finalize_leaf({"document_id": "doc"})

    connect_mock.assert_called_once()


def test_workflow_manager_load_trigger_and_child_edge_paths(tmp_path, monkeypatch):
    config = TempConfig(tmp_path / "manager.sqlite3", {})
    manager = WorkflowManager(config)
    manager._mark_document_failed = Mock()
    manager.workflow_loader.load_workflow = Mock(return_value=None)

    assert manager.trigger_workflow_for_file("file.pdf", "id", "file.pdf", "web") is False
    manager._mark_document_failed.assert_called_once()

    manager.workflow_loader.load_workflow = Mock(side_effect=RuntimeError("load failed"))
    assert manager.trigger_workflow_for_file(
        "file.pdf",
        "id",
        "file.pdf",
        "web",
        document_id="document",
    ) is False

    manager._trigger_child_workflows({})

    monkeypatch.setattr(
        "modules.workflow_manager.connect",
        Mock(side_effect=OSError("database unavailable")),
    )
    WorkflowManager._mark_document_failed(manager, None, "reason")
    WorkflowManager._mark_document_failed(manager, "document", "reason")


def test_workflow_manager_helpers_cover_invalid_metadata_and_indices(tmp_path, monkeypatch):
    config = TempConfig(
        tmp_path / "manager.sqlite3",
        {
            "pipeline": ["extract"],
            "tasks": {
                "extract": {
                    "module": "standard_step.extraction.extract_pdf",
                    "class": "ExtractPdfTask",
                    "params": "invalid",
                }
            },
        },
    )
    manager = WorkflowManager(config)
    manager._record_extract_preflight_failure = Mock()

    monkeypatch.setattr(
        "modules.workflow_manager.preflight_extract_v2_access",
        Mock(return_value=None),
    )
    assert manager._fail_children_when_extract_preflight_fails({}, [], 0) is False
    assert manager._fail_children_when_extract_preflight_fails({}, [], 9) is False

    assert manager._task_at_index(-1) == (None, {})
    assert manager._is_extract_task("other", {"class": "ExtractTask"}) is True

    repository = Mock()
    repository.get.side_effect = [
        None,
        {"metadata_json": "[]"},
    ]
    WorkflowManager._merge_document_metadata(
        repository,
        "missing",
        {"failure": True},
        "message",
        "task",
    )
    WorkflowManager._merge_document_metadata(
        repository,
        "document",
        {"failure": True},
        "message",
        "task",
    )
    repository.update_metadata.assert_called_once()

    payload = WorkflowManager._segment_failure_payload(
        {"id": "child", "metadata_json": "[]"}
    )
    assert payload["pages"] == []

    child = {
        "id": "child",
        "batch_id": "batch",
        "parent_document_id": "parent",
        "file_path": "child.pdf",
        "metadata_json": '{"inherited_context": {"key": "value"}}',
    }
    context = WorkflowManager._build_child_context(child, {}, 3)
    assert context["metadata"]["inherited_context"] == {"key": "value"}


def test_workflow_manager_skips_missing_children_and_missing_failure_roots(
    tmp_path,
    monkeypatch,
):
    manager = WorkflowManager(TempConfig(tmp_path / "manager.sqlite3", {}))
    documents = Mock()
    documents.get.side_effect = [
        None,
        {
            "id": "child",
            "batch_id": "batch",
            "file_path": "child.pdf",
            "metadata_json": "{}",
        },
        None,
    ]
    monkeypatch.setattr(
        "modules.workflow_manager.connect",
        lambda config: nullcontext(object()),
    )
    monkeypatch.setattr(
        "modules.workflow_manager.DocumentRepository",
        lambda conn: documents,
    )
    monkeypatch.setattr("modules.workflow_manager.TaskRunRepository", Mock())
    monkeypatch.setattr(
        manager,
        "_fail_children_when_extract_preflight_fails",
        Mock(return_value=False),
    )
    manager.workflow_loader.load_workflow = Mock(return_value=None)

    manager._trigger_child_workflows({"split_children": ["missing", "child"]})
    manager._record_extract_preflight_failure(
        parent_context={},
        child_documents=[],
        start_task_index=0,
        task_key="extract",
        task_config={},
        message="failed",
        params={},
    )
    manager._record_extract_preflight_failure(
        parent_context={"document_id": "root", "batch_id": "batch"},
        child_documents=[],
        start_task_index=0,
        task_key="extract",
        task_config={},
        message="failed",
        params={},
    )

    manager.workflow_loader.load_workflow.assert_called_once_with(start_task_index=0)
