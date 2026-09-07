"""Small contract tests for GLM-OCR task defensive branches."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.exceptions import TaskError
from standard_step.extraction.glm_ocr_adapter import (
    GlmOcrAdapterError,
    GlmOcrModelNotFoundError,
    GlmOcrPdfError,
    GlmOcrResponseError,
    GlmOcrTimeoutError,
    GlmOcrUnavailableError,
)
from standard_step.extraction.glm_ocr_extract import (
    GlmOcrExtractTask,
    _adapter_error_message,
    _host_classification,
    _validate_ollama_host,
)
from test.extraction.test_glm_ocr_extract import _fields, _params
from test.helpers_sqlite import TempConfig


def _task(tmp_path, **overrides) -> tuple[GlmOcrExtractTask, dict]:
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    task = GlmOcrExtractTask(
        TempConfig(tmp_path / "state.sqlite3", {}), **_params(**overrides)
    )
    return task, {"file_path": str(pdf)}


def test_on_start_translates_non_task_configuration_errors(tmp_path, monkeypatch) -> None:
    task, context = _task(tmp_path)
    monkeypatch.setattr(task, "_load_parameters", lambda: (_ for _ in ()).throw(TypeError("bad")))
    with pytest.raises(TaskError, match="configuration is invalid"):
        task.on_start(context)
    assert context["fatal_failure"]["failure_type"] == "glm_ocr_failed"


@pytest.mark.parametrize(
    "overrides",
    [
        {"fields": {}},
        {"fields": {str(i): {"type": "str"} for i in range(101)}},
        {"ollama_host": ""},
        {"model": ""},
        {"document_instructions": 1},
        {"prompt_style": "invalid"},
        {"prompt_style": "verbatim", "document_instructions": ""},
        {"resolution_mode": "invalid"},
        {"resolution_mode": "document", "resolver_model": ""},
        {"dpi": 0},
        {"resolver_max_attempts": 6},
        {"resolver_max_dimension": 255},
        {"timeout_seconds": 0},
    ],
)
def test_required_field_validation_rejects_invalid_settings(tmp_path, overrides) -> None:
    task, context = _task(tmp_path, **overrides)
    with pytest.raises(TaskError):
        task.on_start(context)


def test_task_helpers_cover_safe_metadata_flags_and_invalid_result(tmp_path) -> None:
    task, _ = _task(tmp_path)
    task._load_parameters()
    task._merge_review_flag({"review_flags": {"existing": True}})
    dict_context = {"review_flags": {"existing": True}}
    task._merge_review_flag(dict_context)
    assert "glm_ocr_unscored" in dict_context["review_flags"]
    scalar_context = {"review_flags": "legacy"}
    task._merge_review_flag(scalar_context)
    assert isinstance(scalar_context["review_flags"], list)
    with pytest.raises(TaskError, match="invalid structured result"):
        task._processed_data(SimpleNamespace(data=[]))


def test_glm_ocr_run_and_parameter_loading_defensive_branches(tmp_path) -> None:
    task, context = _task(tmp_path)
    with pytest.raises(TaskError, match=r"context\['file_path'\]"):
        task.validate_required_fields({"file_path": None})
    task._parameters_loaded = False
    context["file_path"] = str(tmp_path / "missing.pdf")
    with pytest.raises(TaskError, match="source PDF"):
        task.validate_required_fields(context)

    task, context = _task(tmp_path)
    task._parameters_loaded = True
    task.validate_required_fields = lambda _context: (_ for _ in ()).throw(TaskError("validation"))
    with pytest.raises(TaskError, match="validation"):
        task.run(context)
    assert context["error_step"] == "GlmOcrExtractTask"

    task, context = _task(tmp_path)
    task._build_adapter = lambda: SimpleNamespace(
        extract=lambda *_args, **_kwargs: SimpleNamespace(
            data={"supplier": "ACME"}, calls=[], page_count=1, field_pages={},
            findings=[], normalization_findings=[], conflicts=[]
        )
    )
    context["data"] = ["legacy"]
    context["metadata"] = "legacy"
    result = task.run(context)
    assert result["data"]["invoice_number"] is None
    assert isinstance(result["metadata"], dict)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GlmOcrModelNotFoundError("x"), "not installed"),
        (GlmOcrTimeoutError("x"), "timed out"),
        (GlmOcrPdfError("x"), "source PDF"),
        (GlmOcrResponseError("x"), "invalid or incomplete"),
        (GlmOcrUnavailableError("x"), "unavailable"),
        (GlmOcrAdapterError("x"), "unavailable"),
    ],
)
def test_provider_errors_are_translated_without_details(error, expected) -> None:
    assert expected in _adapter_error_message(error)


def test_ollama_host_validation_and_classification() -> None:
    for value in ("http://localhost:11434", "https://example.test", "http://[::1]"):
        _validate_ollama_host(value)
    assert _host_classification("http://LOCALHOST:11434") == "loopback"
    assert _host_classification("https://example.test") == "remote"
    for value in ("ftp://host", "http://user:pass@host", "http://host/path", "http://host:0", "http://host:99999"):
        with pytest.raises(TaskError):
            _validate_ollama_host(value)
    with pytest.raises(TaskError, match="invalid port"):
        _validate_ollama_host("http://host:not-a-port")
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
