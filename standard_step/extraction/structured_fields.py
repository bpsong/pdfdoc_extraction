"""Provider-neutral structured extraction schema and normalization helpers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass(frozen=True, slots=True)
class FieldNormalizationFinding:
    """Describe one non-fatal configured-field normalization problem."""

    path: str
    code: str
    message: str


@dataclass(slots=True)
class NormalizedFieldsResult:
    """Normalized configured values plus reviewable conversion findings."""

    data: dict[str, Any]
    findings: list[FieldNormalizationFinding] = field(default_factory=list)


def parse_field_type(type_str: str) -> Any:
    """Convert a configured extraction type string to a Python annotation."""
    clean_type = type_str.strip()
    if clean_type.startswith("Optional[") and clean_type.endswith("]"):
        return Optional[parse_field_type(clean_type[9:-1])]
    if clean_type.startswith("List[") and clean_type.endswith("]"):
        return List[parse_field_type(clean_type[5:-1])]
    if clean_type in {"Dict[str, Any]", "dict"}:
        return Dict[str, Any]

    return {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "Decimal": Decimal,
        "Any": Any,
    }.get(clean_type, Any)


def build_data_schema(
    fields: dict[str, Any],
    *,
    strict_objects: bool = False,
    include_required: bool = True,
) -> dict[str, Any]:
    """Build JSON Schema from configured workflow fields.

    The defaults deliberately preserve the existing LlamaCloud schema shape.
    GLM-OCR callers can opt into strict objects and page-level schemas without
    top-level required properties.
    """
    properties: dict[str, Any] = {}
    required_fields: list[str] = []

    for field_key, field_config in fields.items():
        if not isinstance(field_config, dict):
            continue

        if field_config.get("is_table", False):
            properties[field_key] = build_table_schema(
                field_config,
                strict_objects=strict_objects,
            )
        elif has_object_fields(field_config):
            properties[field_key] = build_object_schema(
                field_config,
                strict_objects=strict_objects,
            )
        else:
            properties[field_key] = schema_for_type(
                str(field_config.get("type", "str")),
                strict_objects=strict_objects,
            )

        description = field_config.get("description") or field_config.get("alias")
        if description:
            properties[field_key]["description"] = str(description)

        if include_required and not is_optional_type(
            str(field_config.get("type", "str"))
        ):
            required_fields.append(str(field_key))

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if strict_objects:
        schema["additionalProperties"] = False
    if required_fields:
        schema["required"] = required_fields
    return schema


def build_table_schema(
    field_config: dict[str, Any],
    *,
    strict_objects: bool = False,
) -> dict[str, Any]:
    """Build an array-of-configured-objects schema."""
    return {
        "type": "array",
        "items": schema_for_configured_fields(
            field_config.get("item_fields", {}),
            strict_objects=strict_objects,
        ),
    }


def build_object_schema(
    field_config: dict[str, Any],
    *,
    strict_objects: bool = False,
) -> dict[str, Any]:
    """Build a typed object schema from configured child fields."""
    return schema_for_configured_fields(
        field_config.get("object_fields", {}),
        strict_objects=strict_objects,
    )


def schema_for_configured_fields(
    fields: Any,
    *,
    strict_objects: bool = False,
) -> dict[str, Any]:
    """Build a flat object schema from extraction-style field definitions."""
    item_properties: dict[str, Any] = {}
    required_items: list[str] = []

    configured_fields = fields if isinstance(fields, dict) else {}
    for item_key, item_config in configured_fields.items():
        if not isinstance(item_config, dict):
            continue
        item_properties[item_key] = schema_for_type(
            str(item_config.get("type", "str")),
            strict_objects=strict_objects,
        )
        description = item_config.get("description") or item_config.get("alias")
        if description:
            item_properties[item_key]["description"] = str(description)

        if not is_optional_type(str(item_config.get("type", "str"))):
            required_items.append(str(item_key))

    item_schema: dict[str, Any] = {
        "type": "object",
        "properties": item_properties,
    }
    if strict_objects:
        item_schema["additionalProperties"] = False
    if required_items:
        item_schema["required"] = required_items
    return item_schema


def has_object_fields(field_config: dict[str, Any]) -> bool:
    """Return whether a field defines a structured object payload."""
    clean_type = unwrap_optional(str(field_config.get("type", "str")).strip())
    return clean_type == "Dict[str, Any]" and isinstance(
        field_config.get("object_fields"), dict
    )


def schema_for_type(
    type_str: str,
    *,
    strict_objects: bool = False,
) -> dict[str, Any]:
    """Translate one configured type string into JSON Schema."""
    clean_type = unwrap_optional(type_str.strip())

    if clean_type.startswith("List[") and clean_type.endswith("]"):
        inner_type = clean_type[5:-1].strip()
        return {
            "type": "array",
            "items": schema_for_type(inner_type, strict_objects=strict_objects),
        }

    if clean_type.startswith("Dict[") or clean_type == "dict":
        result: dict[str, Any] = {"type": "object"}
        if strict_objects:
            result["additionalProperties"] = False
        return result

    type_mapping = {
        "str": "string",
        "float": "number",
        "Decimal": "number",
        "int": "integer",
        "bool": "boolean",
        "Any": "string",
    }
    return {"type": type_mapping.get(clean_type, "string")}


def unwrap_optional(type_str: str) -> str:
    """Remove all configured Optional wrappers."""
    clean_type = type_str
    while clean_type.startswith("Optional[") and clean_type.endswith("]"):
        clean_type = clean_type[9:-1].strip()
    return clean_type


def is_optional_type(type_str: str) -> bool:
    """Return whether a configured field type may be omitted."""
    clean_type = str(type_str).strip()
    return clean_type.startswith("Optional[") and clean_type.endswith("]")


def get_extracted_value(
    data: dict[str, Any],
    field_key: str,
    alias: str,
) -> tuple[bool, Any]:
    """Return a value by display alias first, then workflow field key."""
    if alias in data:
        return True, data[alias]
    if field_key in data:
        return True, data[field_key]
    return False, None


def coerce_value(
    value: Any,
    type_str: str,
    *,
    logger: logging.Logger | None = None,
    path: str = "",
    findings: list[FieldNormalizationFinding] | None = None,
) -> Any:
    """Coerce a value with the existing extraction task's loose semantics."""
    target_findings = findings if findings is not None else []
    if value is None:
        return None

    inner_type = type_str
    is_optional = False
    if inner_type.startswith("Optional[") and inner_type.endswith("]"):
        is_optional = True
        inner_type = inner_type[9:-1]

    def record(code: str, message: str) -> None:
        target_findings.append(
            FieldNormalizationFinding(path=path, code=code, message=message)
        )
        if logger:
            logger.warning("%s at %s", message, path or "<root>")

    def bool_coerce(item: Any) -> bool:
        if isinstance(item, str) and item.lower() in {
            "false",
            "f",
            "no",
            "0",
            "off",
        }:
            return False
        return bool(item)

    def int_coerce(item: Any) -> Any:
        try:
            return int(float(item))
        except (TypeError, ValueError):
            record("invalid_integer", "Value could not be converted to int")
            return item

    conversion_table = {
        "str": str,
        "float": float,
        "int": int_coerce,
        "bool": bool_coerce,
        "Decimal": Decimal,
    }

    if "[" not in inner_type and "{" not in inner_type:
        converter = conversion_table.get(inner_type)
        if converter is None:
            record("unknown_type", f"Unknown configured type: {inner_type}")
            return value
        try:
            return converter(value)
        except (TypeError, ValueError, ArithmeticError):
            record(
                "conversion_failed",
                f"Value could not be converted to {inner_type}",
            )
            return value

    if inner_type.startswith("List["):
        if not isinstance(value, list):
            return value
        if not inner_type.endswith("]"):
            record("malformed_type", f"Malformed List type: {inner_type}")
            return value
        list_content = inner_type[5:-1]
        processed_list = []
        for index, item in enumerate(value):
            if item is None and is_optional:
                continue
            processed_list.append(
                coerce_value(
                    item,
                    list_content,
                    logger=logger,
                    path=_join_path(path, str(index)),
                    findings=target_findings,
                )
            )
        return processed_list

    if inner_type.startswith("Dict["):
        if not isinstance(value, dict):
            return value
        if not inner_type.endswith("]"):
            record("malformed_type", f"Malformed Dict type: {inner_type}")
            return value
        dict_content = inner_type[5:-1]
        parts = [part.strip() for part in dict_content.split(",")]
        if len(parts) != 2:
            record("malformed_type", f"Malformed Dict type: {inner_type}")
            return value
        key_type, value_type = parts
        return {
            coerce_value(
                key,
                key_type,
                logger=logger,
                path=_join_path(path, str(key)),
                findings=target_findings,
            ): coerce_value(
                item,
                value_type,
                logger=logger,
                path=_join_path(path, str(key)),
                findings=target_findings,
            )
            for key, item in value.items()
        }

    record("unknown_type", f"Unknown configured type: {inner_type}")
    return value


