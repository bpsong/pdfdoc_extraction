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
from modules.config_protocol import ConfigProvider as ConfigManager
from modules.db.connection import connect, json_loads
from modules.db.repositories import BatchRepository, DocumentRepository, TaskRunRepository
from modules.exceptions import TaskError
from modules.services.failure_service import _redact, _redact_text
from standard_step.extraction.llama_cloud_v2 import preflight_extract_v2_access

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

        if self._fail_children_when_extract_preflight_fails(parent_context, child_documents, start_task_index):
            return

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

    def _fail_children_when_extract_preflight_fails(
        self,
        parent_context: Dict[str, Any],
        child_documents: list[dict[str, Any] | None],
        start_task_index: int,
    ) -> bool:
        """Return True when child workflows were stopped by extract preflight failure."""
        task_key, task_config = self._task_at_index(start_task_index)
        if not task_key or not self._is_extract_task(task_key, task_config):
            return False
        raw_params = task_config.get("params")
        params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        try:
            preflight_extract_v2_access(
                api_key=str(params.get("api_key") or ""),
                configuration_id=params.get("configuration_id") if isinstance(params.get("configuration_id"), str) else None,
                project_id=params.get("project_id") if isinstance(params.get("project_id"), str) else None,
                organization_id=params.get("organization_id") if isinstance(params.get("organization_id"), str) else None,
            )
            return False
        except TaskError as exc:
            self._record_extract_preflight_failure(
                parent_context=parent_context,
                child_documents=[child for child in child_documents if child is not None],
                start_task_index=start_task_index,
                task_key=task_key,
                task_config=task_config,
                message=getattr(exc, "message", str(exc)),
                params=params,
            )
            return True

    def _record_extract_preflight_failure(
        self,
        *,
        parent_context: Dict[str, Any],
        child_documents: list[dict[str, Any]],
        start_task_index: int,
        task_key: str,
        task_config: dict[str, Any],
        message: str,
        params: dict[str, Any],
    ) -> None:
        """Persist one source-level failure when downstream extract config is invalid."""
        root_document_id = str(parent_context.get("document_id") or parent_context.get("id") or "")
        batch_id = str(parent_context.get("batch_id") or "")
        if not root_document_id or not batch_id:
            return
        module_name = str(task_config.get("module") or "")
        class_name = str(task_config.get("class") or "")
        configuration_id = params.get("configuration_id") if isinstance(params.get("configuration_id"), str) else None
        safe_message = _redact_text(message)
        affected_segments = [self._segment_failure_payload(child) for child in child_documents]
        fatal_failure = {
            "failure_type": "extract_preflight_failed",
            "message": safe_message,
            "provider": "llamacloud_extract_v2",
            "configuration_id": configuration_id,
            "affected_split_documents": len(child_documents),
            "segments": affected_segments,
            "operator_action": (
                "Correct the LlamaCloud Extract API key or configuration_id, "
                "then re-ingest the original source PDF."
            ),
        }
        output = {
            "error": safe_message,
            "error_step": task_key,
            "fatal_failure": _redact(fatal_failure),
            "document_id": root_document_id,
            "batch_id": batch_id,
            "affected_child_documents": [child.get("id") for child in child_documents],
        }
        with connect(self.config_manager) as conn:
            documents = DocumentRepository(conn)
            task_runs = TaskRunRepository(conn)
            root = documents.get(root_document_id)
            if root is None:
                return
            run = task_runs.create_started(
                batch_id=batch_id,
                document_id=root_document_id,
                task_key=task_key,
                task_index=start_task_index,
                module_name=module_name,
                class_name=class_name,
                input_data={
                    "preflight": True,
                    "configuration_id": configuration_id,
                    "affected_split_documents": len(child_documents),
                },
            )
            task_runs.mark_failed(run["id"], safe_message, output)
            self._merge_document_metadata(documents, root_document_id, fatal_failure, safe_message, task_key)
            documents.update_status(root_document_id, "failed")
            for child in child_documents:
                child_id = str(child.get("id"))
                documents.update_current_task(child_id, start_task_index, task_key)
                self._merge_document_metadata(documents, child_id, fatal_failure, safe_message, task_key)
                documents.update_status(child_id, "failed")
            BatchRepository(conn).recompute_counts(batch_id)

    @staticmethod
    def _merge_document_metadata(
        documents: DocumentRepository,
        document_id: str,
        fatal_failure: dict[str, Any],
        message: str,
        task_key: str,
    ) -> None:
        document = documents.get(document_id)
        if document is None:
            return
        metadata = json_loads(document.get("metadata_json"), {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["fatal_failure"] = _redact(fatal_failure)
        metadata["fatal_error"] = _redact_text(message)
        metadata["fatal_error_step"] = task_key
        documents.update_metadata(document_id, metadata)

    @staticmethod
    def _segment_failure_payload(child: dict[str, Any]) -> dict[str, Any]:
        metadata = json_loads(child.get("metadata_json"), {})
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "document_id": child.get("id"),
            "filename": child.get("original_filename"),
            "category": child.get("split_category"),
            "confidence": child.get("split_confidence"),
            "pages": metadata.get("split_pages") or [],
            "page_start": child.get("page_start"),
            "page_end": child.get("page_end"),
        }

    def _task_at_index(self, task_index: int) -> tuple[str | None, dict[str, Any]]:
        pipeline = self.config_manager.get("pipeline", [])
        if not isinstance(pipeline, list) or task_index < 0 or task_index >= len(pipeline):
            return None, {}
        task_key = str(pipeline[task_index])
        task_config = self.config_manager.get(f"tasks.{task_key}", {})
        return task_key, task_config if isinstance(task_config, dict) else {}

    @staticmethod
    def _is_extract_task(task_key: str, task_config: dict[str, Any]) -> bool:
        module_name = str(task_config.get("module") or "").lower()
        class_name = str(task_config.get("class") or "").lower()
        key = task_key.lower()
        return "extract" in key or ".extraction" in module_name or "extract" in class_name

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
