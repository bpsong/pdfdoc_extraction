"""Shared contracts for versioned pipeline and review-schema configuration."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Callable, Iterator, Literal, Mapping, NotRequired, TypedDict


PIPELINE_DEFINITION_SCHEMA_VERSION = 1
REVIEW_SCHEMA_FORMAT_VERSION = 1
PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION = 1
REDACTED_VALUE = "[REDACTED]"
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
SECRET_ALIAS_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
SECRET_KEY_PARTS = ("api_key", "password", "secret", "token", "credential")

ValidationSourceKind = Literal[
    "runtime",
    "pipeline_draft",
    "pipeline_version",
    "review_schema_draft",
    "review_schema_version",
    "portable_pipeline",
    "portable_review_schema",
]
LifecycleState = Literal["active", "inactive", "archived"]


SecretReference = TypedDict("SecretReference", {"$secret": str})
PipelineTaskDefinition = TypedDict(
    "PipelineTaskDefinition",
    {
        "module": str,
        "class": str,
        "params": dict[str, Any],
        "label": str,
        "on_error": str,
    },
    total=False,
)


class PipelineDefinition(TypedDict):
    """Complete executable pipeline definition contract."""

    schema_version: int
    pipeline: list[str]
    tasks: dict[str, dict[str, Any]]


class ReviewSchemaDefinition(TypedDict):
    """Canonical review UI and payload validation contract."""

    fields: dict[str, dict[str, Any]]
    title: NotRequired[str]
    description: NotRequired[str]


class VersionSummary(TypedDict):
    """Transport-safe immutable-version identity."""

    id: str
    version_number: int
    content_hash: str


class SchemaDependency(TypedDict):
    """Exact review dependency attributed to one pipeline task."""

    task_key: str
    schema_version_id: str


class VersionedConfigError(ValueError):
    """Base error for invalid versioned configuration."""


class CanonicalizationError(VersionedConfigError):
    """Raised when a value cannot be represented as canonical JSON."""


class SecretReferenceError(VersionedConfigError):
    """Raised when a secret reference is malformed or unresolved."""


class RuntimeResolvedDefinition(Mapping[str, Any]):
    """Read-only runtime mapping intentionally unsupported by JSON encoders."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = dict(values)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


@dataclass(frozen=True, slots=True)
class ValidationSource:
    """Stable identity for one validation target."""

    kind: ValidationSourceKind
    key: str | None = None
    revision: int | None = None
    version_number: int | None = None

    @property
    def prefix(self) -> str:
        """Return the finding-path prefix for this source."""
        if self.kind == "runtime":
            return "runtime"
        key = self.key or "unknown"
        label = self.kind.replace("_", "-")
        if self.revision is not None:
            return f"{label}:{key}@draft-r{self.revision}"
        if self.version_number is not None:
            return f"{label}:{key}@{self.version_number}"
        return f"{label}:{key}"


@dataclass(frozen=True, slots=True)
class ReviewSchemaCoordinate:
    """Portable identity for an immutable review-schema version."""

    key: str
    version_number: int
    content_hash: str


def normalize_key(value: str, *, label: str = "key") -> str:
    """Return a validated lowercase kebab-case key."""
    normalized = str(value or "").strip().lower()
    if not KEY_PATTERN.fullmatch(normalized):
        raise VersionedConfigError(
            f"{label} must be lowercase kebab-case and start with a letter."
        )
    return normalized


def normalize_lifecycle(value: str) -> LifecycleState:
    """Return a supported normalized template lifecycle state."""
    normalized = str(value or "").strip().lower()
    if normalized not in {"active", "inactive", "archived"}:
        raise VersionedConfigError("Lifecycle state must be active, inactive, or archived.")
    return normalized  # type: ignore[return-value]


def validate_secret_alias(value: str) -> str:
    """Return a validated secret alias."""
    alias = str(value or "").strip()
    if not SECRET_ALIAS_PATTERN.fullmatch(alias):
        raise SecretReferenceError(
            "Secret alias must start with a lowercase letter and contain only "
            "lowercase letters, numbers, hyphens, or underscores."
        )
    return alias


def is_secret_key(value: str) -> bool:
    """Return whether a parameter key is secret-like."""
    lowered = str(value or "").lower()
    return any(part in lowered for part in SECRET_KEY_PARTS)


def is_secret_reference(value: Any) -> bool:
    """Return whether value is an exact secret-reference object."""
    return (
        isinstance(value, dict)
        and set(value) == {"$secret"}
        and isinstance(value["$secret"], str)
    )


