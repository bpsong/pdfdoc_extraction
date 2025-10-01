"""Polling-based watch service for incoming PDF files with optional header validation.

This module implements a simple polling monitor that:
- Scans a configured watch directory for PDF files.
- Optionally validates a minimal PDF header signature with retries.
- Renames detected PDFs to UUID-based filenames and moves them into a processing directory.
- Invokes a provided callback to process each file.
- Integrates with ShutdownManager to ensure graceful shutdown by registering a stop routine.

Responsibilities:
- Process existing PDFs present at startup, then continuously poll for new PDFs.
- Retry file operations (rename/move and processing) with logging, and perform optional cleanup on final failure.
- Maintain a set of processed file paths to avoid duplicate handling.
"""

from modules.shutdown_manager import ShutdownManager
import os
import time
import uuid
import shutil
import logging
from threading import Event
from modules.utils import windows_long_path, is_pdf_header

logger = logging.getLogger(__name__)

class WatchFolderMonitor:
    """Monitor a directory for PDF files and hand them off for processing.

    This monitor performs a two-phase flow:
    1) On start, process existing PDF files in the watch directory.
    2) Then enter a polling loop to detect and process newly arrived PDFs until stopped.

    Dependencies:
        - config_manager: Provides configuration values:
            - "watch_folder.dir": Path to the directory to watch for PDFs.
            - "watch_folder.processing_dir": Path where files are moved/renamed to UUID filenames.
        - process_file_callback: Callable invoked to process each file.
        - retry_file_operation_func: External retry facility (not used directly; retained for compatibility).

    Settings:
        - polling_interval (int): Seconds between polls for new files (default 5).
        - retry_attempts (int): Number of attempts for PDF header validation (default 3).
        - retry_delay (float): Delay in seconds between validation attempts (default 0.2).

    High-level flow:
        - Existing files: For each PDF found, move to processing dir with UUID name, then invoke callback.
        - New files: Poll directory; for unseen PDF, optionally validate header, move with UUID, invoke callback.

    """

    def __init__(self, config_manager, process_file_callback, retry_file_operation_func):
        """Initialize the monitor and derive configured directories.

        Args:
            config_manager: Configuration manager used to fetch paths
                "watch_folder.dir" and "watch_folder.processing_dir".
            process_file_callback: Callable to process a file after it is moved.
                Signature: process_file_callback(new_filepath, uuid_str, source_label, original_filename=...).
            retry_file_operation_func: Dependency placeholder for external retry function
                retained for compatibility; internal retries are handled by _retry_file_operation.

        Notes:
            - Initializes internal state: stop_event, processed_files set, polling interval,
              retry attempts and delay, and resolved directory paths.
        """
        self.logger = logging.getLogger(__name__)
        self.config_manager = config_manager
        self.process_file_callback = process_file_callback
        self.retry_file_operation_func = retry_file_operation_func
        self.stop_event = Event()
        self.processed_files = set()
        self.polling_interval = 5  # seconds
        self.watch_folder_path = self.config_manager.get("watch_folder.dir")
        self.processing_folder_path = self.config_manager.get("watch_folder.processing_dir")
        self.retry_attempts = 3
        self.retry_delay = 0.2

    def _retry_file_operation(self, operation, *args, description="file operation", attempts=None, delay=None, cleanup_func=None, **kwargs):
        """Execute a file-related operation with basic retry logic.

        Args:
            operation: Callable to execute (e.g., shutil.move or a processing callback).
            *args: Positional arguments forwarded to the operation.
            description (str): Human-readable description for logging context.
            attempts (int | None): Number of attempts; defaults to 3 if None.
            delay (float | None): Delay in seconds between attempts; defaults to 0.2 if None.
            cleanup_func (Callable | None): Optional callable executed on the final failure
                (after all attempts). Used to perform cleanup (e.g., revert state).
            **kwargs: Keyword arguments forwarded to the operation.

        Returns:
            bool: True if the operation succeeded within the attempts; False otherwise.

        Notes:
            - Logs each attempt at debug level before running and warns on failures.
            - If all attempts fail, cleanup_func is called once (if provided) before returning False.
        """
        attempts = attempts or 3
        delay = delay or 0.2
        for attempt in range(1, attempts + 1):
            try:
                self.logger.debug(f"Attempt {attempt} for {description} with args {args} and kwargs {kwargs}")
                operation(*args, **kwargs)
                return True
            except Exception as e:
                self.logger.warning(f"Attempt {attempt} failed for {description}: {e}")
                if attempt == attempts:
                    if cleanup_func:
                        cleanup_func()
                    return False
                time.sleep(delay)

    def _is_valid_pdf_header(self, filepath):
        """Check for a minimal PDF header signature with retry by delegating to shared util.

        Args:
            filepath (str): Path to the candidate PDF file.

        Returns:
            bool: True if the file begins with b'%PDF-'; False after exhausting retries.

        Notes:
            - Delegates to modules.utils.is_pdf_header which implements retries and logging.
            - Uses configured retry_attempts and retry_delay and passes this instance's logger.
        """
        # Use centralized helper with parameters consistent with previous behavior:
        # read_size=5 ('%PDF-'), attempts=self.retry_attempts, delay=self.retry_delay
        return is_pdf_header(filepath, read_size=5, attempts=self.retry_attempts, delay=self.retry_delay, logger=self.logger)

    def _process_existing_files(self):
        """Process PDFs already present in the watch directory at startup.

        Behavior:
            - Iterate PDFs in the watch directory.
            - For unprocessed files, generate a UUID, move/rename to processing directory,
              then invoke the processing callback.
            - Mark paths as processed to avoid duplicate handling.

        Side Effects:
            - Moves files from watch directory to processing directory.
            - Logs successes and failures; updates processed_files set.

        Returns:
            None
        """
        logger.info(f"Processing existing files in {self.watch_folder_path}...")
        for filename in os.listdir(self.watch_folder_path):
            if filename.lower().endswith('.pdf'):
                filepath = os.path.join(self.watch_folder_path, filename)
                if filepath not in self.processed_files:
                    file_uuid = uuid.uuid4()
                    new_filename = f"{file_uuid}.pdf"
                    new_filepath = os.path.join(self.processing_folder_path, new_filename)

                    if self._retry_file_operation(shutil.move, windows_long_path(filepath), windows_long_path(new_filepath), description=f"rename file {filepath} to {new_filepath}"):
                        logger.info(f"Successfully renamed {filepath} to {new_filepath}")
                        if self._retry_file_operation(
                            self.process_file_callback,
                            new_filepath,
                            str(file_uuid),
                            "watch_folder",
                            original_filename=filename,
                            description=f"process existing file {new_filepath}"):
                            self.processed_files.add(new_filepath)
                        else:
                            logger.error(f"Failed to process existing file {new_filepath} after retries.")
                    else:
                        logger.error(f"Failed to rename {filepath} to {new_filepath} after retries. Skipping processing.")
                        self.processed_files.add(filepath)
        logger.info("Finished processing existing files.")

    def _monitor_new_files(self):
        """Continuously poll the watch directory for new PDFs and process them.

        Behavior:
            - While stop_event is not set, list the watch directory and handle unseen PDFs.
            - For each new file, validate the header, then move/rename to processing
              directory with a UUID filename and invoke the processing callback.
            - Record processed paths to avoid duplicates.

        Notes:
            - Uses polling with interval defined by polling_interval.
            - Catches and logs unexpected exceptions to keep the loop alive.

        Returns:
            None
        """
        logger.info(f"Starting watch folder monitoring for new PDF files in {self.watch_folder_path}...")
        while not self.stop_event.is_set():
            try:
                for filename in os.listdir(self.watch_folder_path):
                    if filename.lower().endswith('.pdf'):
                        filepath = os.path.join(self.watch_folder_path, filename)
                        if filepath not in self.processed_files:
                            logger.info(f"Found new PDF: {filepath}")
                            if not self._is_valid_pdf_header(filepath):
                                logger.warning(f"Skipping {filepath} due to invalid PDF header.")
                                self.processed_files.add(filepath)
                                continue

                            file_uuid = uuid.uuid4()
                            new_filename = f"{file_uuid}.pdf"
                            new_filepath = os.path.join(self.processing_folder_path, new_filename)

                            if self._retry_file_operation(shutil.move, windows_long_path(filepath), windows_long_path(new_filepath), description=f"rename file {filepath} to {new_filepath}"):
                                logger.info(f"Successfully renamed {filepath} to {new_filepath}")
                                if self._retry_file_operation(
                                    self.process_file_callback,
                                    new_filepath,
                                    str(file_uuid),
                                    "watch_folder",
                                    original_filename=filename,
                                    description=f"process new file {new_filepath}"):
                                    self.processed_files.add(new_filepath)
                                else:
                                    logger.error(f"Failed to process new file {new_filepath} after retries.")
                            else:
                                logger.error(f"Failed to rename {filepath} to {new_filepath} after retries. Skipping processing.")
                                self.processed_files.add(filepath)
                time.sleep(self.polling_interval) # Move sleep inside try block
            except KeyboardInterrupt:
                logger.info("Watch folder monitoring interrupted by user.")
                # Removed direct call to ShutdownManager.shutdown() to allow main.py to handle shutdown
                break  # Exit the loop gracefully
            except Exception as e:
                logger.error(f"Error during watch folder monitoring: {e}")

    def start(self):
        """Start monitoring: register stop with ShutdownManager, process existing, then poll.

        Registers:
            - stop(): Registered with ShutdownManager for graceful shutdown.

        Flow:
            - Process existing files first to clear backlog.
            - Enter the monitoring loop for new files.

        Returns:
            None
        """
        shutdown_manager = ShutdownManager()
        shutdown_manager.register_cleanup_task(self.stop)
        self._process_existing_files()
        self._monitor_new_files()

    def stop(self):
        """Signal the monitoring loop to stop.

        Sets:
            - stop_event: Once set, the polling loop will exit after the current iteration.

        Returns:
            None
        """
        self.stop_event.set()
