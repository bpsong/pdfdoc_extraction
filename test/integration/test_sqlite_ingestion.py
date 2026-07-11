from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.file_processor import FileProcessor
from modules.watch_folder_monitor import WatchFolderMonitor


class TempConfig:
    def __init__(self, root: Path) -> None:
        self._config_path = root / "config.yaml"
        self._values = {
            "database.path": str(root / "app.sqlite3"),
            "database.run_migrations_on_startup": True,
            "web.upload_dir": str(root / "web_upload"),
            "watch_folder.dir": str(root / "watch"),
            "watch_folder.processing_dir": str(root / "processing"),
            "watch_folder.validate_pdf_header": True,
        }
        for key in ("web.upload_dir", "watch_folder.dir", "watch_folder.processing_dir"):
            Path(self._values[key]).mkdir(parents=True, exist_ok=True)

    def get(self, key, default=None):
        return self._values.get(key, default)

    def get_all(self):
        return dict(self._values)


class FakeUpload:
    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        import io

        self.file = io.BytesIO(data)


class FakeWorkflowManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def trigger_workflow_for_file(self, **kwargs):
        self.calls.append(kwargs)


class RetryWorkflowManager(FakeWorkflowManager):
    def trigger_workflow_for_file(self, **kwargs):
        super().trigger_workflow_for_file(**kwargs)
        return len(self.calls) > 1


def test_web_upload_creates_sqlite_batch_document_and_workflow_context(tmp_path):
    config = TempConfig(tmp_path)
    initialize_database(config)
    workflow = FakeWorkflowManager()
    processor = FileProcessor(config, lambda func, *args, **kwargs: func(*args, **kwargs), workflow)

    file_id = processor.process_web_upload(FakeUpload("invoice.pdf", b"%PDF-1.4"), source="web")

    with connect(config) as conn:
        batch = conn.execute("SELECT * FROM batches").fetchone()
        document = conn.execute("SELECT * FROM documents").fetchone()

    assert batch["source"] == "web"
    assert batch["original_filename"] == "invoice.pdf"
    assert document["id"] == file_id
    assert document["batch_id"] == batch["id"]
    assert workflow.calls[0]["batch_id"] == batch["id"]
    assert workflow.calls[0]["document_id"] == file_id
    assert workflow.calls[0]["unique_id"] == file_id


def test_watch_folder_ingestion_creates_matching_sqlite_records(tmp_path):
    config = TempConfig(tmp_path)
    initialize_database(config)
    workflow = FakeWorkflowManager()
    processor = FileProcessor(config, lambda func, *args, **kwargs: func(*args, **kwargs), workflow)

    sample = Path(config.get("watch_folder.dir")) / "watched.pdf"
    sample.write_bytes(b"%PDF-1.7")
    monitor = WatchFolderMonitor(config, processor.process_file, None)
    monitor._process_existing_files()

    with connect(config) as conn:
        batch = conn.execute("SELECT * FROM batches").fetchone()
        document = conn.execute("SELECT * FROM documents").fetchone()

    assert batch["source"] == "watch_folder"
    assert batch["original_filename"] == "watched.pdf"
    assert document["batch_id"] == batch["id"]
    assert workflow.calls[0]["source"] == "watch_folder"
    assert workflow.calls[0]["batch_id"] == batch["id"]
    assert workflow.calls[0]["document_id"] == document["id"]


def test_retried_watch_processing_reuses_sqlite_ingestion_state(tmp_path):
    config = TempConfig(tmp_path)
    initialize_database(config)
    workflow = RetryWorkflowManager()
    processor = FileProcessor(config, lambda func, *args, **kwargs: func(*args, **kwargs), workflow)
    source = Path(config.get("watch_folder.processing_dir")) / "document.pdf"
    source.write_bytes(b"%PDF-1.7")

    first = processor.process_file(str(source), "document", "watch_folder", "invoice.pdf")
    second = processor.process_file(str(source), "document", "watch_folder", "invoice.pdf")

    with connect(config) as conn:
        batch_count = conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        document_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    assert first is False
    assert second is True
    assert batch_count == 1
    assert document_count == 1
    assert workflow.calls[0]["batch_id"] == workflow.calls[1]["batch_id"]
    assert workflow.calls[0]["document_id"] == workflow.calls[1]["document_id"]


def test_batch_api_endpoints_return_sqlite_state(tmp_path, monkeypatch):
    config = TempConfig(tmp_path)
    initialize_database(config)
    workflow = FakeWorkflowManager()
    processor = FileProcessor(config, lambda func, *args, **kwargs: func(*args, **kwargs), workflow)
    processor.process_web_upload(FakeUpload("invoice.pdf", b"%PDF-1.4"), source="web")

    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, processor

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    client = TestClient(app)

    batches = client.get("/api/batches").json()
    batch_id = batches[0]["id"]

    assert client.get("/api/batches").status_code == 200
    assert client.get(f"/api/batches/{batch_id}").json()["id"] == batch_id
    documents = client.get(f"/api/batches/{batch_id}/documents").json()
    assert documents[0]["batch_id"] == batch_id