def canonicalize_json(value: Any) -> Any:
    """Return a JSON-only deep copy with deterministic object-key order."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("Non-finite numbers are not valid JSON.")
        return value
    if isinstance(value, list):
        return [canonicalize_json(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise CanonicalizationError("JSON object keys must be strings.")
            normalized[key] = canonicalize_json(value[key])
        return normalized
    raise CanonicalizationError(
        f"Unsupported non-JSON value type: {type(value).__name__}."
    )


def canonical_json_text(value: Any) -> str:
    """Serialize a value as canonical UTF-8 JSON text."""
    return json.dumps(
        canonicalize_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    """Return the SHA-256 hash of canonical unresolved JSON."""
    return hashlib.sha256(canonical_json_text(value).encode("utf-8")).hexdigest()


def validate_secret_references(value: Any, *, path: str = "") -> list[str]:
    """Return paths containing malformed references or literal secret values."""
    findings: list[str] = []
    if isinstance(value, dict):
        if "$secret" in value:
            if not is_secret_reference(value):
                findings.append(path or "$")
                return findings
            try:
                validate_secret_alias(value["$secret"])
            except SecretReferenceError:
                findings.append(path or "$")
            return findings
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if is_secret_key(str(key)) and not is_secret_reference(item):
                findings.append(child_path)
                continue
            findings.extend(validate_secret_references(item, path=child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            findings.extend(validate_secret_references(item, path=child_path))
    return findings


def _resolve_secret_value(value: Any, secrets: Mapping[str, Any]) -> Any:
    if is_secret_reference(value):
        alias = validate_secret_alias(value["$secret"])
        if alias not in secrets or secrets[alias] in (None, ""):
            raise SecretReferenceError(f"Secret alias is not configured: {alias}")
        return secrets[alias]
    if isinstance(value, dict):
        if "$secret" in value:
            raise SecretReferenceError("Malformed secret reference object.")
        return {
            str(key): _resolve_secret_value(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_resolve_secret_value(item, secrets) for item in value]
    return value


def resolve_secret_references(
    value: Mapping[str, Any], secrets: Mapping[str, Any]
) -> RuntimeResolvedDefinition:
    """Return a non-serializable runtime mapping with secret aliases resolved."""
    resolved = _resolve_secret_value(dict(value), secrets)
    return RuntimeResolvedDefinition(resolved)


def replace_secret_references_for_validation(value: Any) -> Any:
    """Return a validation-only copy with references represented by placeholders."""
    if is_secret_reference(value):
        validate_secret_alias(value["$secret"])
        return "configured-secret-reference"
    if isinstance(value, dict):
        return {
            str(key): replace_secret_references_for_validation(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [replace_secret_references_for_validation(item) for item in value]
    return value


def redact_sensitive(
    value: Any,
    *,
    secret_configured: Callable[[str], bool] | None = None,
) -> Any:
    """Return a display-safe deep copy that never contains secret values."""
    if is_secret_reference(value):
        alias = validate_secret_alias(value["$secret"])
        redacted: dict[str, Any] = {"$secret": alias}
        if secret_configured is not None:
            redacted["configured"] = bool(secret_configured(alias))
        return redacted
    if isinstance(value, dict):
        redacted_mapping: dict[str, Any] = {}
        for key, item in value.items():
            if is_secret_key(str(key)) and not is_secret_reference(item):
                redacted_mapping[str(key)] = REDACTED_VALUE
            else:
                redacted_mapping[str(key)] = redact_sensitive(
                    item,
                    secret_configured=secret_configured,
                )
        return redacted_mapping
    if isinstance(value, list):
        return [
            redact_sensitive(item, secret_configured=secret_configured)
            for item in value
        ]
    return value


def preserve_secret_references(
    submitted: Any,
    existing: Any,
    *,
    placeholder: str = REDACTED_VALUE,
) -> Any:
    """Replace UI placeholders with existing references, never secret values."""
    if submitted == placeholder:
        if not is_secret_reference(existing):
            raise SecretReferenceError(
                "A redacted placeholder has no existing secret reference."
            )
        return dict(existing)
    if isinstance(submitted, dict):
        existing_mapping = existing if isinstance(existing, dict) else {}
        return {
            str(key): preserve_secret_references(
                item, existing_mapping.get(key), placeholder=placeholder
            )
            for key, item in submitted.items()
        }
    if isinstance(submitted, list):
        existing_list = existing if isinstance(existing, list) else []
        return [
            preserve_secret_references(
                item,
                existing_list[index] if index < len(existing_list) else None,
                placeholder=placeholder,
            )
            for index, item in enumerate(submitted)
        ]
    return submitted


def build_display_snapshot(definition: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic parameter-free pipeline display snapshot."""
    pipeline = definition.get("pipeline")
    tasks = definition.get("tasks")
    pipeline_entries = pipeline if isinstance(pipeline, list) else []
    task_mapping = tasks if isinstance(tasks, dict) else {}
    steps: list[dict[str, Any]] = []
    for position, task_key in enumerate(pipeline_entries):
        if not isinstance(task_key, str):
            continue
        raw_task = task_mapping.get(task_key)
        task = raw_task if isinstance(raw_task, dict) else {}
        steps.append(
            {
                "key": task_key,
                "label": str(task.get("label") or task_key.replace("_", " ").title()),
                "module": str(task.get("module") or ""),
                "class": str(task.get("class") or ""),
                "position": position,
                "on_error": task.get("on_error"),
            }
        )
    snapshot_basis = {"version": 1, "steps": steps}
    return {
        **snapshot_basis,
        "content_hash": content_hash(snapshot_basis),
        "step_count": len(steps),
    }
