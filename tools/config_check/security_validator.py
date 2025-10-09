"""
Security validation for configuration files.

This module provides security analysis capabilities for the config-check tool,
identifying potential security vulnerabilities in configuration files before
deployment. It focuses on path traversal vulnerabilities, insecure file paths,
and directory security issues.

Key Features:
- Path traversal vulnerability detection with configurable patterns
- Directory security validation for upload and watch folders
- Task-specific path parameter security analysis
- Security remediation recommendations with severity levels
- Integration with existing validation pipeline

Classes:
    SecurityIssue: Represents a security-related validation issue
    SecurityAnalysisResult: Aggregated security analysis results
    SecurityValidator: Main security analysis engine

Security Checks:
- Path traversal patterns: ../, ..\\, .., ~, $ and other dangerous patterns
- Absolute vs relative path validation
- Directory boundary validation
- File path sanitization checks
- Task parameter security validation
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SecurityIssue:
    """Represents a security-related validation issue."""

    path: str
    message: str
    code: str
    severity: str = "warning"  # "info", "warning", "error"
    details: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class SecurityAnalysisResult:
    """Aggregated security analysis results."""

    errors: List[SecurityIssue]
    warnings: List[SecurityIssue]
    info: List[SecurityIssue]

    def __init__(self) -> None:
        self.errors = []
        self.warnings = []
        self.info = []

    def add_issue(self, issue: SecurityIssue) -> None:
        """Add an issue to the appropriate severity list."""
        if issue.severity == "error":
            self.errors.append(issue)
        elif issue.severity == "warning":
            self.warnings.append(issue)
        else:
            self.info.append(issue)

    @property
    def all_issues(self) -> List[SecurityIssue]:
        """Get all issues regardless of severity."""
        return self.errors + self.warnings + self.info


class SecurityValidator:
    """Validates configuration for security issues."""

    # Dangerous path patterns that could indicate path traversal vulnerabilities
    DANGEROUS_PATH_PATTERNS = {
        "../",      # Unix path traversal
        "..\\",     # Windows path traversal
        "..",       # Generic parent directory reference
        "~",        # Home directory reference
        "$",        # Environment variable reference
        "%",        # Windows environment variable reference
        "|",        # Command injection potential
        ";",        # Command separator
        "&",        # Command separator
        "`",        # Command substitution
        "$(",       # Command substitution
        "${",       # Variable substitution
    }

    # Additional suspicious patterns
    SUSPICIOUS_PATTERNS = {
        "/etc/",    # Unix system directory
        "/var/",    # Unix variable directory
        "/tmp/",    # Unix temporary directory
        "C:\\Windows\\",  # Windows system directory
        "C:\\Program Files\\",  # Windows program directory
        "\\\\",     # UNC path indicator
        "//",       # Double slash (potential protocol confusion)
    }

    # Path parameters commonly found in task configurations
    PATH_PARAMETERS = {
        "data_dir", "files_dir", "reference_file", "processing_dir",
        "archive_dir", "upload_dir", "dir", "filename", "output_dir",
        "input_dir", "temp_dir", "log_dir", "backup_dir"
    }

    def __init__(self) -> None:
        self.logger = logger.getChild(self.__class__.__name__)

    def validate_security(self, config: Dict[str, Any]) -> SecurityAnalysisResult:
        """Validate configuration for security issues."""
        self.logger.debug("Starting security validation analysis")
        result = SecurityAnalysisResult()

        # Validate file path security
        path_issues = self._validate_path_security(config)
        for issue in path_issues:
            result.add_issue(issue)

        # Validate directory configurations
        directory_issues = self._validate_directory_security(config)
        for issue in directory_issues:
            result.add_issue(issue)

        # Validate task-specific security
        task_issues = self._validate_task_security(config)
        for issue in task_issues:
            result.add_issue(issue)

        self.logger.debug(
            "Security analysis complete: %d errors, %d warnings, %d info",
            len(result.errors),
            len(result.warnings),
            len(result.info)
        )

        return result

    def _validate_path_security(self, config: Dict[str, Any]) -> List[SecurityIssue]:
        """Validate file paths for security issues."""
        issues: List[SecurityIssue] = []

        # Check web upload directory
        web_config = config.get("web", {})
        upload_dir = web_config.get("upload_dir", "")
        if upload_dir:
            path_issues = self._analyze_path_security(
                "web.upload_dir", upload_dir, "upload directory"
            )
            issues.extend(path_issues)

        # Check watch folder directory
        watch_config = config.get("watch_folder", {})
        watch_dir = watch_config.get("dir", "")
        if watch_dir:
            path_issues = self._analyze_path_security(
                "watch_folder.dir", watch_dir, "watch directory"
            )
            issues.extend(path_issues)

        # Check processing directory
        processing_dir = watch_config.get("processing_dir", "")
        if processing_dir:
            path_issues = self._analyze_path_security(
                "watch_folder.processing_dir", processing_dir, "processing directory"
            )
            issues.extend(path_issues)

        return issues

    def _validate_directory_security(self, config: Dict[str, Any]) -> List[SecurityIssue]:
        """Validate directory configurations for security issues."""
        issues: List[SecurityIssue] = []

        # Check for world-writable directories (if we can determine permissions)
        directories_to_check = []
        
        # Collect directory paths from configuration
        web_config = config.get("web", {})
        if web_config.get("upload_dir"):
            directories_to_check.append(("web.upload_dir", web_config["upload_dir"]))

        watch_config = config.get("watch_folder", {})
        if watch_config.get("dir"):
            directories_to_check.append(("watch_folder.dir", watch_config["dir"]))

        # Check directory security properties
        for config_path, directory_path in directories_to_check:
            dir_issues = self._analyze_directory_permissions(config_path, directory_path)
            issues.extend(dir_issues)

        return issues

    def _validate_task_security(self, config: Dict[str, Any]) -> List[SecurityIssue]:
        """Validate task-specific paths for security issues."""
        issues: List[SecurityIssue] = []
        tasks = config.get("tasks", {})

        for task_name, task_config in tasks.items():
            if not isinstance(task_config, dict):
                continue

            params = task_config.get("params", {})
            if not isinstance(params, dict):
                continue

            # Check common path parameters
            for param_name in self.PATH_PARAMETERS:
                if param_name in params:
                    param_value = params[param_name]
                    if isinstance(param_value, str) and param_value:
                        path_issues = self._analyze_path_security(
                            f"tasks.{task_name}.params.{param_name}",
                            param_value,
                            f"task parameter '{param_name}'"
                        )
                        issues.extend(path_issues)

            # Check nested storage parameters
            storage_config = params.get("storage", {})
            if isinstance(storage_config, dict):
                for storage_param in ["data_dir", "filename"]:
                    if storage_param in storage_config:
                        param_value = storage_config[storage_param]
                        if isinstance(param_value, str) and param_value:
                            path_issues = self._analyze_path_security(
                                f"tasks.{task_name}.params.storage.{storage_param}",
                                param_value,
                                f"storage parameter '{storage_param}'"
                            )
                            issues.extend(path_issues)

        return issues

    def _analyze_path_security(self, config_path: str, path_value: str, description: str) -> List[SecurityIssue]:
        """Analyze a single path for security issues."""
        issues: List[SecurityIssue] = []

        # Check for dangerous path traversal patterns
        dangerous_patterns = self._find_dangerous_patterns(path_value)
        if dangerous_patterns:
            severity = "error" if any(p in ["../", "..\\", ".."] for p in dangerous_patterns) else "warning"
            issues.append(SecurityIssue(
                path=config_path,
                message=f"{description.capitalize()} path '{path_value}' contains potentially dangerous patterns: {', '.join(dangerous_patterns)}. "
                       f"This may be vulnerable to path traversal attacks.",
                code="security-path-traversal-risk",
                severity=severity,
                details={
                    "path": path_value,
                    "dangerous_patterns": list(dangerous_patterns),
                    "description": description
                }
            ))

        # Check for suspicious system paths
        suspicious_patterns = self._find_suspicious_patterns(path_value)
        if suspicious_patterns:
            issues.append(SecurityIssue(
                path=config_path,
                message=f"{description.capitalize()} path '{path_value}' references system directories: {', '.join(suspicious_patterns)}. "
                       f"Ensure this is intentional and properly secured.",
                code="security-suspicious-system-path",
                severity="warning",
                details={
                    "path": path_value,
                    "suspicious_patterns": list(suspicious_patterns),
                    "description": description
                }
            ))

        # Check for absolute vs relative path security implications
        if os.path.isabs(path_value):
            # Absolute paths can be more secure but need validation
            if self._is_potentially_unsafe_absolute_path(path_value):
                issues.append(SecurityIssue(
                    path=config_path,
                    message=f"{description.capitalize()} uses absolute path '{path_value}' that may pose security risks. "
                           f"Ensure the path is within expected boundaries.",
                    code="security-unsafe-absolute-path",
                    severity="info",
                    details={
                        "path": path_value,
                        "description": description,
                        "is_absolute": True
                    }
                ))
        else:
            # Relative paths need careful handling
            if self._is_potentially_unsafe_relative_path(path_value):
                issues.append(SecurityIssue(
                    path=config_path,
                    message=f"{description.capitalize()} uses relative path '{path_value}' that may escape intended boundaries. "
                           f"Consider using absolute paths or additional validation.",
                    code="security-unsafe-relative-path",
                    severity="warning",
                    details={
                        "path": path_value,
                        "description": description,
                        "is_absolute": False
                    }
                ))

        return issues

    def _analyze_directory_permissions(self, config_path: str, directory_path: str) -> List[SecurityIssue]:
        """Analyze directory permissions for security issues."""
        issues: List[SecurityIssue] = []

        try:
            # Try to resolve the path to check if it exists
            resolved_path = Path(directory_path).resolve()
            
            # Check if directory exists and we can analyze it
            if resolved_path.exists() and resolved_path.is_dir():
                # On Windows, we have limited permission checking capabilities
                # But we can still check for some basic security issues
                
                # Check if the directory is in a potentially unsafe location
                path_str = str(resolved_path).lower()
                
                # Check for directories in system locations
                unsafe_locations = [
                    "c:\\windows\\temp",
                    "c:\\temp",
                    "/tmp",
                    "/var/tmp"
                ]
                
                for unsafe_location in unsafe_locations:
                    if unsafe_location in path_str:
                        issues.append(SecurityIssue(
                            path=config_path,
                            message=f"Directory '{directory_path}' is located in a potentially unsafe system location. "
                                   f"Consider using a more secure location.",
                            code="security-unsafe-directory-location",
                            severity="warning",
                            details={
                                "path": directory_path,
                                "resolved_path": str(resolved_path),
                                "unsafe_location": unsafe_location
                            }
                        ))
                        break

        except (OSError, ValueError) as e:
            # If we can't analyze the directory, note it as an info item
            issues.append(SecurityIssue(
                path=config_path,
                message=f"Could not analyze directory security for '{directory_path}': {e}. "
                       f"Ensure the directory exists and is accessible.",
                code="security-directory-analysis-failed",
                severity="info",
                details={
                    "path": directory_path,
                    "error": str(e)
                }
            ))

        return issues

    def _find_dangerous_patterns(self, path: str) -> Set[str]:
        """Find dangerous patterns in a path string."""
        found_patterns = set()
        path_lower = path.lower()
        
        for pattern in self.DANGEROUS_PATH_PATTERNS:
            if pattern.lower() in path_lower:
                found_patterns.add(pattern)
        
        return found_patterns

    def _find_suspicious_patterns(self, path: str) -> Set[str]:
        """Find suspicious system path patterns."""
        found_patterns = set()
        path_lower = path.lower()
        
        for pattern in self.SUSPICIOUS_PATTERNS:
            if pattern.lower() in path_lower:
                found_patterns.add(pattern)
        
        return found_patterns

    def _is_potentially_unsafe_absolute_path(self, path: str) -> bool:
        """Check if an absolute path is potentially unsafe."""
        path_lower = path.lower()
        
        # Check for system directories that should generally be avoided
        unsafe_absolute_patterns = [
            "c:\\windows\\",
            "c:\\program files\\",
            "/etc/",
            "/var/",
            "/usr/",
            "/bin/",
            "/sbin/"
        ]
        
        return any(pattern in path_lower for pattern in unsafe_absolute_patterns)

    def _is_potentially_unsafe_relative_path(self, path: str) -> bool:
        """Check if a relative path is potentially unsafe."""
        # Relative paths with parent directory references are risky
        return ".." in path or path.startswith("/") or path.startswith("\\")


def validate_security(config: Dict[str, Any]) -> SecurityAnalysisResult:
    """Convenience function to validate configuration security."""
    validator = SecurityValidator()
    return validator.validate_security(config)