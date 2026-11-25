"""Durable SQLite-backed document processing worker."""

from __future__ import annotations

import logging
from threading import Event
from typing import Any
import uuid

from modules.config_protocol import ConfigProvider
from modules.db.connection import immediate_transaction, json_loads, managed_connect
from modules.db.repositories import BatchRepository, JobClaim, ProcessingJobRepository, ReviewRepository
from modules.file_processor import FileProcessor
from modules.services.processing_lease import JobClaimLost, ProcessingLease
from modules.services.processing_job_service import ProcessingJobService
from modules.services.runtime_health_service import RuntimeHealthReporter
from modules.services.workflow_state_service import WorkflowStateService
from modules.workflow_manager import RetryableWorkflowStartError, WorkflowManager


logger = logging.getLogger(__name__)


class ProcessingWorker:
    """Claim durable jobs and execute their assigned workflow versions."""

    def __init__(
        self,
        config: ConfigProvider,
        *,
        file_processor: Any | None = None,
        worker_id: str | None = None,
        health_reporter: RuntimeHealthReporter | None = None,
    ) -> None:
        self.config = config
        self.worker_id = worker_id or f"worker-{uuid.uuid4()}"
        self.poll_interval = max(
            0.1, float(config.get("processing_queue.poll_interval", 1) or 1)
        )
        self.lease_seconds = max(
            30, int(config.get("processing_queue.lease_seconds", 3600) or 3600)
        )
        self.retry_delay = max(
            0.1, float(config.get("processing_queue.retry_delay", 5) or 5)
        )
        self.stop_event = Event()
        self.health_reporter = health_reporter
        self.file_processor = file_processor

    def run_once(self) -> bool:
        """Claim and process one job, returning whether work was claimed."""
        with managed_connect(self.config) as conn, immediate_transaction(conn):
            ProcessingJobService(conn).recover_expired()
            job = ProcessingJobRepository(conn).claim_next(
                worker_id=self.worker_id, lease_expires_at=ProcessingLease.deadline(self.lease_seconds),
            )
            if job is None:
                return False
            document_id = str(job["document_id"])
            claim = JobClaim(str(job["id"]), self.worker_id, int(job["attempt_count"]))
            if claim.attempt_count > 1:
                review = ReviewRepository(conn).find_latest_for_document(document_id, review_kind="extraction")
                if review and json_loads(review.get("metadata_json"), {}).get("lookup_scope"):
                    # The lookup gate committed the review and its paused task before the old worker died.
                    ProcessingJobRepository(conn).mark_completed(claim)
                    return True
            document = WorkflowStateService(conn).transition_document(
                document_id, "processing", reason="processing_job_claimed",
            )

        lease = ProcessingLease(self.config, claim, self.lease_seconds)
        if self.health_reporter is not None:
            self.health_reporter.set_status("busy", {"job_id": claim.job_id})
        try:
            with lease.maintain():
                self._execute(job, document, lease)
        finally:
            if self.health_reporter is not None and not self.stop_event.is_set():
                self.health_reporter.set_status("ready")
        return True

    def _execute(
        self, job: dict[str, Any], document: dict[str, Any], lease: ProcessingLease,
    ) -> None:
        retry_at = None
        reason = "processing_job_failed"
        try:
            with managed_connect(self.config) as conn:
                lease.check(conn)
                batch = BatchRepository(conn).get(str(job["batch_id"]))
                if batch is None:
                    raise ValueError("Queued batch no longer exists.")
            processor = self.file_processor or FileProcessor(
                self.config, None, WorkflowManager(self.config, lease=lease),
            )
            result = processor.process_file(
                filepath=str(document["file_path"]), unique_id=str(document["id"]),
                source=str(batch["source"]),
                original_filename=str(document.get("original_filename") or document["file_path"]),
                batch_id=str(batch["id"]), document_id=str(document["id"]), create_sqlite_state=False,
            )
            if result is not False:
                with managed_connect(self.config) as conn:
                    ProcessingJobRepository(conn).mark_completed(lease.claim)
                return
            error = "Workflow execution returned failure."
        except JobClaimLost:
            logger.info("Stopped execution after losing processing claim %s", lease.claim)
            return
        except Exception as exc:
            logger.exception("Processing job failed: job_id=%s", lease.claim.job_id)
            error = str(exc)[:2000]
            reason = "processing_job_exception"
            if isinstance(exc, (RetryableWorkflowStartError, OSError)):
                retry_at = ProcessingJobService.retry_at(self.retry_delay)

        with managed_connect(self.config) as conn, immediate_transaction(conn):
            updated = ProcessingJobRepository(conn).mark_failed(lease.claim, error=error, retry_at=retry_at)
            if updated and updated["status"] == "failed":
                WorkflowStateService(conn).transition_document(str(document["id"]), "failed", reason=reason)

    def run(self) -> None:
        """Poll until shutdown is requested."""
        logger.info("Durable processing worker started: worker_id=%s", self.worker_id)
        while not self.stop_event.is_set():
            if not self.run_once():
                self.stop_event.wait(self.poll_interval)

    def stop(self) -> None:
        """Request a graceful stop after the current job."""
        self.stop_event.set()


def build_worker(
    config: ConfigProvider,
    *,
    health_reporter: RuntimeHealthReporter | None = None,
) -> ProcessingWorker:
    """Build the production worker with the real workflow executor."""
    return ProcessingWorker(config, health_reporter=health_reporter)
