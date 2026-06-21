from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository, ExtractionRepository, ReviewRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from test.helpers_sqlite import TempConfig


class _FakeAuth:
    token_exp_minutes = 30


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, TempConfig, dict]:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "web": {"upload_dir": str(artifact_root / "web_upload")},
            "watch_folder": {
                "dir": str(artifact_root / "watch"),
                "processing_dir": str(artifact_root / "processing"),
            },
            "tasks": {
                "split_documents": {"params": {"split_dir": str(artifact_root / "split")}},
                "store_pdf": {"params": {"files_dir": str(artifact_root / "files")}},
            },
        },
    )
    initialize_database(config)
    pdf_path = artifact_root / "processing" / "invoice.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf")

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
        document_id = created["document"]["id"]
        DocumentRepository(conn).add_file(
            document_id=document_id,
            file_type="original_pdf",
            file_path=str(pdf_path),
        )
        task_run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=document_id,
            task_key="extract_document_data",
            task_index=0,
            module_name="standard_step.extraction.extract_pdf",
            class_name="ExtractPdfTask",
        )
        result = ExtractionRepository(conn).save_result(
            document_id=document_id,
            task_run_id=task_run["id"],
            provider="llamacloud_extract_v2",
            provider_job_id="job-123",
            data={"supplier": "Acme", "total": 12.5},
            metadata={"configuration_id": "cfg-1"},
        )
        ExtractionRepository(conn).save_fields(
            document_id=document_id,
            extraction_result_id=result["id"],
            fields=[
                {
                    "field_key": "supplier",
                    "field_alias": "Supplier",
                    "extracted_value": "Acme",
                    "final_value": "Acme",
                    "confidence": 0.95,
                    "review_status": "not_required",
                },
                {
                    "field_key": "total",
                    "field_alias": "Total",
                    "extracted_value": 12.5,
                    "final_value": 12.5,
                    "confidence": 0.62,
                    "requires_review": True,
                    "review_status": "required",
                    "source": {
                        "confidence_details": {
                            "aggregation": "minimum_nested_confidence",
                            "confidence": 0.62,
                            "nested_confidences": {
                                "value": {"confidence": 0.62, "confidence_band": "low"},
                            },
                        }
                    },
                },
            ],
        )
        review = ReviewRepository(conn).create_review_item(
            batch_id=created["batch"]["id"],
            document_id=document_id,
            queue_name="invoice_review",
            reason="low_confidence",
            scope="low_confidence_fields",
            created_by_task_run_id=task_run["id"],
        )

    def fake_get_dependencies():
        return config, _FakeAuth(), None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app = FastAPI()
    app.include_router(api_router.build_router())
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    return TestClient(app), config, {"created": created, "review": review, "pdf_path": pdf_path}


def test_document_extraction_api_returns_ui_ready_payload(tmp_path, monkeypatch) -> None:
    client, _, state = _client(tmp_path, monkeypatch)
    document_id = state["created"]["document"]["id"]

    response = client.get(f"/api/documents/{document_id}/extraction")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document"]["filename"] == "invoice.pdf"
    assert payload["document"]["preview_url"] == f"/api/documents/{document_id}/file/pdf"
    assert payload["latest_extraction"]["provider_job_id"] == "job-123"
    assert payload["review_item_id"] == state["review"]["id"]
    assert payload["fields"][0]["field_key"] == "supplier"
    assert payload["fields"][0]["confidence_band"] == "high"
    assert payload["fields"][1]["confidence_band"] == "low"
    assert payload["fields"][1]["confidence_details"]["nested_confidences"]["value"]["confidence"] == 0.62
    assert payload["fields"][1]["requires_review"] is True
    assert payload["files"][0]["filename"] == "invoice.pdf"


def test_document_extraction_api_404s_for_unknown_document(tmp_path, monkeypatch) -> None:
    client, _, _ = _client(tmp_path, monkeypatch)

    response = client.get("/api/documents/missing/extraction")

    assert response.status_code == 404


def test_document_pdf_preview_serves_registered_file(tmp_path, monkeypatch) -> None:
    client, _, state = _client(tmp_path, monkeypatch)
    document_id = state["created"]["document"]["id"]

    response = client.get(f"/api/documents/{document_id}/file/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.content.startswith(b"%PDF-1.4")


def test_document_pdf_preview_rejects_registered_file_outside_allowed_roots(tmp_path, monkeypatch) -> None:
    client, config, state = _client(tmp_path, monkeypatch)
    document_id = state["created"]["document"]["id"]
    outside_pdf = tmp_path / "outside.pdf"
    outside_pdf.write_bytes(b"%PDF-1.4\n% outside")

    with connect(config) as conn:
        conn.execute("UPDATE documents SET file_path = ? WHERE id = ?", (str(outside_pdf), document_id))
        conn.execute("UPDATE document_files SET file_path = ? WHERE document_id = ?", (str(outside_pdf), document_id))
        conn.commit()

    response = client.get(f"/api/documents/{document_id}/file/pdf")

    assert response.status_code == 404
    assert response.json()["detail"] == "PDF file not found"


def test_document_pdf_preview_returns_404_for_missing_allowed_file(tmp_path, monkeypatch) -> None:
    client, config, state = _client(tmp_path, monkeypatch)
    document_id = state["created"]["document"]["id"]
    missing_pdf = state["pdf_path"].parent / "missing.pdf"

    with connect(config) as conn:
        conn.execute("UPDATE documents SET file_path = ? WHERE id = ?", (str(missing_pdf), document_id))
        conn.execute("UPDATE document_files SET file_path = ? WHERE document_id = ?", (str(missing_pdf), document_id))
        conn.commit()

    response = client.get(f"/api/documents/{document_id}/file/pdf")

    assert response.status_code == 404
    assert response.json()["detail"] == "PDF file not found"
