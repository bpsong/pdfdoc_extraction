from concurrent.futures import ThreadPoolExecutor
from threading import Event

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository, ExtractionRepository, TaskRunRepository
from modules.resume_manager import ResumeManager
from modules.services.batch_service import BatchService
from modules.workflow_loader import WorkflowLoader
from test.helpers_sqlite import TempConfig
from test.workflow.test_workflow_task_run_tracking import _patch_prefect


def test_resume_manager_resumes_next_task_and_guards_duplicate_resume(tmp_path, monkeypatch):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline": ["review_gate", "store"],
            "tasks": {
                "review_gate": {"module": "tests", "class": "ReviewGate", "params": {}, "on_error": "stop"},
                "store": {"module": "tests", "class": "StoreTask", "params": {}, "on_error": "stop"},
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
        result = ExtractionRepository(conn).save_result(
            document_id=created["document"]["id"],
            provider="test",
            data={"supplier": "Corrected"},
        )
        ExtractionRepository(conn).save_fields(
            document_id=created["document"]["id"],
            extraction_result_id=result["id"],
            fields=[{"field_key": "supplier", "extracted_value": "Original", "final_value": "Corrected"}],
        )
        DocumentRepository(conn).update_current_task(created["document"]["id"], 0, "review_gate")
        DocumentRepository(conn).update_status(created["document"]["id"], "review_completed")

    seen_contexts = []

    class StoreTask:
        def __init__(self, config_manager, **params):
            pass

        def on_start(self, context):
            pass

        def run(self, context):
            seen_contexts.append(dict(context))
            context.setdefault("data", {})["stored"] = True
            return context

    class CleanupTask(StoreTask):
        def run(self, context):
            return context

    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    monkeypatch.setattr(WorkflowLoader, "_import_task_class", lambda self, module_name, class_name: StoreTask)
    WorkflowLoader._instance = None

    first = ResumeManager(config).resume_document(created["document"]["id"], user="operator")
    second = ResumeManager(config).resume_document(created["document"]["id"], user="operator")

    with connect(config) as conn:
        task_runs = TaskRunRepository(conn).list_by_document(created["document"]["id"])

    assert first is True
    assert second is False
    assert seen_contexts[0]["data"]["supplier"] == "Corrected"
    assert [run["task_key"] for run in task_runs] == ["store", "cleanup_task"]
    assert [run["status"] for run in task_runs] == ["completed", "completed"]


def test_resume_manager_atomically_rejects_concurrent_resume(tmp_path, monkeypatch):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline": ["review_gate", "store"],
            "tasks": {
                "review_gate": {"module": "tests", "class": "ReviewGate", "params": {}, "on_error": "stop"},
                "store": {"module": "tests", "class": "StoreTask", "params": {}, "on_error": "stop"},
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
        DocumentRepository(conn).update_current_task(created["document"]["id"], 0, "review_gate")
        DocumentRepository(conn).update_status(created["document"]["id"], "review_completed")

    flow_started = Event()
    release_flow = Event()

    def blocking_flow(context):
        flow_started.set()
        assert release_flow.wait(timeout=5)
        return context

    monkeypatch.setattr(WorkflowLoader, "load_workflow", lambda self, start_task_index=0: blocking_flow)
    WorkflowLoader._instance = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(ResumeManager(config).resume_document, created["document"]["id"], "operator")
        assert flow_started.wait(timeout=5)
        second = ResumeManager(config).resume_document(created["document"]["id"], user="operator")
        release_flow.set()
        assert first.result(timeout=5) is True

    assert second is False


def test_resume_manager_finalizes_when_review_gate_is_last(tmp_path, monkeypatch):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline": ["review_gate"],
            "tasks": {
                "review_gate": {"module": "tests", "class": "ReviewGate", "params": {}, "on_error": "stop"},
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
        DocumentRepository(conn).update_current_task(created["document"]["id"], 0, "review_gate")
        DocumentRepository(conn).update_status(created["document"]["id"], "review_completed")

    class CleanupTask:
        def __init__(self, config_manager, **params):
            pass

        def on_start(self, context):
            pass

        def run(self, context):
            return context

    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    WorkflowLoader._instance = None

    resumed = ResumeManager(config).resume_document(created["document"]["id"], user="operator")

    with connect(config) as conn:
        document = DocumentRepository(conn).get(created["document"]["id"])
        batch = BatchService(conn).get_batch(created["batch"]["id"])
        task_runs = TaskRunRepository(conn).list_by_document(created["document"]["id"])

    assert resumed is True
    assert document is not None and document["status"] == "completed"
    assert batch is not None and batch["status"] == "completed"
    assert [run["task_key"] for run in task_runs] == ["cleanup_task"]
