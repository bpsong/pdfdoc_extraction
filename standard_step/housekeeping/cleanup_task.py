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
from modules.db.connection import connect
from modules.db.repositories import DocumentRepository
from modules.exceptions import TaskError


class CleanupTask(BaseTask):
    """Task to delete a processed file from the processing directory.

    Responsibilities:
        - Validate required parameters.
        - Remove the processed per-item file if present.
        - Log success or warnings if the file is missing.

    Integration:
        Runs as a final housekeeping step and returns the context unchanged.
        Uses BaseTask for initialization/logging.

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

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Delete transient processed files referenced by the context.

        Args:
            context (Dict[str, Any]): Pipeline context with:
                - file_path (str or Path-like): Path to the processed file.
                - cleanup_paths (list[str], optional): Preferred transient files
                  to delete.
                - id (str): Unique identifier (unused here).

        Raises:
            TaskError: If filesystem deletion fails.

        Notes:
            - Side effects: Filesystem unlink of transient processed files.
            - Registered SQLite document artifacts are preserved.
            - This terminal step returns the unchanged context.
        """
        self.validate_required_fields(context)

        cleanup_paths = context.get("cleanup_paths")
        if cleanup_paths:
            paths = [Path(str(path)) for path in cleanup_paths]
        else:
            file_path_str = context.get('file_path')
            if not file_path_str:
                self.logger.warning(f"Missing file_path in context for cleanup. Skipping.")
                return context
            paths = [Path(str(file_path_str))]

        for file_path in paths:
            self._cleanup_path(file_path, context)

        # This task does not delete the status text file

        return context

    def _cleanup_path(self, file_path: Path, context: Dict[str, Any]) -> None:
        """Delete one transient path unless it is a registered artifact."""
        if not file_path.exists():
            self.logger.warning(f"File {file_path} not found for cleanup. Skipping.")
            return

        if self._is_registered_document_artifact(file_path, context):
            self.logger.info(f"Preserving registered artifact during cleanup: {file_path}")
            return

        try:
            file_path.unlink()
            self.logger.info(f"Removed processed file: {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to remove processed file {file_path}: {e}")
            raise TaskError(f"Failed to cleanup processed file: {e}")

    def _is_registered_document_artifact(self, file_path: Path, context: Dict[str, Any]) -> bool:
        """Return True when the path is registered in SQLite document_files."""
        document_id = context.get("document_id")
        if not document_id:
            return False
        try:
            target = file_path.resolve()
            with connect(self.config_manager) as conn:
                documents = DocumentRepository(conn)
                for record in documents.list_files(str(document_id)):
                    if Path(str(record["file_path"])).resolve() == target:
                        return True
        except Exception as exc:
            self.logger.debug("Failed to inspect document_files during cleanup: %s", exc)
        return False
