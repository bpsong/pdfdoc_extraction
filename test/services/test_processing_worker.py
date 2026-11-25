"""Focused tests for durable processing job claims and recovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from threading import Event
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from modules.db.connection import connect, managed_connect
from modules.services.startup_migration_service import initialize_database
from modules.db.repositories import JobClaim, ProcessingJobRepository
from modules.services.processing_lease import ProcessingLease
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


@pytest.mark.parametrize("old_status", ["processing", "review_required", "completed"])
def test_third_expiry_is_terminal_and_preserves_committed_state(tmp_path: Path, old_status: str) -> None:
    config, _, processor = build_job(tmp_path)
    with managed_connect(config) as conn:
        jobs = ProcessingJobRepository(conn)
        for attempt in range(1, 4):
            job = jobs.claim_next(worker_id="worker", lease_expires_at=ProcessingLease.deadline(-1))
            assert job and job["attempt_count"] == attempt
            jobs.requeue_expired()
        conn.execute("UPDATE documents SET status=?", (old_status,))

    worker = ProcessingWorker(config, file_processor=processor)
    assert worker.run_once() is False
    assert worker.run_once() is False
    with managed_connect(config) as conn:
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
        assert (job["status"], job["attempt_count"], job["worker_id"]) == ("failed", 3, None)
        assert job["last_error"] == "lease_expired_attempts_exhausted"
        expected = "failed" if old_status == "processing" else old_status
        assert conn.execute("SELECT status FROM documents").fetchone()[0] == expected
    assert processor.calls == []


def test_legacy_exhausted_queued_job_is_closed(tmp_path: Path) -> None:
    config, _, _ = build_job(tmp_path)
    with managed_connect(config) as conn:
        conn.execute("UPDATE processing_jobs SET attempt_count=6")
        assert ProcessingJobRepository(conn).claim_next(
            worker_id="worker", lease_expires_at=ProcessingLease.deadline(30),
        ) is None
    assert ProcessingWorker(config).run_once() is False
    with managed_connect(config) as conn:
        assert tuple(conn.execute("SELECT status, attempt_count FROM processing_jobs").fetchone()) == ("failed", 6)


@pytest.mark.parametrize("stale_result", [True, False, OSError("retry")])
def test_stale_attempt_cannot_write_after_same_worker_id_reclaims(
    tmp_path: Path, stale_result: bool | OSError,
) -> None:
    config, _, processor = build_job(tmp_path)

    def replace_claim(**kwargs: object) -> bool:
        with managed_connect(config) as conn:
            jobs = ProcessingJobRepository(conn)
            row = conn.execute("SELECT * FROM processing_jobs").fetchone()
            old = JobClaim(row["id"], row["worker_id"], row["attempt_count"])
            conn.execute("UPDATE processing_jobs SET lease_expires_at=?", (ProcessingLease.deadline(-1),))
            assert not jobs.renew(old, ProcessingLease.deadline(60))
            assert not jobs.mark_completed(old)
            jobs.requeue_expired()
            job = jobs.claim_next(worker_id=old.worker_id, lease_expires_at=ProcessingLease.deadline(60))
            assert job and job["attempt_count"] == 2
            assert not jobs.renew(old, ProcessingLease.deadline(60))
            conn.execute("UPDATE documents SET status='review_required'")
        if isinstance(stale_result, OSError):
            raise stale_result
        return stale_result

    processor.process_file = replace_claim
    assert ProcessingWorker(config, file_processor=processor, worker_id="same-id").run_once()
    with managed_connect(config) as conn:
        row = conn.execute("SELECT status, attempt_count, last_error FROM processing_jobs").fetchone()
        assert tuple(row) == ("running", 2, None)
        assert conn.execute("SELECT status FROM documents").fetchone()[0] == "review_required"


def test_blocked_processor_keeps_claim_across_multiple_renewals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _, processor = build_job(tmp_path)
    renewed = Event()
    renewals = []
    original = ProcessingJobRepository.renew

    def observe(self: ProcessingJobRepository, claim: JobClaim, lease_expires_at: str) -> bool:
        result = original(self, claim, lease_expires_at)
        if result:
            renewals.append(lease_expires_at)
            if len(renewals) >= 7:
                renewed.set()
        return result

    monkeypatch.setattr(ProcessingJobRepository, "renew", observe)
    worker = ProcessingWorker(config, file_processor=processor)
    worker.lease_seconds = 1

    def process(**kwargs: object) -> bool:
        assert renewed.wait(8)
        assert not ProcessingWorker(config, file_processor=FakeProcessor()).run_once()
        return True

    processor.process_file = process
    assert worker.run_once()
    with managed_connect(config) as conn:
        assert tuple(conn.execute("SELECT status, attempt_count FROM processing_jobs").fetchone()) == ("completed", 1)


def test_worker_retries_transient_lease_renewal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _, processor = build_job(tmp_path)
    failed = Event()
    renewed = Event()
    original = ProcessingJobRepository.renew

    def renew(self: ProcessingJobRepository, claim: JobClaim, lease_expires_at: str) -> bool:
        if not failed.is_set():
            failed.set()
            raise sqlite3.OperationalError("temporary database lock")
        result = original(self, claim, lease_expires_at)
        if result:
            renewed.set()
        return result

    def deadline() -> str:
        with managed_connect(config) as conn:
            return conn.execute("SELECT lease_expires_at FROM processing_jobs").fetchone()[0]

    def process(**kwargs: object) -> bool:
        processor.calls.append(kwargs)
        initial = deadline()
        assert renewed.wait(8)
        assert deadline() > initial
        assert not ProcessingWorker(config, file_processor=FakeProcessor()).run_once()
        return True

    monkeypatch.setattr(ProcessingJobRepository, "renew", renew)
    processor.process_file = process
    worker = ProcessingWorker(config, file_processor=processor)
    worker.lease_seconds = 3
    assert worker.run_once()
    assert len(processor.calls) == 1
    with managed_connect(config) as conn:
        row = conn.execute("SELECT status, attempt_count FROM processing_jobs").fetchone()
        assert tuple(row) == ("completed", 1)


def test_real_worker_stops_before_housekeeping_after_claim_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.workflow_loader import WorkflowLoader
    from test.workflow.test_workflow_task_run_tracking import _patch_prefect

    config, _, _ = build_job(tmp_path)
    config.get_all()["watch_folder"] = {"processing_dir": str(tmp_path)}
    _patch_prefect(monkeypatch)

    class InterruptedTask:
        def __init__(self, **kwargs: object) -> None:
            pass

        def on_start(self, context: dict) -> None:
            pass

        def run(self, context: dict) -> dict:
            with managed_connect(config) as conn:
                conn.execute("UPDATE processing_jobs SET lease_expires_at=?", (ProcessingLease.deadline(-1),))
                jobs = ProcessingJobRepository(conn)
                jobs.requeue_expired()
                jobs.claim_next(worker_id="replacement", lease_expires_at=ProcessingLease.deadline(60))
                conn.execute("UPDATE documents SET status='review_required'")
            return context

    monkeypatch.setattr(WorkflowLoader, "_import_task_class", lambda *args: InterruptedTask)
    assert ProcessingWorker(config).run_once()
    with managed_connect(config) as conn:
        assert conn.execute("SELECT status FROM documents").fetchone()[0] == "review_required"
        assert conn.execute("SELECT worker_id FROM processing_jobs").fetchone()[0] == "replacement"
        assert [row[0] for row in conn.execute("SELECT task_key FROM task_runs")] == ["extract"]

def test_recovery_rolls_back_job_when_document_transition_fails(tmp_path: Path) -> None:
    import sqlite3

    config, _, _ = build_job(tmp_path)
    with managed_connect(config) as conn:
        conn.execute("UPDATE processing_jobs SET attempt_count=max_attempts")
        conn.execute("""
            CREATE TRIGGER reject_transition BEFORE UPDATE OF status ON documents
            BEGIN SELECT RAISE(ABORT, 'synthetic document failure'); END
        """)
    with pytest.raises(sqlite3.IntegrityError, match="synthetic document failure"):
        ProcessingWorker(config).run_once()
    with managed_connect(config) as conn:
        assert conn.execute("SELECT status FROM processing_jobs").fetchone()[0] == "queued"
        assert conn.execute("SELECT status FROM documents").fetchone()[0] == "queued"
        conn.execute("DROP TRIGGER reject_transition")
    assert ProcessingWorker(config).run_once() is False
    with managed_connect(config) as conn:
        assert tuple(conn.execute("SELECT status, failed_documents FROM batches").fetchone()) == ("failed", 1)