def normalize_configured_object(
    value: Any,
    configured_fields: dict[str, Any],
    *,
    logger: logging.Logger | None = None,
    path: str = "",
    findings: list[FieldNormalizationFinding] | None = None,
    include_missing: bool = False,
) -> Any:
    """Normalize a flat object using configured child keys and types."""
    if not isinstance(value, dict):
        return value
    target_findings = findings if findings is not None else []
    processed: dict[str, Any] = {}
    for child_key, child_config in configured_fields.items():
        if not isinstance(child_config, dict):
            continue
        child_alias = str(child_config.get("alias", child_key))
        found, child_value = get_extracted_value(value, str(child_key), child_alias)
        if not found:
            if include_missing:
                processed[str(child_key)] = None
            continue
        if isinstance(child_value, str):
            child_value = re.sub(r"\n+", " ", child_value.strip())
        processed[str(child_key)] = normalize_primitive_field(
            child_value,
            child_config,
            logger=logger,
            path=_join_path(path, str(child_key)),
            findings=target_findings,
        )
    return processed


def normalize_scalar_field(
    value: Any,
    field_config: dict[str, Any],
    *,
    logger: logging.Logger | None = None,
    path: str = "",
    findings: list[FieldNormalizationFinding] | None = None,
    include_missing: bool = False,
) -> Any:
    """Normalize one scalar or configured flat object field."""
    field_type = str(field_config.get("type", "str"))
    if unwrap_optional(field_type) == "Dict[str, Any]" and isinstance(
        field_config.get("object_fields"), dict
    ):
        return normalize_configured_object(
            value,
            field_config["object_fields"],
            logger=logger,
            path=path,
            findings=findings,
            include_missing=include_missing,
        )
    return normalize_primitive_field(
        value,
        field_config,
        logger=logger,
        path=path,
        findings=findings,
    )


