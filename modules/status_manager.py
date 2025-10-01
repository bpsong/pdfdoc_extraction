"""
Manages per-file processing status as JSON files in the configured processing directory.

This module exposes a singleton manager that provides thread-safe create, update,
and get operations for JSON status files stored in the processing directory
configured via ConfigManager. Paths are resolved to absolute locations, file I/O
is serialized using locks, and operations are logged. A cleanup routine removes
status files whose final status is Completed or Error.

Thread-safety:
- Singleton instantiation is guarded by a class-level lock.
- File I/O operations are protected by an instance-level lock.

Exceptions:
- I/O and parsing errors are logged rather than raised to avoid interrupting
  processing workflows.

Architecture Reference:
    For detailed system architecture, component interactions, and data persistence
    patterns used in status management, refer to docs/design_architecture.md.
"""
import json
import os
import threading
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import shutil
from modules.config_manager import ConfigManager
from pathlib import Path

class StatusManager:
    """
    Singleton manager for JSON status files in the processing directory.

    This class enforces singleton semantics using a class-level lock. It depends
    on [`modules.config_manager.ConfigManager`](modules/config_manager.py) to
    provide the processing directory path, which is resolved to an absolute path.
    An instance-level lock serializes all file I/O operations. The class logs
    status path construction, status file creation/updates, and cleanup results,
    as well as warnings and errors for missing files and I/O issues.

    Notes:
        - Status files are named "<unique_id>.txt" and stored directly under the
          processing directory.
        - Logging uses a dedicated "StatusManager" logger.

    Architecture Reference:
        For detailed system architecture, component interactions, and data persistence
        patterns used in status management, refer to docs/design_architecture.md.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config: ConfigManager):
        """
        Create or return the singleton instance.

        Args:
            config (ConfigManager): Configuration provider used to resolve the
                processing directory path (watch_folder.processing_dir).

        Returns:
            StatusManager: The singleton instance. On first call, the instance is
            initialized using the provided config; subsequent calls return the same
            instance.

        Notes:
            - Thread-safe via a class-level lock guarding initial creation.
            - The config argument is only used during first instantiation.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(StatusManager, cls).__new__(cls)
                    cls._instance._init(config)
        return cls._instance

    def _init(self, config: ConfigManager):
        """
        Internal initializer; called exactly once for the singleton.

        Args:
            config (ConfigManager): Configuration provider used to obtain and
                resolve the processing directory path.

        Side Effects:
            - Creates an instance-level lock for serializing file I/O.
            - Configures the "StatusManager" logger with a stream handler if absent.
            - Resolves the processing directory to an absolute path and creates it
              if missing.

        Notes:
            - If the processing directory is not present in configuration
              ('watch_folder.processing_dir'), a default "processing_folder_default"
              under the current working directory is used, and an error is logged.
        """
        self._status_lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        
        # Use the passed ConfigManager instance
        self._config = config
        processing_dir_from_config = self._config.get('watch_folder.processing_dir')
        if not processing_dir_from_config:
            self.logger.error("Processing folder path not found in configuration. Status files will not be managed correctly.")
            # Fallback to a default or raise an error, depending on desired behavior
            self._processing_folder_path = os.path.join(os.getcwd(), "processing_folder_default")
        else:
            self._processing_folder_path = os.path.abspath(processing_dir_from_config) # Make it an absolute path

        os.makedirs(self._processing_folder_path, exist_ok=True)
        self.logger.info(f"Status files will be stored in: {self._processing_folder_path}")
        self.logger.debug(f"StatusManager initialized with processing_folder_path: {self._processing_folder_path} (Type: {type(self._processing_folder_path)})")

    def _get_status_file_path(self, unique_id: str) -> str:
        """
        Build the absolute path to the status file for a given unique ID.

        Args:
            unique_id (str): The unique identifier associated with a processing item.

        Returns:
            str: Absolute path to the JSON status file with ".txt" extension located
            directly under the processing directory.

        Notes:
            - Filename format is "<unique_id>.txt".
            - Emits a debug log with the constructed path.
        """
        status_file_path = os.path.join(self._processing_folder_path, f"{unique_id}.txt")
        self.logger.debug(f"Constructed status file path: {status_file_path} for unique_id: {unique_id}")
        return status_file_path

    def create_status(self, unique_id: str, original_filename: str, source: str, file_path: str) -> None:
        """
        Create an initial status record for a file.

        Args:
            unique_id (str): Unique identifier for the processing item.
            original_filename (str): The original input filename.
            source (str): Logical source or origin of the file (e.g., watch-folder name).
            file_path (str): Full path to the file being processed.

        Returns:
            None

        Side Effects:
            - Creates a JSON status file at "<processing_dir>/<unique_id>.txt".

        JSON Schema:
            {
              "id": str,
              "original_filename": str,
              "source": str,
              "file": str,  # basename of file_path
              "status": "Pending",
              "timestamps": {
                "created": str,  # ISO 8601 UTC, 'Z' suffix
                "pending": str   # ISO 8601 UTC, 'Z' suffix
              },
              "error": None,
              "details": {}
            }

        Timestamp Format:
            - All timestamps are ISO 8601 UTC with 'Z' suffix, e.g. "2024-01-01T12:00:00Z".

        Notes:
            - Thread-safe via an instance-level lock during file creation.
            - Errors are logged; exceptions are not raised.

        Architecture Reference:
            For detailed system architecture, component interactions, and data persistence
            patterns used in status management, refer to docs/design_architecture.md.
        """
        status_file = self._get_status_file_path(unique_id)
        current_time = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        initial_status = {
            "id": unique_id,
            "original_filename": original_filename,
            "source": source,
            "file": os.path.basename(file_path), # Store original file basename for reference
            "status": "Pending",
            "timestamps": {
                "created": current_time,
                "pending": current_time
            },
            "error": None,
            "details": {}
        }
        try:
            with self._status_lock:
                with open(status_file, "w", encoding="utf-8") as f:
                    json.dump(initial_status, f, indent=4)
            self.logger.debug(f"Created status file: {status_file}")
        except Exception as e:
            self.logger.error(f"Failed to create status file {status_file}: {e}")

    def update_status(self, unique_id: str, status: str, step: Optional[str] = None,
                       error: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Update the status record for a unique ID.

        Args:
            unique_id (str): The unique identifier for the processing item.
            status (str): New status string (e.g., "Pending", "Processing", "Completed", "Error").
            step (Optional[str]): Optional processing step name; if provided, the
                timestamp is recorded under this key instead of the status value.
            error (Optional[str]): Error description, if any, to set on the record.
            details (Optional[Dict[str, Any]]): Additional data to shallow-merge into
                the "details" field.

        Returns:
            None

        Behavior:
            - Loads and updates an existing status file if present.
            - If missing, creates a minimal placeholder status and updates it:
              {
                "id": unique_id,
                "original_filename": "unknown",
                "file": "unknown",
                "status": "unknown",
                "timestamps": {},
                "error": None,
                "details": {}
              }
            - The timestamp key is "step" when provided; otherwise, the "status" value.
            - Timestamps use ISO 8601 UTC format with 'Z' suffix.
            - "details" are shallow-merged into existing details.

        Notes:
            - Thread-safe via an instance-level lock during read/modify/write.
            - Logs a warning when creating a placeholder, debug on success, and
              errors on failures. Exceptions are not raised.
        """
        status_file = self._get_status_file_path(unique_id)
        try:
            with self._status_lock:
                if os.path.exists(status_file):
                    with open(status_file, "r", encoding="utf-8") as f:
                        current_status = json.load(f)
                else:
                    # If no status file exists, create a new one (this should ideally not happen if create_status is called first)
                    self.logger.warning(f"Status file not found for {unique_id}. Creating a new one with unknown status.")
                    current_status = {
                        "id": unique_id,
                        "original_filename": "unknown",
                        "file": "unknown",
                        "status": "unknown",
                        "timestamps": {},
                        "error": None,
                        "details": {}
                    }
     
                current_status["status"] = status
                timestamp_key = step if step else status
                current_status["timestamps"][timestamp_key] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                if error:
                    current_status["error"] = error
                else:
                    current_status["error"] = None
    
                if details:
                    # Merge details dictionary
                    current_status["details"].update(details)
    
                with open(status_file, "w", encoding="utf-8") as f:
                    json.dump(current_status, f, indent=4)
            self.logger.debug(f"Updated status file: {status_file} with status: {status}")
        except Exception as e:
            self.logger.error(f"Failed to update status file {status_file}: {e}")

    def get_status(self, unique_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the status record for a unique ID.

        Args:
            unique_id (str): The unique identifier for the processing item.

        Returns:
            Optional[Dict[str, Any]]: Parsed JSON dictionary if the status file exists
            and is readable; otherwise, None.

        Notes:
            - Thread-safe via an instance-level lock during read.
            - Logs a warning if the file is missing and an error if reading fails.
            - Exceptions are not raised; None is returned on failure.
        """
        status_file = self._get_status_file_path(unique_id)
        try:
            with self._status_lock:
                if not os.path.exists(status_file):
                    self.logger.warning(f"Status file not found: {status_file}")
                    return None
                with open(status_file, "r", encoding="utf-8") as f:
                    status_data = json.load(f)
                return status_data
        except Exception as e:
            self.logger.error(f"Failed to read status file {status_file}: {e}")
            return None

    def cleanup_status_files(self):
        """
        Remove status files whose final state is Completed or Error.

        Purpose:
            - Scans the processing directory for ".txt" files and deletes those
              whose "status" field equals "Completed" or "Error".

        Returns:
            None

        Notes:
            - Iterates files without raising exceptions; errors are logged.
            - Emits an info log with the total number of files removed.
        """
        removed_count = 0
        try:
            with self._status_lock:
                for entry in os.listdir(self._processing_folder_path):
                    entry_path = os.path.join(self._processing_folder_path, entry)
                    if os.path.isfile(entry_path) and entry.endswith(".txt"):
                        try:
                            with open(entry_path, "r", encoding="utf-8") as f:
                                status_data = json.load(f)
                            if status_data.get("status") in ("Completed", "Error"):
                                os.remove(entry_path)
                                removed_count += 1
                        except Exception as e:
                            self.logger.error(f"Failed to cleanup status file {entry_path}: {e}")
        except Exception as e:
            self.logger.error(f"Failed to cleanup status files: {e}")
        self.logger.info(f"Cleanup complete. Removed {removed_count} status files.")