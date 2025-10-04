"""
Configuration validation entry points.

This module provides the core validation framework for configuration files used by the PDF
processing system. It implements a comprehensive multi-pass validation architecture that
systematically checks different aspects of configuration validity.

The validation system consists of four main validation passes:
1. Schema Validation: Validates configuration structure against Pydantic models
2. Task Reference Validation: Checks task definitions and optional import validation
3. Pipeline Validation: Validates pipeline dependencies and token extraction
4. Path Validation: Validates filesystem paths with Windows-specific handling

Key Features:
- Multi-pass validation architecture for comprehensive checking
- Windows-compatible path handling and validation
- Structured error reporting with file paths and error codes
- Extensible validation framework for custom validation passes
- Integration with YAML parsing and schema validation

Classes:
    ValidationMessage: Represents a single validation message with path context
    ValidationResult: Aggregated validation outcome for a configuration payload
    ConfigValidator: Main validation orchestrator implementing multi-pass validation

Note:
    All path operations are Windows-compatible and include proper path separator
    handling, case-insensitive comparisons, and UNC path support where applicable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .parameter_validator import ParameterValidationResult, validate_parameters
from .path_validator import PathValidator
from .pipeline_validator import PipelineValidationResult, validate_pipeline
from .schema import (
    SchemaValidationResult,
    validate_config_against_schema,
)
from .suggestions import get_suggestion
from .task_validator import TaskValidationResult, validate_tasks
from .yaml_parser import YAMLParser

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ValidationMessage:
    """Represents a single validation message with config path context."""

    path: str
    message: str
    code: Optional[str] = None
    suggestion: Optional[str] = None


class ValidationResult:
    """Aggregated validation outcome for a configuration payload."""

    def __init__(
        self,
        *,
        data: Optional[Dict[str, Any]] = None,
        errors: Optional[List[ValidationMessage]] = None,
        warnings: Optional[List[ValidationMessage]] = None,
    ) -> None:
        self.data = data
        self.errors: List[ValidationMessage] = errors or []
        self.warnings: List[ValidationMessage] = warnings or []

    @property
    def is_valid(self) -> bool:
        return not self.errors


class ConfigValidator:
    """Validate config files using YAML parsing and schema/path checks."""

    def __init__(
        self,
        *,
        strict_mode: bool = False,
        base_dir: Optional[Union[str, Path]] = None,
        import_checks: bool = False,
        yaml_parser: Optional[YAMLParser] = None,
    ) -> None:
        self.strict_mode = strict_mode
        self.base_dir = Path(base_dir) if base_dir else None
        self.import_checks = import_checks
        self.parser = yaml_parser or YAMLParser()
        self.logger = logger.getChild(self.__class__.__name__)
        self.path_validator = PathValidator(base_dir=self.base_dir)
        self._validation_passes = [
            self._run_schema_pass,
            self._run_task_reference_pass,
            self._run_parameter_pass,
            self._run_pipeline_pass,
            self._run_path_pass,
        ]

    def validate(self, config_path: Union[str, Path]) -> ValidationResult:
        """Validate a configuration file on disk."""

        config_path = Path(config_path)
        self.logger.debug("Starting validation for %s", config_path)

        if not config_path.exists():
            return ValidationResult(
                errors=[
                    ValidationMessage(
                        path="config",
                        message=f"Configuration file not found: {config_path}",
                        code="file-not-found",
                    )
                ]
            )

        data, error = self.parser.load(str(config_path))
        if error:
            self.logger.debug("YAML parsing failed: %s", error)
            return ValidationResult(
                errors=[ValidationMessage(path="config", message=error, code="yaml-error")]
            )

        if data is None:
            return ValidationResult(
                errors=[ValidationMessage(path="config", message="Configuration file is empty or contains no valid data", code="empty-config")]
            )

        # Convert MutableMapping to Dict for type compatibility
        config_dict = dict(data) if not isinstance(data, dict) else data
        return self.validate_config_data(config_dict)

    def validate_config_data(self, config_data: Dict[str, Any]) -> ValidationResult:
        """Validate an already parsed configuration mapping."""

        aggregated = ValidationResult()
        current_data: Dict[str, Any] = config_data

        for validation_pass in self._validation_passes:
            pass_result = validation_pass(current_data)
            aggregated.errors.extend(pass_result.errors)
            aggregated.warnings.extend(pass_result.warnings)
            if pass_result.data is not None:
                current_data = pass_result.data
                aggregated.data = current_data

        if aggregated.data is None:
            aggregated.data = current_data

        return aggregated

    def _run_schema_pass(self, config_data: Dict[str, Any]) -> ValidationResult:
        """Run the schema validation pass and return its findings."""

        self.logger.debug("Running schema validation (strict=%s)", self.strict_mode)
        schema_result: SchemaValidationResult = validate_config_against_schema(
            config_data, strict=self.strict_mode
        )

        errors = [
            ValidationMessage(path=issue.path, message=issue.message, code="schema")
            for issue in schema_result.errors
        ]
        warnings = [
            ValidationMessage(path=issue.path, message=issue.message, code="schema")
            for issue in schema_result.warnings
        ]

        data_dict: Optional[Dict[str, Any]] = None
        if schema_result.model is not None:
            data_dict = schema_result.model.model_dump(by_alias=True)

        return ValidationResult(data=data_dict, errors=errors, warnings=warnings)

    def _run_task_reference_pass(self, config_data: Dict[str, Any]) -> ValidationResult:
        """Run task existence and optional import validation."""

        if not isinstance(config_data, dict):
            return ValidationResult()

        task_result: TaskValidationResult = validate_tasks(
            config_data, import_checks=self.import_checks
        )

        errors: List[ValidationMessage] = []
        for issue in task_result.errors:
            suggestion = get_suggestion(issue.code, getattr(issue, "details", None))
            errors.append(
                ValidationMessage(
                    path=issue.path,
                    message=issue.message,
                    code=issue.code,
                    suggestion=suggestion,
                )
            )

        warnings: List[ValidationMessage] = []
        for issue in task_result.warnings:
            suggestion = get_suggestion(issue.code, getattr(issue, "details", None))
            warnings.append(
                ValidationMessage(
                    path=issue.path,
                    message=issue.message,
                    code=issue.code,
                    suggestion=suggestion,
                )
            )

        return ValidationResult(errors=errors, warnings=warnings)

    def _run_parameter_pass(self, config_data: Dict[str, Any]) -> ValidationResult:
        """Run parameter-level validation."""

        if not isinstance(config_data, dict):
            return ValidationResult()

        parameter_result: ParameterValidationResult = validate_parameters(config_data)

        errors: List[ValidationMessage] = []
        for issue in parameter_result.errors:
            suggestion = get_suggestion(issue.code, getattr(issue, "details", None))
            errors.append(
                ValidationMessage(
                    path=issue.path,
                    message=issue.message,
                    code=issue.code,
                    suggestion=suggestion,
                )
            )

        warnings: List[ValidationMessage] = []
        for issue in parameter_result.warnings:
            suggestion = get_suggestion(issue.code, getattr(issue, "details", None))
            warnings.append(
                ValidationMessage(
                    path=issue.path,
                    message=issue.message,
                    code=issue.code,
                    suggestion=suggestion,
                )
            )

        return ValidationResult(errors=errors, warnings=warnings)


    def _run_pipeline_pass(self, config_data: Dict[str, Any]) -> ValidationResult:
        """Run pipeline dependency validation."""

        if not isinstance(config_data, dict):
            return ValidationResult()

        pipeline_result: PipelineValidationResult = validate_pipeline(config_data)

        errors: List[ValidationMessage] = []
        for issue in pipeline_result.errors:
            suggestion = get_suggestion(issue.code, getattr(issue, "details", None))
            errors.append(
                ValidationMessage(
                    path=issue.path,
                    message=issue.message,
                    code=issue.code,
                    suggestion=suggestion,
                )
            )

        warnings: List[ValidationMessage] = []
        for issue in pipeline_result.warnings:
            suggestion = get_suggestion(issue.code, getattr(issue, "details", None))
            warnings.append(
                ValidationMessage(
                    path=issue.path,
                    message=issue.message,
                    code=issue.code,
                    suggestion=suggestion,
                )
            )

        return ValidationResult(errors=errors, warnings=warnings)

    def _run_path_pass(self, config_data: Dict[str, Any]) -> ValidationResult:
        """Run the filesystem-related validation pass."""

        if not isinstance(config_data, dict):
            return ValidationResult()

        path_result = self.path_validator.validate(config_data)

        errors: List[ValidationMessage] = []
        for issue in path_result.errors:
            suggestion = get_suggestion(issue.code, getattr(issue, "details", None))
            errors.append(
                ValidationMessage(
                    path=issue.path,
                    message=issue.message,
                    code=issue.code,
                    suggestion=suggestion,
                )
            )

        warnings: List[ValidationMessage] = []
        for issue in path_result.warnings:
            suggestion = get_suggestion(issue.code, getattr(issue, "details", None))
            warnings.append(
                ValidationMessage(
                    path=issue.path,
                    message=issue.message,
                    code=issue.code,
                    suggestion=suggestion,
                )
            )

        return ValidationResult(errors=errors, warnings=warnings)

