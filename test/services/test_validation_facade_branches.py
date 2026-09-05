"""Focused coverage for facade normalization and dependency findings."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

import modules.services.validation_facade as facade_module
from modules.services.validation_facade import ValidationFacade, _NullConfig
from modules.services.versioned_config_contracts import ValidationSource


def test_facade_pipeline_error_normalization_and_dependencies(monkeypatch) -> None:
    facade = ValidationFacade()
    source = ValidationSource("pipeline_file", key="sample")
    monkeypatch.setattr(
        facade_module,
        "PipelineValidationService",
        lambda _config: Mock(validate=lambda _definition: {"findings": []}),
    )
    result = facade.validate_pipeline(
        {
            "schema_version": 99,
            "pipeline": [],
            "tasks": {
                "missing": {"class": "ReviewGateTask", "params": {}},
                "unresolved": {"class": "ReviewGateTask", "params": {"schema_version_id": "v1"}},
                "mismatch": {"class": "ReviewGateTask", "params": {"schema_version_id": "v2"}},
            },
            "api_key": "literal",
        },
        source=source,
        schema_dependencies={"mismatch": {"id": "v3"}},
    )
    codes = {finding["code"] for finding in result["findings"]}
    assert {"pipeline-schema-version-unsupported", "pipeline-literal-or-invalid-secret", "review-gate-schema-version-required", "review-gate-schema-version-not-found", "review-gate-schema-version-mismatch"} <= codes
    assert result["valid"] is False

    non_json = facade.validate_pipeline({"bad": {1, 2}}, source=source)
    assert non_json["findings"][0]["code"] == "versioned-config-not-json"


def test_facade_review_schema_error_format_and_issue_paths(monkeypatch) -> None:
    facade = ValidationFacade()
    source = ValidationSource("review_schema_file", key="schema")
    monkeypatch.setattr(
        facade_module,
        "SchemaService",
        lambda _config: Mock(validate_schema=lambda _schema: [{"path": "fields.x", "message": "bad"}, {}]),
    )
    result = facade.validate_review_schema(
        {"fields": {}}, source=source, format_version=999
    )
    assert {finding["code"] for finding in result["findings"]} == {
        "review-schema-format-version-unsupported", "review-schema-invalid"
    }
    assert any(finding["path"].endswith(".$") for finding in result["findings"])
    non_json = facade.validate_review_schema({"bad": {1, 2}}, source=source)
    assert non_json["findings"][0]["code"] == "review-schema-not-json"
    assert _NullConfig().get("missing", "default") == "default"


def test_facade_static_result_and_dependency_shortcuts() -> None:
    assert ValidationFacade._validate_schema_dependencies({"tasks": []}, {}) == []
    assert ValidationFacade._validate_schema_dependencies({"tasks": {"x": "not-a-task"}}, {}) == []
    result = ValidationFacade._result(
        ValidationSource("runtime"), [{"severity": "warning", "message": "notice"}]
    )
    assert result["valid"] is True
    assert result["findings"][0]["path"] == "runtime.$"
