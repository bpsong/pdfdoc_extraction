"""Sequential coordinator for SQLite-backed multi-folder ingestion bindings."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from pathlib import Path
import shutil
from threading import Event, RLock
import uuid
from typing import Any

from modules.config_protocol import ConfigProvider
from modules.db.connection import connect, immediate_transaction
from modules.db.repositories import WatchFolderBindingRepository
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.ingress_binding_service import IngressBindingService
from modules.services.runtime_health_service import RuntimeHealthReporter
from modules.utils import is_pdf_header, windows_long_path


logger = logging.getLogger(__name__)


class WatchFolderCoordinator:
    """Reconcile bindings and claim files sequentially under one process lock."""

    def __init__(
        self,
        config: ConfigProvider,
        file_processor: Any | None = None,
        *,
        health_reporter: RuntimeHealthReporter | None = None,
    ) -> None:
        self.config = config
        # Kept as an optional constructor argument for callers that used the
        # pre-queue coordinator. Workflow execution belongs to the worker now.
        self.file_processor = file_processor
        self.health_reporter = health_reporter
        self.polling_interval = float(
            config.get("watch_folder.polling_interval", 5) or 5
        )
        self.retry_attempts = int(
            config.get("watch_folder.retry_attempts", 3) or 3
        )
        self.retry_delay = float(
            config.get("watch_folder.retry_delay", 0.2) or 0.2
        )
        self.processing_dir = Path(
            str(config.get("watch_folder.processing_dir") or "processing")
        ).resolve()
        self.processing_dir.mkdir(parents=True, exist_ok=True)
        self.stop_event = Event()
        self._lock = RLock()
        self._ignored_invalid: set[tuple[str, str]] = set()
        self._scan_issue_count = 0

    def scan_once(self) -> int:
        """Reconcile current bindings and process each folder sequentially."""
        processed = 0
        self._scan_issue_count = 0
        with self._lock:
            with connect(self.config) as conn:
                bindings = IngressBindingService(conn, self.config).list()
            for binding in bindings:
                if not binding["enabled"]:
                    continue
                try:
                    before = self._scan_issue_count
                    count = self._scan_binding(binding)
                    processed += count
                    with connect(self.config) as health_conn:
                        repo = WatchFolderBindingRepository(health_conn)
                        if repo.get(binding["id"]):
                            repo.record_health(binding["id"], issue="Folder scan or file claim failed." if self._scan_issue_count > before else None,
                                               ingested=count, ignored_count=sum(key[0] == binding["id"] for key in self._ignored_invalid))
                except Exception:
                    self._scan_issue_count += 1
                    logger.exception(
                        "Watch binding scan failed for binding_id=%s",
                        binding["id"],
                    )
        if self.health_reporter is not None:
            if self._scan_issue_count:
                self.health_reporter.set_status(
                    "degraded",
                    {"binding_issue_count": self._scan_issue_count},
                )
            else:
                self.health_reporter.set_status("ready")
        return processed

    def _scan_binding(self, binding: dict[str, Any]) -> int:
        folder = Path(str(binding["folder_path"]))
        if not folder.is_dir():
            self._scan_issue_count += 1
            logger.warning(
                "Watch binding is inaccessible: binding_id=%s", binding["id"]
            )
            return 0
        processed = 0
        try:
            candidates = sorted(
                path for path in folder.iterdir() if path.suffix.lower() == ".pdf"
            )
        except OSError:
            self._scan_issue_count += 1
            logger.warning(
                "Watch binding cannot be listed: binding_id=%s", binding["id"]
            )
            return 0
        for source_path in candidates:
            invalid_key = (str(binding["id"]), str(source_path).casefold())
            if invalid_key in self._ignored_invalid:
                continue
            if not is_pdf_header(
                str(source_path),
                read_size=5,
                attempts=self.retry_attempts,
                delay=self.retry_delay,
                logger=logger,
            ):
                self._ignored_invalid.add(invalid_key)
                logger.warning(
                    "Invalid PDF ignored for binding_id=%s", binding["id"]
                )
                continue
            if self._claim_and_process(source_path, binding):
                processed += 1
        return processed

    def _claim_and_process(
        self, source_path: Path, binding: dict[str, Any]
    ) -> bool:
        """Serialize a claim with binding mutations across application processes."""
        with connect(self.config) as conn:
            with immediate_transaction(conn):
                current = WatchFolderBindingRepository(conn).get(binding["id"])
                if not current or not current["enabled"] or current.get("retired_at"):
                    return False
                if Path(current["folder_path"]).resolve() != source_path.parent.resolve():
                    return False
                return self._claim_current(source_path, current, conn)

    def _claim_current(self, source_path: Path, binding: dict[str, Any], conn: Any) -> bool:
        """Move first to claim, then persist one durable processing job."""
        try:
            IngestionAssignmentService(conn, self.config).resolve_selection(
                str(binding["pipeline_version_id"]), role="system"
            )
        except ValueError:
            self._scan_issue_count += 1
            return False
        document_id = str(uuid.uuid4())
        destination = self.processing_dir / f"{document_id}.pdf"
        try:
            shutil.move(
                windows_long_path(str(source_path)),
                windows_long_path(str(destination)),
            )
        except OSError:
            self._scan_issue_count += 1
            logger.warning(
                "Watch file claim failed for binding_id=%s", binding["id"]
            )
            return False

        try:
            with nullcontext(conn):
                created = IngestionAssignmentService(conn, self.config).create_batch(
                    pipeline_version_id=str(binding["pipeline_version_id"]),
                    role="system",
                    source="watch_folder",
                    assignment_source="watch_folder",
                    files=[
                        {
                            "document_id": document_id,
                            "file_path": str(destination),
                            "original_filename": source_path.name,
                            "status": "queued",
                            "metadata": {"ingress_binding_id": binding["id"]},
                        }
                    ],
                    user=None,
                    metadata={"ingress_binding_id": binding["id"], "source_folder": binding["folder_path"], "binding_revision": binding.get("revision", 1)},
                    ingress_binding_id=str(binding["id"]),
                    status="queued",
                )
            batch = created["batch"]
            document = created["documents"][0]
        except Exception:
            self._scan_issue_count += 1
            self._restore_claim(destination, source_path)
            logger.exception(
                "Watch assignment failed for binding_id=%s", binding["id"]
            )
            return False

        logger.info(
            "Watch file queued for durable processing: binding_id=%s batch_id=%s document_id=%s",
            binding["id"],
            batch["id"],
            document["id"],
        )
        return True

    @staticmethod
    def _restore_claim(destination: Path, source_path: Path) -> None:
        try:
            if destination.exists() and not source_path.exists():
                shutil.move(
                    windows_long_path(str(destination)),
                    windows_long_path(str(source_path)),
                )
        except OSError:
            logger.warning("Failed to restore an unassigned watch-folder claim.")

    def start(self) -> None:
        """Run reconciliation at least once per configured polling interval."""
        while not self.stop_event.is_set():
            self.scan_once()
            self.stop_event.wait(self.polling_interval)

    def stop(self) -> None:
        """Request graceful shutdown after the current serialized claim."""
        self.stop_event.set()
