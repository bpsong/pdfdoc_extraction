"""Configured local LiteParse and Ollama structured extraction task."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from modules.base_task import BaseTask
from modules.config_protocol import ConfigProvider
from modules.db.connection import managed_connect
from modules.db.repositories import ExtractionRepository
from modules.exceptions import TaskError
from standard_step.extraction.liteparse_adapter import (
    LiteParseExtractionError,
    LiteParseOllamaAdapter,
    build_citation_schema,
    validate_liteparse_options,
)


class LiteParseExtractTask(BaseTask):
    """Extract configurable fields locally using LiteParse text and Ollama."""

    def __init__(self, config_manager: ConfigProvider, **params: Any) -> None:
        super().__init__(config_manager=config_manager, **params)
        self.options: dict[str, Any] = {}
        self.fields: dict[str, Any] = {}

    def on_start(self, context: dict) -> None:
        self.initialize_context(context)
        try:
            self.validate_required_fields(context)
        except TaskError as error:
            self.register_error(context, error)
            raise

    def validate_required_fields(self, context: dict) -> None:
        """Validate only published parameters and the workflow PDF input."""
        try:
            self.options = validate_liteparse_options(self.params)
            fields = self.params.get("fields")
            if not isinstance(fields, dict) or not 1 <= len(fields) <= 100:
                raise ValueError("fields must contain 1-100 configured fields.")
            build_citation_schema(fields)
            self.fields = fields
        except (ValueError, TypeError) as error:
            raise TaskError("LiteParse extraction configuration is invalid.") from error
        path = context.get("file_path")
        if not isinstance(path, str) or not Path(path).is_file():
            raise TaskError("LiteParse extraction requires a readable context['file_path'] PDF.")

    def run(self, context: dict) -> dict:
        """Persist nullable-confidence fields and preserve the shared context."""
        self.initialize_context(context)
        try:
            self.validate_required_fields(context)
            result = LiteParseOllamaAdapter(**self.options).extract(
                Path(context["file_path"]), self.fields,
                self.options["document_instructions"],
            )
            if context.get("document_id"):
                rows = [{
                    "field_key": key, "field_alias": config.get("alias") or key,
                    "extracted_value": result.data[key], "final_value": result.data[key],
                    "confidence": None, "confidence_label": None,
                    "requires_review": False, "review_status": "not_required",
                    "source": result.sources[key],
                } for key, config in self.fields.items()]
                with managed_connect(self.config_manager) as conn:
                    repo = ExtractionRepository(conn)
                    saved = repo.save_result(
                        document_id=str(context["document_id"]),
                        task_run_id=context.get("task_run_id"), provider="liteparse_ollama",
                        provider_job_id=None, data=result.data, metadata=result.metadata,
                    )
                    repo.save_fields(document_id=str(context["document_id"]),
                                     extraction_result_id=str(saved["id"]), fields=rows)
                context["extraction_result_id"] = saved["id"]
            if not isinstance(context.get("data"), dict):
                context["data"] = {}
            context["data"].update(result.data)
            if not isinstance(context.get("metadata"), dict):
                context["metadata"] = {}
            context["metadata"]["liteparse"] = result.metadata
            self._review_flag(context)
            # Prefect retries reuse this mutable context. A successful attempt
            # must clear its own earlier failure without masking another task.
            if context.get("error_step") == self.task_key(context):
                context["error"] = None
                context["error_step"] = None
            return context
        except TaskError as error:
            self.register_error(context, error)
            raise
        except LiteParseExtractionError as error:
            task_error = TaskError(str(error))
            self.register_error(context, task_error)
            raise task_error from error
        except (sqlite3.Error, OSError, ValueError, TypeError, KeyError) as error:
            task_error = TaskError("LiteParse extraction or result persistence failed.")
            self.logger.error("LiteParse extraction failed (%s)", type(error).__name__)
            self.register_error(context, task_error)
            raise task_error from error

    def _review_flag(self, context: dict) -> None:
        """Request review without inventing confidence or pausing the workflow."""
        entry = {"reason": "unscored_extraction", "field_keys": list(self.fields)}
        flags = context.get("review_flags")
        if flags is None:
            context["review_flags"] = {"liteparse_unscored": entry}
        elif isinstance(flags, dict):
            flags.setdefault("liteparse_unscored", entry)
        else:
            value = {"flag": "liteparse_unscored", **entry}
            if not isinstance(flags, list):
                flags = [flags]
                context["review_flags"] = flags
            if value not in flags:
                flags.append(value)
