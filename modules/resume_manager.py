"""Resume orchestration for documents paused by app-level human review."""

from __future__ import annotations

from typing import Any

from modules.config_protocol import ConfigProvider as ConfigManager
from modules.db.connection import connect, json_loads
from modules.db.repositories import DocumentRepository, ExtractionRepository, TaskRunRepository
from modules.services.workflow_state_service import WorkflowStateService
from modules.workflow_loader import WorkflowLoader


class ResumeManager:
    """Resume a reviewed document from the task after the paused gate."""

    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager
        self.pipeline = config_manager.get("pipeline", []) or []

    def resume_document(self, document_id: str, user: str | None = None) -> bool:
        """Resume a document after review without duplicating downstream work."""
        with connect(self.config_manager) as conn:
            documents = DocumentRepository(conn)
            extractions = ExtractionRepository(conn)
            task_runs = TaskRunRepository(conn)
            workflow_state = WorkflowStateService(conn, pipeline=self.pipeline)
            document = documents.get(document_id)
            if document is None:
                return False
            if document.get("status") != "review_completed":
                return False

            next_task = workflow_state.next_task_after_current(document_id)
            next_index = next_task[0] if next_task is not None else len(self.pipeline)
            if workflow_state.has_completed_at_or_after(document_id, next_index):
                return False

            if not documents.claim_review_resume(document_id):
                return False
            context = self._build_resume_context(document, extractions, task_runs)
            context["resumed_by"] = user
            context["start_task_index"] = next_index

        flow_func = WorkflowLoader(self.config_manager).load_workflow(start_task_index=next_index)
        if flow_func is None:
            return False
        flow_func(context)
        return True

    def _build_resume_context(
        self,
        document: dict[str, Any],
        extractions: ExtractionRepository,
        task_runs: TaskRunRepository,
    ) -> dict[str, Any]:
        """Build workflow context from document record and corrected final values."""
        document_id = str(document["id"])
        latest_extraction = extractions.get_latest_result(document_id) or {}
        data: dict[str, Any] = {}
        for field in extractions.get_fields(document_id):
            data[str(field["field_key"])] = json_loads(field.get("final_value_json"))
        context = {
            "id": document_id,
            "batch_id": document["batch_id"],
            "document_id": document_id,
            "file_path": document["file_path"],
            "original_filename": document.get("original_filename"),
            "source": "resume",
            "data": data,
            "metadata": {
                "latest_extraction_result_id": latest_extraction.get("id"),
                "latest_extraction_metadata": json_loads(latest_extraction.get("metadata_json"), {}),
            },
        }
        continued_failures = []
        for task_run in task_runs.list_by_document(document_id):
            if task_run.get("status") != "failed":
                continue
            output = json_loads(task_run.get("output_json"), {})
            continued_failures.append(
                {
                    "error": task_run.get("error"),
                    "error_step": output.get("error_step") or task_run.get("task_key"),
                    "fatal_failure": output.get("fatal_failure"),
                }
            )
        if continued_failures:
            context["continued_failures"] = continued_failures
        return context
