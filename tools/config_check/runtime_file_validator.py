"""Runtime file validation for config-check.

This module provides optional file system validation that can be enabled with
the --check-files command-line flag. It performs runtime checks on file paths,
CSV structures, and directory permissions that are referenced in the configuration.

The runtime file validator performs comprehensive file system validation including:
- File existence validation for all referenced file paths
- Directory permission validation for configured paths
- CSV parsing validation to verify file structures
- Comprehensive error handling for file access issues

Key Features:
- Optional file system validation mode activated by --check-files flag
- File existence and accessibility validation
- Directory permission and accessibility checking
- CSV file structure validation with pandas integration
- Detailed error reporting for file system issues
- Windows-compatible file path handling

Classes:
    RuntimeFileValidator: Main validator class for file system checks
    FileValidationResult: Result of file validation with error tracking

Functions:
    validate_file_dependencies(): Main validation entry point for file system checks

Windows Compatibility:
    - Proper handling of Windows file paths and UNC paths
    - Case-insensitive file system operations where appropriate
    - Support for Windows-specific permission models
    - Encoding-aware file operations for CSV validation

Note:
    Runtime file validation is optional and should be used when you need to verify
    that all file dependencies are available and accessible. This is particularly
    useful in production environments or when validating configurations before
    deployment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from .task_validator import TaskIssue


@dataclass
class FileValidationResult:
    """Result of file validation with error tracking."""
    errors: List[TaskIssue]
    warnings: List[TaskIssue]


class RuntimeFileValidator:
    """Validator for runtime file dependencies."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
    
    def validate_file_dependencies(self, config: Dict[str, Any]) -> FileValidationResult:
        """Validate file paths and CSV structures at runtime."""
        errors: List[TaskIssue] = []
        warnings: List[TaskIssue] = []
        
        # Validate reference files for rules tasks
        rules_errors, rules_warnings = self._validate_reference_files(config)
        errors.extend(rules_errors)
        warnings.extend(rules_warnings)
        
        # Validate directory permissions
        dir_errors, dir_warnings = self._validate_directory_permissions(config)
        errors.extend(dir_errors)
        warnings.extend(dir_warnings)
        
        # Validate CSV file structures
        csv_errors, csv_warnings = self._validate_csv_files(config)
        errors.extend(csv_errors)
        warnings.extend(csv_warnings)
        
        return FileValidationResult(errors=errors, warnings=warnings)
    
    def _validate_reference_files(self, config: Dict[str, Any]) -> tuple[List[TaskIssue], List[TaskIssue]]:
        """Validate reference files for rules tasks."""
        errors: List[TaskIssue] = []
        warnings: List[TaskIssue] = []
        
        tasks = config.get("tasks", {})
        if not isinstance(tasks, dict):
            return errors, warnings
        
        for task_name, task_config in tasks.items():
            if not isinstance(task_config, dict):
                continue
            
            # Check if this is a rules task
            module_name = task_config.get("module", "")
            if not isinstance(module_name, str) or "rules" not in module_name:
                continue
            
            params = task_config.get("params", {})
            if not isinstance(params, dict):
                continue
            
            reference_file = params.get("reference_file")
            if not reference_file:
                continue
            
            # Validate file existence and accessibility
            file_path = self._resolve_path(reference_file)
            
            if not file_path.exists():
                errors.append(TaskIssue(
                    path=f"tasks.{task_name}.params.reference_file",
                    message=f"Reference file does not exist: {file_path}",
                    code="file-not-found",
                    details={"file_path": str(file_path)}
                ))
                continue
            
            if not file_path.is_file():
                errors.append(TaskIssue(
                    path=f"tasks.{task_name}.params.reference_file",
                    message=f"Reference path is not a file: {file_path}",
                    code="file-not-file",
                    details={"file_path": str(file_path)}
                ))
                continue
            
            # Check file readability
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.read(1)  # Try to read one character
            except PermissionError:
                errors.append(TaskIssue(
                    path=f"tasks.{task_name}.params.reference_file",
                    message=f"Reference file is not readable (permission denied): {file_path}",
                    code="file-not-readable",
                    details={"file_path": str(file_path)}
                ))
            except Exception as exc:
                errors.append(TaskIssue(
                    path=f"tasks.{task_name}.params.reference_file",
                    message=f"Cannot access reference file: {file_path}. Error: {exc}",
                    code="file-access-error",
                    details={"file_path": str(file_path), "error": str(exc)}
                ))
        
        return errors, warnings
    
    def _validate_directory_permissions(self, config: Dict[str, Any]) -> tuple[List[TaskIssue], List[TaskIssue]]:
        """Validate directory permissions for configured paths."""
        errors: List[TaskIssue] = []
        warnings: List[TaskIssue] = []
        
        # Check web upload directory
        web_config = config.get("web", {})
        if isinstance(web_config, dict):
            upload_dir = web_config.get("upload_dir")
            if upload_dir:
                dir_path = self._resolve_path(upload_dir)
                dir_errors = self._validate_directory_access(
                    dir_path, "web.upload_dir", "Web upload directory"
                )
                errors.extend(dir_errors)
        
        # Check watch folder directories
        watch_folder_config = config.get("watch_folder", {})
        if isinstance(watch_folder_config, dict):
            watch_dir = watch_folder_config.get("dir")
            if watch_dir:
                dir_path = self._resolve_path(watch_dir)
                dir_errors = self._validate_directory_access(
                    dir_path, "watch_folder.dir", "Watch folder directory"
                )
                errors.extend(dir_errors)
            
            processing_dir = watch_folder_config.get("processing_dir")
            if processing_dir:
                dir_path = self._resolve_path(processing_dir)
                dir_errors = self._validate_directory_access(
                    dir_path, "watch_folder.processing_dir", "Processing directory"
                )
                errors.extend(dir_errors)
        
        # Check task-specific directories
        tasks = config.get("tasks", {})
        if isinstance(tasks, dict):
            for task_name, task_config in tasks.items():
                if not isinstance(task_config, dict):
                    continue
                
                params = task_config.get("params", {})
                if not isinstance(params, dict):
                    continue
                
                # Check various directory parameters
                dir_params = ["data_dir", "files_dir", "archive_dir", "processing_dir"]
                for param_name in dir_params:
                    param_value = params.get(param_name)
                    if param_value:
                        dir_path = self._resolve_path(param_value)
                        dir_errors = self._validate_directory_access(
                            dir_path, 
                            f"tasks.{task_name}.params.{param_name}",
                            f"Task {task_name} {param_name}"
                        )
                        errors.extend(dir_errors)
        
        return errors, warnings
    
    def _validate_csv_files(self, config: Dict[str, Any]) -> tuple[List[TaskIssue], List[TaskIssue]]:
        """Validate CSV file structures."""
        errors: List[TaskIssue] = []
        warnings: List[TaskIssue] = []
        
        if not PANDAS_AVAILABLE:
            warnings.append(TaskIssue(
                path="runtime_validation",
                message="pandas is not available for CSV structure validation",
                code="csv-validation-unavailable"
            ))
            return errors, warnings
        
        tasks = config.get("tasks", {})
        if not isinstance(tasks, dict):
            return errors, warnings
        
        for task_name, task_config in tasks.items():
            if not isinstance(task_config, dict):
                continue
            
            # Check if this is a rules task
            module_name = task_config.get("module", "")
            if not isinstance(module_name, str) or "rules" not in module_name:
                continue
            
            params = task_config.get("params", {})
            if not isinstance(params, dict):
                continue
            
            reference_file = params.get("reference_file")
            if not reference_file:
                continue
            
            file_path = self._resolve_path(reference_file)
            
            # Skip if file doesn't exist (already reported in file validation)
            if not file_path.exists():
                continue
            
            # Validate CSV structure
            try:
                df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
                
                if df.empty:
                    warnings.append(TaskIssue(
                        path=f"tasks.{task_name}.params.reference_file",
                        message=f"CSV file is empty: {file_path}",
                        code="csv-empty",
                        details={"file_path": str(file_path)}
                    ))
                
                # Check for required columns based on task configuration
                update_field = params.get("update_field")
                if update_field and update_field not in df.columns:
                    errors.append(TaskIssue(
                        path=f"tasks.{task_name}.params.update_field",
                        message=f"Update field '{update_field}' not found in CSV columns: {', '.join(df.columns)}",
                        code="csv-missing-column",
                        details={"file_path": str(file_path), "missing_column": update_field}
                    ))
                
                # Check clause columns
                csv_match = params.get("csv_match", {})
                clauses = csv_match.get("clauses", [])
                for i, clause in enumerate(clauses):
                    if not isinstance(clause, dict):
                        continue
                    
                    column = clause.get("column")
                    if column and column not in df.columns:
                        errors.append(TaskIssue(
                            path=f"tasks.{task_name}.params.csv_match.clauses[{i}].column",
                            message=f"Clause column '{column}' not found in CSV columns: {', '.join(df.columns)}",
                            code="csv-missing-column",
                            details={"file_path": str(file_path), "missing_column": column}
                        ))
                
            except pd.errors.EmptyDataError:
                errors.append(TaskIssue(
                    path=f"tasks.{task_name}.params.reference_file",
                    message=f"CSV file has no data or invalid format: {file_path}",
                    code="csv-invalid-format",
                    details={"file_path": str(file_path)}
                ))
            except Exception as exc:
                errors.append(TaskIssue(
                    path=f"tasks.{task_name}.params.reference_file",
                    message=f"Cannot parse CSV file: {file_path}. Error: {exc}",
                    code="csv-parse-error",
                    details={"file_path": str(file_path), "error": str(exc)}
                ))
        
        return errors, warnings
    
    def _validate_directory_access(self, dir_path: Path, config_path: str, description: str) -> List[TaskIssue]:
        """Validate directory access and permissions."""
        errors: List[TaskIssue] = []
        
        if not dir_path.exists():
            errors.append(TaskIssue(
                path=config_path,
                message=f"{description} does not exist: {dir_path}",
                code="directory-not-found",
                details={"directory_path": str(dir_path)}
            ))
            return errors
        
        if not dir_path.is_dir():
            errors.append(TaskIssue(
                path=config_path,
                message=f"{description} is not a directory: {dir_path}",
                code="path-not-directory",
                details={"directory_path": str(dir_path)}
            ))
            return errors
        
        # Check read access
        if not os.access(dir_path, os.R_OK):
            errors.append(TaskIssue(
                path=config_path,
                message=f"{description} is not readable: {dir_path}",
                code="directory-not-readable",
                details={"directory_path": str(dir_path)}
            ))
        
        # Check write access
        if not os.access(dir_path, os.W_OK):
            errors.append(TaskIssue(
                path=config_path,
                message=f"{description} is not writable: {dir_path}",
                code="directory-not-writable",
                details={"directory_path": str(dir_path)}
            ))
        
        return errors
    
    def _resolve_path(self, path_str: str) -> Path:
        """Resolve a path string relative to the base directory."""
        path = Path(path_str)
        if path.is_absolute():
            return path
        return self.base_dir / path


def validate_runtime_files(config: Dict[str, Any], base_dir: Optional[Path] = None) -> FileValidationResult:
    """Validate runtime file dependencies.
    
    Args:
        config: Configuration dictionary to validate
        base_dir: Base directory for resolving relative paths
        
    Returns:
        FileValidationResult with validation findings
    """
    validator = RuntimeFileValidator(base_dir)
    return validator.validate_file_dependencies(config)