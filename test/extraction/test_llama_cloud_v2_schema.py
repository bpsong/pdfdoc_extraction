"""Tests for LlamaCloud Extract v2 schema generation."""

from standard_step.extraction.llama_cloud_v2 import build_data_schema


def test_build_data_schema_marks_only_non_optional_fields_required() -> None:
    """Required JSON schema fields follow the configured Optional wrapper."""
    schema = build_data_schema(
        {
            "invoice_number": {"alias": "Invoice number", "type": "str"},
            "purchase_order": {
                "alias": "Purchase order",
                "type": "Optional[str]",
            },
        }
    )

    assert schema["required"] == ["invoice_number"]
    assert schema["properties"]["purchase_order"]["type"] == "string"


def test_build_data_schema_marks_table_columns_required() -> None:
    """Table item schemas carry required state for each configured column."""
    schema = build_data_schema(
        {
            "items": {
                "alias": "Items",
                "type": "List[Any]",
                "is_table": True,
                "item_fields": {
                    "description": {"alias": "Description", "type": "str"},
                    "quantity": {"alias": "Quantity", "type": "int"},
                    "is_credit": {"alias": "Is credit", "type": "bool"},
                    "discount": {
                        "alias": "Discount",
                        "type": "Optional[float]",
                    },
                },
            }
        }
    )

    assert schema["required"] == ["items"]
    item_schema = schema["properties"]["items"]["items"]
    assert item_schema["required"] == ["description", "quantity", "is_credit"]
    assert item_schema["properties"]["quantity"]["type"] == "integer"
    assert item_schema["properties"]["is_credit"]["type"] == "boolean"


def test_build_data_schema_omits_empty_required_lists() -> None:
    """Schemas with only optional fields do not emit empty required arrays."""
    schema = build_data_schema(
        {"notes": {"alias": "Notes", "type": "Optional[str]"}}
    )

    assert "required" not in schema
