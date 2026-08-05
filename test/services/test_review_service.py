import pytest

from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository, ExtractionRepository, ReviewRepository
from modules.services.batch_service import BatchService
from modules.services.review_service import ReviewService, ReviewServiceError
from test.helpers_sqlite import TempConfig


def test_review_service_claim_draft_diff_complete_and_expired_lock(tmp_path):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
        extraction = ExtractionRepository(conn).save_result(
            document_id=created["document"]["id"],
            provider="test",
            data={"supplier": "Acme"},
        )
        ExtractionRepository(conn).save_fields(
            document_id=created["document"]["id"],
            extraction_result_id=extraction["id"],
            fields=[{"field_key": "supplier", "extracted_value": "Acme", "confidence": 0.1}],
        )
        review = ReviewRepository(conn).create_review_item(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            queue_name="default_review",
            reason="low_confidence",
            scope="low_confidence_fields",
        )
        service = ReviewService(conn, config)

        service.claim(review["id"], "alice")
        with pytest.raises(ReviewServiceError):
            service.claim(review["id"], "bob")
        draft = service.save_draft(review["id"], "alice", {"supplier": "Acme Pte Ltd"})
        diff = service.diff_preview(review["id"], {"supplier": "Acme Pte Ltd"})
        result = service.complete(review["id"], "alice", {"supplier": "Acme Pte Ltd"}, trigger_resume=False)
        fields = ExtractionRepository(conn).get_fields(created["document"]["id"])
        completed_review = ReviewRepository(conn).get(review["id"])
        with pytest.raises(ReviewServiceError, match="no longer available"):
            service.claim(review["id"], "alice")
        with pytest.raises(ReviewServiceError, match="no longer available"):
            service.release(review["id"], "alice")
        completed_document = DocumentRepository(conn).get(created["document"]["id"])

    assert draft["metadata"]["draft"]["corrections"]["supplier"] == "Acme Pte Ltd"
    assert diff["change_count"] == 1
    assert result["status"] == "completed"
    assert completed_review is not None
    assert completed_review["status"] == "completed"
    assert completed_document is not None
    assert completed_document["status"] == "review_completed"
    assert json_loads(fields[0]["final_value_json"]) == "Acme Pte Ltd"


def test_review_service_reclaims_expired_lock(tmp_path):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
        review = ReviewRepository(conn).create_review_item(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            queue_name="default_review",
            reason="low_confidence",
            scope="low_confidence_fields",
        )
        service = ReviewService(conn, config)
        service.claim(review["id"], "alice", timeout_minutes=-1)
        claimed = service.claim(review["id"], "bob")

    assert claimed["assigned_to"] == "bob"


def test_review_service_corrects_missing_glm_object_and_array_fields(tmp_path):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename=pdf_path.name,
        )
        extraction = ExtractionRepository(conn).save_result(
            document_id=created["document"]["id"],
            provider="glm_ocr_ollama",
            data={"summary": None, "items": None},
        )
        ExtractionRepository(conn).save_fields(
            document_id=created["document"]["id"],
            extraction_result_id=extraction["id"],
            fields=[
                {"field_key": "summary", "extracted_value": None},
                {"field_key": "items", "extracted_value": None},
            ],
        )
        ExtractionRepository(conn).set_review_requirements(
            created["document"]["id"], ["summary", "items"]
        )
        review = ReviewRepository(conn).create_review_item(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            queue_name="default_review",
            reason="business_rule",
            scope="low_confidence_fields",
            metadata={"highlight_fields": ["summary", "items"]},
        )
        service = ReviewService(conn, config)
        service.claim(review["id"], "operator")
        service.complete(
            review["id"],
            "operator",
            {
                "summary": {"currency": "SGD", "tax": 9.0},
                "items": [{"description": "Paper", "quantity": 2}],
            },
            trigger_resume=False,
        )
        fields = {
            row["field_key"]: row
            for row in ExtractionRepository(conn).get_fields(
                created["document"]["id"]
            )
        }

    assert json_loads(fields["summary"]["final_value_json"]) == {
        "currency": "SGD",
        "tax": 9.0,
    }
    assert json_loads(fields["items"]["final_value_json"]) == [
        {"description": "Paper", "quantity": 2}
    ]
    assert fields["summary"]["review_status"] == "corrected"
    assert fields["items"]["review_status"] == "corrected"
