from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import ExtractionRepository, ReviewRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from standard_step.review.review_gate import ReviewGateTask
from test.helpers_sqlite import TempConfig


def _create_document_with_field(tmp_path, confidence):
    pdf_path = tmp_path / f"invoice-{confidence}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir(exist_ok=True)
    (schema_dir / "invoice.yaml").write_text(
        "fields:\n  supplier:\n    type: string\n    required: true\n",
        encoding="utf-8",
    )
    config = TempConfig(tmp_path / "app.sqlite3", {"schema": {"directories": [str(schema_dir)]}})
    initialize_database(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename=pdf_path.name,
        )
        task_run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            task_key="review_gate",
            task_index=1,
            module_name="standard_step.review.review_gate",
            class_name="ReviewGateTask",
        )
        result = ExtractionRepository(conn).save_result(
            document_id=created["document"]["id"],
            provider="test",
            data={"supplier": "Acme"},
        )
        ExtractionRepository(conn).save_fields(
            document_id=created["document"]["id"],
            extraction_result_id=result["id"],
            fields=[{"field_key": "supplier", "extracted_value": "Acme", "confidence": confidence}],
        )
    return config, created, task_run


def test_review_gate_passes_when_all_rules_are_satisfied(tmp_path):
    config, created, task_run = _create_document_with_field(tmp_path, 0.95)
    task = ReviewGateTask(config, confidence_threshold=0.8, schema_file="invoice.yaml")
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "task_run_id": task_run["id"],
        "data": {"supplier": "Acme"},
    }

    result = task.run(context)

    assert result["review_required"] is False
    assert result["review_gate_status"] == "passed"


def test_review_gate_pauses_for_low_confidence_and_does_not_duplicate_open_item(tmp_path):
    config, created, task_run = _create_document_with_field(tmp_path, 0.2)
    task = ReviewGateTask(config, confidence_threshold=0.8, schema_file="invoice.yaml")
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "task_run_id": task_run["id"],
        "data": {"supplier": "Acme"},
    }

    first = task.run(dict(context))
    second = task.run(dict(context))

    with connect(config) as conn:
        reviews = ReviewRepository(conn).list_queue()
        metadata = json_loads(reviews[0]["metadata_json"])

    assert first["pipeline_state"] == "paused"
    assert second["review_item_id"] == first["review_item_id"]
    assert len(reviews) == 1
    assert metadata["highlight_fields"] == ["supplier"]
    assert metadata["schema_file"] == "invoice.yaml"
