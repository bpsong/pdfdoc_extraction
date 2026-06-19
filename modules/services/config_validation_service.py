"""Config validation service for API/UI callers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.config_protocol import ConfigProvider as ConfigManager
from modules.services.pipeline_validation_service import (
    PipelineValidationService,
    validate_all_schemas,
)
from tools.config_check.validator import ConfigValidator, ValidationMessage
from tools.config_check.yaml_parser import YAMLParser


class ConfigValidationService:
    """Wrap shared config-check validation without shelling out."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """Initialize service with the active app configuration."""
        self.config_manager = config_manager

    def validate_active_config(self) -> dict[str, Any]:
        """Validate the active config file."""
        config_path = Path(getattr(self.config_manager, "_config_path", "config.yaml"))
        validator = self._validator(base_dir=config_path.parent)
        result = validator.validate(config_path)
        return self._response(
            source=str(config_path),
            data=result.data,
            errors=result.errors,
            warnings=result.warnings,
            extra_findings=self._extra_findings(result.data),
        )

    def validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate parsed config data or YAML text from an API request."""
        config_data = self._extract_config_data(payload)
        validator = self._validator(base_dir=self._base_dir())
        result = validator.validate_config_data(config_data)
        return self._response(
            source="payload",
            data=result.data,
            errors=result.errors,
            warnings=result.warnings,
            extra_findings=self._extra_findings(result.data),
        )

    def validate_pipeline(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate only pipeline-level rules for parsed config data."""
        config_data = self._extract_config_data(payload)
        return PipelineValidationService(self.config_manager).validate(config_data)

    def validate_all_schemas(self) -> dict[str, Any]:
        """Validate all configured schema files."""
        return validate_all_schemas(self.config_manager)

    def _validator(self, *, base_dir: Path) -> ConfigValidator:
        """Build the shared config validator used by CLI and API paths."""
        return ConfigValidator(
            base_dir=base_dir,
            import_checks=False,
            check_files=False,
        )

    def _extra_findings(self, config_data: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Return pipeline and schema findings for a config payload."""
        if not isinstance(config_data, dict):
            return []
        pipeline_result = PipelineValidationService(self.config_manager).validate(config_data)
        return list(pipeline_result["findings"])

    def _extract_config_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract a config mapping from API payload shapes."""
        if "config" in payload:
            config = payload["config"]
            if not isinstance(config, dict):
                raise ValueError("payload.config must be an object")
            return config

        if "yaml" in payload or "yaml_text" in payload:
            yaml_text = payload.get("yaml", payload.get("yaml_text"))
            if not isinstance(yaml_text, str):
                raise ValueError("payload.yaml must be a string")
            data, error = YAMLParser().loads(yaml_text, source="payload.yaml")
            if error:
                raise ValueError(error)
            if not isinstance(data, dict):
                raise ValueError("payload.yaml root must be a mapping")
            return dict(data)

        if "pipeline" in payload or "tasks" in payload:
            return payload

        raise ValueError("Payload must include config, yaml, or pipeline/tasks keys")

    def _response(
        self,
        *,
        source: str,
        data: dict[str, Any] | None,
        errors: list[ValidationMessage],
        warnings: list[ValidationMessage],
        extra_findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a normalized validation response."""
        findings = [
            self._message_to_finding("error", message)
            for message in errors
        ]
        findings.extend(
            self._message_to_finding("warning", message)
            for message in warnings
        )
        findings.extend(extra_findings)
        findings = self._dedupe_findings(findings)
        return {
            "source": source,
            "valid": not any(finding["severity"] == "error" for finding in findings),
            "summary": {
                "errors": sum(1 for finding in findings if finding["severity"] == "error"),
                "warnings": sum(1 for finding in findings if finding["severity"] == "warning"),
            },
            "findings": findings,
            "normalized": data,
        }

    @staticmethod
    def _dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return findings without duplicate path/code/severity messages."""
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for finding in findings:
            marker = (
                str(finding.get("severity") or ""),
                str(finding.get("path") or ""),
                str(finding.get("code") or ""),
                str(finding.get("message") or ""),
            )
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(finding)
        return deduped

    @staticmethod
    def _message_to_finding(severity: str, message: ValidationMessage) -> dict[str, Any]:
        """Convert config-check message objects into API findings."""
        return {
            "severity": severity,
            "path": message.path,
            "message": message.message,
            "code": message.code,
            "suggestion": message.suggestion,
        }

    def _base_dir(self) -> Path:
        """Return the active config directory for path-relative validation."""
        config_path = getattr(self.config_manager, "_config_path", None)
        return Path(config_path).parent if config_path else Path.cwd()
