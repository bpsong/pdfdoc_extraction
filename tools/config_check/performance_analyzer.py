"""
Performance impact analysis for configuration validation.

This module provides performance analysis capabilities for the config-check tool,
identifying potential performance issues in configuration files before deployment.
It analyzes extraction task complexity, rules task complexity, and cumulative
pipeline impact to provide optimization recommendations.

Key Features:
- Extraction field complexity analysis with configurable thresholds
- Rules clause complexity detection and optimization suggestions
- Cumulative pipeline impact assessment
- Performance optimization recommendations with severity levels
- Integration with existing validation pipeline

Classes:
    PerformanceIssue: Represents a performance-related validation issue
    PerformanceAnalysisResult: Aggregated performance analysis results
    PerformanceAnalyzer: Main performance analysis engine

Performance Thresholds:
- Extraction fields: Warning at >20 fields, Error at >50 fields
- Rules clauses: Warning at >10 clauses, Error at >25 clauses
- Table fields: Info at >1 table field, Warning at >3 table fields
- Pipeline tasks: Warning at >15 tasks, Error at >30 tasks
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PerformanceIssue:
    """Represents a performance-related validation issue."""

    path: str
    message: str
    code: str
    severity: str = "warning"  # "info", "warning", "error"
    details: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class PerformanceAnalysisResult:
    """Aggregated performance analysis results."""

    errors: List[PerformanceIssue]
    warnings: List[PerformanceIssue]
    info: List[PerformanceIssue]

    def __init__(self) -> None:
        self.errors = []
        self.warnings = []
        self.info = []

    def add_issue(self, issue: PerformanceIssue) -> None:
        """Add an issue to the appropriate severity list."""
        if issue.severity == "error":
            self.errors.append(issue)
        elif issue.severity == "warning":
            self.warnings.append(issue)
        else:
            self.info.append(issue)

    @property
    def all_issues(self) -> List[PerformanceIssue]:
        """Get all issues regardless of severity."""
        return self.errors + self.warnings + self.info


class PerformanceAnalyzer:
    """Analyzes configuration for performance impact."""

    # Performance thresholds
    EXTRACTION_FIELD_WARNING_THRESHOLD = 20
    EXTRACTION_FIELD_ERROR_THRESHOLD = 50
    TABLE_FIELD_INFO_THRESHOLD = 1
    TABLE_FIELD_WARNING_THRESHOLD = 3
    PIPELINE_TASK_WARNING_THRESHOLD = 15
    PIPELINE_TASK_ERROR_THRESHOLD = 30

    def __init__(self) -> None:
        self.logger = logger.getChild(self.__class__.__name__)

    def analyze_performance_impact(self, config: Dict[str, Any]) -> PerformanceAnalysisResult:
        """Analyze configuration for performance issues."""
        self.logger.debug("Starting performance impact analysis")
        result = PerformanceAnalysisResult()

        # Analyze extraction field complexity
        extraction_issues = self._analyze_extraction_complexity(config)
        for issue in extraction_issues:
            result.add_issue(issue)

        # Analyze rules task complexity
        rules_issues = self._analyze_rules_complexity(config)
        for issue in rules_issues:
            result.add_issue(issue)

        # Analyze pipeline cumulative impact
        pipeline_issues = self._analyze_pipeline_impact(config)
        for issue in pipeline_issues:
            result.add_issue(issue)

        self.logger.debug(
            "Performance analysis complete: %d errors, %d warnings, %d info",
            len(result.errors),
            len(result.warnings),
            len(result.info)
        )

        return result

    def _analyze_extraction_complexity(self, config: Dict[str, Any]) -> List[PerformanceIssue]:
        """Analyze extraction tasks for performance impact."""
        issues: List[PerformanceIssue] = []
        tasks = config.get("tasks", {})

        for task_name, task_config in tasks.items():
            if not self._is_extraction_task(task_config):
                continue

            params = task_config.get("params", {})
            fields = params.get("fields", [])
            
            if not isinstance(fields, list):
                continue

            field_count = len(fields)
            
            # Check for excessive field counts
            if field_count > self.EXTRACTION_FIELD_ERROR_THRESHOLD:
                issues.append(PerformanceIssue(
                    path=f"tasks.{task_name}.params.fields",
                    message=f"Extraction task has {field_count} fields, which may severely impact performance. "
                           f"Consider reducing to under {self.EXTRACTION_FIELD_WARNING_THRESHOLD} fields.",
                    code="performance-excessive-fields-critical",
                    severity="error",
                    details={
                        "field_count": field_count,
                        "recommended_max": self.EXTRACTION_FIELD_WARNING_THRESHOLD,
                        "critical_threshold": self.EXTRACTION_FIELD_ERROR_THRESHOLD
                    }
                ))
            elif field_count > self.EXTRACTION_FIELD_WARNING_THRESHOLD:
                issues.append(PerformanceIssue(
                    path=f"tasks.{task_name}.params.fields",
                    message=f"Extraction task has {field_count} fields. "
                           f"Consider reducing to under {self.EXTRACTION_FIELD_WARNING_THRESHOLD} for optimal performance.",
                    code="performance-excessive-fields",
                    severity="warning",
                    details={
                        "field_count": field_count,
                        "recommended_max": self.EXTRACTION_FIELD_WARNING_THRESHOLD
                    }
                ))

            # Analyze table field complexity
            table_fields = [f for f in fields if isinstance(f, dict) and f.get("is_table", False)]
            table_count = len(table_fields)
            
            if table_count > self.TABLE_FIELD_WARNING_THRESHOLD:
                issues.append(PerformanceIssue(
                    path=f"tasks.{task_name}.params.fields",
                    message=f"Extraction task has {table_count} table fields, which may impact performance. "
                           f"Consider consolidating table data or splitting into separate tasks.",
                    code="performance-multiple-tables-warning",
                    severity="warning",
                    details={
                        "table_field_count": table_count,
                        "recommended_max": self.TABLE_FIELD_WARNING_THRESHOLD
                    }
                ))
            elif table_count > self.TABLE_FIELD_INFO_THRESHOLD:
                issues.append(PerformanceIssue(
                    path=f"tasks.{task_name}.params.fields",
                    message=f"Extraction task has {table_count} table fields. "
                           f"Monitor performance and consider consolidation if processing is slow.",
                    code="performance-multiple-tables",
                    severity="info",
                    details={
                        "table_field_count": table_count
                    }
                ))

            # Check for complex field configurations
            complex_fields = []
            for field in fields:
                if isinstance(field, dict):
                    # Check for fields with complex extraction patterns
                    if field.get("description", "").count("extract") > 2:
                        complex_fields.append(field.get("name", "unnamed"))
                    # Check for fields with multiple conditions
                    if isinstance(field.get("conditions"), list) and len(field.get("conditions", [])) > 3:
                        complex_fields.append(field.get("name", "unnamed"))

            if complex_fields:
                issues.append(PerformanceIssue(
                    path=f"tasks.{task_name}.params.fields",
                    message=f"Fields with complex extraction patterns detected: {', '.join(complex_fields[:3])}. "
                           f"Complex patterns may impact extraction performance.",
                    code="performance-complex-field-patterns",
                    severity="info",
                    details={
                        "complex_fields": complex_fields,
                        "complex_field_count": len(complex_fields)
                    }
                ))

        return issues

    def _analyze_rules_complexity(self, config: Dict[str, Any]) -> List[PerformanceIssue]:
        """Analyze rules tasks for performance impact."""
        issues: List[PerformanceIssue] = []
        tasks = config.get("tasks", {})

        for task_name, task_config in tasks.items():
            if not self._is_rules_task(task_config):
                continue

            params = task_config.get("params", {})
            csv_match = params.get("csv_match", {})
            clauses = csv_match.get("clauses", [])
            
            if not isinstance(clauses, list):
                continue

            clause_count = len(clauses)

            # Analyze clause complexity patterns (only for deeply nested paths)
            complex_clauses = 0
            
            for clause in clauses:
                if isinstance(clause, dict):
                    # Check for complex context paths (more than 3 levels deep)
                    from_context = clause.get("from_context", "")
                    if isinstance(from_context, str) and from_context.count(".") > 3:
                        complex_clauses += 1

            # Only warn about deeply nested context paths (4+ levels)
            if complex_clauses > 0:
                issues.append(PerformanceIssue(
                    path=f"tasks.{task_name}.params.csv_match.clauses",
                    message=f"Rules task has {complex_clauses} clauses with deeply nested context paths (4+ levels). "
                           f"Consider simplifying context path structure.",
                    code="performance-complex-context-paths",
                    severity="info",
                    details={
                        "complex_clause_count": complex_clauses,
                        "total_clauses": clause_count
                    }
                ))

        return issues

    def _analyze_pipeline_impact(self, config: Dict[str, Any]) -> List[PerformanceIssue]:
        """Analyze pipeline cumulative impact."""
        issues: List[PerformanceIssue] = []
        pipeline = config.get("pipeline", [])
        
        if not isinstance(pipeline, list):
            return issues

        task_count = len(pipeline)
        
        # Check for excessive pipeline length
        if task_count > self.PIPELINE_TASK_ERROR_THRESHOLD:
            issues.append(PerformanceIssue(
                path="pipeline",
                message=f"Pipeline has {task_count} tasks, which may severely impact processing time. "
                       f"Consider optimizing or parallelizing tasks.",
                code="performance-excessive-pipeline-length-critical",
                severity="error",
                details={
                    "task_count": task_count,
                    "recommended_max": self.PIPELINE_TASK_WARNING_THRESHOLD,
                    "critical_threshold": self.PIPELINE_TASK_ERROR_THRESHOLD
                }
            ))
        elif task_count > self.PIPELINE_TASK_WARNING_THRESHOLD:
            issues.append(PerformanceIssue(
                path="pipeline",
                message=f"Pipeline has {task_count} tasks. "
                       f"Consider optimizing for better performance (recommended: <{self.PIPELINE_TASK_WARNING_THRESHOLD}).",
                code="performance-excessive-pipeline-length",
                severity="warning",
                details={
                    "task_count": task_count,
                    "recommended_max": self.PIPELINE_TASK_WARNING_THRESHOLD
                }
            ))

        # Analyze task type distribution
        tasks = config.get("tasks", {})
        extraction_tasks = []
        rules_tasks = []
        storage_tasks = []
        
        for task_name in pipeline:
            if isinstance(task_name, str) and task_name in tasks:
                task_config = tasks[task_name]
                if self._is_extraction_task(task_config):
                    extraction_tasks.append(task_name)
                elif self._is_rules_task(task_config):
                    rules_tasks.append(task_name)
                elif self._is_storage_task(task_config):
                    storage_tasks.append(task_name)

        # Warn about multiple extraction tasks
        if len(extraction_tasks) > 2:
            issues.append(PerformanceIssue(
                path="pipeline",
                message=f"Pipeline has {len(extraction_tasks)} extraction tasks: {', '.join(extraction_tasks[:3])}. "
                       f"Multiple extraction tasks may significantly impact performance.",
                code="performance-multiple-extraction-tasks",
                severity="warning",
                details={
                    "extraction_task_count": len(extraction_tasks),
                    "extraction_tasks": extraction_tasks
                }
            ))

        # Info about task distribution
        if len(rules_tasks) > 5:
            issues.append(PerformanceIssue(
                path="pipeline",
                message=f"Pipeline has {len(rules_tasks)} rules tasks. "
                       f"Consider consolidating rules logic for better performance.",
                code="performance-multiple-rules-tasks",
                severity="info",
                details={
                    "rules_task_count": len(rules_tasks),
                    "rules_tasks": rules_tasks[:5]  # Limit for readability
                }
            ))

        return issues

    def _is_extraction_task(self, task_config: Dict[str, Any]) -> bool:
        """Check if a task is an extraction task."""
        module = task_config.get("module", "")
        return isinstance(module, str) and "extraction" in module.lower()

    def _is_rules_task(self, task_config: Dict[str, Any]) -> bool:
        """Check if a task is a rules task."""
        module = task_config.get("module", "")
        return isinstance(module, str) and "rules" in module.lower()

    def _is_storage_task(self, task_config: Dict[str, Any]) -> bool:
        """Check if a task is a storage task."""
        module = task_config.get("module", "")
        return isinstance(module, str) and "storage" in module.lower()


def analyze_performance(config: Dict[str, Any]) -> PerformanceAnalysisResult:
    """Convenience function to analyze configuration performance impact."""
    analyzer = PerformanceAnalyzer()
    return analyzer.analyze_performance_impact(config)