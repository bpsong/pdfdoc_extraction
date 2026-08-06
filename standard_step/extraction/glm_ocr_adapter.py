"""Local Ollama adapter for schema-directed GLM-OCR PDF extraction."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import jsonschema
import ollama
import pymupdf

from modules.utils import windows_long_path
from standard_step.extraction.glm_ocr_prompt import (
    GlmOcrSchemaBundle,
    build_glm_ocr_schemas,
    build_scalar_object_prompt,
    build_table_prompt,
)
from standard_step.extraction.structured_fields import (
    FieldNormalizationFinding,
    get_extracted_value,
    is_optional_type,
    normalize_configured_fields,
    normalize_scalar_field,
    normalize_table_field,
)


class GlmOcrAdapterError(RuntimeError):
    """Base class for safe local extraction adapter failures."""


class GlmOcrUnavailableError(GlmOcrAdapterError):
    """Raised when the configured Ollama service cannot be reached."""


class GlmOcrModelNotFoundError(GlmOcrAdapterError):
    """Raised when Ollama does not advertise the configured model."""


class GlmOcrTimeoutError(GlmOcrAdapterError):
    """Raised when a local model request exceeds its timeout."""


class GlmOcrResponseError(GlmOcrAdapterError):
    """Raised for invalid or incomplete Ollama response envelopes."""


class GlmOcrPdfError(GlmOcrAdapterError):
    """Raised when a PDF cannot be safely opened or rendered."""


@dataclass(frozen=True, slots=True)
class GlmOcrCallRecord:
    """Non-sensitive metadata for one page/model call."""

    page_number: int
    call_type: str
    duration_seconds: float
    completion_reason: str | None
    prompt_hash: str
    schema_hash: str


@dataclass(frozen=True, slots=True)
class GlmOcrConflict:
    """Describe a value conflict without retaining either raw value."""

    path: str
    retained_page: int
    conflicting_page: int


@dataclass(frozen=True, slots=True)
class GlmOcrAdapterFinding:
    """Describe a non-fatal response or final-schema issue."""

    path: str
    code: str
    message: str
    page_number: int | None = None
    call_type: str | None = None


@dataclass(slots=True)
class GlmOcrAdapterResult:
    """Merged normalized data and safe extraction evidence."""

    data: dict[str, Any]
    page_count: int
    field_pages: dict[str, list[int]]
    calls: list[GlmOcrCallRecord]
    findings: list[GlmOcrAdapterFinding] = field(default_factory=list)
    normalization_findings: list[FieldNormalizationFinding] = field(
        default_factory=list
    )
    conflicts: list[GlmOcrConflict] = field(default_factory=list)


class GlmOcrAdapter:
    """Render PDFs and run deterministic schema-directed Ollama calls."""

    def __init__(
        self,
        *,
        ollama_host: str,
        model: str,
        dpi: int = 216,
        num_ctx: int = 8192,
        num_predict: int = 2048,
        timeout_seconds: float = 300,
        client: Any | None = None,
        client_factory: Callable[..., Any] = ollama.Client,
    ) -> None:
        if dpi <= 0 or num_ctx <= 0 or num_predict <= 0 or timeout_seconds <= 0:
            raise ValueError("GLM-OCR numeric settings must be greater than zero")
        if not isinstance(ollama_host, str) or not ollama_host.strip():
            raise ValueError("ollama_host must be a non-empty string")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        self.ollama_host = ollama_host.strip()
        self.model = model.strip()
        self.dpi = dpi
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._client_factory = client_factory

    def extract(
        self,
        file_path: str,
        fields: dict[str, Any],
        *,
        document_instructions: str = "",
    ) -> GlmOcrAdapterResult:
        """Extract and merge configured values from all pages of one PDF."""
        schemas = build_glm_ocr_schemas(fields)
        client = self._get_client()
        self._validate_runtime(client)
        page_images = self.render_pdf(file_path)
        calls: list[GlmOcrCallRecord] = []
        findings: list[GlmOcrAdapterFinding] = []
        normalization_findings: list[FieldNormalizationFinding] = []
        conflicts: list[GlmOcrConflict] = []
        field_pages: dict[str, list[int]] = {key: [] for key in fields}
        merged: dict[str, Any] = {}
        if schemas.table_field_key is not None:
            merged[schemas.table_field_key] = []
        scalar_pages: dict[str, int] = {}
        object_child_pages: dict[str, int] = {}
        seen_table_rows: set[str] = set()
        parsed_response_count = 0

        scalar_prompt = None
        if schemas.scalar_page_schema is not None:
            scalar_prompt = build_scalar_object_prompt(
                schemas.scalar_fields,
                schemas.scalar_page_schema,
                document_instructions=document_instructions,
            )
        table_prompt = None
        if (
            schemas.table_page_schema is not None
            and schemas.table_field_key is not None
            and schemas.table_field is not None
        ):
            table_prompt = build_table_prompt(
                schemas.table_field_key,
                schemas.table_field,
                schemas.table_page_schema,
                document_instructions=document_instructions,
            )

        for page_number, image_bytes in enumerate(page_images, start=1):
            if scalar_prompt is not None and schemas.scalar_page_schema is not None:
                page_data, record = self._call_model(
                    client,
                    page_number=page_number,
                    call_type="scalar_object",
                    image_bytes=image_bytes,
                    prompt=scalar_prompt,
                    schema=schemas.scalar_page_schema,
                )
                parsed_response_count += 1
                calls.append(record)
                findings.extend(
                    _schema_findings(
                        page_data,
                        schemas.scalar_page_schema,
                        page_number=page_number,
                        call_type="scalar_object",
                    )
                )
                self._merge_scalar_fields(
                    page_data,
                    schemas,
                    page_number,
                    merged,
                    scalar_pages,
                    object_child_pages,
                    field_pages,
                    normalization_findings,
                    conflicts,
                )
                recovery_fields = _missing_required_scalar_fields(
                    page_data,
                    schemas.scalar_fields,
                )
                if recovery_fields:
                    recovery_schemas = build_glm_ocr_schemas(recovery_fields)
                    if recovery_schemas.scalar_page_schema is None:
                        raise GlmOcrResponseError(
                            "GLM-OCR could not build a scalar recovery schema"
                        )
                    recovery_prompt = build_scalar_object_prompt(
                        recovery_fields,
                        recovery_schemas.scalar_page_schema,
                        document_instructions=document_instructions,
                        recovery_pass=True,
                    )
                    recovery_data, recovery_record = self._call_model(
                        client,
                        page_number=page_number,
                        call_type="scalar_recovery",
                        image_bytes=image_bytes,
                        prompt=recovery_prompt,
                        schema=recovery_schemas.scalar_page_schema,
                    )
                    parsed_response_count += 1
                    calls.append(recovery_record)
                    findings.extend(
                        _schema_findings(
                            recovery_data,
                            recovery_schemas.scalar_page_schema,
                            page_number=page_number,
                            call_type="scalar_recovery",
                        )
                    )
                    self._merge_scalar_fields(
                        recovery_data,
                        recovery_schemas,
                        page_number,
                        merged,
                        scalar_pages,
                        object_child_pages,
                        field_pages,
                        normalization_findings,
                        conflicts,
                    )

            if table_prompt is not None and schemas.table_page_schema is not None:
                page_data, record = self._call_model(
                    client,
                    page_number=page_number,
                    call_type="table",
                    image_bytes=image_bytes,
                    prompt=table_prompt,
                    schema=schemas.table_page_schema,
                )
                parsed_response_count += 1
                calls.append(record)
                findings.extend(
                    _schema_findings(
                        page_data,
                        schemas.table_page_schema,
                        page_number=page_number,
                        call_type="table",
                    )
                )
                self._merge_table_field(
                    page_data,
                    schemas,
                    page_number,
                    merged,
                    field_pages,
                    seen_table_rows,
                    normalization_findings,
                )

        if parsed_response_count == 0:
            raise GlmOcrResponseError(
                "GLM-OCR returned no parseable structured response"
            )

        normalized = normalize_configured_fields(
            merged,
            fields,
            include_missing=True,
        )
        normalization_findings.extend(normalized.findings)
        findings.extend(_schema_findings(normalized.data, schemas.canonical_schema))
        return GlmOcrAdapterResult(
            data=normalized.data,
            page_count=len(page_images),
            field_pages=field_pages,
            calls=calls,
            findings=findings,
            normalization_findings=normalization_findings,
            conflicts=conflicts,
        )

    def render_pdf(self, file_path: str) -> list[bytes]:
        """Render every PDF page to PNG bytes while reliably closing resources."""
        if not isinstance(file_path, str) or not file_path.strip():
            raise GlmOcrPdfError("PDF path was not provided")
        normalized_path = windows_long_path(file_path)
        if not os.path.isfile(normalized_path):
            raise GlmOcrPdfError("PDF file does not exist or is not readable")

        document: Any | None = None
        try:
            document = pymupdf.open(normalized_path)
            if document.page_count < 1:
                raise GlmOcrPdfError("PDF contains no pages")
            scale = self.dpi / 72.0
            matrix = pymupdf.Matrix(scale, scale)
            images: list[bytes] = []
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                pixmap = None
                try:
                    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                    images.append(pixmap.tobytes("png"))
                finally:
                    pixmap = None
                    page = None
            return images
        except GlmOcrPdfError:
            raise
        except Exception as exc:
            raise GlmOcrPdfError("PDF could not be opened or rendered") from exc
        finally:
            if document is not None:
                document.close()

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory(
                host=self.ollama_host,
                timeout=self.timeout_seconds,
            )
        return self._client

    def _validate_runtime(self, client: Any) -> None:
        try:
            response = client.list()
        except Exception as exc:
            raise _safe_ollama_exception(exc, during="service validation") from exc
        models = _response_value(response, "models", [])
        names = {
            name
            for entry in models or []
            if (name := _model_name(entry)) is not None
        }
        if not any(_model_names_match(self.model, name) for name in names):
            raise GlmOcrModelNotFoundError(
                "Configured GLM-OCR model is not installed in Ollama"
            )

    def _call_model(
        self,
        client: Any,
        *,
        page_number: int,
        call_type: str,
        image_bytes: bytes,
        prompt: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], GlmOcrCallRecord]:
        started = time.perf_counter()
        try:
            response = client.generate(
                model=self.model,
                prompt=prompt,
                images=[image_bytes],
                format=schema,
                stream=False,
                options={
                    "temperature": 0,
                    "num_ctx": self.num_ctx,
                    "num_predict": self.num_predict,
                },
            )
        except Exception as exc:
            raise _safe_ollama_exception(exc, during="model generation") from exc
        duration = time.perf_counter() - started
        done = _response_value(response, "done")
        reason = _response_value(response, "done_reason")
        if done is False or str(reason or "").lower() in {
            "length",
            "max_tokens",
            "token_limit",
        }:
            raise GlmOcrResponseError(
                "GLM-OCR response was incomplete because the token limit was reached"
            )
        response_text = _response_value(response, "response")
        if not isinstance(response_text, str) or not response_text.strip():
            raise GlmOcrResponseError(
                "GLM-OCR returned an empty or invalid response envelope"
            )
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise GlmOcrResponseError(
                "GLM-OCR response was not valid JSON"
            ) from exc
        if not isinstance(parsed, dict):
            raise GlmOcrResponseError(
                "GLM-OCR response JSON must be an object"
            )
        return parsed, GlmOcrCallRecord(
            page_number=page_number,
            call_type=call_type,
            duration_seconds=duration,
            completion_reason=str(reason) if reason is not None else None,
            prompt_hash=_sha256_text(prompt),
            schema_hash=_schema_hash(schema),
        )

    @staticmethod
    def _merge_scalar_fields(
        page_data: dict[str, Any],
        schemas: GlmOcrSchemaBundle,
        page_number: int,
        merged: dict[str, Any],
        scalar_pages: dict[str, int],
        object_child_pages: dict[str, int],
        field_pages: dict[str, list[int]],
        normalization_findings: list[FieldNormalizationFinding],
        conflicts: list[GlmOcrConflict],
    ) -> None:
        for field_key, field_config in schemas.scalar_fields.items():
            alias = str(field_config.get("alias", field_key))
            found, raw_value = get_extracted_value(page_data, field_key, alias)
            if not found:
                continue
            normalized_value = normalize_scalar_field(
                raw_value,
                field_config,
                path=field_key,
                findings=normalization_findings,
            )
            if not _has_value(normalized_value):
                continue
            _append_page(field_pages[field_key], page_number)
            if isinstance(normalized_value, dict) and isinstance(
                field_config.get("object_fields"), dict
            ):
                destination = merged.setdefault(field_key, {})
                if not isinstance(destination, dict):
                    destination = {}
                    merged[field_key] = destination
                for child_key, child_value in normalized_value.items():
                    if not _has_value(child_value):
                        continue
                    path = f"{field_key}.{child_key}"
                    if child_key not in destination or not _has_value(
                        destination[child_key]
                    ):
                        destination[child_key] = child_value
                        object_child_pages[path] = page_number
                    elif not _values_equal(destination[child_key], child_value):
                        conflicts.append(
                            GlmOcrConflict(
                                path=path,
                                retained_page=object_child_pages[path],
                                conflicting_page=page_number,
                            )
                        )
                continue
            if field_key not in merged or not _has_value(merged[field_key]):
                merged[field_key] = normalized_value
                scalar_pages[field_key] = page_number
            elif not _values_equal(merged[field_key], normalized_value):
                conflicts.append(
                    GlmOcrConflict(
                        path=field_key,
                        retained_page=scalar_pages[field_key],
                        conflicting_page=page_number,
                    )
                )

    @staticmethod
    def _merge_table_field(
        page_data: dict[str, Any],
        schemas: GlmOcrSchemaBundle,
        page_number: int,
        merged: dict[str, Any],
        field_pages: dict[str, list[int]],
        seen_rows: set[str],
        normalization_findings: list[FieldNormalizationFinding],
    ) -> None:
        if schemas.table_field_key is None or schemas.table_field is None:
            return
        key = schemas.table_field_key
        alias = str(schemas.table_field.get("alias", key))
        rows = normalize_table_field(
            page_data,
            key,
            alias,
            schemas.table_field,
            findings=normalization_findings,
        )
        if not rows:
            return
        destination = merged.setdefault(key, [])
        for row in rows:
            fingerprint = _stable_json(row)
            if fingerprint in seen_rows:
                continue
            seen_rows.add(fingerprint)
            destination.append(row)
        _append_page(field_pages[key], page_number)


def _schema_findings(
    value: dict[str, Any],
    schema: dict[str, Any],
    *,
    page_number: int | None = None,
    call_type: str | None = None,
) -> list[GlmOcrAdapterFinding]:
    validator = jsonschema.Draft202012Validator(schema)
    findings: list[GlmOcrAdapterFinding] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.path)):
        path = ".".join(str(part) for part in error.absolute_path)
        findings.append(
            GlmOcrAdapterFinding(
                path=path,
                code=f"schema_{error.validator}",
                message=(
                    "Structured response did not satisfy the configured "
                    f"'{error.validator}' constraint"
                ),
                page_number=page_number,
                call_type=call_type,
            )
        )
    return findings


def _missing_required_scalar_fields(
    page_data: dict[str, Any],
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Return required scalar/object definitions not populated on one page."""
    missing: dict[str, Any] = {}
    for field_key, field_config in fields.items():
        if is_optional_type(str(field_config.get("type", "str"))):
            continue
        alias = str(field_config.get("alias", field_key))
        found, value = get_extracted_value(page_data, field_key, alias)
        if not found or not _has_value(value):
            missing[field_key] = field_config
            continue
        object_fields = field_config.get("object_fields")
        if not isinstance(object_fields, dict):
            continue
        if not isinstance(value, dict) or _missing_required_object_child(
            value,
            object_fields,
        ):
            missing[field_key] = field_config
    return missing


