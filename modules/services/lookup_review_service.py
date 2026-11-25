"""Plan and accept CSV lookup resolutions within extraction review."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from modules.config_protocol import ConfigProvider
from modules.db.connection import json_loads
from modules.db.repositories import LookupKey, PipelineVersionRepository, TaskRunRepository
from modules.services.csv_reference_lookup import (
    LookupConfig, LookupEvaluation, ReferenceChangedError, ReferenceDataError,
    evaluate_reference, lookup_inputs,
)
from modules.services.lookup_decision_service import (
    DecisionState, LookupConflictError, LookupDecision, LookupDecisionService, resolution_values,
)
from modules.services.lookup_pipeline_validation import active_lookup_configs
from modules.services.pipeline_definition_service import ExecutablePipeline
from modules.services.review_business_validation import snapshot_hash
from modules.services.task_registry_service import ASSIGN_NANOID_TASK


Reason = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1000)]
Token = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


def lookup_nanoid(
    task_runs: TaskRunRepository, document_id: str, executable: ExecutablePipeline, before_index: int,
) -> dict[str, str]:
    """Restore the generated ID recorded before this lookup pipeline cursor."""
    for index in range(before_index - 1, -1, -1):
        task = executable.tasks[executable.pipeline[index]]
        if (task.get("module"), task.get("class")) != ASSIGN_NANOID_TASK:
            continue
        run = task_runs.latest_completed_at(document_id, executable.version_id, index)
        value = json_loads(run["output_json"], {}).get("nanoid") if run else None
        if not isinstance(value, str) or not value:
            raise LookupConflictError("The generated document identifier is unavailable for recovery.")
        return {"nanoid": value}
    return {}


class LookupAction(BaseModel):
    """A proposed human decision tied to evaluated evidence."""

    model_config = ConfigDict(extra="forbid")
    action: Literal["select", "skip"]
    evaluation_token: Token
    record_number: Annotated[int, Field(strict=True, ge=1)] | None = None
    reason: Reason

    @model_validator(mode="after")
    def check_record(self) -> LookupAction:
        if (self.action == "select") != (self.record_number is not None):
            raise ValueError("Only a selection specifies a record number.")
        return self


class LookupReviewRequest(BaseModel):
    """Lookup actions and explicit file adoptions in a review request."""

    actions: dict[str, LookupAction] = Field(default_factory=dict)
    adoptions: dict[str, Reason] = Field(default_factory=dict)


@dataclass(frozen=True)
class ReviewLookup:
    key: LookupKey
    config: LookupConfig
    decision: LookupDecision


@dataclass(frozen=True)
class LookupProposal:
    lookup: ReviewLookup
    evaluation: LookupEvaluation
    evaluation_token: str
    state: DecisionState
    returned: dict[str, str]
    selected: int | None
    action: LookupAction | None = None
    adoption: str | None = None
    issue: str | None = None

    @property
    def blocked(self) -> bool:
        return self.issue is not None or self.state not in {"matched", "skipped"}

    def payload(self) -> dict[str, Any]:
        """Expose bounded evidence for the review UI with reference provenance."""
        decision = self.lookup.decision
        evaluation = self.evaluation
        complete = evaluation.match_count == len(evaluation.candidates)
        return {
            "task_key": self.lookup.key.task_key,
            "decision_id": decision.id,
            "decision_revision": decision.revision,
            "source": "csv_reference",
            "source_sha256": evaluation.source_sha256,
            "recorded_source_sha256": decision.evaluation.source_sha256,
            "inputs": [item.model_dump() for item in evaluation.inputs],
            "outcome": evaluation.outcome,
            "state": self.state,
            "required": evaluation.required,
            "returned_values": self.returned,
            "return_fields": [mapping.field for mapping in self.lookup.config.returns],
            "match_count": evaluation.match_count,
            "candidates": [
                {
                    **candidate.model_dump(),
                    "match_evidence": [
                        {"field": item.field, "column": item.column, "mode": item.mode,
                         "reference_value": candidate.matched_columns.get(item.column)}
                        for item in evaluation.inputs
                    ],
                }
                for candidate in evaluation.candidates
            ],
            "candidates_truncated": not complete,
            "selected_record_number": self.selected,
            "evaluation_token": self.evaluation_token,
            "can_select": self.issue is None and self.state == "pending" and complete and bool(evaluation.candidates),
            "can_skip": self.issue is None and self.state == "pending" and not evaluation.required,
            "issue": self.issue,
            "adoption_proposed": self.adoption is not None,
            "blocked": self.blocked,
            "actor": decision.actor,
            "reason": decision.reason,
        }


class LookupReviewService:
    """Read pinned lookups and repeat the preview before atomic acceptance."""

    def __init__(self, conn: sqlite3.Connection, config: ConfigProvider | None = None) -> None:
        self.conn = conn
        self.decisions = LookupDecisionService(conn)
        self.config_path = getattr(config, "_config_path", None)

    def load_before(
        self, document_id: str, version_id: str | None, extraction_id: str | None,
        before_index: int, *, accepted_ids: Mapping[str, str] | None = None,
    ) -> dict[str, ReviewLookup]:
        """Load decisions for exactly the lookup tasks upstream of the gate."""
        if not version_id or (before_index <= 0 and not accepted_ids):
            return {}
        version = PipelineVersionRepository(self.conn).get(version_id)
        definition = json_loads(version["definition_json"], {}) if version else {}
        definition["pipeline"] = definition.get("pipeline", [])[:before_index]
        result: dict[str, ReviewLookup] = {}
        for task_key, settings in active_lookup_configs(definition).items():
            key = LookupKey(document_id, version_id, task_key)
            decision = (
                self.decisions.current(key) if accepted_ids is None
                else self.decisions.get(key, accepted_ids.get(task_key, ""))
            )
            if decision is None or decision.extraction_result_id != extraction_id:
                raise LookupConflictError("An upstream CSV lookup decision is missing for this extraction.")
            result[task_key] = ReviewLookup(key, settings, decision)
        if accepted_ids is not None and set(accepted_ids) != result.keys():
            raise LookupConflictError("Accepted CSV lookup decisions do not match the review scope.")
        return result

    def propose(
        self, lookups: Mapping[str, ReviewLookup], values: Mapping[str, Any],
        request: LookupReviewRequest, review_revision: str,
        *, allow_rematch: bool = True,
    ) -> dict[str, LookupProposal]:
        """Evaluate corrections and validate requested resolutions without writing."""
        if (request.actions.keys() | request.adoptions.keys()) - lookups.keys():
            raise ValueError("Lookup actions must target a lookup in this review.")
        return {
            task: self._propose_one(
                lookup, values, review_revision, request.actions.get(task),
                request.adoptions.get(task), allow_rematch=allow_rematch,
            )
            for task, lookup in lookups.items()
        }

    def _propose_one(
        self, lookup: ReviewLookup, values: Mapping[str, Any], revision: str,
        action: LookupAction | None, adoption: str | None, *, allow_rematch: bool,
    ) -> LookupProposal:
        current = lookup.decision
        evaluation = current.evaluation
        state, selected, returned = current.state, current.selected_record_number, current.returned_values()
        issue = None
        inputs = lookup_inputs(lookup.config, values) if allow_rematch else evaluation.inputs
        if allow_rematch and (adoption is not None or inputs != evaluation.inputs):
            returned, selected, state = {}, None, "pending"
            try:
                evaluation = evaluate_reference(
                    lookup.config, values, config_path=self.config_path,
                    expected_sha256=evaluation.source_sha256 if adoption is None else None,
                )
            except ReferenceChangedError:
                issue = "reference_changed"
            except ReferenceDataError:
                issue = "reference_unavailable"
            else:
                state = evaluation.disposition
                if state == "matched":
                    selected = evaluation.candidates[0].record_number
                    returned = evaluation.candidates[0].complete_values()
        token = snapshot_hash({
            "lookup": lookup.key, "decision": current.id, "review": revision,
            "inputs": [item.model_dump() for item in inputs],
            "evaluation": evaluation.model_dump(mode="json"), "adoption": adoption,
        })
        if action is not None and issue is None:
            if action.evaluation_token != token:
                issue = "stale_lookup_selection"
                returned, selected = {}, None
            elif state != "pending":
                issue = "lookup_action_unavailable"
            else:
                try:
                    returned = resolution_values(evaluation, action.record_number)
                except ValueError:
                    issue = "invalid_lookup_resolution"
                else:
                    selected = action.record_number
                    state = "skipped" if selected is None else "matched"
        return LookupProposal(lookup, evaluation, token, state, returned, selected, action, adoption, issue)

    def accept(self, proposals: Mapping[str, LookupProposal], actor: str) -> dict[str, str]:
        """Commit the validated proposals inside the caller's acceptance transaction."""
        accepted: dict[str, str] = {}
        for task, proposal in proposals.items():
            if proposal.blocked:
                raise LookupConflictError("Resolve all CSV lookups before completing review.")
            lookup = proposal.lookup
            decision = lookup.decision
            if proposal.adoption is not None or proposal.evaluation != decision.evaluation:
                decision = self.decisions.record_reevaluation(
                    lookup.key, proposal.evaluation, expected_revision=decision.revision,
                    actor=actor, adoption_reason=proposal.adoption,
                )
            if proposal.action is not None:
                decision = self.decisions.resolve(
                    lookup.key, expected_revision=decision.revision,
                    record_number=proposal.action.record_number, actor=actor, reason=proposal.action.reason,
                )
            accepted[task] = decision.id
        return accepted
