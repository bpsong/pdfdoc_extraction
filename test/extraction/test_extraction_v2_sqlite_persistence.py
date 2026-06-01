from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import ExtractionRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from standard_step.extraction.extract_pdf_v2 import ExtractPdfV2Task
from test.helpers_sqlite import TempConfig


def test_extract_pdf_v2_persists_result_and_fields_with_nullable_confidence(tmp_path, monkeypatch):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    params = {
        "api_key": "test-key",
        "fields": {
            "supplier": {"alias": "Supplier", "type": "str"},
            "invoice_total": {"alias": "Total", "type": "float"},
        },
    }
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"tasks": {"extract_document_data": {"params": params}}},
    )
    initialize_database(config)

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
        task_run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            task_key="extract_document_data",
            task_index=0,
            module_name="standard_step.extraction.extract_pdf_v2",
            class_name="ExtractPdfV2Task",
        )

    class Result:
        data = {"Supplier": "Acme", "Total": "12.50"}
        extraction_metadata = {
            "field_metadata": {
                "document_metadata": {
                    "Supplier": {"confidence_score": 0.96, "confidence_label": "high"},
                    "Total": {"confidence_score": 0.67, "confidence_label": "medium"},
                }
            }
        }
        job_id = "job-123"

    task = ExtractPdfV2Task(config_manager=config, **params)
    monkeypatch.setattr(task, "_extract_with_retry", lambda path: Result())
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "task_run_id": task_run["id"],
        "file_path": str(pdf_path),
    }

    task.on_start(context)
    result_context = task.run(context)

    with connect(config) as conn:
        repository = ExtractionRepository(conn)
        result = repository.get_latest_result(created["document"]["id"])
        fields = {field["field_key"]: field for field in repository.get_fields(created["document"]["id"])}

    assert result and result["provider_job_id"] == "job-123"
    assert result_context["extraction_result_id"] == result["id"]
    assert json_loads(fields["supplier"]["final_value_json"]) == "Acme"
    assert fields["supplier"]["confidence"] == 0.96
    assert fields["supplier"]["confidence_label"] == "high"
    assert fields["invoice_total"]["confidence"] == 0.67
    assert fields["invoice_total"]["confidence_label"] == "medium"
    assert json_loads(fields["invoice_total"]["final_value_json"]) == 12.5
