"""Synthetic tests for generic local parsing, typing, citations and task errors."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from modules.exceptions import TaskError
from standard_step.extraction.liteparse_adapter import (
    DEFAULTS, LiteParseExtractionError, LiteParseExtractionResult,
    LiteParseOllamaAdapter, build_citation_schema, decode_citations,
    validate_liteparse_options,
)
from standard_step.extraction.liteparse_extract import LiteParseExtractTask
from test.helpers_sqlite import TempConfig
from tools.config_check.parameter_validator import validate_parameters


FIELDS = {
    "reference": {"type": "str", "alias": "Reference"},
    "approved": {"type": "bool", "alias": "Approved"},
    "tags": {"type": "List[str]", "alias": "Tags"},
    "contact": {"type": "Optional[Dict[str, Any]]", "alias": "Contact", "object_fields": {
        "name": {"type": "str", "alias": "Name"},
        "date": {"type": "str", "alias": "Date", "normalizer": "iso_date"},
    }},
    "entries": {"type": "List[Any]", "is_table": True, "alias": "Entries", "item_fields": {
        "description": {"type": "str", "alias": "Description"},
        "quantity": {"type": "float", "alias": "Quantity"},
        "unit": {"type": "Optional[str]", "alias": "Unit"},
    }},
}


def _cited(value: Any, ids: list[str] | None = None) -> dict[str, Any]:
    return {"value": value, "source_ids": ids if ids is not None else ["p1_e0"]}


def _payload() -> dict[str, Any]:
    return {
        "reference": _cited("0007"), "approved": _cited(False),
        "tags": _cited(["urgent"]),
        "contact": {"name": _cited("Sample Person"), "date": _cited("27 May 2025")},
        "entries": [{"description": _cited("Sample goods"),
                     "quantity": _cited(2.5), "unit": _cited(None, [])}],
    }


def _parsed() -> Any:
    word = SimpleNamespace(text="Synthetic text", x=10.0, y=20.0,
                           width=100.0, height=12.0, words=[])
    page = SimpleNamespace(page_num=1, width=600, height=800,
                           text="Synthetic source", text_items=[word])
    return SimpleNamespace(pages=[page], total_pages=1, page_errors=[])


def _adapter(monkeypatch: pytest.MonkeyPatch, payload: dict | None = None,
             **options: Any) -> tuple[LiteParseOllamaAdapter, list]:
    adapter = LiteParseOllamaAdapter(**options)
    requests = []
    monkeypatch.setattr(adapter, "_parse", lambda pdf: _parsed())

    def request(route: str, body: dict | None = None) -> dict:
        requests.append((route, body))
        if route == "/api/tags":
            return {"models": [{"name": DEFAULTS["model"], "digest": "synthetic",
                                "details": {"format": "gguf"}}]}
        return {"done": True, "done_reason": "stop",
                "message": {"content": json.dumps(payload or _payload())}}

    monkeypatch.setattr(adapter, "_request", request)
    return adapter, requests


@pytest.mark.parametrize("options", [
    {"ollama_host": "http://example.com:11434"},
    {"ollama_host": "http://user:secret@localhost:11434"},
    {"ollama_host": "http://localhost:11434/path"},
    {"ollama_host": "http://localhost:0"},
    {"ocr_server_url": "http://remote"}, {"api_key": "secret"},
    {"dpi": 10}, {"num_ctx": True}, {"num_predict": 32768},
    {"timeout_seconds": float("nan")}, {"ocr_enabled": "true"},
    {"target_pages": "0"}, {"target_pages": "3-1"}, {"target_pages": "all"},
])
def test_invalid_runtime_options_fail_without_network(options: dict) -> None:
    with pytest.raises(ValueError):
        validate_liteparse_options(options)


def test_nullable_typed_schema_preserves_generic_objects_lists_and_table() -> None:
    schema = build_citation_schema(FIELDS)
    assert Draft202012Validator(schema).is_valid(_payload())
    missing = deepcopy(_payload())
    missing["reference"] = _cited(None, [])
    missing["entries"] = []
    assert Draft202012Validator(schema).is_valid(missing)
    invalid = deepcopy(_payload())
    invalid["entries"][0]["quantity"] = _cited("2.5 PCS")
    assert not Draft202012Validator(schema).is_valid(invalid)
    invalid = deepcopy(_payload())
    invalid["unexpected"] = "discarded?"
    assert not Draft202012Validator(schema).is_valid(invalid)


def test_extraction_normalizes_dates_and_returns_only_typed_business_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic")
    adapter, requests = _adapter(monkeypatch)
    result = adapter.extract(pdf, FIELDS, "Read the shipping manifest.")
    assert result.data["reference"] == "0007"
    assert result.data["approved"] is False
    assert result.data["tags"] == ["urgent"]
    assert result.data["contact"]["date"] == "2025-05-27"
    assert result.data["entries"][0]["quantity"] == 2.5
    assert result.sources["entries"]["word_boxes"][0]["bbox"] == [10, 20, 110, 32]
    assert result.metadata["model_call_count"] == 1
    assert result.metadata["confidence_available"] is False
    assert len(requests) == 2
    body = requests[1][1]
    assert body["think"] is False and body["options"]["temperature"] == 0
    assert body["keep_alive"] == 0
    assert "Read the shipping manifest." in body["messages"][1]["content"]
    assert "Synthetic source" not in json.dumps(result.metadata)


def test_unknown_citations_never_invent_boxes_or_numeric_confidence() -> None:
    payload = _payload()
    payload["reference"] = _cited("0007", ["unknown-id"])
    values, sources = decode_citations(payload, FIELDS, {})
    assert values["reference"] == "0007"
    assert sources["reference"]["word_boxes"] == []
    assert sources["reference"]["pages"] == []
    assert sources["reference"]["citation_findings"]


def test_real_local_parser_reads_native_pdf_with_timeout(tmp_path: Path) -> None:
    import fitz

    pdf = tmp_path / "synthetic.pdf"
    with fitz.open() as document:
        for text in ("Synthetic shipping manifest 0007", "Synthetic second page"):
            page = document.new_page()
            page.insert_text((72, 72), text)
        document.save(pdf)
    parsed = LiteParseOllamaAdapter(target_pages="2")._parse(pdf)
    assert parsed.total_pages == 2
    assert [page.page_num for page in parsed.pages] == [2]
    assert "Synthetic second page" in parsed.pages[0].text
    assert parsed.pages[0].text_items
    with pytest.raises(LiteParseExtractionError, match="exceed"):
        LiteParseOllamaAdapter(target_pages="3")._parse(pdf)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_model_numbers_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, number: float,
) -> None:
    payload = _payload()
    payload["entries"][0]["quantity"] = _cited(number)
    adapter, _ = _adapter(monkeypatch, payload)
    with pytest.raises(LiteParseExtractionError, match="invalid structured"):
        adapter.extract(tmp_path / "source.pdf", FIELDS)


def test_cloud_backed_ollama_model_never_receives_document_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, requests = _adapter(monkeypatch)
    original = adapter._request

    def request(route: str, body: dict | None = None) -> dict:
        response = original(route, body)
        response["models"][0]["remote_host"] = "https://example.invalid"
        return response

    monkeypatch.setattr(adapter, "_request", request)
    with pytest.raises(LiteParseExtractionError, match="cloud models"):
        adapter.extract(tmp_path / "source.pdf", FIELDS)
    assert [route for route, body in requests] == ["/api/tags"]


def test_overflowing_numeric_literal_is_not_valid_business_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, _ = _adapter(monkeypatch)
    original = adapter._request

    def request(route: str, body: dict | None = None) -> dict:
        response = original(route, body)
        if route == "/api/chat":
            response["message"]["content"] = json.dumps(_payload()).replace("2.5", "1e999")
        return response

    monkeypatch.setattr(adapter, "_request", request)
    with pytest.raises(LiteParseExtractionError, match="invalid structured"):
        adapter.extract(tmp_path / "source.pdf", FIELDS)


@pytest.mark.parametrize("options", [
    {"max_input_characters": 10}, {"num_ctx": 100, "num_predict": 10},
])
def test_oversized_input_is_not_silently_truncated_or_sent_to_ollama(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, options: dict,
) -> None:
    adapter, requests = _adapter(monkeypatch, **options)
    with pytest.raises(LiteParseExtractionError, match="exceeds"):
        adapter.extract(tmp_path / "source.pdf", FIELDS)
    assert requests == []


def test_invalid_model_json_is_rejected_without_leaking_customer_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    payload["reference"] = _cited({"private": "PRIVATE_PAYLOAD"})
    adapter, _ = _adapter(monkeypatch, payload)
    with pytest.raises(LiteParseExtractionError) as error:
        adapter.extract(tmp_path / "source.pdf", FIELDS)
    assert "PRIVATE_PAYLOAD" not in str(error.value)


def test_token_limit_response_is_a_failure_not_partial_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, _ = _adapter(monkeypatch)
    original = adapter._request
    monkeypatch.setattr(adapter, "_request", lambda route, body=None:
                        original(route, body) if route == "/api/tags" else
                        {"done": True, "done_reason": "length"})
    with pytest.raises(LiteParseExtractionError, match="token-limited"):
        adapter.extract(tmp_path / "source.pdf", FIELDS)


def test_runtime_and_config_checker_allow_local_fields_without_api_key() -> None:
    definition = {"tasks": {"local": {
        "module": "standard_step.extraction.liteparse_extract",
        "class": "LiteParseExtractTask", "params": {"fields": FIELDS},
    }}, "pipeline": ["local"]}
    assert validate_parameters(definition).errors == []
    definition["tasks"]["local"]["params"]["ollama_host"] = "http://remote"
    assert any(e.code == "param-liteparse-invalid-options"
               for e in validate_parameters(definition).errors)


def test_task_preserves_context_and_flags_without_a_review_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic")
    expected = {"reference": "0007"}
    result = LiteParseExtractionResult(expected, {"reference": {}}, {"provider": "liteparse_ollama"})
    monkeypatch.setattr(LiteParseOllamaAdapter, "extract", lambda *args: result)
    task = LiteParseExtractTask(TempConfig(tmp_path / "test.sqlite3"), fields={"reference": FIELDS["reference"]})
    context = {"file_path": str(pdf), "data": {"kept": True},
               "review_flags": ["existing"], "pipeline_version_id": "pinned"}
    assert task.run(context) is context
    assert context["data"] == {"kept": True, **expected}
    assert context["pipeline_version_id"] == "pinned"
    assert context["review_flags"][0] == "existing"
    assert context["review_flags"][1]["field_keys"] == ["reference"]
    assert "pipeline_state" not in context


def test_task_registers_redacted_errors_with_configured_task_key(tmp_path: Path) -> None:
    task = LiteParseExtractTask(TempConfig(tmp_path / "test.sqlite3"), fields=FIELDS)
    context = {"current_task_key": "configured_local"}
    with pytest.raises(TaskError):
        task.on_start(context)
    assert context["error_step"] == "configured_local"
    assert "readable" in context["error"]


def test_task_registers_provider_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic")

    def failed(*args: Any) -> None:
        raise LiteParseExtractionError("Local Ollama is unavailable or timed out.")

    monkeypatch.setattr(LiteParseOllamaAdapter, "extract", failed)
    task = LiteParseExtractTask(TempConfig(tmp_path / "test.sqlite3"), fields=FIELDS)
    context = {"file_path": str(pdf), "current_task_key": "local"}
    with pytest.raises(TaskError, match="unavailable"):
        task.run(context)
    assert context["error_step"] == "local"


def test_local_failure_messages_do_not_claim_a_cloud_provider() -> None:
    from modules.services.failure_service import _operator_failure_message

    run = {
        "task_key": "local_extract",
        "module_name": "standard_step.extraction.liteparse_extract",
        "class_name": "LiteParseExtractTask",
    }
    message = _operator_failure_message(run, "LiteParse could not parse the PDF.")
    assert message == "LiteParse could not parse the PDF."


@pytest.mark.parametrize("error_step", ["local", "earlier_task"])
def test_successful_retry_clears_only_its_own_registered_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_step: str,
) -> None:
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic")
    result = LiteParseExtractionResult({"reference": "0007"}, {"reference": {}}, {})
    monkeypatch.setattr(LiteParseOllamaAdapter, "extract", lambda *args: result)
    task = LiteParseExtractTask(
        TempConfig(tmp_path / "test.sqlite3"), fields={"reference": FIELDS["reference"]},
    )
    context = {"file_path": str(pdf), "current_task_key": "local",
               "error_step": error_step, "error": "Earlier failure"}
    task.run(context)
    if error_step == "local":
        assert context["error"] is None and context["error_step"] is None
    else:
        assert context["error"] == "Earlier failure"
        assert context["error_step"] == "earlier_task"
