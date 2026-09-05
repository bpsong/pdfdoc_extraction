"""Negative and helper-contract tests for GLM-OCR prompt construction."""

from __future__ import annotations

import pytest

from standard_step.extraction import glm_ocr_prompt as prompt


@pytest.mark.parametrize(
    "fields",
    [
        {"": {"type": "str"}},
        {"name": {"alias": 1, "type": "str"}},
        {"name": {"description": [], "type": "str"}},
        {"name": {"type": "List[Tuple[str]]"}},
        {"name": {"type": "str", "choices": []}},
        {"name": {"type": "str", "choices": ["yes", 1]}},
        {"name": {"type": "str", "choices": ["yes", "YES"]}},
        {"name": {"type": "int", "normalizer": "iso_date"}},
        {"name": {"type": "str", "item_fields": {"x": {"type": "str"}}}},
        {
            "name": {
                "type": "Dict[str, Any]",
                "object_fields": {"x": {"type": "str", "alias": 1}},
            }
        },
        {
            "name": {
                "type": "Dict[str, Any]",
                "object_fields": {"x": "bad"},
            }
        },
        {
            "name": {
                "type": "Dict[str, Any]",
                "object_fields": {"x": {"type": ""}},
            }
        },
        {
            "name": {
                "type": "Dict[str, Any]",
                "object_fields": {"x": {"type": "Dict[str, Any]"}},
            }
        },
        {
            "name": {
                "type": "List[Any]",
                "is_table": True,
                "item_fields": {"x": {"type": "str", "is_table": True}},
            }
        },
        {
            "name": {
                "type": "List[Any]",
                "is_table": True,
                "item_fields": {"x": {"type": "str", "object_fields": {}}},
            }
        },
        {
            "name": {
                "type": "List[Any]",
                "is_table": True,
                "item_fields": {"x": {"type": "str"}},
                "choices": ["x"],
            }
        },
        {
            "name": {
                "type": "List[Any]",
                "is_table": True,
                "item_fields": {"x": {"type": "str"}},
                "normalizer": "iso_date",
            }
        },
        {
            "name": {
                "type": "List[Any]",
                "is_table": True,
                "item_fields": {"x": {"type": "str"}},
                "object_fields": {},
            }
        },
    ],
)
def test_field_validation_rejects_ambiguous_definitions(fields: dict) -> None:
    with pytest.raises(ValueError):
        prompt.validate_glm_ocr_fields(fields)


def test_prompt_helpers_and_schema_mutators_cover_defensive_paths() -> None:
    with pytest.raises(ValueError, match="at least one field"):
        prompt.build_scalar_object_prompt({}, {})
    with pytest.raises(ValueError, match="non-empty item_fields"):
        prompt.build_table_prompt("items", {"type": "List[Any]", "is_table": True, "item_fields": {}}, {})

    assert prompt._ordered_glm_fields({"a": "invalid", "b": {"type": "str"}})["a"] == "invalid"
    schema = {"properties": {"x": {"type": "string", "enum": ["A"]}}}
    prompt._allow_null(schema["properties"]["x"])
    prompt._allow_null(schema["properties"]["x"])
    assert schema["properties"]["x"]["type"] == ["string", "null"]
    assert schema["properties"]["x"]["enum"] == ["A", None]
    prompt._allow_configured_optional_values({}, {})
    prompt._require_nullable_page_values({}, {})
    prompt._require_page_table({}, "missing", {})
    prompt._add_table_row_evidence({}, "missing")
    prompt._apply_glm_field_constraints({}, {})
    prompt._allow_configured_optional_values({"properties": []}, {})
    prompt._require_nullable_page_values({"properties": []}, {})
    prompt._require_page_table({"properties": []}, "items", {})
    prompt._require_page_table({"properties": {"items": []}}, "items", {})
    prompt._add_table_row_evidence({"properties": {"items": []}}, "items")
    prompt._add_table_row_evidence({"properties": {"items": {"items": []}}}, "items")
    prompt._add_table_row_evidence({"properties": {"items": {"items": {}}}}, "items")
    prompt._apply_glm_field_constraints(
        {"properties": {"x": [], "y": {}}}, {"x": "bad", "y": {"type": "str"}}
    )
    list_schema = {"type": ["string"]}
    prompt._allow_null(list_schema)
    assert list_schema["type"] == ["string", "null"]
    assert prompt._field_descriptor("name", {"type": "str"})["required"] is True
    assert prompt._resolver_field_descriptor("items", {"type": "List[Any]", "is_table": True})["key"] == "items"


