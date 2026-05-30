from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import ExtractionRepository, ReviewRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from modules.services.review_service import ReviewService
from modules.workflow_loader import WorkflowLoader
from standard_step.review.review_gate import ReviewGateTask
from test.helpers_sqlite import TempConfig
from test.workflow.test_workflow_task_run_tracking import _patch_prefect


def test_review_pause_and_completion_resumes_from_next_task(tmp_path, monkeypatch):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline": ["extract", "review_gate", "store"],
            "tasks": {
                "extract": {"module": "tests", "class": "ExtractTask", "params": {}, "on_error": "stop"},
                "review_gate": {
                    "module": "standard_step.review.review_gate",
                    "class": "ReviewGateTask",
                    "params": {"confidence_threshold": 0.8},
                    "on_error": "stop",
                },
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

    stored_contexts = []

    class ExtractTask:
        def __init__(self, config_manager, **params):
            self.config_manager = config_manager

        def on_start(self, context):
            pass

        def run(self, context):
            with connect(self.config_manager) as conn:
                repository = ExtractionRepository(conn)
                result = repository.save_result(
                    document_id=context["document_id"],
                    task_run_id=context["task_run_id"],
                    provider="test",
                    data={"supplier": "Acme"},
                )
                repository.save_fields(
                    document_id=context["document_id"],
                    extraction_result_id=result["id"],
                    fields=[{"field_key": "supplier", "extracted_value": "Acme", "confidence": 0.1}],
                )
            context.setdefault("data", {})["supplier"] = "Acme"
            return context

    class StoreTask(ExtractTask):
        def run(self, context):
            stored_contexts.append(dict(context))
            context.setdefault("data", {})["stored"] = True
            return context

    class CleanupTask(ExtractTask):
        def run(self, context):
            return context

    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    monkeypatch.setattr(
        WorkflowLoader,
        "_import_task_class",
        lambda self, module_name, class_name: {
            "ExtractTask": ExtractTask,
            "ReviewGateTask": ReviewGateTask,
            "StoreTask": StoreTask,
        }[class_name],
    )
    WorkflowLoader._instance = None

    paused_context = WorkflowLoader(config).load_workflow()(
        {
            "id": created["document"]["id"],
            "batch_id": created["batch"]["id"],
            "document_id": created["document"]["id"],
            "file_path": str(pdf_path),
        }
    )

    with connect(config) as conn:
        review = ReviewRepository(conn).list_queue()[0]
        service = ReviewService(conn, config)
        service.claim(review["id"], "operator")
        complete_result = service.complete(review["id"], "operator", {"supplier": "Acme Pte Ltd"})
        task_runs = TaskRunRepository(conn).list_by_document(created["document"]["id"])

    assert paused_context["pipeline_state"] == "paused"
    assert complete_result["resume_triggered"] is True
    assert stored_contexts[0]["data"]["supplier"] == "Acme Pte Ltd"
    assert [run["task_key"] for run in task_runs] == ["extract", "review_gate", "store"]
    assert [run["status"] for run in task_runs] == ["completed", "paused", "completed"]
