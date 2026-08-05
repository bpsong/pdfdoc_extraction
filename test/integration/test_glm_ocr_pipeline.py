"""End-to-end versioned workflow coverage for mocked local GLM-OCR."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from modules.base_task import BaseTask
from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import (
    DocumentRepository,
    ExtractionRepository,
    ReviewRepository,
    TaskRunRepository,
)
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.ingress_binding_service import IngressBindingService
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.review_service import ReviewService
from modules.services.watch_folder_coordinator import WatchFolderCoordinator
from modules.workflow_manager import WorkflowManager
from standard_step.extraction.glm_ocr_adapter import GlmOcrAdapterResult
from test.helpers_sqlite import TempConfig
from test.workflow.test_workflow_task_run_tracking import _patch_prefect


GLM_FIELDS: dict[str, dict[str, Any]] = {
    "supplier": {"alias": "Supplier", "type": "str"},
    "invoice_number": {"alias": "Invoice number", "type": "str"},
    "invoice_total": {"alias": "Invoice total", "type": "float"},
    "line_items": {
        "alias": "Line items",
        "type": "List[Any]",
        "is_table": True,
        "item_fields": {
            "description": {"alias": "Description", "type": "str"},
            "quantity": {"alias": "Quantity", "type": "int"},
            "amount": {"alias": "Amount", "type": "float"},
        },
    },
}

REVIEW_SCHEMA = {
    "fields": {
        "supplier": {"type": "string", "required": True},
        "invoice_number": {"type": "string", "required": True},
        "invoice_total": {"type": "number", "required": True},
        "line_items": {
            "type": "array",
            "required": True,
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": "number"},
                    "amount": {"type": "number"},
                },
            },
        },
    }
}


class _NoopCleanupTask(BaseTask):
    """Keep synthetic inputs available for cross-run isolation assertions."""

    def on_start(self, context: dict[str, Any]) -> None:
        self.initialize_context(context)

    def validate_required_fields(self, context: dict[str, Any]) -> None:
        return None

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return context


class _WorkflowProcessor:
    def __init__(self, config: TempConfig) -> None:
        self.manager = WorkflowManager(config)

    def process_file(self, **kwargs: Any) -> bool:
        return bool(
            self.manager.trigger_workflow_for_file(
                kwargs["filepath"],
                kwargs["unique_id"],
                kwargs["original_filename"],
                kwargs["source"],
                batch_id=kwargs["batch_id"],
                document_id=kwargs["document_id"],
            )
        )


def _publish_pipeline(
    config: TempConfig,
    *,
    output_dir: Path,
    include_review: bool,
    key: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    with connect(config) as conn:
        schema_version = None
        if include_review:
            schemas = ReviewSchemaVersionService(conn)
            schema_template = schemas.create_template(
                schema_key=f"{key}-review",
                name=f"{key} review",
                initial_schema=REVIEW_SCHEMA,
                user="admin",
            )
            schema_version = schemas.publish(
                schema_template["template"]["id"],
                expected_revision=1,
                user="admin",
            )["version"]
            schemas.update_template(
                schema_template["template"]["id"],
                status="active",
                user="admin",
            )

        pipeline = ["glm_extract"]
        tasks: dict[str, Any] = {
            "glm_extract": {
                "module": "standard_step.extraction.glm_ocr_extract",
                "class": "GlmOcrExtractTask",
                "params": {
                    "ollama_host": "http://127.0.0.1:11434",
                    "model": "glm-ocr:latest",
                    "document_instructions": "Extract the SuperStore invoice.",
                    "dpi": 216,
                    "num_ctx": 8192,
                    "num_predict": 2048,
                    "timeout_seconds": 300,
                    "fields": GLM_FIELDS,
                },
                "on_error": "stop",
            }
        }
        if include_review and schema_version is not None:
            pipeline.append("review_gate")
            tasks["review_gate"] = {
                "module": "standard_step.review.review_gate",
                "class": "ReviewGateTask",
                "params": {
                    "schema_version_id": schema_version["id"],
                    "confidence_threshold": 0.8,
                    "require_review_when_missing_confidence": True,
                    "review_scope": "low_confidence_fields",
                    "queue_name": "glm_review",
                },
                "on_error": "stop",
            }
        pipeline.append("save_csv")
        tasks["save_csv"] = {
            "module": "standard_step.storage.store_metadata_as_csv",
            "class": "StoreMetadataAsCsv",
            "params": {
                "data_dir": str(output_dir),
                "filename": "{id}",
                "extraction": {"fields": GLM_FIELDS},
            },
            "on_error": "stop",
        }
        definition = {"schema_version": 1, "pipeline": pipeline, "tasks": tasks}
        service = PipelineTemplateService(conn)
        created = service.create_template(
            template_key=key,
            name=key.replace("-", " ").title(),
            initial_definition=definition,
            user="admin",
        )
        version = service.publish(
            created["template"]["id"], expected_revision=1, user="admin"
        )["version"]
        service.update_template(
            created["template"]["id"], status="active", user="admin"
        )
        return version, schema_version


@pytest.fixture
def glm_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    processing_dir = tmp_path / "processing"
    upload_dir = tmp_path / "upload"
    processing_dir.mkdir()
    upload_dir.mkdir()
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "web": {"upload_dir": str(upload_dir)},
            "watch_folder": {
                "processing_dir": str(processing_dir),
                "retry_attempts": 1,
                "retry_delay": 0,
            },
        },
    )
    initialize_database(config)
    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", _NoopCleanupTask)

    results = {
        b"upload": {
            "supplier": "SuperStore Upload",
            "invoice_number": "WEB-001",
            "invoice_total": 30.0,
            "line_items": [
                {"description": "Chair", "quantity": 1, "amount": 10.0},
                {"description": "Desk", "quantity": 2, "amount": 20.0},
            ],
        },
        b"watch": {
            "supplier": "SuperStore Watch",
            "invoice_number": "WATCH-002",
            "invoice_total": 42.0,
            "line_items": [
                {"description": "Binder", "quantity": 3, "amount": 42.0}
            ],
        },
        b"direct": {
            "supplier": "SuperStore Direct",
            "invoice_number": "DIRECT-003",
            "invoice_total": 12.0,
            "line_items": [
                {"description": "Paper", "quantity": 4, "amount": 12.0}
            ],
        },
    }

    class _MockAdapter:
        def extract(self, pdf_path: str, fields: dict[str, Any], **_: Any):
            content = Path(pdf_path).read_bytes()
            marker = next(marker for marker in results if marker in content)
            data = results[marker]
            return GlmOcrAdapterResult(
                data=data,
                page_count=1,
                field_pages={key: [1] for key in fields},
                calls=[],
            )

    monkeypatch.setattr(
        "standard_step.extraction.glm_ocr_extract.GlmOcrExtractTask._build_adapter",
        lambda self: _MockAdapter(),
    )
    return config


def _ingest_upload(
    config: TempConfig, version_id: str, pdf_path: Path
) -> dict[str, Any]:
    with connect(config) as conn:
        return IngestionAssignmentService(conn, config).create_batch(
            pipeline_version_id=version_id,
            role="operator",
            source="web",
            assignment_source="upload",
            files=[
                {
                    "file_path": str(pdf_path),
                    "original_filename": pdf_path.name,
                    "status": "processing",
                }
            ],
            user="operator",
            status="processing",
        )


def _complete_review(config: TempConfig, document_id: str, corrections: dict[str, Any]):
    with connect(config) as conn:
        review = ReviewRepository(conn).find_open_for_document(document_id)
        assert review is not None
        service = ReviewService(conn, config)
        service.claim(review["id"], "operator")
        completed = service.complete(review["id"], "operator", corrections)
        return review, completed


def _csv_rows(path: str) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_upload_and_watch_workflows_pause_review_resume_and_export_separately(
    tmp_path: Path, glm_runtime: TempConfig
) -> None:
    config = glm_runtime
    output_dir = tmp_path / "reviewed-csv"
    version, schema_version = _publish_pipeline(
        config,
        output_dir=output_dir,
        include_review=True,
        key="glm-reviewed",
    )
    assert schema_version is not None

    upload_pdf = tmp_path / "upload-superstore.pdf"
    upload_pdf.write_bytes(b"%PDF-1.4\n% upload")
    uploaded = _ingest_upload(config, version["id"], upload_pdf)
    upload_document = uploaded["documents"][0]
    assert WorkflowManager(config).trigger_workflow_for_file(
        str(upload_pdf),
        upload_document["id"],
        upload_pdf.name,
        "web",
        batch_id=uploaded["batch"]["id"],
        document_id=upload_document["id"],
    )

    with connect(config) as conn:
        upload_result = ExtractionRepository(conn).get_latest_result(
            upload_document["id"]
        )
        upload_fields = ExtractionRepository(conn).get_fields(upload_document["id"])
        upload_runs_before = TaskRunRepository(conn).list_by_document(
            upload_document["id"]
        )
        upload_review = ReviewRepository(conn).find_open_for_document(
            upload_document["id"]
        )
    assert upload_result is not None
    assert upload_review is not None
    assert upload_result["provider"] == "glm_ocr_ollama"
    assert json_loads(upload_result["metadata_json"])["provider"] == "glm_ocr_ollama"
    assert {item["confidence"] for item in upload_fields} == {None}
    assert all(item["requires_review"] == 1 for item in upload_fields)
    assert upload_review["review_schema_version_id"] == schema_version["id"]
    assert [(run["task_key"], run["status"]) for run in upload_runs_before] == [
        ("glm_extract", "completed"),
        ("review_gate", "paused"),
    ]
    task_run_payloads = "".join(
        str(run.get("input_json") or "") + str(run.get("output_json") or "")
        for run in upload_runs_before
    )
    for raw_runtime_value in (
        "SuperStore Upload",
        "WEB-001",
        "Extract the SuperStore invoice.",
        "http://127.0.0.1:11434",
    ):
        assert raw_runtime_value not in task_run_payloads

    _, upload_completed = _complete_review(
        config, upload_document["id"], {"supplier": "Corrected Upload Supplier"}
    )
    assert upload_completed["resume_triggered"] is True
    with connect(config) as conn:
        upload_files = DocumentRepository(conn).list_files(upload_document["id"])
        upload_runs = TaskRunRepository(conn).list_by_document(upload_document["id"])
    upload_csv = next(item for item in upload_files if item["file_type"] == "export_csv")
    upload_rows = _csv_rows(upload_csv["file_path"])
    assert len(upload_rows) == 2
    assert {row["Supplier"] for row in upload_rows} == {"Corrected Upload Supplier"}
    assert [run["task_key"] for run in upload_runs] == [
        "glm_extract",
        "review_gate",
        "save_csv",
        "cleanup_task",
    ]
    assert all(run["pipeline_version_id"] == version["id"] for run in upload_runs)

    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    with connect(config) as conn:
        binding = IngressBindingService(conn, config).create(
            folder_path=str(watch_dir),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
    watch_pdf = watch_dir / "watch-superstore.pdf"
    watch_pdf.write_bytes(b"%PDF-1.4\n% watch")
    coordinator = WatchFolderCoordinator(config, _WorkflowProcessor(config))
    assert coordinator.scan_once() == 1

    with connect(config) as conn:
        watched_documents = conn.execute(
            """
            SELECT d.*
            FROM documents d
            JOIN batches b ON b.id = d.batch_id
            WHERE b.ingress_binding_id = ?
            """,
            (binding["id"],),
        ).fetchall()
        assert len(watched_documents) == 1
        watch_document = dict(watched_documents[0])
        watch_review = ReviewRepository(conn).find_open_for_document(
            watch_document["id"]
        )
        watch_fields = ExtractionRepository(conn).get_fields(watch_document["id"])
    assert watch_review is not None
    assert watch_document["pipeline_version_id"] == version["id"]
    assert watch_review["review_schema_version_id"] == schema_version["id"]
    assert all(item["confidence"] is None and item["requires_review"] == 1 for item in watch_fields)

    _, watch_completed = _complete_review(
        config, watch_document["id"], {"invoice_total": 43.0}
    )
    assert watch_completed["resume_triggered"] is True
    with connect(config) as conn:
        watch_files = DocumentRepository(conn).list_files(watch_document["id"])
        watch_runs = TaskRunRepository(conn).list_by_document(watch_document["id"])
    watch_csv = next(item for item in watch_files if item["file_type"] == "export_csv")
    watch_rows = _csv_rows(watch_csv["file_path"])
    assert len(watch_rows) == 1
    assert watch_rows[0]["Invoice total"] == "43.0"
    assert all(run["pipeline_version_id"] == version["id"] for run in watch_runs)
    assert upload_document["id"] != watch_document["id"]
    assert upload_csv["file_path"] != watch_csv["file_path"]
    assert upload_pdf != Path(watch_document["file_path"])


def test_gate_free_glm_pipeline_exports_without_creating_review_state(
    tmp_path: Path, glm_runtime: TempConfig
) -> None:
    config = glm_runtime
    version, _ = _publish_pipeline(
        config,
        output_dir=tmp_path / "direct-csv",
        include_review=False,
        key="glm-direct",
    )
    direct_pdf = tmp_path / "direct-superstore.pdf"
    direct_pdf.write_bytes(b"%PDF-1.4\n% direct")
    created = _ingest_upload(config, version["id"], direct_pdf)
    document = created["documents"][0]

    assert WorkflowManager(config).trigger_workflow_for_file(
        str(direct_pdf),
        document["id"],
        direct_pdf.name,
        "web",
        batch_id=created["batch"]["id"],
        document_id=document["id"],
    )

    with connect(config) as conn:
        reviews = ReviewRepository(conn).list_queue()
        runs = TaskRunRepository(conn).list_by_document(document["id"])
        files = DocumentRepository(conn).list_files(document["id"])
    csv_file = next(item for item in files if item["file_type"] == "export_csv")
    rows = _csv_rows(csv_file["file_path"])
    assert reviews == []
    assert [run["task_key"] for run in runs] == [
        "glm_extract",
        "save_csv",
        "cleanup_task",
    ]
    assert all(run["status"] == "completed" for run in runs)
    assert len(rows) == 1
    assert rows[0]["Supplier"] == "SuperStore Direct"
    assert rows[0]["item_Description"] == "Paper"
