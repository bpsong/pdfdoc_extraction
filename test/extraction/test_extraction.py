import os
from pathlib import Path
import pytest
from unittest.mock import MagicMock
from modules.config_manager import ConfigManager
from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import ExtractionRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from standard_step.extraction.extract_pdf import ExtractPdfTask
from test.helpers_sqlite import TempConfig
from typing import List, Optional

TEST_DIR = Path(__file__).parent
CONFIG_PATH = Path("test/data/extraction_config.yaml")
SAMPLE_PDF_SOURCE = Path("test/data/sample_invoice.pdf")

# Define MockStatusManager outside the test class to avoid scope issues
class MockStatusManager:
    _instance = None
    status_updates = []

    def __new__(cls, config_manager=None):
        if cls._instance is None:
            cls._instance = super(MockStatusManager, cls).__new__(cls)
            cls._instance._init(config_manager)
        return cls._instance

    def _init(self, config_manager):
        self.config_manager = config_manager

    def update_status(self, unique_id, status, step=None, error=None, details=None):
        MockStatusManager.status_updates.append((unique_id, status, step, error))

class TestExtractPdfTask:

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, monkeypatch):
        ConfigManager._instance = None
        self.config_manager = MagicMock()
        self.config_manager.get_all.return_value = {
            "tasks": {
                "extract_document_data": {
                    "params": {
                        "fields": {
                            "field1": {"type": "str", "alias": "field1"},
                            "serial_numbers": {"type": "List[str]", "alias": "serial_numbers"},
                        }
                    }
                }
            }
        }

        monkeypatch.setattr("modules.status_manager.StatusManager", MockStatusManager)
        monkeypatch.setattr("standard_step.extraction.extract_pdf.StatusManager", MockStatusManager)
        
        MockStatusManager.status_updates = []

        yield MockStatusManager

    def test_status_manager_updates(self, monkeypatch, setup_and_teardown):
        context = {"id": "test_id_status", "file_path": str(SAMPLE_PDF_SOURCE)}
        
        MockStatusManager = setup_and_teardown
        MockStatusManager.status_updates = []

        sample_response = MagicMock()
        sample_response.data = {
            "field1": "value1",
            "serial_numbers": ["123", None, "456"]
        }
        sample_response.extraction_metadata = {}
        monkeypatch.setattr(
            "standard_step.extraction.extract_pdf.run_extract_v2_job",
            MagicMock(return_value=sample_response),
        )

        task = ExtractPdfTask(
            config_manager=self.config_manager,
            api_key="dummy",
            fields={
                "field1": {"type": "str", "alias": "field1"},
                "serial_numbers": {"type": "List[str]", "alias": "serial_numbers"}
            }
        )
        
        task.on_start(context)
        task.run(context)

        # The implementation emits several intermediate status updates.
        # Assert the first and last updates match the expected start and completion events.
        expected_start = ("test_id_status", "Task Started: extract_document_data", "Task Started: extract_document_data", None)
        expected_end = ("test_id_status", "Task Completed: extract_document_data", "Task Completed: extract_document_data", None)

        assert MockStatusManager.status_updates[0] == expected_start
        assert MockStatusManager.status_updates[-1] == expected_end

    def test_extract_pdf(self, monkeypatch, setup_and_teardown):
        sample_response = MagicMock()
        sample_response.data = {
            "supplier_name": "Test Supplier",
            "client_name": "Test Client",
            "client_address": "123 Test St",
            "invoice_amount": 100.50,
            "insurance_start_date": "2023-01-01",
            "insurance_end_date": "2024-01-01",
            "policy_number": "POL123",
            "serial_numbers": ["SN123", None, "SN456"],
            "invoice_type": "Invoice",
        }
        sample_response.extraction_metadata = {}
        monkeypatch.setattr(
            "standard_step.extraction.extract_pdf.run_extract_v2_job",
            MagicMock(return_value=sample_response),
        )

        unique_id = "test_invoice_id"
        context = {
            "id": unique_id,
            "file_path": str(SAMPLE_PDF_SOURCE),
        }

        task = ExtractPdfTask(
            config_manager=self.config_manager,
            api_key="dummy_api_key",
            fields={
                "supplier_name": {"type": "str", "alias": "supplier_name"},
                "client_name": {"type": "str", "alias": "client_name"},
                "client_address": {"type": "str", "alias": "client_address"},
                "invoice_amount": {"type": "float", "alias": "invoice_amount"},
                "insurance_start_date": {"type": "str", "alias": "insurance_start_date"},
                "insurance_end_date": {"type": "str", "alias": "insurance_end_date"},
                "policy_number": {"type": "str", "alias": "policy_number"},
                "serial_numbers": {"type": "Optional[List[str]]", "alias": "serial_numbers"},
                "invoice_type": {"type": "str", "alias": "invoice_type"},
            }
        )
        
        task.on_start(context)
        try:
            result_context = task.run(context)
        except Exception as e:
            pytest.fail(f"ExtractPdfTask.run raised an exception: {e}")

        assert "data" in result_context, "'data' key missing in result context"

        data = result_context["data"]

        expected_fields = {
            "supplier_name": str,
            "client_name": str,
            "client_address": str,
            "invoice_amount": (float, int),
            "insurance_start_date": str,
            "insurance_end_date": str,
            "policy_number": str,
            "serial_numbers": list,
            "invoice_type": str,
        }

        for field, expected_type in expected_fields.items():
            assert field in data, f"Field '{field}' missing in extracted data"
            value = data[field]
            if field == "serial_numbers":
                assert isinstance(value, list) and all(isinstance(i, str) for i in value), \
                    f"Field '{field}' should be list of strings after filtering None"
                assert None not in value, "None values should be filtered from serial_numbers"
            else:
                assert isinstance(value, expected_type), \
                    f"Field '{field}' expected type {expected_type} but got {type(value)}"

        assert "metadata" in result_context
        assert result_context["metadata"]["extraction_configuration_id"] is None
        assert result_context["metadata"]["extraction_status"] == "success"

        # Align assertions with current implementation where status string equals descriptive step
        assert MockStatusManager.status_updates[-1][1] == "Task Completed: extract_document_data"
        assert MockStatusManager.status_updates[-1][2] == "Task Completed: extract_document_data"


