"""Shared validation facade for YAML, SQLite, API, and portable sources."""

from __future__ import annotations

from typing import Any, Mapping

from modules.config_protocol import ConfigProvider
from modules.services.pipeline_validation_service import PipelineValidationService
from modules.services.schema_service import SchemaService
from modules.services.versioned_config_contracts import (
    PIPELINE_DEFINITION_SCHEMA_VERSION,
    REVIEW_SCHEMA_FORMAT_VERSION,
    CanonicalizationError,
    ValidationSource,
    canonicalize_json,
    replace_secret_references_for_validation,
    validate_secret_references,
)


class _NullConfig:
    """Minimal config provider for content-only review-schema validation."""

    def get(self, key: str, default: Any = None) -> Any:
        return default


class ValidationFacade:
    """Validate explicit configuration content and qualify every finding."""

    def __init__(self, config_manager: ConfigProvider | None = None) -> None:
        self.config_manager = config_manager

    def validate_pipeline(
        self,
        definition: Mapping[str, Any],
        *,
        source: ValidationSource,
        schema_dependencies: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Validate one explicit pipeline definition."""
        findings: list[dict[str, Any]] = []
        try:
            normalized = canonicalize_json(dict(definition))
        except CanonicalizationError as exc:
            return self._result(
                source,
                [
                    self._finding(
                        "error",
                        "$",
                        str(exc),
                        "versioned-config-not-json",
                    )
                ],
            )
        if normalized.get("schema_version") != PIPELINE_DEFINITION_SCHEMA_VERSION:
            findings.append(
                self._finding(
                    "error",
                    "schema_version",
                    "Unsupported pipeline definition schema_version.",
                    "pipeline-schema-version-unsupported",
                )
            )
        for path in validate_secret_references(normalized):
            findings.append(
                self._finding(
                    "error",
                    path,
                    "Secret-like parameters must use a valid $secret reference.",
                    "pipeline-literal-or-invalid-secret",
                )
            )
        validation_copy = replace_secret_references_for_validation(normalized)
        base_result = PipelineValidationService(self.config_manager).validate(validation_copy)
        findings.extend(base_result["findings"])
        findings.extend(
            self._validate_schema_dependencies(
                normalized,
                schema_dependencies or {},
            )
        )
        return self._result(source, findings)

    def validate_review_schema(
        self,
        schema: Mapping[str, Any],
        *,
        source: ValidationSource,
        format_version: int = REVIEW_SCHEMA_FORMAT_VERSION,
    ) -> dict[str, Any]:
        """Validate one explicit review-schema document."""
        findings: list[dict[str, Any]] = []
        try:
            normalized = canonicalize_json(dict(schema))
        except CanonicalizationError as exc:
            return self._result(
                source,
                [self._finding("error", "$", str(exc), "review-schema-not-json")],
            )
        if format_version != REVIEW_SCHEMA_FORMAT_VERSION:
            findings.append(
                self._finding(
                    "error",
                    "format_version",
                    "Unsupported review-schema format version.",
                    "review-schema-format-version-unsupported",
                )
            )
        service = SchemaService(self.config_manager or _NullConfig())
        for issue in service.validate_schema(normalized):
            findings.append(
                self._finding(
                    "error",
                    str(issue.get("path") or "$"),
                    str(issue.get("message") or "Invalid review schema."),
                    "review-schema-invalid",
                )
            )
        return self._result(source, findings)

    @staticmethod
    def _validate_schema_dependencies(
        definition: Mapping[str, Any],
        dependencies: Mapping[str, Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        tasks = definition.get("tasks")
        if not isinstance(tasks, dict):
            return findings
        for task_key, raw_task in tasks.items():
            if not isinstance(raw_task, dict) or raw_task.get("class") != "ReviewGateTask":
                continue
            params = raw_task.get("params")
            version_id = params.get("schema_version_id") if isinstance(params, dict) else None
            if not isinstance(version_id, str) or not version_id:
                findings.append(
                    ValidationFacade._finding(
                        "error",
                        f"tasks.{task_key}.params.schema_version_id",
                        "ReviewGateTask requires an exact published schema_version_id.",
                        "review-gate-schema-version-required",
                    )
                )
                continue
            dependency = dependencies.get(str(task_key))
            if dependency is None:
                findings.append(
                    ValidationFacade._finding(
                        "error",
                        f"tasks.{task_key}.params.schema_version_id",
                        "Review schema dependency could not be resolved.",
                        "review-gate-schema-version-not-found",
                    )
                )
                continue
            if str(dependency.get("id") or "") != version_id:
                findings.append(
                    ValidationFacade._finding(
                        "error",
                        f"tasks.{task_key}.params.schema_version_id",
                        "Review task schema version disagrees with its dependency.",
                        "review-gate-schema-version-mismatch",
                    )
                )
        return findings

    @staticmethod
    def _finding(severity: str, path: str, message: str, code: str) -> dict[str, Any]:
        return {
            "severity": severity,
            "path": path,
            "message": message,
            "code": code,
            "details": {},
        }

    @staticmethod
    def _result(source: ValidationSource, findings: list[dict[str, Any]]) -> dict[str, Any]:
        qualified: list[dict[str, Any]] = []
        for finding in findings:
            path = str(finding.get("path") or "$")
            qualified.append({**finding, "path": f"{source.prefix}.{path}"})
        return {
            "valid": not any(item.get("severity") == "error" for item in qualified),
            "source": source.prefix,
            "findings": qualified,
        }

