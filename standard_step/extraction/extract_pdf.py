"""Extract structured data from PDFs using LlamaCloud Extract v2.

This module provides ExtractPdfTask, a pipeline step that orchestrates
document data extraction via LlamaCloud. It validates required
parameters, runs an Extract v2 job, post-processes the result, validates it
against a dynamically created Pydantic model, and merges the data into the
pipeline context.

Notes:
    - Reads runtime parameters (api_key, configuration_id, fields) from BaseTask.params.
    - Interacts with the filesystem indirectly via the external service using
      the provided file path.
    - Errors are surfaced as TaskError after being logged.
"""
import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from pydantic import create_model
from pydantic import BaseModel, ValidationError, Field, ConfigDict
from modules.base_task import BaseTask
from modules.config_protocol import ConfigProvider as ConfigManager
from modules.db.connection import connect
from modules.db.repositories import ExtractionRepository
from modules.exceptions import TaskError
from modules.utils import windows_long_path
from standard_step.extraction.llama_cloud_v2 import (
    extract_confidence_label,
    extract_field_source,
    extract_numeric_confidence,
    run_extract_v2_job,
)


_ALLOWED_FIELD_TYPES: Dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "Decimal": Decimal,
    "Any": Any,
    "dict": dict,
}


def _parse_field_type(type_value: Any) -> Any:
    """Parse an allowlisted extraction field type string.

    Supports the same config-facing type syntax used by extraction validation:
    base types, Optional[T], List[T], Dict[K, V], and nested combinations.

    Args:
        type_value: Configured field type value.

    Returns:
        A Python type annotation suitable for Pydantic model creation.

    Raises:
        ValueError: If the type value is malformed or unsupported.
    """
    if type_value is None:
        return Any
    if not isinstance(type_value, str):
        raise ValueError(
            f"Field type must be a string, got {type(type_value).__name__}."
        )

    clean_type = type_value.strip()
    if not clean_type:
        return Any
    if clean_type in _ALLOWED_FIELD_TYPES:
        return _ALLOWED_FIELD_TYPES[clean_type]

    if clean_type.startswith("Optional[") and clean_type.endswith("]"):
        inner_type = clean_type[len("Optional["):-1].strip()
        if not inner_type:
            raise ValueError(f"Malformed Optional field type: {type_value!r}")
        return Optional[_parse_field_type(inner_type)]

    if clean_type.startswith("List[") and clean_type.endswith("]"):
        inner_type = clean_type[len("List["):-1].strip()
        if not inner_type:
            raise ValueError(f"Malformed List field type: {type_value!r}")
        return list[_parse_field_type(inner_type)]

    if clean_type.startswith("Dict[") and clean_type.endswith("]"):
        type_args = clean_type[len("Dict["):-1]
        parts = _split_top_level_type_args(type_args)
        if len(parts) != 2:
            raise ValueError(f"Malformed Dict field type: {type_value!r}")
        key_type = _parse_field_type(parts[0])
        value_type = _parse_field_type(parts[1])
        return dict[key_type, value_type]

    raise ValueError(f"Unsupported field type: {type_value!r}")


def _split_top_level_type_args(type_args: str) -> list[str]:
    """Split comma-separated type arguments without splitting nested brackets."""
    parts: list[str] = []
    start = 0
    depth = 0

    for index, char in enumerate(type_args):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth < 0:
                return []
        elif char == "," and depth == 0:
            parts.append(type_args[start:index].strip())
            start = index + 1

    if depth != 0:
        return []

    parts.append(type_args[start:].strip())
    return [part for part in parts if part]


