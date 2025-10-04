"""Output formatting and structured error reporting for config validation.

This module provides comprehensive output formatting and structured error reporting for
configuration validation results, supporting both human-readable text and machine-readable
JSON formats with detailed findings and actionable suggestions.

The reporter system supports multiple output formats and severity levels:
- ERROR: Critical issues that prevent configuration usage
- WARNING: Non-critical issues that should be reviewed
- INFO: Informational messages for configuration insights

Key Features:
- Multiple output formats (text, JSON) for different use cases
- Structured finding categorization with severity levels
- Actionable suggestions for fixing configuration issues
- Windows-compatible output with proper encoding handling
- Configurable output destinations (stdout, files)
- Comprehensive summary statistics and exit code determination
- Integration with validation result objects from all validator modules

Classes:
    FindingLevel: Enumeration of severity levels for validation findings
    Finding: Individual validation finding with context and suggestions
    ValidationReporter: Main reporting engine with multiple output formats

Output Formats:
    - Text: Human-readable format with grouped findings and suggestions
    - JSON: Machine-readable format for integration with other tools
    - Structured error reporting with consistent formatting

Windows Compatibility:
    - UTF-8 encoding support for international characters
    - Windows-compatible line endings and path display
    - Proper handling of Windows file paths in error messages
    - Console output compatible with Windows terminals

Exit Codes:
    - 0: No issues found (success)
    - 1: Errors found (critical issues)
    - 2: Warnings only (non-critical issues)

Note:
    The reporter integrates with all validation modules and provides
    consistent formatting across different types of validation findings.
    Suggestions are included by default to help users fix configuration issues.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO


class FindingLevel(Enum):
    """Categorization levels for validation findings."""
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(slots=True)
class Finding:
    """Represents a single validation finding with context and suggestions."""

    path: str
    """Configuration path where the finding was detected (e.g., 'web.upload_dir')"""

    level: FindingLevel
    """Severity level of the finding"""

    message: str
    """Human-readable description of the issue"""

    suggestion: Optional[str] = None
    """Actionable suggestion for fixing the issue"""

    code: Optional[str] = None
    """Error code for programmatic handling"""

    config_path: Optional[str] = None
    """Path to the configuration file where the finding was detected"""


class ValidationReporter:
    """Handles structured output formatting for validation results."""

    def __init__(
        self,
        output_format: str = "text",
        output_file: Optional[TextIO] = None,
        show_suggestions: bool = True
    ) -> None:
        """
        Initialize the validation reporter.

        Args:
            output_format: Output format ('text' or 'json')
            output_file: Optional file to write output to (defaults to stdout)
            show_suggestions: Whether to include suggestions in output
        """
        self.output_format = output_format
        self.output_file = output_file or sys.stdout
        self.show_suggestions = show_suggestions
        self.findings: List[Finding] = []

    def add_finding(
        self,
        path: str,
        level: FindingLevel,
        message: str,
        suggestion: Optional[str] = None,
        code: Optional[str] = None,
        config_path: Optional[str] = None
    ) -> None:
        """
        Add a finding to the report.

        Args:
            path: Configuration path where finding was detected
            level: Severity level of the finding
            message: Human-readable description
            suggestion: Optional actionable suggestion
            code: Optional error code
            config_path: Optional path to config file
        """
        finding = Finding(
            path=path,
            level=level,
            message=message,
            suggestion=suggestion,
            code=code,
            config_path=config_path
        )
        self.findings.append(finding)

    def add_validation_result(self, result, config_path: Optional[str] = None) -> None:
        """
        Add findings from a ValidationResult object.

        Args:
            result: ValidationResult object with errors and warnings
            config_path: Path to the configuration file
        """
        # Add errors as ERROR level findings
        for error in result.errors:
            self.add_finding(
                path=error.path,
                level=FindingLevel.ERROR,
                message=error.message,
                suggestion=getattr(error, "suggestion", None),
                code=getattr(error, "code", None),
                config_path=config_path
            )

        # Add warnings as WARNING level findings
        for warning in result.warnings:
            self.add_finding(
                path=warning.path,
                level=FindingLevel.WARNING,
                message=warning.message,
                suggestion=getattr(warning, "suggestion", None),
                code=getattr(warning, "code", None),
                config_path=config_path
            )

    def generate_report(self) -> str:
        """
        Generate the complete validation report.

        Returns:
            Formatted report string
        """
        if self.output_format == "json":
            return self._generate_json_report()
        else:
            return self._generate_text_report()

    def _generate_text_report(self) -> str:
        """Generate human-readable text report."""
        if not self.findings:
            return "Validation passed with no issues found.\n"

        grouped_findings = self._group_findings_by_level()
        report_lines: list[str] = []

        for level in [FindingLevel.ERROR, FindingLevel.WARNING, FindingLevel.INFO]:
            findings = grouped_findings.get(level, [])
            if not findings:
                continue

            if report_lines:
                report_lines.append("")

            level_name = level.value
            report_lines.append(f"{level_name}S:")
            report_lines.append("=" * len(level_name + "S:"))

            for finding in findings:
                report_lines.append(f"  [{level.value}] {finding.path}: {finding.message}")

                if self.show_suggestions and finding.suggestion:
                    report_lines.append(f"    Suggestion: {finding.suggestion}")

        summary = self.generate_summary()
        report_lines.append("")
        report_lines.append(summary)

        return "\n".join(report_lines)

    def _generate_json_report(self) -> str:
        """Generate machine-readable JSON report."""
        # Group findings by level for summary
        grouped_findings = self._group_findings_by_level()

        # Convert findings to dictionaries
        findings_data = []
        for finding in self.findings:
            finding_dict = {
                "path": finding.path,
                "level": finding.level.value,
                "message": finding.message,
                "code": finding.code,
                "config_path": finding.config_path
            }
            if self.show_suggestions and finding.suggestion:
                finding_dict["suggestion"] = finding.suggestion
            findings_data.append(finding_dict)

        # Create summary statistics
        summary_stats = {
            "total": len(self.findings),
            "errors": len(grouped_findings.get(FindingLevel.ERROR, [])),
            "warnings": len(grouped_findings.get(FindingLevel.WARNING, [])),
            "info": len(grouped_findings.get(FindingLevel.INFO, []))
        }

        # Determine overall status
        status = "valid"
        if summary_stats["errors"] > 0:
            status = "invalid"
        elif summary_stats["warnings"] > 0:
            status = "warning"

        # Create complete report
        report_data = {
            "status": status,
            "summary": summary_stats,
            "exit_code": self.determine_exit_code(),
            "findings": findings_data
        }

        return json.dumps(report_data, indent=2)

    def _group_findings_by_level(self) -> Dict[FindingLevel, List[Finding]]:
        """Group findings by their level for organized reporting."""
        grouped = {
            FindingLevel.ERROR: [],
            FindingLevel.WARNING: [],
            FindingLevel.INFO: []
        }

        for finding in self.findings:
            grouped[finding.level].append(finding)

        return grouped

    def generate_summary(self) -> str:
        """Generate summary statistics string."""
        if not self.findings:
            return "Validation passed with no issues found."

        grouped_findings = self._group_findings_by_level()
        errors = len(grouped_findings[FindingLevel.ERROR])
        warnings = len(grouped_findings[FindingLevel.WARNING])
        info = len(grouped_findings[FindingLevel.INFO])

        def _plural(count: int, noun: str) -> str:
            suffix = "" if count == 1 else "s"
            return f"{count} {noun}{suffix}"

        if errors > 0:
            return (
                "Validation failed with "
                f"{_plural(errors, 'error')}, "
                f"{_plural(warnings, 'warning')}, "
                f"{_plural(info, 'info message')}."
            )

        if warnings > 0:
            return (
                "Validation passed with "
                f"{_plural(errors, 'error')}, "
                f"{_plural(warnings, 'warning')}, "
                f"{_plural(info, 'info message')}."
            )

        return (
            "Validation passed with "
            f"{_plural(errors, 'error')}, "
            f"{_plural(warnings, 'warning')}, "
            f"{_plural(info, 'info message')}."
        )

    def determine_exit_code(self) -> int:
        """
        Determine appropriate exit code based on findings.

        Returns:
            Exit code: 0=none, 1=errors, 2=warnings-only
        """
        grouped_findings = self._group_findings_by_level()

        if grouped_findings[FindingLevel.ERROR]:
            return 1  # Errors found
        elif grouped_findings[FindingLevel.WARNING]:
            return 2  # Warnings only
        else:
            return 0  # No issues

    def print_report(self) -> None:
        """Print the report to the configured output file."""
        report = self.generate_report()
        print(report, file=self.output_file)

    def has_findings(self, level: Optional[FindingLevel] = None) -> bool:
        """
        Check if there are any findings, optionally filtered by level.

        Args:
            level: Optional level to filter by

        Returns:
            True if findings exist (for the specified level if provided)
        """
        if level is None:
            return len(self.findings) > 0
        else:
            return any(f.level == level for f in self.findings)

    def clear_findings(self) -> None:
        """Clear all findings from the reporter."""
        self.findings.clear()