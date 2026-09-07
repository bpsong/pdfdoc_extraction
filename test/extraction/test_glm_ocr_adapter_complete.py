"""Low-level adapter contract tests for validation and evidence helpers."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from standard_step.extraction import glm_ocr_adapter as adapter
from standard_step.extraction.glm_ocr_prompt import build_glm_ocr_schemas


def _adapter(**overrides) -> adapter.GlmOcrAdapter:
    values = {
        "ollama_host": "http://127.0.0.1:11434",
        "model": "glm-ocr:latest",
        "client": Mock(),
    }
    values.update(overrides)
    return adapter.GlmOcrAdapter(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"dpi": 0},
        {"num_ctx": 0},
        {"num_predict": 0},
        {"resolver_max_attempts": 6},
        {"resolver_max_dimension": 255},
        {"ollama_host": ""},
        {"model": ""},
        {"resolution_mode": "document", "resolver_model": ""},
    ],
)
def test_adapter_constructor_rejects_invalid_runtime_settings(overrides) -> None:
    with pytest.raises(ValueError):
        _adapter(**overrides)


def test_runtime_validation_and_client_creation_cover_model_shapes() -> None:
    client = Mock()
    client.list.return_value = SimpleNamespace(models=[{"name": "glm-ocr:latest"}, {"model": "other"}])
    instance = _adapter(client=client)
    assert instance._get_client() is client
    instance._validate_runtime(client)
    client.list.return_value = {"models": [{"name": "other"}]}
    with pytest.raises(adapter.GlmOcrModelNotFoundError):
        instance._validate_runtime(client)
    document = _adapter(client=client, resolution_mode="document", resolver_model="resolver")
    client.list.return_value = {"models": [{"model": "glm-ocr:latest"}]}
    with pytest.raises(adapter.GlmOcrModelNotFoundError):
        document._validate_runtime(client)


@pytest.mark.parametrize(
    "response",
    [
        {"done": False, "response": "{}"},
        {"done_reason": "length", "response": "{}"},
        {"done": True, "response": ""},
        {"done": True, "response": "not json"},
        {"done": True, "response": "[]"},
    ],
)
def test_generate_response_protocol_errors(response) -> None:
    client = Mock()
    client.generate.return_value = response
    with pytest.raises(adapter.GlmOcrResponseError):
        _adapter(client=client)._call_model(
            client, page_number=1, call_type="scalar", image_bytes=b"x",
            prompt="prompt", schema={"type": "object"},
        )


def test_generate_and_resolver_call_records_and_safe_exceptions() -> None:
    client = Mock()
    client.generate.return_value = {"done": True, "done_reason": "stop", "response": json.dumps({"x": 1})}
    value, record = _adapter(client=client)._call_model(
        client, page_number=2, call_type="scalar", image_bytes=b"x",
        prompt="prompt", schema={"type": "object"},
    )
    assert value == {"x": 1}
    assert record.page_number == 2
    client.chat.return_value = {"done": True, "message": {"content": '{"value": 1}'}}
    document = _adapter(client=client, resolution_mode="document", resolver_model="resolver")
    value, record = document._call_resolver_model(
        client, call_type="resolver", image_bytes=[], prompt="prompt", schema={"type": "object"}
    )
    assert value == {"value": 1}
    assert record.page_number is None
    client.chat.return_value = {"done": True, "message": {"content": "[]"}}
    with pytest.raises(adapter.GlmOcrResponseError):
        document._call_resolver_model(client, call_type="resolver", image_bytes=[], prompt="p", schema={})
    client.chat.side_effect = TimeoutError()
    with pytest.raises(adapter.GlmOcrTimeoutError):
        document._call_resolver_model(client, call_type="resolver", image_bytes=[], prompt="p", schema={})
    client.chat.side_effect = None
    client.chat.return_value = {"done": True, "message": {}}
    with pytest.raises(adapter.GlmOcrResponseError, match="empty or invalid"):
        document._call_resolver_model(client, call_type="resolver", image_bytes=[], prompt="p", schema={})


def test_evidence_helpers_cover_deduplication_chunking_and_grounding() -> None:
    candidates = []
    adapter._add_candidate(candidates, 1, {"a": 1}, evidence_text="a")
    adapter._add_candidate(candidates, 1, {"a": 1}, evidence_text="duplicate")
    assert len(candidates) == 1
    adapter._add_candidate(candidates, 2, {"a": 2})
    assert adapter._candidate_page_numbers(candidates + [{"page_number": True}, {"page_number": 0}]) == [1, 2]
    assert len(adapter._table_candidate_chunks(candidates, max_chars=10)) == 2
    assert adapter._valid_page_numbers([1, 2, True, 0, 3], page_count=2) == [1, 2]
    assert adapter._valid_page_numbers("bad", page_count=2) == []
    assert adapter._candidate_pages_for_value(candidates, {"a": 1}) == [1]
    assert adapter._candidate_pages_for_value(candidates, [{"a": 1}], table_rows=True) == [1]
    assert adapter._required_resolver_value_missing(None, {"type": "List[Any]"})
    assert not adapter._required_resolver_value_missing([], {"type": "List[Any]"})
    assert adapter._required_resolver_value_missing("", {"type": "str"})
    assert adapter._required_resolver_value_missing(None, {"type": "Optional[List[str]]"})
    assert adapter._model_name(SimpleNamespace(name="model")) == "model"
    assert adapter._model_name({}) is None
    assert adapter._model_names_match("glm-ocr", "glm-ocr:latest")
    assert not adapter._model_names_match("glm-ocr:custom", "glm-ocr:latest")

    field_config = {
        "item_fields": {
            "description": {"type": "str"},
            "code": {"type": "str"},
            "quantity": {"type": "int"},
        }
    }
    rows, repaired = adapter._ground_table_rows(
        [{"description": "wrong", "code": None, "quantity": 99}],
        [{"value": {"description": "A, B", "code": "A, B", "quantity": 2}}],
        field_config,
    )
    assert repaired == [0]
    assert rows[0]["quantity"] == 2
    assert adapter._ground_table_rows([], [], {}) == ([], [])
    assert adapter._ground_table_rows(
        [{"first": "a", "source": "b", "target": "c"}],
        [{"value": {"first": "a", "source": "b", "target": "c"}}],
        {"item_fields": {"first": {"type": "str"}, "source": {"type": "str"}, "target": {"type": "str"}}},
    )[1] == []
    assert adapter._ground_table_rows(
        [{"first": "a", "source": "x,y", "target": "y"}],
        [{"value": {"first": "a", "source": "x,y", "target": 3}}],
        {"item_fields": {"first": {"type": "str"}, "source": {"type": "str"}, "target": {"type": "str"}}},
    )[1] == [0]
    assert adapter._ground_table_rows(
        [{"first": "a", "source": "x,", "target": "", "last": ""}],
        [{"value": {"first": "a", "source": "x,", "target": "", "last": ""}}],
        {"item_fields": {"first": {"type": "str"}, "source": {"type": "str"}, "target": {"type": "str"}, "last": {"type": "str"}}},
    )[1] == []
    assert adapter._is_text_field({"type": "Optional[str]"})
    assert not adapter._is_text_field({"type": "int"})


def test_merge_helpers_cover_empty_schema_and_missing_object_values() -> None:
    schemas = build_glm_ocr_schemas({"name": {"type": "str"}})
    merged = {"summary": "not-an-object"}
    field_pages = {"name": []}
    object_pages = {}
    candidates = {"name": []}
    findings = []
    adapter.GlmOcrAdapter._merge_scalar_fields(
        {"name": "value", "missing": "ignored"}, schemas, 1, merged,
        {}, object_pages, field_pages, findings, [], candidates,
    )
    assert merged["name"] == "value"
    empty_schemas = build_glm_ocr_schemas({"name": {"type": "str"}})
    empty_schemas = empty_schemas.__class__(
        canonical_schema=empty_schemas.canonical_schema,
        scalar_page_schema=empty_schemas.scalar_page_schema,
        table_page_schema=empty_schemas.table_page_schema,
        scalar_fields=empty_schemas.scalar_fields,
        table_field_key=None,
        table_field=None,
    )
    adapter.GlmOcrAdapter._merge_table_field(
        {}, empty_schemas, 1, {}, {}, set(), [], {}
    )
    adapter.GlmOcrAdapter._merge_scalar_fields(
        {}, schemas, 1, {}, {}, {}, {"name": []}, [], [], {"name": []}
    )
    object_schemas = build_glm_ocr_schemas(
        {"details": {"type": "Dict[str, Any]", "object_fields": {"name": {"type": "str"}}}}
    )
    merged_object = {"details": "legacy"}
    adapter.GlmOcrAdapter._merge_scalar_fields(
        {"details": {"name": "new"}}, object_schemas, 1, merged_object,
        {}, {}, {"details": []}, [], [], {"details": []},
    )
    assert merged_object["details"]["name"] == "new"
    assert adapter._missing_required_scalar_fields(
        {"summary": {"alias": "Summary"}},
        {"summary": {"type": "Dict[str, Any]", "object_fields": {"name": {"type": "str"}}}},
    )
    assert adapter._missing_required_object_child({}, {"name": {"type": "str"}})


def test_render_pdf_validates_arguments_and_safe_value_helpers(tmp_path) -> None:
    instance = _adapter()
    with pytest.raises(adapter.GlmOcrPdfError, match="path"):
        instance.render_pdf("")
    with pytest.raises(adapter.GlmOcrPdfError, match="does not exist"):
        instance.render_pdf("missing.pdf")
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"not-a-pdf")
    with pytest.raises(adapter.GlmOcrPdfError, match="maximum dimension"):
        instance.render_pdf(str(pdf), max_dimension=0)
    assert adapter._has_value(0)
    assert not adapter._has_value(None)
    assert adapter._values_equal({"a": 1}, {"a": 1})


def _call_record(call_type: str = "resolver") -> adapter.GlmOcrCallRecord:
    return adapter.GlmOcrCallRecord(
        page_number=None,
        call_type=call_type,
        duration_seconds=0.0,
        completion_reason="stop",
        prompt_hash="prompt",
        schema_hash="schema",
    )


def test_document_resolver_field_retry_missing_pages_and_defensive_exits() -> None:
    instance = _adapter(resolution_mode="document", resolver_model="resolver")
    instance.resolver_max_attempts = 2
    instance._call_resolver_model = Mock(
        side_effect=[
            adapter.GlmOcrResponseError("invalid"),
            ({"value": "invoice", "page_numbers": []}, _call_record()),
        ]
    )
    instance.resolver_max_attempts = 2
    findings = []
    resolved, pages = instance._resolve_document_fields(
        Mock(),
        page_images=[b"page"],
        page_count=1,
        fields={"invoice_number": {"type": "str"}},
        candidates={"invoice_number": []},
        document_instructions="",
        calls=[],
        findings=findings,
        normalization_findings=[],
    )
    assert resolved["invoice_number"] == "invoice"
    assert pages["invoice_number"] == []
    assert any(item.code == "resolver_missing_pages" for item in findings)

    instance._call_resolver_model = Mock(
        side_effect=[
            ({"value": None, "page_numbers": []}, _call_record()),
            ({"value": None, "page_numbers": []}, _call_record()),
        ]
    )
    instance.resolver_max_attempts = 2
    findings = []
    instance._resolve_document_fields(
        Mock(),
        page_images=[b"page"],
        page_count=1,
        fields={"required": {"type": "str"}},
        candidates={"required": []},
        document_instructions="",
        calls=[],
        findings=findings,
        normalization_findings=[],
    )
    assert any(item.code == "resolver_unresolved" for item in findings)

    instance.resolver_max_attempts = 0
    with pytest.raises(adapter.GlmOcrResponseError, match="no parseable"):
        instance._resolve_document_fields(
            Mock(), page_images=[b"page"], page_count=1,
            fields={"value": {"type": "str"}}, candidates={"value": []},
            document_instructions="", calls=[], findings=[], normalization_findings=[],
        )


def test_extract_handles_empty_pages_and_unbuildable_recovery_schema(monkeypatch) -> None:
    instance = _adapter()
    instance._validate_runtime = Mock()
    instance.render_pdf = Mock(return_value=[])
    with pytest.raises(adapter.GlmOcrResponseError, match="no parseable"):
        instance.extract("source.pdf", {"optional": {"type": "Optional[str]"}})

    fields = {"required": {"type": "str"}}
    instance.render_pdf = Mock(return_value=[b"page"])
    instance._call_model = Mock(return_value=({}, _call_record("scalar_object")))
    original_builder = adapter.build_glm_ocr_schemas
    recovery_bundle = adapter.GlmOcrSchemaBundle(
        canonical_schema={},
        scalar_page_schema=None,
        table_page_schema=None,
        scalar_fields=fields,
        table_field_key=None,
        table_field=None,
    )
    calls = 0

    def build_bundle(value):
        nonlocal calls
        calls += 1
        return original_builder(value) if calls == 1 else recovery_bundle

    monkeypatch.setattr(adapter, "build_glm_ocr_schemas", build_bundle)
    with pytest.raises(adapter.GlmOcrResponseError, match="recovery schema"):
        instance.extract("source.pdf", fields)

    monkeypatch.setattr(adapter, "build_glm_ocr_schemas", original_builder)
    instance = _adapter(resolution_mode="document", resolver_model="resolver")
    instance._validate_runtime = Mock()
    instance.render_pdf = Mock(side_effect=[[b"page"], [b"page", b"extra"]])
    instance._call_model = Mock(return_value=({"optional": "value"}, _call_record("scalar_object")))
    with pytest.raises(adapter.GlmOcrPdfError, match="match the source"):
        instance.extract("source.pdf", {"optional": {"type": "Optional[str]"}})


def test_document_resolver_table_retry_split_and_page_fallbacks() -> None:
    table_config = {
        "type": "List[Any]",
        "is_table": True,
        "item_fields": {"name": {"type": "str"}},
    }
    valid = ({"value": [{"name": "A"}], "page_numbers": []}, _call_record("document_table"))

    instance = _adapter(resolution_mode="document", resolver_model="resolver")
    instance._call_resolver_model = Mock(
        side_effect=[adapter.GlmOcrTokenLimitError("limit"), valid, valid]
    )
    findings = []
    rows, pages = instance._resolve_document_table(
        Mock(), page_images=[b"page"], field_key="items", field_config=table_config,
        candidates=[{"page_number": 1, "value": {"name": "A"}}, {"page_number": 1, "value": {"name": "B"}}],
        page_count=1, document_instructions="", calls=[], findings=findings,
        normalization_findings=[],
    )
    assert rows and pages == [1]
    assert any(item.code == "resolver_chunk_split" for item in findings)

    for error in (adapter.GlmOcrTokenLimitError("limit"), adapter.GlmOcrResponseError("bad")):
        instance.resolver_max_attempts = 2
        instance._call_resolver_model = Mock(side_effect=[error, valid])
        findings = []
        rows, pages = instance._resolve_document_table(
            Mock(), page_images=[b"page"], field_key="items", field_config=table_config,
            candidates=[{"page_number": 1, "value": {"name": "A"}}], page_count=1,
            document_instructions="", calls=[], findings=findings, normalization_findings=[],
        )
        assert rows and pages == [1]
        assert any(item.code == "resolver_retry" for item in findings)

    for error in (adapter.GlmOcrTokenLimitError("limit"), adapter.GlmOcrResponseError("bad")):
        instance.resolver_max_attempts = 1
        instance._call_resolver_model = Mock(side_effect=error)
        with pytest.raises(adapter.GlmOcrResponseError):
            instance._resolve_document_table(
                Mock(), page_images=[b"page"], field_key="items", field_config=table_config,
                candidates=[{"page_number": 1, "value": {"name": "A"}}], page_count=1,
                document_instructions="", calls=[], findings=[], normalization_findings=[],
            )

    instance._call_resolver_model = Mock(
        side_effect=[
            ({"value": None, "page_numbers": []}, _call_record("document_table")),
            valid,
        ]
    )
    instance.resolver_max_attempts = 2
    findings = []
    instance._resolve_document_table(
        Mock(), page_images=[b"page"], field_key="items", field_config=table_config,
        candidates=[{"page_number": 1, "value": {"name": "A"}}], page_count=1,
        document_instructions="", calls=[], findings=findings, normalization_findings=[],
    )
    assert any(item.code == "resolver_retry" for item in findings)

    instance.resolver_max_attempts = 0
    with pytest.raises(adapter.GlmOcrResponseError, match="no parseable"):
        instance._resolve_document_table(
            Mock(), page_images=[b"page"], field_key="items", field_config=table_config,
            candidates=[{"page_number": 1, "value": {"name": "A"}}], page_count=1,
            document_instructions="", calls=[], findings=[], normalization_findings=[],
        )
    with pytest.raises(adapter.GlmOcrResponseError, match="page images"):
        instance._resolve_document_table(
            Mock(), page_images=[], field_key="items", field_config=table_config,
            candidates=[{"page_number": 1, "value": {"name": "A"}}], page_count=1,
            document_instructions="", calls=[], findings=[], normalization_findings=[],
        )
# pyright: reportArgumentType=false
