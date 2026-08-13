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
    TABLE_ROW_EVIDENCE_KEY,
    build_document_resolver_prompt,
    build_document_resolver_schema,
    build_glm_ocr_schemas,
    build_scalar_object_prompt,
    build_table_evidence_resolver_prompt,
    build_table_prompt,
    validate_glm_ocr_resolution_mode,
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
    """Non-sensitive metadata for one page or document model call."""

    page_number: int | None
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
        resolution_mode: str = "page_merge",
        resolver_model: str = "",
        resolver_max_dimension: int = 1280,
        resolver_num_ctx: int = 8192,
        resolver_num_predict: int = 1536,
        resolver_max_attempts: int = 2,
        timeout_seconds: float = 300,
        client: Any | None = None,
        client_factory: Callable[..., Any] = ollama.Client,
    ) -> None:
        if (
            dpi <= 0
            or num_ctx <= 0
            or num_predict <= 0
            or resolver_max_dimension <= 0
            or resolver_num_ctx <= 0
            or resolver_num_predict <= 0
            or resolver_max_attempts <= 0
            or timeout_seconds <= 0
        ):
            raise ValueError("GLM-OCR numeric settings must be greater than zero")
        if not isinstance(ollama_host, str) or not ollama_host.strip():
            raise ValueError("ollama_host must be a non-empty string")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        validate_glm_ocr_resolution_mode(resolution_mode)
        if resolution_mode == "document" and (
            not isinstance(resolver_model, str) or not resolver_model.strip()
        ):
            raise ValueError(
                "resolver_model must be a non-empty string in document mode"
            )
        if resolver_max_attempts > 5:
            raise ValueError("resolver_max_attempts must be between 1 and 5")
        if not 256 <= resolver_max_dimension <= 4096:
            raise ValueError("resolver_max_dimension must be between 256 and 4096")
        self.ollama_host = ollama_host.strip()
        self.model = model.strip()
        self.dpi = dpi
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.resolution_mode = resolution_mode
        self.resolver_model = resolver_model.strip()
        self.resolver_max_dimension = resolver_max_dimension
        self.resolver_num_ctx = resolver_num_ctx
        self.resolver_num_predict = resolver_num_predict
        self.resolver_max_attempts = resolver_max_attempts
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._client_factory = client_factory

    def extract(
        self,
        file_path: str,
        fields: dict[str, Any],
        *,
        document_instructions: str = "",
        prompt_style: str = "detailed",
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
        candidates: dict[str, list[dict[str, Any]]] = {
            key: [] for key in fields
        }
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
                prompt_style=prompt_style,
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
                prompt_style=prompt_style,
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
                    candidates,
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
                        prompt_style=prompt_style,
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
                        candidates,
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
                    candidates,
                )

        if parsed_response_count == 0:
            raise GlmOcrResponseError(
                "GLM-OCR returned no parseable structured response"
            )

        if self.resolution_mode == "document":
            resolver_page_images: list[bytes] = []
            if any(
                not field_config.get("is_table", False)
                for field_config in fields.values()
            ):
                resolver_page_images = self.render_pdf(
                    file_path,
                    max_dimension=self.resolver_max_dimension,
                )
                if len(resolver_page_images) != len(page_images):
                    raise GlmOcrPdfError(
                        "Resolver page rendering did not match the source PDF"
                    )
            merged, field_pages = self._resolve_document_fields(
                client,
                page_images=resolver_page_images,
                page_count=len(page_images),
                fields=fields,
                candidates=candidates,
                document_instructions=document_instructions,
                calls=calls,
                findings=findings,
                normalization_findings=normalization_findings,
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

    def render_pdf(
        self,
        file_path: str,
        *,
        max_dimension: int | None = None,
    ) -> list[bytes]:
        """Render every PDF page to PNG bytes while reliably closing resources."""
        if not isinstance(file_path, str) or not file_path.strip():
            raise GlmOcrPdfError("PDF path was not provided")
        normalized_path = windows_long_path(file_path)
        if not os.path.isfile(normalized_path):
            raise GlmOcrPdfError("PDF file does not exist or is not readable")
        if max_dimension is not None and max_dimension <= 0:
            raise GlmOcrPdfError("PDF render maximum dimension must be positive")

        document: Any | None = None
        try:
            document = pymupdf.open(normalized_path)
            if document.page_count < 1:
                raise GlmOcrPdfError("PDF contains no pages")
            images: list[bytes] = []
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                pixmap = None
                try:
                    scale = self.dpi / 72.0
                    if max_dimension is not None:
                        longest_edge = max(page.rect.width, page.rect.height)
                        if longest_edge > 0:
                            scale = min(scale, max_dimension / longest_edge)
                    matrix = pymupdf.Matrix(scale, scale)
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
        if self.resolution_mode == "document" and not any(
            _model_names_match(self.resolver_model, name) for name in names
        ):
            raise GlmOcrModelNotFoundError(
                "Configured document resolver model is not installed in Ollama"
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

    def _resolve_document_fields(
        self,
        client: Any,
        *,
        page_images: list[bytes],
        page_count: int,
        fields: dict[str, Any],
        candidates: dict[str, list[dict[str, Any]]],
        document_instructions: str,
        calls: list[GlmOcrCallRecord],
        findings: list[GlmOcrAdapterFinding],
        normalization_findings: list[FieldNormalizationFinding],
    ) -> tuple[dict[str, Any], dict[str, list[int]]]:
        """Resolve each configured field independently against every page."""
        resolved: dict[str, Any] = {}
        field_pages: dict[str, list[int]] = {key: [] for key in fields}
        for field_key, field_config in fields.items():
            schema = build_document_resolver_schema(
                field_key,
                field_config,
                page_count=page_count,
            )
            required = not is_optional_type(
                str(field_config.get("type", "str"))
            )
            if field_config.get("is_table", False):
                table_rows, table_pages = self._resolve_document_table(
                    client,
                    field_key=field_key,
                    field_config=field_config,
                    candidates=candidates.get(field_key, []),
                    page_count=page_count,
                    document_instructions=document_instructions,
                    calls=calls,
                    findings=findings,
                    normalization_findings=normalization_findings,
                )
                resolved[field_key] = table_rows
                field_pages[field_key] = table_pages
                continue
            final_data: dict[str, Any] | None = None
            final_schema_findings: list[GlmOcrAdapterFinding] = []
            for attempt_number in range(1, self.resolver_max_attempts + 1):
                prompt = build_document_resolver_prompt(
                    field_key,
                    field_config,
                    candidates.get(field_key, []),
                    page_count=page_count,
                    document_instructions=document_instructions,
                    attempt_number=attempt_number,
                )
                call_type = (
                    "document_object"
                    if isinstance(field_config.get("object_fields"), dict)
                    else "document_scalar"
                )
                try:
                    response_data, record = self._call_resolver_model(
                        client,
                        call_type=call_type,
                        image_bytes=page_images,
                        prompt=prompt,
                        schema=schema,
                    )
                except GlmOcrResponseError:
                    if attempt_number >= self.resolver_max_attempts:
                        raise
                    findings.append(
                        GlmOcrAdapterFinding(
                            path=field_key,
                            code="resolver_retry",
                            message=(
                                "Document resolver returned an invalid structured "
                                "response and was retried"
                            ),
                            call_type=call_type,
                        )
                    )
                    continue
                calls.append(record)
                attempt_findings = _schema_findings(
                    response_data,
                    schema,
                    call_type=call_type,
                    path_prefix=field_key,
                )
                final_data = response_data
                final_schema_findings = attempt_findings
                value = response_data.get("value")
                should_retry = bool(attempt_findings) or (
                    required
                    and _required_resolver_value_missing(value, field_config)
                )
                if should_retry and attempt_number < self.resolver_max_attempts:
                    findings.append(
                        GlmOcrAdapterFinding(
                            path=field_key,
                            code="resolver_retry",
                            message=(
                                "Document resolver result was incomplete and was retried"
                            ),
                            call_type=call_type,
                        )
                    )
                    continue
                break

            if final_data is None:
                raise GlmOcrResponseError(
                    "Document resolver returned no parseable structured response"
                )
            findings.extend(final_schema_findings)
            raw_value = final_data.get("value")
            normalized_value = normalize_scalar_field(
                raw_value,
                field_config,
                path=field_key,
                findings=normalization_findings,
            )
            resolved[field_key] = normalized_value
            if _has_value(normalized_value):
                pages = _valid_page_numbers(
                    final_data.get("page_numbers"),
                    page_count=page_count,
                )
                if not pages:
                    pages = _candidate_pages_for_value(
                        candidates.get(field_key, []),
                        normalized_value,
                    )
                field_pages[field_key] = pages
                if not pages:
                    findings.append(
                        GlmOcrAdapterFinding(
                            path=field_key,
                            code="resolver_missing_pages",
                            message=(
                                "Document resolver returned a value without valid page evidence"
                            ),
                            call_type=call_type,
                        )
                    )
            elif required and _required_resolver_value_missing(
                normalized_value,
                field_config,
            ):
                findings.append(
                    GlmOcrAdapterFinding(
                        path=field_key,
                        code="resolver_unresolved",
                        message=(
                            "Document resolver could not locate a required configured value"
                        ),
                        call_type=call_type,
                    )
                )
        return resolved, field_pages

    def _resolve_document_table(
        self,
        client: Any,
        *,
        field_key: str,
        field_config: dict[str, Any],
        candidates: list[dict[str, Any]],
        page_count: int,
        document_instructions: str,
        calls: list[GlmOcrCallRecord],
        findings: list[GlmOcrAdapterFinding],
        normalization_findings: list[FieldNormalizationFinding],
    ) -> tuple[list[dict[str, Any]], list[int]]:
        """Reconcile table rows from bounded structured evidence chunks."""
        chunks = _table_candidate_chunks(candidates)
        if not chunks:
            return [], []

        schema = build_document_resolver_schema(
            field_key,
            field_config,
            page_count=page_count,
        )
        resolved_rows: list[dict[str, Any]] = []
        resolved_pages: set[int] = set()
        for chunk_number, chunk in enumerate(chunks, start=1):
            final_data: dict[str, Any] | None = None
            final_schema_findings: list[GlmOcrAdapterFinding] = []
            for attempt_number in range(1, self.resolver_max_attempts + 1):
                prompt = build_table_evidence_resolver_prompt(
                    field_key,
                    field_config,
                    chunk,
                    page_count=page_count,
                    document_instructions=document_instructions,
                    attempt_number=attempt_number,
                    chunk_number=chunk_number,
                    chunk_count=len(chunks),
                )
                try:
                    response_data, record = self._call_resolver_model(
                        client,
                        call_type="document_table",
                        image_bytes=[],
                        prompt=prompt,
                        schema=schema,
                    )
                except GlmOcrResponseError:
                    if attempt_number >= self.resolver_max_attempts:
                        raise
                    findings.append(
                        GlmOcrAdapterFinding(
                            path=field_key,
                            code="resolver_retry",
                            message=(
                                "Document table resolver returned an invalid "
                                "structured response and was retried"
                            ),
                            call_type="document_table",
                        )
                    )
                    continue
                calls.append(record)
                attempt_findings = _schema_findings(
                    response_data,
                    schema,
                    call_type="document_table",
                    path_prefix=field_key,
                )
                final_data = response_data
                final_schema_findings = attempt_findings
                if (
                    attempt_findings or response_data.get("value") is None
                ) and attempt_number < self.resolver_max_attempts:
                    findings.append(
                        GlmOcrAdapterFinding(
                            path=field_key,
                            code="resolver_retry",
                            message=(
                                "Document table resolver result was incomplete "
                                "and was retried"
                            ),
                            call_type="document_table",
                        )
                    )
                    continue
                break

            if final_data is None:
                raise GlmOcrResponseError(
                    "Document table resolver returned no parseable structured response"
                )
            findings.extend(final_schema_findings)
            alias = str(field_config.get("alias", field_key))
            normalized_rows = normalize_table_field(
                {field_key: final_data.get("value")},
                field_key,
                alias,
                field_config,
                findings=normalization_findings,
            ) or []
            normalized_rows, repaired_indexes = _ground_table_rows(
                normalized_rows,
                chunk,
                field_config,
            )
            for row_index in repaired_indexes:
                findings.append(
                    GlmOcrAdapterFinding(
                        path=f"{field_key}.{row_index}",
                        code="table_evidence_realign",
                        message=(
                            "Document table cells were realigned from explicit "
                            "structured row evidence"
                        ),
                        call_type="document_table",
                    )
                )
            resolved_rows.extend(normalized_rows)
            pages = _valid_page_numbers(
                final_data.get("page_numbers"),
                page_count=page_count,
            )
            if not pages and normalized_rows:
                pages = _candidate_page_numbers(chunk)
            resolved_pages.update(pages)
        return resolved_rows, sorted(resolved_pages)

    def _call_resolver_model(
        self,
        client: Any,
        *,
        call_type: str,
        image_bytes: list[bytes],
        prompt: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], GlmOcrCallRecord]:
        """Call the configured resolver with optional ordered page images."""
        started = time.perf_counter()
        try:
            message: dict[str, Any] = {
                "role": "user",
                "content": prompt,
            }
            if image_bytes:
                message["images"] = image_bytes
            response = client.chat(
                model=self.resolver_model,
                messages=[message],
                format=schema,
                stream=False,
                think=False,
                options={
                    "temperature": 0,
                    "num_ctx": self.resolver_num_ctx,
                    "num_predict": self.resolver_num_predict,
                },
            )
        except Exception as exc:
            raise _safe_ollama_exception(
                exc,
                during="document resolution",
            ) from exc
        duration = time.perf_counter() - started
        done = _response_value(response, "done")
        reason = _response_value(response, "done_reason")
        if done is False or str(reason or "").lower() in {
            "length",
            "max_tokens",
            "token_limit",
        }:
            raise GlmOcrResponseError(
                "Document resolver response was incomplete because the token limit was reached"
            )
        message = _response_value(response, "message")
        response_text = _response_value(message, "content")
        if not isinstance(response_text, str) or not response_text.strip():
            raise GlmOcrResponseError(
                "Document resolver returned an empty or invalid response envelope"
            )
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise GlmOcrResponseError(
                "Document resolver response was not valid JSON"
            ) from exc
        if not isinstance(parsed, dict):
            raise GlmOcrResponseError(
                "Document resolver response JSON must be an object"
            )
        return parsed, GlmOcrCallRecord(
            page_number=None,
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
        candidates: dict[str, list[dict[str, Any]]],
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
            _add_candidate(candidates[field_key], page_number, normalized_value)
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
        candidates: dict[str, list[dict[str, Any]]],
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
        found_raw, raw_rows = get_extracted_value(page_data, key, alias)
        raw_rows = raw_rows if found_raw and isinstance(raw_rows, list) else []
        destination = merged.setdefault(key, [])
        for row_index, row in enumerate(rows):
            evidence_text = None
            if row_index < len(raw_rows) and isinstance(raw_rows[row_index], dict):
                raw_evidence = raw_rows[row_index].get(TABLE_ROW_EVIDENCE_KEY)
                if isinstance(raw_evidence, str) and raw_evidence.strip():
                    evidence_text = raw_evidence.strip()
            _add_candidate(
                candidates[key],
                page_number,
                row,
                evidence_text=evidence_text,
            )
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
    path_prefix: str | None = None,
) -> list[GlmOcrAdapterFinding]:
    validator = jsonschema.Draft202012Validator(schema)
    findings: list[GlmOcrAdapterFinding] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.path)):
        path = ".".join(str(part) for part in error.absolute_path)
        if path_prefix:
            path = f"{path_prefix}.{path}" if path else path_prefix
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