def test_extract_pdf_persists_confidence_for_review_gate(tmp_path, monkeypatch):
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
            module_name="standard_step.extraction.extract_pdf",
            class_name="ExtractPdfTask",
        )

    class Result:
        data = {"Supplier": "Acme", "Total": "12.50"}
        extraction_metadata = {
            "field_metadata": {
                "document_metadata": {
                    "Supplier": {"confidence_score": 0.94, "confidence_label": "high"},
                    "Total": {"confidence_score": 0.61, "confidence_label": "low"},
                }
            }
        }
        job_id = "job-v1"

    runner = MagicMock(return_value=Result())
    monkeypatch.setattr("standard_step.extraction.extract_pdf.run_extract_v2_job", runner)
    monkeypatch.setattr("standard_step.extraction.extract_pdf.StatusManager", MockStatusManager)
    MockStatusManager.status_updates = []

    task = ExtractPdfTask(config_manager=config, **params)
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

    assert result and result["provider_job_id"] == "job-v1"
    assert result_context["extraction_result_id"] == result["id"]
    assert json_loads(fields["supplier"]["final_value_json"]) == "Acme"
    assert fields["supplier"]["confidence"] == 0.94
    assert fields["supplier"]["confidence_label"] == "high"
    assert fields["invoice_total"]["confidence"] == 0.61
    assert fields["invoice_total"]["confidence_label"] == "low"
    assert json_loads(fields["invoice_total"]["final_value_json"]) == 12.5
    assert runner.call_args.kwargs["confidence_scores"] is True
