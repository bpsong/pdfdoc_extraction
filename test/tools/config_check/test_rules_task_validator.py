"""Tests for rules task validation functionality.

This module contains comprehensive tests for the RulesTaskValidator class
that validates rules task configurations including CSV structure validation,
column existence validation, clause uniqueness detection, context path validation,
deprecation warnings, and semantic validation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
import yaml

# Add tools directory to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOLS_PATH = PROJECT_ROOT / "tools"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TOOLS_PATH) not in sys.path:
    sys.path.insert(0, str(TOOLS_PATH))

from tools.config_check.rules_task_validator import RulesTaskValidator, validate_rules_task
from tools.config_check.task_validator import TaskIssue


class TestCSVStructureValidation:
    """Test CSV structure validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = RulesTaskValidator()
        self.fixtures_path = Path(__file__).parent / "fixtures" / "rules_task"
        self.csv_path = self.fixtures_path / "csv_files"
    
    def test_valid_csv_file_parsing_and_column_detection(self):
        """Test valid CSV file parsing and column detection."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not have any CSV structure errors
        csv_errors = [f for f in findings if f.code in ["rules-csv-not-readable", "rules-csv-empty", "file-not-found"]]
        assert len(csv_errors) == 0
        
        # Should have stored columns for later validation
        assert "test_task" in self.validator._csv_columns
        expected_columns = ["supplier_name", "invoice_number", "amount", "status", "policy_number"]
        assert self.validator._csv_columns["test_task"] == expected_columns
    
    def test_empty_csv_file_handling(self):
        """Test empty CSV file handling."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "empty_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect empty CSV
        empty_errors = [f for f in findings if f.code == "rules-csv-empty"]
        assert len(empty_errors) == 1
        assert "empty" in empty_errors[0].message.lower()
        assert "empty_reference.csv" in empty_errors[0].message
    
    def test_malformed_csv_file_error_handling(self):
        """Test malformed CSV file error handling."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "invalid_format.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should handle malformed CSV gracefully
        # Note: pandas might still parse this file, so we check if it either:
        # 1. Reports an error, or 2. Successfully parses with available columns
        csv_errors = [f for f in findings if f.code in ["rules-csv-not-readable", "rules-csv-empty"]]
        
        # If no CSV errors, then pandas parsed it successfully
        if len(csv_errors) == 0:
            assert "test_task" in self.validator._csv_columns
        else:
            # If there are errors, they should be descriptive
            assert any("Cannot read CSV file" in error.message for error in csv_errors)
    
    def test_missing_file_error_scenarios(self):
        """Test missing file error scenarios."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "nonexistent_file.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect missing file
        missing_errors = [f for f in findings if f.code == "file-not-found"]
        assert len(missing_errors) == 1
        assert "not found" in missing_errors[0].message
        assert "nonexistent_file.csv" in missing_errors[0].message
    
    def test_completely_empty_csv_file(self):
        """Test completely empty CSV file handling."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "completely_empty.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect empty data error
        empty_errors = [f for f in findings if f.code in ["rules-csv-missing-headers", "rules-csv-empty"]]
        assert len(empty_errors) >= 1
        assert any("empty" in error.message.lower() or "no columns" in error.message.lower() 
                  for error in empty_errors)
    
    def test_no_reference_file_specified(self):
        """Test behavior when no reference file is specified."""
        task_config = {
            "params": {
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not generate CSV-related errors when no reference file is specified
        csv_errors = [f for f in findings if f.code.startswith("rules-csv") or f.code == "file-not-found"]
        assert len(csv_errors) == 0
    
    @patch('tools.config_check.rules_task_validator.PANDAS_AVAILABLE', False)
    def test_pandas_not_available(self):
        """Test behavior when pandas is not available."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect pandas missing
        pandas_errors = [f for f in findings if f.code == "rules-csv-pandas-missing"]
        assert len(pandas_errors) == 1
        assert "pandas is required" in pandas_errors[0].message


