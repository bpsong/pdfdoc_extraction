from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import TaskRunRepository
from modules.services.batch_service import BatchService
from test.helpers_sqlite import TempConfig


def _config(tmp_path: Path) -> TempConfig:
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"auth": {"roles_enabled": True}, "authentication": {"username": "admin"}},
    )
    initialize_database(config)
    return config


def _client(monkeypatch, config: TempConfig) -> TestClient:
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies() -> tuple[Any, None, None, None, None]:
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    return TestClient(app)


def _seed_failed_document(config: TempConfig, tmp_path: Path, *, error: str = "bad llx-secret") -> dict[str, Any]:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% failure api test")
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
        run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            task_key="extract",
            task_index=1,
            module_name="standard_step.extraction.extract_pdf",
            class_name="ExtractPdfTask",
            input_data={"api_key": "llx-secret"},
        )
        TaskRunRepository(conn).mark_failed(
            run["id"],
            error,
            {
                "fatal_failure": {
                    "failure_type": "task_failed",
                    "message": error,
                    "provider": "llamacloud",
                    "provider_job_id": "job-123",
                    "configuration_id": "cfg-missing",
                    "api_key": "llx-secret",
                }
            },
        )
    return created


def test_failures_api_lists_details_and_clears_notifications(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    created = _seed_failed_document(config, tmp_path)
    document_id = created["document"]["id"]
    client = _client(monkeypatch, config)

    notifications = client.get("/api/failures/notifications")
    assert notifications.status_code == 200
    assert notifications.json()["count"] == 1

    failures = client.get("/api/failures")
    assert failures.status_code == 200
    failure_payload = failures.json()
    assert failure_payload["total"] == 1
    assert failure_payload["failures"][0]["document"]["id"] == document_id
    assert failure_payload["failures"][0]["preview_url"] == f"/api/documents/{document_id}/file/pdf"
    assert "llx-secret" not in failures.text
    assert "[REDACTED]" in failures.text

    detail = client.get(f"/api/failures/{document_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["failure"]["provider"] == "llamacloud"
    assert detail_payload["failure"]["provider_job_id"] == "job-123"
    assert detail_payload["latest_failed_task"]["output"]["fatal_failure"]["api_key"] == "[REDACTED]"
    assert detail_payload["preview_url"] == f"/api/documents/{document_id}/file/pdf"

    cleared = client.post("/api/failures/notifications/clear")
    assert cleared.status_code == 200
    assert cleared.json()["count"] == 0
    assert client.get("/api/failures/notifications").json()["count"] == 0

    with connect(config) as conn:
        run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=document_id,
            task_key="split",
            task_index=0,
            module_name="standard_step.split.llamacloud_split",
            class_name="LlamaCloudSplitTask",
        )
        TaskRunRepository(conn).mark_failed(run["id"], "new split failure", {"fatal_failure": {"message": "new split failure"}})

    assert client.get("/api/failures/notifications").json()["count"] == 1