@pytest.mark.parametrize("page_count", [0, -1])
def test_document_resolver_rejects_non_positive_page_count(page_count: int) -> None:
    with pytest.raises(ValueError, match="page_count"):
        prompt.build_document_resolver_schema("name", {"type": "str"}, page_count=page_count)


def test_resolver_and_table_prompt_reject_invalid_options_and_support_verbatim() -> None:
    field = {"type": "str", "alias": "Name"}
    with pytest.raises(ValueError, match="page_count"):
        prompt.build_document_resolver_prompt("name", field, [], page_count=0)
    with pytest.raises(ValueError, match="attempt_number"):
        prompt.build_document_resolver_prompt("name", field, [], page_count=1, attempt_number=0)
    table = {
        "type": "List[Any]",
        "is_table": True,
        "item_fields": {"name": {"type": "str"}},
    }
    with pytest.raises(ValueError, match="attempt_number"):
        prompt.build_table_evidence_resolver_prompt("items", table, [], page_count=1, attempt_number=0, image_page_numbers=[1])
    with pytest.raises(ValueError, match="page_count"):
        prompt.build_table_evidence_resolver_prompt("items", table, [], page_count=0, image_page_numbers=[1])
    with pytest.raises(ValueError, match="chunk position"):
        prompt.build_table_evidence_resolver_prompt("items", table, [], page_count=1, chunk_number=2, chunk_count=1, image_page_numbers=[1])
    with pytest.raises(ValueError, match="requires a table"):
        prompt.build_table_evidence_resolver_prompt("name", field, [], page_count=1, image_page_numbers=[1])
    assert prompt.build_table_prompt(
        "items", table, {}, document_instructions="Rows only.", prompt_style="verbatim"
    ) == "Rows only."
    document_table_prompt = prompt.build_document_resolver_prompt(
        "items", table, [], page_count=1
    )
    assert "complete logical table" in document_table_prompt
    with pytest.raises(ValueError, match="requires document instructions"):
        prompt.build_table_prompt("items", table, {}, prompt_style="verbatim")


def test_object_constraints_are_rejected_and_candidate_bounds_are_stable() -> None:
    with pytest.raises(ValueError, match="Object field"):
        prompt.validate_glm_ocr_fields(
            {"summary": {"type": "Dict[str, Any]", "choices": ["x"], "object_fields": {"name": {"type": "str"}}}}
        )
    assert prompt._bounded_candidate_evidence([], max_chars=1) == ("[]", "")
    encoded, note = prompt._bounded_candidate_evidence([{"value": "x" * 20}], max_chars=5)
    assert encoded == "[]"
    assert "inspect all page images" in note


def test_schema_mutators_skip_malformed_nested_properties() -> None:
    prompt._allow_configured_optional_values(
        {"properties": {"x": "bad"}}, {"x": {"type": "Optional[str]"}, "missing": {"type": "str"}}
    )
    prompt._require_nullable_page_values(
        {"properties": {"x": "bad"}}, {"x": {"type": "str"}, "missing": {"type": "str"}}
    )
    prompt._add_table_row_evidence(
        {"properties": {"items": {"items": {"properties": []}}}}, "items"
    )
    prompt._apply_glm_field_constraints(
        {"properties": {"x": "bad"}}, {"x": {"type": "str", "choices": ["x"]}}
    )
