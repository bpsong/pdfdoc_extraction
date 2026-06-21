"""PDF extraction task with array-of-objects support for LlamaCloud Extract v2 responses.

This module provides ExtractPdfTask, an enhanced pipeline step that handles
both scalar fields and table fields (arrays of objects) from LlamaCloud Extract
responses. It keeps the existing scalar extraction contract and adds support
for structured data from tables and arrays within PDF documents.

Key Features:
    - Extracts scalar fields with type conversion and normalization
    - Handles table fields as arrays of objects with subfield mapping
    - Preserves extraction metadata including field citations and usage stats
    - Supports dynamic field configuration via ConfigManager
    - Maintains the existing scalar extraction context structure

Notes:
    - Configuration is loaded from 'tasks.extract_document_data.params' section in config.yaml
    - Supports only one table field per extraction (PRD limitation)
    - Uses LlamaCloud Extract v2 for PDF processing
    - Stores extracted values under workflow field keys from configuration
    - Filters None values from lists when applicable
"""

import logging
import re
from typing import Any, Dict, Optional, List, Union

# Import get_logger if available, otherwise use standard logging
try:
    from modules.logging_config import get_logger
except ImportError:
    # Fallback to standard logging if get_logger is not available
    def get_logger(name: str):
        return logging.getLogger(name)
from modules.base_task import BaseTask
from modules.config_protocol import ConfigProvider as ConfigManager
from modules.db.connection import connect
from modules.db.repositories import ExtractionRepository
from modules.exceptions import TaskError
from modules.services.failure_service import _redact_text
from standard_step.extraction.llama_cloud_v2 import (
    extract_confidence_label,
    extract_field_source,
    extract_numeric_confidence,
    humanize_extract_error,
    is_non_retryable_extract_error,
    run_extract_v2_job,
)


