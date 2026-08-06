"""Tests for dynamic GLM-OCR schema and prompt generation."""

import json

import pytest

from standard_step.extraction.glm_ocr_prompt import (
    build_glm_ocr_schemas,
    build_scalar_object_prompt,
    build_table_prompt,
    validate_glm_ocr_fields,
)


def _mixed_fields() -> dict:
    return {
        "invoice_number": {
            "alias": "Invoice #",
            "description": "Keep leading zeros",
            "type": "str",
        },
        "optional_note": {
            "alias": "Note",
            "description": "Café \"备注\"",
            "type": "Optional[str]",
        },
        "tags": {
            "alias": "Tags",
            "description": "Visible category labels",
            "type": "Optional[List[str]]",
        },
        "summary": {
            "alias": "Summary",
            "type": "Dict[str, Any]",
            "object_fields": {
                "currency": {"alias": "Currency", "type": "str"},
                "tax": {"alias": "Tax", "type": "Optional[float]"},
            },
        },
        "line_items": {
            "alias": "Line items",
            "description": "Product rows",
            "type": "List[Any]",
            "is_table": True,
            "item_fields": {
                "sku": {"alias": "Product ID", "type": "str"},
                "quantity": {"alias": "Qty", "type": "int"},
                "amount": {"alias": "Amount", "type": "float"},
                "note": {"alias": "Note", "type": "Optional[str]"},
            },
        },
    }


def test_mixed_schemas_are_strict_partitioned_and_deterministic() -> None:
    first = build_glm_ocr_schemas(_mixed_fields())
    second = build_glm_ocr_schemas(_mixed_fields())

    assert first == second
    assert first.table_field_key == "line_items"
    assert set(first.scalar_fields) == {
        "invoice_number",
        "optional_note",
        "tags",
        "summary",
    }
    assert first.canonical_schema["required"] == [
        "invoice_number",
        "summary",
        "line_items",
    ]
    assert first.canonical_schema["additionalProperties"] is False
    assert first.scalar_page_schema is not None
    assert first.table_page_schema is not None
    assert first.scalar_page_schema["required"] == [
        "invoice_number",
        "optional_note",
        "tags",
        "summary",
    ]
    assert first.table_page_schema["required"] == ["line_items"]
    scalar_properties = first.scalar_page_schema["properties"]
    assert scalar_properties["invoice_number"]["type"] == ["string", "null"]
    assert scalar_properties["optional_note"]["type"] == ["string", "null"]
    assert scalar_properties["tags"]["type"] == ["array", "null"]
    assert scalar_properties["summary"]["type"] == ["object", "null"]
    assert first.scalar_page_schema["properties"]["summary"]["required"] == [
        "currency",
        "tax",
    ]
    assert scalar_properties["summary"]["properties"]["currency"]["type"] == [
        "string",
        "null",
    ]
    assert scalar_properties["summary"]["properties"]["tax"]["type"] == [
        "number",
        "null",
    ]
    row_schema = first.table_page_schema["properties"]["line_items"]["items"]
    assert row_schema["required"] == ["sku", "quantity", "amount", "note"]
    assert all(
        "null" in row_schema["properties"][key]["type"]
        for key in ("sku", "quantity", "amount", "note")
    )
    assert row_schema["additionalProperties"] is False
    canonical_properties = first.canonical_schema["properties"]
    assert canonical_properties["invoice_number"]["type"] == "string"
    assert canonical_properties["optional_note"]["type"] == ["string", "null"]
    assert canonical_properties["summary"]["properties"]["currency"]["type"] == (
        "string"
    )
    assert canonical_properties["summary"]["properties"]["tax"]["type"] == [
        "number",
        "null",
    ]


@pytest.mark.parametrize(
    ("fields", "has_scalar", "has_table"),
    [
        ({"name": {"alias": "Name", "type": "str"}}, True, False),
        (
            {
                "summary": {
                    "type": "Dict[str, Any]",
                    "object_fields": {"count": {"type": "int"}},
                }
            },
            True,
            False,
        ),
        (
            {"line_items": _mixed_fields()["line_items"]},
            False,
            True,
        ),
        (_mixed_fields(), True, True),
    ],
)
def test_scalar_object_table_and_mixed_partitions(
    fields: dict,
    has_scalar: bool,
    has_table: bool,
) -> None:
    bundle = build_glm_ocr_schemas(fields)

    assert (bundle.scalar_page_schema is not None) is has_scalar
    assert (bundle.table_page_schema is not None) is has_table


