"""Evaluate a read-only reference register against document-level values."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections.abc import Iterator, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from modules.config_paths import resolve_config_path
from modules.services.task_registry_service import BUILTIN_TASKS


DEFAULT_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_CANDIDATES = 50
CSV_LOOKUP_TASK = BUILTIN_TASKS["csv_reference_lookup"]
LOOKUP_RESERVED_FIELDS = frozenset({
    "id", "nanoid", "filename", "source", "original_filename", "file_path", "timestamp",
    "document_id", "batch_id", "pipeline_version_id", "pipeline_template_id",
    "data", "metadata", "extraction_result_id", "task_run_id", "current_task_key",
})
_DECIMAL_TEXT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")

Comparison = Literal["case_sensitive", "case_insensitive", "numeric"]
Policy = Literal["review", "fail", "continue"]
NonemptyText = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]
TopLevelField = Annotated[str, StringConstraints(strict=True, pattern=r"^[^.\[\]\s]+$")]


class MatchClause(BaseModel):
    """Bind an extraction field to a named reference column."""

    model_config = ConfigDict(extra="forbid")
    field: TopLevelField
    column: NonemptyText
    mode: Comparison = "case_sensitive"


class ReturnMapping(BaseModel):
    """Copy one reference cell to a new document-level field."""

    model_config = ConfigDict(extra="forbid")
    column: NonemptyText
    field: TopLevelField


class LookupConfig(BaseModel):
    """Pinned task parameters used by the evaluator and publication checks."""

    model_config = ConfigDict(extra="forbid")
    reference_file: NonemptyText
    clauses: Annotated[list[MatchClause], Field(min_length=1, max_length=5)]
    returns: Annotated[list[ReturnMapping], Field(min_length=1)]
    required: Annotated[bool, Field(strict=True)] = True
    on_no_match: Policy = "review"
    on_multiple_matches: Policy = "review"

    @model_validator(mode="after")
    def validate_bindings(self) -> LookupConfig:
        """Reject collisions visible within this task and incompatible policies."""
        targets = {mapping.field for mapping in self.returns}
        if len(targets) != len(self.returns):
            raise ValueError("Return field keys must be unique.")
        if targets.intersection(clause.field for clause in self.clauses):
            raise ValueError("A return field cannot overwrite a match input.")
        if targets & LOOKUP_RESERVED_FIELDS:
            raise ValueError("Return field keys cannot use reserved workflow names.")
        if self.required and "continue" in (self.on_no_match, self.on_multiple_matches):
            raise ValueError("A required lookup cannot continue without enrichment.")
        return self


class ReferenceDataError(ValueError):
    """The worker cannot evaluate the configured reference data."""


class ReferenceChangedError(ReferenceDataError):
    """The bytes needed to reevaluate this decision are unavailable."""


class ReferenceUnavailableError(ReferenceDataError):
    """The validating process cannot open the configured file."""


class MatchInput(BaseModel):
    """Store the input and comparison key separately for review evidence."""

    field: str
    column: str
    mode: Comparison
    original: str | None
    normalized: str | None
    issue: Literal["missing", "blank", "invalid"] | None = None


class Candidate(BaseModel):
    """Retain the displayed match columns and mapped values from one row."""

    record_number: int
    matched_columns: dict[str, str]
    values: dict[str, str]

    def complete_values(self) -> dict[str, str]:
        """Require every mapped cell before releasing any returned field."""
        if any(not value.strip() for value in self.values.values()):
            raise ReferenceDataError("A selected record contains a blank return cell.")
        return dict(self.values)


class LookupEvaluation(BaseModel):
    """Record a deterministic outcome and bounded evidence for later reuse."""

    source_sha256: str
    required: bool
    inputs: list[MatchInput]
    match_count: int
    candidates: list[Candidate]
    outcome: Literal["matched", "no_match", "multiple_matches"]
    disposition: Literal["matched", "pending", "skipped", "failed"]


def _key(value: object, mode: Comparison) -> str | Decimal | None:
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        if mode == "numeric":
            return Decimal(trimmed) if _DECIMAL_TEXT.fullmatch(trimmed) else None
        return trimmed.casefold() if mode == "case_insensitive" else trimmed
    if mode == "numeric" and (
        type(value) is int or (isinstance(value, float) and math.isfinite(value))
    ):
        return Decimal(str(value))
    return None


def _input(clause: MatchClause, value: object, key: str | Decimal | None) -> MatchInput:
    issue: Literal["missing", "blank", "invalid"] | None = None
    if key is None:
        if value is None:
            issue = "missing"
        elif isinstance(value, str) and not value.strip():
            issue = "blank"
        else:
            issue = "invalid"
    return MatchInput(
        field=clause.field, column=clause.column, mode=clause.mode,
        original=str(value) if isinstance(value, (str, int, float)) else None,
        normalized=str(key) if key is not None else None, issue=issue,
    )


def lookup_inputs(config: LookupConfig, values: Mapping[str, object]) -> list[MatchInput]:
    """Describe current inputs using the same normalization as the matcher."""
    inputs = []
    for clause in config.clauses:
        value = values.get(clause.field)
        inputs.append(_input(clause, value, _key(value, clause.mode)))
    return inputs


def _read_reference(
    config: LookupConfig,
    config_path: str | Path | None,
    max_bytes: int,
) -> bytes:
    try:
        path = resolve_config_path(config.reference_file, config_path=config_path)
        with path.open("rb") as source:
            raw = source.read(max_bytes + 1)
    except (OSError, RuntimeError, ValueError):
        raise ReferenceUnavailableError("The configured reference file could not be read.") from None
    if len(raw) > max_bytes:
        raise ReferenceDataError("The reference file exceeds the byte limit.")
    return raw


def _reference_rows(raw: bytes, config: LookupConfig) -> tuple[dict[str, int], Iterator[list[str]]]:
    try:
        contents = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ReferenceDataError("The reference file is not valid UTF-8.") from None
    if "\0" in contents:
        raise ReferenceDataError("The reference file contains a null character.")
    rows = csv.reader(io.StringIO(contents, newline=""), strict=True)
    try:
        header = next(rows, [])
    except csv.Error:
        raise ReferenceDataError("The reference file contains a malformed or oversized header.") from None
    if not header or len(set(header)) != len(header) or any(not column.strip() for column in header):
        raise ReferenceDataError("The reference file needs unique, nonblank column names.")
    indexes = {column: index for index, column in enumerate(header)}
    if any(item.column not in indexes for item in [*config.clauses, *config.returns]):
        raise ReferenceDataError("The reference file is missing a configured column.")
    return indexes, rows


def validate_reference_header(config: LookupConfig, *, config_path: str | Path) -> None:
    """Check configured columns without interpreting any business rows."""
    _reference_rows(_read_reference(config, config_path, DEFAULT_MAX_BYTES), config)


def evaluate_reference(
    config: LookupConfig,
    values: Mapping[str, object],
    *,
    config_path: str | Path | None = None,
    expected_sha256: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> LookupEvaluation:
    """Read and hash one bounded buffer, then evaluate all reference records."""
    if max_bytes < 1 or max_candidates < 1:
        raise ValueError("Reference byte and candidate limits must be positive.")
    try:
        raw = _read_reference(config, config_path, max_bytes)
    except ReferenceUnavailableError:
        if expected_sha256 is not None:
            raise ReferenceChangedError("The original reference file is unavailable.") from None
        raise
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ReferenceChangedError("The reference file has changed since evaluation.")

    source_values = [values.get(clause.field) for clause in config.clauses]
    keys = [_key(value, clause.mode) for clause, value in zip(config.clauses, source_values)]
    inputs = [
        _input(clause, value, key)
        for clause, value, key in zip(config.clauses, source_values, keys)
    ]
    count = 0
    candidates: list[Candidate] = []
    indexes, rows = _reference_rows(raw, config)
    try:
        for record_number, row in enumerate(rows, start=1):
            if len(row) != len(indexes):
                raise ReferenceDataError(f"Reference record {record_number} has the wrong column count.")
            cells = [row[indexes[clause.column]] for clause in config.clauses]
            row_keys = [_key(cell, clause.mode) for cell, clause in zip(cells, config.clauses)]
            if any(key is None and cell.strip() for key, cell in zip(row_keys, cells)):
                raise ReferenceDataError(f"Reference record {record_number} has an invalid numeric key.")
            if None in keys or keys != row_keys:
                continue
            count += 1
            if len(candidates) < max_candidates:
                candidates.append(Candidate(
                    record_number=record_number,
                    matched_columns={clause.column: cell for clause, cell in zip(config.clauses, cells)},
                    values={mapping.field: row[indexes[mapping.column]] for mapping in config.returns},
                ))
    except csv.Error:
        raise ReferenceDataError("The reference file contains malformed or oversized CSV fields.") from None

    if count == 1:
        candidates[0].complete_values()
        return LookupEvaluation(source_sha256=digest, required=config.required, inputs=inputs, match_count=count,
                                candidates=candidates, outcome="matched", disposition="matched")
    policy = config.on_multiple_matches if count else config.on_no_match
    dispositions: dict[Policy, Literal["pending", "skipped", "failed"]] = {
        "review": "pending", "continue": "skipped", "fail": "failed",
    }
    return LookupEvaluation(
        source_sha256=digest, required=config.required, inputs=inputs, match_count=count, candidates=candidates,
        outcome="multiple_matches" if count else "no_match", disposition=dispositions[policy],
    )