class ExtractPdfTask(BaseTask):
    """PDF extraction task with array-of-objects support.

    This task extends the scalar extraction workflow to handle table fields
    containing arrays of objects. It processes LlamaCloud Extract responses that
    include both scalar fields and structured table data.

    The task follows the standard task creation guidelines with proper
    initialization, error handling, and logging.

    Attributes:
        config_manager (ConfigManager): Central configuration manager instance.
        api_key (str): LlamaCloud API key for authentication.
        configuration_id (Optional[str]): Saved LlamaCloud Extract v2 configuration identifier.
        fields (Dict[str, Any]): Field configuration including scalar and table fields.
        table_field_key (Optional[str]): Key of the table field (marked with is_table: true).
        item_fields (Dict[str, Any]): Subfield configuration for the table field.
        task_slug (str): Task identifier for status tracking.

    Configuration:
        The task loads configuration from the 'tasks.extract_document_data.params' section including:
        - api_key: LlamaCloud API authentication key
        - configuration_id: Optional saved LlamaCloud Extract v2 configuration identifier
        - tier: Optional Extract v2 tier used for inline configuration
        - parse_tier: Optional Parse tier used for inline configuration
        - fields: Field definitions with types, aliases, and table config

    Example:
        Configuration in config.yaml:
        tasks:
          extract_document_data:
            params:
              api_key: "your_llama_cloud_api_key"
              configuration_id: "your_configuration_id"
              fields:
                supplier_name:
                  alias: "Supplier name"
                  type: "str"
                items:
                  alias: "Items"
                  type: "List[Any]"
                  is_table: true
                  item_fields:
                    description:
                      alias: "Description"
                      type: "str"
                    quantity:
                      alias: "Quantity"
                      type: "str"
    """

    def __init__(self, config_manager: ConfigManager, **params):
        """Initialize ExtractPdfTask with configuration and parameters.

        Args:
            config_manager: The application configuration manager.
            **params: Runtime parameters including api_key, configuration_id, fields.
        """
        super().__init__(config_manager=config_manager, **params)
        self.config_manager = config_manager
        self.params = params
        self.task_slug = "extract_document_data"
        self.logger = get_logger(__name__)
        self.api_key: Optional[str] = None
        self.configuration_id: Optional[str] = None
        self.tier: str = "agentic"
        self.parse_tier: Optional[str] = None
        self.extraction_target: str = "per_doc"
        self.cite_sources: Optional[bool] = None
        self.confidence_scores: Optional[bool] = True
        self.project_id: Optional[str] = None
        self.organization_id: Optional[str] = None
        self.poll_interval_seconds: float = 2.0
        self.timeout_seconds: float = 1800.0
        self.fields: Dict[str, Any] = {}
        self.table_field_key: Optional[str] = None
        self.item_fields: Dict[str, Any] = {}

    def on_start(self, context: dict) -> None:
        """Perform task initialization and early validation.

        Sets up the task context, loads configuration from the correct path,
        and validates required configuration parameters.

        Args:
            context: The pipeline context dictionary.

        Raises:
            TaskError: If required configuration parameters are missing.

        Side Effects:
            - Initializes context with standard keys.
            - Loads and validates api_key and fields from config.
            - Finds and stores table field configuration.
        """
        try:
            # Call parent on_start to initialize context
            super().on_start(context)

            # Load params from config_manager with fallback to self.params
            params = self.config_manager.get(f'tasks.{self.task_slug}.params', self.params)

            if params is None:
                params = {}

            if not isinstance(params, dict):
                params = {}

            # Extract required parameters with explicit types for static analysis.
            api_key = params.get('api_key')
            self.api_key = api_key if isinstance(api_key, str) else None
            configuration_id = params.get('configuration_id')
            self.configuration_id = configuration_id if isinstance(configuration_id, str) else None
            self.tier = str(params.get('tier') or 'agentic')
            parse_tier = params.get('parse_tier')
            self.parse_tier = parse_tier if isinstance(parse_tier, str) else None
            self.extraction_target = str(params.get('extraction_target') or 'per_doc')
            cite_sources = params.get('cite_sources')
            self.cite_sources = cite_sources if isinstance(cite_sources, bool) else None
            confidence_scores = params.get('confidence_scores', True)
            self.confidence_scores = confidence_scores if isinstance(confidence_scores, bool) else None
            project_id = params.get('project_id')
            self.project_id = project_id if isinstance(project_id, str) else None
            organization_id = params.get('organization_id')
            self.organization_id = organization_id if isinstance(organization_id, str) else None
            self.poll_interval_seconds = float(params.get('poll_interval_seconds', 2.0))
            self.timeout_seconds = float(params.get('timeout_seconds', 1800.0))
            fields = params.get('fields', {})
            self.fields = fields if isinstance(fields, dict) else {}

            self.logger.info(f"Loaded {len(self.fields)} fields from configuration")

            # Find table field configuration (marked with is_table: true)
            table_fields = []
            for field_key, field_config in self.fields.items():
                if field_config.get('is_table', False):
                    table_fields.append(field_key)

            if table_fields:
                if len(table_fields) > 1:
                    error_msg = f"Multiple table fields configured: {table_fields}. Only one table field is supported."
                    self.logger.error(error_msg)
                    raise TaskError(error_msg)
                table_field_key = table_fields[0]
                self.table_field_key = table_field_key
                table_config = self.fields.get(table_field_key, {})
                self.item_fields = table_config.get('item_fields', {}) if isinstance(table_config, dict) else {}
                self.logger.info(f"Found table field: {table_field_key} with {len(self.item_fields)} item fields")
            else:
                self.table_field_key = None
                self.item_fields = {}
                self.logger.debug("No table fields found in configuration")

        except Exception as e:
            error_msg = f"Failed to initialize ExtractPdfTask: {str(e)}"
            self.logger.error(error_msg)
            raise TaskError(error_msg)

    def _require_api_key(self) -> str:
        """Return the configured API key after narrowing its type."""
        if not self.api_key:
            raise TaskError("API key not found in configuration")
        return self.api_key

    def _extract_with_retry(self, file_path: str, max_retries: int = 3) -> Any:
        """Extract PDF with retry logic and exponential backoff.

        Args:
            file_path: Path to the PDF file to extract.
            max_retries: Maximum number of retry attempts.

        Returns:
            Extracted result from LlamaCloud Extract v2 API.

        Raises:
            TaskError: If all retry attempts fail.
        """
        import time
        import random

        for attempt in range(max_retries):
            try:
                self.logger.debug(f"Extraction attempt {attempt + 1}/{max_retries} for {file_path}")
                api_key = self._require_api_key()

                extracted_result = run_extract_v2_job(
                    api_key=api_key,
                    file_path=file_path,
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

                self.logger.info(f"Extraction successful on attempt {attempt + 1}")
                return extracted_result

            except Exception as e:
                if is_non_retryable_extract_error(e):
                    error_msg = humanize_extract_error(e, configuration_id=self.configuration_id)
                    self.logger.error(error_msg)
                    raise TaskError(error_msg)

                if attempt == max_retries - 1:
                    # Last attempt failed, raise the error
                    error_msg = humanize_extract_error(e, configuration_id=self.configuration_id)
                    self.logger.error(error_msg)
                    raise TaskError(error_msg)

                # Calculate exponential backoff delay with jitter
                delay = (2 ** attempt) + random.uniform(0, 1)
                self.logger.warning(f"Extraction attempt {attempt + 1} failed: {str(e)}. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)

        # This should never be reached, but just in case
        error_msg = f"Extraction failed after {max_retries} attempts"
        raise TaskError(error_msg)

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute PDF extraction with array-of-objects support.

        Extracts structured data from PDF using LlamaCloud Extract v2, handling
        both scalar fields and table fields (arrays of objects). Processes
        the response, normalizes field names, applies type conversions, and
        preserves metadata.

        Args:
            context: Pipeline context containing:
                - id: Unique identifier.
                - file_path: Path to PDF file for extraction

        Returns:
            Updated context dictionary with:
                - data: Normalized extracted data (scalars + table arrays)
                - metadata: Extraction metadata including citations and usage

        Raises:
            TaskError: If file path is missing, extraction fails, or
                      validation errors occur.
        """
        file_path = context.get("file_path")

        # Wrap entire logic in try-except for proper error handling
        try:
            # Validate required fields
            self.validate_required_fields(context)

            # Use windows_long_path for file path
            from modules.utils import windows_long_path
            if file_path is None:
                error_msg = "File path is None"
                raise TaskError(error_msg)
            normalized_file_path = windows_long_path(file_path)

            config_label = self.configuration_id or "inline field schema"
            self.logger.info(f"Starting v2 extraction from {normalized_file_path} using {config_label}")

            # Retry logic for API calls
            extracted_result = self._extract_with_retry(normalized_file_path)

            # Extract data from response
            data = getattr(extracted_result, 'data', {}) or {}
            metadata = getattr(extracted_result, 'extraction_metadata', {}) or {}
            field_count = len(data) if isinstance(data, dict) else 0
            self.logger.info(
                "Extraction job %s returned %s fields for %s",
                getattr(extracted_result, "job_id", None),
                field_count,
                context.get("id", "unknown"),
            )

            # Find table field configuration
            table_field_config = self._find_table_field_config()
            table_field_key = table_field_config['key'] if table_field_config else None
            table_field_alias = table_field_config['alias'] if table_field_config else None

            # Process scalar fields and table fields
            processed_data = self._process_fields(data, table_field_key, table_field_alias)

            # Initialize context data if needed
            if "data" not in context or not isinstance(context["data"], dict):
                context["data"] = {}

            # Update context with processed data
            context["data"].update(processed_data)

            # Preserve metadata
            context["metadata"] = {
                "extraction_configuration_id": self.configuration_id,
                "extraction_job_id": getattr(extracted_result, "job_id", None),
                "extraction_metadata": metadata,
                "extraction_status": "success"
            }

            self._persist_extraction_result(
                context=context,
                processed_data=processed_data,
                metadata=metadata if isinstance(metadata, dict) else {},
                provider_job_id=getattr(extracted_result, "job_id", None),
            )

            self.logger.info("V2 extraction successful for %s", context.get("id", "unknown"))
            return context

        except TaskError as e:
            # Handle TaskError specifically
            message = _redact_text(getattr(e, "message", str(e)))
            context["fatal_failure"] = {
                "failure_type": "extract_task_failed",
                "message": message,
                "provider": "llamacloud_extract_v2",
                "configuration_id": self.configuration_id,
                "operator_action": (
                    "Inspect the source PDF or LlamaCloud Extract configuration, "
                    "then re-ingest as a new document if appropriate."
                ),
            }
            self.register_error(context, e)
            raise
        except Exception as e:
            # Handle unexpected exceptions
            error_msg = _redact_text(f"Unexpected error in {self.task_slug}: {str(e)}")
            self.logger.error(error_msg)
            task_error = TaskError(error_msg)
            context["fatal_failure"] = {
                "failure_type": "extract_unexpected_error",
                "message": error_msg,
                "provider": "llamacloud_extract_v2",
                "configuration_id": self.configuration_id,
                "operator_action": (
                    "Inspect the source PDF or LlamaCloud Extract configuration, "
                    "then re-ingest as a new document if appropriate."
                ),
            }
            self.register_error(context, task_error)
            raise task_error

    def _persist_extraction_result(
        self,
        *,
        context: Dict[str, Any],
        processed_data: Dict[str, Any],
        metadata: Dict[str, Any],
        provider_job_id: str | None,
    ) -> None:
        """Persist extraction result and normalized fields when document state exists."""
        document_id = context.get("document_id")
        if not document_id:
            return

        fields = self._build_persisted_fields(processed_data, metadata)
        with connect(self.config_manager) as conn:
            repository = ExtractionRepository(conn)
            result = repository.save_result(
                document_id=str(document_id),
                task_run_id=context.get("task_run_id"),
                provider="llamacloud_extract_v2",
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
    ) -> List[Dict[str, Any]]:
        """Convert processed extraction output into extracted_fields rows."""
        persisted_fields: List[Dict[str, Any]] = []
        for field_key, value in processed_data.items():
            field_config = self.fields.get(field_key, {})
            alias = field_config.get("alias", field_key) if isinstance(field_config, dict) else field_key
            confidence = self._extract_numeric_confidence(metadata, field_key, alias)
            persisted_fields.append(
                {
                    "field_key": field_key,
                    "field_alias": alias,
                    "extracted_value": value,
                    "final_value": value,
                    "confidence": confidence,
                    "confidence_label": self._extract_confidence_label(metadata, field_key, alias),
                    "requires_review": False,
                    "review_status": "not_required",
                    "source": self._extract_field_source(metadata, field_key, alias),
                }
            )
        return persisted_fields

    @staticmethod
    def _metadata_candidates(metadata: Dict[str, Any], field_key: str, alias: str) -> list[Any]:
        """Return likely field-specific metadata objects from varied provider shapes."""
        from standard_step.extraction.llama_cloud_v2 import metadata_candidates

        return metadata_candidates(metadata, field_key, alias)

    @classmethod
    def _extract_numeric_confidence(cls, metadata: Dict[str, Any], field_key: str, alias: str) -> float | None:
        """Extract numeric confidence, preserving NULL when confidence is absent or non-numeric."""
        return extract_numeric_confidence(metadata, field_key, alias)

    @classmethod
    def _extract_confidence_label(cls, metadata: Dict[str, Any], field_key: str, alias: str) -> str | None:
        """Extract a textual confidence label when provider metadata includes one."""
        return extract_confidence_label(metadata, field_key, alias)

    @classmethod
    def _extract_field_source(cls, metadata: Dict[str, Any], field_key: str, alias: str) -> Dict[str, Any]:
        """Extract field citation/source metadata when present."""
        return extract_field_source(metadata, field_key, alias)

    def validate_required_fields(self, context: Dict[str, Any]) -> None:
        """Validate required configuration parameters.

        Ensures that all required extraction parameters are present and valid,
        including API key, fields configuration, and file path. A saved Extract
        v2 configuration ID is optional because the task can build an inline
        schema from configured fields.

        Args:
            context: Pipeline context containing file_path and other required data.

        Raises:
            TaskError: If any required parameter is missing or invalid.
        """
        # Call parent validation
        super().validate_required_fields(context)

        # Validate API key is non-empty. A saved configuration is optional because
        # the task can build an inline Extract v2 configuration from fields.
        if not self.api_key:
            error_msg = "API key not found in configuration"
            self.logger.error(error_msg)
            raise TaskError(error_msg)

        # Validate fields configuration is non-empty
        if not self.fields:
            error_msg = "Fields configuration not found"
            self.logger.error(error_msg)
            raise TaskError(error_msg)

        # Validate file path exists
        file_path = context.get("file_path")
        if not file_path:
            error_msg = "File path not provided in context"
            self.logger.error(error_msg)
            raise TaskError(error_msg)

        # Use windows_long_path for path validation
        from modules.utils import windows_long_path
        normalized_path = windows_long_path(file_path)

        import os
        if not os.path.exists(normalized_path):
            error_msg = f"File does not exist: {normalized_path}"
            self.logger.error(error_msg)
            raise TaskError(error_msg)

        self.logger.debug(f"Validated file path: {normalized_path}")

    def _find_table_field_config(self) -> Optional[Dict[str, Any]]:
        """Find the table field configuration (marked with is_table: true).

        Returns the table field configuration using instance variables set in on_start.
        This implements the PRD limitation of supporting only one table per extraction.

        Returns:
            Dictionary containing 'key' and 'alias' of the table field, or None if not found.
        """
        if not self.table_field_key:
            return None

        # Get the table field configuration from fields
        field_config = self.fields.get(self.table_field_key, {})
        return {
            'key': self.table_field_key,
            'alias': field_config.get('alias', self.table_field_key),
            'config': field_config
        }

    def _process_fields(self, data: Dict[str, Any], table_field_key: Optional[str],
                       table_field_alias: Optional[str]) -> Dict[str, Any]:
        """Process and normalize extracted fields.

        Handles both scalar fields and table fields, applying normalization,
        type conversion, and structural transformations as needed.

        Args:
            data: Raw extracted data from LlamaCloud Extract response.
            table_field_key: Key name of the table field in configuration.
            table_field_alias: Alias name of the table field in the data.

        Returns:
            Dictionary keyed by configured workflow field names with processed values.
        """
        processed_data = {}

        if not self.fields:
            return processed_data

        for field_key, field_config in self.fields.items():
            alias = field_config.get('alias', field_key)
            is_table = field_config.get('is_table', False)

            # Skip table fields - handled separately
            if is_table:
                if field_key == table_field_key:
                    table_data = self._process_table_field(data, field_key, alias, field_config)
                    processed_data[field_key] = table_data
                continue

            # Process scalar field
            found, value = self._get_extracted_value(data, field_key, alias)
            if found:
                value = self._process_scalar_field(value, field_config)
                processed_data[field_key] = value

        return processed_data

    @staticmethod
    def _get_extracted_value(
        data: Dict[str, Any],
        field_key: str,
        alias: str,
    ) -> tuple[bool, Any]:
        """Return extracted value by alias or field key.

        LlamaCloud saved configurations may return JSON keys as schema field
        names (for example, ``supplier_name``), while inline schemas may return
        display aliases (for example, ``Supplier name``). The workflow accepts
        both.
        """
        if alias in data:
            return True, data[alias]
        if field_key in data:
            return True, data[field_key]
        return False, None

    def _process_value(self, value: Any, type_str: str) -> Any:
        """Process a value with lightweight type parser supporting Optional, List, Dict, and nested types.

        Supports type annotations including:
        - Simple types: 'str', 'float', 'int', 'bool', 'Decimal'
        - Optional types: 'Optional[str]', 'Optional[List[float]]'
        - List types: 'List[str]', 'List[Dict[str, str]]'
        - Dict types: 'Dict[str, str]'
        - Nested types: 'List[List[str]]', 'Optional[List[Dict[str, Any]]]'

        Args:
            value: Raw value to process.
            type_str: Type string to parse and apply.

        Returns:
            Processed value with appropriate type conversion and structure.

        Note:
            - For Optional[T]: Returns None if value is None, otherwise processes inner type T
            - For List[T]: If value is list, maps _process_value(item, T) for each item; filters None if Optional[List]
            - For Dict[K, V]: If value is dict, processes key-value pairs with respective types
            - For nested types: Applies parser recursively depth-first
            - Fallback: Returns value as-is with warning log for unknown types
        """
        from decimal import Decimal

        # Handle None values for Optional types
        if value is None:
            # Check if type is Optional - if so, return None
            if type_str.startswith('Optional[') and type_str.endswith(']'):
                return None
            # For non-Optional types, return None as-is
            return None

        # Strip Optional wrapper and process inner type
        inner_type = type_str
        is_optional = False
        if inner_type.startswith('Optional[') and inner_type.endswith(']'):
            is_optional = True
            inner_type = inner_type[9:-1]  # Remove 'Optional[' prefix and ']' suffix

        # Custom coercion functions for enhanced type conversion
        def bool_coerce(val: Any) -> bool:
            """Custom boolean coercion with loose parsing used by scalar extraction.

            For str values, checks lowercase: 'false', 'f', 'no', '0', 'off' -> False
            For non-str values, uses bool(value)
            """
            if isinstance(val, str):
                false_values = {'false', 'f', 'no', '0', 'off'}
                if val.lower() in false_values:
                    self.logger.debug(f"Coerced '{val}' to bool False")
                    return False
                # For other strings, let bool() handle it (e.g., 'true', '1', etc.)
            result = bool(val)
            self.logger.debug(f"Coerced '{val}' to bool {result}")
            return result

        def int_coerce(val: Any) -> int:
            """Custom integer coercion using a float intermediate step for scalar extraction.

            First tries float(value) to handle decimals like "12.0" -> 12.0
            Then int(that) to get integer. Handles "00123" -> 123 via float stripping zeros.
            Catches ValueError and logs warning, returns value as-is if strict mode fails.
            """
            try:
                # First try float to handle decimal strings like "12.0"
                float_val = float(val)
                result = int(float_val)
                self.logger.debug(f"Coerced '{val}' to int {result}")
                return result
            except (ValueError, TypeError) as e:
                self.logger.warning(f"Failed to convert {val} to int: {e}")
                return val

        # Conversion table for simple types using custom coercion functions
        conversion_table = {
            'str': str,
            'float': float,
            'int': int_coerce,
            'bool': bool_coerce,
            'Decimal': Decimal
        }

        # Handle simple types (no brackets)
        if '[' not in inner_type and '{' not in inner_type:
            converter = conversion_table.get(inner_type)
            if converter:
                try:
                    return converter(value)
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"Failed to convert {value} to {inner_type}: {e}")
                    return value
            else:
                # Unknown simple type, return as-is
                self.logger.warning(f"Unknown simple type: {inner_type}")
                return value

        # Handle List types: List[T] or List[List[T]]
        if inner_type.startswith('List['):
            if not isinstance(value, list):
                return value

            # Extract inner type from List[T]
            if not inner_type.endswith(']'):
                self.logger.warning(f"Malformed List type: {inner_type}")
                return value

            list_content = inner_type[5:-1]  # Remove 'List[' and ']'
            processed_list = []

            for item in value:
                # Filter None values for Optional[List] types
                if item is None and is_optional:
                    continue
                processed_item = self._process_value(item, list_content)
                processed_list.append(processed_item)

            return processed_list

        # Handle Dict types: Dict[K, V]
        if inner_type.startswith('Dict['):
            if not isinstance(value, dict):
                return value

            # Extract key_type, value_type from Dict[K, V]
            if not inner_type.endswith(']'):
                self.logger.warning(f"Malformed Dict type: {inner_type}")
                return value

            dict_content = inner_type[5:-1]  # Remove 'Dict[' and ']'

            # Split on comma to separate key and value types
            parts = [p.strip() for p in dict_content.split(',')]
            if len(parts) != 2:
                self.logger.warning(f"Malformed Dict type content: {dict_content}")
                return value

            key_type, value_type = parts

            processed_dict = {}
            for k, v in value.items():
                processed_key = self._process_value(k, key_type)
                processed_value = self._process_value(v, value_type)
                processed_dict[processed_key] = processed_value

            return processed_dict

        # Unknown complex type
        self.logger.warning(f"Unknown complex type: {inner_type}")
        return value

    def _process_scalar_field(self, value: Any, field_config: Dict[str, Any]) -> Any:
        """Process a scalar field with configured type conversion.

        Args:
            value: Raw field value from extraction.
            field_config: Field configuration including type and alias.

        Returns:
            Processed value with appropriate type conversion.
        """
        field_type = field_config.get('type', 'str')
        return self._process_value(value, field_type)

    def _process_table_field(self, data: Dict[str, Any], field_key: str, alias: str,
                            field_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process table field (array of objects) with subfield mapping.

        Args:
            data: Raw extracted data containing the table field.
            field_key: Configured workflow field key.
            alias: Field alias in the extracted data.
            field_config: Table field configuration including item_fields.

        Returns:
            List of dictionaries keyed by configured subfield names with cleaned values.
        """
        found, table_data = self._get_extracted_value(data, field_key, alias)
        if not found:
            table_data = []

        if not isinstance(table_data, list):
            self.logger.warning(f"Table field {alias} is not a list, returning empty list")
            return []

        processed_items = []
        item_fields = field_config.get('item_fields', {})

        self.logger.debug(f"Processing {len(table_data)} table items with {len(item_fields)} configured fields")

        for item_idx, item in enumerate(table_data):
            if not isinstance(item, dict):
                self.logger.warning(f"Table item at index {item_idx} is not a dict: {item}")
                continue

            processed_item = {}
            for subfield_key, subfield_config in item_fields.items():
                subfield_alias = subfield_config.get('alias', subfield_key)

                found, value = self._get_extracted_value(item, subfield_key, subfield_alias)
                if found:
                    # Clean string values (replace newlines with spaces)
                    if isinstance(value, str):
                        value = re.sub(r'\n+', ' ', value.strip())
                    # Apply type conversion using enhanced _process_value method
                    processed_value = self._process_value(value, subfield_config.get('type', 'str'))
                    processed_item[subfield_key] = processed_value
                    self.logger.debug(f"Processed table field {subfield_key} -> {processed_value}")
                else:
                    self.logger.debug(f"Field alias '{subfield_alias}' not found in table item {item_idx}")

            if processed_item:  # Only add non-empty items
                processed_items.append(processed_item)
                self.logger.debug(f"Added processed table item: {processed_item}")
            else:
                self.logger.debug(f"Skipping empty table item at index {item_idx}")

        self.logger.info(f"Successfully processed {len(processed_items)}/{len(table_data)} table items")
        return processed_items
