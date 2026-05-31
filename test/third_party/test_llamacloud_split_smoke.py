"""Live LlamaCloud Split smoke test.

This test is intentionally gated by RUN_LLAMACLOUD_SPLIT_SMOKE=1 because it
uploads a real PDF to LlamaCloud and waits for a live Split job.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from pypdf import PdfReader

from standard_step.split.llamacloud_split_adapter import LlamaCloudSplitAdapter


SAMPLE_PDF = Path(
    r"D:\python_code\pdfdoc_extraction\sample stock invoices from internet\random_merged_invoices_31May26.pdf"
)
DEFAULT_CONFIG_PATHS = (Path("dev_config.yaml"), Path("config.yaml"))


def _load_api_key() -> str | None:
    """Return API key from environment or local config without printing it."""
    env_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if env_key:
        return env_key

    config_paths = [
        Path(os.getenv("LLAMACLOUD_SPLIT_SMOKE_CONFIG", ""))
    ] if os.getenv("LLAMACLOUD_SPLIT_SMOKE_CONFIG") else list(DEFAULT_CONFIG_PATHS)

    for config_path in config_paths:
        if not config_path.exists():
            continue
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        task_params = (
            config.get("tasks", {})
            .get("extract_document_data", {})
            .get("params", {})
        )
        api_key = task_params.get("api_key")
        if api_key:
            return str(api_key)
    return None


@pytest.mark.skipif(
    os.getenv("RUN_LLAMACLOUD_SPLIT_SMOKE") != "1",
    reason="Set RUN_LLAMACLOUD_SPLIT_SMOKE=1 to run the live LlamaCloud Split smoke test.",
)
def test_llamacloud_split_live_smoke_returns_expected_invoice_segments() -> None:
    """Upload the sample merged invoice PDF and verify live Split JSON output."""
    api_key = _load_api_key()
    if not api_key:
        pytest.skip(
            "LLAMA_CLOUD_API_KEY, dev_config.yaml, config.yaml, or "
            "LLAMACLOUD_SPLIT_SMOKE_CONFIG task API key is required."
        )
    if not SAMPLE_PDF.exists():
        pytest.skip(f"Sample PDF does not exist: {SAMPLE_PDF}")

    assert len(PdfReader(str(SAMPLE_PDF)).pages) == 4

    adapter = LlamaCloudSplitAdapter(
        api_key=api_key,
        allow_uncategorized="forbid",
        polling_interval_seconds=2.0,
        timeout_seconds=180.0,
    )
    result = adapter.split_pdf(
        str(SAMPLE_PDF),
        [
            {
                "name": "invoice",
                "description": (
                    "A single invoice document. Split each separate invoice into its own "
                    "segment even when adjacent invoices share the same category."
                ),
            }
        ],
    )

    payload: dict[str, Any] = {
        "provider_job_id": result.provider_job_id,
        "status": result.status,
        "segments": [
            {
                "category": segment.category,
                "confidence": segment.confidence,
                "pages": segment.pages,
                "page_start": segment.page_start,
                "page_end": segment.page_end,
            }
            for segment in result.segments
        ],
        "raw_response": result.raw_response,
    }
    print("LLAMACLOUD_SPLIT_SMOKE_JSON=" + json.dumps(payload, sort_keys=True))

    assert isinstance(result.raw_response, dict)
    assert result.status and result.status.lower() == "completed"
    assert len(result.segments) == 4
    assert [segment.pages for segment in result.segments] == [[1], [2], [3], [4]]
