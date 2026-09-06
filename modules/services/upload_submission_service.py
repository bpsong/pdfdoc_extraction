"""Content identity and durable upload receipt lookup."""

import hashlib
import json
import sqlite3

from modules.db.repositories import UploadSubmissionRepository
from modules.services.upload_receiver import ReceivedUploadBatch


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
    return {"status": "accepted", "batch_id": created["batch"]["id"]}
