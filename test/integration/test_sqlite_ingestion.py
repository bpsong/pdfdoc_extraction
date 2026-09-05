"""Assigned ingestion persists jobs before the worker starts processing."""
from pathlib import Path

from modules.db.connection import connect
from modules.file_processor import FileProcessor
from modules.services.ingress_binding_service import IngressBindingService
from modules.services.processing_worker import ProcessingWorker
from modules.services.watch_folder_coordinator import WatchFolderCoordinator
from test.integration.test_batch_upload_api import build_client


def _upload(client, config):
    response = client.post(
        "/api/batches/upload", data={"pipeline_version_id": config.pipeline_version_id},
        files=[("files", ("invoice.pdf", b"%PDF-1.4\n", "application/pdf"))],
    )
    assert response.status_code == 200
    return response.json()


def test_web_upload_creates_sqlite_batch_document_and_workflow_context(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)
    uploaded = _upload(client, config)
    assert workflow.calls == []
    worker = ProcessingWorker(config, file_processor=FileProcessor(config, None, workflow))
    assert worker.run_once()
    with connect(config) as conn:
        document = conn.execute("SELECT * FROM documents").fetchone()
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
    assert document["id"] == uploaded["document_ids"][0]
    assert document["batch_id"] == uploaded["batch_id"]
    assert document["pipeline_version_id"] == config.pipeline_version_id
    assert job["status"] == "completed"
    assert workflow.calls[0]["document_id"] == document["id"]
    assert workflow.calls[0]["batch_id"] == document["batch_id"]
    assert workflow.calls[0]["source"] == "web"


def test_watch_folder_ingestion_creates_matching_sqlite_records(tmp_path, monkeypatch):
    _, config, workflow = build_client(tmp_path, monkeypatch)
    watch = Path(config.get("watch_folder.dir"))
    with connect(config) as conn:
        binding = IngressBindingService(conn, config).create(
            folder_path=str(watch), pipeline_version_id=config.pipeline_version_id,
            enabled=True, user="admin",
        )
    (watch / "watched.pdf").write_bytes(b"%PDF-1.7\n")
    processor = FileProcessor(config, None, workflow)
    coordinator = WatchFolderCoordinator(config, processor)
    assert coordinator.scan_once() == 1
    assert coordinator.scan_once() == 0
    assert workflow.calls == []
    assert ProcessingWorker(config, file_processor=processor).run_once()
    with connect(config) as conn:
        batch = conn.execute("SELECT * FROM batches").fetchone()
        document = conn.execute("SELECT * FROM documents").fetchone()
    assert batch["ingress_binding_id"] == binding["id"]
    assert document["pipeline_version_id"] == config.pipeline_version_id
    assert workflow.calls[0]["source"] == "watch_folder"
    assert workflow.calls[0]["document_id"] == document["id"]


def test_retried_watch_processing_reuses_sqlite_ingestion_state(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)
    uploaded = _upload(client, config)
    processor = FileProcessor(config, None, workflow)
    original = processor.process_file
    attempts = []

    def transient_failure(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise OSError("Synthetic transient I/O failure")
        return original(**kwargs)

    monkeypatch.setattr(processor, "process_file", transient_failure)
    worker = ProcessingWorker(config, file_processor=processor)
    assert worker.run_once()
    with connect(config) as conn:
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
        assert job["status"] == "queued"
        conn.execute("UPDATE processing_jobs SET available_at = '2000-01-01T00:00:00+00:00'")
        conn.commit()
    assert worker.run_once()
    assert attempts[0]["document_id"] == attempts[1]["document_id"] == uploaded["document_ids"][0]
    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert conn.execute("SELECT status FROM processing_jobs").fetchone()[0] == "completed"


def test_batch_api_endpoints_return_sqlite_state(tmp_path, monkeypatch):
    client, config, _ = build_client(tmp_path, monkeypatch)
    uploaded = _upload(client, config)
    batch_id = uploaded["batch_id"]
    assert client.get("/api/batches").json()[0]["id"] == batch_id
    assert client.get(f"/api/batches/{batch_id}").json()["id"] == batch_id
    documents = client.get(f"/api/batches/{batch_id}/documents").json()
    assert documents[0]["batch_id"] == batch_id
    assert documents[0]["id"] == uploaded["document_ids"][0]
