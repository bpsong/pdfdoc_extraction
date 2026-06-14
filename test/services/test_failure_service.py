from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import TaskRunRepository
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
            module_name="standard_step.extraction.extract_pdf_v2",
            class_name="ExtractPdfV2Task",
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
