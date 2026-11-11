"""Validate business-rule syntax and field bindings without evaluating data."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from modules.services.business_validation import BusinessValidationConfig, RequiredIfRule
from modules.services.business_validation_registry import NUMBERS, get_validator
from modules.services.versioned_config_contracts import (
    BUSINESS_RULE_SCHEMA_FORMAT_VERSION, REVIEW_SCHEMA_FORMAT_VERSION,
    SUPPORTED_REVIEW_SCHEMA_FORMAT_VERSIONS,
)


def review_schema_format(schema: Mapping[str, Any]) -> int:
    """Give rule-bearing publications a format rejected by older releases."""
    return (BUSINESS_RULE_SCHEMA_FORMAT_VERSION if "business_validation" in schema
            else REVIEW_SCHEMA_FORMAT_VERSION)


def require_business_rule_capability(schema: Mapping[str, Any], format_version: Any) -> None:
    """Reject authoring-only legacy rule versions at execution boundaries."""
    if type(format_version) is not int or format_version not in SUPPORTED_REVIEW_SCHEMA_FORMAT_VERSIONS:
        raise ValueError("Unsupported published review schema format version.")
    if "business_validation" in schema and format_version != BUSINESS_RULE_SCHEMA_FORMAT_VERSION:
        raise ValueError("Republish the review form with format 2 and select its new pipeline version before execution.")


def _resolve_field(root: Mapping[str, Any], pointer: str) -> Mapping[str, Any] | None:
    """Resolve schema types using the same JSON Pointer traversal as values."""
    current: Mapping[str, Any] = root
    for encoded in pointer[1:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if current.get("type") == "object":
            properties = current.get("properties")
            next_field = properties.get(key) if isinstance(properties, Mapping) else None
        elif current.get("type") == "array" and (
            key == "0" or (key.isascii() and key.isdigit() and not key.startswith("0"))
        ):
            next_field = current.get("items")
        else:
            return None
        if not isinstance(next_field, Mapping):
            return None
        current = next_field
    return current


def validate_business_validation_schema(schema: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return safe findings for optional rules, including disabled rule bindings.

    Keep the supplied definition unchanged so canonical hashes and portable
    documents do not acquire implicit defaults during validation.
    """
    if "business_validation" not in schema:
        return []
    try:
        config = BusinessValidationConfig.model_validate(schema["business_validation"])
    except ValidationError as exc:
        findings = []
        for error in exc.errors(include_input=False, include_url=False, include_context=False):
            location = [str(part) for part in error["loc"] if part not in {
                "line_amount:v1", "sum_equals:v1",
            }]
            findings.append({
                "path": ".".join(["business_validation", *location]),
                "message": (
                    "Select an available validator version."
                    if error["type"] in {"union_tag_invalid", "union_tag_not_found"}
                    else error["msg"]
                ),
            })
        return findings

    root = {"type": "object", "properties": schema.get("fields", {})}
    findings: list[dict[str, str]] = []
    for index, rule in enumerate(config.rules):
        prefix = f"business_validation.rules.{index}"
        plugin = get_validator(rule.validator)
        if plugin is None:
            findings.append({'path': f'{prefix}.validator', 'message': 'Select an available validator version.'})
            continue
        items = None
        if plugin.collection:
            collection = _resolve_field(root, getattr(rule, plugin.collection))
            items = collection.get('items') if collection else None
            if (not collection or collection.get('type') != 'array'
                    or not isinstance(items, Mapping) or items.get('type') != 'object'):
                findings.append({'path': f'{prefix}.{plugin.collection}',
                                 'message': 'Select an existing array of objects for the item collection.'})
                continue
        for binding in plugin.bindings:
            scope = items if binding.scope == 'row' else root
            if scope is None:
                findings.append({'path': f'{prefix}.{binding.name}',
                                 'message': 'Select an existing field in the indicated scope.'})
                continue
            pointers = getattr(rule, binding.name)
            for number, pointer in enumerate(pointers if binding.many else (pointers,)):
                field = _resolve_field(scope, pointer)
                if not field or binding.types is not None and field.get('type', 'string') not in binding.types:
                    kind = 'numeric ' if binding.types == NUMBERS else 'date ' if binding.types == frozenset({'date'}) else ''
                    suffix = f'.{number}' if binding.many else ''
                    findings.append({'path': f'{prefix}.{binding.name}{suffix}',
                                     'message': f'Select an existing {kind}field in the indicated scope.'})
        if isinstance(rule, RequiredIfRule) and rule.equals is not None:
            condition = _resolve_field(root, rule.when)
            field_type = condition.get('type', 'string') if condition else None
            compatible = (field_type in NUMBERS and type(rule.equals) in {int, float}
                          or field_type == 'boolean' and type(rule.equals) is bool
                          or field_type in {'string', 'date', 'datetime'} and isinstance(rule.equals, str)
                          or field_type == 'enum')
            if not compatible:
                findings.append({'path': f'{prefix}.equals', 'message': 'Condition value must match the selected field type.'})
            elif field_type == 'enum':
                choices = (condition or {}).get('choices') or (condition or {}).get('enum')
                if isinstance(choices, list):
                    options = [choice.get('value', choice.get('label')) if isinstance(choice, Mapping) else choice
                               for choice in choices]
                    if not any((type(option) is type(rule.equals)
                                or type(option) in {int, float} and type(rule.equals) in {int, float})
                               and option == rule.equals for option in options):
                        findings.append({'path': f'{prefix}.equals', 'message': 'Select a condition value offered by the field.'})
    return findings
