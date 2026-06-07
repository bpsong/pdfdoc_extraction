from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import BatchRepository, TaskRunRepository
from modules.file_processor import FileProcessor
from modules.services.batch_service import BatchService
from modules.services.processing_state_service import build_pipeline_snapshot


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
            "tasks": {
                "extract_invoice": {
                    "module": "standard_step.extraction.extract_pdf_v2",
                    "class": "ExtractPdfV2Task",
                    "params": {"api_key": "secret"},
                },
                "review_gate": {
                    "module": "standard_step.review.review_gate",
                    "class": "ReviewGateTask",
                },
            },
            "pipeline": ["extract_invoice", "review_gate"],
        }
        for key in ("web.upload_dir", "watch_folder.dir", "watch_folder.processing_dir"):
            Path(self._values[key]).mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def get_all(self) -> dict[str, Any]:
        return dict(self._values)


class FakeWorkflowManager:
    def trigger_workflow_for_file(self, **kwargs: Any) -> bool:
        return True


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, TempConfig]:
    config = TempConfig(tmp_path)
    initialize_database(config)
    processor = FileProcessor(config, lambda func, *args, **kwargs: func(*args, **kwargs), FakeWorkflowManager())
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, processor

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    return TestClient(app), config


def test_batch_processing_state_api_returns_snapshot_and_task_states(tmp_path, monkeypatch):
    client, config = _client(tmp_path, monkeypatch)

    with connect(config) as conn:
        snapshot = build_pipeline_snapshot(config)
        created = BatchService(conn).create_ingestion_batch_with_documents(
            source="web",
            files=[{"file_path": str(tmp_path / "invoice.pdf"), "original_filename": "invoice.pdf"}],
            metadata={"pipeline_snapshot": snapshot},
            status="processing",
        )
        task_run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=created["documents"][0]["id"],
            task_key="extract_invoice",
            task_index=0,
            module_name="standard_step.extraction.extract_pdf_v2",
            class_name="ExtractPdfV2Task",
        )
        TaskRunRepository(conn).mark_completed(task_run["id"])

    response = client.get(f"/api/batches/{created['batch']['id']}/processing-state")

    assert response.status_code == 200
    payload = response.json()
    assert [step["key"] for step in payload["pipeline_snapshot"]["steps"]] == ["extract_invoice", "review_gate"]
    assert payload["aggregate_step_states"][0]["state"] == "completed"
    assert payload["documents"][0]["last_completed_step"]["key"] == "extract_invoice"
    assert "params" not in payload["pipeline_snapshot"]["steps"][0]


def test_processing_state_api_returns_404_for_missing_batch(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get("/api/batches/missing/processing-state")

    assert response.status_code == 404


def test_processing_state_api_requires_authentication(tmp_path, monkeypatch):
    config = TempConfig(tmp_path)
    initialize_database(config)
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    client = TestClient(app)

    response = client.get("/api/processing-state")

    assert response.status_code == 401


def test_processing_state_api_falls_back_for_historical_batch_without_snapshot(tmp_path, monkeypatch):
    client, config = _client(tmp_path, monkeypatch)

    with connect(config) as conn:
        batch = BatchRepository(conn).create(source="web", original_filename="old.pdf", metadata={"file_count": 1})

    response = client.get(f"/api/batches/{batch['id']}/processing-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline_snapshot"]["fallback"] is True
    assert payload["pipeline_snapshot"]["steps"][0]["key"] == "extract_invoice"


def test_processing_state_list_api_returns_recent_batches(tmp_path, monkeypatch):
    client, config = _client(tmp_path, monkeypatch)

    with connect(config) as conn:
        BatchRepository(conn).create(source="web", original_filename="one.pdf")

    response = client.get("/api/processing-state")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["batches"]) == 1
    assert payload["pipeline_groups"][0]["batch_count"] == 1
