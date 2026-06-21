from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from modules.services.failure_service import FailureService
from test.helpers_sqlite import TempConfig


def _create_failed_document(tmp_path, *, error="boom"):
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
        run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            task_key="extract_document_data",
            task_index=1,
            module_name="standard_step.extraction.extract_pdf",
            class_name="ExtractPdfTask",
            input_data={"api_key": "llx-secret-token"},
        )
        TaskRunRepository(conn).mark_failed(
            run["id"],
            error,
            {
                "fatal_failure": {
                    "failure_type": "task_failed",
                    "message": error,
                    "provider_job_id": "job-1",
                    "api_key": "llx-secret-token",
                }
            },
        )
    return config, created


def test_failure_service_lists_failed_documents_and_redacts_secrets(tmp_path):
    config, created = _create_failed_document(tmp_path, error="bad key llx-secret-token")

    with connect(config) as conn:
        payload = FailureService(conn).list_failures()
        detail = FailureService(conn).get_failure(created["document"]["id"])

    assert payload["total"] == 1
    assert payload["failures"][0]["document"]["id"] == created["document"]["id"]
    assert "[REDACTED]" in payload["failures"][0]["failure"]["message"]
    assert detail is not None
    assert detail["failure"]["provider_job_id"] == "job-1"
    assert detail["latest_failed_task"]["output"]["fatal_failure"]["api_key"] == "[REDACTED]"
    assert detail["preview_url"].endswith(f"/api/documents/{created['document']['id']}/file/pdf")


def test_failure_service_humanizes_historical_extract_provider_errors(tmp_path):
    error = (
        "TaskError: Extraction failed after 3 attempts: Error code: 404 - "
        "{'detail': 'not_found: Extract configuration cfg-missing not found'}"
    )
    config, created = _create_failed_document(tmp_path, error=error)

    with connect(config) as conn:
        payload = FailureService(conn).list_failures()
        detail = FailureService(conn).get_failure(created["document"]["id"])

    expected = (
        "LlamaCloud Extract configuration 'cfg-missing' was not found. "
        "Check the Extract task configuration_id, then re-ingest the source PDF."
    )
    assert payload["failures"][0]["failure"]["message"] == expected
    assert detail is not None
    assert detail["latest_failed_task"]["error"] == expected


def test_failure_notifications_clear_globally_until_new_failure(tmp_path):
    config, created = _create_failed_document(tmp_path)

    with connect(config) as conn:
        service = FailureService(conn)
        assert service.notification_status()["count"] == 1
        assert service.clear_notifications(user="admin")["count"] == 0

        run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            task_key="split_document",
            task_index=0,
            module_name="standard_step.split.llamacloud_split",
            class_name="LlamaCloudSplitTask",
        )
        TaskRunRepository(conn).mark_failed(run["id"], "new failure", {"fatal_failure": {"message": "new failure"}})

        assert service.notification_status()["count"] == 1


def test_failure_service_groups_repeated_split_child_extract_failures(tmp_path):
    pdf_path = tmp_path / "bundle.pdf"
    child_one = tmp_path / "child-1.pdf"
    child_two = tmp_path / "child-2.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    child_one.write_bytes(b"%PDF-1.4")
    child_two.write_bytes(b"%PDF-1.4")
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="bundle.pdf",
        )
        documents = DocumentRepository(conn)
        documents.update_status(created["document"]["id"], "failed")
        children = [
            documents.create_child(
                batch_id=created["batch"]["id"],
                parent_document_id=created["document"]["id"],
                file_path=str(child_one),
                original_filename="bundle_segment_001_invoice_p1-1.pdf",
                status="failed",
                split_category="invoice",
                split_confidence="high",
                page_start=1,
                page_end=1,
                metadata={"split_pages": [1]},
            ),
            documents.create_child(
                batch_id=created["batch"]["id"],
                parent_document_id=created["document"]["id"],
                file_path=str(child_two),
                original_filename="bundle_segment_002_invoice_p2-2.pdf",
                status="failed",
                split_category="invoice",
                split_confidence="high",
                page_start=2,
                page_end=2,
                metadata={"split_pages": [2]},
            ),
        ]
        for child in children:
            run = TaskRunRepository(conn).create_started(
                batch_id=created["batch"]["id"],
                document_id=child["id"],
                task_key="extract_document_data",
                task_index=1,
                module_name="standard_step.extraction.extract_pdf",
                class_name="ExtractPdfTask",
            )
            TaskRunRepository(conn).mark_failed(
                run["id"],
                "LlamaCloud Extract configuration 'cfg-missing' was not found.",
                {"fatal_failure": {"message": "LlamaCloud Extract configuration 'cfg-missing' was not found."}},
            )

        service = FailureService(conn)
        payload = service.list_failures()
        detail = service.get_failure(children[0]["id"])
        notifications = service.notification_status()

    assert payload["total"] == 1
    failure = payload["failures"][0]
    assert failure["source_document"]["id"] == created["document"]["id"]
    assert failure["group"]["count"] == 2
    assert len(failure["group"]["segments"]) == 2
    assert notifications["count"] == 1
    assert detail is not None
    assert detail["source_document"]["id"] == created["document"]["id"]
    assert detail["source_preview_url"].endswith(f"/api/documents/{created['document']['id']}/file/pdf")
    assert detail["split_segment"]["pages"] == [1]
    assert len(detail["related_failures"]) == 2
