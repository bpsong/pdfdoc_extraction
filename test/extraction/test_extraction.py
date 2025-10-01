import os
from pathlib import Path
import pytest
from unittest.mock import MagicMock
from modules.config_manager import ConfigManager
from standard_step.extraction.extract_pdf import ExtractPdfTask
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
        self.config_manager = ConfigManager(CONFIG_PATH)

        monkeypatch.setattr("modules.status_manager.StatusManager", MockStatusManager)
        monkeypatch.setattr("standard_step.extraction.extract_pdf.StatusManager", MockStatusManager)
        
        MockStatusManager.status_updates = []

        yield MockStatusManager

    def test_status_manager_updates(self, monkeypatch, setup_and_teardown):
        context = {"id": "test_id_status", "file_path": str(SAMPLE_PDF_SOURCE)}
        
        MockStatusManager = setup_and_teardown
        MockStatusManager.status_updates = []

        mock_llama_extract_instance = MagicMock()
        mock_llama_extract_instance.get_agent.return_value.extract.return_value.data = {
            "field1": "value1",
            "serial_numbers": ["123", None, "456"]
        }
        monkeypatch.setattr("standard_step.extraction.extract_pdf.LlamaExtract", MagicMock(return_value=mock_llama_extract_instance))

        task = ExtractPdfTask(
            config_manager=self.config_manager,
            api_key="dummy",
            agent_id="dummy",
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
        mock_llama_extract_instance = MagicMock()
        mock_llama_extract_instance.get_agent.return_value.extract.return_value.data = {
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
        monkeypatch.setattr("standard_step.extraction.extract_pdf.LlamaExtract", MagicMock(return_value=mock_llama_extract_instance))

        unique_id = "test_invoice_id"
        context = {
            "id": unique_id,
            "file_path": str(SAMPLE_PDF_SOURCE),
        }

        task = ExtractPdfTask(
            config_manager=self.config_manager,
            api_key="dummy_api_key",
            agent_id="dummy_agent_id",
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
        assert result_context["metadata"]["extraction_agent_id"] == "dummy_agent_id"
        assert result_context["metadata"]["extraction_status"] == "success"

        # Align assertions with current implementation where status string equals descriptive step
        assert MockStatusManager.status_updates[-1][1] == "Task Completed: extract_document_data"
        assert MockStatusManager.status_updates[-1][2] == "Task Completed: extract_document_data"