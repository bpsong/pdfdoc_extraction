"""Provider-independent page segment and split result contracts."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SplitSegment:
    """Normalized split segment returned by a split provider.

    Attributes:
        category: Provider classification, or None when unavailable.
        confidence: Provider confidence label (for example, "high"), not a score.
        pages: Exact 1-based source page numbers in output order; these drive
            PDF creation and need not form a contiguous range.
        page_start: Inclusive minimum source page number, used for summaries.
        page_end: Inclusive maximum source page number, used for summaries.
        metadata: Provider-specific details, such as the raw segment and index.
    """

    category: str | None
    confidence: str | None
    pages: list[int]
    page_start: int
    page_end: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SplitResult:
    """Normalized split result consumed by the split pipeline task.

    Attributes:
        provider_job_id: External job identifier, or None for a local decision.
        status: Provider/local result status; not a workflow document status.
        segments: Ordered output segments; an empty list represents no segments.
        raw_response: Provider response retained for diagnostics/provenance;
            local decisions may supply an empty dictionary.
    """

    provider_job_id: str | None
    status: str | None
    segments: list[SplitSegment]
    raw_response: dict[str, Any]
