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


def _create_document_with_fields(tmp_path, fields):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir(exist_ok=True)
    (schema_dir / "invoice.yaml").write_text(
        "\n".join(
            [
                "fields:",
                "  supplier:",
                "    type: string",
                "    required: true",
                "  serial_numbers:",
                "    type: array",
                "    required: false",
                "    items:",
                "      type: string",
            ]
        )
        + "\n",
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
            data={field["field_key"]: field.get("extracted_value") for field in fields},
        )
        ExtractionRepository(conn).save_fields(
            document_id=created["document"]["id"],
            extraction_result_id=result["id"],
            fields=fields,
        )
    return config, created, task_run


def _create_document_with_required_line_items(tmp_path, confidence, nested_confidences=None):
    pdf_path = tmp_path / "invoice-line-items.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir(exist_ok=True)
    (schema_dir / "invoice.yaml").write_text(
        "\n".join(
            [
                "fields:",
                "  line_items:",
                "    type: array",
                "    required: true",
                "    items:",
                "      type: object",
                "      properties:",
                "        sku:",
                "          type: string",
                "        quantity:",
                "          type: number",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = TempConfig(tmp_path / "app.sqlite3", {"schema": {"directories": [str(schema_dir)]}})
    initialize_database(config)
    source = {}
    if nested_confidences is not None:
        source = {
            "confidence_details": {
                "aggregation": "minimum_nested_confidence",
                "confidence": confidence,
                "nested_confidences": nested_confidences,
            }
        }
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
            data={"line_items": [{"sku": "ABC", "quantity": 2}]},
        )
        ExtractionRepository(conn).save_fields(
            document_id=created["document"]["id"],
            extraction_result_id=result["id"],
            fields=[
                {
                    "field_key": "line_items",
                    "extracted_value": [{"sku": "ABC", "quantity": 2}],
                    "confidence": confidence,
                    "source": source,
                }
            ],
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
    with connect(config) as conn:
        fields = ExtractionRepository(conn).get_fields(created["document"]["id"])
        reviews = ReviewRepository(conn).list_queue()
    assert fields[0]["requires_review"] == 0
    assert fields[0]["review_status"] == "not_required"
    assert reviews == []


def test_review_gate_uses_field_threshold_override(tmp_path):
    config, created, task_run = _create_document_with_field(tmp_path, 0.91)
    task = ReviewGateTask(
        config,
        confidence_threshold=0.8,
        field_threshold_overrides={"supplier": 0.95},
        schema_file="invoice.yaml",
    )
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "task_run_id": task_run["id"],
        "data": {"supplier": "Acme"},
    }

    result = task.run(context)

    assert result["pipeline_state"] == "paused"
    with connect(config) as conn:
        reviews = ReviewRepository(conn).list_queue()
        metadata = json_loads(reviews[0]["metadata_json"])
    assert metadata["field_threshold_overrides"] == {"supplier": 0.95}
    assert metadata["highlight_fields"] == ["supplier"]


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
        fields = ExtractionRepository(conn).get_fields(created["document"]["id"])

    assert first["pipeline_state"] == "paused"
    assert second["review_item_id"] == first["review_item_id"]
    assert len(reviews) == 1
    assert metadata["highlight_fields"] == ["supplier"]
    assert metadata["low_confidence_fields"] == ["supplier"]
    assert metadata["high_confidence_fields"] == []
    assert metadata["schema_file"] == "invoice.yaml"
    assert fields[0]["requires_review"] == 1
    assert fields[0]["review_status"] == "required"


def test_review_gate_ignores_optional_field_missing_confidence_when_schema_marks_optional(tmp_path):
    config, created, task_run = _create_document_with_fields(
        tmp_path,
        [
            {"field_key": "supplier", "extracted_value": "Acme", "confidence": 0.95},
            {"field_key": "serial_numbers", "extracted_value": None, "confidence": None},
        ],
    )
    task = ReviewGateTask(config, confidence_threshold=0.9, schema_file="invoice.yaml")
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "task_run_id": task_run["id"],
        "data": {"supplier": "Acme", "serial_numbers": None},
    }

    result = task.run(context)

    with connect(config) as conn:
        reviews = ReviewRepository(conn).list_queue()
        fields = {field["field_key"]: field for field in ExtractionRepository(conn).get_fields(created["document"]["id"])}

    assert result["review_required"] is False
    assert result["review_gate_status"] == "passed"
    assert reviews == []
    assert fields["serial_numbers"]["requires_review"] == 0


def test_review_gate_pauses_for_required_field_missing_confidence(tmp_path):
    config, created, task_run = _create_document_with_fields(
        tmp_path,
        [
            {"field_key": "supplier", "extracted_value": "Acme", "confidence": None},
            {"field_key": "serial_numbers", "extracted_value": None, "confidence": None},
        ],
    )
    task = ReviewGateTask(config, confidence_threshold=0.9, schema_file="invoice.yaml")
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "task_run_id": task_run["id"],
        "data": {"supplier": "Acme", "serial_numbers": None},
    }

    result = task.run(context)

    with connect(config) as conn:
        reviews = ReviewRepository(conn).list_queue()
        metadata = json_loads(reviews[0]["metadata_json"])

    assert result["review_required"] is True
    assert metadata["highlight_fields"] == ["supplier"]
    assert metadata["reasons"] == [{"reason": "missing_confidence", "field_key": "supplier"}]


def test_review_gate_passes_required_array_when_aggregate_confidence_is_high(tmp_path):
    config, created, task_run = _create_document_with_required_line_items(
        tmp_path,
        0.96,
        {
            "0.sku": {"confidence": 0.98},
            "0.quantity": {"confidence": 0.96},
        },
    )
    task = ReviewGateTask(config, confidence_threshold=0.95, schema_file="invoice.yaml")
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "task_run_id": task_run["id"],
        "data": {"line_items": [{"sku": "ABC", "quantity": 2}]},
    }

    result = task.run(context)

    with connect(config) as conn:
        reviews = ReviewRepository(conn).list_queue()

    assert result["review_required"] is False
    assert result["review_gate_status"] == "passed"
    assert reviews == []


def test_review_gate_records_nested_low_confidence_paths_for_required_array(tmp_path):
    config, created, task_run = _create_document_with_required_line_items(
        tmp_path,
        0.82,
        {
            "0.sku": {"confidence": 0.98},
            "0.quantity": {"confidence": 0.82},
        },
    )
    task = ReviewGateTask(config, confidence_threshold=0.95, schema_file="invoice.yaml")
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "task_run_id": task_run["id"],
        "data": {"line_items": [{"sku": "ABC", "quantity": 2}]},
    }

    result = task.run(context)

    with connect(config) as conn:
        reviews = ReviewRepository(conn).list_queue()
        metadata = json_loads(reviews[0]["metadata_json"])

    assert result["review_required"] is True
    assert metadata["highlight_fields"] == ["line_items"]
    assert metadata["low_confidence_fields"] == ["line_items"]
    assert metadata["low_confidence_paths"] == ["line_items.0.quantity"]
