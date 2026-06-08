from pathlib import Path

from pypdf import PdfWriter

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import AuditRepository, DocumentRepository
from modules.services.batch_service import BatchService
from modules.services.fan_in_service import FanInService
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
                    category="invoice",
                    confidence="high",
                    pages=[2],
                    page_start=2,
                    page_end=2,
                    metadata={"raw_segment": {"pages": [2]}},
                ),
            ],
            raw_response={"id": "spl-1"},
        )


def test_split_fan_in_finalizes_root_and_batch_after_child_workflows(tmp_path, monkeypatch):
    source = tmp_path / "bundle.pdf"
    _write_pdf(source, 2)
    processing_dir = tmp_path / "processing"
    processing_dir.mkdir()
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "watch_folder": {"processing_dir": str(processing_dir)},
            "pipeline": ["split", "leaf_done"],
            "tasks": {
                "split": {
                    "module": "standard_step.split.llamacloud_split",
                    "class": "LlamaCloudSplitTask",
                    "params": {
                        "enabled": True,
                        "adapter": FakeSplitAdapter(),
                        "categories": [{"name": "invoice"}],
                        "split_dir": str(tmp_path / "split"),
                    },
                    "on_error": "stop",
                },
                "leaf_done": {
                    "module": "tests",
                    "class": "FakeLeafDoneTask",
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

    class FakeLeafDoneTask:
        def __init__(self, config_manager, **params):
            pass

        def on_start(self, context):
            pass

        def run(self, context):
            context.setdefault("data", {})["leaf_done"] = True
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
            "FakeLeafDoneTask": FakeLeafDoneTask,
        }[class_name],
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
        batch = BatchService(conn).get_batch(created["batch"]["id"])
        audit_events = [
            event for event in AuditRepository(conn).list_for_document(created["document"]["id"])
            if event["event_type"] == "fan_in_completed"
        ]
        result = FanInService(conn).finalize_leaf(
            {
                "id": children[0]["id"],
                "document_id": children[0]["id"],
                "batch_id": created["batch"]["id"],
            }
        )
        audit_events_after_repeat = [
            event for event in AuditRepository(conn).list_for_document(created["document"]["id"])
            if event["event_type"] == "fan_in_completed"
        ]

    assert ok is True
    assert root and root["status"] == "completed"
    assert [child["status"] for child in children] == ["completed", "completed"]
    assert batch and batch["status"] == "completed"
    assert batch["total_documents"] == 2
    assert batch["completed_documents"] == 2
    assert batch["failed_documents"] == 0
    assert len(audit_events) == 1
    assert result and result.root_status == "completed"
    assert len(audit_events_after_repeat) == 1