class TestColumnExistenceValidation:
    """Test column existence validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = RulesTaskValidator()
        self.fixtures_path = Path(__file__).parent / "fixtures" / "rules_task"
        self.csv_path = self.fixtures_path / "csv_files"
    
    def test_validation_of_update_field_against_csv_columns(self):
        """Test validation of update_field against CSV columns."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",  # Valid column
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not have update_field errors
        update_field_errors = [f for f in findings if "update_field" in f.path and f.code == "rules-column-not-found"]
        assert len(update_field_errors) == 0
    
    def test_validation_of_invalid_update_field(self):
        """Test validation of invalid update_field."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "nonexistent_field",  # Invalid column
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect invalid update_field
        update_field_errors = [f for f in findings if "update_field" in f.path and f.code == "rules-column-not-found"]
        assert len(update_field_errors) == 1
        assert "nonexistent_field" in update_field_errors[0].message
        assert "not found in CSV columns" in update_field_errors[0].message
    
    def test_validation_of_clause_column_references(self):
        """Test validation of clause column references."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},  # Valid
                        {"column": "invoice_number", "from_context": "invoice_number"},  # Valid
                        {"column": "amount", "from_context": "total_amount"}  # Valid
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not have clause column errors
        clause_column_errors = [f for f in findings if "clauses[" in f.path and f.code == "rules-column-not-found"]
        assert len(clause_column_errors) == 0
    
    def test_error_reporting_for_nonexistent_clause_columns(self):
        """Test error reporting for non-existent clause columns."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},  # Valid
                        {"column": "missing_column", "from_context": "some_value"},  # Invalid
                        {"column": "another_missing_column", "from_context": "another_value"}  # Invalid
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect invalid clause columns
        clause_column_errors = [f for f in findings if "clauses[" in f.path and f.code == "rules-column-not-found"]
        assert len(clause_column_errors) == 2
        
        # Check specific error messages
        error_messages = [error.message for error in clause_column_errors]
        assert any("missing_column" in msg for msg in error_messages)
        assert any("another_missing_column" in msg for msg in error_messages)
        assert all("not found in CSV columns" in msg for msg in error_messages)
    
    def test_column_validation_with_missing_csv_columns(self):
        """Test column validation when CSV columns are not available (CSV validation failed)."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "nonexistent_file.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should have file not found error but no column validation errors
        file_errors = [f for f in findings if f.code == "file-not-found"]
        column_errors = [f for f in findings if f.code == "rules-column-not-found"]
        
        assert len(file_errors) == 1
        assert len(column_errors) == 0  # Column validation should be skipped
    
    def test_column_validation_with_invalid_csv_match_structure(self):
        """Test column validation when csv_match is not a dictionary."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": "invalid_structure"  # Not a dictionary
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should skip column validation when csv_match is invalid
        column_errors = [f for f in findings if f.code == "rules-column-not-found"]
        assert len(column_errors) == 0
    
    def test_column_validation_with_invalid_clause_structure(self):
        """Test column validation when clauses contain non-dictionary items."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},  # Valid
                        "invalid_clause",  # Not a dictionary
                        {"column": "invoice_number", "from_context": "invoice_number"}  # Valid
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should validate valid clauses and skip invalid ones
        column_errors = [f for f in findings if f.code == "rules-column-not-found"]
        assert len(column_errors) == 0  # All valid columns should pass
    
    def test_column_validation_with_empty_column_names(self):
        """Test column validation with empty or None column names."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "", "from_context": "supplier_name"},  # Empty column
                        {"column": None, "from_context": "invoice_number"},  # None column
                        {"from_context": "amount"}  # Missing column key
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not generate column validation errors for empty/None columns
        column_errors = [f for f in findings if f.code == "rules-column-not-found"]
        assert len(column_errors) == 0


class TestClauseUniquenessValidation:
    """Test clause uniqueness validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = RulesTaskValidator()
        self.fixtures_path = Path(__file__).parent / "fixtures" / "rules_task"
        self.csv_path = self.fixtures_path / "csv_files"
    
    def test_detection_of_completely_identical_clauses(self):
        """Test detection of completely identical clauses."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},
                        {"column": "invoice_number", "from_context": "invoice_number"},
                        {"column": "supplier_name", "from_context": "supplier_name"},  # Exact duplicate
                        {"column": "amount", "from_context": "total_amount", "number": True},
                        {"column": "amount", "from_context": "total_amount", "number": True}  # Exact duplicate with number flag
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect duplicate clauses
        duplicate_errors = [f for f in findings if f.code == "rules-duplicate-clause"]
        assert len(duplicate_errors) == 2
        
        # Check error messages contain duplicate information
        error_messages = [error.message for error in duplicate_errors]
        assert any("supplier_name" in msg for msg in error_messages)
        assert any("total_amount" in msg for msg in error_messages)
    
    def test_warning_generation_for_multiple_clauses_on_same_column(self):
        """Test warning generation for multiple clauses on same column."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},
                        {"column": "amount", "from_context": "total_amount"},
                        {"column": "amount", "from_context": "different_amount"},  # Same column, different context
                        {"column": "invoice_number", "from_context": "invoice_number"},
                        {"column": "amount", "from_context": "another_amount"}  # Third clause on same column
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should warn about multiple clauses on same column
        impossible_condition_warnings = [f for f in findings if f.code == "rules-impossible-condition"]
        assert len(impossible_condition_warnings) == 1
        
        warning = impossible_condition_warnings[0]
        assert "amount" in warning.message
        assert "impossible AND conditions" in warning.message
        assert "indices:" in warning.message
    
    def test_info_messages_for_multiple_clauses_using_same_context(self):
        """Test info messages for multiple clauses using same context."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},
                        {"column": "invoice_number", "from_context": "supplier_name"},  # Same context, different column
                        {"column": "amount", "from_context": "total_amount"},
                        {"column": "policy_number", "from_context": "supplier_name"}  # Same context again
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should generate info message about context reuse
        context_reuse_info = [f for f in findings if f.code == "rules-context-reuse"]
        assert len(context_reuse_info) == 1
        
        info = context_reuse_info[0]
        assert "supplier_name" in info.message
        assert "Multiple clauses use context" in info.message
        assert "might be intentional" in info.message
    
    def test_no_warnings_for_unique_clauses(self):
        """Test that no warnings are generated for unique clauses."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},
                        {"column": "invoice_number", "from_context": "invoice_number"},
                        {"column": "amount", "from_context": "total_amount"},
                        {"column": "policy_number", "from_context": "policy_number"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not have any uniqueness-related issues
        uniqueness_issues = [f for f in findings if f.code in [
            "rules-duplicate-clause", "rules-impossible-condition", "rules-context-reuse"
        ]]
        assert len(uniqueness_issues) == 0
    
    def test_clause_uniqueness_with_number_flag_variations(self):
        """Test clause uniqueness detection with number flag variations."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "amount", "from_context": "total_amount", "number": True},
                        {"column": "amount", "from_context": "total_amount", "number": False},  # Different number flag
                        {"column": "amount", "from_context": "total_amount"},  # No number flag (default False)
                        {"column": "amount", "from_context": "total_amount", "number": False}  # Duplicate of clause 2
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect two duplicates (clauses 2 and 3 are identical - both default to False)
        duplicate_errors = [f for f in findings if f.code == "rules-duplicate-clause"]
        assert len(duplicate_errors) == 2
        
        # Should warn about multiple clauses on same column
        impossible_condition_warnings = [f for f in findings if f.code == "rules-impossible-condition"]
        assert len(impossible_condition_warnings) == 1
    
    def test_clause_uniqueness_with_invalid_csv_match_structure(self):
        """Test clause uniqueness validation when csv_match is not a dictionary."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": "invalid_structure"  # Not a dictionary
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should skip uniqueness validation when csv_match is invalid
        uniqueness_issues = [f for f in findings if f.code in [
            "rules-duplicate-clause", "rules-impossible-condition", "rules-context-reuse"
        ]]
        assert len(uniqueness_issues) == 0
    
    def test_clause_uniqueness_with_invalid_clause_structure(self):
        """Test clause uniqueness validation when clauses contain non-dictionary items."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},
                        "invalid_clause",  # Not a dictionary
                        {"column": "supplier_name", "from_context": "supplier_name"},  # Duplicate of first
                        {"column": "invoice_number", "from_context": "invoice_number"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect duplicate between valid clauses and skip invalid ones
        duplicate_errors = [f for f in findings if f.code == "rules-duplicate-clause"]
        assert len(duplicate_errors) == 1
    
    def test_clause_uniqueness_with_empty_clauses_list(self):
        """Test clause uniqueness validation with empty clauses list."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": []  # Empty list
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not generate any uniqueness issues for empty clauses
        uniqueness_issues = [f for f in findings if f.code in [
            "rules-duplicate-clause", "rules-impossible-condition", "rules-context-reuse"
        ]]
        assert len(uniqueness_issues) == 0
    
    def test_clause_uniqueness_with_missing_column_or_context(self):
        """Test clause uniqueness validation with missing column or context values."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},
                        {"column": "", "from_context": "supplier_name"},  # Empty column
                        {"column": "supplier_name", "from_context": ""},  # Empty context
                        {"from_context": "supplier_name"},  # Missing column
                        {"column": "supplier_name"}  # Missing context
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should handle missing/empty values gracefully
        # Only clauses with both column and context should be considered for uniqueness
        uniqueness_issues = [f for f in findings if f.code in [
            "rules-duplicate-clause", "rules-impossible-condition", "rules-context-reuse"
        ]]
        
        # Should not crash and should handle the valid clauses appropriately
        assert isinstance(uniqueness_issues, list)


class TestContextPathValidation:
    """Test context path validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = RulesTaskValidator()
        self.fixtures_path = Path(__file__).parent / "fixtures" / "rules_task"
        self.csv_path = self.fixtures_path / "csv_files"
        self.extraction_path = self.fixtures_path / "extraction_fields"
    
    def _load_extraction_fields(self, filename: str) -> Dict[str, Any]:
        """Load extraction fields from YAML file."""
        with open(self.extraction_path / filename, 'r') as f:
            data = yaml.safe_load(f)
            return data.get('fields', {})
    
    def test_valid_dotted_path_syntax_validation(self):
        """Test valid dotted path syntax validation."""
        extraction_fields = self._load_extraction_fields("sample_extraction.yaml")
        
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},  # Valid
                        {"column": "invoice_number", "from_context": "invoice_number"},  # Valid
                        {"column": "amount", "from_context": "total_amount"},  # Valid
                        {"column": "policy_number", "from_context": "policy_number"}  # Valid
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config, extraction_fields)
        
        # Should not have any context path syntax errors
        context_path_errors = [f for f in findings if f.code == "rules-context-path-invalid"]
        assert len(context_path_errors) == 0
    
    def test_invalid_path_syntax_error_detection(self):
        """Test invalid path syntax error detection."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "123invalid_start"},  # Invalid: starts with number
                        {"column": "invoice_number", "from_context": "field-with-dashes"},  # Invalid: contains dashes
                        {"column": "amount", "from_context": "field with spaces"},  # Invalid: contains spaces
                        {"column": "status", "from_context": "field..double.dots"}  # Invalid: double dots
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect invalid path syntax
        context_path_errors = [f for f in findings if f.code == "rules-context-path-invalid"]
        assert len(context_path_errors) == 4
        
        # Check specific error messages
        error_messages = [error.message for error in context_path_errors]
        assert any("123invalid_start" in msg for msg in error_messages)
        assert any("field-with-dashes" in msg for msg in error_messages)
        assert any("field with spaces" in msg for msg in error_messages)
        assert any("field..double.dots" in msg for msg in error_messages)
        assert all("Invalid dotted path syntax" in msg for msg in error_messages)
    
    def test_field_existence_validation_against_extraction_fields(self):
        """Test field existence validation against extraction fields."""
        extraction_fields = self._load_extraction_fields("sample_extraction.yaml")
        
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},  # Exists in extraction
                        {"column": "invoice_number", "from_context": "invoice_number"},  # Exists in extraction
                        {"column": "amount", "from_context": "nonexistent_field"},  # Does not exist
                        {"column": "status", "from_context": "another_missing_field"}  # Does not exist
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config, extraction_fields)
        
        # Should detect missing fields
        field_not_found_warnings = [f for f in findings if f.code == "rules-field-not-found"]
        assert len(field_not_found_warnings) == 2
        
        # Check specific error messages
        error_messages = [error.message for error in field_not_found_warnings]
        assert any("nonexistent_field" in msg for msg in error_messages)
        assert any("another_missing_field" in msg for msg in error_messages)
        assert all("not found in extraction fields" in msg for msg in error_messages)
    
    def test_context_path_validation_without_extraction_fields(self):
        """Test context path validation when no extraction fields are provided."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},
                        {"column": "invoice_number", "from_context": "nonexistent_field"}  # Can't validate without extraction fields
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not generate field existence errors when no extraction fields provided
        field_not_found_warnings = [f for f in findings if f.code == "rules-field-not-found"]
        assert len(field_not_found_warnings) == 0
    
    def test_context_path_validation_with_empty_extraction_fields(self):
        """Test context path validation with empty extraction fields."""
        extraction_fields = self._load_extraction_fields("empty_fields.yaml")
        
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},
                        {"column": "invoice_number", "from_context": "invoice_number"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config, extraction_fields)
        
        # Should not generate field not found warnings when extraction fields is empty (no fields to validate against)
        field_not_found_warnings = [f for f in findings if f.code == "rules-field-not-found"]
        assert len(field_not_found_warnings) == 0
    
    def test_context_path_validation_with_complex_dotted_paths(self):
        """Test context path validation with complex dotted paths."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "nested.field.value"},  # Valid dotted path
                        {"column": "invoice_number", "from_context": "deep.nested.field.path"},  # Valid dotted path
                        {"column": "amount", "from_context": "single_field"},  # Valid single field
                        {"column": "status", "from_context": "field.with.numbers123"}  # Valid with numbers
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not have any context path syntax errors for valid dotted paths
        context_path_errors = [f for f in findings if f.code == "rules-context-path-invalid"]
        assert len(context_path_errors) == 0
    
    def test_context_path_validation_with_missing_from_context(self):
        """Test context path validation when from_context is missing or empty."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},  # Valid
                        {"column": "invoice_number", "from_context": ""},  # Empty context
                        {"column": "amount"},  # Missing from_context
                        {"column": "status", "from_context": None}  # None context
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should skip validation for clauses without valid from_context
        context_path_errors = [f for f in findings if f.code in ["rules-context-path-invalid", "rules-field-not-found"]]
        assert len(context_path_errors) == 0
    
    def test_context_path_validation_with_invalid_csv_match_structure(self):
        """Test context path validation when csv_match is not a dictionary."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": "invalid_structure"  # Not a dictionary
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should skip context path validation when csv_match is invalid
        context_path_errors = [f for f in findings if f.code in ["rules-context-path-invalid", "rules-field-not-found"]]
        assert len(context_path_errors) == 0


class TestDeprecationWarnings:
    """Test deprecation warning functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = RulesTaskValidator()
        self.fixtures_path = Path(__file__).parent / "fixtures" / "rules_task"
        self.csv_path = self.fixtures_path / "csv_files"
    
    def test_detection_of_deprecated_data_prefixes(self):
        """Test detection of deprecated 'data.' prefixes."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "data.supplier_name"},  # Deprecated
                        {"column": "invoice_number", "from_context": "data.invoice_number"},  # Deprecated
                        {"column": "amount", "from_context": "total_amount"},  # Not deprecated
                        {"column": "status", "from_context": "data.status_value"}  # Deprecated
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect deprecated data. prefixes
        deprecation_warnings = [f for f in findings if f.code == "rules-deprecated-data-prefix"]
        assert len(deprecation_warnings) == 3
        
        # Check specific warning messages
        warning_messages = [warning.message for warning in deprecation_warnings]
        assert any("data.supplier_name" in msg for msg in warning_messages)
        assert any("data.invoice_number" in msg for msg in warning_messages)
        assert any("data.status_value" in msg for msg in warning_messages)
        assert all("Deprecated 'data.' prefix" in msg for msg in warning_messages)
    
    def test_warning_message_generation(self):
        """Test warning message generation for deprecated prefixes."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "data.supplier_name"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should generate appropriate warning message
        deprecation_warnings = [f for f in findings if f.code == "rules-deprecated-data-prefix"]
        assert len(deprecation_warnings) == 1
        
        warning = deprecation_warnings[0]
        assert "data.supplier_name" in warning.message
        assert "Deprecated 'data.' prefix" in warning.message
        assert "Use bare field name" in warning.message
        assert "supplier_name" in warning.message  # Should suggest the replacement
    
    def test_suggested_corrections_in_warning_messages(self):
        """Test suggested corrections in warning messages."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "data.nested.field.path"},
                        {"column": "invoice_number", "from_context": "data.simple_field"},
                        {"column": "amount", "from_context": "data.field_with_123numbers"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should generate warnings with correct suggestions
        deprecation_warnings = [f for f in findings if f.code == "rules-deprecated-data-prefix"]
        assert len(deprecation_warnings) == 3
        
        # Check that suggestions are correct (data. prefix removed)
        warning_messages = [warning.message for warning in deprecation_warnings]
        assert any("nested.field.path" in msg for msg in warning_messages)
        assert any("simple_field" in msg for msg in warning_messages)
        assert any("field_with_123numbers" in msg for msg in warning_messages)
        
        # Check that details contain suggested replacements
        for warning in deprecation_warnings:
            if hasattr(warning, 'details') and warning.details:
                assert 'suggested_replacement' in warning.details
    
    def test_no_warnings_for_non_deprecated_paths(self):
        """Test that no warnings are generated for non-deprecated paths."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},  # No prefix
                        {"column": "invoice_number", "from_context": "nested.field.path"},  # No data. prefix
                        {"column": "amount", "from_context": "simple_field"},  # No prefix
                        {"column": "status", "from_context": "field.with.dots"}  # No data. prefix
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not generate any deprecation warnings
        deprecation_warnings = [f for f in findings if f.code == "rules-deprecated-data-prefix"]
        assert len(deprecation_warnings) == 0
    
    def test_deprecation_warnings_with_empty_from_context(self):
        """Test deprecation warnings when from_context is empty or missing."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": ""},  # Empty context
                        {"column": "invoice_number"},  # Missing from_context
                        {"column": "amount", "from_context": None},  # None context
                        {"column": "status", "from_context": "data.valid_field"}  # Valid deprecated field
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should only generate warning for the valid deprecated field
        deprecation_warnings = [f for f in findings if f.code == "rules-deprecated-data-prefix"]
        assert len(deprecation_warnings) == 1
        assert "data.valid_field" in deprecation_warnings[0].message
    
    def test_deprecation_warnings_with_invalid_csv_match_structure(self):
        """Test deprecation warnings when csv_match is not a dictionary."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": "invalid_structure"  # Not a dictionary
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should skip deprecation warnings when csv_match is invalid
        deprecation_warnings = [f for f in findings if f.code == "rules-deprecated-data-prefix"]
        assert len(deprecation_warnings) == 0
    
    def test_deprecation_warnings_with_invalid_clause_structure(self):
        """Test deprecation warnings when clauses contain non-dictionary items."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "data.supplier_name"},  # Valid deprecated
                        "invalid_clause",  # Not a dictionary
                        {"column": "invoice_number", "from_context": "data.invoice_number"}  # Valid deprecated
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should generate warnings for valid clauses and skip invalid ones
        deprecation_warnings = [f for f in findings if f.code == "rules-deprecated-data-prefix"]
        assert len(deprecation_warnings) == 2
        
        warning_messages = [warning.message for warning in deprecation_warnings]
        assert any("data.supplier_name" in msg for msg in warning_messages)
        assert any("data.invoice_number" in msg for msg in warning_messages)
    
    def test_deprecation_warnings_edge_cases(self):
        """Test deprecation warnings with edge cases."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "data."},  # Just "data."
                        {"column": "invoice_number", "from_context": "data"},  # Just "data" (no dot)
                        {"column": "amount", "from_context": "datax.field"},  # Similar but not "data."
                        {"column": "status", "from_context": "data.field.data.nested"}  # data. prefix with nested data
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should only detect actual "data." prefixes
        deprecation_warnings = [f for f in findings if f.code == "rules-deprecated-data-prefix"]
        
        # Should detect "data." and "data.field.data.nested" (both start with "data.")
        assert len(deprecation_warnings) == 2
        
        warning_messages = [warning.message for warning in deprecation_warnings]
        assert any("data." in msg for msg in warning_messages)
        assert any("data.field.data.nested" in msg for msg in warning_messages)


