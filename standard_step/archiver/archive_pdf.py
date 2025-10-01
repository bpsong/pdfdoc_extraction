"""Archive original PDFs into a designated archive directory.

This module defines the ArchivePdfTask, a pipeline task responsible for
copying the original input PDF into a configured archive directory with a
sanitized and uniqueness-safe filename. It participates in the PDF processing
pipeline after input ingestion and before/after extraction depending on the
workflow configuration.

Notes:
    - Reads configuration via ConfigManager for the 'archive_dir' setting.
    - Updates processing status via StatusManager on start/success/failure.
    - Performs filesystem copy operations and may create a new unique filename.
    - No behavioral changes should be introduced by documentation updates.
"""

import os
import shutil
import logging
from pathlib import Path
from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError
from modules.utils import windows_long_path, sanitize_filename, generate_unique_filepath, retry_io


class ArchivePdfTask(BaseTask):
    """Task that archives the original PDF to a configured directory.

    Responsibilities:
        - Validate that an archive directory is provided and exists.
        - Copy the original file to the archive directory using a sanitized,
          uniqueness-safe filename.
        - Record start/success/failure states via StatusManager.

    Integration:
        This class is a standard step in the pipeline and uses BaseTask
        facilities for context handling and error registration.

    Args:
        config_manager (ConfigManager): Project configuration manager.
        **params: Optional parameters overriding configuration, including
            'archive_dir' for destination directory.

    Notes:
        - Side effects include filesystem writes (copy) and status updates via
          StatusManager.
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

        This logs the start and updates StatusManager with a 'started' state.

        Args:
            context (dict): The pipeline context dictionary.

        Notes:
            Attempts to update StatusManager but intentionally does not fail
            the task if status updates cause exceptions.
        """
        self.logger.info(f"Starting ArchivePdfTask with archive_dir: {self.archive_dir}")
        # Unified timestamp convention
        try:
            unique_id = str(context.get("id", "unknown"))
            from modules.status_manager import StatusManager
            StatusManager(self.config_manager).update_status(unique_id, "started", step="Task Started: archive_pdf")
        except Exception:
            # Avoid failing start on status write issues
            pass

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
        StatusManager is updated on success/failure, and any error is recorded
        into the context via BaseTask.register_error.

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
            - Side effects: filesystem copy, status updates via StatusManager.
            - Paths are normalized to Windows long path format.
        """
        self.initialize_context(context)
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
            target_path = generate_unique_filepath(archive_dir_path, base_name, ext)

            # Convert paths to Windows long path format
            src_path = windows_long_path(file_path)
            dst_path = windows_long_path(str(target_path))

            self.logger.info(f"Copying file from '{src_path}' to '{dst_path}'")
            self._copy_file(src_path, dst_path)

            context.setdefault("data", {})
            context["data"]["archive_status"] = f"File archived successfully to {dst_path}"
            self.logger.info(f"File archived successfully to {dst_path}")
            # Unified timestamp convention (success)
            try:
                from modules.status_manager import StatusManager
                StatusManager(self.config_manager).update_status(str(context.get("id")), "success", step="Task Completed: archive_pdf")
            except Exception:
                pass

        except TaskError as e:
            self.logger.error(f"TaskError in ArchivePdfTask: {e}")
            # Unified timestamp convention (failure)
            try:
                from modules.status_manager import StatusManager
                StatusManager(self.config_manager).update_status(str(context.get("id")), "failed", step="Task Failed: archive_pdf", error=str(e))
            except Exception:
                pass
            self.register_error(context, e)
        except Exception as e:
            self.logger.error(f"Unexpected error in ArchivePdfTask: {e}", exc_info=True)
            # Unified timestamp convention (failure)
            try:
                from modules.status_manager import StatusManager
                StatusManager(self.config_manager).update_status(str(context.get("id")), "failed", step="Task Failed: archive_pdf", error=str(e))
            except Exception:
                pass
            self.register_error(context, TaskError(f"Unexpected error: {e}"))

        return context