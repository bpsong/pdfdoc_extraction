"""Resume orchestration for documents paused by app-level human review."""

from __future__ import annotations

from typing import Any

from modules.config_protocol import ConfigProvider as ConfigManager
from modules.db.connection import managed_connect, json_loads
from modules.db.repositories import DocumentRepository, ExtractionRepository, TaskRunRepository, ManualSplitRepository, ReviewRepository
from modules.services.workflow_state_service import WorkflowStateService
from modules.services.pipeline_definition_service import PipelineDefinitionService
from modules.services.split_result_service import restore_single_document_context
from modules.workflow_loader import WorkflowLoader


class ResumeManager:
    """Resume a reviewed document from the task after the paused gate."""

    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager

    def resume_document(self, document_id: str, user: str | None = None) -> bool:
        """Resume a document after review without duplicating downstream work."""
        with managed_connect(self.config_manager) as conn:
            documents = DocumentRepository(conn)
            extractions = ExtractionRepository(conn)
            task_runs = TaskRunRepository(conn)
            document = documents.get(document_id)
            if document is None:
                return False
            if document.get("status") != "review_completed":
                return False
            if not document.get("pipeline_version_id"):
                return False
            try:
                executable = PipelineDefinitionService(
                    conn, self.config_manager
                ).load_for_document(document_id)
            except Exception:
                return False
            pipeline = executable.pipeline
            workflow_state = WorkflowStateService(
                conn,
                pipeline=pipeline,
                pipeline_version_id=(
                    executable.version_id if executable is not None else None
                ),
            )

            next_task = workflow_state.next_task_after_current(document_id)
            next_index = next_task[0] if next_task is not None else len(pipeline)
            manual_decision = None
            latest_review = ReviewRepository(conn).find_latest_for_document(document_id)
            if latest_review and latest_review.get("review_kind") == "manual_split" and latest_review.get("status") == "completed":
                manual_decision = ManualSplitRepository(conn).get_for_review(latest_review["id"])
                if not manual_decision or not manual_decision.get("action") or manual_decision.get("phase") == "applied":
                    return False
                next_index = int(manual_decision["task_index"])
                if pipeline[next_index] != manual_decision["task_key"]:
                    return False
            if manual_decision:
                from modules.services.manual_split_service import is_completed_cleanup
                if any(
                    int(run.get("task_index") or 0) > next_index and not is_completed_cleanup(run)
                    for run in task_runs.list_by_document(document_id)
                ):
                    return False
            elif workflow_state.has_completed_at_or_after(document_id, next_index):
                return False

            if not documents.claim_review_resume(document_id):
                return False
            context = self._build_resume_context(
                document, extractions, task_runs,
                retry_manual_decision_id=manual_decision["id"] if manual_decision else None,
            )
            if manual_decision:
                checkpoint = json_loads(manual_decision.get("checkpoint_json"), {})
                context["data"] = checkpoint.get("data", {})
                context["metadata"].update(checkpoint.get("metadata", {}))
                context["manual_split_decision_id"] = manual_decision["id"]
            context["resumed_by"] = user
            context["start_task_index"] = next_index
            if executable is not None:
                context["pipeline_version_id"] = executable.version_id
                context["pipeline_template_id"] = executable.template_id

        loader = WorkflowLoader(
            self.config_manager,
            definition=executable.definition,
            pipeline_version_id=executable.version_id,
            pipeline_template_id=executable.template_id,
        )
        flow_func = loader.load_workflow(start_task_index=next_index)
        if flow_func is None:
            if manual_decision:
                with managed_connect(self.config_manager) as conn:
                    WorkflowStateService(conn).transition_document(document_id, "review_completed", reason="manual_split_launch_unavailable")
            return False
        try:
            final_context = flow_func(context)
        except Exception:
            with managed_connect(self.config_manager) as conn:
                WorkflowStateService(conn).transition_document(document_id, "failed", reason="review_resume_failed")
            raise
        if isinstance(final_context, dict) and final_context.get("pipeline_state") == "fan_out":
            from modules.workflow_manager import WorkflowManager
            WorkflowManager(self.config_manager)._trigger_child_workflows(final_context)
        return True

    def _build_resume_context(
        self,
        document: dict[str, Any],
        extractions: ExtractionRepository,
        task_runs: TaskRunRepository,
        *,
        retry_manual_decision_id: str | None = None,
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
        restore_single_document_context(context, document)
        continued_failures = []
        for task_run in task_runs.list_by_document(document_id):
            if task_run.get("status") != "failed":
                continue
            if (task_run.get("module_name") == "standard_step.split.manual_split"
                    and task_run.get("class_name") == "ManualSplitTask"):
                decision = ManualSplitRepository(task_runs.conn).get_for_task(
                    document_id, str(task_run.get("pipeline_version_id")), task_run["task_key"],
                )
                if decision and decision.get("action") and (
                    decision["phase"] == "applied" or decision["id"] == retry_manual_decision_id
                ):
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
