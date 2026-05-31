from pathlib import Path

from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import AuditRepository, DocumentRepository
from modules.services.batch_service import BatchService
from modules.services.fan_in_service import FanInService
from test.helpers_sqlite import TempConfig


def _create_batch_with_children(tmp_path: Path, child_count: int = 2) -> tuple[TempConfig, dict, list[dict]]:
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    source_pdf = tmp_path / "bundle.pdf"
    source_pdf.write_bytes(b"%PDF-1.4")

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(source_pdf),
            original_filename="bundle.pdf",
        )
        documents = DocumentRepository(conn)
        documents.update_status(created["document"]["id"], "split_completed")
        children = [
            documents.create_child(
                batch_id=created["batch"]["id"],
                parent_document_id=created["document"]["id"],
                file_path=str(tmp_path / f"child_{index}.pdf"),
                status="queued",
            )
            for index in range(child_count)
        ]
    return config, created, children


def test_fan_in_completes_root_and_batch_after_all_leaves_complete(tmp_path):
    config, created, children = _create_batch_with_children(tmp_path)

    with connect(config) as conn:
        service = FanInService(conn)
        first = service.finalize_leaf(
            {
                "id": children[0]["id"],
                "document_id": children[0]["id"],
                "batch_id": created["batch"]["id"],
            }
        )
        documents = DocumentRepository(conn)
        root_after_first = documents.get(created["document"]["id"])
        batch_after_first = BatchService(conn).get_batch(created["batch"]["id"])

        second = service.finalize_leaf(
            {
                "id": children[1]["id"],
                "document_id": children[1]["id"],
                "batch_id": created["batch"]["id"],
            }
        )
        root_after_second = documents.get(created["document"]["id"])
        batch_after_second = BatchService(conn).get_batch(created["batch"]["id"])

    assert first and first.root_status == "processing"
    assert root_after_first and root_after_first["status"] == "processing"
    assert batch_after_first and batch_after_first["status"] == "processing"
    assert batch_after_first["total_documents"] == 2
    assert batch_after_first["completed_documents"] == 1

    assert second and second.root_status == "completed"
    assert root_after_second and root_after_second["status"] == "completed"
    assert batch_after_second and batch_after_second["status"] == "completed"
    assert batch_after_second["total_documents"] == 2
    assert batch_after_second["completed_documents"] == 2
    assert batch_after_second["failed_documents"] == 0


def test_fan_in_marks_aggregate_completed_with_errors_for_failed_leaf(tmp_path):
    config, created, children = _create_batch_with_children(tmp_path)

    with connect(config) as conn:
        service = FanInService(conn)
        service.finalize_leaf(
            {
                "id": children[0]["id"],
                "document_id": children[0]["id"],
                "batch_id": created["batch"]["id"],
            }
        )
        result = service.finalize_leaf(
            {
                "id": children[1]["id"],
                "document_id": children[1]["id"],
                "batch_id": created["batch"]["id"],
                "error": "export failed",
            }
        )
        documents = DocumentRepository(conn)
        root = documents.get(created["document"]["id"])
        failed_child = documents.get(children[1]["id"])
        batch = BatchService(conn).get_batch(created["batch"]["id"])

    assert result and result.root_status == "completed_with_errors"
    assert root and root["status"] == "completed_with_errors"
    assert failed_child and failed_child["status"] == "failed"
    assert batch and batch["status"] == "completed_with_errors"
    assert batch["total_documents"] == 2
    assert batch["completed_documents"] == 1
    assert batch["failed_documents"] == 1


def test_fan_in_preserves_review_required_leaf_as_non_terminal(tmp_path):
    config, created, children = _create_batch_with_children(tmp_path)

    with connect(config) as conn:
        documents = DocumentRepository(conn)
        documents.update_status(children[0]["id"], "review_required")
        result = FanInService(conn).finalize_leaf(
            {
                "id": children[0]["id"],
                "document_id": children[0]["id"],
                "batch_id": created["batch"]["id"],
                "pipeline_state": "paused",
            }
        )
        root = documents.get(created["document"]["id"])
        child = documents.get(children[0]["id"])
        batch = BatchService(conn).get_batch(created["batch"]["id"])

    assert result and result.root_status == "review_required"
    assert child and child["status"] == "review_required"
    assert root and root["status"] == "review_required"
    assert batch and batch["status"] == "review_required"
    assert batch["completed_documents"] == 0


def test_fan_in_handles_unsplit_root_as_leaf(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
        result = FanInService(conn).finalize_leaf(
            {
                "id": created["document"]["id"],
                "document_id": created["document"]["id"],
                "batch_id": created["batch"]["id"],
            }
        )
        document = DocumentRepository(conn).get(created["document"]["id"])
        batch = BatchService(conn).get_batch(created["batch"]["id"])

    assert result and result.root_document_id == created["document"]["id"]
    assert result.total_leaves == 1
    assert document and document["status"] == "completed"
    assert batch and batch["status"] == "completed"
    assert batch["total_documents"] == 1


def test_fan_in_audit_event_is_idempotent(tmp_path):
    config, created, children = _create_batch_with_children(tmp_path, child_count=1)

    with connect(config) as conn:
        service = FanInService(conn)
        context = {
            "id": children[0]["id"],
            "document_id": children[0]["id"],
            "batch_id": created["batch"]["id"],
        }
        service.finalize_leaf(context)
        service.finalize_leaf(context)
        audit_events = [
            event for event in AuditRepository(conn).list_for_document(created["document"]["id"])
            if event["event_type"] == "fan_in_completed"
        ]

    assert len(audit_events) == 1
    event_payload = json_loads(audit_events[0]["event_json"], {})
    assert event_payload["total_leaves"] == 1
    assert event_payload["completed_leaves"] == 1