def normalize_primitive_field(
    value: Any,
    field_config: dict[str, Any],
    *,
    logger: logging.Logger | None = None,
    path: str = "",
    findings: list[FieldNormalizationFinding] | None = None,
) -> Any:
    """Coerce one primitive value and apply configured deterministic rules."""
    target_findings = findings if findings is not None else []
    normalized = coerce_value(
        value,
        str(field_config.get("type", "str")),
        logger=logger,
        path=path,
        findings=target_findings,
    )
    if normalized is None:
        return None

    normalizer = field_config.get("normalizer")
    if normalizer == "iso_date":
        normalized = _normalize_iso_date(
            normalized,
            logger=logger,
            path=path,
            findings=target_findings,
        )

    choices = field_config.get("choices")
    if isinstance(normalized, str) and isinstance(choices, list):
        normalized = _normalize_choice(
            normalized,
            choices,
            logger=logger,
            path=path,
            findings=target_findings,
        )
    return normalized


def normalize_table_field(
    data: dict[str, Any],
    field_key: str,
    alias: str,
    field_config: dict[str, Any],
    *,
    logger: logging.Logger | None = None,
    findings: list[FieldNormalizationFinding] | None = None,
    include_missing: bool = False,
) -> list[dict[str, Any]] | None:
    """Normalize an array-of-objects field using configured row fields."""
    target_findings = findings if findings is not None else []
    found, table_data = get_extracted_value(data, field_key, alias)
    if not found:
        return None if include_missing else []
    if not isinstance(table_data, list):
        target_findings.append(
            FieldNormalizationFinding(
                path=field_key,
                code="invalid_table",
                message="Table field is not an array",
            )
        )
        if logger:
            logger.warning("Table field %s is not a list", alias)
        return None if include_missing else []

    item_fields = field_config.get("item_fields", {})
    configured_items = item_fields if isinstance(item_fields, dict) else {}
    processed_items: list[dict[str, Any]] = []
    for item_index, item in enumerate(table_data):
        if not isinstance(item, dict):
            target_findings.append(
                FieldNormalizationFinding(
                    path=f"{field_key}.{item_index}",
                    code="invalid_table_item",
                    message="Table item is not an object",
                )
            )
            continue
        processed_item: dict[str, Any] = {}
        for subfield_key, subfield_config in configured_items.items():
            if not isinstance(subfield_config, dict):
                continue
            subfield_alias = str(subfield_config.get("alias", subfield_key))
            item_found, item_value = get_extracted_value(
                item,
                str(subfield_key),
                subfield_alias,
            )
            if not item_found:
                if include_missing:
                    processed_item[str(subfield_key)] = None
                continue
            if isinstance(item_value, str):
                item_value = re.sub(r"\n+", " ", item_value.strip())
            processed_item[str(subfield_key)] = normalize_primitive_field(
                item_value,
                subfield_config,
                logger=logger,
                path=f"{field_key}.{item_index}.{subfield_key}",
                findings=target_findings,
            )
        if processed_item:
            processed_items.append(processed_item)
    return processed_items


