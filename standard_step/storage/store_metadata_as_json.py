"""Persist extracted metadata as a JSON file with optional alias mapping.

This module provides StoreMetadataAsJson, a pipeline task that serializes
context['data'] to a JSON file in a configured directory. Keys are mapped to
their configured aliases when available. The file name is created from a
template and uniqueness is ensured before writing.

Notes:
    - Reads 'data_dir' and 'filename' from task params (required).
    - Uses StatusManager for standardized start/success/failure updates.
    - Performs filesystem writes and guarantees a unique output path.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from modules.utils import sanitize_filename, generate_unique_filepath, preprocess_filename_value
from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError
import logging
from modules.utils import windows_long_path


class StoreMetadataAsJson(BaseTask):
    """Task that writes extracted metadata to a JSON file.

    Responsibilities:
        - Validate required parameters and resolve output directory.
        - Map keys to configured aliases when available.
        - Generate a unique filename from a template and write JSON output.

    Integration:
        Uses BaseTask params for configuration and StatusManager for progress
        reporting. Expects extracted data in context['data'].

    Args:
        config_manager (ConfigManager): Project configuration manager.
        **params: Must include 'data_dir' (str) and 'filename' (str).

    Notes:
        - Side effects: Filesystem write and status updates.
        - Errors are reported as TaskError and logged.
    """

    def __init__(self, config_manager: ConfigManager, **params):
        """Initialize the task and capture required parameters.

        Args:
            config_manager (ConfigManager): The configuration manager instance.
            **params: Must include 'data_dir' and 'filename'.

        Raises:
            TaskError: If required parameters are missing.
        """
        super().__init__(config_manager=config_manager, **params)
        self.logger = logging.getLogger(__name__)  # Initialize logger
        
        self.data_dir: Optional[Path] = None
        self.filename_template: Optional[str] = None
        self.extraction_fields_config: Optional[Dict[str, Any]] = None

        # Extract parameters from self.params
        data_dir_str = self.params.get('data_dir')
        filename = self.params.get('filename')

        if not data_dir_str:
            raise TaskError("Missing 'data_dir' parameter in configuration for StoreMetadataAsJson task.")
        if not filename:
            raise TaskError("Missing 'filename' parameter in configuration for StoreMetadataAsJson task.")

        
        self.data_dir = Path(windows_long_path(data_dir_str))
        self.filename_template = filename

        # Optional: look up extraction fields configuration for aliasing
        tasks_config = self.config_manager.get_all().get("tasks", {})
        extract_task_definition = tasks_config.get("extract_document_data", {})
        extraction_step_params = extract_task_definition.get("params", {})
        
        if "fields" in extraction_step_params:
            self.extraction_fields_config = extraction_step_params["fields"]

        if not self.extraction_fields_config:
            self.logger.warning("Could not find 'extraction.fields' configuration. JSON keys might not use aliases.")

    def on_start(self, context: Dict[str, Any]) -> None:
        """Lifecycle hook executed when the task starts.

        Initializes context and marks the task as started in StatusManager.

        Args:
            context (Dict[str, Any]): The pipeline context.
        """
        # Initialize context keys
        self.initialize_context(context)
        # Unified timestamp convention
        try:
            unique_id = str(context.get("id", "unknown"))
            from modules.status_manager import StatusManager
            StatusManager(self.config_manager).update_status(unique_id, "Task Started: store_metadata_json", step="Task Started: store_metadata_json")
        except Exception:
            # Avoid failing start on status write issues
            pass

    def validate_required_fields(self, context: Dict[str, Any]):
        """Validate required parameters.

        Args:
            context (Dict[str, Any]): Unused; present for interface parity.

        Raises:
            TaskError: If data_dir or filename_template are not set.
        """
        if not self.data_dir:
            raise TaskError("StoreMetadataAsJson task missing required field: 'data_dir'")
        if not self.filename_template:
            raise TaskError("StoreMetadataAsJson task missing required field: 'filename_template'")
        # No need to validate extraction_fields_config as it's optional for basic functionality

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Write extracted metadata to a JSON file in the configured directory.

        Serializes context['data'] to JSON, mapping keys to aliases if provided
        in the extraction fields configuration.

        Args:
            context (Dict[str, Any]): Pipeline context containing:
                - id (str): Unique identifier for status logging.
                - data (dict): Extracted metadata to persist.

        Returns:
            Dict[str, Any]: The unmodified context.

        Raises:
            TaskError: If extracted data is missing/unsupported or writing fails.

        Notes:
            - Side effects: Filesystem write and status updates via StatusManager.
        """
        extracted_data = context.get("data")  # Use "data" as per PRD
        unique_id = context.get("id")

        if not extracted_data:
            self.logger.warning(f"No extracted data found for {unique_id}. Skipping JSON storage.")
            return context

        self.validate_required_fields(context)  # Call validation here

        # Ensure filename_template and data_dir are not None after validation
        if self.filename_template is None:
            raise TaskError("Filename template is not set after validation.")
        if self.data_dir is None:
            raise TaskError("Data directory is not set after validation.")

        # Update status: preparing to write JSON
        try:
            from modules.status_manager import StatusManager
            StatusManager(self.config_manager).update_status(str(unique_id), "Preparing to write JSON", step="Preparing to write JSON")
        except Exception:
            pass

        # Generate filename from template and extracted data
        try:
            # Format the filename using extracted_data. Ensure all values are strings for formatting.
            # Also, sanitize each part of the filename.
            formatted_filename_parts = {
                k: sanitize_filename(preprocess_filename_value(v)) if not isinstance(v, list) else sanitize_filename(",".join(map(preprocess_filename_value, v)))
                for k, v in extracted_data.items()
            }
            base_filename = self.filename_template.format(**formatted_filename_parts)
        except KeyError as e:
            raise TaskError(f"Filename template '{self.filename_template}' contains missing key from extracted data: {e}")
        except Exception as e:
            raise TaskError(f"Failed to format filename using template '{self.filename_template}': {e}")

        # Ensure .json extension
        if not base_filename.lower().endswith(".json"):
            base_filename += ".json"
        
        # Generate unique filepath
        output_path = generate_unique_filepath(self.data_dir, os.path.splitext(base_filename)[0], ".json")

        # Update status: writing JSON file
        try:
            from modules.status_manager import StatusManager
            StatusManager(self.config_manager).update_status(str(unique_id), "Writing JSON file", step="Writing JSON file")
        except Exception:
            pass

        try:
            # Transform keys to aliases
            processed_json_data = {}
            if isinstance(extracted_data, dict):
                for key, value in extracted_data.items():
                    alias = key
                    if self.extraction_fields_config and key in self.extraction_fields_config:
                        alias = self.extraction_fields_config[key].get("alias", key)
                    processed_json_data[alias] = value
            else:
                # If extracted_data is not a dict, store it as is or raise an error
                # For now, let's assume it's always a dict for JSON storage based on PRD
                raise TaskError("Extracted data is not in a supported format (dict) for JSON storage.")

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(processed_json_data, f, indent=4)
            self.logger.info(f"Metadata for {unique_id} stored as JSON at {output_path}")
            # Unified timestamp convention (success)
            try:
                from modules.status_manager import StatusManager
                StatusManager(self.config_manager).update_status(str(unique_id), "Task Completed: store_metadata_json", step="Task Completed: store_metadata_json")
            except Exception:
                pass
        except Exception as e:
            # Unified timestamp convention (failure)
            try:
                from modules.status_manager import StatusManager
                StatusManager(self.config_manager).update_status(str(unique_id), "Task Failed: store_metadata_json", step="Task Failed: store_metadata_json", error=str(e))
            except Exception:
                pass
            raise TaskError(f"Failed to store metadata as JSON for {unique_id}: {e}")

        return context