class ExtractPdfTask(BaseTask):
    """Task that extracts domain data from a PDF using LlamaCloud Extract v2.

    Responsibilities:
        - Validate required parameters (api_key and fields).
        - Run a LlamaCloud Extract v2 job against the file path.
        - Filter/normalize extracted lists to remove None values when needed.
        - Validate fields using a dynamically created Pydantic model.
        - Merge validated data into context['data'] and update metadata.

    Integration:
        Uses BaseTask for context initialization and error conventions.

    Args:
        config_manager (ConfigManager): Project configuration manager.
        **params: Expected keys include 'api_key', optional 'configuration_id', and 'fields'.

    Notes:
        - Side effects include remote API calls and SQLite extraction
          persistence when document context exists.
        - Raises TaskError for validation or extraction errors.

    Performance Considerations:
        - PDF extraction involves remote API calls that may have rate limits imposed by the external service.
        - Large PDF files (>50MB) may cause extended processing times; consider file size optimization for high-volume scenarios.
    """

    def __init__(self, config_manager: ConfigManager, **params):
        """Initialize ExtractPdfTask and capture required parameters.

        Args:
            config_manager (ConfigManager): The application configuration manager.
            **params: Runtime parameters: 'api_key', optional 'configuration_id', and 'fields'.

        Notes:
            Parameters are accessed via self.params provided by BaseTask.
        """
        super().__init__(config_manager=config_manager, **params)
        self.logger = logging.getLogger(__name__)
        
        api_key = self.params.get("api_key")
        self.api_key: Optional[str] = api_key if isinstance(api_key, str) else None
        configuration_id = self.params.get("configuration_id")
        self.configuration_id: Optional[str] = configuration_id if isinstance(configuration_id, str) else None
        self.tier: str = str(self.params.get("tier") or "agentic")
        parse_tier = self.params.get("parse_tier")
        self.parse_tier: Optional[str] = parse_tier if isinstance(parse_tier, str) else None
        self.extraction_target: str = str(self.params.get("extraction_target") or "per_doc")
        cite_sources = self.params.get("cite_sources")
        self.cite_sources: Optional[bool] = cite_sources if isinstance(cite_sources, bool) else None
        confidence_scores = self.params.get("confidence_scores", True)
        self.confidence_scores: Optional[bool] = confidence_scores if isinstance(confidence_scores, bool) else None
        project_id = self.params.get("project_id")
        self.project_id: Optional[str] = project_id if isinstance(project_id, str) else None
        organization_id = self.params.get("organization_id")
        self.organization_id: Optional[str] = organization_id if isinstance(organization_id, str) else None
        self.poll_interval_seconds = float(self.params.get("poll_interval_seconds", 2.0))
        self.timeout_seconds = float(self.params.get("timeout_seconds", 1800.0))
        fields = self.params.get("fields")
        self.fields: Dict[str, Any] = fields if isinstance(fields, dict) else {}

    def _require_api_key(self) -> str:
        """Return the configured API key after narrowing its type."""
        if not self.api_key:
            raise TaskError("API key not found in configuration for ExtractPdfTask.")
        return self.api_key

    def on_start(self, context: dict):
        """Lifecycle hook executed when the task starts.

        Initializes context and performs parameter presence checks.

        Args:
            context (dict): The pipeline context dict. Must contain 'id'.

        Raises:
            TaskError: If api_key or fields are missing.

        """
        self.initialize_context(context)

        if not self.api_key:
            raise TaskError("API key not found in configuration for ExtractPdfTask.")
        if not self.fields:
            raise TaskError("Fields not found in configuration for ExtractPdfTask.")

    def run(self, context: dict) -> dict:
        """Run Extract v2 against the configured schema and validate results.

        Expects a file path in the context and validates configured field
        definitions. It calls the LlamaCloud Extract v2 adapter to extract
        data, accepts returned keys by either configured alias or workflow field
        key, normalizes list fields, validates using a dynamically created
        Pydantic model, and writes validated values to context['data'] and
        metadata.

        Args:
            context (dict): Pipeline context. Requires:
                - id (str): Unique identifier.
                - file_path (str): Source PDF file to extract from.

        Returns:
            dict: Updated context with:
                - data (dict): Validated extracted values merged in.
                - metadata (dict): Includes extraction job/configuration details and status.

        Raises:
            TaskError: If file_path is missing, validation fails, or the
                external service reports an error.

        Notes:
            - Side effects: remote API call and optional SQLite persistence.

        Performance Considerations:
            - This method makes synchronous remote API calls that may be subject to rate limiting by the external service.
            - PDF processing times scale with file size and complexity; monitor API quotas for high-volume processing scenarios.
        """
        file_path = context.get("file_path")
        unique_id = str(context.get("id"))

        if not file_path:
            raise TaskError("File path not provided in context.")

        if not self.fields:
            error_msg = "Fields configuration is missing or empty."
            self.logger.error(error_msg)
            raise TaskError(error_msg)

        normalized_file_path = windows_long_path(file_path)
        config_label = self.configuration_id or "inline field schema"
        self.logger.info(f"Extracting data from {normalized_file_path} using {config_label}...")

        try:
            api_key = self._require_api_key()
            extracted_result = run_extract_v2_job(
                api_key=api_key,
                file_path=normalized_file_path,
                fields=self.fields,
                configuration_id=self.configuration_id,
                tier=self.tier,
                parse_tier=self.parse_tier,
                extraction_target=self.extraction_target,
                cite_sources=self.cite_sources,
                confidence_scores=self.confidence_scores,
                project_id=self.project_id,
                organization_id=self.organization_id,
                poll_interval_seconds=self.poll_interval_seconds,
                timeout_seconds=self.timeout_seconds,
                logger=self.logger,
            )

            # Extract data dictionary from result
            data = getattr(extracted_result, 'data', {}) or {}
            field_count = len(data) if isinstance(data, dict) else 0
            self.logger.info(
                "Extraction job %s returned %s fields for %s",
                getattr(extracted_result, "job_id", None),
                field_count,
                unique_id,
            )

            # Preprocess data by alias or workflow field key. Saved LlamaCloud
            # configurations may return either form.
            processed_data = data.copy()
            for field_name, field_config in self.fields.items():
                alias = field_config.get("alias")
                source_key = alias if alias in processed_data else field_name
                if source_key in processed_data and isinstance(processed_data[source_key], list):
                    field_type_str = field_config.get("type", "")
                    if "List[str]" in field_type_str or "Optional[List[str]]" in field_type_str:
                        original_list = processed_data[source_key]
                        filtered_list = [item for item in original_list if item is not None]
                        processed_data[source_key] = filtered_list

            # Dynamically create a Pydantic model for validation. populate_by_name
            # lets the workflow accept either aliases or workflow field keys.
            model_fields = {}
            for field_name, field_config in self.fields.items():
                field_type_str = field_config.get("type", "Any")
                field_type = _parse_field_type(field_type_str)
                alias = field_config.get("alias", field_name)
                model_fields[field_name] = (field_type, Field(alias=alias))
            model_config = ConfigDict(populate_by_name=True, extra="ignore")
            DynamicModel = create_model("DynamicModel", __config__=model_config, **model_fields)

            # Validate extracted data
            validated_data = DynamicModel(**processed_data).model_dump()

            # Merge extracted data into existing context['data'] dictionary
            if "data" not in context or not isinstance(context["data"], dict):
                context["data"] = {}
            context["data"].update(validated_data)

            # Update context with metadata
            context["metadata"] = {
                "extraction_configuration_id": self.configuration_id,
                "extraction_job_id": getattr(extracted_result, "job_id", None),
                "extraction_metadata": getattr(extracted_result, "extraction_metadata", {}),
                "extraction_status": "success"
            }

            self._persist_extraction_result(
                context=context,
                processed_data=validated_data,
                metadata=getattr(extracted_result, "extraction_metadata", {}) or {},
                provider_job_id=getattr(extracted_result, "job_id", None),
            )

            self.logger.info(f"Extraction successful for {unique_id}")

        except ValidationError as ve:
            error_msg = f"Validation error during extraction: {ve}"
            self.logger.error(error_msg)
            raise TaskError(error_msg)

        except Exception as e:
            error_msg = f"Extraction failed: {e}"
            self.logger.error(error_msg)
            raise TaskError(error_msg)

        return context

    def _persist_extraction_result(
        self,
        *,
        context: Dict[str, Any],
        processed_data: Dict[str, Any],
        metadata: Dict[str, Any],
        provider_job_id: str | None,
    ) -> None:
        """Persist extraction result and confidence metadata for review workflows."""
        document_id = context.get("document_id")
        if not document_id:
            return

        fields = self._build_persisted_fields(processed_data, metadata)
        with connect(self.config_manager) as conn:
            repository = ExtractionRepository(conn)
            result = repository.save_result(
                document_id=str(document_id),
                task_run_id=context.get("task_run_id"),
                provider="llamacloud_extract",
                provider_job_id=provider_job_id,
                data=processed_data,
                metadata={
                    "configuration_id": self.configuration_id,
                    "extraction_metadata": metadata,
                },
            )
            repository.save_fields(
                document_id=str(document_id),
                extraction_result_id=result["id"],
                fields=fields,
            )
        context["extraction_result_id"] = result["id"]

    def _build_persisted_fields(
        self,
        processed_data: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Convert validated extraction output into extracted_fields rows."""
        persisted_fields: list[dict[str, Any]] = []
        for field_key, value in processed_data.items():
            field_config = self.fields.get(field_key, {})
            alias = field_config.get("alias", field_key) if isinstance(field_config, dict) else field_key
            persisted_fields.append(
                {
                    "field_key": field_key,
                    "field_alias": alias,
                    "extracted_value": value,
                    "final_value": value,
                    "confidence": extract_numeric_confidence(metadata, field_key, alias),
                    "confidence_label": extract_confidence_label(metadata, field_key, alias),
                    "requires_review": False,
                    "review_status": "not_required",
                    "source": extract_field_source(metadata, field_key, alias),
                }
            )
        return persisted_fields

    def validate_required_fields(self, context: dict):
        """Validate presence of required runtime parameters.

        Args:
            context (dict): Unused; present for BaseTask interface consistency.

        Raises:
            TaskError: If any of the required parameters are missing.
        """
        errors = []
        if not self.api_key:
            errors.append("API key is missing in configuration.")
        if not self.fields:
            errors.append("Fields are missing in configuration.")

        if errors:
            error_msg = " ".join(errors)
            self.logger.error(error_msg)
            raise TaskError(error_msg)
