"""Deterministic schema and prompt generation for local GLM-OCR extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from standard_step.extraction.structured_fields import (
    build_data_schema,
    has_object_fields,
    is_optional_type,
    unwrap_optional,
)


SUPPORTED_SCALAR_TYPES = {"str", "int", "float", "bool", "Decimal", "Any"}


@dataclass(frozen=True, slots=True)
class GlmOcrSchemaBundle:
    """Schemas and field partitions needed for page-oriented extraction."""

    canonical_schema: dict[str, Any]
    scalar_page_schema: dict[str, Any] | None
    table_page_schema: dict[str, Any] | None
    scalar_fields: dict[str, Any]
    table_field_key: str | None
    table_field: dict[str, Any] | None


def build_glm_ocr_schemas(fields: dict[str, Any]) -> GlmOcrSchemaBundle:
    """Validate configured fields and build strict final/page schemas."""
    validate_glm_ocr_fields(fields)
    scalar_fields = {
        key: config
        for key, config in fields.items()
        if not config.get("is_table", False)
    }
    table_entries = [
        (key, config)
        for key, config in fields.items()
        if config.get("is_table", False)
    ]
    table_key, table_field = table_entries[0] if table_entries else (None, None)

    scalar_schema = (
        build_data_schema(
            scalar_fields,
            strict_objects=True,
            include_required=False,
        )
        if scalar_fields
        else None
    )
    table_schema = (
        build_data_schema(
            {table_key: table_field},
            strict_objects=True,
            include_required=False,
        )
        if table_key is not None and table_field is not None
        else None
    )
    return GlmOcrSchemaBundle(
        canonical_schema=build_data_schema(fields, strict_objects=True),
        scalar_page_schema=scalar_schema,
        table_page_schema=table_schema,
        scalar_fields=scalar_fields,
        table_field_key=table_key,
        table_field=table_field,
    )


def validate_glm_ocr_fields(fields: Any) -> None:
    """Reject unsupported or ambiguous visual field definitions."""
    if not isinstance(fields, dict) or not fields:
        raise ValueError("GLM-OCR fields must be a non-empty object")

    table_count = 0
    for field_key, field_config in fields.items():
        _validate_field_key(field_key, "top-level")
        if not isinstance(field_config, dict):
            raise ValueError(f"Field '{field_key}' must be an object")
        _validate_text_metadata(field_key, field_config)
        field_type = field_config.get("type")
        if not isinstance(field_type, str) or not field_type.strip():
            raise ValueError(f"Field '{field_key}' must have a non-empty type")

        if field_config.get("is_table", False):
            table_count += 1
            if table_count > 1:
                raise ValueError("GLM-OCR supports at most one table field")
            if unwrap_optional(field_type.strip()) != "List[Any]":
                raise ValueError(
                    f"Table field '{field_key}' must use type 'List[Any]'"
                )
            _validate_children(field_key, field_config.get("item_fields"), "item")
            if "object_fields" in field_config:
                raise ValueError(
                    f"Table field '{field_key}' cannot define object_fields"
                )
            continue

        if has_object_fields(field_config):
            _validate_children(
                field_key,
                field_config.get("object_fields"),
                "object",
            )
            continue
        if "object_fields" in field_config:
            raise ValueError(
                f"Field '{field_key}' with object_fields must use type 'Dict[str, Any]'"
            )
        if "item_fields" in field_config:
            raise ValueError(
                f"Non-table field '{field_key}' cannot define item_fields"
            )
        _validate_supported_type(field_type, f"Field '{field_key}'")


def build_scalar_object_prompt(
    fields: dict[str, Any],
    schema: dict[str, Any],
    *,
    document_instructions: str = "",
) -> str:
    """Build a stable prompt for one page's scalar and object fields."""
    if not fields:
        raise ValueError("Scalar/object prompt requires at least one field")
    field_lines = [_describe_field(key, config) for key, config in fields.items()]
    instructions = document_instructions.strip() or "None."
    return "\n".join(
        [
            "Extract configured scalar and object values from this single PDF page.",
            "Return exactly one JSON object matching the supplied JSON Schema.",
            "Use the configured field keys as JSON keys; aliases only identify "
            "labels in the document.",
            "Do not invent, infer, or copy a value when it is not visibly "
            "supported on this page.",
            "Omit a top-level field that is absent on this page.",
            "Preserve leading zeros for fields whose configured type is string.",
            "For numeric fields, return JSON numbers without currency symbols "
            "or thousands separators.",
            "Do not include commentary, Markdown, code fences, or properties "
            "outside the schema.",
            f"Document instructions: {instructions}",
            "Configured fields:",
            *field_lines,
            "JSON Schema:",
            _stable_json(schema),
        ]
    )


