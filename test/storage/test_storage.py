import os
import pytest
import tempfile
from pathlib import Path
import shutil
from unittest.mock import MagicMock, patch
import csv # Added import
import json # Added import
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError
from modules.utils import sanitize_filename, generate_unique_filepath
from standard_step.storage.store_metadata_as_csv import StoreMetadataAsCsv
from standard_step.storage.store_metadata_as_json import StoreMetadataAsJson
from standard_step.storage.store_file_to_localdrive import StoreFileToLocaldrive

@pytest.fixture
def temp_dir():
    dirpath = tempfile.mkdtemp()
    yield Path(dirpath)
    shutil.rmtree(dirpath)

@pytest.fixture
def mock_config_manager():
    # Mock ConfigManager to provide pipeline configuration with extraction fields
    mock_config = {
        "tasks": {
            "extract_document_data": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask", # Added class
                "params": {
                    "fields": {
                        "invoice_amount": {"type": "float", "alias": "Invoice Total"},
                        "invoice_no": {"type": "str", "alias": "Invoice Number"},
                        "supplier": {"type": "str", "alias": "Supplier Name"},
                        "date": {"type": "str", "alias": "Invoice Date"}
                    }
                }
            },
            "store_csv": {
                "module": "standard_step.storage.store_metadata_as_csv",
                "class": "StoreMetadataAsCsv", # Added class
                "params": {
                    "data_dir": "data",
                    "filename": "{supplier}_{invoice_amount}_{invoice_no}"
                }
            },
            "store_json": {
                "module": "standard_step.storage.store_metadata_as_json",
                "class": "StoreMetadataAsJson", # Added class
                "params": {
                    "data_dir": "data",
                    "filename": "{supplier}_{invoice_amount}_{invoice_no}"
                }
            },
            "store_file": {
                "module": "standard_step.storage.store_file_to_localdrive",
                "class": "StoreFileToLocaldrive", # Added class
                "params": {
                    "files_dir": "files",
                    "filename": "{supplier}_{invoice_amount}_{invoice_no}_{date}"
                }
            }
        },
        "pipeline": [
            "extract_document_data",
            "store_csv",
            "store_json",
            "store_file"
        ]
    }
    mock_manager = MagicMock(spec=ConfigManager)
    mock_manager.get.side_effect = lambda key, default=None: mock_config.get(key, default)
    # Also mock get_all for the new ConfigManager.get_all() method
    mock_manager.get_all.return_value = mock_config
    return mock_manager

