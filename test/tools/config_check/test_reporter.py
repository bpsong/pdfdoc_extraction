#!/usr/bin/env python3
"""
Test suite for config-check reporter functionality.

This module contains comprehensive tests for the output formatting and reporting system.
Tests cover Finding dataclass, ValidationReporter class, text and JSON output formats,
categorization system, and exit code determination.
"""

import json
import sys
import tempfile
from io import StringIO
from pathlib import Path

# Add the tools directory to the path so we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from tools.config_check.reporter import Finding, FindingLevel, ValidationReporter


class TestFinding:
    """Test cases for Finding dataclass functionality."""

    def test_finding_creation_minimal(self):
        """Test creating a Finding with minimal required fields."""
        finding = Finding(
            path="web.upload_dir",
            level=FindingLevel.ERROR,
            message="Directory does not exist"
        )

        assert finding.path == "web.upload_dir"
        assert finding.level == FindingLevel.ERROR
        assert finding.message == "Directory does not exist"
        assert finding.suggestion is None
        assert finding.code is None
        assert finding.config_path is None

    def test_finding_creation_complete(self):
        """Test creating a Finding with all fields."""
        finding = Finding(
            path="tasks.cleanup.module",
            level=FindingLevel.WARNING,
            message="Module not found in Python path",
            suggestion="Add module to PYTHONPATH or install package",
            code="import-error",
            config_path="/path/to/config.yaml"
        )

        assert finding.path == "tasks.cleanup.module"
        assert finding.level == FindingLevel.WARNING
        assert finding.message == "Module not found in Python path"
        assert finding.suggestion == "Add module to PYTHONPATH or install package"
        assert finding.code == "import-error"
        assert finding.config_path == "/path/to/config.yaml"

    def test_finding_slots_optimization(self):
        """Test that Finding uses slots for memory optimization."""
        finding = Finding(
            path="test.path",
            level=FindingLevel.INFO,
            message="Test message"
        )

        # Should not be able to add arbitrary attributes due to slots
        try:
            finding.arbitrary_attr = "test"  # type: ignore[attr-defined]
            assert False, "Should not be able to add arbitrary attributes with slots"
        except AttributeError:
            pass  # Expected behavior