def _add_candidate(
    candidates: list[dict[str, Any]],
    page_number: int,
    value: Any,
    *,
    evidence_text: str | None = None,
) -> None:
    fingerprint = _stable_json(value)
    for candidate in candidates:
        if (
            candidate.get("page_number") == page_number
            and _stable_json(candidate.get("value")) == fingerprint
        ):
            return
    candidate = {"page_number": page_number, "value": value}
    if evidence_text:
        candidate[TABLE_ROW_EVIDENCE_KEY] = evidence_text
    candidates.append(candidate)


def _table_candidate_chunks(
    candidates: list[dict[str, Any]],
    *,
    max_chars: int = 12000,
) -> list[list[dict[str, Any]]]:
    """Partition ordered rows without splitting one structured candidate."""
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for candidate in candidates:
        proposed = [*current, candidate]
        if current and len(_stable_json(proposed)) > max_chars:
            chunks.append(current)
            current = [candidate]
        else:
            current = proposed
    if current:
        chunks.append(current)
    return chunks


def _candidate_page_numbers(candidates: list[dict[str, Any]]) -> list[int]:
    """Return valid positive source pages represented in candidate evidence."""
    return sorted(
        {
            page_number
            for candidate in candidates
            if isinstance((page_number := candidate.get("page_number")), int)
            and not isinstance(page_number, bool)
            and page_number > 0
        }
    )


