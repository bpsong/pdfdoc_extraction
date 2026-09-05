"""Durable SQLite-backed document processing worker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from threading import Event
from typing import Any
import uuid

from modules.config_protocol import ConfigProvider
from modules.db.connection import connect
from modules.db.repositories import BatchRepository, DocumentRepository, ProcessingJobRepository
from modules.file_processor import FileProcessor
from modules.services.processing_job_service import ProcessingJobService
from modules.services.runtime_health_service import RuntimeHealthReporter
from modules.services.workflow_state_service import WorkflowStateService
from modules.workflow_manager import WorkflowManager


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
        self.file_processor = file_processor or FileProcessor(
            config, None, WorkflowManager(config)
        )

    def run_once(self) -> bool:
        """Claim and process one job, returning whether work was claimed."""
        with connect(self.config) as conn:
            jobs = ProcessingJobRepository(conn)
            jobs.requeue_expired()
            lease_expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=self.lease_seconds)
            ).isoformat()
            job = jobs.claim_next(
                worker_id=self.worker_id,
                lease_expires_at=lease_expires_at,
            )
        if job is None:
            return False

        job_id = str(job["id"])
        document_id = str(job["document_id"])
        document: dict[str, Any] | None = None
        if self.health_reporter is not None:
            self.health_reporter.set_status("busy", {"job_id": job_id})
        try:
            with connect(self.config) as conn:
                document = DocumentRepository(conn).get(document_id)
                batch = BatchRepository(conn).get(str(job["batch_id"]))
                if document is None or batch is None:
                    raise ValueError("Queued document or batch no longer exists.")
                WorkflowStateService(conn).transition_document(
                    document_id,
                    "processing",
                    reason="processing_job_claimed",
                )

            result = self.file_processor.process_file(
                filepath=str(document["file_path"]),
                unique_id=document_id,
                source=str(batch["source"]),
                original_filename=str(document.get("original_filename") or document["file_path"]),
                batch_id=str(batch["id"]),
                document_id=document_id,
                create_sqlite_state=False,
            )
            if result is False:
                with connect(self.config) as conn:
                    WorkflowStateService(conn).transition_document(
                        document_id,
                        "failed",
                        reason="processing_job_failed",
                    )
                    ProcessingJobRepository(conn).mark_failed(
                        job_id,
                        worker_id=self.worker_id,
                        error="Workflow execution returned failure.",
                    )
                return True

            with connect(self.config) as conn:
                ProcessingJobRepository(conn).mark_completed(
                    job_id, worker_id=self.worker_id
                )
            return True
        except Exception as exc:
            error = str(exc)[:2000]
            logger.exception("Processing job failed: job_id=%s", job_id)
            with connect(self.config) as conn:
                updated = ProcessingJobRepository(conn).mark_failed(
                    job_id,
                    worker_id=self.worker_id,
                    error=error,
                    retry_at=ProcessingJobService.retry_at(self.retry_delay),
                )
                if updated and updated.get("status") == "failed" and document is not None:
                    WorkflowStateService(conn).transition_document(
                        document_id,
                        "failed",
                        reason="processing_job_exception",
                    )
            return True
        finally:
            if self.health_reporter is not None and not self.stop_event.is_set():
                self.health_reporter.set_status("ready")

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
