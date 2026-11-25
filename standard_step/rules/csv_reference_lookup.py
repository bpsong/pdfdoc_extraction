"""Read a CSV reference register and enrich the current document with text."""

from __future__ import annotations

import sqlite3
from typing import Any

from pydantic import ValidationError

from modules.base_task import BaseTask
from modules.db.connection import managed_connect
from modules.db.repositories import ExtractionRepository, LookupKey
from modules.exceptions import TaskError
from modules.services.csv_reference_lookup import LookupConfig, ReferenceDataError, evaluate_reference
from modules.services.lookup_decision_service import LookupConflictError, LookupDecisionService


class CsvReferenceLookupTask(BaseTask):
    """Look up configured reference columns and copy their text into document data."""

    def on_start(self, context: dict[str, Any]) -> None:
        self.initialize_context(context)

    def validate_required_fields(self, context: dict[str, Any]) -> None:
        """Require the pinned workflow identity and its current data."""
        for field in ("document_id", "pipeline_version_id", "current_task_key"):
            if not isinstance(context.get(field), str) or not context[field]:
                raise TaskError("CSV lookup requires a persisted document in a published pipeline.")
        if not isinstance(context.get("data"), dict):
            raise TaskError("CSV lookup requires document data from extraction.")

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Persist the decision before making lookup values available downstream."""
        try:
            self.validate_required_fields(context)
            config = LookupConfig.model_validate(self.params)
            values = context["data"]
            if any(mapping.field in values for mapping in config.returns):
                raise TaskError("A CSV lookup return field conflicts with existing document data.")
            key = LookupKey(context["document_id"], context["pipeline_version_id"], context["current_task_key"])
            with managed_connect(self.config_manager) as conn:
                extraction_id = context.get("extraction_result_id")
                if not extraction_id:
                    current = ExtractionRepository(conn).get_latest_result(key.document_id)
                    extraction_id = current["id"] if current else None
                if not extraction_id:
                    raise TaskError("CSV lookup requires a persisted extraction result.")
                decision = LookupDecisionService(conn).record_initial(
                    key, extraction_id, lambda: evaluate_reference(
                        config, values, config_path=getattr(self.config_manager, "_config_path", None),
                    ),
                )
            if decision.state == "failed":
                if decision.evaluation.outcome == "multiple_matches":
                    raise TaskError("CSV lookup matched multiple reference records.")
                raise TaskError("CSV lookup found no matching reference record.")
            context["data"] = {**values, **decision.returned_values()}
            return context
        except (TaskError, ValidationError, ReferenceDataError, LookupConflictError, sqlite3.Error) as exc:
            if isinstance(exc, TaskError):
                error = exc
            elif isinstance(exc, ValidationError):
                error = TaskError("CSV lookup configuration is invalid.")
            elif isinstance(exc, sqlite3.Error):
                error = TaskError("CSV lookup could not save or load the workflow decision.")
            else:
                error = TaskError(str(exc))
            self.register_error(context, error)
            raise error from None
