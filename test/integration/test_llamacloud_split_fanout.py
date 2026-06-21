from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from modules.services.failure_service import FailureService
from modules.exceptions import TaskError
from modules.status_manager import StatusManager
from modules.workflow_loader import WorkflowLoader
from modules.workflow_manager import WorkflowManager
from standard_step.split.llamacloud_split import LlamaCloudSplitTask
from standard_step.split.llamacloud_split_adapter import SplitResult, SplitSegment
from test.helpers_sqlite import TempConfig
from test.workflow.test_workflow_task_run_tracking import _patch_prefect


def _write_pdf(path: Path, page_count: int) -> None:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as file_obj:
        writer.write(file_obj)


class FakeSplitAdapter:
    def split_pdf(self, file_path, categories):
        return SplitResult(
            provider_job_id="spl-1",
            status="completed",
            segments=[
                SplitSegment(
                    category="invoice",
                    confidence="high",
                    pages=[1],
                    page_start=1,
                    page_end=1,
                    metadata={"raw_segment": {"pages": [1]}},
                ),
                SplitSegment(
                    category="receipt",
                    confidence="medium",
                    pages=[2],
                    page_start=2,
                    page_end=2,
                    metadata={"raw_segment": {"pages": [2]}},
                ),
            ],
            raw_response={"id": "spl-1"},
        )


def test_split_fanout_starts_child_workflows_and_skips_parent_reference_update(tmp_path, monkeypatch):
    source = tmp_path / "bundle.pdf"
    _write_pdf(source, 2)
    processing_dir = tmp_path / "processing"
    processing_dir.mkdir()
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "watch_folder": {"processing_dir": str(processing_dir)},
            "pipeline": ["split", "update_reference"],
            "tasks": {
                "split": {
                    "module": "standard_step.split.llamacloud_split",
                    "class": "LlamaCloudSplitTask",
                    "params": {
                        "enabled": True,
                        "adapter": FakeSplitAdapter(),
                        "categories": [{"name": "invoice"}, {"name": "receipt"}],
                        "split_dir": str(tmp_path / "split"),
                    },
                    "on_error": "stop",
                },
                "update_reference": {
                    "module": "tests",
                    "class": "FakeUpdateReferenceTask",
                    "params": {},
                    "on_error": "stop",
                },
            },
        },
    )
    initialize_database(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(source),
            original_filename="bundle.pdf",
        )

    update_contexts = []

    class FakeUpdateReferenceTask:
        def __init__(self, config_manager, **params):
            pass

        def on_start(self, context):
            pass

        def run(self, context):
            update_contexts.append(dict(context))
            context.setdefault("data", {})["reference_updated"] = True
            return context

    class CleanupTask:
        def __init__(self, config_manager, **params):
            pass

        def on_start(self, context):
            pass

        def run(self, context):
            return context

    _patch_prefect(monkeypatch)
    WorkflowLoader._instance = None
    StatusManager._instance = None
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    monkeypatch.setattr(
        WorkflowLoader,
        "_import_task_class",
        lambda self, module_name, class_name: {
            "LlamaCloudSplitTask": LlamaCloudSplitTask,
            "FakeUpdateReferenceTask": FakeUpdateReferenceTask,
        }[class_name],
    )

    manager = WorkflowManager(config)
    ok = manager.trigger_workflow_for_file(
        file_path=str(source),
        unique_id=created["document"]["id"],
        original_filename="bundle.pdf",
        source="web",
        batch_id=created["batch"]["id"],
        document_id=created["document"]["id"],
    )

    with connect(config) as conn:
        documents = DocumentRepository(conn)
        children = documents.list_children(created["document"]["id"])
        parent_runs = TaskRunRepository(conn).list_by_document(created["document"]["id"])
        child_runs = [TaskRunRepository(conn).list_by_document(child["id"]) for child in children]

    assert ok is True
    assert len(children) == 2
    assert [run["task_key"] for run in parent_runs] == ["split"]
    assert [context["document_id"] for context in update_contexts] == [child["id"] for child in children]
    assert all(context["parent_document_id"] == created["document"]["id"] for context in update_contexts)
    assert all(context["source_original_filename"] == "bundle.pdf" for context in update_contexts)
    assert all(context["split_pages"] for context in update_contexts)
    assert [[run["task_key"] for run in runs] for runs in child_runs] == [["update_reference"], ["update_reference"]]


