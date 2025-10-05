"""Schema definitions and helpers for config-check.

Defines Pydantic models for the configuration format along with helpers to
validate user-supplied configuration data and emit actionable diagnostics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


class WebConfig(BaseModel):
    """Configuration for the web upload component."""

    model_config = ConfigDict(extra="allow")

    upload_dir: str = Field(
        ..., min_length=1, description="Directory where uploaded files are stored"
    )
    secret_key: str = Field(
        ...,
        min_length=1,
        description="Secret key used for signing sessions and CSRF tokens",
    )


class AuthenticationConfig(BaseModel):
    """Authentication credentials for accessing the web interface."""

    model_config = ConfigDict(extra="allow")

    username: str = Field(
        ..., min_length=1, description="Username used to authenticate web requests"
    )
    password_hash: str = Field(
        ...,
        min_length=1,
        pattern=r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$",
        description="BCrypt password hash protecting the authentication user",
    )


class WatchFolderConfig(BaseModel):
    """Configuration for the watch folder monitor."""

    model_config = ConfigDict(extra="allow")

    dir: str = Field(
        ..., min_length=1, description="Directory monitored for new PDF files"
    )
    recursive: Optional[bool] = Field(
        default=False,
        description="Monitor sub-directories when set to True",
    )


class TaskDefinition(BaseModel):
    """Definition of a single task entry under tasks.*."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    module: str = Field(..., min_length=1, description="Python module implementing the task")
    class_name: str = Field(
        ..., min_length=1, alias="class", description="Class name implementing the task"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary keyword arguments passed to the task constructor",
    )
    on_error: Optional[str] = Field(
        default=None,
        description="Task error handling policy: 'stop' or 'continue'",
    )

    @field_validator("params", mode="before")
    @classmethod
    def _coerce_params(cls, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        raise TypeError("params must be a mapping of key/value pairs")

    @field_validator("on_error")
    @classmethod
    def _validate_on_error(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError("on_error must be 'stop' or 'continue'")
        normalized = value.lower().strip()
        if normalized not in {"stop", "continue"}:
            raise ValueError("on_error must be 'stop' or 'continue'")
        return normalized


class ConfigModel(BaseModel):
    """Top-level configuration model for the PDF processing system."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    web: WebConfig = Field(..., description="Web server configuration")
    watch_folder: WatchFolderConfig = Field(
        ..., description="Watch folder configuration"
    )
    tasks: Dict[str, TaskDefinition] = Field(
        ..., min_length=1, description="Mapping of task identifiers to their definitions"
    )
    pipeline: List[str] = Field(
        ..., min_length=1, description="Ordered execution pipeline referencing task keys"
    )

    # Optional sections (schema remains open-ended for future expansion)
    logging: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional logging configuration block"
    )
    authentication: AuthenticationConfig = Field(
        ..., description="Authentication settings for the web interface"
    )
    secrets: Optional[Dict[str, Any]] = Field(
        default=None, description="Secret management configuration"
    )

    # Metadata fields common to several installations
    name: Optional[str] = Field(default=None, description="Friendly configuration name")
    description: Optional[str] = Field(
        default=None, description="Human readable description of this configuration"
    )
    version: Optional[str] = Field(default=None, description="Configuration version string")

    @field_validator("tasks")
    @classmethod
    def _ensure_tasks_not_empty(cls, value: Dict[str, TaskDefinition]) -> Dict[str, TaskDefinition]:
        if not value:
            raise ValueError("at least one task must be defined")
        return value

    @field_validator("pipeline")
    @classmethod
    def _validate_pipeline_entries(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("pipeline must contain at least one task reference")
        cleaned: List[str] = []
        for idx, item in enumerate(value):
            if not isinstance(item, str):
                raise TypeError(f"pipeline[{idx}] must be a string referencing a task id")
            if not item.strip():
                raise ValueError(f"pipeline[{idx}] must be a non-empty task id")
            cleaned.append(item.strip())
        return cleaned


@dataclass(slots=True)
class SchemaValidationIssue:
    """Represents a single schema validation error or warning."""

    path: str
    message: str


@dataclass(slots=True)
class SchemaValidationResult:
    """Collection of schema validation findings along with the parsed model."""

    model: Optional[ConfigModel]
    errors: List[SchemaValidationIssue]
    warnings: List[SchemaValidationIssue]


def load_config_schema() -> Dict[str, Any]:
    """Return the JSON schema describing the configuration model."""

    return ConfigModel.model_json_schema()


def validate_config_against_schema(
    config_data: Dict[str, Any], *, strict: bool = False
) -> SchemaValidationResult:
    """Validate raw configuration data against the schema.

    Args:
        config_data: Raw configuration data loaded from YAML.
        strict: If True unknown keys are treated as errors; otherwise warnings.

    Returns:
        SchemaValidationResult with parsed model (when valid) and findings.
    """

    errors: List[SchemaValidationIssue] = []
    warnings: List[SchemaValidationIssue] = []

    try:
        model = ConfigModel.model_validate(config_data)
    except ValidationError as exc:
        logger.debug("Schema validation failed: %s", exc)
        errors.extend(_convert_validation_errors(exc))
        return SchemaValidationResult(model=None, errors=errors, warnings=warnings)

    extras = list(_collect_extra_fields(model))
    if extras:
        target = errors if strict else warnings
        level_message = (
            "Unknown key is not permitted in strict mode"
            if strict
            else "Unknown key not defined by schema"
        )
        for path in extras:
            target.append(
                SchemaValidationIssue(
                    path=path,
                    message=level_message,
                )
            )

    return SchemaValidationResult(model=model, errors=errors, warnings=warnings)


def _convert_validation_errors(exc: ValidationError) -> Iterable[SchemaValidationIssue]:
    for error in exc.errors():
        loc = error.get("loc", ())
        path = _format_location(loc)
        msg = error.get("msg", "Invalid value")
        yield SchemaValidationIssue(path=path or "root", message=msg)


def _format_location(location: Iterable[Any]) -> str:
    parts: List[str] = []
    for entry in location:
        if isinstance(entry, int):
            if not parts:
                parts.append(f"[{entry}]")
            else:
                parts[-1] = f"{parts[-1]}[{entry}]"
        else:
            parts.append(str(entry))
    return ".".join(parts)


def _collect_extra_fields(model: BaseModel, prefix: str = "") -> Iterable[str]:
    model_extra = getattr(model, "model_extra", None) or {}
    for key in model_extra:
        yield f"{prefix}.{key}".lstrip(".")

    field_items = getattr(model.__class__, "model_fields", {})
    for field_name in field_items:
        value = getattr(model, field_name)
        if isinstance(value, BaseModel):
            next_prefix = f"{prefix}.{field_name}".lstrip(".")
            yield from _collect_extra_fields(value, next_prefix)
        elif isinstance(value, dict):
            next_prefix = f"{prefix}.{field_name}".lstrip(".")
            for sub_key, sub_value in value.items():
                sub_prefix = f"{next_prefix}.{sub_key}" if next_prefix else str(sub_key)
                if isinstance(sub_value, BaseModel):
                    yield from _collect_extra_fields(sub_value, sub_prefix)
        elif isinstance(value, list):
            next_prefix = f"{prefix}.{field_name}".lstrip(".")
            for idx, item in enumerate(value):
                if isinstance(item, BaseModel):
                    yield from _collect_extra_fields(item, f"{next_prefix}[{idx}]")
