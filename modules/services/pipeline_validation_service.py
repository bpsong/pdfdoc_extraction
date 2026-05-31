"""Pipeline-specific validation service for UI/API callers."""

from __future__ import annotations

from typing import Any

from modules.config_manager import ConfigManager
from modules.services.schema_service import SchemaService
from tools.config_check.pipeline_validator import validate_pipeline


def _finding(
    *,
    severity: str,
    path: str,
    message: str,
    code: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a normalized validation finding."""
    return {
        "severity": severity,
        "path": path,
        "message": message,
        "code": code,
        "details": details or {},
    }


class PipelineValidationService:
    """Validate pipeline ordering and task-specific pipeline assumptions."""

    def __init__(self, config_manager: ConfigManager | None = None) -> None:
        """Initialize service with optional config for schema checks."""
        self.config_manager = config_manager

    def validate(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """Validate pipeline configuration and return UI-ready findings."""
        findings: list[dict[str, Any]] = []
        base_result = validate_pipeline(config_data)
        findings.extend(
            _finding(
                severity="error",
                path=issue.path,
                message=issue.message,
                code=issue.code,
                details=issue.details,
            )
            for issue in base_result.errors
        )
        findings.extend(
            _finding(
                severity="warning",
                path=issue.path,
                message=issue.message,
                code=issue.code,
                details=issue.details,
            )
            for issue in base_result.warnings
        )
        findings.extend(self._validate_review_gate(config_data))
        findings.extend(self._validate_split(config_data))
        findings.extend(self._validate_schema_references(config_data))

        return {
            "valid": not any(finding["severity"] == "error" for finding in findings),
            "findings": findings,
        }

    def _validate_review_gate(self, config_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate ReviewGateTask-specific parameters."""
        findings: list[dict[str, Any]] = []
        for task_key, task_cfg in _iter_tasks(config_data):
            if task_cfg.get("class") != "ReviewGateTask":
                continue
            params = task_cfg.get("params", {})
            if not isinstance(params, dict):
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params",
                        message="ReviewGateTask params must be a mapping.",
                        code="review-gate-params-not-mapping",
                    )
                )
                continue

            threshold = params.get("confidence_threshold")
            if threshold is not None and (
                isinstance(threshold, bool)
                or not isinstance(threshold, (int, float))
                or threshold < 0
                or threshold > 1
            ):
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params.confidence_threshold",
                        message="ReviewGateTask confidence_threshold must be between 0 and 1.",
                        code="review-gate-invalid-confidence-threshold",
                    )
                )

            resume_policy = params.get("resume_policy")
            if resume_policy is not None and resume_policy != "next_task":
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params.resume_policy",
                        message="ReviewGateTask currently supports only resume_policy: next_task.",
                        code="review-gate-invalid-resume-policy",
                    )
                )

            split_levels = params.get("split_confidence_levels_requiring_review")
            if split_levels is not None:
                allowed = {"high", "medium", "low"}
                if (
                    not isinstance(split_levels, list)
                    or any(level not in allowed for level in split_levels)
                ):
                    findings.append(
                        _finding(
                            severity="error",
                            path=f"tasks.{task_key}.params.split_confidence_levels_requiring_review",
                            message="Split confidence review levels must be a list containing high, medium, or low.",
                            code="review-gate-invalid-split-confidence-levels",
                        )
                    )
        return findings

    def _validate_split(self, config_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate split task parameters and fan-out/fan-in assumptions."""
        findings: list[dict[str, Any]] = []
        pipeline = config_data.get("pipeline") if isinstance(config_data.get("pipeline"), list) else []
        split_task_keys: list[str] = []
        for task_key, task_cfg in _iter_tasks(config_data):
            if task_cfg.get("class") != "LlamaCloudSplitTask":
                continue
            split_task_keys.append(task_key)
            params = task_cfg.get("params", {})
            if not isinstance(params, dict):
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params",
                        message="LlamaCloudSplitTask params must be a mapping.",
                        code="split-params-not-mapping",
                    )
                )
                continue

            if params.get("enabled", False):
                if not params.get("configuration_id") and not params.get("categories"):
                    findings.append(
                        _finding(
                            severity="error",
                            path=f"tasks.{task_key}.params.categories",
                            message="Enabled LlamaCloudSplitTask requires categories or configuration_id.",
                            code="split-missing-categories-or-configuration",
                        )
                    )
                if not params.get("api_key") and not params.get("adapter"):
                    findings.append(
                        _finding(
                            severity="warning",
                            path=f"tasks.{task_key}.params.api_key",
                            message="Enabled LlamaCloudSplitTask needs api_key at runtime unless an adapter is injected by tests.",
                            code="split-missing-runtime-api-key",
                        )
                    )

            allow_uncategorized = params.get("allow_uncategorized", "include")
            if allow_uncategorized not in {"include", "forbid", "omit"}:
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params.allow_uncategorized",
                        message="allow_uncategorized must be one of include, forbid, or omit.",
                        code="split-invalid-allow-uncategorized",
                    )
                )

            categories = params.get("categories")
            if categories is not None and (
                not isinstance(categories, list)
                or any(not isinstance(category, dict) or not category.get("name") for category in categories)
            ):
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params.categories",
                        message="Split categories must be a list of mappings with a name.",
                        code="split-invalid-categories",
                    )
                )

        for task_key in split_task_keys:
            if task_key in pipeline and pipeline.index(task_key) == len(pipeline) - 1:
                findings.append(
                    _finding(
                        severity="warning",
                        path="pipeline",
                        message="Split task is the final pipeline step; fan-out children will have no downstream work.",
                        code="split-final-pipeline-step",
                    )
                )
        return findings

    def _validate_schema_references(self, config_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate schema references used by review-gate tasks."""
        if self.config_manager is None:
            return []
        findings: list[dict[str, Any]] = []
        schema_service = SchemaService(self.config_manager)
        for task_key, task_cfg in _iter_tasks(config_data):
            if task_cfg.get("class") != "ReviewGateTask":
                continue
            params = task_cfg.get("params", {})
            if not isinstance(params, dict) or not params.get("schema_file"):
                continue
            schema_name = str(params["schema_file"])
            if schema_service.load_schema(schema_name) is None:
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params.schema_file",
                        message=f"Schema file could not be loaded: {schema_name}",
                        code="review-gate-schema-not-found",
                        details={"schema_file": schema_name},
                    )
                )
                continue
            schema = schema_service.load_schema(schema_name)
            if schema:
                for issue in schema_service.validate_schema(schema):
                    findings.append(
                        _finding(
                            severity="error",
                            path=f"schemas.{schema_name}.{issue['path']}",
                            message=issue["message"],
                            code="schema-invalid",
                        )
                    )
        return findings


def validate_all_schemas(config_manager: ConfigManager) -> dict[str, Any]:
    """Validate all configured schema files."""
    schema_service = SchemaService(config_manager)
    findings: list[dict[str, Any]] = []
    for schema_info in schema_service.list_schemas():
        schema_name = str(schema_info["name"])
        schema = schema_service.load_schema(schema_name)
        if schema is None:
            findings.append(
                _finding(
                    severity="error",
                    path=f"schemas.{schema_name}",
                    message=f"Schema file could not be loaded: {schema_name}",
                    code="schema-load-failed",
                )
            )
            continue
        for issue in schema_service.validate_schema(schema):
            findings.append(
                _finding(
                    severity="error",
                    path=f"schemas.{schema_name}.{issue['path']}",
                    message=issue["message"],
                    code="schema-invalid",
                )
            )
    return {
        "valid": not findings,
        "findings": findings,
    }


def _iter_tasks(config_data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return well-formed task mappings from a config payload."""
    tasks = config_data.get("tasks")
    if not isinstance(tasks, dict):
        return []
    return [
        (str(task_key), task_cfg)
        for task_key, task_cfg in tasks.items()
        if isinstance(task_cfg, dict)
    ]
