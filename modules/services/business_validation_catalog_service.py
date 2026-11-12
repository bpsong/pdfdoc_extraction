"""Safe, provider-neutral views of the source-controlled validator catalog."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from modules.services.business_validation_metadata import ValidatorControl
from modules.services import business_validation_registry as registry


COMMON_CONTROLS = (
    ValidatorControl("enabled", "Enabled", "boolean", default=True),
    ValidatorControl("severity", "Severity", "choice", default="warning",
                     choices=(("warning", "Warning"), ("blocking", "Blocking"))),
    ValidatorControl("require_review", "Require review on warning", "boolean", default=True),
    ValidatorControl("message", "Mismatch message (optional)", "text", max_length=500, required=False),
)


def _control(control: ValidatorControl) -> dict[str, Any]:
    result = asdict(control)
    result["types"] = sorted(control.types) if control.types is not None else None
    result["choices"] = [{"value": value, "label": label} for value, label in control.choices]
    result["visible_when"] = [{"field": path, "values": list(values)} for path, values in control.visible_when]
    return result


def business_validator_catalog() -> dict[str, Any]:
    """Expose editor data only, excluding Python objects and module paths."""
    return {
        "catalog_version": 1,
        "common_controls": [_control(control) for control in COMMON_CONTROLS],
        "validators": [
            {"id": plugin.identifier, "title": plugin.editor.title,
             "description": plugin.editor.description, "category": plugin.editor.category,
             "collection": plugin.collection,
             "collection_when": ({"field": plugin.collection_when[0], "values": list(plugin.collection_when[1])}
                                 if plugin.collection_when else None),
             "controls": [_control(control) for control in plugin.editor.controls]}
            for plugin in registry.APPROVED_VALIDATORS.values() if plugin.editor is not None
        ],
    }


def business_validator_labels() -> dict[str, str]:
    """Return presentation labels separately from stored reports and form hashes."""
    return {plugin.identifier: plugin.editor.title
            for plugin in registry.APPROVED_VALIDATORS.values() if plugin.editor is not None}
