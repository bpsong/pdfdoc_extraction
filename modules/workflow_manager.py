"""Workflow coordination utilities for launching Prefect flows for individual files.

This module is responsible for:
- Loading the workflow function via WorkflowLoader.
- Triggering the Prefect flow asynchronously for the file.
- Updating SQLite document state on trigger failures when document context exists.

Architecture Reference:
    For detailed system architecture, component interactions, and workflow orchestration
    patterns, refer to docs/design_architecture.md.
"""
import logging
from typing import Dict, Any

from prefect import flow
from modules.workflow_loader import WorkflowLoader
from modules.config_manager import ConfigManager
from modules.db.connection import connect, json_loads
from modules.db.repositories import DocumentRepository

class WorkflowManager:
    """Orchestrates workflow triggering for file processing.

    This manager coordinates between collaborators to start a workflow for
    a specific file:
    - ConfigManager: Provides configuration used by workflow loading and status handling.
    - WorkflowLoader: Loads the Prefect flow function to execute.

    Responsibilities include initializing collaborators, creating the initial
    SQLite context, loading the workflow, triggering it with the initial context,
    and marking SQLite-backed documents failed on load/trigger failures.

    Architecture Reference:
        For detailed system architecture, component interactions, and workflow orchestration
        patterns, refer to docs/design_architecture.md.
    """
    def __init__(self, config_manager: ConfigManager):
        """Initialize WorkflowManager with required collaborators.

        Args:
            config_manager: Configuration provider used to construct the
                WorkflowLoader and to supply settings.
        """
        self.config_manager = config_manager
        self.workflow_loader = WorkflowLoader(config_manager)
        self.logger = logging.getLogger(__name__)
        
    def trigger_workflow_for_file(
        self,
        file_path: str,
        unique_id: str,
        original_filename: str,
        source: str,
        batch_id: str | None = None,
        document_id: str | None = None,
    ):
        """Trigger a new Prefect flow instance for the given file.

        Loads the workflow, assembles the initial context, and starts the flow.
        On workflow load failure or any exception during trigger, marks the
        SQLite document failed when document context exists and returns False.

        Args:
            file_path: Absolute or project-relative path to the input file.
            unique_id: Unique identifier for this processing instance.
            original_filename: Original filename provided for logging/status.
            source: Source label of the file (e.g., watch folder, API).

        Returns:
            bool: True if the workflow trigger was successfully initiated,
            otherwise False.

        Notes:
            - The flow is invoked directly. Prefect execution controls task-run
              state through ``WorkflowStateService``.

        Architecture Reference:
            For detailed system architecture, component interactions, and workflow
            orchestration patterns, refer to docs/design_architecture.md.
        """
        try:
            # Load the workflow
            flow_func = self.workflow_loader.load_workflow()
            if not flow_func:
                self.logger.error("Failed to load workflow")
                self._mark_document_failed(document_id, "Workflow Load Failed")
                return False
                
            # Create context with file-specific parameters
            initial_context = {
                "id": unique_id,
                "file_path": file_path,
                "original_filename": original_filename,
                "source": source
            }
            if batch_id:
                initial_context["batch_id"] = batch_id
            if document_id:
                initial_context["document_id"] = document_id
            
            # Start the flow (Prefect executes synchronously; log before and after for clarity)
            self.logger.info(
                f"Workflow triggered for file: {original_filename} (ID: {unique_id}) from source: {source}"
            )
            final_context = flow_func(initial_context)
            if isinstance(final_context, dict) and final_context.get("pipeline_state") == "fan_out":
                self._trigger_child_workflows(final_context)
            self.logger.info(
                f"Workflow completed for file: {original_filename} (ID: {unique_id}) from source: {source}"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to trigger workflow for {original_filename}: {e}")
            self._mark_document_failed(document_id, f"Workflow Trigger Failed: {e}")
            return False

    def _mark_document_failed(self, document_id: str | None, reason: str) -> None:
        """Mark a SQLite document failed after workflow launch failures."""
        if not document_id:
            return
        try:
            with connect(self.config_manager) as conn:
                documents = DocumentRepository(conn)
                if documents.get(str(document_id)):
                    documents.update_status(str(document_id), "failed")
        except Exception:
            self.logger.debug("Failed to persist workflow launch failure: %s", reason, exc_info=True)

    def _trigger_child_workflows(self, parent_context: Dict[str, Any]) -> None:
        """Start child document workflows after a split fan-out."""
        child_ids = [str(child_id) for child_id in parent_context.get("split_children") or []]
        if not child_ids:
            return

        start_task_index = int(parent_context.get("fan_out_start_task_index") or 0)
        with connect(self.config_manager) as conn:
            documents = DocumentRepository(conn)
            child_documents = [documents.get(child_id) for child_id in child_ids]

        for child in child_documents:
            if child is None:
                continue
            child_context = self._build_child_context(child, parent_context, start_task_index)
            flow_func = self.workflow_loader.load_workflow(start_task_index=start_task_index)
            if not flow_func:
                self.logger.error("Failed to load child workflow for %s", child["id"])
                continue
            self.logger.info(
                "Starting child workflow for document %s from task index %s",
                child["id"],
                start_task_index,
            )
            flow_func(child_context)

    @staticmethod
    def _build_child_context(
        child: Dict[str, Any],
        parent_context: Dict[str, Any],
        start_task_index: int,
    ) -> Dict[str, Any]:
        """Build a workflow context for one split child document."""
        metadata = json_loads(child.get("metadata_json"), {})
        child_id = str(child["id"])
        context: Dict[str, Any] = {
            "id": child_id,
            "batch_id": child["batch_id"],
            "document_id": child_id,
            "parent_document_id": child.get("parent_document_id"),
            "root_document_id": metadata.get("root_document_id") or child.get("parent_document_id"),
            "file_path": child["file_path"],
            "original_filename": child.get("original_filename"),
            "source": "split",
            "source_original_filename": metadata.get("source_original_filename") or parent_context.get("original_filename"),
            "source_file_path": metadata.get("source_file_path") or parent_context.get("file_path"),
            "split_category": child.get("split_category"),
            "split_confidence": child.get("split_confidence"),
            "split_pages": metadata.get("split_pages") or [],
            "page_start": child.get("page_start"),
            "page_end": child.get("page_end"),
            "start_task_index": start_task_index,
            "metadata": {
                "split": metadata,
                "parent_document_id": child.get("parent_document_id"),
                "root_document_id": metadata.get("root_document_id") or child.get("parent_document_id"),
            },
        }
        if "inherited_context" in metadata:
            context["metadata"]["inherited_context"] = metadata["inherited_context"]
        return context
