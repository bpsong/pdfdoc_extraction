"""Housekeeping step that removes processed files from the processing area.

This module defines CleanupTask, a terminal housekeeping step in the pipeline
that deletes the per-item working copy (usually a UUID-named PDF) from the
processing directory once upstream steps are complete.

Notes:
    - Reads 'processing_dir' from task params (defaults to 'processing').
    - Performs filesystem deletes and logs outcomes.
    - Does not modify or remove status tracking files.
"""

import logging
from typing import Any, Dict
from pathlib import Path

from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError


class CleanupTask(BaseTask):
    """Task to delete a processed file from the processing directory.

    Responsibilities:
        - Validate required parameters.
        - Remove the processed per-item file if present.
        - Log success or warnings if the file is missing.

    Integration:
        Runs as a final housekeeping step and does not return an updated
        context. Uses BaseTask for initialization/logging.

    Args:
        config_manager (ConfigManager): Project configuration manager.
        **params: Optional overrides including 'processing_dir'.

    Notes:
        - Side effects: Filesystem delete (Path.unlink). No status updates.
    """

    def __init__(self, config_manager: ConfigManager, **params):
        """Initialize CleanupTask and resolve working directory.

        Args:
            config_manager (ConfigManager): The configuration manager instance.
            **params: Optional keys, notably 'processing_dir'. Defaults to
                'processing' if not provided.
        """
        super().__init__(config_manager=config_manager, **params)
        self.logger = logging.getLogger(__name__)

        self.processing_dir: Path = Path(self.params.get('processing_dir', 'processing'))

    def on_start(self, context: Dict[str, Any]) -> None:
        """Lifecycle hook invoked when the task starts.

        Initializes context and logs the file about to be cleaned up.

        Args:
            context (Dict[str, Any]): Pipeline context. Uses 'file_path' for
                logging if present.
        """
        self.initialize_context(context)
        self.logger.info(f"Starting CleanupTask for file {context.get('file_path')}")

    def validate_required_fields(self, context: Dict[str, Any]):
        """Validate that required fields/params are present.

        Args:
            context (Dict[str, Any]): Unused; present for interface parity.

        Raises:
            TaskError: If 'processing_dir' is not set.
        """
        if not self.processing_dir:
            raise TaskError("CleanupTask missing required field: 'processing_dir'")

    def run(self, context: Dict[str, Any]) -> None:
        """Delete the processed file referenced by the context if it exists.

        Args:
            context (Dict[str, Any]): Pipeline context with:
                - file_path (str or Path-like): Path to the processed file.
                - id (str): Unique identifier (unused here).

        Raises:
            TaskError: If filesystem deletion fails.

        Notes:
            - Side effects: Filesystem unlink of the processed file.
            - This terminal step intentionally does not return a context.
        """
        self.validate_required_fields(context)

        file_path_str = context.get('file_path')
        unique_id = context.get('id')

        if not file_path_str:
            self.logger.warning(f"Missing file_path in context for cleanup. Skipping.")
            return

        file_path = Path(str(file_path_str))  # Ensure it's a string for Path

        if not file_path.exists():
            self.logger.warning(f"File {file_path} not found for cleanup. Skipping.")
            return

        # Remove the UUID-named PDF document from the processing directory
        try:
            file_path.unlink()
            self.logger.info(f"Removed processed file: {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to remove processed file {file_path}: {e}")
            raise TaskError(f"Failed to cleanup processed file: {e}")

        # This task does not delete the status text file

        # As this is the last step, do not return context