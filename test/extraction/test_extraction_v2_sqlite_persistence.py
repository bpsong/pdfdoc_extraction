from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import ExtractionRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from standard_step.extraction.llama_cloud_v2 import extract_confidence_details, extract_numeric_confidence, _to_plain_dict
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


def test_extract_pdf_v2_persists_table_confidence_details(tmp_path, monkeypatch):
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    params = {
        "api_key": "test-key",
        "fields": {
            "items": {
                "alias": "Items",
                "type": "List[Any]",
                "is_table": True,
                "item_fields": {
                    "itemName": {"alias": "Item name", "type": "str"},
                    "quantity": {"alias": "Quantity", "type": "float"},
                },
            },
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
        data = {"Items": [{"Item name": "Paper", "Quantity": "2"}]}
        extraction_metadata = {
            "field_metadata": {
                "document_metadata": {
                    "Items": [
                        {
                            "itemName": {"confidence": 0.96, "citation": [{"page": 1}]},
                            "quantity": {"confidence": 0.91},
                        }
                    ]
                }
            }
        }
        job_id = "job-table"

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
    task.run(context)

    with connect(config) as conn:
        fields = {field["field_key"]: field for field in ExtractionRepository(conn).get_fields(created["document"]["id"])}

    items = fields["items"]
    source = json_loads(items["source_json"], {})
    nested = source["confidence_details"]["nested_confidences"]
    assert items["confidence"] == 0.91
    assert json_loads(items["final_value_json"]) == [{"itemName": "Paper", "quantity": 2.0}]
    assert nested["0.itemName"]["confidence"] == 0.96
    assert nested["0.itemName"]["source"] == {"provider_source": [{"page": 1}]}
    assert nested["0.quantity"]["confidence"] == 0.91


def test_llamacloud_metadata_model_is_normalized_to_plain_dict() -> None:
    class MetadataModel:
        def model_dump(self, *, mode: str, exclude_none: bool) -> dict:
            return {
                "field_metadata": {
                    "document_metadata": {
                        "Supplier": {"confidence": 0.91},
                    },
                    "page_metadata": None,
                }
            }

    metadata = _to_plain_dict(MetadataModel())

    assert metadata == {
        "field_metadata": {
            "document_metadata": {
                "Supplier": {"confidence": 0.91},
            },
            "page_metadata": None,
        }
    }
    assert extract_numeric_confidence(metadata, "supplier", "Supplier") == 0.91


def test_confidence_parser_accepts_direct_field_metadata_shape() -> None:
    metadata = {
        "field_metadata": {
            "supplier": {
                "parsing_confidence": 0.88,
                "extraction_confidence": 0.83,
                "confidence": 0.85,
            }
        }
    }

    assert extract_numeric_confidence(metadata, "supplier", "Supplier") == 0.85


def test_confidence_parser_aggregates_object_array_metadata() -> None:
    metadata = {
        "field_metadata": {
            "document_metadata": {
                "items": [
                    {
                        "itemName": {"confidence": 0.994, "citation": [{"page": 1}]},
                        "quantity": {"confidence": 1.0},
                        "unitPrice": {"confidence": 0.97},
                    },
                    {
                        "itemName": {"confidence": 0.88},
                        "quantity": {"confidence": "not-a-number"},
                    },
                ]
            }
        }
    }

    details = extract_confidence_details(metadata, "items", "items")

    assert extract_numeric_confidence(metadata, "items", "items") == 0.88
    assert details["aggregation"] == "minimum_nested_confidence"
    assert details["confidence"] == 0.88
    assert details["nested_confidences"]["0.itemName"]["confidence"] == 0.994
    assert details["nested_confidences"]["0.itemName"]["source"] == {"provider_source": [{"page": 1}]}
    assert details["nested_confidences"]["1.itemName"]["confidence_band"] == "medium"


def test_confidence_parser_aggregates_object_and_scalar_array_metadata() -> None:
    object_metadata = {
        "field_metadata": {
            "document_metadata": {
                "address": {
                    "city": {"confidence": 0.93},
                    "postalCode": {"confidence_score": 0.79},
                }
            }
        }
    }
    array_metadata = {
        "field_metadata": {
            "document_metadata": {
                "serial_numbers": [
                    {"confidence": 0.98},
                    {"confidence": 0.76},
                ]
            }
        }
    }

    assert extract_numeric_confidence(object_metadata, "address", "Address") == 0.79
    assert extract_numeric_confidence(array_metadata, "serial_numbers", "Serial numbers") == 0.76


def test_confidence_parser_returns_none_when_no_numeric_confidence_exists() -> None:
    metadata = {
        "field_metadata": {
            "document_metadata": {
                "items": [{"itemName": {"confidence": "unknown"}}]
            }
        }
    }

    assert extract_numeric_confidence(metadata, "items", "items") is None
