import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import TaskRunRepository
from modules.services.batch_service import BatchService
from modules.workflow_loader import WorkflowLoader
from test.helpers_sqlite import TempConfig


def _patch_prefect(monkeypatch):
    def fake_task(*args, **kwargs):
        def decorator(fn):
            def wrapped(*w_args, **w_kwargs):
                return {"result": fn(*w_args, **w_kwargs)}

            return wrapped

        return decorator

    def fake_flow(*args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    monkeypatch.setattr("modules.workflow_loader.task", fake_task)
    monkeypatch.setattr("modules.workflow_loader.flow", fake_flow)
    monkeypatch.setattr("modules.workflow_loader.get_run_logger", lambda: type("Logger", (), {"info": lambda *a, **k: None})())


def test_workflow_loader_records_task_runs_and_stops_when_paused(tmp_path, monkeypatch):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline": ["first", "review_gate", "after"],
            "tasks": {
                "first": {"module": "tests", "class": "FirstTask", "params": {}, "on_error": "stop"},
                "review_gate": {"module": "tests", "class": "PauseTask", "params": {}, "on_error": "stop"},
                "after": {"module": "tests", "class": "AfterTask", "params": {}, "on_error": "stop"},
            },
        },
    )
    initialize_database(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
    batch = created["batch"]
    document = created["document"]

    class FirstTask:
        def __init__(self, config_manager, **params):
            pass

        def on_start(self, context):
            pass

        def run(self, context):
            context.setdefault("data", {})["first"] = True
            return context

    class PauseTask(FirstTask):
        def run(self, context):
            context["pipeline_state"] = "paused"
            context["review_item_id"] = "review-1"
            return context

    class AfterTask(FirstTask):
        def run(self, context):
            context.setdefault("data", {})["after"] = True
            return context

    class CleanupTask(FirstTask):
        def run(self, context):
            context.setdefault("data", {})["cleanup"] = True
            return context

    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    monkeypatch.setattr(
        WorkflowLoader,
        "_import_task_class",
        lambda self, module_name, class_name: {"FirstTask": FirstTask, "PauseTask": PauseTask, "AfterTask": AfterTask}[class_name],
    )
    WorkflowLoader._instance = None

    workflow = WorkflowLoader(config).load_workflow()
    assert workflow is not None
    result = workflow(
        {
            "id": document["id"],
            "batch_id": batch["id"],
            "document_id": document["id"],
            "file_path": str(pdf_path),
        }
    )

    with connect(config) as conn:
        task_runs = TaskRunRepository(conn).list_by_document(document["id"])

    assert result["pipeline_state"] == "paused"
    assert [run["task_key"] for run in task_runs] == ["first", "review_gate"]
    assert [run["status"] for run in task_runs] == ["completed", "paused"]
    assert "after" not in result.get("data", {})
    assert "cleanup" not in result.get("data", {})


def test_workflow_loader_marks_task_run_failed_when_task_import_exits(tmp_path, monkeypatch):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline": ["broken"],
            "tasks": {
                "broken": {"module": "missing.module", "class": "MissingTask", "params": {}, "on_error": "stop"},
            },
        },
    )
    initialize_database(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
    batch = created["batch"]
    document = created["document"]

    _patch_prefect(monkeypatch)
    monkeypatch.setattr(
        WorkflowLoader,
        "_import_task_class",
        lambda self, module_name, class_name: (_ for _ in ()).throw(SystemExit(1)),
    )
    WorkflowLoader._instance = None

    with pytest.raises(SystemExit):
        workflow = WorkflowLoader(config).load_workflow()
        assert workflow is not None
        workflow(
            {
                "id": document["id"],
                "batch_id": batch["id"],
                "document_id": document["id"],
                "file_path": str(pdf_path),
            }
        )

    with connect(config) as conn:
        task_runs = TaskRunRepository(conn).list_by_document(document["id"])

    assert [run["task_key"] for run in task_runs] == ["broken"]
    assert task_runs[0]["status"] == "failed"
    assert task_runs[0]["ended_at"]
    assert "Task setup failed" in task_runs[0]["error"]
