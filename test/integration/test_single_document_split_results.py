"""Split results distinguish original continuation from child creation."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.repositories import DocumentRepository, ExtractionRepository
from modules.services.batch_service import BatchService
from modules.services.startup_migration_service import initialize_database
from standard_step.split.llamacloud_split import LlamaCloudSplitTask
from standard_step.split.llamacloud_split_adapter import SplitResult, SplitSegment
from test.helpers_sqlite import TempConfig
from test.services.test_ingestion_assignment_service import publish_pipeline
from test.standard_step.split.test_llamacloud_split_task import _write_pdf


def seed_single_document(config: TempConfig, directory: Path) -> dict[str, Any]:
    """Execute the real split task against a synthetic whole-document response."""
    source = directory / "synthetic-single-invoice.pdf"
    _write_pdf(source, 2)
    with connect(config) as conn:
        template, version = publish_pipeline(conn, key="single-results")
        created = BatchService(conn).create_ingestion_batch(
            source="web", file_path=str(source), original_filename=source.name,
            pipeline_template_id=template["id"], pipeline_version_id=version["id"],
            pipeline_assignment_source="upload",
        )

    class Adapter:
        def split_pdf(self, file_path: str, categories: list[dict[str, Any]]) -> SplitResult:
            return SplitResult("synthetic-job", "completed", [
                SplitSegment("invoice", "high", [1, 2], 1, 2, {})
            ], {})

    context = {"document_id": created["document"]["id"],
               "batch_id": created["batch"]["id"], "file_path": str(source),
               "original_filename": source.name, "current_task_key": "split"}
    task = LlamaCloudSplitTask(config, enabled=True, adapter=Adapter(),
                              categories=[{"name": "invoice"}], split_dir=str(directory / "split"))
    result = task.run(context)
    assert not result.get("error")
    with connect(config) as conn:
        ExtractionRepository(conn).save_result(
            document_id=created["document"]["id"], provider="synthetic",
            data={"invoice_number": "SYNTHETIC-001"},
        )
        DocumentRepository(conn).update_status(created["document"]["id"], "completed")
    return created


def test_single_document_split_results_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    created = seed_single_document(config, tmp_path)
    app = FastAPI()
    app.include_router(api_router.build_router())
    monkeypatch.setattr(api_router, "get_dependencies", lambda: (config, None, None, None, None))
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    client = TestClient(app)
    url = f"/api/batches/{created['batch']['id']}/split-results"
    response = client.get(url)
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["documents_created"] == 0
    assert payload["summary"]["documents_continuing"] == 1
    root = payload["sources"][0]
    assert root["split_outcome"] == "single_document"
    assert root["status"] == "completed"
    assert root["category"] == "invoice"
    assert root["pages"] == [1, 2]
    assert root["children"] == []
    assert root["extraction_document_id"] == created["document"]["id"]
    assert "source_sha256" not in response.text
    assert "raw_response" not in response.text
    for status in ("review_required", "failed"):
        with connect(config) as conn:
            DocumentRepository(conn).update_status(root["document_id"], status)
        updated = client.get(url).json()["sources"][0]
        assert updated["status"] == status
        assert updated["split_outcome"] == "single_document"
        assert updated["extraction_document_id"] == root["document_id"]
    with connect(config) as conn:
        docs = DocumentRepository(conn)
        docs.update_status(root["document_id"], "failed")
        docs.create_child(
            batch_id=created["batch"]["id"], parent_document_id=root["document_id"],
            file_path=str(tmp_path / "historical.pdf"), original_filename="historical.pdf",
            status="failed",
        )
    mixed = client.get(url).json()
    assert mixed["sources"][0]["split_outcome"] == "split_completed"
    assert mixed["sources"][0]["status"] == "failed"
    assert mixed["summary"]["documents_created"] == 1
    assert mixed["summary"]["documents_continuing"] == 0
    assert mixed["summary"]["failed"] == 1


def test_unsplit_root_is_not_inferred_to_be_single_document(tmp_path: Path) -> None:
    from modules.services.split_result_service import build_split_results

    result = build_split_results([{"id": "root", "status": "processing"}])
    assert result["sources"][0]["split_outcome"] is None
    assert result["sources"][0]["extraction_document_id"] is None
    assert result["summary"]["documents_continuing"] == 0


def test_single_document_decision_rolls_back_when_audit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.db.connection import json_loads
    from modules.db.repositories import AuditRepository
    from modules.services.split_result_service import save_single_document_decision

    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    created = seed_single_document(config, tmp_path)

    def reject_audit(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Synthetic audit write failure")

    monkeypatch.setattr(AuditRepository, "append", reject_audit)
    with connect(config) as conn:
        documents = DocumentRepository(conn)
        root = documents.get(created["document"]["id"])
        original_metadata = json_loads(root["metadata_json"], {})
        decision = {**original_metadata["split_result"], "category": "receipt"}
        with pytest.raises(RuntimeError, match="Synthetic audit"):
            save_single_document_decision(conn, root, decision)
        persisted = documents.get(root["id"])
        assert persisted["document_type"] == "invoice"
        assert json_loads(persisted["metadata_json"], {}) == original_metadata
