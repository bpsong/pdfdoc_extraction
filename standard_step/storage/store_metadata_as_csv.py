"""Persist extracted metadata as a CSV file with alias-aware headers.

This module provides StoreMetadataAsCsv, a pipeline task that writes extracted
data ('context.data') to a CSV file in a configured directory. It supports both
a single dict and a list of dicts. Column headers prefer configured aliases
(from the extraction fields config) when available. The output filename is
formatted from a template and made unique if needed.

Notes:
    - Reads 'data_dir' and 'filename' from task params (required).
    - Uses StatusManager for standardized start/success/failure updates.
    - Performs filesystem writes and guarantees a unique output path.
"""

import csv
import os
from pathlib import Path
from typing import Any, Dict, Optional, List
from modules.utils import sanitize_filename, generate_unique_filepath, preprocess_filename_value
from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError
import logging
from modules.utils import windows_long_path


class StoreMetadataAsCsv(BaseTask):
    """Task that writes extracted metadata to a CSV file.

    Responsibilities:
        - Validate required parameters and resolve output directory.
        - Normalize extracted data (dict or list of dicts) for CSV writing.
        - Prefer alias names for headers when available in extraction config.
        - Generate a unique filename from a template and write the CSV.

    Integration:
        Uses BaseTask params for configuration and StatusManager for progress
        reporting. Expects extracted data in context['data'].

    Args:
        config_manager (ConfigManager): Project configuration manager.
        **params: Must include 'data_dir' (str) and 'filename' (str).

    Notes:
        - Side effects: Filesystem write and status updates.
        - Errors are reported as TaskError and logged.

    Performance Considerations:
        - CSV writing operations may involve significant I/O overhead for large datasets (>1000 rows).
        - Rate limiting: File write operations are throttled; consider batch processing for high-volume data exports.
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
            raise TaskError("Missing 'data_dir' parameter in configuration for StoreMetadataAsCsv task.")
        if not filename:
            raise TaskError("Missing 'filename' parameter in configuration for StoreMetadataAsCsv task.")

        
        self.data_dir = Path(windows_long_path(data_dir_str))
        self.filename_template = filename

        # Optional: look up extraction fields configuration for aliasing
        tasks_config = self.config_manager.get_all().get("tasks", {})
        extract_task_definition = tasks_config.get("extract_document_data", {})
        extraction_step_params = extract_task_definition.get("params", {})
        
        if "fields" in extraction_step_params:
            self.extraction_fields_config = extraction_step_params["fields"]
        
        if not self.extraction_fields_config:
            self.logger.warning("Could not find 'extraction.fields' configuration. CSV headers might not use aliases.")

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
            StatusManager(self.config_manager).update_status(unique_id, "Task Started: store_metadata_csv", step="Task Started: store_metadata_csv")
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
            raise TaskError("StoreMetadataAsCsv task missing required field: 'data_dir'")
        if not self.filename_template:
            raise TaskError("StoreMetadataAsCsv task missing required field: 'filename_template'")
        # No need to validate extraction_fields_config as it's optional for basic functionality

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Write extracted metadata to a CSV file in the configured directory.

        Supports context['data'] as a single dict or a list of dicts. Values are
        cleaned for CSV output (strings have newlines removed; lists are joined).

        Args:
            context (Dict[str, Any]): Pipeline context containing:
                - id (str): Unique identifier for status logging.
                - data (dict or list[dict]): Extracted metadata to persist.

        Returns:
            Dict[str, Any]: The unmodified context.

        Raises:
            TaskError: If extracted data is missing/unsupported or writing fails.

        Notes:
            - Side effects: Filesystem write and status updates via StatusManager.

        Performance Considerations:
            - This method performs synchronous CSV file I/O, which may block for large datasets (>1000 records).
            - Rate limiting: File operations are throttled to prevent system overload; use streaming for high-volume exports.
        """
        extracted_data = context.get("data")  # Use "data" as per PRD
        unique_id = context.get("id")

        if not extracted_data:
            self.logger.warning(f"No extracted data found for {unique_id}. Skipping CSV storage.")
            return context

        self.validate_required_fields(context)  # Call validation here

        # Ensure filename_template and data_dir are not None after validation
        if self.filename_template is None:
            raise TaskError("Filename template is not set after validation.")
        if self.data_dir is None:
            raise TaskError("Data directory is not set after validation.")

        # Determine data_list and data_for_filename_formatting
        data_list: List[Dict[str, Any]] = []
        data_for_filename_formatting: Dict[str, Any] = {}

        if isinstance(extracted_data, dict):
            data_list = [extracted_data]
            data_for_filename_formatting = extracted_data
        elif isinstance(extracted_data, list) and all(isinstance(item, dict) for item in extracted_data):
            data_list = extracted_data
            if extracted_data:
                data_for_filename_formatting = extracted_data[0]  # Use first item for filename
            else:
                self.logger.warning(f"Extracted data is an empty list for {unique_id}. Skipping CSV storage.")
                return context
        else:
            raise TaskError("Extracted data is not in a supported format (dict or list of dicts) for CSV storage.")

        # Prepare processed_data and fieldnames
        processed_data = []
        # Determine all unique fieldnames from the processed data, prioritizing aliases
        unique_fieldnames = set()
        for item in data_list:
            for key, value in item.items():
                alias = key
                if self.extraction_fields_config and key in self.extraction_fields_config:
                    alias = self.extraction_fields_config[key].get("alias", key)
                unique_fieldnames.add(alias)
        
        fieldnames = list(unique_fieldnames)
        fieldnames.sort()  # Sort for consistent CSV output

        for item in data_list:
            processed_item = {}
            for key, value in item.items():
                # Get alias if available, otherwise use original key
                alias = key
                if self.extraction_fields_config and key in self.extraction_fields_config:
                    alias = self.extraction_fields_config[key].get("alias", key)
                
                # Clean string values (replace newlines with spaces)
                if isinstance(value, str):
                    processed_item[alias] = value.replace('\\n', ' ').replace('\\r', '')
                # Join list values with commas
                elif isinstance(value, list):
                    processed_item[alias] = ", ".join(map(str, value))
                else:
                    processed_item[alias] = value
            processed_data.append(processed_item)

        # Update status: preparing to write CSV
        try:
            from modules.status_manager import StatusManager
            StatusManager(self.config_manager).update_status(str(unique_id), "Preparing to write CSV", step="Preparing to write CSV")
        except Exception:
            pass

        # Generate filename from template and extracted data
        try:
            # Format the filename using data_for_filename_formatting. Ensure all values are strings for formatting.
            # Also, sanitize each part of the filename.
            formatted_filename_parts = {
                k: sanitize_filename(preprocess_filename_value(v)) if not isinstance(v, list) else sanitize_filename(",".join(map(preprocess_filename_value, v)))
                for k, v in data_for_filename_formatting.items()
            }
            base_filename = self.filename_template.format(**formatted_filename_parts)
        except KeyError as e:
            raise TaskError(f"Filename template '{self.filename_template}' contains missing key from extracted data: {e}")
        except Exception as e:
            raise TaskError(f"Failed to format filename using template '{self.filename_template}': {e}")

        # Ensure .csv extension
        if not base_filename.lower().endswith(".csv"):
            base_filename += ".csv"
        
        # Generate unique filepath
        output_path = generate_unique_filepath(self.data_dir, os.path.splitext(base_filename)[0], ".csv")

        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                # Update status: writing rows
                try:
                    from modules.status_manager import StatusManager
                    StatusManager(self.config_manager).update_status(str(unique_id), "Writing CSV rows", step="Writing CSV rows")
                except Exception:
                    pass
                writer.writerows(processed_data)
            self.logger.info(f"Metadata for {unique_id} stored as CSV at {output_path}")
            # Unified timestamp convention (success)
            try:
                from modules.status_manager import StatusManager
                StatusManager(self.config_manager).update_status(str(unique_id), "Task Completed: store_metadata_csv", step="Task Completed: store_metadata_csv")
            except Exception:
                pass
        except Exception as e:
            # Unified timestamp convention (failure)
            try:
                from modules.status_manager import StatusManager
                StatusManager(self.config_manager).update_status(str(unique_id), "Task Failed: store_metadata_csv", step="Task Failed: store_metadata_csv", error=str(e))
            except Exception:
                pass
            raise TaskError(f"Failed to store metadata as CSV for {unique_id}: {e}")

        return context