def _ground_table_rows(
    rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    field_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[int]]:
    """Ground resolver rows and realign explicit delimited text cells."""
    item_fields = field_config.get("item_fields")
    if not isinstance(item_fields, dict):
        return rows, []
    field_keys = list(item_fields)
    grounded_rows: list[dict[str, Any]] = []
    repaired_indexes: list[int] = []
    for row_index, row in enumerate(rows):
        candidate = candidates[row_index] if row_index < len(candidates) else {}
        candidate_row = candidate.get("value")
        if not isinstance(candidate_row, dict):
            grounded_rows.append(row)
            continue
        grounded = dict(row)
        evidence_values = [
            value for value in candidate_row.values() if _has_value(value)
        ]
        evidence_text = " ".join(str(value) for value in evidence_values)
        changed = False
        for field_key in field_keys:
            value = grounded.get(field_key)
            if not _has_value(value):
                fallback = candidate_row.get(field_key)
                if _has_value(fallback):
                    grounded[field_key] = fallback
                    changed = True
                continue
            if isinstance(value, str) and value.casefold() not in evidence_text.casefold():
                fallback = candidate_row.get(field_key)
                grounded[field_key] = fallback
                changed = True
            elif not isinstance(value, str) and not any(
                _values_equal(value, evidence_value)
                for evidence_value in evidence_values
            ):
                grounded[field_key] = candidate_row.get(field_key)
                changed = True

        for start_index, field_key in enumerate(field_keys):
            if start_index == 0 or not _is_text_field(item_fields[field_key]):
                continue
            target_keys: list[str] = []
            for target_key in field_keys[start_index:]:
                if not _is_text_field(item_fields[target_key]):
                    break
                target_keys.append(target_key)
            if len(target_keys) < 2:
                continue
            source_value = candidate_row.get(field_key)
            if not isinstance(source_value, str) or "," not in source_value:
                continue
            parts: list[str] = []
            for target_key in target_keys:
                target_value = candidate_row.get(target_key)
                if not isinstance(target_value, str) or not target_value.strip():
                    continue
                parts.extend(
                    part.strip()
                    for part in target_value.split(",")
                    if part.strip()
                )
                if len(parts) >= len(target_keys):
                    break
            if len(parts) != len(target_keys):
                continue
            for target_key, part in zip(target_keys, parts):
                if grounded.get(target_key) != part:
                    grounded[target_key] = part
                    changed = True
            break
        grounded_rows.append(grounded)
        if changed:
            repaired_indexes.append(row_index)
    return grounded_rows, repaired_indexes