def _missing_required_object_child(
    value: dict[str, Any],
    fields: dict[str, Any],
) -> bool:
    """Return whether a configured required object child lacks a page value."""
    for child_key, child_config in fields.items():
        if is_optional_type(str(child_config.get("type", "str"))):
            continue
        alias = str(child_config.get("alias", child_key))
        found, child_value = get_extracted_value(value, child_key, alias)
        if not found or not _has_value(child_value):
            return True
    return False


def _safe_ollama_exception(error: Exception, *, during: str) -> GlmOcrAdapterError:
    name = type(error).__name__.lower()
    if isinstance(error, TimeoutError) or "timeout" in name:
        return GlmOcrTimeoutError(f"Ollama timed out during {during}")
    return GlmOcrUnavailableError(f"Ollama was unavailable during {during}")


def _response_value(response: Any, key: str, default: Any = None) -> Any:
    if isinstance(response, Mapping):
        return response.get(key, default)
    return getattr(response, key, default)


def _model_name(model_entry: Any) -> str | None:
    for key in ("model", "name"):
        value = _response_value(model_entry, key)
        if isinstance(value, str) and value:
            return value
    return None


def _model_names_match(requested: str, installed: str) -> bool:
    requested_lower = requested.casefold()
    installed_lower = installed.casefold()
    return installed_lower == requested_lower or (
        ":" not in requested_lower
        and installed_lower == f"{requested_lower}:latest"
    )


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _values_equal(first: Any, second: Any) -> bool:
    return _stable_json(first) == _stable_json(second)


def _append_page(pages: list[int], page_number: int) -> None:
    if page_number not in pages:
        pages.append(page_number)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _schema_hash(schema: dict[str, Any]) -> str:
    return _sha256_text(_stable_json(schema))


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
