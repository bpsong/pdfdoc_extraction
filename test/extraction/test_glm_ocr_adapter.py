"""Unit tests for the direct Ollama/GLM-OCR adapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pymupdf
import pytest

from standard_step.extraction.glm_ocr_adapter import (
    GlmOcrAdapter,
    GlmOcrModelNotFoundError,
    GlmOcrPdfError,
    GlmOcrResponseError,
    GlmOcrTimeoutError,
    GlmOcrUnavailableError,
)


def _fields() -> dict:
    return {
        "invoice_number": {
            "alias": "Invoice number",
            "type": "str",
        },
        "summary": {
            "alias": "Summary",
            "type": "Dict[str, Any]",
            "object_fields": {
                "currency": {"alias": "Currency", "type": "str"},
                "tax": {"alias": "Tax", "type": "Optional[float]"},
            },
        },
        "items": {
            "alias": "Items",
            "type": "List[Any]",
            "is_table": True,
            "item_fields": {
                "sku": {"alias": "SKU", "type": "str"},
                "quantity": {"alias": "Quantity", "type": "int"},
            },
        },
    }


def _make_pdf(path: Path, page_count: int = 1) -> Path:
    document = pymupdf.open()
    try:
        for page_number in range(1, page_count + 1):
            page = document.new_page()
            page.insert_text((72, 72), f"Synthetic invoice page {page_number}")
        document.save(path)
    finally:
        document.close()
    return path


def _response(data: dict, *, reason: str = "stop", done: bool = True) -> dict:
    return {
        "response": json.dumps(data),
        "done": done,
        "done_reason": reason,
    }


def _chat_response(
    data: dict,
    *,
    reason: str = "stop",
    done: bool = True,
) -> dict:
    return {
        "message": {"content": json.dumps(data)},
        "done": done,
        "done_reason": reason,
    }


def _client(*responses: dict) -> Mock:
    client = Mock()
    client.list.return_value = {"models": [{"model": "glm-ocr:latest"}]}
    client.generate.side_effect = list(responses)
    return client


def _adapter(client: Mock | None = None, **overrides) -> GlmOcrAdapter:
    values = {
        "ollama_host": "http://127.0.0.1:11434",
        "model": "glm-ocr:latest",
        "dpi": 144,
        "num_ctx": 4096,
        "num_predict": 1024,
        "timeout_seconds": 30,
        "client": client,
    }
    values.update(overrides)
    return GlmOcrAdapter(**values)


def test_one_page_mixed_requests_use_native_ollama_payloads(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "invoice.pdf")
    client = _client(
        _response(
            {
                "invoice_number": "000123",
                "summary": {"currency": "USD", "tax": 2.5},
            }
        ),
        _response({"items": [{"sku": "A01", "quantity": 2}]}),
    )

    result = _adapter(client).extract(
        str(pdf_path),
        _fields(),
        document_instructions="Read the billing invoice only.",
    )

    assert result.data == {
        "invoice_number": "000123",
        "summary": {"currency": "USD", "tax": 2.5},
        "items": [{"sku": "A01", "quantity": 2}],
    }
    assert result.page_count == 1
    assert result.field_pages == {
        "invoice_number": [1],
        "summary": [1],
        "items": [1],
    }
    assert [record.call_type for record in result.calls] == [
        "scalar_object",
        "table",
    ]
    assert [record.page_number for record in result.calls] == [1, 1]
    assert [record.completion_reason for record in result.calls] == ["stop", "stop"]
    assert all(record.duration_seconds >= 0 for record in result.calls)
    assert all(len(record.prompt_hash) == 64 for record in result.calls)
    assert all(len(record.schema_hash) == 64 for record in result.calls)

    scalar_request, table_request = [call.kwargs for call in client.generate.call_args_list]
    for request in (scalar_request, table_request):
        assert request["model"] == "glm-ocr:latest"
        assert request["stream"] is False
        assert request["options"] == {
            "temperature": 0,
            "num_ctx": 4096,
            "num_predict": 1024,
        }
        assert isinstance(request["format"], dict)
        assert request["format"]["additionalProperties"] is False
        assert len(request["images"]) == 1
        assert request["images"][0].startswith(b"\x89PNG")
    assert set(scalar_request["format"]["properties"]) == {
        "invoice_number",
        "summary",
    }
    assert set(table_request["format"]["properties"]) == {"items"}
    assert scalar_request["format"]["required"] == [
        "invoice_number",
        "summary",
    ]
    assert scalar_request["format"]["properties"]["invoice_number"]["type"] == [
        "string",
        "null",
    ]
    assert table_request["format"]["required"] == ["items"]
    assert table_request["format"]["properties"]["items"]["type"] == "array"
    assert "Read the billing invoice only." in scalar_request["prompt"]
    assert "Read the billing invoice only." in table_request["prompt"]


def test_compact_prompt_style_is_used_for_scalar_and_table_calls(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "invoice.pdf")
    client = _client(
        _response(
            {
                "invoice_number": "000123",
                "summary": {"currency": "USD", "tax": 2.5},
            }
        ),
        _response({"items": [{"sku": "A01", "quantity": 2}]}),
    )

    _adapter(client).extract(
        str(pdf_path),
        _fields(),
        document_instructions="Read the invoice.",
        prompt_style="compact",
    )

    scalar_request, table_request = [call.kwargs for call in client.generate.call_args_list]
    for request in (scalar_request, table_request):
        assert request["format"]["type"] == "object"
        assert "JSON Schema:" not in request["prompt"]
        assert "Read the invoice." in request["prompt"]


def test_multi_page_merges_objects_records_conflicts_and_deduplicates_rows(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "two-pages.pdf", page_count=2)
    client = _client(
        _response(
            {
                "invoice_number": "FIRST",
                "summary": {"currency": "USD", "tax": None},
            }
        ),
        _response(
            {
                "items": [
                    {"sku": "A", "quantity": 1},
                    {"sku": "B", "quantity": 2},
                ]
            }
        ),
        _response(
            {
                "invoice_number": "SECOND",
                "summary": {"currency": "USD", "tax": "3.50"},
            }
        ),
        _response(
            {
                "items": [
                    {"sku": "B", "quantity": "2"},
                    {"sku": "C", "quantity": 3},
                ]
            }
        ),
    )

    result = _adapter(client).extract(str(pdf_path), _fields())

    assert result.data == {
        "invoice_number": "FIRST",
        "summary": {"currency": "USD", "tax": 3.5},
        "items": [
            {"sku": "A", "quantity": 1},
            {"sku": "B", "quantity": 2},
            {"sku": "C", "quantity": 3},
        ],
    }
    assert result.field_pages == {
        "invoice_number": [1, 2],
        "summary": [1, 2],
        "items": [1, 2],
    }
    conflict_summary = [
        (item.path, item.retained_page, item.conflicting_page)
        for item in result.conflicts
    ]
    assert conflict_summary == [
        ("invoice_number", 1, 2)
    ]
    assert client.generate.call_count == 4


def test_document_mode_resolves_each_field_against_all_ordered_pages(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "resolved.pdf", page_count=2)
    client = _client(
        _response(
            {
                "invoice_number": "FIRST",
                "summary": {"currency": "USD", "tax": None},
            }
        ),
        _response({"items": [{"sku": "A", "quantity": 1}]}),
        _response(
            {
                "invoice_number": "SECOND",
                "summary": {"currency": "SGD", "tax": 3.5},
            }
        ),
        _response({"items": [{"sku": "B", "quantity": 2}]}),
    )
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.side_effect = [
        _chat_response({"value": "SECOND", "page_numbers": [2]}),
        _chat_response(
            {
                "value": {"currency": "SGD", "tax": 3.5},
                "page_numbers": [1, 2],
            }
        ),
        _chat_response(
            {
                "value": [
                    {"sku": "A", "quantity": 1},
                    {"sku": "B", "quantity": 2},
                ],
                "page_numbers": [1, 2],
            }
        ),
    ]

    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
        resolver_num_ctx=8192,
        resolver_num_predict=1536,
        resolver_max_attempts=2,
    ).extract(
        str(pdf_path),
        _fields(),
        document_instructions="Use the configured business roles.",
    )

    assert result.data == {
        "invoice_number": "SECOND",
        "summary": {"currency": "SGD", "tax": 3.5},
        "items": [
            {"sku": "A", "quantity": 1},
            {"sku": "B", "quantity": 2},
        ],
    }
    assert result.field_pages == {
        "invoice_number": [2],
        "summary": [1, 2],
        "items": [1, 2],
    }
    assert [record.call_type for record in result.calls[-3:]] == [
        "document_scalar",
        "document_object",
        "document_table",
    ]
    assert all(record.page_number is None for record in result.calls[-3:])
    assert client.chat.call_count == 3
    requests = [call.kwargs for call in client.chat.call_args_list]
    for request in requests:
        assert request["model"] == "qwen3.5:9b-q4_K_M"
        assert request["think"] is False
        assert request["stream"] is False
        assert request["options"] == {
            "temperature": 0,
            "num_ctx": 8192,
            "num_predict": 1536,
        }
        assert request["format"]["required"] == ["value", "page_numbers"]
        assert "Use the configured business roles." in request["messages"][0]["content"]
    for request in requests[:2]:
        assert len(request["messages"][0]["images"]) == 2
        for image in request["messages"][0]["images"]:
            pixmap = pymupdf.Pixmap(image)
            assert max(pixmap.width, pixmap.height) <= 1280
    assert "images" not in requests[2]["messages"][0]
    assert "No document images are supplied" in requests[2]["messages"][0]["content"]


def test_document_mode_retries_an_unresolved_required_field(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "resolver-retry.pdf")
    client = _client(_response({"invoice_number": "INV-7"}))
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.side_effect = [
        _chat_response({"value": None, "page_numbers": []}),
        _chat_response({"value": "INV-7", "page_numbers": [1]}),
    ]

    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
    ).extract(
        str(pdf_path),
        {"invoice_number": {"alias": "Invoice number", "type": "str"}},
    )

    assert result.data == {"invoice_number": "INV-7"}
    assert result.field_pages == {"invoice_number": [1]}
    assert client.chat.call_count == 2
    assert any(item.code == "resolver_retry" for item in result.findings)
    assert "independent retry" in client.chat.call_args_list[1].kwargs["messages"][0]["content"]


def test_document_mode_accepts_an_empty_required_table_without_retry(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "empty-resolved-table.pdf")
    client = _client(_response({"items": []}))
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
    ).extract(str(pdf_path), {"items": _fields()["items"]})

    assert result.data == {"items": []}
    assert result.field_pages == {"items": []}
    client.chat.assert_not_called()
    assert not any(item.code == "resolver_unresolved" for item in result.findings)


def test_document_mode_recovers_value_when_glm_has_no_candidate(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "image-recovery.pdf")
    client = _client(_response({"supplier_name": None}))
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.return_value = _chat_response(
        {"value": "Visible Issuer Ltd", "page_numbers": [1]}
    )

    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
    ).extract(
        str(pdf_path),
        {
            "supplier_name": {
                "alias": "Supplier name",
                "type": "Optional[str]",
            }
        },
    )

    assert result.data == {"supplier_name": "Visible Issuer Ltd"}
    assert result.field_pages == {"supplier_name": [1]}
    prompt = client.chat.call_args.kwargs["messages"][0]["content"]
    assert "Page-level candidate count: 0" in prompt


def test_document_mode_retries_schema_invalid_object_response(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "invalid-object.pdf")
    client = _client(
        _response({"summary": {"currency": "SGD", "tax": 2.5}})
    )
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.side_effect = [
        _chat_response({"value": {"tax": 2.5}, "page_numbers": [1]}),
        _chat_response(
            {
                "value": {"currency": "SGD", "tax": 2.5},
                "page_numbers": [1],
            }
        ),
    ]

    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
    ).extract(str(pdf_path), {"summary": _fields()["summary"]})

    assert result.data == {"summary": {"currency": "SGD", "tax": 2.5}}
    assert client.chat.call_count == 2
    assert any(item.code == "resolver_retry" for item in result.findings)
    assert not any(item.code.startswith("schema_") for item in result.findings)


def test_document_mode_exhausts_malformed_json_retries_safely(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "resolver-malformed.pdf")
    client = _client(_response({"name": "Acme"}))
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.side_effect = [
        {"message": {"content": "not-json"}, "done": True},
        {"message": {"content": "still-not-json"}, "done": True},
    ]

    with pytest.raises(GlmOcrResponseError, match="not valid JSON"):
        _adapter(
            client,
            resolution_mode="document",
            resolver_model="qwen3.5:9b-q4_K_M",
            resolver_max_attempts=2,
        ).extract(str(pdf_path), {"name": {"type": "str"}})

    assert client.chat.call_count == 2


def test_document_mode_retries_truncated_response_and_skips_optional_absence_retry(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "resolver-truncated.pdf")
    client = _client(_response({"note": None}))
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.side_effect = [
        _chat_response(
            {"value": None, "page_numbers": []},
            reason="length",
        ),
        _chat_response({"value": None, "page_numbers": []}),
    ]

    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
        resolver_max_attempts=2,
    ).extract(str(pdf_path), {"note": {"type": "Optional[str]"}})

    assert result.data == {"note": None}
    assert client.chat.call_count == 2
    assert sum(item.code == "resolver_retry" for item in result.findings) == 1


def test_document_mode_uses_candidate_page_when_citation_is_invalid(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "invalid-pages.pdf")
    client = _client(_response({"name": "Acme"}))
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.return_value = _chat_response(
        {"value": "Acme", "page_numbers": [2, 2]}
    )

    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
        resolver_max_attempts=1,
    ).extract(str(pdf_path), {"name": {"type": "str"}})

    assert result.data == {"name": "Acme"}
    assert result.field_pages == {"name": [1]}
    assert any(item.path == "name.page_numbers" for item in result.findings)


def test_document_mode_preserves_legitimate_duplicate_rows(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "duplicate-rows.pdf")
    row = {"sku": "A", "quantity": 1}
    client = _client(_response({"items": [row]}))
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.return_value = _chat_response(
        {"value": [row, row], "page_numbers": [1]}
    )

    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
    ).extract(str(pdf_path), {"items": _fields()["items"]})

    assert result.data == {"items": [row, row]}
    assert result.field_pages == {"items": [1]}
    message = client.chat.call_args.kwargs["messages"][0]
    assert "images" not in message
    assert "Structured candidate rows" in message["content"]


def test_document_table_reassigns_only_structured_candidate_cells(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "shifted-table.pdf")
    client = _client(
        _response(
            {
                "items": [
                    {
                        "sku": "Furniture, FUR-CH-4421",
                        "quantity": 1,
                        "__glm_ocr_row_evidence__": (
                            "Furniture | FUR-CH-4421 | 1"
                        ),
                    }
                ]
            }
        )
    )
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.return_value = _chat_response(
        {
            "value": [{"sku": "FUR-CH-4421", "quantity": 1}],
            "page_numbers": [1],
        }
    )

    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
    ).extract(str(pdf_path), {"items": _fields()["items"]})

    assert result.data == {
        "items": [{"sku": "FUR-CH-4421", "quantity": 1}]
    }
    request = client.chat.call_args.kwargs
    assert "images" not in request["messages"][0]
    assert "Furniture | FUR-CH-4421 | 1" in request["messages"][0]["content"]


def test_document_table_grounds_hallucinations_and_realigns_delimited_cells(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "delimited-table.pdf")
    table = {
        "alias": "Items",
        "type": "List[Any]",
        "is_table": True,
        "item_fields": {
            "product_name": {"alias": "Product", "type": "str"},
            "sub_category": {"alias": "Sub-category", "type": "str"},
            "category": {"alias": "Category", "type": "str"},
            "product_id": {"alias": "Product ID", "type": "str"},
            "quantity": {"alias": "Quantity", "type": "int"},
        },
    }
    client = _client(
        _response(
            {
                "items": [
                    {
                        "product_name": "Manager Chair, Indigo",
                        "sub_category": "Chairs, Furniture",
                        "category": "FUR-CH-4421",
                        "product_id": "ORDER-99",
                        "quantity": 1,
                    }
                ]
            }
        )
    )
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.return_value = _chat_response(
        {
            "value": [
                {
                    "product_name": "Unsupported footer",
                    "sub_category": "Chairs, Furniture",
                    "category": "FUR-CH-4421",
                    "product_id": "ORDER-99",
                    "quantity": 1,
                }
            ],
            "page_numbers": [1],
        }
    )

    result = _adapter(
        client,
        resolution_mode="document",
        resolver_model="qwen3.5:9b-q4_K_M",
    ).extract(str(pdf_path), {"items": table})

    assert result.data == {
        "items": [
            {
                "product_name": "Manager Chair, Indigo",
                "sub_category": "Chairs",
                "category": "Furniture",
                "product_id": "FUR-CH-4421",
                "quantity": 1,
            }
        ]
    }
    assert any(
        item.code == "table_evidence_realign" for item in result.findings
    )


def test_document_runtime_requires_both_configured_models(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "missing-resolver.pdf")
    client = _client()

    with pytest.raises(GlmOcrModelNotFoundError, match="resolver model"):
        _adapter(
            client,
            resolution_mode="document",
            resolver_model="qwen3.5:9b-q4_K_M",
        ).extract(str(pdf_path), {"name": {"type": "str"}})

    client.generate.assert_not_called()
    client.chat.assert_not_called()


def test_document_resolver_timeout_is_redacted_and_not_retried(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "resolver-timeout.pdf")
    client = _client(_response({"name": "Acme"}))
    client.list.return_value = {
        "models": [
            {"model": "glm-ocr:latest"},
            {"model": "qwen3.5:9b-q4_K_M"},
        ]
    }
    client.chat.side_effect = TimeoutError("private resolver endpoint")

    with pytest.raises(GlmOcrTimeoutError, match="document resolution") as exc:
        _adapter(
            client,
            resolution_mode="document",
            resolver_model="qwen3.5:9b-q4_K_M",
        ).extract(str(pdf_path), {"name": {"type": "str"}})

    assert "private resolver endpoint" not in str(exc.value)
    assert client.chat.call_count == 1


@pytest.mark.parametrize(
    ("fields", "response_data", "expected_type"),
    [
        (
            {"name": {"alias": "Name", "type": "str"}},
            {"name": "Acme"},
            "scalar_object",
        ),
        (
            {"items": _fields()["items"]},
            {"items": [{"sku": "A", "quantity": 1}]},
            "table",
        ),
    ],
)
def test_only_configured_call_category_runs(
    tmp_path: Path,
    fields: dict,
    response_data: dict,
    expected_type: str,
) -> None:
    pdf_path = _make_pdf(tmp_path / f"{expected_type}.pdf")
    client = _client(_response(response_data))

    result = _adapter(client).extract(str(pdf_path), fields)

    assert client.generate.call_count == 1
    assert [record.call_type for record in result.calls] == [expected_type]


def test_scalar_array_is_normalized_through_the_shared_field_contract(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "scalar-array.pdf")
    client = _client(_response({"Tags": [1, "02"]}))

    result = _adapter(client).extract(
        str(pdf_path),
        {"tags": {"alias": "Tags", "type": "Optional[List[str]]"}},
    )

    assert result.data == {"tags": ["1", "02"]}


def test_page_null_and_empty_table_are_valid_absence_values(tmp_path: Path) -> None:
    scalar_pdf = _make_pdf(tmp_path / "optional.pdf")
    scalar_result = _adapter(_client(_response({"note": None}))).extract(
        str(scalar_pdf),
        {"note": {"alias": "Note", "type": "Optional[str]"}},
    )

    assert scalar_result.data == {"note": None}
    assert scalar_result.field_pages == {"note": []}
    assert scalar_result.findings == []

    table_pdf = _make_pdf(tmp_path / "empty-table.pdf")
    table_result = _adapter(_client(_response({"items": []}))).extract(
        str(table_pdf),
        {"items": _fields()["items"]},
    )

    assert table_result.data == {"items": []}
    assert table_result.field_pages == {"items": []}
    assert table_result.findings == []


def test_client_factory_receives_host_and_timeout_and_accepts_latest_alias(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "factory.pdf")
    client = _client(_response({"name": "Acme"}))
    client.list.return_value = {"models": [{"name": "glm-ocr:latest"}]}
    factory = Mock(return_value=client)
    adapter = _adapter(
        None,
        model="glm-ocr",
        client_factory=factory,
    )

    adapter.extract(str(pdf_path), {"name": {"type": "str"}})

    factory.assert_called_once_with(
        host="http://127.0.0.1:11434",
        timeout=30,
    )


def test_service_unavailable_and_missing_model_are_safe(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "runtime.pdf")
    unavailable = Mock()
    unavailable.list.side_effect = ConnectionError("secret endpoint detail")
    with pytest.raises(GlmOcrUnavailableError, match="service validation") as exc:
        _adapter(unavailable).extract(
            str(pdf_path),
            {"name": {"type": "str"}},
        )
    assert "secret endpoint detail" not in str(exc.value)
    assert unavailable.list.call_count == 1

    missing = Mock()
    missing.list.return_value = {"models": [{"model": "another:latest"}]}
    with pytest.raises(GlmOcrModelNotFoundError, match="not installed"):
        _adapter(missing).extract(
            str(pdf_path),
            {"name": {"type": "str"}},
        )
    missing.generate.assert_not_called()


def test_timeout_malformed_json_and_truncation_fail_without_retry(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "response-errors.pdf")

    timeout_client = _client()
    timeout_client.generate.side_effect = TimeoutError("raw timeout detail")
    with pytest.raises(GlmOcrTimeoutError, match="model generation") as exc:
        _adapter(timeout_client).extract(
            str(pdf_path),
            {"name": {"type": "str"}},
        )
    assert "raw timeout detail" not in str(exc.value)
    assert timeout_client.generate.call_count == 1

    malformed = _client({"response": "not-json", "done": True})
    with pytest.raises(GlmOcrResponseError, match="not valid JSON"):
        _adapter(malformed).extract(
            str(pdf_path),
            {"name": {"type": "str"}},
        )
    assert malformed.generate.call_count == 1

    truncated = _client(_response({"name": "partial"}, reason="length"))
    with pytest.raises(GlmOcrResponseError, match="token limit"):
        _adapter(truncated).extract(
            str(pdf_path),
            {"name": {"type": "str"}},
        )
    assert truncated.generate.call_count == 1


def test_type_invalid_but_parseable_result_returns_partial_data_and_findings(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "invalid-value.pdf")
    client = _client(_response({"quantity": "not-a-number"}))

    result = _adapter(client).extract(
        str(pdf_path),
        {"quantity": {"alias": "Quantity", "type": "int"}},
    )

    assert result.data == {"quantity": "not-a-number"}
    assert any(item.code == "invalid_integer" for item in result.normalization_findings)
    assert any(item.code == "schema_type" for item in result.findings)
    assert all("not-a-number" not in item.message for item in result.findings)


def test_missing_value_is_preserved_as_none_with_final_schema_finding(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "missing-value.pdf")
    client = _client(
        _response({"invoice_number": None}),
        _response({"invoice_number": None}),
    )

    result = _adapter(client).extract(
        str(pdf_path),
        {"invoice_number": {"type": "str"}},
    )

    assert result.data == {"invoice_number": None}
    assert result.field_pages == {"invoice_number": []}
    assert any(item.code in {"schema_required", "schema_type"} for item in result.findings)
    assert [record.call_type for record in result.calls] == [
        "scalar_object",
        "scalar_recovery",
    ]


def test_required_null_value_gets_one_focused_recovery_pass(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "recovery.pdf")
    client = _client(
        _response({"invoice_number": None, "optional_note": None}),
        _response({"invoice_number": "000123"}),
    )

    result = _adapter(client).extract(
        str(pdf_path),
        {
            "invoice_number": {"alias": "Invoice #", "type": "str"},
            "optional_note": {"alias": "Note", "type": "Optional[str]"},
        },
    )

    assert result.data == {
        "invoice_number": "000123",
        "optional_note": None,
    }
    assert result.field_pages == {
        "invoice_number": [1],
        "optional_note": [],
    }
    assert [record.call_type for record in result.calls] == [
        "scalar_object",
        "scalar_recovery",
    ]
    recovery_request = client.generate.call_args_list[1].kwargs
    assert set(recovery_request["format"]["properties"]) == {"invoice_number"}
    assert "focused recovery pass" in recovery_request["prompt"]
    assert "optional_note" not in recovery_request["format"]["properties"]


def test_render_pdf_uses_normalized_path_and_returns_in_memory_pngs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = _make_pdf(tmp_path / "render.pdf", page_count=2)
    normalized = Mock(return_value=str(pdf_path))
    monkeypatch.setattr(
        "standard_step.extraction.glm_ocr_adapter.windows_long_path",
        normalized,
    )

    images = _adapter(Mock()).render_pdf(str(pdf_path))

    normalized.assert_called_once_with(str(pdf_path))
    assert len(images) == 2
    assert all(image.startswith(b"\x89PNG") for image in images)


def test_render_pdf_bounds_resolver_images_without_changing_ocr_dpi(
    tmp_path: Path,
) -> None:
    pdf_path = _make_pdf(tmp_path / "bounded-render.pdf")
    adapter = _adapter(Mock(), dpi=216, resolver_max_dimension=960)

    ocr_image = pymupdf.Pixmap(adapter.render_pdf(str(pdf_path))[0])
    resolver_image = pymupdf.Pixmap(
        adapter.render_pdf(str(pdf_path), max_dimension=960)[0]
    )

    assert max(ocr_image.width, ocr_image.height) > 960
    assert max(resolver_image.width, resolver_image.height) <= 960
    assert resolver_image.width < ocr_image.width
    assert resolver_image.height < ocr_image.height


def test_missing_and_invalid_pdf_raise_safe_errors(tmp_path: Path) -> None:
    adapter = _adapter(Mock())
    with pytest.raises(GlmOcrPdfError, match="does not exist"):
        adapter.render_pdf(str(tmp_path / "missing.pdf"))

    invalid_path = tmp_path / "invalid.pdf"
    invalid_path.write_bytes(b"not a pdf")
    with pytest.raises(GlmOcrPdfError, match="could not be opened") as exc:
        adapter.render_pdf(str(invalid_path))
    assert str(invalid_path) not in str(exc.value)


def test_pdf_document_closes_when_page_rendering_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = Mock()
    document.page_count = 1
    document.load_page.side_effect = RuntimeError("render detail")
    monkeypatch.setattr(
        "standard_step.extraction.glm_ocr_adapter.os.path.isfile",
        lambda _path: True,
    )
    monkeypatch.setattr(
        "standard_step.extraction.glm_ocr_adapter.pymupdf.open",
        Mock(return_value=document),
    )

    with pytest.raises(GlmOcrPdfError, match="could not be opened or rendered"):
        _adapter(Mock()).render_pdf("synthetic.pdf")

    document.close.assert_called_once_with()


def test_empty_and_unreadable_pdf_paths_fail_safely_and_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "standard_step.extraction.glm_ocr_adapter.os.path.isfile",
        lambda _path: True,
    )
    empty_document = Mock()
    empty_document.page_count = 0
    open_mock = Mock(return_value=empty_document)
    monkeypatch.setattr(
        "standard_step.extraction.glm_ocr_adapter.pymupdf.open",
        open_mock,
    )

    with pytest.raises(GlmOcrPdfError, match="no pages"):
        _adapter(Mock()).render_pdf("empty.pdf")
    empty_document.close.assert_called_once_with()

    open_mock.side_effect = PermissionError("private filesystem detail")
    with pytest.raises(GlmOcrPdfError, match="could not be opened") as exc:
        _adapter(Mock()).render_pdf("unreadable.pdf")
    assert "private filesystem detail" not in str(exc.value)
