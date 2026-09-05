"""Focused tests for pipeline-template service error and helper paths."""

from __future__ import annotations

from contextlib import nullcontext
import json
from unittest.mock import Mock

import pytest

import modules.services.pipeline_template_service as template_module
from modules.services.pipeline_template_service import (
    PipelineTemplateConflictError,
    PipelineTemplateValidationError,
    PipelineTemplateService,
)
from modules.services.versioned_config_contracts import content_hash


def _service() -> PipelineTemplateService:
    service = object.__new__(PipelineTemplateService)
    service.conn = Mock()
    service.templates = Mock()
    service.drafts = Mock()
    service.versions = Mock()
    service.dependencies = Mock()
    service.audit = Mock()
    service.validation = Mock()
    service.configured_secret_aliases = set()
    return service


def test_validate_and_import_draft_paths() -> None:
    service = _service()
    template = {"id": "t1", "template_key": "main", "name": "Main"}
    definition = {"schema_version": 3, "pipeline": [], "tasks": {}}
    service._require_template = Mock(return_value=template)
    service._require_draft = Mock(return_value={"definition_json": json.dumps(definition), "revision": 2})
    service._resolve_dependencies = Mock(return_value={})
    service.validation.validate_pipeline.return_value = {"valid": True, "findings": [], "source": "pipeline_draft:main@draft-r2"}
    service._append_dependency_findings = Mock()
    service._append_secret_findings = Mock()
    assert service.validate_draft("t1", user="alice")["valid"] is True
    service.save_draft = Mock(return_value={"revision": 3, "content_hash": "hash"})
    service._require_template.return_value = template
    assert service.import_draft("t1", expected_revision=2, definition=definition, user="alice")["revision"] == 3
    service.audit.append.assert_called()


def test_template_update_preconditions_and_clone_errors(monkeypatch) -> None:
    service = _service()
    monkeypatch.setattr(template_module, "immediate_transaction", lambda _conn: nullcontext())
    current = {
        "id": "t1", "template_key": "main", "name": "Main", "description": "",
        "document_type": None, "operator_instructions": "", "operator_selectable": 1,
        "status": "inactive",
    }
    service._require_template = Mock(return_value=current)
    with pytest.raises(ValueError, match="Unsupported"):
        service.update_template("t1", status="invalid", user="alice")
    current["status"] = "archived"
    with pytest.raises(PipelineTemplateConflictError, match="restored"):
        service.update_template("t1", status="inactive", user="alice")
    current["status"] = "inactive"
    service.versions.list_for_owner.return_value = []
    with pytest.raises(PipelineTemplateConflictError, match="published version"):
        service.update_template("t1", status="active", user="alice")
    current["status"] = "active"
    with pytest.raises(PipelineTemplateConflictError, match="inactive"):
        service.update_template("t1", status="archived", user="alice")
    current["status"] = "inactive"
    service.versions.list_for_owner.return_value = [{"id": "v1"}]
    service.conn.execute.return_value.fetchone.return_value = {"1": 1}
    with pytest.raises(PipelineTemplateConflictError, match="bindings"):
        service.update_template("t1", status="archived", user="alice")

    service.versions.list_for_owner.return_value = []
    with pytest.raises(PipelineTemplateConflictError, match="published"):
        service.clone("t1", template_key="clone", name="Clone", user="alice")


def test_diff_load_and_dependency_helper_errors() -> None:
    service = _service()
    service._require_template = Mock(return_value={"template_key": "main"})
    service._require_draft = Mock(return_value={"base_version_id": "v1", "definition_json": json.dumps({})})
    service.versions.get.return_value = None
    with pytest.raises(KeyError, match="Unknown pipeline version"):
        service.diff("t1")
    with pytest.raises(KeyError, match="Unknown pipeline version"):
        service.load_version("missing")

    definition = {"schema_version": 3, "pipeline": [], "tasks": {}}
    version = {"id": "v1", "template_id": "t1", "definition_json": json.dumps(definition), "content_hash": "wrong"}
    service.versions.get.return_value = version
    with pytest.raises(RuntimeError, match="content hash"):
        service.load_version("v1")
    version["content_hash"] = content_hash(definition)
    service.dependencies.list_for_pipeline.return_value = [{"task_key": "unexpected", "schema_version_id": "s1"}]
    with pytest.raises(RuntimeError, match="dependency rows"):
        service.load_version("v1")

    service._require_template.return_value = {"template_key": "main"}
    service._require_draft.return_value = {"base_version_id": None, "definition_json": json.dumps(definition)}
    assert service.diff("t1")["changed"] is True