def _is_text_field(field_config: dict[str, Any]) -> bool:
    """Return whether a configured field is scalar text, including optional text."""
    type_name = str(field_config.get("type", "str")).strip()
    if type_name.startswith("Optional[") and type_name.endswith("]"):
        type_name = type_name[9:-1].strip()
    return type_name == "str"


def _valid_page_numbers(value: Any, *, page_count: int) -> list[int]:
    if not isinstance(value, list):
        return []
    pages = {
        page
        for page in value
        if isinstance(page, int)
        and not isinstance(page, bool)
        and 1 <= page <= page_count
    }
    return sorted(pages)


def _candidate_pages_for_value(
    candidates: list[dict[str, Any]],
    value: Any,
    *,
    table_rows: bool = False,
) -> list[int]:
    pages: set[int] = set()
    resolved_values = value if table_rows and isinstance(value, list) else [value]
    fingerprints = {_stable_json(item) for item in resolved_values}
    for candidate in candidates:
        if _stable_json(candidate.get("value")) in fingerprints:
            page_number = candidate.get("page_number")
            if isinstance(page_number, int) and not isinstance(page_number, bool):
                pages.add(page_number)
    return sorted(pages)


def _required_resolver_value_missing(
    value: Any,
    field_config: dict[str, Any],
) -> bool:
    type_name = str(field_config.get("type", "str")).strip()
    if type_name.startswith("Optional[") and type_name.endswith("]"):
        type_name = type_name[9:-1].strip()
    if type_name.startswith("List["):
        return value is None
    return not _has_value(value)


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
