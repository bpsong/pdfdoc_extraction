"""Sequential coordinator for SQLite-backed multi-folder ingestion bindings."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from threading import Event, RLock
import time
import uuid
from typing import Any

from modules.config_protocol import ConfigProvider
from modules.db.connection import connect
from modules.db.repositories import DocumentRepository
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.ingress_binding_service import IngressBindingService
from modules.utils import is_pdf_header, windows_long_path


logger = logging.getLogger(__name__)


class WatchFolderCoordinator:
    """Reconcile bindings and claim files sequentially under one process lock."""

    def __init__(self, config: ConfigProvider, file_processor: Any) -> None:
        self.config = config
        self.file_processor = file_processor
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

    def scan_once(self) -> int:
        """Reconcile current bindings and process each folder sequentially."""
        processed = 0
        with self._lock:
            with connect(self.config) as conn:
                bindings = IngressBindingService(conn, self.config).list()
            for binding in bindings:
                if not binding["enabled"]:
                    continue
                try:
                    processed += self._scan_binding(binding)
                except Exception:
                    logger.exception(
                        "Watch binding scan failed for binding_id=%s",
                        binding["id"],
                    )
        return processed

    def _scan_binding(self, binding: dict[str, Any]) -> int:
        folder = Path(str(binding["folder_path"]))
        if not folder.is_dir():
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
        """Move first to claim, then persist and execute with captured binding IDs."""
        document_id = str(uuid.uuid4())
        destination = self.processing_dir / f"{document_id}.pdf"
        try:
            shutil.move(
                windows_long_path(str(source_path)),
                windows_long_path(str(destination)),
            )
        except OSError:
            logger.warning(
                "Watch file claim failed for binding_id=%s", binding["id"]
            )
            return False

        try:
            with connect(self.config) as conn:
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
                            "status": "processing",
                            "metadata": {"ingress_binding_id": binding["id"]},
                        }
                    ],
                    user=None,
                    metadata={"ingress_binding_id": binding["id"]},
                    ingress_binding_id=str(binding["id"]),
                    status="processing",
                )
            batch = created["batch"]
            document = created["documents"][0]
        except Exception:
            self._restore_claim(destination, source_path)
            logger.exception(
                "Watch assignment failed for binding_id=%s", binding["id"]
            )
            return False

        for attempt in range(1, self.retry_attempts + 1):
            try:
                result = self.file_processor.process_file(
                    filepath=str(destination),
                    unique_id=str(document["id"]),
                    source="watch_folder",
                    original_filename=source_path.name,
                    batch_id=str(batch["id"]),
                    document_id=str(document["id"]),
                    create_sqlite_state=False,
                )
                if result is not False:
                    return True
            except Exception:
                logger.warning(
                    "Watch processing attempt failed for binding_id=%s attempt=%s",
                    binding["id"],
                    attempt,
                )
            if attempt < self.retry_attempts:
                time.sleep(self.retry_delay)
        with connect(self.config) as conn:
            DocumentRepository(conn).update_status(str(document["id"]), "failed")
        return False

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