class TestStoreMetadataAsCsv:
    @pytest.fixture(autouse=True)
    def setup(self, mock_config_manager):
        ConfigManager._instance = None # Ensure singleton is reset
        self.config_manager = mock_config_manager
        
        # Retrieve task parameters from the mocked config
        tasks_config = self.config_manager.get_all().get("tasks", {})
        csv_task_params = tasks_config.get("store_csv", {}).get("params", {})

        self.task = StoreMetadataAsCsv(self.config_manager, **csv_task_params)
        self.task.on_start({}) # Call on_start to initialize internal attributes

    def test_csv_filename_generation_and_uniqueness(self, temp_dir):
        self.task.data_dir = temp_dir
        self.task.filename_template = "{supplier}_{invoice_no}.csv"

        extracted_data = {
            "supplier": "Acme Corp",
            "invoice_no": "INV/2023-001",
            "invoice_amount": 100.00
        }
        context = {"data": extracted_data, "id": "test_id_1"}

        # Expected sanitized base filename part
        sanitized_base_name_part = sanitize_filename("Acme Corp_INV/2023-001") # Corrected input to sanitize_filename
        expected_first_filename = f"{sanitized_base_name_part}.csv"
        expected_second_filename = f"{sanitized_base_name_part}_1.csv"
        expected_third_filename = f"{sanitized_base_name_part}_2.csv"

        # Test initial file creation
        self.task.run(context)
        assert (temp_dir / expected_first_filename).exists(), f"Expected {expected_first_filename} to be created. Actual files: {[f.name for f in temp_dir.iterdir()]}"

        # Test unique filename generation (e.g., _1)
        self.task.run(context) # Run again with same data to trigger uniqueness
        assert (temp_dir / expected_second_filename).exists(), f"Expected {expected_second_filename} to be created. Actual files: {[f.name for f in temp_dir.iterdir()]}"

        # Test unique filename generation (e.g., _2)
        self.task.run(context) # Run again to trigger _2
        assert (temp_dir / expected_third_filename).exists(), f"Expected {expected_third_filename} to be created. Actual files: {[f.name for f in temp_dir.iterdir()]}"

    def test_csv_data_transformation_and_headers(self, temp_dir):
        self.task.data_dir = temp_dir
        self.task.filename_template = "{supplier}_{invoice_no}.csv"

        extracted_data = {
            "supplier": "Beta Ltd",
            "invoice_no": "INV-002",
            "invoice_amount": 250.50,
            "items": ["item1", "item2"]
        }
        context = {"data": extracted_data, "id": "test_id_2"}
        self.task.run(context)

        output_path = temp_dir / sanitize_filename("Beta Ltd_INV-002.csv")
        with open(output_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            data_row = next(reader)
        
        # Check headers (aliases)
        assert "Supplier Name" in headers
        assert "Invoice Number" in headers
        assert "Invoice Total" in headers
        assert "items" in headers # 'items' has no alias in mock config, so original key is used

        # Check data transformation (newlines, lists)
        assert data_row[headers.index("Supplier Name")] == "Beta Ltd"
        assert data_row[headers.index("Invoice Number")] == "INV-002"
        assert data_row[headers.index("Invoice Total")] == "250.5"
        assert data_row[headers.index("items")] == "item1, item2"

    def test_csv_missing_extracted_data(self, temp_dir):
        self.task.data_dir = temp_dir
        self.task.filename_template = "{supplier}_{invoice_no}.csv"
        context = {"data": None, "id": "test_id_3"} # No extracted data

        result = self.task.run(context)
        assert result == context # Should return context unchanged
        assert not any(temp_dir.iterdir()) # No files should be created

    def test_csv_validation_failure(self, mock_config_manager):
        # Test missing data_dir
        # Test missing data_dir
        with pytest.raises(TaskError, match="Missing 'data_dir' parameter in configuration for StoreMetadataAsCsv task."):
            StoreMetadataAsCsv(mock_config_manager, data_dir=None, filename="test.csv")

        # Test missing filename_template
        with pytest.raises(TaskError, match="Missing 'filename' parameter in configuration for StoreMetadataAsCsv task."):
            StoreMetadataAsCsv(mock_config_manager, data_dir="dummy_dir", filename=None)

class TestStoreMetadataAsJson:
    @pytest.fixture(autouse=True)
    def setup(self, mock_config_manager):
        ConfigManager._instance = None # Ensure singleton is reset
        self.config_manager = mock_config_manager

        # Retrieve task parameters from the mocked config
        tasks_config = self.config_manager.get_all().get("tasks", {})
        json_task_params = tasks_config.get("store_json", {}).get("params", {})

        self.task = StoreMetadataAsJson(self.config_manager, **json_task_params)
        self.task.on_start({}) # Call on_start to initialize internal attributes

    def test_json_filename_generation_and_uniqueness(self, temp_dir):
        self.task.data_dir = temp_dir
        self.task.filename_template = "{supplier}_{invoice_no}.json"

        extracted_data = {
            "supplier": "Gamma Inc",
            "invoice_no": "JSON-001",
            "invoice_amount": 300.00
        }
        context = {"data": extracted_data, "id": "json_test_id_1"}

        # Test initial file creation
        self.task.run(context)
        expected_filename = sanitize_filename("Gamma Inc_JSON-001.json")
        assert (temp_dir / expected_filename).exists()

        # Test unique filename generation (e.g., _1)
        self.task.run(context) # Run again with same data to trigger uniqueness
        expected_filename_2 = sanitize_filename("Gamma Inc_JSON-001_1.json")
        assert (temp_dir / expected_filename_2).exists()

    def test_json_data_transformation_and_content(self, temp_dir):
        self.task.data_dir = temp_dir
        self.task.filename_template = "{supplier}_{invoice_no}.json"

        extracted_data = {
            "supplier": "Delta Co",
            "invoice_no": "JSON-002",
            "invoice_amount": 400.00
        }
        context = {"data": extracted_data, "id": "json_test_id_2"}
        self.task.run(context)

        output_path = temp_dir / sanitize_filename("Delta Co_JSON-002.json")
        with open(output_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        # Check if aliases are used
        assert content.get("Supplier Name") == "Delta Co"
        assert content.get("Invoice Number") == "JSON-002"
        assert content.get("Invoice Total") == 400.00
        assert "supplier" not in content # Original key should not be present if alias used

    def test_json_validation_failure(self, mock_config_manager):
        # Test missing data_dir
        with pytest.raises(TaskError, match="Missing 'data_dir' parameter in configuration for StoreMetadataAsJson task."):
            StoreMetadataAsJson(mock_config_manager, data_dir=None, filename="test.json")

        # Test missing filename_template
        with pytest.raises(TaskError, match="Missing 'filename' parameter in configuration for StoreMetadataAsJson task."):
            StoreMetadataAsJson(mock_config_manager, data_dir="dummy_dir", filename=None)

class TestStoreFileToLocaldrive:
    @pytest.fixture(autouse=True)
    def setup(self, mock_config_manager):
        ConfigManager._instance = None # Ensure singleton is reset
        self.config_manager = mock_config_manager

        # Retrieve task parameters from the mocked config
        tasks_config = self.config_manager.get_all().get("tasks", {})
        file_task_params = tasks_config.get("store_file", {}).get("params", {})

        self.task = StoreFileToLocaldrive(self.config_manager, **file_task_params)
        self.task.on_start({}) # Call on_start to initialize internal attributes

    @patch('shutil.copy') # Mock shutil.copy to prevent actual file operations
    def test_file_storage_filename_generation_and_uniqueness(self, mock_copy, temp_dir):
        self.task.files_dir = temp_dir
        self.task.filename = "{supplier}_{invoice_no}_{date}.pdf"

        extracted_data = {
            "supplier": "Epsilon Ltd",
            "invoice_no": "FILE-001",
            "date": "2024-07-21"
        }
        context = {
            "file_path": Path("dummy_source.pdf"),
            "id": "file_test_id_1",
            "original_filename": "original.pdf",
            "data": extracted_data
        }

        # Test initial file creation
        self.task.run(context)
        expected_base_filename = sanitize_filename("Epsilon Ltd_FILE-001_2024-07-21.pdf")
        mock_copy.assert_called_once_with(Path("dummy_source.pdf"), temp_dir / expected_base_filename)
        mock_copy.reset_mock()

        # Test unique filename generation (e.g., _1)
        # Simulate file existence for uniqueness check
        (temp_dir / expected_base_filename).touch() 
        self.task.run(context)
        expected_unique_filename = sanitize_filename("Epsilon Ltd_FILE-001_2024-07-21_1.pdf")
        mock_copy.assert_called_once_with(Path("dummy_source.pdf"), temp_dir / expected_unique_filename)
        mock_copy.reset_mock()

    @patch('shutil.copy')
    def test_file_storage_missing_context_data(self, mock_copy, temp_dir):
        self.task.files_dir = temp_dir
        self.task.filename = "{supplier}_{invoice_no}.pdf"
        context = {"file_path": None, "id": "file_test_id_2", "original_filename": None, "data": {}} # Missing data

        result = self.task.run(context)
        assert result == context # Should return context unchanged
        mock_copy.assert_not_called() # No file copy should happen

    def test_file_storage_validation_failure(self, mock_config_manager):
        # Test missing files_dir
        with pytest.raises(TaskError, match="Missing 'files_dir' parameter in configuration for StoreFileToLocaldrive task."):
            StoreFileToLocaldrive(mock_config_manager, files_dir=None, rename_pattern="test.pdf")

        # Test missing rename_pattern
        with pytest.raises(TaskError, match="Missing 'filename' parameter in configuration for StoreFileToLocaldrive task."):
            StoreFileToLocaldrive(mock_config_manager, files_dir="dummy_dir", rename_pattern=None)