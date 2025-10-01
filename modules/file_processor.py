"""File processing utilities for handling web uploads and triggering workflows.

This module is responsible for:
  - Receiving and storing web uploads into a configured upload directory.
  - Optionally validating PDF headers using a minimal magic-bytes check.
  - Generating a UUID and renaming/moving files into the processing directory.
  - Creating a UUID-based filename and creating initial status records via StatusManager.
  - Triggering downstream processing through WorkflowManager.

It does not change files' content; it orchestrates placement, metadata/status creation,
and workflow initiation based on configuration.
"""

import os
import uuid
from typing import Optional
import logging
from pathlib import Path

from modules.config_manager import ConfigManager
from modules.workflow_manager import WorkflowManager
from modules.status_manager import StatusManager
from modules.utils import windows_long_path, is_pdf_header

logger = logging.getLogger(__name__)

class FileProcessor:
    """Coordinates moving uploaded files into processing and starting workflows.

    Dependencies:
      - ConfigManager: Provides configuration values such as directories and flags.
      - retry_operation_func: Callable for retrying operations (injected, not used here).
      - WorkflowManager: Triggers downstream workflows for a given file.

    Directories:
      - web.upload_dir: Temporary location where web uploads are first written.
      - watch_folder.processing_dir: Destination directory where files are renamed to
        their UUID and processed by the workflow.

    High-level flow:
       1) Accept upload and write it into web.upload_dir.
       2) Optionally validate that the file is a PDF by checking the '%PDF-' header.
       3) Generate a UUID, rename the file to <uuid>.pdf, and move it to processing_dir.
       4) Create an initial status entry for tracking.
       5) Trigger the workflow via WorkflowManager.

    Performance Considerations:
       - File processing involves synchronous I/O operations that may block for large files (>10MB).
       - Rate limiting: File operations are throttled to prevent system overload; consider batching for high-volume scenarios.
    """

    def __init__(self, config_manager: ConfigManager, retry_operation_func, workflow_manager: WorkflowManager) -> None:
        """Initialize the file processor and ensure required directories exist.

        Args:
            config_manager (ConfigManager): Provides configuration, including:
                - watch_folder.processing_dir (str): Processing directory path.
                - web.upload_dir (str): Upload directory path.
                - watch_folder.validate_pdf_header (bool): If True, validate PDF magic header.
            retry_operation_func (Callable): A callable used for retrying operations if needed.
            workflow_manager (WorkflowManager): Manager used to trigger workflows.

        Notes:
            - Initializes a StatusManager instance for status lifecycle handling.
            - Ensures the processing directory exists (creates it if missing).
            - Ensures the web upload directory exists when configured.
            - Emits informational logs when directories are created.

        Raises:
            ValueError: If the processing directory is unspecified or empty in configuration.
        """
        self.config_manager = config_manager
        self.retry_operation_func = retry_operation_func
        self.workflow_manager = workflow_manager
        self.processing_folder_path = str(self.config_manager.get('watch_folder.processing_dir', 'processing_folder'))
        self.status_manager = StatusManager(self.config_manager)  # Initialize StatusManager
        if not self.processing_folder_path:
            raise ValueError("Processing folder directory not specified in config.yaml or is empty.")
        
        # Ensure the processing folder exists
        if not os.path.exists(self.processing_folder_path):
            os.makedirs(self.processing_folder_path)
            logger.info(f"Created processing folder: {self.processing_folder_path}")

        # Ensure web upload folder exists (validated by ConfigManager, but ensure here at runtime)
        web_upload_dir = self.config_manager.get('web.upload_dir')
        if web_upload_dir and not os.path.exists(web_upload_dir):
            os.makedirs(web_upload_dir, exist_ok=True)
            logger.info(f"Created web upload folder: {web_upload_dir}")

    def _validate_pdf_header(self, file_path: str) -> bool:
        """Delegate to the centralized is_pdf_header utility.

        Uses the shared helper which supports retries for partially-written files.
        """
        # Use 5 bytes ('%PDF-'), 3 attempts and 0.2s delay to match watch folder behavior.
        return is_pdf_header(file_path, read_size=5, attempts=3, delay=0.2, logger=logger)

    def process_web_upload(self, upload_file, source: str = "web") -> str:
        """Handle a web-uploaded file and initiate processing.

        Steps:
          1) Save the uploaded file to web.upload_dir using its original filename.
          2) Optionally validate PDF header depending on configuration.
          3) Generate a UUID and rename to '<uuid>.pdf'.
          4) Move the file into the processing directory.
          5) Create status and trigger the workflow via process_file.

        Args:
            upload_file: A Starlette/FastAPI UploadFile instance or a file-like/bytes-like object.
            source (str): Origin label of the upload (default: "web").

        Returns:
            str: The generated unique_id (UUID string) for the uploaded file.

        Raises:
            ValueError: If web.upload_dir is not configured or if PDF validation fails.
            Exception: Propagates any I/O related errors encountered during save/move operations.

        Performance Considerations:
            - This method performs synchronous file I/O, which may block for large files (>10MB).
            - Rate limiting: Operations are throttled to prevent system overload; use async variants for high throughput.
        """
        # Resolve directories
        upload_dir = str(self.config_manager.get('web.upload_dir'))
        if not upload_dir:
            raise ValueError("web.upload_dir is not configured")
        processing_dir = self.processing_folder_path

        # Persist initial upload
        original_name = getattr(upload_file, "filename", None) or "uploaded.pdf"
        original_name = os.path.basename(original_name)
        temp_path = os.path.join(upload_dir, original_name)

        # Save file contents
        try:
            # FastAPI UploadFile exposes .file (SpooledTemporaryFile). Support both UploadFile and file-like.
            if hasattr(upload_file, "file"):
                with open(temp_path, "wb") as out_f:
                    out_f.write(upload_file.file.read())
            else:
                # Assume a bytes-like or file-like object
                data = upload_file.read() if hasattr(upload_file, "read") else bytes(upload_file)
                with open(temp_path, "wb") as out_f:
                    out_f.write(data)
        except Exception as e:
            logger.error(f"Failed to save uploaded file to {temp_path}: {e}")
            raise

        # Validate PDF header if enabled (use shared utility)
        if bool(self.config_manager.get('watch_folder.validate_pdf_header', True)):
            # Use centralized helper to allow retries for partially-written files.
            # Parameters: read_size=5 ('%PDF-'), attempts=3, delay=0.2s between attempts.
            if not is_pdf_header(temp_path, read_size=5, attempts=3, delay=0.2, logger=logger):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
                raise ValueError("Invalid PDF header")

        # Generate UUID and rename to UUID.pdf
        unique_id = str(uuid.uuid4())
        final_name = f"{unique_id}.pdf"
        final_processing_path = os.path.join(processing_dir, final_name)

        try:
            # Move into processing folder with new name
            os.replace(temp_path, final_processing_path)
        except Exception as e:
            logger.error(f"Failed to move file into processing folder: {e}")
            # Cleanup temp file if still exists
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            raise

        # Delegate to process_file for status + workflow trigger
        self.process_file(
            filepath=final_processing_path,
            unique_id=unique_id,
            source=source,
            original_filename=original_name
        )
        return unique_id

    def process_file(self,
                     filepath: str,
                     unique_id: str,
                     source: str,
                     original_filename: Optional[str] = None) -> bool:
        """Process a file already in the processing directory with a UUID name.

        Intended for files that have been placed/renamed to their UUID form (e.g., '<uuid>.pdf').

        Args:
            filepath (str): Full path to the file in the processing directory.
            unique_id (str): UUID identifier associated with the file.
            source (str): Origin label of the file (e.g., 'web', 'watch_folder').
            original_filename (Optional[str]): Original filename, if available.

        Returns:
            bool: True if status creation and workflow trigger were initiated successfully.

        Notes:
            - Creates an initial status entry via StatusManager.
            - Triggers the configured workflow via WorkflowManager.
            - Emits info/debug logs to trace processing.
        """
        # if caller passed in the real original name, use it; otherwise fall back
        filename = original_filename or os.path.basename(filepath)
        destination_path = filepath  # File is already renamed and placed correctly

        logger.info(f"Processing file {filepath} with UUID {unique_id}")

        # Create initial status record
        logger.debug(f"FileProcessor.process_file - unique_id: {unique_id}, filepath: {filepath}")
        self.status_manager.create_status(
            unique_id=unique_id,
            original_filename=filename,
            source=source,
            file_path=destination_path
        )
        logger.info(f"Created pending status record for {filename} with ID {unique_id}")
        
        # Trigger workflow for this file
        self.workflow_manager.trigger_workflow_for_file(
            file_path=destination_path,
            unique_id=unique_id,
            original_filename=filename,
            source=source
        )
        
        return True