def test_split_fanout_extract_preflight_failure_stops_children_once(tmp_path, monkeypatch):
    source = tmp_path / "bundle.pdf"
    _write_pdf(source, 2)
    processing_dir = tmp_path / "processing"
    processing_dir.mkdir()
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "watch_folder": {"processing_dir": str(processing_dir)},
            "pipeline": ["split", "extract_document_data"],
            "tasks": {
                "split": {
                    "module": "standard_step.split.llamacloud_split",
                    "class": "LlamaCloudSplitTask",
                    "params": {
                        "enabled": True,
                        "adapter": FakeSplitAdapter(),
                        "categories": [{"name": "invoice"}, {"name": "receipt"}],
                        "split_dir": str(tmp_path / "split"),
                    },
                    "on_error": "stop",
                },
                "extract_document_data": {
                    "module": "standard_step.extraction.extract_pdf",
                    "class": "ExtractPdfTask",
                    "params": {
                        "api_key": "llx-bad",
                        "configuration_id": "cfg-missing",
                        "fields": {"invoiceNumber": {"alias": "Invoice Number", "type": "str"}},
                    },
                    "on_error": "stop",
                },
            },
        },
    )
    initialize_database(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(source),
            original_filename="bundle.pdf",
        )

    class CleanupTask:
        def __init__(self, config_manager, **params):
            pass

        def on_start(self, context):
            pass

        def run(self, context):
            return context

    _patch_prefect(monkeypatch)
    WorkflowLoader._instance = None
    StatusManager._instance = None
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    monkeypatch.setattr(
        WorkflowLoader,
        "_import_task_class",
        lambda self, module_name, class_name: {"LlamaCloudSplitTask": LlamaCloudSplitTask}[class_name],
    )
    monkeypatch.setattr(
        "modules.workflow_manager.preflight_extract_v2_access",
        lambda **kwargs: (_ for _ in ()).throw(
            TaskError("LlamaCloud Extract configuration 'cfg-missing' was not found.")
        ),
    )

    ok = WorkflowManager(config).trigger_workflow_for_file(
        file_path=str(source),
        unique_id=created["document"]["id"],
        original_filename="bundle.pdf",
        source="web",
        batch_id=created["batch"]["id"],
        document_id=created["document"]["id"],
    )

    with connect(config) as conn:
        documents = DocumentRepository(conn)
        root = documents.get(created["document"]["id"])
        children = documents.list_children(created["document"]["id"])
        parent_runs = TaskRunRepository(conn).list_by_document(created["document"]["id"])
        child_runs = [TaskRunRepository(conn).list_by_document(child["id"]) for child in children]
        notifications = FailureService(conn).notification_status()
        failures = FailureService(conn).list_failures()

    assert ok is True
    assert root and root["status"] == "failed"
    assert len(children) == 2
    assert [child["status"] for child in children] == ["failed", "failed"]
    assert [run["task_key"] for run in parent_runs] == ["split", "extract_document_data"]
    assert [run["status"] for run in parent_runs] == ["completed", "failed"]
    assert child_runs == [[], []]
    assert notifications["count"] == 1
    assert failures["total"] == 1
    assert failures["failures"][0]["source_document"]["id"] == created["document"]["id"]
    assert "cfg-missing" in failures["failures"][0]["failure"]["message"]


def test_split_results_api_returns_parent_child_payload(tmp_path, monkeypatch):
    source = tmp_path / "bundle.pdf"
    child_pdf = tmp_path / "child.pdf"
    _write_pdf(source, 2)
    _write_pdf(child_pdf, 1)
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(source),
            original_filename="bundle.pdf",
        )
        documents = DocumentRepository(conn)
        documents.update_status(created["document"]["id"], "split_completed")
        child = documents.create_child(
            batch_id=created["batch"]["id"],
            parent_document_id=created["document"]["id"],
            file_path=str(child_pdf),
            original_filename="bundle_segment_001_invoice_p1-1.pdf",
            page_start=1,
            page_end=1,
            split_category="invoice",
            split_confidence="high",
            metadata={"split_pages": [1]},
        )
        documents.add_file(document_id=child["id"], file_type="split_pdf", file_path=str(child_pdf))

    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    client = TestClient(app)

    response = client.get(f"/api/batches/{created['batch']['id']}/split-results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_files"] == 1
    assert payload["summary"]["documents_created"] == 1
    assert payload["sources"][0]["status"] == "success"
    assert payload["sources"][0]["children"][0]["category"] == "invoice"
    assert payload["sources"][0]["children"][0]["pages"] == [1]
