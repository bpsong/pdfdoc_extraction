"""Configurable workflow task that pauses documents requiring human review."""

from __future__ import annotations

from typing import Any

from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.db.connection import connect, json_loads
from modules.db.repositories import DocumentRepository, ExtractionRepository
from modules.exceptions import TaskError
from modules.services.review_service import ReviewService
from modules.services.schema_service import SchemaService


class ReviewGateTask(BaseTask):
    """Pause workflow execution when extracted data requires operator review."""

    def __init__(self, config_manager: ConfigManager, **params: Any) -> None:
        super().__init__(config_manager=config_manager, **params)
        self.confidence_threshold = float(params.get("confidence_threshold", 0.8))
        self.per_document_type_thresholds = self._threshold_map(params.get("per_document_type_thresholds"))
        self.field_threshold_overrides = self._threshold_map(params.get("field_threshold_overrides"))
        self.split_confidence_levels = set(params.get("split_confidence_levels_requiring_review") or [])
        self.require_missing_confidence = bool(params.get("require_review_when_missing_confidence", True))
        self.require_missing_required = bool(params.get("require_review_for_missing_required_fields", True))
        self.always_review = bool(params.get("always_review", False))
        self.schema_file = params.get("schema_file")
        self.queue_name = str(params.get("queue_name", "default_review"))
        self.review_scope = str(params.get("review_scope", "low_confidence_fields"))
        self.allow_edit_high_confidence = bool(params.get("allow_operator_to_edit_high_confidence_fields", True))
        self.resume_policy = str(params.get("resume_policy", "next_task"))

    def on_start(self, context: dict) -> None:
        """Initialize the shared task context."""
        self.initialize_context(context)

    def run(self, context: dict) -> dict:
        """Evaluate review rules and pause the pipeline when review is required."""
        document_id = context.get("document_id")
        batch_id = context.get("batch_id")
        if not document_id or not batch_id:
            context["review_required"] = False
            context["review_gate_status"] = "passed"
            return context

        with connect(self.config_manager) as conn:
            extraction_repository = ExtractionRepository(conn)
            document_repository = DocumentRepository(conn)
            review_service = ReviewService(conn, self.config_manager)

            fields = extraction_repository.get_fields(str(document_id))
            document = document_repository.get(str(document_id)) or {}
            reasons, highlight_fields = self._review_reasons(context, fields, document)
            extraction_repository.set_review_requirements(str(document_id), highlight_fields)

            if not reasons:
                context["review_required"] = False
                context["review_gate_status"] = "passed"
                return context

            metadata = self._review_metadata(context, fields, reasons, highlight_fields, document)
            review_item = review_service.create_review_item(
                batch_id=str(batch_id),
                document_id=str(document_id),
                queue_name=self.queue_name,
                reason=reasons[0]["reason"],
                scope=self.review_scope,
                created_by_task_run_id=context.get("task_run_id"),
                metadata=metadata,
            )
            document_repository.update_status(str(document_id), "review_required")

        context["review_required"] = True
        context["review_gate_status"] = "paused"
        context["pipeline_state"] = "paused"
        context["pause_reason"] = "review_required"
        context["review_item_id"] = review_item["id"]
        return context

    def validate_required_fields(self, context: dict) -> None:
        """Validate task preconditions."""
        if self.confidence_threshold < 0 or self.confidence_threshold > 1:
            raise TaskError("confidence_threshold must be between 0 and 1")
        for label, threshold in {
            **self.per_document_type_thresholds,
            **self.field_threshold_overrides,
        }.items():
            if threshold < 0 or threshold > 1:
                raise TaskError(f"Confidence threshold for {label} must be between 0 and 1")

    def _review_reasons(
        self,
        context: dict,
        fields: list[dict[str, Any]],
        document: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        reasons: list[dict[str, Any]] = []
        highlight_fields: list[str] = []

        if self.always_review:
            reasons.append({"reason": "always_review"})

        split_confidence = context.get("split_confidence") or document.get("split_confidence")
        if split_confidence in self.split_confidence_levels:
            reasons.append({"reason": "split_confidence", "value": split_confidence})

        schema = SchemaService(self.config_manager).load_schema(str(self.schema_file)) if self.schema_file else None
        required_schema_fields = self._required_schema_fields(schema)

        for field in fields:
            field_key = str(field["field_key"])
            confidence = field.get("confidence")
            if not self._should_check_field_confidence(field_key, required_schema_fields):
                continue
            threshold = self._threshold_for_field(field_key, context, document)
            if confidence is None:
                if self.require_missing_confidence:
                    reasons.append({"reason": "missing_confidence", "field_key": field_key})
                    highlight_fields.append(field_key)
                continue
            if float(confidence) < threshold:
                reasons.append(
                    {
                        "reason": "low_confidence",
                        "field_key": field_key,
                        "confidence": confidence,
                        "threshold": threshold,
                    }
                )
                highlight_fields.append(field_key)

        business_flags = context.get("review_flags") or context.get("business_rule_flags") or []
        if isinstance(business_flags, dict):
            business_flags = [key for key, value in business_flags.items() if value]
        for flag in business_flags if isinstance(business_flags, list) else []:
            reasons.append({"reason": "business_rule", "flag": flag})

        if self.schema_file:
            payload = context.get("data") if isinstance(context.get("data"), dict) else self._fields_payload(fields)
            schema_errors = SchemaService(self.config_manager).validate_payload(payload, schema=schema)
            for error in schema_errors:
                if not self.require_missing_required and "Required field" in error.get("message", ""):
                    continue
                reasons.append({"reason": "schema_error", "field_key": error.get("path"), "message": error.get("message")})
                if error.get("path"):
                    highlight_fields.append(str(error["path"]).split(".")[0])

        return reasons, sorted(set(highlight_fields))

    def _review_metadata(
        self,
        context: dict,
        fields: list[dict[str, Any]],
        reasons: list[dict[str, Any]],
        highlight_fields: list[str],
        document: dict[str, Any],
    ) -> dict[str, Any]:
        editable_fields = [str(field["field_key"]) for field in fields]
        if self.review_scope == "low_confidence_fields" and not self.allow_edit_high_confidence:
            editable_fields = highlight_fields
        high_confidence_fields = []
        for field in fields:
            field_key = str(field["field_key"])
            if field.get("confidence") is not None and float(field["confidence"]) >= self._threshold_for_field(
                field_key,
                context,
                document,
            ):
                high_confidence_fields.append(field_key)
        schema_hash = SchemaService(self.config_manager).schema_hash(str(self.schema_file)) if self.schema_file else None
        return {
            "schema_file": self.schema_file,
            "schema_version": schema_hash,
            "review_scope": self.review_scope,
            "confidence_threshold": self.confidence_threshold,
            "per_document_type_thresholds": self.per_document_type_thresholds,
            "field_threshold_overrides": self.field_threshold_overrides,
            "editable_fields": editable_fields,
            "highlight_fields": highlight_fields,
            "low_confidence_fields": highlight_fields,
            "high_confidence_fields": sorted(high_confidence_fields),
            "reasons": reasons,
            "allow_operator_to_edit_high_confidence_fields": self.allow_edit_high_confidence,
            "resume_policy": self.resume_policy,
            "task_run_id": context.get("task_run_id"),
        }

    @staticmethod
    def _fields_payload(fields: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            str(field["field_key"]): json_loads(field.get("final_value_json"), json_loads(field.get("extracted_value_json")))
            for field in fields
        }

    @staticmethod
    def _threshold_map(value: Any) -> dict[str, float]:
        """Normalize a threshold override mapping."""
        if not isinstance(value, dict):
            return {}
        return {str(key): float(item) for key, item in value.items() if str(key)}

    @staticmethod
    def _required_schema_fields(schema: dict[str, Any] | None) -> set[str] | None:
        """Return top-level required field keys from a review schema.

        ``None`` means no schema was available, so the legacy behavior is to
        evaluate confidence for every extracted field.
        """
        if schema is None:
            return None
        fields = schema.get("fields")
        if not isinstance(fields, dict):
            return set()
        return {
            str(field_key)
            for field_key, field_config in fields.items()
            if isinstance(field_config, dict) and bool(field_config.get("required", False))
        }

    def _should_check_field_confidence(self, field_key: str, required_schema_fields: set[str] | None) -> bool:
        """Return whether confidence rules should gate review for a field."""
        if required_schema_fields is None:
            return True
        return field_key in required_schema_fields or field_key in self.field_threshold_overrides

    def _threshold_for_field(
        self,
        field_key: str,
        context: dict[str, Any],
        document: dict[str, Any],
    ) -> float:
        """Return the configured threshold for a field and document type."""
        if field_key in self.field_threshold_overrides:
            return self.field_threshold_overrides[field_key]
        document_type = (
            context.get("document_type")
            or document.get("document_type")
            or context.get("split_category")
            or document.get("split_category")
        )
        if document_type and str(document_type) in self.per_document_type_thresholds:
            return self.per_document_type_thresholds[str(document_type)]
        return self.confidence_threshold
