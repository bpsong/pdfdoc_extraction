from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.file_processor import FileProcessor


class TempConfig:
    """Config stub for batch upload API tests."""

    def __init__(self, root: Path) -> None:
        self._config_path = root / "config.yaml"
        self._values = {
            "database.path": str(root / "app.sqlite3"),
            "database.run_migrations_on_startup": True,
            "web.upload_dir": str(root / "web_upload"),
            "watch_folder.dir": str(root / "watch"),
            "watch_folder.processing_dir": str(root / "processing"),
            "watch_folder.validate_pdf_header": True,
            "tasks": {
                "extract_invoice": {
                    "module": "standard_step.extraction.extract_pdf_v2",
                    "class": "ExtractPdfV2Task",
                    "params": {"api_key": "secret"},
                },
                "store_json": {
                    "module": "standard_step.storage.store_metadata_as_json",
                    "class": "StoreMetadataAsJson",
                },
            },
            "pipeline": ["extract_invoice", "store_json"],
        }
        for key in ("web.upload_dir", "watch_folder.dir", "watch_folder.processing_dir"):
            Path(self._values[key]).mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def get_all(self) -> dict[str, Any]:
        return dict(self._values)


class FakeWorkflowManager:
    """Workflow manager stub that records trigger calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def trigger_workflow_for_file(self, **kwargs: Any) -> bool:
        self.calls.append(kwargs)
        return True


def build_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, TempConfig, FakeWorkflowManager]:
    """Build a test client with real SQLite state and fake workflow execution."""

    config = TempConfig(tmp_path)
    initialize_database(config)
    workflow = FakeWorkflowManager()
    processor = FileProcessor(config, lambda func, *args, **kwargs: func(*args, **kwargs), workflow)
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, workflow, processor

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    return TestClient(app), config, workflow


def test_batch_upload_api_creates_one_batch_for_multiple_pdfs(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("invoice_a.pdf", b"%PDF-1.4\ninvoice-a", "application/pdf")),
            ("files", ("invoice_b.pdf", b"%PDF-1.4\ninvoice-b", "application/pdf")),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert len(payload["document_ids"]) == 2

    with connect(config) as conn:
        batches = conn.execute("SELECT * FROM batches").fetchall()
        documents = conn.execute("SELECT * FROM documents ORDER BY original_filename").fetchall()
        source_files = conn.execute(
            "SELECT * FROM document_files WHERE file_type = 'source_original'"
        ).fetchall()

    assert len(batches) == 1
    assert batches[0]["id"] == payload["batch_id"]
    assert batches[0]["source"] == "web"
    assert batches[0]["total_documents"] == 2
    metadata = json_loads(batches[0]["metadata_json"])
    snapshot = metadata["pipeline_snapshot"]
    assert [step["key"] for step in snapshot["steps"]] == ["extract_invoice", "store_json"]
    assert snapshot["steps"][0]["category"] == "extract"
    assert "params" not in snapshot["steps"][0]
    assert [document["original_filename"] for document in documents] == ["invoice_a.pdf", "invoice_b.pdf"]
    assert {document["id"] for document in documents} == set(payload["document_ids"])
    assert len(source_files) == 2
    assert all(Path(document["file_path"]).exists() for document in documents)
    assert len(workflow.calls) == 2
    assert {call["batch_id"] for call in workflow.calls} == {payload["batch_id"]}
    assert {call["document_id"] for call in workflow.calls} == set(payload["document_ids"])


def test_batch_upload_api_rejects_invalid_pdf_without_persisting_state(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("not-a-pdf.txt", b"%PDF-1.4\ntext", "text/plain")),
        ],
    )

    assert response.status_code == 400
    with connect(config) as conn:
        batch_count = conn.execute("SELECT COUNT(*) AS count FROM batches").fetchone()["count"]
        document_count = conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]

    assert batch_count == 0
    assert document_count == 0
    assert workflow.calls == []
