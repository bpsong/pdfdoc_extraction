"""Tests for provider-neutral structured extraction field helpers."""

from decimal import Decimal
from typing import Any, Dict, List, Optional, get_args, get_origin

from standard_step.extraction.llama_cloud_v2 import (
    build_data_schema as llama_build_data_schema,
    parse_field_type as llama_parse_field_type,
)
from standard_step.extraction.structured_fields import (
    build_data_schema,
    normalize_configured_fields,
    parse_field_type,
)


def _mixed_fields() -> dict[str, Any]:
    return {
        "invoice_number": {
            "alias": "Invoice number",
            "description": "Identifier printed on the invoice",
            "type": "str",
        },
        "tags": {"alias": "Tags", "type": "Optional[List[str]]"},
        "summary": {
            "alias": "Summary",
            "type": "Dict[str, Any]",
            "object_fields": {
                "customer": {"alias": "Customer", "type": "str"},
                "note": {"alias": "Note", "type": "Optional[str]"},
            },
        },
        "items": {
            "alias": "Items",
            "type": "List[Any]",
            "is_table": True,
            "item_fields": {
                "sku": {"alias": "SKU", "type": "str"},
                "quantity": {"alias": "Quantity", "type": "int"},
                "discount": {"alias": "Discount", "type": "Optional[float]"},
            },
        },
    }


def test_independent_glm_schema_matches_existing_llama_contract() -> None:
    """The standalone GLM helper matches the existing LlamaCloud contract."""
    expected = {
        "type": "object",
        "properties": {
            "invoice_number": {
                "type": "string",
                "description": "Identifier printed on the invoice",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags",
            },
            "summary": {
                "type": "object",
                "properties": {
                    "customer": {"type": "string", "description": "Customer"},
                    "note": {"type": "string", "description": "Note"},
                },
                "required": ["customer"],
                "description": "Summary",
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string", "description": "SKU"},
                        "quantity": {
                            "type": "integer",
                            "description": "Quantity",
                        },
                        "discount": {
                            "type": "number",
                            "description": "Discount",
                        },
                    },
                    "required": ["sku", "quantity"],
                },
                "description": "Items",
            },
        },
        "required": ["invoice_number", "summary", "items"],
    }

    assert build_data_schema(_mixed_fields()) == expected
    assert llama_build_data_schema(_mixed_fields()) == expected
    assert "additionalProperties" not in expected


def test_strict_schema_closes_all_configured_objects() -> None:
    schema = build_data_schema(_mixed_fields(), strict_objects=True)

    assert schema["additionalProperties"] is False
    assert schema["properties"]["summary"]["additionalProperties"] is False
    assert (
        schema["properties"]["items"]["items"]["additionalProperties"]
        is False
    )


def test_page_schema_omits_only_top_level_required_properties() -> None:
    schema = build_data_schema(
        _mixed_fields(),
        strict_objects=True,
        include_required=False,
    )

    assert "required" not in schema
    assert schema["properties"]["summary"]["required"] == ["customer"]
    assert schema["properties"]["items"]["items"]["required"] == [
        "sku",
        "quantity",
    ]


def test_type_parser_supports_scalar_optional_list_object_and_table_types() -> None:
    assert parse_field_type("str") is str
    assert parse_field_type("Decimal") is Decimal
    optional = parse_field_type("Optional[int]")
    assert get_origin(optional) is not None and set(get_args(optional)) == {int, type(None)}
    scalar_list = parse_field_type("List[float]")
    assert get_origin(scalar_list) is list and get_args(scalar_list) == (float,)
    assert parse_field_type("Dict[str, Any]") == Dict[str, Any]
    object_array = parse_field_type("List[Dict[str, Any]]")
    assert get_origin(object_array) is list
    assert get_args(object_array) == (Dict[str, Any],)
    assert llama_parse_field_type("List[str]") == List[str]


def test_normalization_prefers_alias_and_cleans_object_and_table_newlines() -> None:
    result = normalize_configured_fields(
        {
            "invoice_number": "key-value",
            "Invoice number": "alias-value",
            "Summary": {"Customer": " Acme\n\nLtd "},
            "Items": [
                {"SKU": " A\n01 ", "Quantity": "2"},
                {"SKU": "B02", "Quantity": "bad"},
            ],
        },
        _mixed_fields(),
    )

    assert result.data == {
        "invoice_number": "alias-value",
        "summary": {"customer": "Acme Ltd"},
        "items": [
            {"sku": "A 01", "quantity": 2},
            {"sku": "B02", "quantity": "bad"},
        ],
    }
    assert [(item.path, item.code) for item in result.findings] == [
        ("items.1.quantity", "invalid_integer")
    ]


def test_normalization_can_preserve_missing_configured_keys() -> None:
    result = normalize_configured_fields(
        {"Summary": {}, "Items": [{}]},
        _mixed_fields(),
        include_missing=True,
    )

    assert result.data["invoice_number"] is None
    assert result.data["tags"] is None
    assert result.data["summary"] == {"customer": None, "note": None}
    assert result.data["items"] == [
        {"sku": None, "quantity": None, "discount": None}
    ]


def test_glm_constraints_normalize_dates_and_canonical_choice_tokens() -> None:
    fields = {
        "note_type": {
            "alias": "Note type",
            "type": "str",
            "choices": ["debit", "credit"],
        },
        "coverage": {
            "alias": "Coverage",
            "type": "Dict[str, Any]",
            "object_fields": {
                "start": {
                    "alias": "Start",
                    "type": "str",
                    "normalizer": "iso_date",
                },
                "end": {
                    "alias": "End",
                    "type": "str",
                    "normalizer": "iso_date",
                },
            },
        },
    }

    result = normalize_configured_fields(
        {
            "Note type": "Tax Invoice/Debit Note",
            "Coverage": {"Start": "25 NOV 2024", "End": "24/11/2026"},
        },
        fields,
    )

    assert result.data == {
        "note_type": "debit",
        "coverage": {"start": "2024-11-25", "end": "2026-11-24"},
    }
    assert result.findings == []


def test_invalid_date_and_ambiguous_choice_remain_reviewable() -> None:
    result = normalize_configured_fields(
        {"Date": "late November", "Type": "debit / credit"},
        {
            "date": {
                "alias": "Date",
                "type": "str",
                "normalizer": "iso_date",
            },
            "type": {
                "alias": "Type",
                "type": "str",
                "choices": ["debit", "credit"],
            },
        },
    )

    assert result.data == {"date": "late November", "type": "debit / credit"}
    assert [(item.path, item.code) for item in result.findings] == [
        ("date", "invalid_iso_date"),
        ("type", "invalid_choice"),
    ]
