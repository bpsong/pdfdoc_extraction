"""Adapter for LlamaCloud Split beta decisions.

LlamaCloud Split returns page-level split decisions. It does not create local
PDF files; physical PDF splitting is handled by ``llamacloud_split.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import time
from typing import Any

from modules.exceptions import TaskError


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


class LlamaCloudSplitAdapter:
    """Run LlamaCloud Split and normalize beta API output."""

    def __init__(
        self,
        *,
        api_key: str,
        project_id: str | None = None,
        organization_id: str | None = None,
        configuration_id: str | None = None,
        allow_uncategorized: str = "include",
        polling_interval_seconds: float = 1.0,
        timeout_seconds: float = 7200.0,
    ) -> None:
        """Initialize the adapter.

        Args:
            api_key: LlamaCloud API key.
            project_id: Optional LlamaCloud project scope.
            organization_id: Optional LlamaCloud organization scope.
            configuration_id: Optional saved Split configuration ID.
            allow_uncategorized: Split uncategorized behavior.
            polling_interval_seconds: Polling interval for completion.
            timeout_seconds: Maximum wait time for completion.
        """
        self.api_key = api_key
        self.project_id = project_id
        self.organization_id = organization_id
        self.configuration_id = configuration_id
        self.allow_uncategorized = allow_uncategorized
        self.polling_interval_seconds = polling_interval_seconds
        self.timeout_seconds = timeout_seconds

    def split_pdf(self, file_path: str, categories: list[dict[str, Any]]) -> SplitResult:
        """Upload a PDF to LlamaCloud Split and return normalized decisions.

        Args:
            file_path: Source PDF path.
            categories: Split category definitions.

        Returns:
            Normalized split result.

        Raises:
            TaskError: If configuration is invalid or provider processing fails.
        """
        if not self.api_key:
            raise TaskError("LlamaCloud Split requires api_key.")
        if not self.configuration_id and not categories:
            raise TaskError("LlamaCloud Split requires categories or configuration_id.")

        try:
            from llama_cloud import LlamaCloud
        except ImportError as exc:  # pragma: no cover - covered by dependency install.
            raise TaskError("llama-cloud package is required for LlamaCloud Split.") from exc

        client = LlamaCloud(api_key=self.api_key)
        scope = self._request_scope()
        file_obj = client.files.create(file=file_path, purpose="split", **scope)
        document_input = {"type": "file_id", "value": file_obj.id}

        split_params: dict[str, Any] = {
            "document_input": document_input,
            **scope,
        }
        if self.configuration_id:
            split_params["configuration_id"] = self.configuration_id
        else:
            split_params["configuration"] = {
                "categories": categories,
                "splitting_strategy": {"allow_uncategorized": self.allow_uncategorized},
            }

        created_job = client.beta.split.create(**split_params)
        job = self._wait_for_completion(client, created_job, scope)

        return self._normalize_response(job)

    def _request_scope(self) -> dict[str, str]:
        """Return optional LlamaCloud organization/project scope."""
        scope: dict[str, str] = {}
        if self.project_id:
            scope["project_id"] = self.project_id
        if self.organization_id:
            scope["organization_id"] = self.organization_id
        return scope

    def _wait_for_completion(
        self,
        client: Any,
        created_job: Any,
        scope: dict[str, str],
    ) -> Any:
        """Poll a LlamaCloud Split job until it reaches a terminal state."""
        job = created_job
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            status = str(_get_attr(job, "status", "") or "").lower()
            if status in {"completed", "complete", "success"}:
                return job
            if status in {"failed", "cancelled", "canceled"}:
                error_message = _get_attr(job, "error_message") or _get_attr(job, "error")
                raise TaskError(
                    f"LlamaCloud Split job {_get_attr(job, 'id')} ended with status {status}: {error_message}"
                )
            if time.monotonic() >= deadline:
                raise TaskError(f"LlamaCloud Split job {_get_attr(job, 'id')} timed out after {self.timeout_seconds}s.")

            split_job_id = _get_attr(job, "id")
            if not split_job_id:
                raise TaskError("LlamaCloud Split did not return a split job id.")
            time.sleep(max(0.0, self.polling_interval_seconds))
            job = client.beta.split.get(split_job_id, **scope)

    @classmethod
    def _normalize_response(cls, response: Any) -> SplitResult:
        """Normalize a LlamaCloud Split response object."""
        provider_job_id = _get_attr(response, "id")
        status = _get_attr(response, "status")
        result = _get_attr(response, "result")
        raw_response = _json_safe(response)
        raw_segments = _get_attr(result, "segments") if result is not None else []

        segments: list[SplitSegment] = []
        for index, raw_segment in enumerate(raw_segments or []):
            pages = [int(page) for page in (_get_attr(raw_segment, "pages") or [])]
            if not pages:
                continue
            if any(page < 1 for page in pages):
                raise TaskError("LlamaCloud Split returned non-positive page numbers.")
            category = _get_attr(raw_segment, "category")
            confidence = _get_attr(raw_segment, "confidence_category")
            segments.append(
                SplitSegment(
                    category=str(category) if category is not None else None,
                    confidence=str(confidence) if confidence is not None else None,
                    pages=pages,
                    page_start=min(pages),
                    page_end=max(pages),
                    metadata={
                        "provider": "llamacloud_split",
                        "segment_index": index,
                        "raw_segment": _json_safe(raw_segment),
                    },
                )
            )

        return SplitResult(
            provider_job_id=str(provider_job_id) if provider_job_id is not None else None,
            status=str(status) if status is not None else None,
            segments=segments,
            raw_response=raw_response if isinstance(raw_response, dict) else {"response": raw_response},
        )


def _get_attr(value: Any, name: str, default: Any = None) -> Any:
    """Read an attribute or dictionary key from provider objects."""
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _json_safe(value: Any) -> Any:
    """Convert provider SDK models into JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if hasattr(value, "dict"):
        try:
            return _json_safe(value.dict())
        except TypeError:
            pass
    if hasattr(value, "__dict__"):
        return _json_safe({key: item for key, item in vars(value).items() if not key.startswith("_")})
    return str(value)
