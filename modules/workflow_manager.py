"""Workflow coordination utilities for launching Prefect flows for individual files.

This module is responsible for:
- Creating the initial processing status for a file.
- Loading the workflow function via WorkflowLoader.
- Triggering the Prefect flow asynchronously for the file.
- Updating status records on success or failure of the trigger.

Architecture Reference:
    For detailed system architecture, component interactions, and workflow orchestration
    patterns, refer to docs/design_architecture.md.
"""
import logging
import warnings
from typing import Dict, Any

warnings.filterwarnings(
    "ignore",
    message=r"Config key `.*` is set in model_config but will be ignored because no .+ source is configured.*",
    module="pydantic_settings.main",
    category=UserWarning,
)

from prefect import flow
from modules.workflow_loader import WorkflowLoader
from modules.config_manager import ConfigManager
from modules.status_manager import StatusManager

class WorkflowManager:
    """Orchestrates workflow triggering for file processing.

    This manager coordinates between collaborators to start a workflow for
    a specific file, without awaiting its execution:
    - ConfigManager: Provides configuration used by workflow loading and status handling.
    - WorkflowLoader: Loads the Prefect flow function to execute.
    - StatusManager: Creates and updates per-file processing status.

    Responsibilities include initializing collaborators, creating the initial
    status, loading the workflow, triggering it with the initial context, and
    updating statuses upon load failures or trigger exceptions.

    Architecture Reference:
        For detailed system architecture, component interactions, and workflow orchestration
        patterns, refer to docs/design_architecture.md.
    """
    def __init__(self, config_manager: ConfigManager):
        """Initialize WorkflowManager with required collaborators.

        Args:
            config_manager: Configuration provider used to construct the
                WorkflowLoader and StatusManager and to supply settings.
        """
        self.config_manager = config_manager
        self.workflow_loader = WorkflowLoader(config_manager)
        self.logger = logging.getLogger(__name__)
        self.status_manager = StatusManager(self.config_manager)
        
    def trigger_workflow_for_file(self, file_path: str, unique_id: str, original_filename: str, source: str):
        """Trigger a new Prefect flow instance for the given file.

        Creates the initial status, loads the workflow, assembles the initial
        context, updates status to "Workflow Triggered", and starts the flow
        asynchronously. On workflow load failure or any exception during
        trigger, updates the status accordingly and returns False.

        Args:
            file_path: Absolute or project-relative path to the input file.
            unique_id: Unique identifier for this processing instance.
            original_filename: Original filename provided for logging/status.
            source: Source label of the file (e.g., watch folder, API).

        Returns:
            bool: True if the workflow trigger was successfully initiated,
            otherwise False.

        Notes:
            - The flow is started asynchronously (no await) by calling the
              loaded Prefect flow function directly.
            - Status transitions:
                * Initially created via StatusManager.create_status(...)
                * Updated to "Workflow Triggered" before starting the flow
                * On load failure: "Workflow Load Failed"
                * On exception during trigger: "Workflow Trigger Failed"

        Architecture Reference:
            For detailed system architecture, component interactions, and workflow
            orchestration patterns, refer to docs/design_architecture.md.
        """
        try:
            # Create initial status for the file
            self.status_manager.create_status(unique_id, original_filename, source, file_path)
            
            # Load the workflow
            flow_func = self.workflow_loader.load_workflow()
            if not flow_func:
                self.logger.error("Failed to load workflow")
                self.status_manager.update_status(unique_id, "Workflow Load Failed", error="Failed to load workflow")
                return False
                
            # Create context with file-specific parameters
            initial_context = {
                "id": unique_id,
                "file_path": file_path,
                "original_filename": original_filename,
                "source": source
            }
            
            self.status_manager.update_status(unique_id, "Workflow Triggered")
            
            # Start the flow asynchronously
            flow_func(initial_context)
            
            self.logger.info(f"Workflow triggered for file: {original_filename} (ID: {unique_id}) from source: {source}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to trigger workflow for {original_filename}: {e}")
            self.status_manager.update_status(unique_id, "Workflow Trigger Failed", error=str(e))
            return False