def normalize_configured_fields(
    data: dict[str, Any],
    fields: dict[str, Any],
    *,
    logger: logging.Logger | None = None,
    include_missing: bool = False,
) -> NormalizedFieldsResult:
    """Normalize a provider payload into configured workflow field keys."""
    processed: dict[str, Any] = {}
    findings: list[FieldNormalizationFinding] = []
    for field_key, field_config in fields.items():
        if not isinstance(field_config, dict):
            continue
        key = str(field_key)
        alias = str(field_config.get("alias", key))
        if field_config.get("is_table", False):
            processed[key] = normalize_table_field(
                data,
                key,
                alias,
                field_config,
                logger=logger,
                findings=findings,
                include_missing=include_missing,
            )
            continue

        found, value = get_extracted_value(data, key, alias)
        if not found:
            if include_missing:
                processed[key] = None
            continue
        processed[key] = normalize_scalar_field(
            value,
            field_config,
            logger=logger,
            path=key,
            findings=findings,
            include_missing=include_missing,
        )
    return NormalizedFieldsResult(data=processed, findings=findings)


def _join_path(prefix: str, part: str) -> str:
    return f"{prefix}.{part}" if prefix else part


def _normalize_iso_date(
    value: Any,
    *,
    logger: logging.Logger | None,
    path: str,
    findings: list[FieldNormalizationFinding],
) -> Any:
    """Normalize common unambiguous document-date strings to ISO format."""
    if not isinstance(value, str):
        findings.append(
            FieldNormalizationFinding(
                path=path,
                code="invalid_iso_date",
                message="ISO date normalizer requires a text value",
            )
        )
        return value
    text = " ".join(value.strip().split())
    for date_format in (
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    findings.append(
        FieldNormalizationFinding(
            path=path,
            code="invalid_iso_date",
            message="Value could not be normalized to an ISO date",
        )
    )
    if logger:
        logger.warning("Value could not be normalized to an ISO date at %s", path)
    return value


def _normalize_choice(
    value: str,
    choices: list[Any],
    *,
    logger: logging.Logger | None,
    path: str,
    findings: list[FieldNormalizationFinding],
) -> str:
    """Return the configured spelling for an exact or unique token match."""
    text = " ".join(value.strip().split())
    string_choices = [choice for choice in choices if isinstance(choice, str)]
    exact = [choice for choice in string_choices if choice.casefold() == text.casefold()]
    if len(exact) == 1:
        return exact[0]
    token_matches = [
        choice
        for choice in string_choices
        if re.search(rf"(?<!\w){re.escape(choice)}(?!\w)", text, re.IGNORECASE)
    ]
    if len(token_matches) == 1:
        return token_matches[0]
    findings.append(
        FieldNormalizationFinding(
            path=path,
            code="invalid_choice",
            message="Value did not match exactly one configured choice",
        )
    )
    if logger:
        logger.warning("Value did not match a configured choice at %s", path)
    return value
