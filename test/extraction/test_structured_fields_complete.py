"""Focused coverage for provider-neutral structured-field helpers."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

from standard_step.extraction.structured_fields import (
    build_data_schema,
    coerce_value,
    get_extracted_value,
    has_object_fields,
    is_optional_type,
    normalize_configured_fields,
    normalize_primitive_field,
    normalize_scalar_field,
    normalize_table_field,
    parse_field_type,
    schema_for_type,
    unwrap_optional,
)


def test_type_parsing_and_schema_variants() -> None:
    assert parse_field_type(" Optional[List[int]] ")
    assert parse_field_type("dict")
    assert parse_field_type("not-a-type") is object or parse_field_type("not-a-type") is not None
    assert schema_for_type("Optional[List[int]]") == {
        "type": "array",
        "items": {"type": "integer"},
    }
    assert schema_for_type("Dict[str, Any]", strict_objects=True) == {
        "type": "object",
        "additionalProperties": False,
    }
    assert schema_for_type("List[Decimal]") == {"type": "array", "items": {"type": "number"}}
    assert "ignored" not in build_data_schema({"obj": {"type": "Dict[str, Any]", "object_fields": {"ignored": "bad"}}})["properties"]["obj"]["properties"]
    assert unwrap_optional("Optional[Optional[str]]") == "str"
    assert is_optional_type("Optional[str]")
    assert not is_optional_type("str")


def test_build_data_schema_handles_scalar_object_table_and_invalid_entries() -> None:
    fields = {
        "supplier": {"type": "str", "alias": "Supplier"},
        "amount": {"type": "Optional[float]"},
        "details": {
            "type": "Dict[str, Any]",
            "object_fields": {"code": {"type": "int", "description": "Code"}},
        },
        "items": {
            "is_table": True,
            "item_fields": {"name": {"type": "str"}},
        },
        "ignored": "not a field definition",
    }
    schema = build_data_schema(fields, strict_objects=True)
    assert schema["required"] == ["supplier", "details", "items"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["supplier"]["description"] == "Supplier"
    assert schema["properties"]["details"]["properties"]["code"]["description"] == "Code"
    assert has_object_fields(fields["details"])
    assert not has_object_fields({"type": "Dict[str, Any]", "object_fields": []})


def test_extracted_value_and_coercion_error_paths() -> None:
    assert get_extracted_value({"Alias": 1}, "key", "Alias") == (True, 1)
    assert get_extracted_value({"key": 2}, "key", "Alias") == (True, 2)
    assert get_extracted_value({}, "key", "Alias") == (False, None)
    assert coerce_value(None, "int") is None
    assert coerce_value("4.9", "int") == 4
    assert coerce_value("false", "bool") is False
    assert coerce_value("yes", "bool") is True
    assert coerce_value("1.2", "float") == 1.2
    assert coerce_value("2.5", "Decimal") == Decimal("2.5")
    assert coerce_value("x", "unknown") == "x"
    findings = []
    assert coerce_value("bad", "int", path="amount", findings=findings) == "bad"
    assert findings[-1].code == "invalid_integer"
    findings.clear()
    assert coerce_value("bad", "float", path="amount", findings=findings) == "bad"
    assert findings[-1].code == "conversion_failed"
    logger = Mock()
    assert coerce_value("bad", "int", logger=logger, path="amount") == "bad"
    logger.warning.assert_called()


def test_collection_coercion_and_malformed_types() -> None:
    assert coerce_value(["1", None], "Optional[List[int]]") == [1]
    assert coerce_value("not-list", "List[int]") == "not-list"
    findings = []
    assert coerce_value(["1"], "List[", findings=findings) == ["1"]
    assert findings[-1].code == "malformed_type"
    assert coerce_value({"1": "2"}, "Dict[str, int]") == {"1": 2}
    findings = []
    assert coerce_value({"1": "2"}, "Dict[int]", findings=findings) == {"1": "2"}
    assert findings[-1].code == "malformed_type"
    assert coerce_value("not-dict", "Dict[str, int]") == "not-dict"
    findings = []
    assert coerce_value({}, "Dict[", findings=findings) == {}
    assert findings[-1].code == "malformed_type"
    findings = []
    assert coerce_value("x", "Tuple[int]", findings=findings) == "x"
    assert findings[-1].code == "unknown_type"


def test_normalization_handles_dates_choices_objects_tables_and_missing_values() -> None:
    findings = []
    assert normalize_primitive_field(
        "  01 Jan 2024  ",
        {"type": "str", "normalizer": "iso_date", "choices": ["Yes", "No"]},
        path="date",
        findings=findings,
    ) == "2024-01-01"
    assert normalize_primitive_field(
        "maybe", {"type": "str", "choices": ["Yes", "No"]}, findings=findings
    ) == "maybe"
    assert findings[-1].code == "invalid_choice"
    assert normalize_primitive_field(
        10, {"type": "int", "normalizer": "iso_date"}, findings=findings
    ) == 10
    assert findings[-1].code == "invalid_iso_date"

    config = {
        "name": {"alias": "Name", "type": "str"},
        "count": {"type": "int"},
        "bad": "ignored",
    }
    result = normalize_configured_fields(
        {"Name": "  Alice\nSmith ", "count": "3"}, config, include_missing=True
    )
    assert result.data == {"name": "  Alice\nSmith ", "count": 3}
    assert normalize_scalar_field(
        {"Name": "A"}, {"type": "Dict[str, Any]", "object_fields": config}, include_missing=True
    )["name"] == "A"
    assert normalize_scalar_field("not-an-object", {"type": "Dict[str, Any]", "object_fields": config}) == "not-an-object"
    assert normalize_primitive_field(None, {"type": "str"}) is None

    table_config = {
        "is_table": True,
        "item_fields": {"amount": {"type": "float"}, "name": {"type": "str"}},
    }
    table_findings = []
    assert normalize_table_field({}, "items", "Items", table_config, include_missing=True) is None
    assert normalize_table_field(
        {"Items": "bad"}, "items", "Items", table_config, findings=table_findings
    ) == []
    assert table_findings[-1].code == "invalid_table"
    table_findings.clear()
    rows = normalize_table_field(
        {"items": [{"amount": "2.5", "name": " A\nB "}, "bad", {}]},
        "items", "Items", table_config, findings=table_findings, include_missing=True,
    )
    assert rows == [{"amount": 2.5, "name": "A B"}, {"amount": None, "name": None}]
    assert any(item.code == "invalid_table_item" for item in table_findings)
    assert normalize_table_field(
        {"items": [{"name": "x", "amount": 1}]},
        "items", "Items", {"item_fields": {"ignored": "bad", "name": {"type": "str"}}},
    ) == [{"name": "x"}]
    logger = Mock()
    logged_findings = []
    assert normalize_table_field(
        {"Items": "bad"}, "items", "Items", table_config,
        logger=logger, findings=logged_findings,
    ) == []
    logger.warning.assert_called()


def test_date_and_choice_normalizers_cover_exact_and_invalid_matches() -> None:
    logger = Mock()
    findings = []
    assert normalize_primitive_field(
        "not-a-date", {"type": "str", "normalizer": "iso_date"},
        logger=logger, findings=findings,
    ) == "not-a-date"
    assert normalize_primitive_field(
        "yes", {"type": "str", "choices": ["Yes", "No"]}, findings=findings
    ) == "Yes"
    assert normalize_primitive_field(
        "yes or no", {"type": "str", "choices": ["Yes", "No"]},
        logger=logger, findings=findings,
    ) == "yes or no"
    assert logger.warning.call_count >= 2
