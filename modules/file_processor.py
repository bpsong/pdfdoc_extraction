"""Bridge an already-ingested SQLite processing job to WorkflowManager.

Primary uploads and watch-folder claims create assigned batch/document/job state
in their ingestion services. FileProcessor requires those identities before
triggering synchronous workflow execution. Its legacy process_web_upload helper
is not used by the retired HTTP upload endpoint and cannot create unassigned
workflow state."""

import os
import uuid
from typing import Any, Optional, Protocol
import logging

from modules.config_protocol import ConfigProvider as ConfigManager
from modules.utils import is_pdf_header

logger = logging.getLogger(__name__)


class WorkflowTrigger(Protocol):
    """Trigger a workflow for an ingested file."""

    def trigger_workflow_for_file(
        self,
        *,
        file_path: str,
        unique_id: str,
        original_filename: str,
        source: str,
        batch_id: str | None = None,
        document_id: str | None = None,
    ) -> Any:
        """Start processing for a file and its workflow context."""

class FileProcessor:
    """Trigger workflows for files with existing assigned SQLite identities.

    Construction prepares configured processing/upload directories. Primary ingestion
    belongs to UploadReceiver and ingestion services. The injected retry callable is
    retained for compatibility and is not used here. This class provides no file-I/O
    rate limiter."""

    def __init__(
        self,
        config_manager: ConfigManager,
        retry_operation_func: Any,
        workflow_manager: WorkflowTrigger,
    ) -> None:
        """Initialize the file processor and ensure required directories exist.

        Args:
            config_manager (ConfigManager): Provides configuration, including:
                - watch_folder.processing_dir (str): Processing directory path.
                - web.upload_dir (str): Upload directory path.
                - watch_folder.validate_pdf_header (bool): If True, validate PDF magic header.
            retry_operation_func (Callable): A callable used for retrying operations if needed.
            workflow_manager (WorkflowManager): Manager used to trigger workflows.

        Notes:
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

    def _create_sqlite_ingestion_state(
        self,
        *,
        filepath: str,
        unique_id: str,
        source: str,
        original_filename: str,
    ) -> tuple[str | None, str | None]:
        """Reject unassigned ingestion instead of creating legacy state."""
        raise ValueError(
            "An exact published pipeline assignment is required before processing "
            f"'{original_filename}'. Create the batch through the assigned upload "
            "or watch-folder ingestion flow."
        )

    def _validate_pdf_header(self, file_path: str) -> bool:
        """Delegate to the centralized is_pdf_header utility.

        Uses the shared helper which supports retries for partially-written files.
        """
        # Use 5 bytes ('%PDF-'), 3 attempts and 0.2s delay to match watch folder behavior.
        return is_pdf_header(file_path, read_size=5, attempts=3, delay=0.2, logger=logger)

    def process_web_upload(self, upload_file, source: str = "web") -> str:
        """Run the legacy upload helper, which cannot assign a pipeline.

        Saves the supplied upload, optionally checks its PDF header, moves it to a UUID
        working path, then calls process_file without assigned batch/document IDs. That
        unassigned call raises ValueError; the moved file can remain on disk. Production
        HTTP uploads use UploadReceiver and assigned batch ingestion instead.

        Args:
            upload_file: UploadFile, file-like object, or bytes-like content.
            source: Compatibility origin label.

        Raises:
            ValueError: Invalid PDF or missing exact pipeline assignment.
            OSError: Saving or moving the file fails."""
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
                except OSError as exc:
                    logger.warning("Failed to remove invalid PDF upload: %s", type(exc).__name__)
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
            except OSError as exc:
                logger.warning("Failed to remove upload after move failure: %s", type(exc).__name__)
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
                     original_filename: Optional[str] = None,
                     *,
                     batch_id: Optional[str] = None,
                     document_id: Optional[str] = None,
                     create_sqlite_state: bool = True) -> bool:
        """Execute a file's assigned workflow synchronously.

        Args:
            filepath: Path to an already-placed working PDF.
            unique_id: Existing workflow identity.
            source: Intake origin label.
            original_filename: Original name, falling back to the working basename.
            batch_id: Required existing SQLite batch identity.
            document_id: Required existing SQLite document identity.
            create_sqlite_state: Legacy flag; missing IDs are rejected rather than created.

        Returns:
            Whether the workflow trigger returned a value other than False. A completed
            invocation can still contain recorded task failure or a review pause.

        Raises:
            ValueError: Existing assigned batch/document identities are absent."""
        # if caller passed in the real original name, use it; otherwise fall back
        filename = original_filename or os.path.basename(filepath)
        destination_path = filepath  # File is already renamed and placed correctly

        logger.info(f"Processing file {filepath} with UUID {unique_id}")

        if create_sqlite_state and not (batch_id and document_id):
            batch_id, document_id = self._create_sqlite_ingestion_state(
                filepath=destination_path,
                unique_id=unique_id,
                source=source,
                original_filename=filename,
            )

        if not batch_id or not document_id:
            raise ValueError(
                "Processing requires SQLite batch and document records with an "
                "exact published pipeline assignment."
            )
        
        # Trigger workflow for this file. Some tests and third-party callers still
        # inject a pre-refactor WorkflowManager-shaped object, so keep that
        # compatibility while passing SQLite ids to the real manager.
        workflow_kwargs = {
            "file_path": destination_path,
            "unique_id": unique_id,
            "original_filename": filename,
            "source": source,
        }
        if batch_id:
            workflow_kwargs["batch_id"] = batch_id
        if document_id:
            workflow_kwargs["document_id"] = document_id
        try:
            trigger_result = self.workflow_manager.trigger_workflow_for_file(**workflow_kwargs)
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            workflow_kwargs.pop("batch_id", None)
            workflow_kwargs.pop("document_id", None)
            trigger_result = self.workflow_manager.trigger_workflow_for_file(**workflow_kwargs)
        
        return trigger_result is not False
