from __future__ import annotations

import math
import json

import pytest

from modules.services.portable_config_service import (
    PortableConfigError,
    export_pipeline_bundle,
    import_pipeline_bundle,
)
from modules.services.validation_facade import ValidationFacade
from modules.services.versioned_config_contracts import (
    CanonicalizationError,
    ReviewSchemaCoordinate,
    SecretReferenceError,
    ValidationSource,
    build_display_snapshot,
    canonical_json_text,
    canonicalize_json,
    content_hash,
    normalize_key,
    preserve_secret_references,
    redact_sensitive,
    resolve_secret_references,
    validate_secret_references,
)


def _definition(schema_value: object | None = None) -> dict:
    params = {
        "api_key": {"$secret": "llamacloud-primary"},
        "configuration_id": "cfg",
        "fields": {"invoice_number": {"type": "str", "description": "Invoice"}},
    }
    tasks = {
        "extract": {
            "module": "standard_step.extraction.llama_cloud_v2",
            "class": "ExtractPdfTask",
            "params": params,
            "on_error": "stop",
        }
    }
    pipeline = ["extract"]
    if schema_value is not None:
        tasks["review"] = {
            "module": "standard_step.review.review_gate",
            "class": "ReviewGateTask",
            "params": {
                "schema_version_id": schema_value,
                "confidence_threshold": 0.8,
            },
            "on_error": "stop",
        }
        pipeline.append("review")
    return {"schema_version": 1, "pipeline": pipeline, "tasks": tasks}


def test_canonical_json_is_deterministic_and_preserves_array_order():
    left = {"z": [2, 1], "a": {"b": True, "a": "é"}, "n": None}
    right = {"n": None, "a": {"a": "é", "b": True}, "z": [2, 1]}
    assert canonical_json_text(left) == canonical_json_text(right)
    assert content_hash(left) == content_hash(right)
    assert canonicalize_json(left)["z"] == [2, 1]
    assert content_hash({"z": [1, 2]}) != content_hash({"z": [2, 1]})


@pytest.mark.parametrize("value", [{1: "bad"}, {1, 2}, (1, 2), math.inf, math.nan])
def test_canonical_json_rejects_non_json_values(value):
    with pytest.raises(CanonicalizationError):
        canonicalize_json(value)


def test_keys_and_secret_references_are_validated_resolved_and_redacted():
    assert normalize_key(" Invoice-Processing ") == "invoice-processing"
    with pytest.raises(ValueError):
        normalize_key("not valid")
    definition = _definition()
    assert validate_secret_references(definition) == []
    resolved = resolve_secret_references(definition, {"llamacloud-primary": "top-secret"})
    assert resolved["tasks"]["extract"]["params"]["api_key"] == "top-secret"
    with pytest.raises(TypeError):
        json.dumps(resolved)
    assert definition["tasks"]["extract"]["params"]["api_key"] == {
        "$secret": "llamacloud-primary"
    }
    redacted = redact_sensitive(definition, secret_configured=lambda alias: alias in {"llamacloud-primary"})
    assert redacted["tasks"]["extract"]["params"]["api_key"] == {
        "$secret": "llamacloud-primary",
        "configured": True,
    }
    with pytest.raises(SecretReferenceError):
        resolve_secret_references(definition, {})
    assert validate_secret_references({"api_key": "literal"}) == ["api_key"]
    assert validate_secret_references({"api_key": {"$secret": "BAD"}}) == ["api_key"]
    assert preserve_secret_references(
        {"api_key": "[REDACTED]"}, definition["tasks"]["extract"]["params"]
    ) == {"api_key": {"$secret": "llamacloud-primary"}}
    with pytest.raises(SecretReferenceError):
        preserve_secret_references({"api_key": "[REDACTED]"}, {})


def test_display_snapshot_excludes_params_and_is_deterministic():
    snapshot = build_display_snapshot(_definition())
    assert snapshot["step_count"] == 1
    assert snapshot["steps"][0]["key"] == "extract"
    assert "params" not in snapshot["steps"][0]
    assert snapshot == build_display_snapshot(_definition())


def test_validation_facade_qualifies_pipeline_and_schema_findings():
    facade = ValidationFacade()
    valid = facade.validate_pipeline(
        _definition(),
        source=ValidationSource(kind="pipeline_draft", key="invoice", revision=2),
    )
    assert valid["source"] == "pipeline-draft:invoice@draft-r2"
    assert all(item["path"].startswith(valid["source"]) for item in valid["findings"])

    with_schema = facade.validate_pipeline(
        _definition("schema-v1"),
        source=ValidationSource(kind="pipeline_version", key="invoice", version_number=1),
        schema_dependencies={"review": {"id": "schema-v1"}},
    )
    assert not any(
        item["code"].startswith("review-gate-schema-version")
        for item in with_schema["findings"]
    )

    invalid_schema = facade.validate_review_schema(
        {"fields": {"choice": {"type": "enum"}}},
        source=ValidationSource(kind="review_schema_draft", key="invoice", revision=1),
    )
    assert invalid_schema["valid"] is False
    assert all(
        item["path"].startswith("review-schema-draft:invoice@draft-r1")
        for item in invalid_schema["findings"]
    )


def test_portable_pipeline_round_trip_and_dependency_resolution():
    definition = _definition("schema-id")
    coordinate = ReviewSchemaCoordinate("invoice-review", 2, "a" * 64)
    bundle = export_pipeline_bundle(
        definition,
        template_key="invoice-processing",
        template_name="Invoice Processing",
        resolve_version=lambda version_id: coordinate if version_id == "schema-id" else None,
    )
    assert "schema_version_id" not in bundle["definition"]["tasks"]["review"]["params"]
    imported, dependencies = import_pipeline_bundle(
        bundle,
        resolve_coordinate=lambda item: "target-schema-id" if item == coordinate else None,
    )
    assert imported["tasks"]["review"]["params"]["schema_version_id"] == "target-schema-id"
    assert dependencies["review"] == coordinate


def test_portable_pipeline_requires_online_or_embedded_dependency():
    definition = _definition("schema-id")
    coordinate = ReviewSchemaCoordinate("invoice-review", 2, content_hash({"fields": {}}))
    bundle = export_pipeline_bundle(
        definition,
        template_key="invoice-processing",
        template_name="Invoice Processing",
        resolve_version=lambda _: coordinate,
    )
    with pytest.raises(PortableConfigError, match="Unresolved"):
        import_pipeline_bundle(bundle)

    embedded = export_pipeline_bundle(
        definition,
        template_key="invoice-processing",
        template_name="Invoice Processing",
        resolve_version=lambda _: coordinate,
        embedded_schemas={"schema-id": {"fields": {}}},
    )
    imported, _ = import_pipeline_bundle(embedded)
    assert imported["tasks"]["review"]["params"]["schema_version_id"].startswith("embedded:")

    embedded["dependencies"]["review_schemas"].append(
        dict(embedded["dependencies"]["review_schemas"][0])
    )
    with pytest.raises(PortableConfigError, match="Duplicate"):
        import_pipeline_bundle(embedded)
