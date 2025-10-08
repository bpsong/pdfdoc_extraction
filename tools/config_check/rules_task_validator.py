"""Rules task validation for config-check.

This module provides comprehensive validation for rules tasks (update_reference.py)
that process CSV files and update reference data based on pipeline context values.

The rules task validator performs specialized validation including:
- CSV structure validation using pandas to check file accessibility and headers
- Column existence validation to verify update_field and clause columns exist in CSV
- Clause uniqueness detection to identify duplicate clauses and potential conflicts
- Context path validation with proper dotted notation checking
- Deprecation warnings for "data." prefixes in from_context paths
- Semantic validation to detect type mismatches and unrealistic field references

Key Features:
- CSV file parsing and structure validation
- Column reference validation against actual CSV headers
- Duplicate clause detection with conflict warnings
- Context path syntax validation with field existence checking
- Deprecation warnings for legacy "data." prefix usage
- Semantic validation for type mismatches and impossible conditions
- Comprehensive error reporting with specific path context

Classes:
    RulesTaskValidator: Main validator class for rules task configurations
    CSVValidationResult: Result of CSV file validation with column information
    ClauseValidationResult: Result of clause validation with issue tracking

Functions:
    validate_rules_task(): Main validation entry point for rules task configurations

Windows Compatibility:
    - Proper handling of Windows file paths and CSV encoding
    - Case-sensitive column name validation as per CSV standards
    - Support for Windows-specific file access patterns

Note:
    CSV validation requires pandas for file parsing and structure analysis.
    This validation is designed to catch configuration errors before runtime
    and provide actionable feedback for troubleshooting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from .task_validator import TaskIssue


@dataclass
class CSVValidationResult:
    """Result of CSV file validation."""
    is_valid: bool
    columns: List[str]
    error_message: Optional[str] = None
    row_count: Optional[int] = None


@dataclass
class ClauseValidationResult:
    """Result of clause validation."""
    clause_index: int
    column: str
    from_context: str
    issues: List[str]
    is_duplicate: bool = False
    has_deprecated_prefix: bool = False


class ContextPathValidator:
    """Validates from_context dotted paths."""
    
    VALID_PATH_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$')
    DEPRECATED_DATA_PREFIX = re.compile(r'^data\.')
    
    def validate_context_path(self, path: str, available_fields: Optional[List[str]] = None) -> List[str]:
        """Validate a context path and return any issues."""
        issues = []
        
        # Check basic syntax
        if not self.VALID_PATH_PATTERN.match(path):
            issues.append(f"Invalid dotted path syntax: '{path}'")
        
        # Check for deprecated data. prefix
        if self.DEPRECATED_DATA_PREFIX.match(path):
            issues.append(f"Deprecated 'data.' prefix in path: '{path}'. Use bare field name instead.")
        
        # Check if field exists in extraction fields
        if available_fields:
            clean_path = self.DEPRECATED_DATA_PREFIX.sub('', path)
            if clean_path not in available_fields:
                issues.append(f"Field '{clean_path}' not found in extraction fields")
        
        return issues


class RulesTaskValidator:
    """Specialized validator for rules task configurations."""
    
    def __init__(self):
        self.context_validator = ContextPathValidator()
        self._csv_columns: Dict[str, List[str]] = {}
    
    def validate_rules_task(self, task_name: str, task_config: Dict[str, Any], 
                          extraction_fields: Optional[Dict[str, Any]] = None) -> List[TaskIssue]:
        """Comprehensive validation of rules task configuration."""
        findings: List[TaskIssue] = []
        
        # CSV structure validation
        findings.extend(self._validate_csv_structure(task_name, task_config))
        
        # Column existence validation
        findings.extend(self._validate_column_existence(task_name, task_config))
        
        # Clause uniqueness validation
        findings.extend(self._validate_clause_uniqueness(task_name, task_config))
        
        # Context path validation
        findings.extend(self._validate_context_paths(task_name, task_config, extraction_fields))
        
        # Deprecation warnings
        findings.extend(self._check_deprecation_warnings(task_name, task_config))
        
        # Semantic validation
        findings.extend(self._validate_semantic_issues(task_name, task_config, extraction_fields))
        
        return findings
    
    def _validate_csv_structure(self, task_name: str, task_config: Dict[str, Any]) -> List[TaskIssue]:
        """Validate CSV file structure and accessibility."""
        findings: List[TaskIssue] = []
        
        params = task_config.get("params", {})
        reference_file = params.get("reference_file")
        
        if not reference_file:
            return findings
        
        if not PANDAS_AVAILABLE:
            findings.append(TaskIssue(
                path=f"tasks.{task_name}.params.reference_file",
                message="pandas is required for CSV validation but is not available",
                code="rules-csv-pandas-missing"
            ))
            return findings
        
        try:
            # Try to read the CSV file
            df = pd.read_csv(reference_file, dtype=str, keep_default_na=False)
            
            if df.empty:
                findings.append(TaskIssue(
                    path=f"tasks.{task_name}.params.reference_file",
                    message=f"Reference CSV file '{reference_file}' is empty",
                    code="rules-csv-empty"
                ))
            
            # Store columns for later validation
            self._csv_columns[task_name] = df.columns.tolist()
            
        except FileNotFoundError:
            findings.append(TaskIssue(
                path=f"tasks.{task_name}.params.reference_file",
                message=f"Reference CSV file '{reference_file}' not found",
                code="file-not-found"
            ))
        except pd.errors.EmptyDataError:
            findings.append(TaskIssue(
                path=f"tasks.{task_name}.params.reference_file",
                message=f"Reference CSV file '{reference_file}' is empty or has no columns",
                code="rules-csv-missing-headers"
            ))
        except Exception as exc:
            findings.append(TaskIssue(
                path=f"tasks.{task_name}.params.reference_file",
                message=f"Cannot read CSV file '{reference_file}': {exc}",
                code="rules-csv-not-readable"
            ))
        
        return findings
    
    def _validate_column_existence(self, task_name: str, task_config: Dict[str, Any]) -> List[TaskIssue]:
        """Validate that referenced columns exist in the CSV file."""
        findings: List[TaskIssue] = []
        
        # Skip if CSV validation failed
        if task_name not in self._csv_columns:
            return findings
        
        params = task_config.get("params", {})
        csv_columns = self._csv_columns[task_name]
        
        # Validate update_field
        update_field = params.get("update_field")
        if update_field and update_field not in csv_columns:
            findings.append(TaskIssue(
                path=f"tasks.{task_name}.params.update_field",
                message=f"Update field '{update_field}' not found in CSV columns: {', '.join(csv_columns)}",
                code="rules-column-not-found"
            ))
        
        # Validate clause columns
        csv_match = params.get("csv_match", {})
        
        # Validate that csv_match is a dictionary
        if not isinstance(csv_match, dict):
            return findings  # Skip validation if csv_match is not a dict (error handled elsewhere)
        
        clauses = csv_match.get("clauses", [])
        
        for i, clause in enumerate(clauses):
            if not isinstance(clause, dict):
                continue
                
            column = clause.get("column")
            if column and column not in csv_columns:
                findings.append(TaskIssue(
                    path=f"tasks.{task_name}.params.csv_match.clauses[{i}].column",
                    message=f"Clause column '{column}' not found in CSV columns: {', '.join(csv_columns)}",
                    code="rules-column-not-found"
                ))
        
        return findings
    
    def _validate_clause_uniqueness(self, task_name: str, task_config: Dict[str, Any]) -> List[TaskIssue]:
        """Validate clause uniqueness and detect potential conflicts."""
        findings: List[TaskIssue] = []
        
        params = task_config.get("params", {})
        csv_match = params.get("csv_match", {})
        
        # Validate that csv_match is a dictionary
        if not isinstance(csv_match, dict):
            return findings  # Skip validation if csv_match is not a dict (error handled elsewhere)
        
        clauses = csv_match.get("clauses", [])
        
        # Track clauses for duplicate detection
        clause_signatures = []
        column_usage = {}
        context_usage = {}
        
        for i, clause in enumerate(clauses):
            if not isinstance(clause, dict):
                continue
                
            column = clause.get("column")
            from_context = clause.get("from_context")
            
            # Create signature for exact duplicate detection
            signature = (column, from_context, clause.get("number", False))
            
            if signature in clause_signatures:
                findings.append(TaskIssue(
                    path=f"tasks.{task_name}.params.csv_match.clauses[{i}]",
                    message=f"Duplicate clause: column='{column}', from_context='{from_context}'",
                    code="rules-duplicate-clause",
                    details={"severity": "error"}
                ))
            else:
                clause_signatures.append(signature)
            
            # Track column usage for impossible condition detection
            if column:
                column_usage.setdefault(column, []).append(i)
            
            # Track context usage for info messages
            if from_context:
                context_usage.setdefault(from_context, []).append(i)
        
        # Warn about multiple clauses on same column
        for column, clause_indices in column_usage.items():
            if len(clause_indices) > 1:
                findings.append(TaskIssue(
                    path=f"tasks.{task_name}.params.csv_match.clauses",
                    message=f"Multiple clauses reference column '{column}' (indices: {clause_indices}). "
                           f"This may create impossible AND conditions.",
                    code="rules-impossible-condition",
                    details={"severity": "warning"}
                ))
        
        # Info about multiple clauses using same context
        for context, clause_indices in context_usage.items():
            if len(clause_indices) > 1:
                findings.append(TaskIssue(
                    path=f"tasks.{task_name}.params.csv_match.clauses",
                    message=f"Multiple clauses use context '{context}' (indices: {clause_indices}). "
                           f"This might be intentional but worth noting.",
                    code="rules-context-reuse",
                    details={"severity": "info"}
                ))
        
        return findings
    
    def _validate_context_paths(self, task_name: str, task_config: Dict[str, Any], 
                               extraction_fields: Optional[Dict[str, Any]] = None) -> List[TaskIssue]:
        """Validate context paths in clauses."""
        findings: List[TaskIssue] = []
        
        params = task_config.get("params", {})
        csv_match = params.get("csv_match", {})
        
        # Validate that csv_match is a dictionary
        if not isinstance(csv_match, dict):
            return findings  # Skip validation if csv_match is not a dict (error handled elsewhere)
        
        clauses = csv_match.get("clauses", [])
        
        # Extract available field names from extraction fields
        available_fields = []
        if extraction_fields:
            available_fields = list(extraction_fields.keys())
        
        for i, clause in enumerate(clauses):
            if not isinstance(clause, dict):
                continue
                
            from_context = clause.get("from_context")
            if not from_context:
                continue
            
            issues = self.context_validator.validate_context_path(from_context, available_fields)
            
            for issue in issues:
                # Determine severity based on issue type
                if "Invalid dotted path syntax" in issue:
                    code = "rules-context-path-invalid"
                    severity = "error"
                elif "not found in extraction fields" in issue:
                    code = "rules-field-not-found"
                    severity = "warning"
                else:
                    code = "rules-context-path-issue"
                    severity = "warning"
                
                findings.append(TaskIssue(
                    path=f"tasks.{task_name}.params.csv_match.clauses[{i}].from_context",
                    message=issue,
                    code=code,
                    details={"severity": severity}
                ))
        
        return findings
    
    def _check_deprecation_warnings(self, task_name: str, task_config: Dict[str, Any]) -> List[TaskIssue]:
        """Check for deprecated 'data.' prefixes in context paths."""
        findings: List[TaskIssue] = []
        
        params = task_config.get("params", {})
        csv_match = params.get("csv_match", {})
        
        # Validate that csv_match is a dictionary
        if not isinstance(csv_match, dict):
            return findings  # Skip validation if csv_match is not a dict (error handled elsewhere)
        
        clauses = csv_match.get("clauses", [])
        
        for i, clause in enumerate(clauses):
            if not isinstance(clause, dict):
                continue
                
            from_context = clause.get("from_context", "")
            if from_context and from_context.startswith("data."):
                suggested_path = from_context[5:]  # Remove "data." prefix
                findings.append(TaskIssue(
                    path=f"tasks.{task_name}.params.csv_match.clauses[{i}].from_context",
                    message=f"Deprecated 'data.' prefix in context path: '{from_context}'. "
                           f"Use bare field name '{suggested_path}' instead.",
                    code="rules-deprecated-data-prefix",
                    details={"severity": "warning", "suggested_replacement": suggested_path}
                ))
        
        return findings
    
    def _validate_semantic_issues(self, task_name: str, task_config: Dict[str, Any], 
                                 extraction_fields: Optional[Dict[str, Any]] = None) -> List[TaskIssue]:
        """Validate semantic issues like type mismatches and unrealistic field references."""
        findings: List[TaskIssue] = []
        
        params = task_config.get("params", {})
        csv_match = params.get("csv_match", {})
        
        # Validate that csv_match is a dictionary
        if not isinstance(csv_match, dict):
            return findings  # Skip validation if csv_match is not a dict (error handled elsewhere)
        
        clauses = csv_match.get("clauses", [])
        
        # Skip if CSV validation failed
        if task_name not in self._csv_columns:
            return findings
        
        csv_columns = self._csv_columns[task_name]
        
        for i, clause in enumerate(clauses):
            if not isinstance(clause, dict):
                continue
                
            column = clause.get("column")
            from_context = clause.get("from_context", "")
            number_flag = clause.get("number")
            
            if not column or not from_context:
                continue
            
            # Check for potential type mismatches
            if self._is_likely_numeric_column(column) and number_flag is False:
                findings.append(TaskIssue(
                    path=f"tasks.{task_name}.params.csv_match.clauses[{i}]",
                    message=f"Column '{column}' appears to be numeric but clause forces string comparison. "
                           f"Consider removing 'number: false' or verify the column type.",
                    code="rules-semantic-type-mismatch",
                    details={"severity": "warning"}
                ))
            
            # Check for unrealistic field references
            clean_context = from_context.replace("data.", "") if from_context.startswith("data.") else from_context
            if self._is_unrealistic_field_reference(clean_context):
                findings.append(TaskIssue(
                    path=f"tasks.{task_name}.params.csv_match.clauses[{i}].from_context",
                    message=f"Field reference '{clean_context}' doesn't match common extraction patterns. "
                           f"Verify this field exists in your extraction configuration.",
                    code="rules-unrealistic-field-reference",
                    details={"severity": "info"}
                ))
        
        return findings
    
    def _is_likely_numeric_column(self, column_name: str) -> bool:
        """Check if a column name suggests numeric content."""
        numeric_indicators = [
            'amount', 'total', 'price', 'cost', 'value', 'sum', 'count', 'number',
            'qty', 'quantity', 'rate', 'percent', 'percentage', 'tax', 'fee',
            'balance', 'credit', 'debit', 'invoice_total', 'subtotal'
        ]
        
        column_lower = column_name.lower()
        return any(indicator in column_lower for indicator in numeric_indicators)
    
    def _is_unrealistic_field_reference(self, field_name: str) -> bool:
        """Check if a field reference seems unrealistic for typical extraction."""
        # Common extraction field patterns
        common_patterns = [
            'invoice', 'date', 'amount', 'total', 'supplier', 'vendor', 'customer',
            'address', 'phone', 'email', 'number', 'id', 'reference', 'order',
            'purchase', 'tax', 'description', 'item', 'quantity', 'price', 'cost'
        ]
        
        field_lower = field_name.lower()
        
        # If field contains common patterns, it's likely realistic
        if any(pattern in field_lower for pattern in common_patterns):
            return False
        
        # Check for very generic or system-like names that might be unrealistic
        unrealistic_patterns = [
            'test', 'example', 'sample', 'dummy', 'temp', 'tmp', 'debug',
            'foo', 'bar', 'baz', 'placeholder', 'xxx', 'yyy', 'zzz'
        ]
        
        return any(pattern in field_lower for pattern in unrealistic_patterns)


def validate_rules_task(task_name: str, task_config: Dict[str, Any], 
                       extraction_fields: Optional[Dict[str, Any]] = None) -> List[TaskIssue]:
    """Validate a rules task configuration.
    
    Args:
        task_name: Name of the task being validated
        task_config: Task configuration dictionary
        extraction_fields: Optional extraction field definitions for cross-validation
        
    Returns:
        List of TaskIssue objects representing validation findings
    """
    validator = RulesTaskValidator()
    return validator.validate_rules_task(task_name, task_config, extraction_fields)