class TestSemanticValidation:
    """Test semantic validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = RulesTaskValidator()
        self.fixtures_path = Path(__file__).parent / "fixtures" / "rules_task"
        self.csv_path = self.fixtures_path / "csv_files"
        self.extraction_path = self.fixtures_path / "extraction_fields"
    
    def _load_extraction_fields(self, filename: str) -> Dict[str, Any]:
        """Load extraction fields from YAML file."""
        with open(self.extraction_path / filename, 'r') as f:
            data = yaml.safe_load(f)
            return data.get('fields', {})
    
    def test_type_mismatch_detection_between_fields_and_comparisons(self):
        """Test type mismatch detection between fields and comparisons."""
        extraction_fields = self._load_extraction_fields("numeric_fields.yaml")
        
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "amount", "from_context": "total_amount", "number": False},  # Numeric column, string comparison
                        {"column": "invoice_number", "from_context": "invoice_number", "number": False},  # String column, string comparison (OK)
                        {"column": "supplier_name", "from_context": "supplier_name", "number": True},  # String column, numeric comparison (less common but possible)
                        {"column": "policy_number", "from_context": "quantity", "number": False}  # Numeric-sounding column, string comparison
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config, extraction_fields)
        
        # Should detect type mismatches for numeric columns with string comparison
        type_mismatch_warnings = [f for f in findings if f.code == "rules-semantic-type-mismatch"]
        assert len(type_mismatch_warnings) >= 1
        
        # Check that amount column type mismatch is detected
        warning_messages = [warning.message for warning in type_mismatch_warnings]
        assert any("amount" in msg and "numeric" in msg for msg in warning_messages)
    
    def test_unrealistic_field_reference_detection(self):
        """Test unrealistic field reference detection."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},  # Realistic
                        {"column": "invoice_number", "from_context": "test_field"},  # Unrealistic
                        {"column": "amount", "from_context": "foo_bar_baz"},  # Very unrealistic
                        {"column": "status", "from_context": "dummy_value"},  # Unrealistic
                        {"column": "policy_number", "from_context": "invoice_total"}  # Realistic
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect unrealistic field references
        unrealistic_field_warnings = [f for f in findings if f.code == "rules-unrealistic-field-reference"]
        assert len(unrealistic_field_warnings) >= 2
        
        # Check specific unrealistic fields are detected
        warning_messages = [warning.message for warning in unrealistic_field_warnings]
        assert any("test_field" in msg for msg in warning_messages)
        assert any("foo_bar_baz" in msg for msg in warning_messages)
        assert any("dummy_value" in msg for msg in warning_messages)
    
    def test_impossible_condition_flagging(self):
        """Test impossible condition flagging."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "amount", "from_context": "total_amount"},
                        {"column": "amount", "from_context": "different_amount"},  # Same column, different values
                        {"column": "amount", "from_context": "another_amount"},  # Third clause on same column
                        {"column": "supplier_name", "from_context": "supplier_name"}  # Different column (OK)
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should flag impossible conditions (multiple clauses on same column)
        impossible_condition_warnings = [f for f in findings if f.code == "rules-impossible-condition"]
        assert len(impossible_condition_warnings) == 1
        
        warning = impossible_condition_warnings[0]
        assert "amount" in warning.message
        assert "impossible AND conditions" in warning.message
    
    def test_semantic_validation_with_missing_csv_columns(self):
        """Test semantic validation when CSV columns are not available."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "nonexistent_file.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "amount", "from_context": "total_amount", "number": False}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should skip semantic validation when CSV validation failed
        semantic_warnings = [f for f in findings if f.code in [
            "rules-semantic-type-mismatch", "rules-unrealistic-field-reference"
        ]]
        assert len(semantic_warnings) == 0
        
        # Should still have file not found error
        file_errors = [f for f in findings if f.code == "file-not-found"]
        assert len(file_errors) == 1
    
    def test_semantic_validation_with_realistic_field_names(self):
        """Test that realistic field names don't trigger unrealistic warnings."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "supplier_name"},
                        {"column": "invoice_number", "from_context": "invoice_number"},
                        {"column": "amount", "from_context": "total_amount"},
                        {"column": "status", "from_context": "invoice_date"},
                        {"column": "policy_number", "from_context": "customer_email"}
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should not generate unrealistic field warnings for common field names
        unrealistic_field_warnings = [f for f in findings if f.code == "rules-unrealistic-field-reference"]
        assert len(unrealistic_field_warnings) == 0
    
    def test_semantic_validation_with_numeric_column_detection(self):
        """Test numeric column detection logic."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "amount", "from_context": "total_amount", "number": False},  # Should warn
                        {"column": "supplier_name", "from_context": "supplier_name", "number": False},  # Should not warn
                        {"column": "status", "from_context": "status", "number": False}  # Should not warn
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should only warn about the amount column (numeric column with string comparison)
        type_mismatch_warnings = [f for f in findings if f.code == "rules-semantic-type-mismatch"]
        assert len(type_mismatch_warnings) == 1
        assert "amount" in type_mismatch_warnings[0].message
    
    def test_semantic_validation_with_invalid_csv_match_structure(self):
        """Test semantic validation when csv_match is not a dictionary."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": "invalid_structure"  # Not a dictionary
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should skip semantic validation when csv_match is invalid
        semantic_warnings = [f for f in findings if f.code in [
            "rules-semantic-type-mismatch", "rules-unrealistic-field-reference"
        ]]
        assert len(semantic_warnings) == 0
    
    def test_semantic_validation_with_missing_clause_data(self):
        """Test semantic validation with missing column or context data."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "amount", "from_context": "total_amount", "number": False},  # Complete clause
                        {"column": "", "from_context": "supplier_name"},  # Empty column
                        {"column": "supplier_name", "from_context": ""},  # Empty context
                        {"from_context": "invoice_number"},  # Missing column
                        {"column": "policy_number"}  # Missing context
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should only validate complete clauses
        type_mismatch_warnings = [f for f in findings if f.code == "rules-semantic-type-mismatch"]
        assert len(type_mismatch_warnings) == 1  # Only the complete clause should be validated
        assert "amount" in type_mismatch_warnings[0].message
    
    def test_semantic_validation_with_data_prefix_handling(self):
        """Test semantic validation handles data. prefixes correctly."""
        task_config = {
            "params": {
                "reference_file": str(self.csv_path / "valid_reference.csv"),
                "update_field": "status",
                "csv_match": {
                    "clauses": [
                        {"column": "supplier_name", "from_context": "data.test_field"},  # Should detect unrealistic after removing prefix
                        {"column": "invoice_number", "from_context": "data.invoice_number"},  # Should be realistic after removing prefix
                        {"column": "amount", "from_context": "data.foo_bar"}  # Should detect unrealistic after removing prefix
                    ]
                }
            }
        }
        
        findings = self.validator.validate_rules_task("test_task", task_config)
        
        # Should detect unrealistic fields after removing data. prefix
        unrealistic_field_warnings = [f for f in findings if f.code == "rules-unrealistic-field-reference"]
        assert len(unrealistic_field_warnings) >= 1
        
        # Should also have deprecation warnings
        deprecation_warnings = [f for f in findings if f.code == "rules-deprecated-data-prefix"]
        assert len(deprecation_warnings) == 3