"""Synthetic versioned invoice form shared by R4 configuration tests."""

from pathlib import Path
from typing import Any


def invoice_review_schema() -> dict[str, Any]:
    """Return independent row and subtotal rules with compatible form fields."""
    return {
        "title": "Synthetic invoice review",
        "fields": {
            "items": {"type": "array", "label": "Invoice items", "items": {
                "type": "object", "properties": {
                    "quantity": {"type": "number", "label": "Quantity"},
                    "unit_price": {"type": "number", "label": "Unit price"},
                    "line_total": {"type": "number", "label": "Line total"},
                    "description": {"type": "string"},
                },
            }},
            "subtotal": {"type": "number", "label": "Subtotal before discount"},
        },
        "business_validation": {"format_version": 1, "rules": [
            {"id": "item_amount", "validator": "line_amount:v1", "collection": "/items",
             "quantity": "/quantity", "unit_price": "/unit_price", "line_total": "/line_total"},
            {"id": "subtotal", "validator": "sum_equals:v1", "collection": "/items",
             "item_value": "/line_total", "target": "/subtotal", "severity": "blocking"},
        ]},
    }


def seed_business_review(config: Any, directory: Path, *, schema: dict[str, Any] | None = None,
                         values: dict[str, Any] | None = None) -> dict[str, Any]:
    """Seed synthetic persisted extraction and an exactly pinned review task."""
    from modules.db.connection import managed_connect
    from modules.db.repositories import DocumentRepository, ExtractionRepository, TaskRunRepository
    from modules.services.batch_service import BatchService
    from modules.services.review_schema_version_service import ReviewSchemaVersionService
    from standard_step.review.review_gate import ReviewGateTask
    from test.helpers_sqlite import assign_pipeline, seed_pipeline
    from pypdf import PdfWriter

    schema = schema if schema is not None else invoice_review_schema()
    values = values if values is not None else {
        "items": [{"quantity": 3, "unit_price": 10, "line_total": 300}], "subtotal": 30,
    }
    path = directory / "synthetic-invoice.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.write(path)
    with managed_connect(config) as conn:
        forms = ReviewSchemaVersionService(conn)
        template = forms.create_template(schema_key="invoice-rules", name="Invoice rules",
                                         initial_schema=schema, user="admin")["template"]
        version = forms.publish(template["id"], expected_revision=1, user="admin")["version"]
        created = BatchService(conn).create_ingestion_batch(
            source="web", file_path=str(path), original_filename=path.name,
        )
    definition = {"schema_version": 1, "pipeline": ["review"], "tasks": {
        "review": {"module": "standard_step.review.review_gate", "class": "ReviewGateTask",
                   "params": {"schema_version_id": version["id"]}},
    }}
    pipeline = seed_pipeline(config, definition)
    document_id = created["document"]["id"]
    assign_pipeline(config, document_id, pipeline)
    with managed_connect(config) as conn:
        source = DocumentRepository(conn).add_file(
            document_id=document_id, file_type="original_pdf", file_path=str(path),
        )
        extraction = ExtractionRepository(conn).save_result(
            document_id=document_id, provider="synthetic", data=values,
        )
        ExtractionRepository(conn).save_fields(
            document_id=document_id, extraction_result_id=extraction["id"], fields=[
                {"field_key": key, "extracted_value": value, "confidence": .99}
                for key, value in values.items()
            ],
        )
        run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"], document_id=document_id, task_key="review", task_index=0,
            module_name="standard_step.review.review_gate", class_name="ReviewGateTask",
            pipeline_version_id=pipeline["id"],
        )
    task = ReviewGateTask(config, schema_version_id=version["id"], _review_schema=schema,
                          _review_schema_hash=version["content_hash"])
    context = {"document_id": document_id, "batch_id": created["batch"]["id"],
               "task_run_id": run["id"], "pipeline_version_id": pipeline["id"], "data": values}
    return {"task": task, "context": context, "version": version, "source": source,
            "extraction": extraction, "created": created, "run": run, "values": values}
