"""Pipeline-specific validation service for UI/API callers."""

from __future__ import annotations

from typing import Any

from modules.config_protocol import ConfigProvider as ConfigManager
from modules.services.schema_service import SchemaService
from modules.services.task_registry_service import ApprovedTaskRegistry
from tools.config_check.parameter_validator import validate_parameters
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
        parameter_result = validate_parameters(config_data)
        findings.extend(
            _finding(
                severity="error",
                path=issue.path,
                message=issue.message,
                code=issue.code,
                details=issue.details,
            )
            for issue in parameter_result.errors
        )
        findings.extend(
            _finding(
                severity="warning",
                path=issue.path,
                message=issue.message,
                code=issue.code,
                details=issue.details,
            )
            for issue in parameter_result.warnings
        )
        findings.extend(self._validate_review_gate(config_data))
        findings.extend(self._validate_split(config_data))
        findings.extend(self._validate_pipeline_task_cardinality(config_data))
        findings.extend(self._validate_task_approvals(config_data))
        findings.extend(self._validate_schema_references(config_data))

        findings = _dedupe_findings(findings)
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

    def _validate_task_approvals(self, config_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate that active pipeline tasks are approved for dynamic import."""
        return ApprovedTaskRegistry(self.config_manager, config_data=config_data).validate_pipeline_config(config_data)

    def _validate_pipeline_task_cardinality(self, config_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate required singleton task types and dependency ordering."""
        raw_pipeline = config_data.get("pipeline")
        pipeline: list[Any] = raw_pipeline if isinstance(raw_pipeline, list) else []
        raw_tasks = config_data.get("tasks")
        tasks: dict[str, Any] = raw_tasks if isinstance(raw_tasks, dict) else {}
        occurrences: dict[str, list[dict[str, Any]]] = {
            "extract": [],
            "split": [],
            "review": [],
        }
        duplicate_type_occurrences: dict[str, list[dict[str, Any]]] = {}

        for index, task_key in enumerate(pipeline):
            if not isinstance(task_key, str):
                continue
            task_cfg = tasks.get(task_key)
            if not isinstance(task_cfg, dict):
                continue
            task_type = _pipeline_task_type(task_cfg)
            occurrence = {"task_key": task_key, "index": index, "path": f"pipeline[{index}]"}
            if task_type in occurrences:
                occurrences[task_type].append(occurrence)
            else:
                duplicate_type = _duplicate_warning_type(task_cfg)
                duplicate_type_occurrences.setdefault(duplicate_type, []).append(occurrence)

        findings: list[dict[str, Any]] = []
        labels = {
            "extract": "extract",
            "split": "split",
            "review": "review gate",
        }
        codes = {
            "extract": "pipeline-multiple-extract-tasks",
            "split": "pipeline-multiple-split-tasks",
            "review": "pipeline-multiple-review-gate-tasks",
        }
        for task_type, matches in occurrences.items():
            if len(matches) <= 1:
                continue
            findings.append(
                _finding(
                    severity="error",
                    path=matches[1]["path"],
                    message=(
                        f"Workflow pipeline can include only one {labels[task_type]} task; "
                        f"found {len(matches)}."
                    ),
                    code=codes[task_type],
                    details={"task_type": task_type, "task_keys": [match["task_key"] for match in matches]},
                )
            )

        extract_matches = occurrences["extract"]
        split_matches = occurrences["split"]
        review_matches = occurrences["review"]
        if split_matches and extract_matches and split_matches[0]["index"] > extract_matches[0]["index"]:
            findings.append(
                _finding(
                    severity="error",
                    path=split_matches[0]["path"],
                    message="Split task must be configured before the extract task.",
                    code="pipeline-split-after-extract",
                    details={
                        "split_task": split_matches[0]["task_key"],
                        "extract_task": extract_matches[0]["task_key"],
                    },
                )
            )
        if review_matches and extract_matches and review_matches[0]["index"] < extract_matches[0]["index"]:
            findings.append(
                _finding(
                    severity="error",
                    path=review_matches[0]["path"],
                    message="Review gate task must be configured after the extract task.",
                    code="pipeline-review-before-extract",
                    details={
                        "review_task": review_matches[0]["task_key"],
                        "extract_task": extract_matches[0]["task_key"],
                    },
                )
            )

        for duplicate_type, matches in duplicate_type_occurrences.items():
            if len(matches) <= 1:
                continue
            findings.append(
                _finding(
                    severity="warning",
                    path=matches[1]["path"],
                    message=(
                        f"Task type '{duplicate_type}' appears multiple times in the pipeline. "
                        "This is allowed, but verify the duplicate is intentional."
                    ),
                    code="pipeline-duplicate-task-type",
                    details={
                        "task_type": duplicate_type,
                        "task_keys": [match["task_key"] for match in matches],
                    },
                )
            )

        return findings

    def _validate_split(self, config_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate split task parameters and fan-out/fan-in assumptions."""
        findings: list[dict[str, Any]] = []
        raw_pipeline = config_data.get("pipeline")
        pipeline: list[Any] = raw_pipeline if isinstance(raw_pipeline, list) else []
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

            if not isinstance(params.get("split_dir"), str) or not params.get("split_dir", "").strip():
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params.split_dir",
                        message="LlamaCloudSplitTask requires split_dir.",
                        code="split-missing-split-dir",
                    )
                )

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

            fail_levels = params.get("fail_on_confidence_levels")
            if fail_levels is not None:
                allowed_levels = {"high", "medium", "low"}
                if (
                    not isinstance(fail_levels, list)
                    or any(not isinstance(level, str) or level.strip().lower() not in allowed_levels for level in fail_levels)
                ):
                    findings.append(
                        _finding(
                            severity="error",
                            path=f"tasks.{task_key}.params.fail_on_confidence_levels",
                            message="fail_on_confidence_levels must be a list containing high, medium, or low.",
                            code="split-invalid-fail-on-confidence-levels",
                        )
                    )

            fail_unknown = params.get("fail_on_unknown_category")
            if fail_unknown is not None and not isinstance(fail_unknown, bool):
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params.fail_on_unknown_category",
                        message="fail_on_unknown_category must be a boolean.",
                        code="split-invalid-fail-on-unknown-category",
                    )
                )

            allowed_categories = params.get("allowed_categories")
            if allowed_categories is not None and (
                not isinstance(allowed_categories, list)
                or any(not isinstance(category, str) or not category.strip() for category in allowed_categories)
            ):
                findings.append(
                    _finding(
                        severity="error",
                        path=f"tasks.{task_key}.params.allowed_categories",
                        message="allowed_categories must be a list of non-empty strings.",
                        code="split-invalid-allowed-categories",
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


def _dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return findings without repeated severity, code, path, and message values."""
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for finding in findings:
        marker = (
            str(finding.get("severity") or ""),
            str(finding.get("code") or ""),
            str(finding.get("path") or ""),
            str(finding.get("message") or ""),
        )
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(finding)
    return deduped


def _pipeline_task_type(task_cfg: dict[str, Any]) -> str:
    """Classify singleton pipeline task types used by workflow validation."""
    module_name = str(task_cfg.get("module") or "")
    class_name = str(task_cfg.get("class") or "")
    if ".extraction." in module_name or class_name == "ExtractPdfTask":
        return "extract"
    if ".split." in module_name or class_name == "LlamaCloudSplitTask":
        return "split"
    if module_name == "standard_step.review.review_gate" or class_name == "ReviewGateTask":
        return "review"
    return "other"


def _duplicate_warning_type(task_cfg: dict[str, Any]) -> str:
    """Return the task type label used for non-blocking duplicate warnings."""
    module_name = str(task_cfg.get("module") or "")
    class_name = str(task_cfg.get("class") or "")
    return f"{module_name}.{class_name}" if module_name or class_name else "unknown"
