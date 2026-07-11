"""Archive original PDFs into a designated archive directory.

This module defines the ArchivePdfTask, a pipeline task responsible for
copying the original input PDF into a configured archive directory with a
sanitized and uniqueness-safe filename. It participates in the PDF processing
pipeline after input ingestion and before/after extraction depending on the
workflow configuration.

Notes:
    - Reads configuration via ConfigManager for the 'archive_dir' setting.
    - Registers the archived copy as a ``source_archive`` document artifact
      when SQLite document context is available.
    - Performs filesystem copy operations and may create a new unique filename.
    - No behavioral changes should be introduced by documentation updates.
"""

import os
import shutil
import logging
from pathlib import Path
from modules.base_task import BaseTask
from modules.config_protocol import ConfigProvider as ConfigManager
from modules.exceptions import TaskError
from modules.services.artifact_service import register_document_artifact
from modules.utils import (
    release_reserved_filepath,
    reserve_unique_filepath,
    retry_io,
    sanitize_filename,
    windows_long_path,
)


class ArchivePdfTask(BaseTask):
    """Task that archives the original PDF to a configured directory.

    Responsibilities:
        - Validate that an archive directory is provided and exists.
        - Copy the original file to the archive directory using a sanitized,
          uniqueness-safe filename.
        - Register the archived copy in SQLite when document context exists.

    Integration:
        This class is a standard step in the pipeline and uses BaseTask
        facilities for context handling and error registration.

    Args:
        config_manager (ConfigManager): Project configuration manager.
        **params: Optional parameters overriding configuration, including
            'archive_dir' for destination directory.

    Notes:
        - Side effects include filesystem writes (copy) and SQLite artifact
          registration.
        - Errors are reported as TaskError and registered into the task context.
    """

    def __init__(self, config_manager: ConfigManager, **params):
        """Initialize the ArchivePdfTask.

        Resolves the target archive directory from params or configuration and
        prepares logging.

        Args:
            config_manager (ConfigManager): Configuration manager for the app.
            **params: Optional overrides. Supports 'archive_dir'.

        Raises:
            TaskError: Not raised here, but later in validation if archive_dir
                is missing or invalid.

        Notes:
            Converts paths to Windows long path format for robustness.
        """
        super().__init__(config_manager, **params)
        # Extract archive_dir from params or config manager
        archive_dir_param = params.get("archive_dir")
        if archive_dir_param:
            archive_dir = archive_dir_param
        else:
            # Fallback to config manager path for archive_dir
            archive_dir = config_manager.get("tasks.archive_original_file.params.archive_dir")
        if not archive_dir:
            archive_dir = ""
        # Convert to Windows long path format
        self.archive_dir = windows_long_path(archive_dir)
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate_required_fields(self, context: dict):
        """Validate that required configuration/paths are present and valid.

        Args:
            context (dict): The pipeline context dictionary.

        Raises:
            TaskError: If archive_dir is missing, does not exist,
                or is not a directory.
        """
        if not self.archive_dir:
            raise TaskError("Archive directory parameter 'archive_dir' is not set.")
        if not os.path.exists(self.archive_dir):
            raise TaskError(f"Archive directory does not exist: {self.archive_dir}")
        if not os.path.isdir(self.archive_dir):
            raise TaskError(f"Archive directory path is not a directory: {self.archive_dir}")
        self.logger.debug(f"Validated archive directory: {self.archive_dir}")

    def on_start(self, context: dict):
        """Lifecycle hook invoked when the task starts.

        This logs the start.

        Args:
            context (dict): The pipeline context dictionary.

        """
        self.logger.info(f"Starting ArchivePdfTask with archive_dir: {self.archive_dir}")

    @retry_io(max_attempts=3, delay=0.5)
    def _copy_file(self, src: str, dst: str):
        """Copy a file preserving metadata with retry on transient IO failures.

        Args:
            src (str): Source file path.
            dst (str): Destination file path.

        Notes:
            Uses shutil.copy2 to preserve metadata. Decorated with retry_io to
            mitigate transient filesystem errors.
        """
        shutil.copy2(src, dst)

    def run(self, context: dict) -> dict:
        """Execute the archive step for the provided context.

        Expects 'file_path' and 'original_filename' in the context. The file is
        copied to the archive directory with a sanitized, unique filename.
        The archived file is registered in SQLite when document context exists,
        and any error is recorded into the context via BaseTask.register_error.

        Args:
            context (dict): Pipeline context. Must contain:
                - file_path (str): Path to the source file to archive.
                - original_filename (str): Original filename used to derive the
                  archived filename.

        Returns:
            dict: The updated context. Adds/updates:
                - data.archive_status (str): Human-readable success message.

        Raises:
            TaskError: If required context keys are missing or validation fails.

        Notes:
            - Side effects: filesystem copy and SQLite artifact registration.
            - Paths are normalized to Windows long path format.
        """
        self.initialize_context(context)
        target_path: Path | None = None
        try:
            # Use 'file_path' key instead of 'processed_file_path'
            file_path = context.get("file_path")
            original_filename = context.get("original_filename")
            if not file_path:
                raise TaskError("Context missing required key: 'file_path'")
            if not original_filename:
                raise TaskError("Context missing required key: 'original_filename'")

            self.logger.debug(f"File path: {file_path}")
            self.logger.debug(f"Original filename: {original_filename}")

            # Sanitize original filename
            sanitized_filename = sanitize_filename(original_filename)
            base_name, ext = os.path.splitext(sanitized_filename)

            # Generate unique target filepath in archive_dir
            archive_dir_path = Path(self.archive_dir)
            target_path = reserve_unique_filepath(archive_dir_path, base_name, ext)

            # Convert paths to Windows long path format
            src_path = windows_long_path(file_path)
            dst_path = windows_long_path(str(target_path))

            self.logger.info(f"Copying file from '{src_path}' to '{dst_path}'")
            self._copy_file(src_path, dst_path)

            context.setdefault("data", {})
            context["data"]["archive_status"] = f"File archived successfully to {dst_path}"
            self.logger.info(f"File archived successfully to {dst_path}")
            context["archive_path"] = dst_path
            register_document_artifact(
                self.config_manager,
                context,
                file_type="source_archive",
                file_path=dst_path,
                metadata={
                    "task_key": self.task_key(context),
                    "original_filename": original_filename,
                },
            )

        except TaskError as e:
            self._remove_failed_reservation(target_path)
            self.logger.error(f"TaskError in ArchivePdfTask: {e}")
            self.register_error(context, e)
        except Exception as e:
            self._remove_failed_reservation(target_path)
            self.logger.error(f"Unexpected error in ArchivePdfTask: {e}", exc_info=True)
            self.register_error(context, TaskError(f"Unexpected error: {e}"))

        return context

    @staticmethod
    def _remove_failed_reservation(target_path: Path | None) -> None:
        """Remove an output reservation after a failed archive copy."""
        if target_path is not None and not release_reserved_filepath(target_path):
            logging.getLogger(__name__).warning("Failed to remove archive output after a failed write")
