"""Extract structured data from PDFs using a configured external agent.

This module provides ExtractPdfTask, a pipeline step that orchestrates
document data extraction via the LlamaExtract service. It validates required
parameters, calls the remote agent, post-processes the result, validates it
against a dynamically created Pydantic model, and merges the data into the
pipeline context.

Notes:
    - Reads runtime parameters (api_key, agent_id, fields) from BaseTask.params.
    - Updates processing status via StatusManager on start/success/failure.
    - Interacts with the filesystem indirectly via the external service using
      the provided file path.
    - Errors are surfaced as TaskError after being logged and status-updated.
"""
import logging
from typing import Any, Dict, Optional
from pydantic import create_model
from pydantic import BaseModel, ValidationError, Field, ConfigDict
from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError
from modules.status_manager import StatusManager

from llama_cloud_services import LlamaExtract


class ExtractPdfTask(BaseTask):
    """Task that extracts domain data from a PDF using LlamaExtract.

    Responsibilities:
        - Validate required parameters (api_key, agent_id, fields).
        - Invoke LlamaExtract agent to extract data from the file path.
        - Filter/normalize extracted lists to remove None values when needed.
        - Validate fields using a dynamically created Pydantic model.
        - Merge validated data into context['data'] and update metadata/status.

    Integration:
        Uses BaseTask for context initialization and error conventions and
        StatusManager for consistent progress reporting.

    Args:
        config_manager (ConfigManager): Project configuration manager.
        **params: Expected keys include 'api_key', 'agent_id', and 'fields'.

    Notes:
        - Side effects include remote API calls and status updates.
        - Raises TaskError for validation or extraction errors.

    Performance Considerations:
        - PDF extraction involves remote API calls that may have rate limits imposed by the external service.
        - Large PDF files (>50MB) may cause extended processing times; consider file size optimization for high-volume scenarios.
    """

    def __init__(self, config_manager: ConfigManager, **params):
        """Initialize ExtractPdfTask and capture required parameters.

        Args:
            config_manager (ConfigManager): The application configuration manager.
            **params: Runtime parameters: 'api_key', 'agent_id', and 'fields'.

        Notes:
            Parameters are accessed via self.params provided by BaseTask.
        """
        super().__init__(config_manager=config_manager, **params)
        self.logger = logging.getLogger(__name__)
        self.status_manager = StatusManager(self.config_manager)
        
        # Parameters are now directly available via self.params
        self.api_key = self.params.get("api_key")
        self.agent_id = self.params.get("agent_id")
        self.fields = self.params.get("fields")

    def on_start(self, context: dict):
        """Lifecycle hook executed when the task starts.

        Initializes context and marks the task as started in StatusManager.
        Also performs parameter presence checks and fails early if missing.

        Args:
            context (dict): The pipeline context dict. Must contain 'id'.

        Raises:
            TaskError: If any of api_key, agent_id, or fields are missing.

        Notes:
            - Uses StatusManager to record both start and early failure states.
        """
        # Initialize context keys
        self.initialize_context(context)
        # Unified timestamp convention
        self.status_manager.update_status(str(context.get('id', 'unknown')), "Task Started: extract_document_data", step="Task Started: extract_document_data")

        if not self.api_key:
            self.status_manager.update_status(str(context.get('id', 'unknown')), "Task Failed: extract_document_data", step="ExtractPdfTask", error="API key not found in configuration for ExtractPdfTask.")
            raise TaskError("API key not found in configuration for ExtractPdfTask.")
        if not self.agent_id:
            self.status_manager.update_status(str(context.get('id', 'unknown')), "Task Failed: extract_document_data", step="ExtractPdfTask", error="Agent ID not found in configuration for ExtractPdfTask.")
            raise TaskError("Agent ID not found in configuration for ExtractPdfTask.")
        if not self.fields:
            self.status_manager.update_status(str(context.get('id', 'unknown')), "Task Failed: extract_document_data", step="ExtractPdfTask", error="Fields not found in configuration for ExtractPdfTask.")
            raise TaskError("Fields not found in configuration for ExtractPdfTask.")

    def run(self, context: dict) -> dict:
        """Run the extraction against the configured agent and validate results.

        Expects a file path in the context and validates configured field
        definitions. It calls the remote agent to extract data, normalizes list
        fields, validates using a dynamically created Pydantic model, and
        writes validated values to context['data'] and metadata.

        Args:
            context (dict): Pipeline context. Requires:
                - id (str): Unique identifier for status updates.
                - file_path (str): Source PDF file to extract from.

        Returns:
            dict: Updated context with:
                - data (dict): Validated extracted values merged in.
                - metadata (dict): Includes extraction_agent_id and status.

        Raises:
            TaskError: If file_path is missing, validation fails, or the
                external service reports an error.

        Notes:
            - Side effects: Status updates via StatusManager, remote API call.

        Performance Considerations:
            - This method makes synchronous remote API calls that may be subject to rate limiting by the external service.
            - PDF processing times scale with file size and complexity; monitor API quotas for high-volume processing scenarios.
        """
        file_path = context.get("file_path")
        unique_id = str(context.get("id"))

        if not file_path:
            self.status_manager.update_status(unique_id, "Task Failed: extract_document_data", step="ExtractPdfTask", error="File path not provided in context.")
            raise TaskError("File path not provided in context.")

        if not self.fields:
            error_msg = "Fields configuration is missing or empty."
            self.logger.error(error_msg)
            self.status_manager.update_status(unique_id, "Task Failed: extract_document_data", step="ExtractPdfTask", error=error_msg)
            raise TaskError(error_msg)

        self.logger.info(f"Extracting data from {file_path} using agent {self.agent_id}...")

        try:
            # Initialize LlamaExtract client
            client = LlamaExtract(api_key=self.api_key)

            # Get the agent by agent_id (use named parameter id=)
            agent = client.get_agent(id=self.agent_id)

            # Update status: agent acquired
            self.status_manager.update_status(unique_id, "Agent acquired", step="Agent acquired")

            # Call agent.extract with the PDF file path
            extracted_result = agent.extract(file_path)

            # Update status: extraction completed
            self.status_manager.update_status(unique_id, "Extraction completed", step="Extraction completed")

            self.logger.info(f"Raw extracted data for {unique_id}: {extracted_result}")

            # Extract data dictionary from result
            data = getattr(extracted_result, 'data', {}) or {}

            # Preprocess data: filter None from lists for configured fields
            processed_data = data.copy()
            for field_name, field_config in self.fields.items():
                alias = field_config.get("alias")
                if alias and alias in processed_data and isinstance(processed_data[alias], list):
                    field_type_str = field_config.get("type", "")
                    if "List[str]" in field_type_str or "Optional[List[str]]" in field_type_str:
                        original_list = processed_data[alias]
                        filtered_list = [item for item in original_list if item is not None]
                        processed_data[alias] = filtered_list

            # Update status: preprocessing done
            self.status_manager.update_status(unique_id, "Preprocessing done", step="Preprocessing done")

            # Dynamically create Pydantic model for validation based on fields config
            model_fields = {}
            for field_name, field_config in self.fields.items():
                field_type_str = field_config.get("type", "Any")
                field_type = eval(field_type_str, {"List": list, "Optional": Optional, "str": str, "float": float, "int": int, "Any": Any})
                alias = field_config.get("alias", field_name)
                model_fields[field_name] = (field_type, Field(alias=alias))
            model_config = ConfigDict(populate_by_name=True, extra="ignore")
            DynamicModel = create_model("DynamicModel", __config__=model_config, **model_fields)

            # Validate extracted data
            validated_data = DynamicModel(**processed_data).model_dump()

            # Update status: validation done
            self.status_manager.update_status(unique_id, "Validation done", step="Validation done")

            # Merge extracted data into existing context['data'] dictionary
            if "data" not in context or not isinstance(context["data"], dict):
                context["data"] = {}
            context["data"].update(validated_data)

            # Update context with metadata
            context["metadata"] = {
                "extraction_agent_id": self.agent_id,
                "extraction_status": "success"
            }

            # Unified timestamp convention
            self.status_manager.update_status(unique_id, "Task Completed: extract_document_data", step="Task Completed: extract_document_data")
            self.logger.info(f"Extraction successful for {unique_id}")

        except ValidationError as ve:
            error_msg = f"Validation error during extraction: {ve}"
            self.logger.error(error_msg)
            # Unified timestamp convention
            self.status_manager.update_status(unique_id, "Task Failed: extract_document_data", step="Task Failed: extract_document_data", error=error_msg)
            raise TaskError(error_msg)

        except Exception as e:
            error_msg = f"Extraction failed: {e}"
            self.logger.error(error_msg)
            # Unified timestamp convention
            self.status_manager.update_status(unique_id, "Task Failed: extract_document_data", step="Task Failed: extract_document_data", error=error_msg)
            raise TaskError(error_msg)

        return context

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
        if not self.agent_id:
            errors.append("Agent ID is missing in configuration.")
        if not self.fields:
            errors.append("Fields are missing in configuration.")

        if errors:
            error_msg = " ".join(errors)
            self.logger.error(error_msg)
            raise TaskError(error_msg)
