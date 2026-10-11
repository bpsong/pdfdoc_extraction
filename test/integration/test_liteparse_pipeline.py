"""Versioned local extraction, review pause/resume and registered JSON output."""

from pathlib import Path
import json
from typing import Any

import pytest

from modules.db.connection import connect, json_loads
from modules.db.repositories import (
    DocumentRepository, ExtractionRepository, ReviewRepository, TaskRunRepository,
)
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.startup_migration_service import initialize_database
from modules.workflow_manager import WorkflowManager
from standard_step.extraction.liteparse_adapter import (
    LiteParseExtractionResult, LiteParseOllamaAdapter,
)
from test.helpers_sqlite import TempConfig
from test.integration.test_glm_ocr_pipeline import (
    _NoopCleanupTask, _complete_review, _ingest_upload,
)
from test.workflow.test_workflow_task_run_tracking import _patch_prefect


FIELDS = {
    "reference": {"alias": "Reference", "type": "str"},
    "entries": {"alias": "Entries", "type": "List[Any]", "is_table": True,
                "item_fields": {"quantity": {"alias": "Quantity", "type": "float"}}},
}
SCHEMA = {"fields": {
    "reference": {"type": "string", "required": True},
    "entries": {"type": "array", "required": True, "items": {
        "type": "object", "properties": {"quantity": {"type": "number"}},
    }},
}}


@pytest.mark.parametrize("review_required", [True, False])
def test_versioned_generic_task_persists_reviews_resumes_and_exports_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, review_required: bool,
) -> None:
    config = TempConfig(tmp_path / "test.sqlite3", {
        "watch_folder": {"processing_dir": str(tmp_path / "processing")},
    })
    initialize_database(config)
    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", _NoopCleanupTask)
    output = tmp_path / "json"
    with connect(config) as conn:
        forms = ReviewSchemaVersionService(conn)
        form = forms.create_template(schema_key="local-review", name="Local review",
                                     initial_schema=SCHEMA, user="admin")
        form_version = forms.publish(form["template"]["id"], expected_revision=1,
                                     user="admin")["version"]
        forms.update_template(form["template"]["id"], status="active", user="admin")
        tasks = {
            "local": {"module": "standard_step.extraction.liteparse_extract",
                      "class": "LiteParseExtractTask", "params": {"fields": FIELDS}},
            "review": {"module": "standard_step.review.review_gate",
                       "class": "ReviewGateTask", "params": {
                           "schema_version_id": form_version["id"],
                           "require_review_when_missing_confidence": True,
                           "review_scope": "document", "resume_policy": "next_task",
                       }},
            "json": {"module": "standard_step.storage.store_metadata_as_json",
                     "class": "StoreMetadataAsJson", "params": {
                         "data_dir": str(output), "filename": "{id}",
                         "extraction": {"fields": FIELDS},
                     }},
        }
        if not review_required:
            tasks.pop("review")
        pipelines = PipelineTemplateService(conn)
        template = pipelines.create_template(
            template_key="local-generic", name="Local generic",
            initial_definition={"schema_version": 1, "tasks": tasks,
                                "pipeline": list(tasks)}, user="admin",
        )
        version = pipelines.publish(template["template"]["id"],
                                    expected_revision=1, user="admin")["version"]
        pipelines.update_template(template["template"]["id"], status="active", user="admin")

    calls = []

    def extract(adapter: Any, pdf: Path, fields: dict, instructions: str) -> LiteParseExtractionResult:
        calls.append(fields)
        return LiteParseExtractionResult(
            {"reference": "0007", "entries": [{"quantity": 2.5}]},
            {"reference": {"pages": [1], "box_usage": "diagnostic_only"},
             "entries": {"pages": [1], "box_usage": "diagnostic_only"}},
            {"provider": "liteparse_ollama", "confidence_available": False},
        )

    monkeypatch.setattr(LiteParseOllamaAdapter, "extract", extract)
    pdf = tmp_path / "manifest.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% synthetic")
    batch = _ingest_upload(config, version["id"], pdf)
    document = batch["documents"][0]
    assert WorkflowManager(config).trigger_workflow_for_file(
        str(pdf), document["id"], pdf.name, "web",
        batch_id=batch["batch"]["id"], document_id=document["id"],
    )
    with connect(config) as conn:
        result = ExtractionRepository(conn).get_latest_result(document["id"])
        fields = ExtractionRepository(conn).get_fields(document["id"])
        review = ReviewRepository(conn).find_open_for_document(document["id"])
        files = DocumentRepository(conn).list_files(document["id"])
    assert result is not None
    assert result["provider"] == "liteparse_ollama"
    assert all(field["confidence"] is None for field in fields)
    assert json_loads(result["data_json"], {})["entries"] == [{"quantity": 2.5}]
    if review_required:
        assert review is not None
        assert all(field["requires_review"] for field in fields)
        assert not any(file["file_type"] == "export_json" for file in files)
        _, completed = _complete_review(config, document["id"], {"reference": "REVIEWED"})
        assert completed["resume_triggered"] is True
    else:
        assert review is None
    with connect(config) as conn:
        files = DocumentRepository(conn).list_files(document["id"])
        runs = TaskRunRepository(conn).list_by_document(document["id"])
        final = DocumentRepository(conn).get(document["id"])
    artifact = next(file for file in files if file["file_type"] == "export_json")
    exported = json.loads(Path(artifact["file_path"]).read_text(encoding="utf-8"))
    assert exported == {"Reference": "REVIEWED" if review_required else "0007",
                        "Entries": [{"quantity": 2.5}]}
    assert len(calls) == 1
    assert final is not None
    assert final["status"] == "completed"
    assert all(run["pipeline_version_id"] == version["id"] for run in runs)
