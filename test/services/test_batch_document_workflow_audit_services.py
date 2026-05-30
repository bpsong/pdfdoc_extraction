from pathlib import Path

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.audit_service import AuditService
from modules.services.batch_service import BatchService
from modules.services.document_service import DocumentService
from modules.services.workflow_state_service import WorkflowStateService


class TempConfig:
    def __init__(self, db_path: Path) -> None:
        self._config_path = db_path.parent / "config.yaml"
        self._values = {"database.path": str(db_path)}

    def get(self, key, default=None):
        return self._values.get(key, default)


def test_services_coordinate_core_business_operations(tmp_path):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)

    with connect(config) as conn:
        batch_service = BatchService(conn)
        document_service = DocumentService(conn)
        workflow_service = WorkflowStateService(conn, pipeline=["extract", "review_gate", "store"])
        audit_service = AuditService(conn)

        created = batch_service.create_ingestion_batch(
            source="watch_folder",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
            metadata={"source_path": str(pdf_path)},
        )
        batch = created["batch"]
        document = created["document"]

        child = document_service.create_child_document(
            batch_id=batch["id"],
            parent_document_id=document["id"],
            file_path=str(tmp_path / "child.pdf"),
            page_start=1,
            page_end=1,
        )
        task_run = workflow_service.start_task(
            batch_id=batch["id"],
            document_id=document["id"],
            task_key="extract",
            task_index=0,
            module_name="module",
            class_name="Task",
            input_data={"id": document["id"]},
        )
        workflow_service.complete_task(task_run["id"], {"status": "ok"})
        workflow_service.pause_document(document["id"])
        audit = audit_service.append_event(
            event_type="document_paused",
            batch_id=batch["id"],
            document_id=document["id"],
            metadata={"reason": "review_required"},
        )

        details = document_service.get_details(document["id"])
        refreshed_batch = batch_service.recompute(batch["id"])
        is_paused = workflow_service.is_paused(document["id"])
        next_task = workflow_service.next_task_after_current(document["id"])
        document_audit = audit_service.list_for_document(document["id"])

    assert child["parent_document_id"] == document["id"]
    assert is_paused is True
    assert next_task == (1, "review_gate")
    assert details and details["task_runs"][0]["status"] == "completed"
    assert refreshed_batch and refreshed_batch["total_documents"] == 2
    assert document_audit[0]["id"] == audit["id"]
