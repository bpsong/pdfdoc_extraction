"""Provider-independent page segment and split result contracts."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SplitSegment:
    """Normalized split segment returned by a split provider."""

    category: str | None
    confidence: str | None
    pages: list[int]
    page_start: int
    page_end: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SplitResult:
    """Normalized split result consumed by the split pipeline task."""

    provider_job_id: str | None
    status: str | None
    segments: list[SplitSegment]
    raw_response: dict[str, Any]
