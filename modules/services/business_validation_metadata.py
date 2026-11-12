"""Validated presentation metadata for approved business-rule editor widgets."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Annotated, Any, Literal, get_args, get_origin

from pydantic import BaseModel


ControlKind = Literal[
    "field", "collection", "choice", "boolean", "text", "decimal", "integer",
    "typed", "operand",
]
Condition = tuple[str, tuple[Any, ...]]


@dataclass(frozen=True)
class ValidatorControl:
    """One reusable widget; conditions contain literal choices, never code."""

    name: str
    label: str
    kind: ControlKind
    default: Any = None
    scope: Literal["document", "row"] = "document"
    types: frozenset[str] | None = None
    many: bool = False
    choices: tuple[tuple[Any, str], ...] = ()
    visible_when: tuple[Condition, ...] = ()
    condition_field: str | None = None
    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    required: bool = True
    allow_constant: bool = False


@dataclass(frozen=True)
class ValidatorEditor:
    """Display definition shipped with one reviewed validator implementation."""

    title: str
    description: str
    category: str
    controls: tuple[ValidatorControl, ...]


def model_has_path(model: type[BaseModel], path: str) -> bool:
    """Resolve a dotted metadata path across nested/discriminated model types."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,3}", path):
        return False
    parts = path.split(".")
    if any(part in {'constructor', 'prototype', '__proto__'} for part in parts):
        return False
    field = model.model_fields.get(parts[0])
    if field is None:
        return False
    if len(parts) == 1:
        return True

    def models(annotation: Any) -> list[type[BaseModel]]:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [annotation]
        args = get_args(annotation)
        if get_origin(annotation) is Annotated:
            args = args[:1]
        return [candidate for arg in args for candidate in models(arg)]

    return any(model_has_path(child, ".".join(parts[1:])) for child in models(field.annotation))


def rule_value(rule: Any, path: str) -> Any:
    """Read approved descriptor paths without evaluating expressions."""
    value = rule
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else getattr(value, part, None)
    return value


def condition_matches(rule: Any, condition: Condition) -> bool:
    """Match literal metadata conditions without conflating booleans and numbers."""
    value = rule_value(rule, condition[0])
    return any(type(value) is type(choice) and value == choice for choice in condition[1])


def validate_editor(model: type[BaseModel], editor: ValidatorEditor) -> None:
    """Reject inconsistent descriptors before publishing a catalog."""
    if any(not isinstance(text, str) or not text.strip() or len(text) > 500
           for text in (editor.title, editor.description, editor.category)):
        raise ValueError("Invalid approved validator editor text.")
    names: set[str] = set()
    kinds = {"field", "collection", "choice", "boolean", "text", "decimal",
             "integer", "typed", "operand"}
    for control in editor.controls:
        if (not model_has_path(model, control.name) or control.name in names
                or control.kind not in kinds or not isinstance(control.label, str) or not control.label or len(control.label) > 128
                or control.scope not in {"document", "row"}
                or control.types is not None and not control.types <= {
                    "string", "number", "integer", "float", "boolean", "date", "datetime", "enum", "object", "array",
                }):
            raise ValueError("Invalid approved validator editor control.")
        names.add(control.name)
        try:
            json.dumps(control.default, allow_nan=False)
            json.dumps(control.choices, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise ValueError('Editor defaults and choices must be finite JSON values.') from exc
        if control.default is not None:
            if (control.kind == 'boolean' and type(control.default) is not bool
                    or control.kind == 'integer' and type(control.default) is not int
                or control.kind in {'text', 'collection'} and not isinstance(control.default, str)
                or control.kind == 'field' and not (
                    isinstance(control.default, list) and all(isinstance(value, str) for value in control.default)
                    if control.many else isinstance(control.default, str))):
                raise ValueError('Editor default conflicts with its control type.')
        if any(type(value) not in {str, int, float, bool, type(None)} or not isinstance(label, str)
               or not label or len(label) > 128 for value, label in control.choices):
            raise ValueError('Invalid approved validator editor choices.')
        def choice_key(value: Any) -> str:
            if isinstance(value, str):
                return value
            if type(value) in {int, float} and value == int(value):
                return str(int(value))
            return json.dumps(value)

        if control.kind == "choice" and (not control.choices or len({choice_key(v) for v, _ in control.choices}) != len(control.choices)):
            raise ValueError("Invalid approved validator editor choices.")
        if control.default is not None and control.kind == "choice" and not any(
            type(control.default) is type(value) and control.default == value for value, _ in control.choices
        ):
            raise ValueError("Invalid approved validator editor default.")
        if control.condition_field and not model_has_path(model, control.condition_field):
            raise ValueError("Invalid approved validator condition binding.")
        for path, values in control.visible_when:
            if not model_has_path(model, path) or not values or any(type(v) not in {str, int, bool, type(None)} for v in values):
                raise ValueError("Invalid approved validator editor visibility.")
        if (any(value is not None and type(value) is not int for value in (control.minimum, control.maximum))
                or control.minimum is not None and control.maximum is not None and control.minimum > control.maximum
                or control.max_length is not None and (type(control.max_length) is not int or control.max_length < 1)):
            raise ValueError("Invalid approved validator editor bounds.")
