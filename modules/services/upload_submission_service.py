"""Finalize web uploads, commit accepted batches, and look up durable receipts."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from modules.config_protocol import ConfigProvider
from modules.db.connection import immediate_transaction, managed_connect
from modules.db.repositories import PendingUploadRepository, UploadSubmissionRepository
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.upload_receiver import ReceivedUploadBatch, remove_pending_uploads


def accept_staged_upload(
    config: ConfigProvider, *, processing_root: Path, received: ReceivedUploadBatch,
    files: list[dict[str, Any]], user: str, role: str,
    submission_id: str | None, fingerprint: str | None,
) -> dict[str, Any]:
    """Commit file reservations before promotion and release them with the batch."""
    paths = [str(item["file_path"]) for item in files]
    with managed_connect(config) as conn, immediate_transaction(conn):
        if any(os.path.lexists(path) for path in paths):
            raise FileExistsError("An upload destination already exists")
        PendingUploadRepository(conn).reserve(paths)

    accepted = False
    try:
        for upload, path in zip(received.files, paths, strict=True):
            upload.path.replace(path)
        with managed_connect(config) as conn, immediate_transaction(conn):
            created = IngestionAssignmentService(conn, config).create_batch(
                pipeline_version_id=received.pipeline_version_id, role=role,
                source="web", assignment_source="upload", files=files, user=user,
                metadata={"uploaded_by": user, "file_count": len(files)},
                status="queued", submission_id=submission_id, fingerprint=fingerprint,
            )
            replayed = bool(created.get("replayed"))
            if not replayed:
                PendingUploadRepository(conn).release(paths)
        accepted = not replayed
        return created
    finally:
        if not accepted:
            # Replays own only their new copies. Failed commits leave the
            # reservations recoverable even if this process dies during cleanup.
            remove_pending_uploads(config, processing_root, paths)


def submission_fingerprint(received: ReceivedUploadBatch) -> str:
    """Hash ordered file contents and metadata, independently of multipart encoding."""
    files = []
    for upload in received.files:
        with upload.path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        files.append([upload.filename, upload.content_type, upload.size_bytes, digest])
    payload = json.dumps([received.pipeline_version_id, files], ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def submission_status(conn: sqlite3.Connection, user: str, submission_id: str) -> dict:
    """An absent receipt is uncertain: an in-flight request may still commit."""
    row = UploadSubmissionRepository(conn).get(user, submission_id)
    if row is None:
        return {"status": "unknown"}
    created = json.loads(row["response_json"])
    if created.get("purged"):
        return {"status": "purged"}
    return {"status": "accepted", "batch_id": created["batch"]["id"]}
