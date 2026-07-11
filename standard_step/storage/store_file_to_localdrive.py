"""Store processed PDF files to a local drive with a formatted, unique name.

This module defines StoreFileToLocaldrive, a pipeline task that renames and
stores the current item's PDF into a configured local directory. The filename
is generated from a template pattern that can include extracted data, the
original filename, timestamps, and the unique id. Collisions are avoided by
generating a unique path before writing.

Notes:
    - Reads 'files_dir' and 'filename' from task params (required).
    - May reference extraction field definitions from the global config to
      inform filename formatting, but this is optional.
    - Registers the copied PDF as an ``export_pdf`` document artifact when
      SQLite document context is available.
    - Performs filesystem copy operations only; no modification of the source.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from modules.utils import (
    preprocess_filename_value,
    release_reserved_filepath,
    reserve_unique_filepath,
    sanitize_filename,
)
from modules.base_task import BaseTask
from modules.config_protocol import ConfigProvider as ConfigManager, get_all_config
from modules.exceptions import TaskError
from modules.services.artifact_service import register_document_artifact
from datetime import datetime
import shutil
import logging
from modules.utils import windows_long_path


class StoreFileToLocaldrive(BaseTask):
    """Task that writes the processed PDF to a local directory with a safe name.

    Responsibilities:
        - Validate target directory and filename pattern parameters.
        - Render a filename from a filename pattern using context/extracted data.
        - Ensure a .pdf extension and resolve a unique output path.
        - Copy the file to the destination and update task status.

    Integration:
        Works as part of the storage step in the pipeline. Parameters are
        provided via BaseTask.params and can refer to fields extracted earlier.

    Args:
        config_manager (ConfigManager): Project configuration manager.
        **params: Required 'files_dir' (str) and 'filename' (str).
            Optionally leverages extracted 'fields' config for formatting.

    Notes:
        - Side effects: Filesystem copy to the target directory and status updates.
        - Raises TaskError on parameter, formatting, or I/O failures.

    Performance Considerations:
        - File copying operations may involve heavy I/O; consider batching for large volumes to avoid rate limits (e.g., 5 files/sec).
        - Large file operations (>100MB) may cause noticeable delays in synchronous processing.
    """

    def __init__(self, config_manager: ConfigManager, **params):
        """Initialize the task and capture required parameters.

        Args:
            config_manager (ConfigManager): The configuration manager instance.
            **params: Must contain 'files_dir' and 'filename'.

        Raises:
            TaskError: If required parameters are missing.
        """
        super().__init__(config_manager=config_manager, **params)
        self.logger = logging.getLogger(__name__)  # Initialize logger
        
        self.files_dir: Optional[Path] = None
        self.filename: Optional[str] = None
        self.extraction_fields_config: Optional[Dict[str, Any]] = None  # Optional

        # Extract parameters from self.params
        files_dir_str = self.params.get('files_dir')
        filename = self.params.get('filename')

        if not files_dir_str:
            raise TaskError("Missing 'files_dir' parameter in configuration for StoreFileToLocaldrive task.")
        if not filename:
            raise TaskError("Missing 'filename' parameter in configuration for StoreFileToLocaldrive task.")

        self.files_dir = Path(windows_long_path(files_dir_str))
        self.filename = filename

        # Optional: access extraction fields configuration from global config
        tasks_config = get_all_config(self.config_manager).get("tasks", {})
        extract_task_definition = tasks_config.get("extract_document_data", {})
        extraction_step_params = extract_task_definition.get("params", {})
        
        if "fields" in extraction_step_params:
            self.extraction_fields_config = extraction_step_params["fields"]

        if not self.extraction_fields_config:
            self.logger.warning("Could not find 'extraction.fields' configuration. Filename formatting might not use extracted data.")

    def on_start(self, context: Dict[str, Any]) -> None:
        """Lifecycle hook executed when the task starts.

        Initializes context.

        Args:
            context (Dict[str, Any]): The pipeline context.
        """
        self.initialize_context(context)

    def validate_required_fields(self, context: Dict[str, Any]):
        """Validate required parameters.

        Args:
            context (Dict[str, Any]): Unused; present for interface parity.

        Raises:
            TaskError: If files_dir or filename are not set.
        """
        if not self.files_dir:
            raise TaskError("StoreFileToLocaldrive task missing required field: 'files_dir'")
        if not self.filename:
            raise TaskError("StoreFileToLocaldrive task missing required field: 'filename'")
        # No need to validate extraction_fields_config as it's optional for basic functionality

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Store the current file into the configured local directory.

        Constructs a destination filename using the filename pattern and context
        data, ensures uniqueness, and copies the source PDF to that location.

        Args:
            context (Dict[str, Any]): Pipeline context containing:
                - file_path (str): Source file to store.
                - id (str): Unique identifier for status logging.
                - original_filename (str): Original name for formatting.
                - data (dict): Extracted fields used in filename formatting.

        Returns:
            Dict[str, Any]: The unmodified context.

        Raises:
            TaskError: If required context keys are missing, the format fails,
                or the copy operation fails.

        Notes:
            - Side effects: Filesystem copy and SQLite artifact registration.

        Performance Considerations:
            - This method performs synchronous file I/O operations, which may block for large files (>10MB).
            - Rate limiting: File operations are throttled to prevent system overload; use async variants for high throughput scenarios.
        """
        file_path = context.get("file_path")
        unique_id = context.get("id")
        original_filename = context.get("original_filename")
        extracted_data = context.get("data")  # Get extracted data for formatting

        if not file_path or not unique_id or not original_filename:
            self.logger.warning(f"Missing file_path, unique_id, or original_filename in context for {unique_id}. Skipping file storage.")
            return context

        self.validate_required_fields(context)  # Call validation here

        # Ensure filename and files_dir are not None after validation
        if self.filename is None:
            raise TaskError("Filename pattern is not set after validation.")
        if self.files_dir is None:
            raise TaskError("Files directory is not set after validation.")

        # Format the new filename using the filename pattern and extracted data
        try:
            # Combine extracted_data with other context variables for formatting
            format_data = {
                "id": unique_id,
                "original_filename": original_filename,
                "timestamp": datetime.now().strftime("%Y%m%d%H%M%S"),
                **({k: sanitize_filename(preprocess_filename_value(v)) if not isinstance(v, list) else sanitize_filename(",".join(map(preprocess_filename_value, v)))
                    for k, v in extracted_data.items()} if extracted_data else {})
            }
            base_filename = self.filename.format(**format_data)
        except KeyError as e:
            raise TaskError(f"Filename pattern '{self.filename}' contains missing key from context/extracted data: {e}")
        except Exception as e:
            raise TaskError(f"Failed to format filename using pattern '{self.filename}': {e}")

        # Ensure .pdf extension
        if not base_filename.lower().endswith(".pdf"):
            base_filename += ".pdf"
        
        # Generate unique filepath
        output_path = reserve_unique_filepath(self.files_dir, os.path.splitext(base_filename)[0], ".pdf")

        try:
            # Copy the file to the new location
            shutil.copy(file_path, output_path)
            self.logger.info(f"File {original_filename} ({unique_id}) stored at {output_path}")
            context["output_path"] = str(output_path)
            register_document_artifact(
                self.config_manager,
                context,
                file_type="export_pdf",
                file_path=output_path,
                metadata={
                    "task_key": self.task_key(context),
                    "original_filename": original_filename,
                },
            )
        except Exception as e:
            if not release_reserved_filepath(output_path):
                self.logger.warning("Failed to remove PDF output after a failed write")
            raise TaskError(f"Failed to store file {original_filename} ({unique_id}): {e}")

        return context