class TestValidationReporter:
    """Test cases for ValidationReporter class functionality."""

    def test_reporter_initialization_default(self):
        """Test ValidationReporter initialization with default values."""
        reporter = ValidationReporter()

        assert reporter.output_format == "text"
        assert reporter.output_file == sys.stdout
        assert reporter.show_suggestions is True
        assert len(reporter.findings) == 0

    def test_reporter_initialization_custom(self):
        """Test ValidationReporter initialization with custom values."""
        output = StringIO()
        reporter = ValidationReporter(
            output_format="json",
            output_file=output,
            show_suggestions=False
        )

        assert reporter.output_format == "json"
        assert reporter.output_file == output
        assert reporter.show_suggestions is False

    def test_add_finding_method(self):
        """Test adding findings using the add_finding method."""
        reporter = ValidationReporter()

        reporter.add_finding(
            path="web.upload_dir",
            level=FindingLevel.ERROR,
            message="Directory not found",
            suggestion="Create the directory or fix the path",
            code="path-not-found",
            config_path="/app/config.yaml"
        )

        assert len(reporter.findings) == 1
        finding = reporter.findings[0]
        assert finding.path == "web.upload_dir"
        assert finding.level == FindingLevel.ERROR
        assert finding.message == "Directory not found"
        assert finding.suggestion == "Create the directory or fix the path"
        assert finding.code == "path-not-found"
        assert finding.config_path == "/app/config.yaml"

    def test_add_validation_result_method(self):
        """Test adding findings from ValidationResult-like object."""
        from types import SimpleNamespace

        # Create mock ValidationResult-like object
        result = SimpleNamespace()
        result.errors = [
            SimpleNamespace(path="web.upload_dir", message="Directory not found", code="path-error"),
            SimpleNamespace(path="tasks.cleanup", message="Module missing", code="import-error")
        ]
        result.warnings = [
            SimpleNamespace(path="web.port", message="Non-standard port", code="config-warning")
        ]

        reporter = ValidationReporter()
        reporter.add_validation_result(result, config_path="/app/config.yaml")

        assert len(reporter.findings) == 3

        # Check errors were added as ERROR level
        error_findings = [f for f in reporter.findings if f.level == FindingLevel.ERROR]
        assert len(error_findings) == 2
        assert error_findings[0].path == "web.upload_dir"
        assert error_findings[1].path == "tasks.cleanup"

        # Check warnings were added as WARNING level
        warning_findings = [f for f in reporter.findings if f.level == FindingLevel.WARNING]
        assert len(warning_findings) == 1
        assert warning_findings[0].path == "web.port"

    def test_text_format_output_empty(self):
        """Test text format output with no findings."""
        reporter = ValidationReporter(output_format="text")

        report = reporter.generate_report()
        assert "Validation passed with no issues found." in report

    def test_text_format_output_grouped(self):
        """Test text format output with findings grouped by level."""
        reporter = ValidationReporter(output_format="text")

        # Add findings of different levels
        reporter.add_finding("error.path", FindingLevel.ERROR, "Error message", "Error suggestion")
        reporter.add_finding("warning.path", FindingLevel.WARNING, "Warning message", "Warning suggestion")
        reporter.add_finding("info.path", FindingLevel.INFO, "Info message", "Info suggestion")
        reporter.add_finding("another.error", FindingLevel.ERROR, "Another error", "Another suggestion")

        report = reporter.generate_report()

        # Check that sections are properly grouped
        assert "ERRORS:" in report
        assert "WARNINGS:" in report
        assert "INFOS:" in report

        # Check that findings appear under correct sections
        assert "[ERROR] error.path: Error message" in report
        assert "[WARNING] warning.path: Warning message" in report
        assert "[INFO] info.path: Info message" in report
        assert "[ERROR] another.error: Another error" in report

        # Check that suggestions are included
        assert "Suggestion: Error suggestion" in report
        assert "Suggestion: Warning suggestion" in report
        assert "Suggestion: Info suggestion" in report

    def test_text_format_output_no_suggestions(self):
        """Test text format output when suggestions are disabled."""
        reporter = ValidationReporter(output_format="text", show_suggestions=False)

        reporter.add_finding("test.path", FindingLevel.ERROR, "Error message", "This suggestion should not appear")

        report = reporter.generate_report()

        assert "[ERROR] test.path: Error message" in report
        assert "Suggestion:" not in report

    def test_json_format_output_structure(self):
        """Test JSON format output structure."""
        reporter = ValidationReporter(output_format="json")

        reporter.add_finding(
            path="web.upload_dir",
            level=FindingLevel.ERROR,
            message="Directory not found",
            suggestion="Create directory",
            code="path-error",
            config_path="/app/config.yaml"
        )

        report = reporter.generate_report()
        report_data = json.loads(report)

        # Check top-level structure
        assert "status" in report_data
        assert "summary" in report_data
        assert "exit_code" in report_data
        assert "findings" in report_data

        # Check status and exit code
        assert report_data["status"] == "invalid"
        assert report_data["exit_code"] == 1

        # Check summary statistics
        summary = report_data["summary"]
        assert summary["total"] == 1
        assert summary["errors"] == 1
        assert summary["warnings"] == 0
        assert summary["info"] == 0

        # Check findings array
        findings = report_data["findings"]
        assert len(findings) == 1

        finding = findings[0]
        assert finding["path"] == "web.upload_dir"
        assert finding["level"] == "ERROR"
        assert finding["message"] == "Directory not found"
        assert finding["suggestion"] == "Create directory"
        assert finding["code"] == "path-error"
        assert finding["config_path"] == "/app/config.yaml"

    def test_json_format_output_no_suggestions(self):
        """Test JSON format output when suggestions are disabled."""
        reporter = ValidationReporter(output_format="json", show_suggestions=False)

        reporter.add_finding(
            path="test.path",
            level=FindingLevel.WARNING,
            message="Warning message",
            suggestion="This should not appear"
        )

        report = reporter.generate_report()
        report_data = json.loads(report)

        finding = report_data["findings"][0]
        assert "suggestion" not in finding

    def test_json_format_output_mixed_levels(self):
        """Test JSON format output with mixed finding levels."""
        reporter = ValidationReporter(output_format="json")

        reporter.add_finding("error.path", FindingLevel.ERROR, "Error message")
        reporter.add_finding("warning.path", FindingLevel.WARNING, "Warning message")
        reporter.add_finding("info.path", FindingLevel.INFO, "Info message")

        report = reporter.generate_report()
        report_data = json.loads(report)

        # Check status determination (should be invalid due to error)
        assert report_data["status"] == "invalid"
        assert report_data["exit_code"] == 1

        # Check summary
        summary = report_data["summary"]
        assert summary["total"] == 3
        assert summary["errors"] == 1
        assert summary["warnings"] == 1
        assert summary["info"] == 1

    def test_json_format_output_warnings_only(self):
        """Test JSON format output with warnings only (no errors)."""
        reporter = ValidationReporter(output_format="json")

        reporter.add_finding("warning.path", FindingLevel.WARNING, "Warning message")
        reporter.add_finding("info.path", FindingLevel.INFO, "Info message")

        report = reporter.generate_report()
        report_data = json.loads(report)

        # Check status determination (should be warning due to no errors)
        assert report_data["status"] == "warning"
        assert report_data["exit_code"] == 2

        # Check summary
        summary = report_data["summary"]
        assert summary["total"] == 2
        assert summary["errors"] == 0
        assert summary["warnings"] == 1
        assert summary["info"] == 1

    def test_json_format_output_valid(self):
        """Test JSON format output with no findings."""
        reporter = ValidationReporter(output_format="json")

        report = reporter.generate_report()
        report_data = json.loads(report)

        # Check status determination (should be valid with no findings)
        assert report_data["status"] == "valid"
        assert report_data["exit_code"] == 0

        # Check summary
        summary = report_data["summary"]
        assert summary["total"] == 0
        assert summary["errors"] == 0
        assert summary["warnings"] == 0
        assert summary["info"] == 0

        # Check empty findings array
        assert report_data["findings"] == []

    def test_generate_summary_method(self):
        """Test the generate_summary method."""
        reporter = ValidationReporter()

        # Test with no findings
        summary = reporter.generate_summary()
        assert "Validation passed with no issues found." in summary

        # Test with mixed findings
        reporter.add_finding("error.path", FindingLevel.ERROR, "Error message")
        reporter.add_finding("warning.path", FindingLevel.WARNING, "Warning message")
        reporter.add_finding("info.path", FindingLevel.INFO, "Info message")

        summary = reporter.generate_summary()
        assert summary == "Validation failed with 1 error, 1 warning, 1 info message."

    def test_determine_exit_code_method(self):
        """Test the determine_exit_code method."""
        reporter = ValidationReporter()

        # Test with no findings
        assert reporter.determine_exit_code() == 0

        # Test with errors
        reporter.add_finding("error.path", FindingLevel.ERROR, "Error message")
        assert reporter.determine_exit_code() == 1

        # Test with warnings only (should return 2)
        reporter.clear_findings()
        reporter.add_finding("warning.path", FindingLevel.WARNING, "Warning message")
        assert reporter.determine_exit_code() == 2

        # Test with info only (should return 0)
        reporter.clear_findings()
        reporter.add_finding("info.path", FindingLevel.INFO, "Info message")
        assert reporter.determine_exit_code() == 0

        # Test with errors and warnings (should return 1 due to errors)
        reporter.add_finding("error.path", FindingLevel.ERROR, "Error message")
        assert reporter.determine_exit_code() == 1

    def test_has_findings_method(self):
        """Test the has_findings method."""
        reporter = ValidationReporter()

        # Test with no findings
        assert reporter.has_findings() is False
        assert reporter.has_findings(FindingLevel.ERROR) is False

        # Add some findings
        reporter.add_finding("error.path", FindingLevel.ERROR, "Error message")
        reporter.add_finding("warning.path", FindingLevel.WARNING, "Warning message")

        # Test general check
        assert reporter.has_findings() is True

        # Test level-specific checks
        assert reporter.has_findings(FindingLevel.ERROR) is True
        assert reporter.has_findings(FindingLevel.WARNING) is True
        assert reporter.has_findings(FindingLevel.INFO) is False

    def test_print_report_method(self):
        """Test the print_report method."""
        reporter = ValidationReporter(output_format="text")
        reporter.add_finding("test.path", FindingLevel.ERROR, "Test error")

        output = StringIO()
        reporter.output_file = output

        reporter.print_report()

        report_content = output.getvalue()
        assert "[ERROR] test.path: Test error" in report_content

    def test_clear_findings_method(self):
        """Test the clear_findings method."""
        reporter = ValidationReporter()

        reporter.add_finding("error.path", FindingLevel.ERROR, "Error message")
        reporter.add_finding("warning.path", FindingLevel.WARNING, "Warning message")

        assert len(reporter.findings) == 2

        reporter.clear_findings()

        assert len(reporter.findings) == 0
        assert reporter.has_findings() is False


