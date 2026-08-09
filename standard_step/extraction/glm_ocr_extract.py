"""Configured workflow task for local Ollama GLM-OCR extraction."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from modules.base_task import BaseTask
from modules.config_protocol import ConfigProvider as ConfigManager
from modules.db.connection import connect
from modules.db.repositories import ExtractionRepository
from modules.exceptions import TaskError
from standard_step.extraction.glm_ocr_adapter import (
    GlmOcrAdapter,
    GlmOcrAdapterError,
    GlmOcrAdapterResult,
    GlmOcrModelNotFoundError,
    GlmOcrPdfError,
    GlmOcrResponseError,
    GlmOcrTimeoutError,
    GlmOcrUnavailableError,
)
from standard_step.extraction.glm_ocr_prompt import (
    validate_glm_ocr_fields,
    validate_glm_ocr_prompt_style,
)


MAX_TOP_LEVEL_FIELDS = 100
LLAMACLOUD_ONLY_PARAMS = frozenset(
    {
        "api_key",
        "configuration_id",
        "tier",
        "parse_tier",
        "extraction_target",
        "cite_sources",
        "confidence_scores",
        "project_id",
        "organization_id",
        "poll_interval_seconds",
    }
)


class GlmOcrExtractTask(BaseTask):
    """Extract configured structured values with a local GLM-OCR model."""

    def __init__(self, config_manager: ConfigManager, **params: Any) -> None:
        """Capture immutable versioned parameters without runtime side effects."""
        super().__init__(config_manager=config_manager, **params)
        self.ollama_host = ""
        self.model = ""
        self.document_instructions = ""
        self.prompt_style = "detailed"
        self.dpi = 216
        self.num_ctx = 8192
        self.num_predict = 2048
        self.timeout_seconds = 300.0
        self.fields: dict[str, Any] = {}
        self._parameters_loaded = False

    def on_start(self, context: dict) -> None:
        """Initialize context and validate the exact published task parameters."""
        self.initialize_context(context)
        try:
            self._load_parameters()
            self.validate_required_fields(context)
        except TaskError as error:
            self._register_failure(context, error)
            raise
        except (TypeError, ValueError) as error:
            task_error = TaskError("GLM-OCR task configuration is invalid.")
            self.logger.warning(
                "GLM-OCR configuration validation failed (%s)",
                type(error).__name__,
            )
            self._register_failure(context, task_error)
            raise task_error from error

    def validate_required_fields(self, context: dict) -> None:
        """Validate provider settings, configured fields, and the source PDF."""
        if not self._parameters_loaded:
            self._load_parameters()

        unsupported = sorted(LLAMACLOUD_ONLY_PARAMS.intersection(self.params))
        if unsupported:
            raise TaskError(
                "GLM-OCR task contains unsupported LlamaCloud-only parameters."
            )
        if not isinstance(self.fields, dict) or not self.fields:
            raise TaskError("GLM-OCR fields must be a non-empty mapping.")
        if len(self.fields) > MAX_TOP_LEVEL_FIELDS:
            raise TaskError(
                f"GLM-OCR supports at most {MAX_TOP_LEVEL_FIELDS} top-level fields."
            )
        try:
            validate_glm_ocr_fields(self.fields)
        except (TypeError, ValueError) as error:
            raise TaskError("GLM-OCR field configuration is invalid.") from error

        _validate_ollama_host(self.ollama_host)
        if not self.model:
            raise TaskError("GLM-OCR model must be a non-empty string.")
        if not isinstance(self.document_instructions, str):
            raise TaskError("GLM-OCR document instructions must be text.")
        try:
            validate_glm_ocr_prompt_style(self.prompt_style)
        except ValueError as error:
            raise TaskError("GLM-OCR prompt_style is invalid.") from error
        if self.prompt_style == "verbatim" and not self.document_instructions.strip():
            raise TaskError(
                "GLM-OCR verbatim prompt style requires document instructions."
            )
        for key, value in {
            "dpi": self.dpi,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise TaskError(f"GLM-OCR {key} must be a positive integer.")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise TaskError("GLM-OCR timeout_seconds must be a positive number.")

        file_path = context.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            raise TaskError("GLM-OCR requires context['file_path'].")
        if not Path(file_path).is_file():
            raise TaskError("GLM-OCR source PDF does not exist or is unreadable.")

    def run(self, context: dict) -> dict:
        """Extract, normalize, persist, and expose provider-neutral output."""
        self.initialize_context(context)
        try:
            if not self._parameters_loaded:
                self._load_parameters()
            self.validate_required_fields(context)
            adapter = self._build_adapter()
            result = adapter.extract(
                str(context["file_path"]),
                self.fields,
                document_instructions=self.document_instructions,
                prompt_style=self.prompt_style,
            )
            processed_data = self._processed_data(result)
            data = context.get("data")
            if not isinstance(data, dict):
                data = {}
                context["data"] = data
            data.update(processed_data)

            safe_metadata = self._safe_metadata(result)
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                context["metadata"] = metadata
            metadata["glm_ocr"] = safe_metadata
            self._merge_review_flag(context)
            self._persist_extraction_result(
                context=context,
                processed_data=processed_data,
                safe_metadata=safe_metadata,
                result=result,
            )
            return context
        except TaskError as error:
            self._register_failure(context, error)
            raise
        except GlmOcrAdapterError as error:
            task_error = TaskError(_adapter_error_message(error))
            self._register_failure(context, task_error, error=error)
            raise task_error from error
        except Exception as error:
            self.logger.error(
                "Unexpected GLM-OCR extraction failure (%s)",
                type(error).__name__,
            )
            task_error = TaskError("Unexpected GLM-OCR extraction failure.")
            self._register_failure(context, task_error, unexpected=True)
            raise task_error from error

    def _load_parameters(self) -> None:
        """Load only constructor parameters supplied by the pipeline version."""
        host = self.params.get("ollama_host", "http://127.0.0.1:11434")
        model = self.params.get("model", "glm-ocr:latest")
        instructions = self.params.get("document_instructions", "")
        prompt_style = self.params.get("prompt_style", "detailed")
        fields = self.params.get("fields", {})
        self.ollama_host = host.strip() if isinstance(host, str) else ""
        self.model = model.strip() if isinstance(model, str) else ""
        self.document_instructions = instructions
        self.prompt_style = prompt_style
        self.dpi = self.params.get("dpi", 216)
        self.num_ctx = self.params.get("num_ctx", 8192)
        self.num_predict = self.params.get("num_predict", 2048)
        self.timeout_seconds = self.params.get("timeout_seconds", 300)
        self.fields = dict(fields) if isinstance(fields, dict) else {}
        self._parameters_loaded = True

    def _build_adapter(self) -> GlmOcrAdapter:
        """Construct the local provider adapter after validation."""
        return GlmOcrAdapter(
            ollama_host=self.ollama_host,
            model=self.model,
            dpi=self.dpi,
            num_ctx=self.num_ctx,
            num_predict=self.num_predict,
            timeout_seconds=float(self.timeout_seconds),
        )

    def _processed_data(self, result: GlmOcrAdapterResult) -> dict[str, Any]:
        """Return every configured top-level field, using null when absent."""
        if not isinstance(result.data, dict):
            raise TaskError("GLM-OCR returned an invalid structured result.")
        return {
            str(field_key): result.data.get(str(field_key))
            for field_key in self.fields
        }

    def _safe_metadata(self, result: GlmOcrAdapterResult) -> dict[str, Any]:
        """Build execution metadata that excludes prompts, images, and values."""
        calls = []
        for call in result.calls:
            call_data = asdict(call)
            call_data["duration_seconds"] = round(
                float(call_data["duration_seconds"]), 6
            )
            calls.append(call_data)
        return {
            "provider": "glm_ocr_ollama",
            "model": self.model,
            "host_classification": _host_classification(self.ollama_host),
            "page_count": result.page_count,
            "call_strategy": "per_page_scalar_object_optional_recovery_and_table",
            "calls": calls,
            "field_pages": {
                str(key): list(pages) for key, pages in result.field_pages.items()
            },
            "validation_findings": [asdict(item) for item in result.findings],
            "normalization_findings": [
                asdict(item) for item in result.normalization_findings
            ],
            "conflicts": [asdict(item) for item in result.conflicts],
        }

    def _persist_extraction_result(
        self,
        *,
        context: dict,
        processed_data: dict[str, Any],
        safe_metadata: dict[str, Any],
        result: GlmOcrAdapterResult,
    ) -> None:
        """Persist one result and one nullable-confidence row per field."""
        document_id = context.get("document_id")
        if not document_id:
            return
        fields = []
        for field_key, field_config in self.fields.items():
            key = str(field_key)
            config = field_config if isinstance(field_config, dict) else {}
            fields.append(
                {
                    "field_key": key,
                    "field_alias": str(config.get("alias") or key),
                    "extracted_value": processed_data.get(key),
                    "final_value": processed_data.get(key),
                    "confidence": None,
                    "confidence_label": None,
                    "requires_review": False,
                    "review_status": "not_required",
                    "source": self._field_source(key, result),
                }
            )
        with connect(self.config_manager) as conn:
            repository = ExtractionRepository(conn)
            saved = repository.save_result(
                document_id=str(document_id),
                task_run_id=context.get("task_run_id"),
                provider="glm_ocr_ollama",
                provider_job_id=None,
                data=processed_data,
                metadata=safe_metadata,
            )
            repository.save_fields(
                document_id=str(document_id),
                extraction_result_id=str(saved["id"]),
                fields=fields,
            )
        context["extraction_result_id"] = saved["id"]

    @staticmethod
    def _field_source(field_key: str, result: GlmOcrAdapterResult) -> dict[str, Any]:
        """Return safe page and validation evidence for one top-level field."""
        def belongs(path: str) -> bool:
            return path == field_key or path.startswith(f"{field_key}.")

        return {
            "pages": list(result.field_pages.get(field_key, [])),
            "validation_findings": [
                asdict(item) for item in result.findings if belongs(item.path)
            ],
            "normalization_findings": [
                asdict(item)
                for item in result.normalization_findings
                if belongs(item.path)
            ],
            "conflicts": [
                asdict(item) for item in result.conflicts if belongs(item.path)
            ],
        }

    def _merge_review_flag(self, context: dict) -> None:
        """Add the unscored flag while preserving every existing flag."""
        field_keys = [str(key) for key in self.fields]
        entry = {
            "reason": "unscored_extraction",
            "field_keys": field_keys,
        }
        flags = context.get("review_flags")
        if flags is None:
            context["review_flags"] = {"glm_ocr_unscored": entry}
            return
        if isinstance(flags, dict):
            flags.setdefault("glm_ocr_unscored", entry)
            return
        structured_entry = {"flag": "glm_ocr_unscored", **entry}
        if isinstance(flags, list):
            if structured_entry not in flags:
                flags.append(structured_entry)
            return
        context["review_flags"] = [flags, structured_entry]

    def _register_failure(
        self,
        context: dict,
        task_error: TaskError,
        *,
        error: Exception | None = None,
        unexpected: bool = False,
    ) -> None:
        """Register a redacted failure and provider-specific operator guidance."""
        failure_type = "glm_ocr_unexpected_error" if unexpected else "glm_ocr_failed"
        if error is not None:
            provider_failure_types: dict[type[Exception], str] = {
                GlmOcrUnavailableError: "glm_ocr_unavailable",
                GlmOcrModelNotFoundError: "glm_ocr_model_missing",
                GlmOcrTimeoutError: "glm_ocr_timeout",
                GlmOcrPdfError: "glm_ocr_pdf_error",
                GlmOcrResponseError: "glm_ocr_protocol_error",
            }
            failure_type = provider_failure_types.get(type(error), failure_type)
        context["fatal_failure"] = {
            "failure_type": failure_type,
            "message": task_error.message,
            "provider": "glm_ocr_ollama",
            "operator_action": (
                "Verify Ollama is running, the configured model is installed, "
                "and the source PDF is readable, then re-ingest the document."
            ),
        }
        self.register_error(context, task_error)


def _validate_ollama_host(value: str) -> None:
    """Validate a credential-free HTTP(S) Ollama base URL."""
    if not isinstance(value, str) or not value.strip():
        raise TaskError("GLM-OCR ollama_host must be a non-empty HTTP(S) URL.")
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise TaskError("GLM-OCR ollama_host must be a valid HTTP(S) URL.")
    if parsed.username is not None or parsed.password is not None:
        raise TaskError("GLM-OCR ollama_host must not contain credentials.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise TaskError("GLM-OCR ollama_host must be a base URL without a path.")
    try:
        port = parsed.port
    except ValueError as error:
        raise TaskError("GLM-OCR ollama_host contains an invalid port.") from error
    if port is not None and not 1 <= port <= 65535:
        raise TaskError("GLM-OCR ollama_host contains an invalid port.")


def _host_classification(value: str) -> str:
    """Classify the provider host without persisting its address."""
    hostname = (urlsplit(value).hostname or "").casefold()
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return "loopback"
    return "remote"


def _adapter_error_message(error: GlmOcrAdapterError) -> str:
    """Translate provider failures into stable redacted task messages."""
    if isinstance(error, GlmOcrModelNotFoundError):
        return "Configured GLM-OCR model is not installed in Ollama."
    if isinstance(error, GlmOcrTimeoutError):
        return "Local GLM-OCR extraction timed out."
    if isinstance(error, GlmOcrPdfError):
        return "The source PDF could not be opened or rendered for GLM-OCR."
    if isinstance(error, GlmOcrResponseError):
        return "GLM-OCR returned an invalid or incomplete structured response."
    return "Local Ollama service is unavailable for GLM-OCR extraction."
