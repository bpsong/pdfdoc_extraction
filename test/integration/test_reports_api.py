from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import BatchRepository, DocumentRepository, ReviewRepository
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

    def fake_get_dependencies():
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    return TestClient(app)


def _seed_report_data(config: TempConfig, tmp_path: Path) -> None:
    for filename in ("invoice-a.pdf", "invoice-b.pdf"):
        (tmp_path / filename).write_bytes(b"%PDF-1.4")

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch_with_documents(
            source="web",
            files=[
                {
                    "file_path": str(tmp_path / "invoice-a.pdf"),
                    "original_filename": "invoice-a.pdf",
                    "status": "processing",
                },
                {
                    "file_path": str(tmp_path / "invoice-b.pdf"),
                    "original_filename": "invoice-b.pdf",
                    "status": "processing",
                },
            ],
        )
        documents = created["documents"]
        docs = DocumentRepository(conn)
        docs.update_status(documents[0]["id"], "completed")
        docs.update_status(documents[1]["id"], "failed")
        BatchRepository(conn).recompute_counts(created["batch"]["id"])

        review = ReviewRepository(conn).create_review_item(
            batch_id=created["batch"]["id"],
            document_id=documents[0]["id"],
            queue_name="default",
            reason="low_confidence",
            scope="low_confidence_fields",
        )
        ReviewRepository(conn).complete(review["id"], assigned_to="operator")

        conn.execute(
            """
            INSERT INTO task_runs(
                id, batch_id, document_id, task_key, task_index, module_name, class_name,
                status, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "task-run-1",
                created["batch"]["id"],
                documents[0]["id"],
                "extract",
                0,
                "standard_step.extraction.extract_pdf_v2",
                "ExtractPdfV2Task",
                "completed",
                "2026-06-03T00:00:00+00:00",
                "2026-06-03T00:02:00+00:00",
            ),
        )
        conn.commit()


def test_reports_summary_uses_sqlite_state(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_report_data(config, tmp_path)
    client = _client(monkeypatch, config)

    response = client.get("/api/reports/summary")

    assert response.status_code == 200
    payload: dict[str, Any] = response.json()
    assert payload["summary"]["total_batches"] == 1
    assert payload["summary"]["total_documents"] == 2
    assert payload["summary"]["documents_completed"] == 1
    assert payload["summary"]["documents_failed"] == 1
    assert payload["summary"]["documents_reviewed"] == 1
    assert payload["summary"]["average_processing_seconds"] == 120
    assert payload["summary"]["average_processing_display"] == "2.0m"
    assert payload["batch_sources"] == [{"source": "web", "count": 1}]
    assert {row["status"]: row["count"] for row in payload["document_statuses"]} == {
        "completed": 1,
        "failed": 1,
    }
    assert payload["review"]["total"] == 1
    assert payload["recent_batches"][0]["total_documents"] == 2
