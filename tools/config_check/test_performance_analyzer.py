"""
Test suite for PerformanceAnalyzer functionality.

This module provides unit tests for the performance analysis capabilities
of the config-check tool, ensuring that performance issues are correctly
identified and appropriate recommendations are provided.
"""

import unittest
from typing import Dict, Any

from .performance_analyzer import PerformanceAnalyzer, PerformanceAnalysisResult


class TestPerformanceAnalyzer(unittest.TestCase):
    """Test cases for PerformanceAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = PerformanceAnalyzer()

    def test_excessive_extraction_fields_warning(self):
        """Test detection of excessive extraction fields (warning level)."""
        config = {
            "tasks": {
                "extract_data": {
                    "module": "standard_step.extraction.extract_pdf",
                    "params": {
                        "fields": [{"name": f"field_{i}", "alias": f"Field {i}", "type": "str"} for i in range(25)]
                    }
                }
            }
        }

        result = self.analyzer.analyze_performance_impact(config)
        
        # Should have one warning for excessive fields
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0].code, "performance-excessive-fields")
        self.assertIn("25 fields", result.warnings[0].message)

    def test_excessive_extraction_fields_error(self):
        """Test detection of excessive extraction fields (error level)."""
        config = {
            "tasks": {
                "extract_data": {
                    "module": "standard_step.extraction.extract_pdf",
                    "params": {
                        "fields": [{"name": f"field_{i}", "alias": f"Field {i}", "type": "str"} for i in range(55)]
                    }
                }
            }
        }

        result = self.analyzer.analyze_performance_impact(config)
        
        # Should have one error for excessive fields
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].code, "performance-excessive-fields-critical")
        self.assertIn("55 fields", result.errors[0].message)

    def test_multiple_table_fields_warning(self):
        """Test detection of multiple table fields."""
        config = {
            "tasks": {
                "extract_data": {
                    "module": "standard_step.extraction.extract_pdf",
                    "params": {
                        "fields": [
                            {"name": "supplier", "alias": "Supplier", "type": "str"},
                            {"name": "line_items", "alias": "Line Items", "type": "List[dict]", "is_table": True},
                            {"name": "payments", "alias": "Payments", "type": "List[dict]", "is_table": True},
                            {"name": "taxes", "alias": "Taxes", "type": "List[dict]", "is_table": True},
                            {"name": "discounts", "alias": "Discounts", "type": "List[dict]", "is_table": True}
                        ]
                    }
                }
            }
        }

        result = self.analyzer.analyze_performance_impact(config)
        
        # Should have one warning for multiple table fields
        warnings = [w for w in result.warnings if w.code == "performance-multiple-tables-warning"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("4 table fields", warnings[0].message)





    def test_excessive_pipeline_length_warning(self):
        """Test detection of excessive pipeline length."""
        config = {
            "pipeline": [f"task_{i}" for i in range(20)],
            "tasks": {f"task_{i}": {"module": "test.module", "params": {}} for i in range(20)}
        }

        result = self.analyzer.analyze_performance_impact(config)
        
        # Should have one warning for excessive pipeline length
        warnings = [w for w in result.warnings if w.code == "performance-excessive-pipeline-length"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("20 tasks", warnings[0].message)

    def test_multiple_extraction_tasks_warning(self):
        """Test detection of multiple extraction tasks in pipeline."""
        config = {
            "pipeline": ["extract_1", "extract_2", "extract_3", "store_data"],
            "tasks": {
                "extract_1": {"module": "standard_step.extraction.extract_pdf", "params": {}},
                "extract_2": {"module": "standard_step.extraction.extract_pdf_v2", "params": {}},
                "extract_3": {"module": "standard_step.extraction.extract_document", "params": {}},
                "store_data": {"module": "standard_step.storage.store_json", "params": {}}
            }
        }

        result = self.analyzer.analyze_performance_impact(config)
        
        # Should have one warning for multiple extraction tasks
        warnings = [w for w in result.warnings if w.code == "performance-multiple-extraction-tasks"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("3 extraction tasks", warnings[0].message)

    def test_no_performance_issues(self):
        """Test configuration with no performance issues."""
        config = {
            "pipeline": ["extract_data", "store_data"],
            "tasks": {
                "extract_data": {
                    "module": "standard_step.extraction.extract_pdf",
                    "params": {
                        "fields": [
                            {"name": "supplier", "alias": "Supplier", "type": "str"},
                            {"name": "amount", "alias": "Amount", "type": "float"},
                            {"name": "date", "alias": "Date", "type": "str"}
                        ]
                    }
                },
                "store_data": {
                    "module": "standard_step.storage.store_json",
                    "params": {"data_dir": "./output", "filename": "{supplier}.json"}
                }
            }
        }

        result = self.analyzer.analyze_performance_impact(config)
        
        # Should have no performance issues
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.warnings), 0)
        self.assertEqual(len(result.info), 0)

    def test_complex_field_patterns_info(self):
        """Test detection of complex field patterns."""
        config = {
            "tasks": {
                "extract_data": {
                    "module": "standard_step.extraction.extract_pdf",
                    "params": {
                        "fields": [
                            {
                                "name": "complex_field",
                                "alias": "Complex Field",
                                "type": "str",
                                "description": "extract complex data with multiple extract patterns and extract conditions",
                                "conditions": [
                                    {"type": "contains", "value": "pattern1"},
                                    {"type": "matches", "value": "pattern2"},
                                    {"type": "starts_with", "value": "pattern3"},
                                    {"type": "ends_with", "value": "pattern4"}
                                ]
                            }
                        ]
                    }
                }
            }
        }

        result = self.analyzer.analyze_performance_impact(config)
        
        # Should have one info message for complex patterns
        info_messages = [i for i in result.info if i.code == "performance-complex-field-patterns"]
        self.assertEqual(len(info_messages), 1)
        self.assertIn("complex extraction patterns", info_messages[0].message)

    def test_complex_context_paths_info(self):
        """Test detection of deeply nested context paths."""
        config = {
            "tasks": {
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "params": {
                        "reference_file": "reference.csv",
                        "update_field": "status",
                        "csv_match": {
                            "type": "column_equals_all",
                            "clauses": [
                                {"column": "field1", "from_context": "level1.level2.level3.level4.field1"},  # 4+ levels
                                {"column": "field2", "from_context": "simple_field"},  # Simple
                                {"column": "field3", "from_context": "level1.level2.level3.level4.level5.field3"}  # 5+ levels
                            ]
                        }
                    }
                }
            }
        }

        result = self.analyzer.analyze_performance_impact(config)
        
        # Should have one info message for complex context paths
        info_messages = [i for i in result.info if i.code == "performance-complex-context-paths"]
        self.assertEqual(len(info_messages), 1)
        self.assertIn("2 clauses with deeply nested context paths", info_messages[0].message)


if __name__ == "__main__":
    unittest.main()