def test_scalar_prompt_contains_contract_unicode_and_escaped_guidance() -> None:
    bundle = build_glm_ocr_schemas(_mixed_fields())
    assert bundle.scalar_page_schema is not None
    prompt = build_scalar_object_prompt(
        bundle.scalar_fields,
        bundle.scalar_page_schema,
        document_instructions='Use label "发票".\nDo not use CUSTOMER_RUNTIME_987.',
    )

    assert prompt == build_scalar_object_prompt(
        bundle.scalar_fields,
        bundle.scalar_page_schema,
        document_instructions='Use label "发票".\nDo not use CUSTOMER_RUNTIME_987.',
    )
    assert '"key":"invoice_number"' in prompt
    assert '"alias":"Invoice #"' in prompt
    assert '"type":"str"' in prompt
    assert '"required":true' in prompt
    assert "Café" in prompt and "备注" in prompt and "发票" in prompt
    assert "leading zeros" in prompt
    assert "currency symbols or thousands separators" in prompt
    assert "Do not invent" in prompt
    assert "Return every configured top-level field exactly once" in prompt
    assert "Use JSON null" in prompt
    assert "do not omit its key" in prompt
    assert "Omit a top-level field" not in prompt
    schema_text = json.dumps(
        bundle.scalar_page_schema,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert schema_text in prompt


def test_scalar_recovery_prompt_is_focused_without_changing_schema() -> None:
    fields = {"invoice_number": _mixed_fields()["invoice_number"]}
    bundle = build_glm_ocr_schemas(fields)
    assert bundle.scalar_page_schema is not None

    prompt = build_scalar_object_prompt(
        fields,
        bundle.scalar_page_schema,
        recovery_pass=True,
    )

    assert "focused recovery pass" in prompt
    assert "Search the complete page carefully before returning JSON null" in prompt
    assert '"invoice_number"' in prompt


def test_table_prompt_keeps_key_and_row_integrity_rules() -> None:
    bundle = build_glm_ocr_schemas(_mixed_fields())
    assert bundle.table_field_key is not None
    assert bundle.table_field is not None
    assert bundle.table_page_schema is not None
    prompt = build_table_prompt(
        bundle.table_field_key,
        bundle.table_field,
        bundle.table_page_schema,
        document_instructions="Only product rows.",
    )

    assert '"line_items"' in prompt
    assert '"key":"sku"' in prompt
    assert '"key":"quantity"' in prompt
    assert "one JSON object per logical visual row" in prompt
    assert "same visual row" in prompt
    assert "Always return the top-level table property" in prompt
    assert "return an empty array" in prompt
    assert "omit the top-level table property" not in prompt
    for excluded in ("headers", "footers", "subtotals", "blank rows", "duplicate rows"):
        assert excluded in prompt
    assert "Only product rows." in prompt


def test_prompts_do_not_gain_runtime_document_values() -> None:
    bundle = build_glm_ocr_schemas(_mixed_fields())
    assert bundle.scalar_page_schema is not None
    assert bundle.table_field_key is not None
    assert bundle.table_field is not None
    assert bundle.table_page_schema is not None
    runtime_value = "SECRET_INVOICE_RUNTIME_VALUE_731"
    scalar_prompt = build_scalar_object_prompt(
        bundle.scalar_fields,
        bundle.scalar_page_schema,
    )
    table_prompt = build_table_prompt(
        bundle.table_field_key,
        bundle.table_field,
        bundle.table_page_schema,
    )

    assert runtime_value not in scalar_prompt
    assert runtime_value not in table_prompt


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({}, "non-empty"),
        ({"name": "str"}, "must be an object"),
        ({"name": {"alias": "Name"}}, "non-empty type"),
        ({"name": {"type": "Tuple[str]"}}, "unsupported type"),
        (
            {"summary": {"type": "Dict[str, Any]", "object_fields": {}}},
            "non-empty object_fields",
        ),
        (
            {
                "summary": {
                    "type": "str",
                    "object_fields": {"name": {"type": "str"}},
                }
            },
            "must use type 'Dict[str, Any]'",
        ),
        (
            {
                "items": {
                    "type": "List[str]",
                    "is_table": True,
                    "item_fields": {"name": {"type": "str"}},
                }
            },
            "must use type 'List[Any]'",
        ),
        (
            {
                "items": {
                    "type": "List[Any]",
                    "is_table": True,
                    "item_fields": {},
                }
            },
            "non-empty item_fields",
        ),
        (
            {
                "items": _mixed_fields()["line_items"],
                "fees": {
                    **_mixed_fields()["line_items"],
                    "alias": "Fees",
                },
            },
            "at most one table",
        ),
    ],
)
def test_malformed_or_unsupported_definitions_are_rejected(
    fields: dict,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        validate_glm_ocr_fields(fields)
