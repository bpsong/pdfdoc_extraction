"""Coordinate revisioned CSV lookup decisions and effective document values."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel

from modules.db.connection import atomic_transaction
from modules.db.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    LookupDecisionRepository,
    LookupKey,
)
from modules.services.csv_reference_lookup import LookupEvaluation


class LookupConflictError(ValueError):
    """The lookup no longer belongs to the expected workflow revision."""


DecisionState = Literal["matched", "pending", "skipped", "failed"]


class LookupDecision(BaseModel):
    """A persisted evaluation or human resolution for one lookup."""

    id: str
    extraction_result_id: str
    revision: int
    supersedes_id: str | None
    state: DecisionState
    evaluation: LookupEvaluation
    selected_record_number: int | None
    actor: str | None
    reason: str | None

    def returned_values(self) -> dict[str, str]:
        """Project only the text cells selected by this revision."""
        if self.state != "matched":
            return {}
        for candidate in self.evaluation.candidates:
            if candidate.record_number == self.selected_record_number:
                return candidate.complete_values()
        raise LookupConflictError("The selected reference record is missing.")

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> LookupDecision:
        return cls.model_validate({
            **row, "evaluation": LookupEvaluation.model_validate_json(row["evaluation_json"]),
        })


class LookupDecisionService:
    """Persist decisions under a write reservation or a caller-owned transaction."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.decisions = LookupDecisionRepository(conn)

    def current(self, key: LookupKey) -> LookupDecision | None:
        row = self.decisions.current(key)
        return LookupDecision.from_row(row) if row is not None else None

    def get(self, key: LookupKey, decision_id: str) -> LookupDecision | None:
        row = self.decisions.get(key, decision_id)
        return LookupDecision.from_row(row) if row is not None else None

    def _check_source(self, key: LookupKey, extraction_result_id: str) -> None:
        document = DocumentRepository(self.conn).get(key.document_id)
        extraction = ExtractionRepository(self.conn).get_latest_result(key.document_id)
        if (document is None or document["pipeline_version_id"] != key.pipeline_version_id
                or extraction is None or extraction["id"] != extraction_result_id):
            raise LookupConflictError("The document's pipeline or extraction has changed.")

    def record_initial(
        self, key: LookupKey, extraction_result_id: str,
        evaluate: Callable[[], LookupEvaluation],
    ) -> LookupDecision:
        """Reuse a committed decision before reading a potentially changed file."""
        with atomic_transaction(self.conn):
            self._check_source(key, extraction_result_id)
            current = self.current(key)
            if current is not None and current.extraction_result_id == extraction_result_id:
                return current
        evaluation = evaluate()
        with atomic_transaction(self.conn, immediate=True):
            self._check_source(key, extraction_result_id)
            current = self.current(key)
            if current is not None and current.extraction_result_id == extraction_result_id:
                return current
            return self._append_evaluation(key, extraction_result_id, evaluation, current)

    def _checked_revision(self, key: LookupKey, expected_revision: int) -> LookupDecision:
        current = self.current(key)
        if current is None or current.revision != expected_revision:
            raise LookupConflictError("The lookup decision has changed.")
        self._check_source(key, current.extraction_result_id)
        return current

    def resolve(
        self, key: LookupKey, *, expected_revision: int, record_number: int | None,
        actor: str, reason: str,
    ) -> LookupDecision:
        """Select one recorded candidate or explicitly skip an optional lookup."""
        if not actor.strip() or not reason.strip():
            raise ValueError("A lookup resolution requires an actor and reason.")
        with atomic_transaction(self.conn, immediate=True):
            current = self._checked_revision(key, expected_revision)
            if current.state != "pending":
                raise LookupConflictError("The lookup is no longer pending.")
            evaluation = current.evaluation
            resolution_values(evaluation, record_number)
            state: DecisionState = "skipped" if record_number is None else "matched"
            decision = LookupDecision.from_row(self.decisions.append(
                key, extraction_result_id=current.extraction_result_id,
                revision=current.revision + 1, supersedes_id=current.id,
                state=state, evaluation_json=evaluation.model_dump_json(),
                selected_record_number=record_number, actor=actor, reason=reason.strip(),
            ))
            self._audit(key, decision, "lookup_resolved")
            return decision

    def record_reevaluation(
        self, key: LookupKey, evaluation: LookupEvaluation, *,
        expected_revision: int, actor: str, adoption_reason: str | None = None,
    ) -> LookupDecision:
        """Append a new input revision, requiring an explicit reason to adopt new bytes."""
        if not actor.strip():
            raise ValueError("A lookup reevaluation requires an actor.")
        with atomic_transaction(self.conn, immediate=True):
            current = self._checked_revision(key, expected_revision)
            changed = evaluation.source_sha256 != current.evaluation.source_sha256
            if changed and not (adoption_reason or "").strip():
                raise ValueError("Adopting a different reference file requires a reason.")
            decision = self._append_evaluation(
                key, current.extraction_result_id, evaluation, current, actor, adoption_reason,
            )
            self._audit(key, decision, "lookup_reference_adopted" if adoption_reason else "lookup_reevaluated")
            return decision

    def _append_evaluation(
        self, key: LookupKey, extraction_result_id: str, evaluation: LookupEvaluation,
        current: LookupDecision | None, actor: str | None = None, reason: str | None = None,
    ) -> LookupDecision:
        selection = None
        if evaluation.disposition == "matched":
            candidate = evaluation.candidates[0]
            candidate.complete_values()
            selection = candidate.record_number
        return LookupDecision.from_row(self.decisions.append(
            key, extraction_result_id=extraction_result_id,
            revision=current.revision + 1 if current else 1,
            supersedes_id=current.id if current else None, state=evaluation.disposition,
            evaluation_json=evaluation.model_dump_json(), selected_record_number=selection,
            actor=actor, reason=reason.strip() if reason else None,
        ))

    def _audit(self, key: LookupKey, decision: LookupDecision, event_type: str) -> None:
        AuditRepository(self.conn).append_uncommitted(
            event_type=event_type, user=decision.actor, document_id=key.document_id,
            event={"task_key": key.task_key, "decision_id": decision.id, "state": decision.state},
        )

    def effective_data(
        self, document_id: str, pipeline_version_id: str, extraction_result_id: str,
        values: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Merge current returned fields without replacing any document value."""
        rows = self.decisions.current_for_document(document_id, pipeline_version_id, extraction_result_id)
        return merge_lookup_values(values, (LookupDecision.from_row(row).returned_values() for row in rows))


def merge_lookup_values(
    values: Mapping[str, Any], returns: Iterable[Mapping[str, str]],
) -> dict[str, Any]:
    """Project lookup returns without replacing an existing business field."""
    result = dict(values)
    for fields in returns:
        if result.keys() & fields.keys():
            raise LookupConflictError("A reference return field conflicts with a document field.")
        result.update(fields)
    return result


def resolution_values(evaluation: LookupEvaluation, record_number: int | None) -> dict[str, str]:
    """Check pending candidate selection and optional skip against evaluated evidence."""
    if record_number is None:
        if evaluation.required:
            raise ValueError("A required lookup cannot be skipped.")
        return {}
    candidate = next((row for row in evaluation.candidates if row.record_number == record_number), None)
    if candidate is None or len(evaluation.candidates) != evaluation.match_count:
        raise ValueError("Select a record from a complete set of matching candidates.")
    return candidate.complete_values()
