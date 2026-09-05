"""Focused coverage for review-schema lifecycle edge cases."""

from __future__ import annotations

from contextlib import nullcontext
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import modules.services.review_schema_version_service as schema_module
from modules.services.review_schema_version_service import (
    ReviewSchemaConflictError,
    ReviewSchemaVersionService,
    _NullConfig,
)
from modules.services.versioned_config_contracts import content_hash


def _service() -> ReviewSchemaVersionService:
    service = object.__new__(ReviewSchemaVersionService)
    service.conn = Mock()
    service.templates = Mock()
    service.drafts = Mock()
    service.versions = Mock()
    service.audit = Mock()
    service.validation = Mock()
    return service


def test_schema_draft_validation_and_publish_preconditions(monkeypatch) -> None:
    service = _service()
    template = {"id": "t1", "schema_key": "invoice", "status": "archived"}
    service._require_template = Mock(return_value=template)
    service._require_draft = Mock(return_value={"revision": 3, "schema_json": json.dumps({"fields": {}}), "base_version_id": None})
    with pytest.raises(ReviewSchemaConflictError, match="Archived"):
        monkeypatch.setattr(schema_module, "immediate_transaction", lambda _conn: nullcontext())
        service.publish("t1", expected_revision=3, user="alice")
    template["status"] = "inactive"
    with pytest.raises(ReviewSchemaConflictError, match="stale"):
        service.publish("t1", expected_revision=2, user="alice")

    service.validation.validate_review_schema.return_value = {"valid": True, "findings": []}
    service.audit.append = Mock()
    assert service.validate_draft("t1", user="alice")["valid"] is True
    service.validation.validate_review_schema.return_value = {"valid": False, "findings": [{"code": "bad"}]}
    service._require_draft.return_value = {"revision": 3, "schema_json": json.dumps({"fields": {}}), "base_version_id": None}
    with pytest.raises(Exception):
        service.publish("t1", expected_revision=3, user="alice")


def test_schema_update_load_and_export_error_paths(monkeypatch) -> None:
    service = _service()
    monkeypatch.setattr(schema_module, "immediate_transaction", lambda _conn: nullcontext())
    current = {"id": "t1", "schema_key": "invoice", "name": "Invoice", "description": "", "status": "inactive"}
    service._require_template = Mock(return_value=current)
    service.versions.list_for_owner.return_value = []
    with pytest.raises(ValueError, match="Unsupported"):
        service.update_template("t1", status="bad", user="alice")
    current["status"] = "archived"
    with pytest.raises(ReviewSchemaConflictError, match="restored"):
        service.update_template("t1", status="inactive", user="alice")
    current["status"] = "inactive"
    with pytest.raises(ReviewSchemaConflictError, match="published"):
        service.update_template("t1", status="active", user="alice")
    service.versions.get.return_value = None
    with pytest.raises(KeyError, match="version"):
        service.load_version("missing")
    version = {"id": "v1", "schema_json": json.dumps({"fields": {}}), "format_version": 99, "content_hash": content_hash({"fields": {}})}
    service.versions.get.return_value = version
    with pytest.raises(RuntimeError, match="format"):
        service.load_version("v1")
    version["format_version"] = 1
    version["content_hash"] = "wrong"
    with pytest.raises(RuntimeError, match="hash"):
        service.load_version("v1")
    service._require_template.return_value = {"id": "t1", "schema_key": "invoice"}
    service.load_version = Mock(return_value={"schema_template_id": "t1", "format_version": 1, "schema_key": "invoice", "version_number": 1, "content_hash": "hash", "schema": {"fields": {}}})
    service.audit.append = Mock()
    assert json.loads(service.export_version("v1", format="json"))["kind"] == "review-schema"
    with pytest.raises(ValueError, match="yaml or json"):
        service.export_version("v1", format="toml")


def test_schema_export_draft_import_document_and_required_objects() -> None:
    service = _service()
    service._require_template = Mock(return_value={"schema_key": "invoice"})
    service._require_draft = Mock(return_value={"revision": 2, "content_hash": "hash", "schema_json": json.dumps({"fields": {}})})
    service.audit.append = Mock()
    assert "review-schema-draft" in service.export_draft("t1", format="yaml")
    with pytest.raises(ValueError, match="yaml or json"):
        service.export_draft("t1", format="toml")

    service.import_document = Mock(return_value={"fields": {}})
    service.save_draft = Mock(return_value={"revision": 3, "content_hash": "hash"})
    assert service.import_draft("t1", expected_revision=2, text="{}", user="alice")["revision"] == 3
    with pytest.raises(ValueError, match="1 MiB"):
        ReviewSchemaVersionService.import_document("x" * 1_048_577)
    with pytest.raises(ValueError, match="object"):
        ReviewSchemaVersionService.import_document("- value")
    with pytest.raises(ValueError, match="kind"):
        ReviewSchemaVersionService.import_document("kind: bad\nschema: {}")
    with pytest.raises(ValueError, match="format"):
        ReviewSchemaVersionService.import_document("format_version: 99\nschema: {}")
    with pytest.raises(ValueError, match="object"):
        ReviewSchemaVersionService.import_document("schema: []")
    service._require_template = ReviewSchemaVersionService._require_template.__get__(service)
    service.templates.get.return_value = None
    with pytest.raises(KeyError, match="template"):
        service._require_template("t1")
    service._require_draft = ReviewSchemaVersionService._require_draft.__get__(service)
    service.templates.get.return_value = {"id": "t1"}
    service.drafts.get.return_value = None
    with pytest.raises(KeyError, match="draft"):
        service._require_draft("t1")
    assert _NullConfig().get("missing", "fallback") == "fallback"
