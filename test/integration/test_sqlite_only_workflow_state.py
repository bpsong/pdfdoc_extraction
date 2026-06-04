from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.services.batch_service import BatchService
from modules.workflow_manager import WorkflowManager
from test.helpers_sqlite import TempConfig


@dataclass
class FakeExtractResult:
    """Small stand-in for the LlamaCloud Extract v2 result object."""

    data: dict[str, Any]
    extraction_metadata: dict[str, Any]
    job_id: str = "job-sqlite-only"


def _config(tmp_path: Path) -> TempConfig:
    processing_dir = tmp_path / "processing"
    exports_dir = tmp_path / "exports"
    files_dir = tmp_path / "files"
    archive_dir = tmp_path / "archive"
    watch_dir = tmp_path / "watch"
    reference_file = tmp_path / "reference.csv"
    for directory in (processing_dir, exports_dir, files_dir, archive_dir, watch_dir):
        directory.mkdir()
    reference_file.write_text("supplier,status\nACME,\n", encoding="utf-8")

    return TempConfig(
        tmp_path / "app.sqlite3",
        {
            "database": {"path": str(tmp_path / "app.sqlite3"), "run_migrations_on_startup": True},
            "web": {"upload_dir": str(tmp_path / "uploads")},
            "watch_folder": {
                "dir": str(watch_dir),
                "processing_dir": str(processing_dir),
                "validate_pdf_header": True,
            },
            "tasks": {
                "extract_document_data": {
                    "module": "standard_step.extraction.extract_pdf_v2",
                    "class": "ExtractPdfV2Task",
                    "params": {
                        "api_key": "test-api-key",
                        "fields": {
                            "supplier": {"alias": "Supplier", "type": "str"},
                            "amount": {"alias": "Amount", "type": "float"},
                        },
                    },
                },
                "review_gate": {
                    "module": "standard_step.review.review_gate",
                    "class": "ReviewGateTask",
                    "params": {
                        "confidence_threshold": 0.8,
                        "require_review_when_missing_confidence": False,
                        "require_review_for_missing_required_fields": False,
                    },
                },
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "class": "UpdateReferenceTask",
                    "params": {
                        "reference_file": str(reference_file),
                        "update_field": "status",
                        "write_value": "processed",
                        "backup": False,
                        "task_slug": "update_reference",
                        "csv_match": {
                            "type": "column_equals_all",
                            "clauses": [{"column": "supplier", "from_context": "supplier"}],
                        },
                    },
                },
                "store_json": {
                    "module": "standard_step.storage.store_metadata_as_json_v2",
                    "class": "StoreMetadataAsJsonV2",
                    "params": {"data_dir": str(exports_dir), "filename": "{supplier}"},
                },
                "store_csv": {
                    "module": "standard_step.storage.store_metadata_as_csv_v2",
                    "class": "StoreMetadataAsCsvV2",
                    "params": {"data_dir": str(exports_dir), "filename": "{supplier}"},
                },
                "store_file": {
                    "module": "standard_step.storage.store_file_to_localdrive",
                    "class": "StoreFileToLocaldrive",
                    "params": {"files_dir": str(files_dir), "filename": "{supplier}"},
                },
                "archive_pdf": {
                    "module": "standard_step.archiver.archive_pdf",
                    "class": "ArchivePdfTask",
                    "params": {"archive_dir": str(archive_dir)},
                },
            },
            "pipeline": [
                "extract_document_data",
                "review_gate",
                "update_reference",
                "store_json",
                "store_csv",
                "store_file",
                "archive_pdf",
            ],
        },
    )


def test_configured_workflow_uses_sqlite_state_without_status_text_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    initialize_database(config)
    source_pdf = tmp_path / "processing" / "doc-1.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\n% test")

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(source_pdf),
            original_filename="invoice.pdf",
            document_id="doc-1",
        )
    batch_id = created["batch"]["id"]
    document_id = created["document"]["id"]

    def fake_extract(**kwargs: Any) -> FakeExtractResult:
        return FakeExtractResult(
            data={"Supplier": "ACME", "Amount": 10.5},
            extraction_metadata={},
        )

    monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.run_extract_v2_job", fake_extract)

    assert WorkflowManager(config).trigger_workflow_for_file(
        file_path=str(source_pdf),
        unique_id=document_id,
        original_filename="invoice.pdf",
        source="web",
        batch_id=batch_id,
        document_id=document_id,
    )

    status_files = list((tmp_path / "processing").glob("*.txt"))
    assert status_files == []

    with connect(config) as conn:
        document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        task_runs = conn.execute("SELECT * FROM task_runs ORDER BY task_index").fetchall()
        files = conn.execute("SELECT * FROM document_files WHERE document_id = ?", (document_id,)).fetchall()
        extraction = conn.execute("SELECT * FROM extraction_results WHERE document_id = ?", (document_id,)).fetchone()

    assert document["status"] == "completed"
    assert [run["task_key"] for run in task_runs] == config.get("pipeline")
    assert {run["status"] for run in task_runs} == {"completed"}
    assert extraction is not None
    assert json_loads(task_runs[2]["output_json"])["data_keys"] == ["amount", "supplier", "update_reference"]

    file_types = {file_record["file_type"] for file_record in files}
    assert {"source_original", "export_json", "export_csv", "export_pdf", "source_archive"}.issubset(file_types)
    assert "processed" in (tmp_path / "reference.csv").read_text(encoding="utf-8")

    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies() -> tuple[TempConfig, None, None, None, None]:
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    client = TestClient(app)

    files_response = client.get("/api/files")
    assert files_response.status_code == 200
    assert files_response.json()[0]["file_id"] == document_id
    assert files_response.json()[0]["status"] == "completed"

    status_response = client.get(f"/api/status/{document_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["file_id"] == document_id
    assert status_payload["details"]["state_source"] == "sqlite"
    assert len(status_payload["details"]["task_runs"]) == len(config.get("pipeline"))
    assert {"export_json", "export_csv", "export_pdf"}.issubset(
        {record["file_type"] for record in status_payload["details"]["files"]}
    )