def test_dependency_extraction_mismatch_and_required_objects() -> None:
    service = _service()
    definition = {
        "tasks": {
            "extract": {"module": "standard_step.extraction.extract_pdf", "class": "ExtractPdfTask", "params": {"fields": {"amount": {}}}},
            "review": {"class": "ReviewGateTask", "params": {"schema_version_id": "s1"}},
        }
    }
    result = {"valid": True, "findings": [], "source": "pipeline"}
    PipelineTemplateService._append_dependency_findings(
        result,
        definition,
        {"review": {"id": "s1", "schema_json": json.dumps({"fields": {"missing": {}}})}},
    )
    assert result["valid"] is False
    assert result["findings"][0]["code"] == "pipeline-schema-extraction-mismatch"
    assert PipelineTemplateService._dependency_ids({"tasks": "bad"}) == {}
    assert PipelineTemplateService._dependency_ids({"tasks": {"x": "bad"}}) == {}
    service.templates.get.return_value = None
    with pytest.raises(KeyError, match="template"):
        service._require_template("missing")
    service.templates.get.return_value = {"id": "t1"}
    service.drafts.get.return_value = None
    with pytest.raises(KeyError, match="draft"):
        service._require_draft("t1")


def test_publish_and_dependency_filters_cover_remaining_branches(monkeypatch) -> None:
    service = _service()
    monkeypatch.setattr(template_module, "immediate_transaction", lambda _conn: nullcontext())
    service._require_template = Mock(return_value={"id": "t1", "template_key": "main", "status": "archived"})
    service._require_draft = Mock(return_value={"revision": 1, "content_hash": "h", "base_version_id": None, "definition_json": "{}"})
    service._decode_draft = Mock(return_value={"definition": {}})
    service._resolve_dependencies = Mock(return_value={})
    service.validation.validate_pipeline.return_value = {"valid": True, "findings": [], "source": "draft"}
    with pytest.raises(PipelineTemplateConflictError, match="Archived"):
        service.publish("t1", expected_revision=1, user="alice")

    service._require_template.return_value = {"id": "t1", "template_key": "main", "status": "active"}
    service._require_draft.return_value = {"revision": 2, "content_hash": "h2", "base_version_id": None, "definition_json": "{}"}
    with pytest.raises(PipelineTemplateConflictError, match="stale"):
        service.publish("t1", expected_revision=1, user="alice")

    service._require_draft.return_value = {"revision": 1, "content_hash": "h", "base_version_id": None, "definition_json": "{}"}
    service._decode_draft.return_value = {"definition": {}}
    service.validation.validate_pipeline.return_value = {"valid": False, "findings": [{"code": "bad", "severity": "error"}], "source": "draft"}
    with pytest.raises(PipelineTemplateValidationError):
        service.publish("t1", expected_revision=1, user="alice")

    row = {"schema_json": "{}", "content_hash": "wrong", "template_status": "active"}
    service.conn.execute.return_value.fetchone.return_value = row
    assert service._resolve_dependencies({"tasks": {"review": {"class": "ReviewGateTask", "params": {"schema_version_id": "s1"}}}}) == {}
    result = {"findings": [], "source": "draft"}
    PipelineTemplateService._append_dependency_findings(result, {"tasks": {}}, {"review": {"schema_json": "{}"}})
    assert result["findings"] == []

    service.validation.validate_pipeline.side_effect = [
        {"valid": True, "findings": [], "source": "draft"},
        {"valid": False, "findings": [{"severity": "error", "code": "bad"}], "source": "draft"},
    ]
    service._require_template.return_value = {"id": "t1", "template_key": "main", "status": "active"}
    service._require_draft.return_value = {"revision": 1, "content_hash": "h", "base_version_id": None, "definition_json": "{}"}
    with pytest.raises(PipelineTemplateValidationError):
        service.publish("t1", expected_revision=1, user="alice")

    service.conn.execute.return_value.fetchone.return_value = {
        "schema_json": "{}",
        "content_hash": "definitely-wrong",
        "template_status": "active",
    }
    assert service._resolve_dependencies(
        {"tasks": {"review": {"class": "ReviewGateTask", "params": {"schema_version_id": "s1"}}}},
        require_active=True,
    ) == {}


def test_dependency_hash_mismatch_is_ignored() -> None:
    service = _service()
    service.conn.execute.return_value.fetchone.return_value = {
        "schema_json": "{}",
        "content_hash": "not-the-content-hash",
        "template_status": "active",
    }
    assert service._resolve_dependencies(
        {"tasks": {"review": {"class": "ReviewGateTask", "params": {"schema_version_id": "schema-v1"}}}},
        require_active=True,
    ) == {}