class TestIntegration:
    """Integration tests for the complete reporting system."""

    def test_end_to_end_text_format(self):
        """Test complete workflow with text format output."""
        output = StringIO()
        reporter = ValidationReporter(output_format="text", output_file=output)

        # Add various findings
        reporter.add_finding(
            path="web.upload_dir",
            level=FindingLevel.ERROR,
            message="Directory '/uploads' does not exist",
            suggestion="Create the directory or update the path in config",
            code="path-not-found"
        )
        reporter.add_finding(
            path="tasks.cleanup.module",
            level=FindingLevel.WARNING,
            message="Module 'old_module' not found in Python path",
            suggestion="Install the module or update the module reference",
            code="import-warning"
        )

        # Generate and capture report
        reporter.print_report()
        report_content = output.getvalue()

        # Verify structure and content
        assert "ERRORS:" in report_content
        assert "WARNINGS:" in report_content
        assert "[ERROR] web.upload_dir: Directory '/uploads' does not exist" in report_content
        assert "[WARNING] tasks.cleanup.module: Module 'old_module' not found in Python path" in report_content
        assert "Suggestion: Create the directory or update the path in config" in report_content
        assert "Suggestion: Install the module or update the module reference" in report_content
        assert "Validation failed with 1 error, 1 warning, 0 info messages." in report_content

    def test_end_to_end_json_format(self):
        """Test complete workflow with JSON format output."""
        output = StringIO()
        reporter = ValidationReporter(output_format="json", output_file=output)

        # Add findings
        reporter.add_finding(
            path="config.watch_folder.dir",
            level=FindingLevel.ERROR,
            message="Watch directory does not exist",
            suggestion="Create directory or fix path",
            code="missing-dir",
            config_path="config.yaml"
        )

        # Generate report
        reporter.print_report()
        report_content = output.getvalue()

        # Parse and verify JSON structure
        report_data = json.loads(report_content)

        assert report_data["status"] == "invalid"
        assert report_data["exit_code"] == 1
        assert report_data["summary"]["total"] == 1
        assert report_data["summary"]["errors"] == 1
        assert report_data["summary"]["warnings"] == 0
        assert report_data["summary"]["info"] == 0

        finding = report_data["findings"][0]
        assert finding["path"] == "config.watch_folder.dir"
        assert finding["level"] == "ERROR"
        assert finding["message"] == "Watch directory does not exist"
        assert finding["suggestion"] == "Create directory or fix path"
        assert finding["code"] == "missing-dir"
        assert finding["config_path"] == "config.yaml"



