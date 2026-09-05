"""Focused tests for durable processing job claims and recovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import ProcessingJobRepository
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.processing_worker import ProcessingWorker
from test.helpers_sqlite import TempConfig
from test.services.test_ingestion_assignment_service import publish_pipeline


class FakeProcessor:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def process_file(self, **kwargs: object) -> bool:
        self.calls.append(kwargs)
        return self.result


def build_job(tmp_path, *, processor: FakeProcessor | None = None):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline_secrets": {"test-api": "runtime-secret"},
            "processing_queue": {"retry_delay": 0.1},
        },
    )
    initialize_database(config)
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="worker")
        created = IngestionAssignmentService(conn, config).create_batch(
            pipeline_version_id=version["id"],
            role="operator",
            source="web",
            assignment_source="upload",
            files=[
                {
                    "document_id": "document-1",
                    "file_path": str(tmp_path / "document-1.pdf"),
                    "original_filename": "invoice.pdf",
                    "status": "queued",
                }
            ],
            user="operator",
        )
    return config, created, processor or FakeProcessor()


def test_worker_claims_and_completes_one_queued_document(tmp_path):
    config, created, processor = build_job(tmp_path)
    worker = ProcessingWorker(config, file_processor=processor, worker_id="test-worker")

    assert worker.run_once() is True
    assert len(processor.calls) == 1
    assert processor.calls[0]["batch_id"] == created["batch"]["id"]
    assert processor.calls[0]["document_id"] == "document-1"

    with connect(config) as conn:
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
        document = conn.execute(
            "SELECT status FROM documents WHERE id = 'document-1'"
        ).fetchone()
    assert job["status"] == "completed"
    assert job["attempt_count"] == 1
    assert document["status"] == "processing"


def test_worker_marks_workflow_failure_as_terminal(tmp_path):
    config, _, processor = build_job(tmp_path, processor=FakeProcessor(result=False))
    worker = ProcessingWorker(config, file_processor=processor, worker_id="test-worker")

    assert worker.run_once() is True

    with connect(config) as conn:
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
        document = conn.execute(
            "SELECT status FROM documents WHERE id = 'document-1'"
        ).fetchone()
    assert job["status"] == "failed"
    assert document["status"] == "failed"


def test_expired_lease_is_requeued_before_claim(tmp_path):
    config, created, processor = build_job(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with connect(config) as conn:
        jobs = ProcessingJobRepository(conn)
        jobs.claim_next(worker_id="crashed-worker", lease_expires_at=expired)

    worker = ProcessingWorker(config, file_processor=processor, worker_id="recovery-worker")
    assert worker.run_once() is True

    with connect(config) as conn:
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
    assert job["status"] == "completed"
    assert job["attempt_count"] == 2
    assert processor.calls[0]["document_id"] == created["documents"][0]["id"]