def build_table_prompt(
    table_field_key: str,
    table_field: dict[str, Any],
    schema: dict[str, Any],
    *,
    document_instructions: str = "",
) -> str:
    """Build a stable prompt for one page's configured logical table."""
    validate_glm_ocr_fields({table_field_key: table_field})
    item_fields = table_field["item_fields"]
    item_lines = [
        _describe_field(key, config, prefix="row field")
        for key, config in item_fields.items()
    ]
    table_descriptor = _field_descriptor(table_field_key, table_field)
    instructions = document_instructions.strip() or "None."
    return "\n".join(
        [
            "Extract the configured logical table from this single PDF page.",
            "The response property must remain exactly "
            f"{json.dumps(table_field_key, ensure_ascii=False)}.",
            "Return one JSON object per logical visual row in that property's array.",
            "Keep values observed on the same visual row together in the same object.",
            "Exclude headers, footers, subtotals, totals, blank rows, and "
            "duplicate rows unless the configured guidance explicitly says "
            "otherwise.",
            "Do not invent, infer, or copy values that are not visibly "
            "supported in a row.",
            "Preserve leading zeros for row fields whose configured type is string.",
            "For numeric row fields, return JSON numbers without currency "
            "symbols or thousands separators.",
            "When no logical rows are visible, omit the top-level table property.",
            "Do not include commentary, Markdown, code fences, or properties outside the schema.",
            f"Document instructions: {instructions}",
            f"Table: {_stable_json(table_descriptor)}",
            "Configured row fields:",
            *item_lines,
            "JSON Schema:",
            _stable_json(schema),
        ]
    )


def _validate_children(parent_key: str, children: Any, kind: str) -> None:
    if not isinstance(children, dict) or not children:
        raise ValueError(
            f"Field '{parent_key}' must define non-empty {kind}_fields"
        )
    for child_key, child_config in children.items():
        _validate_field_key(child_key, f"{kind} child")
        if not isinstance(child_config, dict):
            raise ValueError(
                f"Child '{parent_key}.{child_key}' must be an object"
            )
        _validate_text_metadata(f"{parent_key}.{child_key}", child_config)
        child_type = child_config.get("type")
        if not isinstance(child_type, str) or not child_type.strip():
            raise ValueError(
                f"Child '{parent_key}.{child_key}' must have a non-empty type"
            )
        if (
            child_config.get("is_table")
            or "item_fields" in child_config
            or "object_fields" in child_config
        ):
            raise ValueError(
                f"Nested structured child '{parent_key}.{child_key}' is not supported"
            )
        _validate_supported_type(child_type, f"Child '{parent_key}.{child_key}'")


def _validate_field_key(field_key: Any, location: str) -> None:
    if not isinstance(field_key, str) or not field_key.strip():
        raise ValueError(f"Every {location} field key must be a non-empty string")


def _validate_text_metadata(field_key: str, config: dict[str, Any]) -> None:
    for property_name in ("alias", "description"):
        value = config.get(property_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(
                f"Field '{field_key}' {property_name} must be a string"
            )


def _validate_supported_type(type_value: str, location: str) -> None:
    clean_type = unwrap_optional(type_value.strip())
    if clean_type.startswith("List[") and clean_type.endswith("]"):
        inner = clean_type[5:-1].strip()
        if inner not in SUPPORTED_SCALAR_TYPES:
            raise ValueError(f"{location} has unsupported type '{type_value}'")
        return
    if clean_type in SUPPORTED_SCALAR_TYPES:
        return
    raise ValueError(f"{location} has unsupported type '{type_value}'")


def _describe_field(
    field_key: str,
    field_config: dict[str, Any],
    *,
    prefix: str = "field",
) -> str:
    descriptor = _field_descriptor(field_key, field_config)
    if has_object_fields(field_config):
        descriptor["children"] = [
            _field_descriptor(key, config)
            for key, config in field_config["object_fields"].items()
        ]
    return f"- {prefix}: {_stable_json(descriptor)}"


def _field_descriptor(
    field_key: str,
    field_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "alias": str(field_config.get("alias", field_key)),
        "description": str(field_config.get("description", "")),
        "key": field_key,
        "required": not is_optional_type(str(field_config.get("type", "str"))),
        "type": str(field_config.get("type", "str")),
    }


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
