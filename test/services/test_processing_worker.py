"""Focused tests for durable processing job claims and recovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, call

from modules.db.connection import connect
from modules.services.startup_migration_service import initialize_database
from modules.db.repositories import ProcessingJobRepository
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.processing_worker import ProcessingWorker
from modules.workflow_manager import RetryableWorkflowStartError
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


def test_worker_retries_transient_start_failure_then_completes(tmp_path):
    class TransientProcessor(FakeProcessor):
        def process_file(self, **kwargs: object) -> bool:
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise RetryableWorkflowStartError("Temporary startup failure")
            return True

    processor = TransientProcessor()
    config, _, _ = build_job(tmp_path, processor=processor)
    worker = ProcessingWorker(config, file_processor=processor, worker_id="test-worker")

    assert worker.run_once() is True
    with connect(config) as conn:
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
        assert job["status"] == "queued"
        assert job["attempt_count"] == 1
        assert conn.execute("SELECT status FROM documents").fetchone()[0] == "processing"
        conn.execute("UPDATE processing_jobs SET available_at = '2000-01-01T00:00:00+00:00'")

    assert worker.run_once() is True
    with connect(config) as conn:
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
    assert job["status"] == "completed"
    assert job["attempt_count"] == 2
    assert len(processor.calls) == 2


def test_worker_does_not_retry_unclassified_exception(tmp_path):
    class BrokenProcessor(FakeProcessor):
        def process_file(self, **kwargs: object) -> bool:
            raise ValueError("Permanent setup failure")

    config, _, _ = build_job(tmp_path)
    worker = ProcessingWorker(config, file_processor=BrokenProcessor(), worker_id="test-worker")

    assert worker.run_once() is True
    with connect(config) as conn:
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
        document = conn.execute("SELECT status FROM documents").fetchone()
    assert job["status"] == "failed"
    assert job["attempt_count"] == 1
    assert document["status"] == "failed"


def test_worker_exhausts_transient_start_retries(tmp_path):
    class TransientProcessor(FakeProcessor):
        def process_file(self, **kwargs: object) -> bool:
            raise RetryableWorkflowStartError("Temporary startup failure")

    config, _, _ = build_job(tmp_path)
    worker = ProcessingWorker(config, file_processor=TransientProcessor(), worker_id="test-worker")
    for attempt in range(1, 4):
        assert worker.run_once() is True
        with connect(config) as conn:
            job = conn.execute("SELECT * FROM processing_jobs").fetchone()
            assert job["attempt_count"] == attempt
            if attempt < 3:
                assert job["status"] == "queued"
                conn.execute("UPDATE processing_jobs SET available_at = '2000-01-01T00:00:00+00:00'")
            else:
                assert job["status"] == "failed"
                assert conn.execute("SELECT status FROM documents").fetchone()[0] == "failed"


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


def test_worker_reports_busy_and_ready_around_work(tmp_path):
    config, _, processor = build_job(tmp_path)
    reporter = Mock()
    worker = ProcessingWorker(
        config,
        file_processor=processor,
        worker_id="health-worker",
        health_reporter=reporter,
    )

    assert worker.run_once() is True

    assert reporter.set_status.call_args_list[0].args[0] == "busy"
    assert reporter.set_status.call_args_list[0].args[1]["job_id"]
    assert reporter.set_status.call_args_list[-1] == call("ready")
