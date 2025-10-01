
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from modules.config_manager import ConfigManager
from modules.status_manager import StatusManager
from modules.exceptions import TaskError
from standard_step.extraction.extract_pdf_v2 import ExtractPdfV2Task
from typing import Dict, Any, List

# Test configuration
TEST_DIR = Path(__file__).parent
SAMPLE_PDF_SOURCE = TEST_DIR / "test_extraction.py"  # Use existing test file as mock PDF

# Mock StatusManager for testing
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
        MockStatusManager.status_updates.append((unique_id, status, step, error, details))


class TestExtractPdfV2Task:
    """Comprehensive test suite for ExtractPdfV2Task."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, monkeypatch):
        """Set up test fixtures and clean up after each test."""
        # Reset ConfigManager singleton
        ConfigManager._instance = None

        # Create sample config dict matching the expected structure in config.yaml
        sample_config = {
            'tasks': {
                'extract_document_data': {
                    'params': {
                        'api_key': 'test_api_key',
                        'agent_id': 'test_agent_id',
                        'fields': {
                            'supplier_name': {'alias': 'Supplier name', 'type': 'str'},
                            'purchase_order_number': {'alias': 'Purchase Order number', 'type': 'str'},
                            'invoice_amount': {'alias': 'Invoice Amount', 'type': 'float'},
                            'project_number': {'alias': 'Project number', 'type': 'str'},
                            'items': {
                                'alias': 'Items',
                                'type': 'List[Any]',
                                'is_table': True,
                                'item_fields': {
                                    'description': {'alias': 'Description', 'type': 'str'},
                                    'quantity': {'alias': 'Quantity', 'type': 'str'}
                                }
                            }
                        }
                    }
                }
            }
        }

        # Mock ConfigManager to return our sample config
        def mock_get(key, default=None):
            keys = key.split('.') if '.' in key else [key]
            result = sample_config
            for k in keys:
                if isinstance(result, dict) and k in result:
                    result = result[k]
                else:
                    return default
            return result

        self.config_manager = MagicMock()
        self.config_manager.get.side_effect = mock_get

        # Patch StatusManager
        monkeypatch.setattr("modules.status_manager.StatusManager", MockStatusManager)
        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.StatusManager", MockStatusManager)

        # Clear status updates
        MockStatusManager.status_updates = []

        yield

    def test_successful_extraction_with_table(self, monkeypatch):
        """Test successful extraction with both scalar fields and table data."""
        # Sample LlamaCloud response as specified in requirements
        sample_response = MagicMock()
        sample_response.data = {
            "Supplier name": "ALLIGATOR SINGAPORE PTE LTD",
            "Purchase Order number": "1781054",
            "Invoice Amount": 44.62,
            "Project number": "S268588",
            "Items": [
                {"Description": "ELECTRODE G-300 3.2MM 5KG FOR MILD STEEL TYPE #6013, 3.2MM X 350MM (5KGS./PKT)", "Quantity": "4.0 PKT"},
                {"Description": "QUICK COUPLER SOCKET F/FUELGAS 5/16 AUTO REV. FLOW COUPLING AS-2 & AP-2 STEEL 3/8\"", "Quantity": "2.0 PCS"},
                {"Description": "3% DISCOUNT", "Quantity": "1.0 TIM"}
            ]
        }
        sample_response.extraction_metadata = {
            "run_id": "3c13c955-34e8-4c36-b498-42a55bbc1db3",
            "extraction_agent_id": "f311fd08-282f-4fef-8a41-f728242159e9",
            "usage": {"total_tokens": 150, "input_tokens": 100, "output_tokens": 50}
        }

        # Mock LlamaExtract
        mock_agent = MagicMock()
        mock_agent.extract.return_value = sample_response

        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        # Test context
        context = {
            "id": "test-uuid",
            "file_path": str(SAMPLE_PDF_SOURCE),
            "original_filename": "test.pdf",
            "source": "test_source"
        }

        # Create and run task
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)  # Call on_start first like in V1 tests
        result_context = task.run(context)

        # Assertions
        assert "data" in result_context
        data = result_context["data"]

        # Test scalar fields normalization
        assert data["supplier_name"] == "ALLIGATOR SINGAPORE PTE LTD"
        assert data["purchase_order_number"] == "1781054"
        assert data["invoice_amount"] == 44.62  # float conversion
        assert isinstance(data["invoice_amount"], float)
        assert data["project_number"] == "S268588"

        # Test table field processing
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 3

        # Test first item
        first_item = data["items"][0]
        assert first_item["description"] == "ELECTRODE G-300 3.2MM 5KG FOR MILD STEEL TYPE #6013, 3.2MM X 350MM (5KGS./PKT)"
        assert first_item["quantity"] == "4.0 PKT"

        # Test second item
        second_item = data["items"][1]
        assert 'QUICK COUPLER' in second_item["description"]
        assert second_item["quantity"] == "2.0 PCS"

        # Test metadata preservation
        assert "metadata" in result_context
        assert result_context["metadata"]["extraction_agent_id"] == "test_agent_id"
        assert result_context["metadata"]["extraction_metadata"] == sample_response.extraction_metadata

        # Test status updates
        status_updates = MockStatusManager.status_updates
        assert any("Task Started: extract_document_data" in update[1] for update in status_updates)
        assert any("Task Completed: extract_document_data" in update[1] for update in status_updates)

        # Test no error in context
        assert result_context.get("error") is None

    def test_scalar_fields_only(self, monkeypatch):
        """Test extraction with only scalar fields, no table fields."""
        # Config without table field
        sample_config = {
            'tasks': {
                'extract_document_data': {
                    'params': {
                        'api_key': 'test_api_key',
                        'agent_id': 'test_agent_id',
                        'fields': {
                            'supplier_name': {'alias': 'Supplier name', 'type': 'str'},
                            'invoice_amount': {'alias': 'Invoice Amount', 'type': 'float'},
                            'project_number': {'alias': 'Project number', 'type': 'str'}
                        }
                    }
                }
            }
        }

        def mock_get(key, default=None):
            keys = key.split('.') if '.' in key else [key]
            result = sample_config
            for k in keys:
                if isinstance(result, dict) and k in result:
                    result = result[k]
                else:
                    return default
            return result

        self.config_manager.get.side_effect = mock_get

        # Mock response with only scalars
        sample_response = MagicMock()
        sample_response.data = {
            "Supplier name": "Test Supplier",
            "Invoice Amount": 100.50,
            "Project number": "TEST123"
        }
        sample_response.extraction_metadata = {"test": "metadata"}

        mock_agent = MagicMock()
        mock_agent.extract.return_value = sample_response
        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)
        result_context = task.run(context)

        # Assertions
        data = result_context["data"]
        assert "supplier_name" in data
        assert "invoice_amount" in data
        assert "project_number" in data
        assert "items" not in data  # No table field

        assert data["supplier_name"] == "Test Supplier"
        assert data["invoice_amount"] == 100.50
        assert isinstance(data["invoice_amount"], float)

        # Metadata preserved
        assert "metadata" in result_context
        assert result_context["metadata"]["extraction_metadata"] == {"test": "metadata"}

    def test_table_field_missing_in_response(self, monkeypatch):
        """Test graceful handling when table field is missing from response."""
        # Mock response without "Items" in data
        sample_response = MagicMock()
        sample_response.data = {
            "Supplier name": "Test Supplier",
            "Invoice Amount": 50.0
            # Missing "Items" field
        }
        sample_response.extraction_metadata = {"test": "metadata"}

        mock_agent = MagicMock()
        mock_agent.extract.return_value = sample_response
        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)
        result_context = task.run(context)

        # Assertions
        data = result_context["data"]

        # Scalar fields processed normally
        assert data["supplier_name"] == "Test Supplier"
        assert data["invoice_amount"] == 50.0

        # Table field should be empty list or None, handled gracefully
        assert data["items"] == []  # Empty list since table data not found

        # No errors should be raised
        assert result_context.get("error") is None

    def test_invalid_pdf_path(self, monkeypatch):
        """Test error handling for invalid PDF file path."""
        # Mock the LlamaExtract to avoid actual API calls
        mock_client = MagicMock()
        mock_client.get_agent.return_value = MagicMock()
        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        context = {
            "id": "test-uuid",
            "file_path": ""  # Empty file path should trigger validation error
        }

        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)

        with pytest.raises(TaskError) as exc_info:
            task.run(context)

        # Verify the error message
        assert "File path not provided" in str(exc_info.value)

        # Test status update with error
        status_updates = MockStatusManager.status_updates
        error_updates = [update for update in status_updates if update[3]]  # Updates with error
        assert len(error_updates) > 0
        assert "Task Failed: extract_document_data" in error_updates[-1][1]

    def test_api_failure(self, monkeypatch):
        """Test error handling when LlamaCloud API fails."""
        # Mock API to raise exception
        def mock_extract(*args, **kwargs):
            raise Exception("API connection failed")

        mock_agent = MagicMock()
        mock_agent.extract.side_effect = mock_extract
        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)

        with pytest.raises(TaskError) as exc_info:
            task.run(context)

        # Test error registered in context
        assert "error" in context
        assert "API connection failed" in str(context["error"])

        # Test status error update
        status_updates = MockStatusManager.status_updates
        error_updates = [update for update in status_updates if update[3]]
        assert len(error_updates) > 0
        assert "Task Failed: extract_document_data" in error_updates[-1][1]

    def test_type_conversion(self, monkeypatch):
        """Test type conversion for different field types."""
        # Mock response with various data types
        sample_response = MagicMock()
        sample_response.data = {
            "Supplier name": "Test Supplier",
            "Invoice Amount": "123.45",  # String that should convert to float
            "Project number": "123",     # String that could convert to int but stays str
            "Items": []  # Empty table
        }
        sample_response.extraction_metadata = {}

        mock_agent = MagicMock()
        mock_agent.extract.return_value = sample_response
        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)
        result_context = task.run(context)

        data = result_context["data"]

        # Test string conversion
        assert data["supplier_name"] == "Test Supplier"
        assert isinstance(data["supplier_name"], str)

        # Test float conversion from string
        assert data["invoice_amount"] == 123.45
        assert isinstance(data["invoice_amount"], float)

        # Test string remains string
        assert data["project_number"] == "123"
        assert isinstance(data["project_number"], str)

    def test_string_cleaning(self, monkeypatch):
        """Test string cleaning in table item descriptions."""
        # Mock response with newlines in descriptions that should be cleaned
        sample_response = MagicMock()
        sample_response.data = {
            "Supplier name": "Test Supplier",
            "Items": [
                {
                    "Description": "Line 1\nLine 2\nLine 3",  # Newlines should be replaced with spaces
                    "Quantity": "1.0 PCS"
                },
                {
                    "Description": "Normal description",  # No newlines
                    "Quantity": "2.0 PCS"
                }
            ]
        }
        sample_response.extraction_metadata = {}

        mock_agent = MagicMock()
        mock_agent.extract.return_value = sample_response
        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)
        result_context = task.run(context)

        data = result_context["data"]
        items = data["items"]

        # Test newline replacement with spaces
        assert items[0]["description"] == "Line 1 Line 2 Line 3"

        # Test normal description unchanged
        assert items[1]["description"] == "Normal description"

    def test_single_table_limitation(self, monkeypatch):
        """Test handling when multiple table fields are configured."""
        # Config with two table fields (should raise error)
        sample_config = {
            'tasks': {
                'extract_document_data': {
                    'params': {
                        'api_key': 'test_api_key',
                        'agent_id': 'test_agent_id',
                        'fields': {
                            'supplier_name': {'alias': 'Supplier name', 'type': 'str'},
                            'items': {
                                'alias': 'Items',
                                'type': 'List[Any]',
                                'is_table': True,
                                'item_fields': {}
                            },
                            'products': {  # Second table field
                                'alias': 'Products',
                                'type': 'List[Any]',
                                'is_table': True,
                                'item_fields': {}
                            }
                        }
                    }
                }
            }
        }

        def mock_get(key, default=None):
            keys = key.split('.') if '.' in key else [key]
            result = sample_config
            for k in keys:
                if isinstance(result, dict) and k in result:
                    result = result[k]
                else:
                    return default
            return result

        self.config_manager.get.side_effect = mock_get

        # Mock successful API response
        sample_response = MagicMock()
        sample_response.data = {"Supplier name": "Test"}
        sample_response.extraction_metadata = {}

        mock_agent = MagicMock()
        mock_agent.extract.return_value = sample_response
        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)

        # Should raise TaskError due to multiple table fields during on_start
        with pytest.raises(TaskError) as exc_info:
            task.on_start(context)

        assert "Multiple table fields configured" in str(exc_info.value)

    def test_table_field_type_conversion(self, monkeypatch):
        """Test type conversion for different field types in table items."""
        # Mock response with mixed data types in table items
        sample_response = MagicMock()
        sample_response.data = {
            "Supplier name": "Test Supplier",
            "Items": [
                {
                    "Description": "Test item 1",
                    "Quantity": "5",  # String that should convert to int
                    "Price": "10.50"  # String that should convert to float
                },
                {
                    "Description": "Test item 2",
                    "Quantity": "3",  # Another string to int conversion
                    "Price": "15.75"  # Another string to float conversion
                }
            ]
        }
        sample_response.extraction_metadata = {}

        mock_agent = MagicMock()
        mock_agent.extract.return_value = sample_response
        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        # Use custom config with int and float types for this test
        custom_config = {
            'tasks': {
                'extract_document_data': {
                    'params': {
                        'api_key': 'test_api_key',
                        'agent_id': 'test_agent_id',
                        'fields': {
                            'supplier_name': {'alias': 'Supplier name', 'type': 'str'},
                            'items': {
                                'alias': 'Items',
                                'type': 'List[Any]',
                                'is_table': True,
                                'item_fields': {
                                    'description': {'alias': 'Description', 'type': 'str'},
                                    'quantity': {'alias': 'Quantity', 'type': 'int'},
                                    'price': {'alias': 'Price', 'type': 'float'}
                                }
                            }
                        }
                    }
                }
            }
        }

        def custom_mock_get(key, default=None):
            keys = key.split('.') if '.' in key else [key]
            result = custom_config
            for k in keys:
                if isinstance(result, dict) and k in result:
                    result = result[k]
                else:
                    return default
            return result

        self.config_manager.get.side_effect = custom_mock_get

        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)
        result_context = task.run(context)

        data = result_context["data"]
        items = data["items"]

        # Test type conversion in table items
        assert len(items) == 2

        # First item - test int and float conversion from strings
        assert items[0]["description"] == "Test item 1"
        assert items[0]["quantity"] == 5  # Should be int
        assert isinstance(items[0]["quantity"], int)
        assert items[0]["price"] == 10.50  # Should be float
        assert isinstance(items[0]["price"], float)

        # Wait, I need to check what the current config has for item_fields
        # Looking at the default config, it only has description and quantity as str
        # Let me modify the test to add price field to the config first

        # Actually, let me add a custom config for this test with price field as float
        sample_config = {
            'tasks': {
                'extract_document_data': {
                    'params': {
                        'api_key': 'test_api_key',
                        'agent_id': 'test_agent_id',
                        'fields': {
                            'supplier_name': {'alias': 'Supplier name', 'type': 'str'},
                            'items': {
                                'alias': 'Items',
                                'type': 'List[Any]',
                                'is_table': True,
                                'item_fields': {
                                    'description': {'alias': 'Description', 'type': 'str'},
                                    'quantity': {'alias': 'Quantity', 'type': 'int'},
                                    'price': {'alias': 'Price', 'type': 'float'}
                                }
                            }
                        }
                    }
                }
            }
        }

        def mock_get(key, default=None):
            keys = key.split('.') if '.' in key else [key]
            result = sample_config
            for k in keys:
                if isinstance(result, dict) and k in result:
                    result = result[k]
                else:
                    return default
            return result

        self.config_manager.get.side_effect = mock_get

        # Re-run with updated config
        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)
        result_context = task.run(context)

        data = result_context["data"]
        items = data["items"]

        # Test type conversion in table items with custom config
        assert len(items) == 2

        # First item - test int and float conversion from strings
        assert items[0]["description"] == "Test item 1"
        assert items[0]["quantity"] == 5  # Should be int
        assert isinstance(items[0]["quantity"], int)
        assert items[0]["price"] == 10.50  # Should be float
        assert isinstance(items[0]["price"], float)

        # Second item
        assert items[1]["description"] == "Test item 2"
        assert items[1]["quantity"] == 3  # Should be int
        assert isinstance(items[1]["quantity"], int)
        assert items[1]["price"] == 15.75  # Should be float
        assert isinstance(items[1]["price"], float)

    def test_bool_coercion(self, monkeypatch):
        """Test bool coercion with loose parsing matching v1 behavior."""
        # Mock response with various string values for boolean coercion
        sample_response = MagicMock()
        sample_response.data = {
            "Supplier name": "Test Supplier",
            "Is Active": "false",      # Should become False
            "Has Discount": "0",       # Should become False
            "Is Valid": "true",        # Should become True
            "Status": "1",             # Should become True
            "Enabled": "no",           # Should become False
            "Flag": "off",             # Should become False
            "Toggle": "on",            # Should become True (bool("on") = True)
            "Valid": "yes",            # Should become True (bool("yes") = True)
            "Boolean Field": True      # Non-string should work normally
        }
        sample_response.extraction_metadata = {}

        mock_agent = MagicMock()
        mock_agent.extract.return_value = sample_response
        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        # Custom config with bool fields
        bool_config = {
            'tasks': {
                'extract_document_data': {
                    'params': {
                        'api_key': 'test_api_key',
                        'agent_id': 'test_agent_id',
                        'fields': {
                            'supplier_name': {'alias': 'Supplier name', 'type': 'str'},
                            'is_active': {'alias': 'Is Active', 'type': 'bool'},
                            'has_discount': {'alias': 'Has Discount', 'type': 'bool'},
                            'is_valid': {'alias': 'Is Valid', 'type': 'bool'},
                            'status': {'alias': 'Status', 'type': 'bool'},
                            'enabled': {'alias': 'Enabled', 'type': 'bool'},
                            'flag': {'alias': 'Flag', 'type': 'bool'},
                            'toggle': {'alias': 'Toggle', 'type': 'bool'},
                            'valid': {'alias': 'Valid', 'type': 'bool'},
                            'boolean_field': {'alias': 'Boolean Field', 'type': 'bool'}
                        }
                    }
                }
            }
        }

        def bool_mock_get(key, default=None):
            keys = key.split('.') if '.' in key else [key]
            result = bool_config
            for k in keys:
                if isinstance(result, dict) and k in result:
                    result = result[k]
                else:
                    return default
            return result

        self.config_manager.get.side_effect = bool_mock_get

        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)
        result_context = task.run(context)

        data = result_context["data"]

        # Test false values
        assert data["is_active"] == False
        assert isinstance(data["is_active"], bool)
        assert data["has_discount"] == False
        assert isinstance(data["has_discount"], bool)
        assert data["enabled"] == False
        assert isinstance(data["enabled"], bool)
        assert data["flag"] == False
        assert isinstance(data["flag"], bool)

        # Test true values
        assert data["is_valid"] == True
        assert isinstance(data["is_valid"], bool)
        assert data["status"] == True
        assert isinstance(data["status"], bool)
        assert data["toggle"] == True
        assert isinstance(data["toggle"], bool)
        assert data["valid"] == True
        assert isinstance(data["valid"], bool)
        assert data["boolean_field"] == True
        assert isinstance(data["boolean_field"], bool)

        # Test string field remains string
        assert data["supplier_name"] == "Test Supplier"
        assert isinstance(data["supplier_name"], str)

    def test_int_coercion(self, monkeypatch):
        """Test int coercion using float intermediate step matching v1 behavior."""
        # Mock response with various string values for integer coercion
        sample_response = MagicMock()
        sample_response.data = {
            "Supplier name": "Test Supplier",
            "Quantity": "12.0",        # Decimal string -> 12
            "Count": "00123",          # Leading zeros -> 123
            "Value": "42",             # Normal string -> 42
            "Amount": 15.7,            # Float -> 15
            "Score": "invalid",        # Invalid string -> should remain as string with warning
            "Ref": "007",              # Leading zeros -> 7
            "Code": "0",               # Zero string -> 0
            "Int Field": 99            # Non-string should work normally
        }
        sample_response.extraction_metadata = {}

        mock_agent = MagicMock()
        mock_agent.extract.return_value = sample_response
        mock_client = MagicMock()
        mock_client.get_agent.return_value = mock_agent

        monkeypatch.setattr("standard_step.extraction.extract_pdf_v2.LlamaExtract", MagicMock(return_value=mock_client))

        # Custom config with int fields
        int_config = {
            'tasks': {
                'extract_document_data': {
                    'params': {
                        'api_key': 'test_api_key',
                        'agent_id': 'test_agent_id',
                        'fields': {
                            'supplier_name': {'alias': 'Supplier name', 'type': 'str'},
                            'quantity': {'alias': 'Quantity', 'type': 'int'},
                            'count': {'alias': 'Count', 'type': 'int'},
                            'value': {'alias': 'Value', 'type': 'int'},
                            'amount': {'alias': 'Amount', 'type': 'int'},
                            'score': {'alias': 'Score', 'type': 'int'},
                            'ref': {'alias': 'Ref', 'type': 'int'},
                            'code': {'alias': 'Code', 'type': 'int'},
                            'int_field': {'alias': 'Int Field', 'type': 'int'}
                        }
                    }
                }
            }
        }

        def int_mock_get(key, default=None):
            keys = key.split('.') if '.' in key else [key]
            result = int_config
            for k in keys:
                if isinstance(result, dict) and k in result:
                    result = result[k]
                else:
                    return default
            return result

        self.config_manager.get.side_effect = int_mock_get

        context = {"id": "test-uuid", "file_path": str(SAMPLE_PDF_SOURCE)}
        task = ExtractPdfV2Task(config_manager=self.config_manager)
        task.on_start(context)
        result_context = task.run(context)

        data = result_context["data"]

        # Test decimal string conversion
        assert data["quantity"] == 12
        assert isinstance(data["quantity"], int)

        # Test leading zeros stripped
        assert data["count"] == 123
        assert isinstance(data["count"], int)
        assert data["ref"] == 7
        assert isinstance(data["ref"], int)

        # Test normal conversion
        assert data["value"] == 42
        assert isinstance(data["value"], int)

        # Test float to int conversion
        assert data["amount"] == 15
        assert isinstance(data["amount"], int)

        # Test zero conversion
        assert data["code"] == 0
        assert isinstance(data["code"], int)

        # Test non-string conversion
        assert data["int_field"] == 99
        assert isinstance(data["int_field"], int)

        # Test invalid string remains as string (with warning logged)
        assert data["score"] == "invalid"
        assert isinstance(data["score"], str)

        # Test string field remains string
        assert data["supplier_name"] == "Test Supplier"
        assert isinstance(data["supplier_name"], str)