"""Coverage for read-only stored and portable configuration validation paths."""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
import yaml

from tools.config_check.stored_validator import (
    StoredSourceValidator,
    _MappingConfig,
    _error,
    _from_findings,
    _json_object,
    _secret_references,
    configured_database_path,
    load_document,
    open_readonly_database,
    portable_contract_schema,
    validate_database_schema,
    validate_portable_file,
    ValidationResult,
)
from modules.db.migrations import SCHEMA_VERSION
from modules.services.versioned_config_contracts import content_hash
from modules.services.versioned_config_contracts import ReviewSchemaCoordinate


def test_document_and_database_path_helpers(tmp_path: Path) -> None:
    good = tmp_path / "good.yaml"
    good.write_text(yaml.safe_dump({"key": "value"}), encoding="utf-8")
    assert load_document(good) == {"key": "value"}
    bad = tmp_path / "bad.yaml"
    bad.write_text("- value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="object"):
        load_document(bad)
    huge = tmp_path / "huge.yaml"
    huge.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="2 MiB"):
        load_document(huge)
    assert configured_database_path(tmp_path / "config.yaml", {}) is None
    assert configured_database_path(tmp_path / "config.yaml", {"database": {"path": "db.sqlite"}}) == tmp_path / "db.sqlite"
    assert configured_database_path(tmp_path / "config.yaml", {"database": {"path": "C:/db.sqlite"}}).is_absolute()


def test_readonly_database_and_schema_findings(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        with open_readonly_database(tmp_path / "missing.sqlite"):
            pass
    empty = sqlite3.connect(":memory:")
    empty.row_factory = sqlite3.Row
    assert validate_database_schema(empty).errors[0].code == "database-schema-unavailable"
    empty.close()
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE schema_migrations(version INTEGER)")
    db.execute("INSERT INTO schema_migrations VALUES (2)")
    assert validate_database_schema(db).errors[0].code == "database-schema-outdated"
    db.execute("UPDATE schema_migrations SET version = ?", (SCHEMA_VERSION,))
    assert validate_database_schema(db).errors[0].code == "database-schema-incomplete"
    db.close()


def test_stored_validator_empty_and_selector_error_paths() -> None:
    conn = Mock()
    cursor = Mock()
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None
    conn.execute.return_value = cursor
    validator = StoredSourceValidator(conn, runtime_config={"pipeline_secrets": "bad"})
    assert validator.validate_default().errors[0].code == "stored-active-pipeline-missing"
    assert validator.validate_pipeline("x").errors[0].code == "stored-selector-invalid"
    assert validator.validate_pipeline("x", draft=True).errors[0].code == "stored-pipeline-not-found"
    assert validator.validate_pipeline("x", version_number=1).errors[0].code == "stored-pipeline-not-found"
    assert validator.validate_pipeline_version_id("x").errors[0].code == "stored-pipeline-not-found"
    assert validator.validate_review_schema("x").errors[0].code == "stored-selector-invalid"
    assert validator.validate_review_schema("x", draft=True).errors[0].code == "stored-review-schema-not-found"
    assert validator.validate_review_schema("x", version_number=1).errors[0].code == "stored-review-schema-not-found"
    assert validator.validate_bindings().is_valid


def test_stored_validator_internal_contract_helpers() -> None:
    assert _MappingConfig({"a": {"b": 2}}).get("a.b") == 2
    assert _MappingConfig({}).get("missing", "fallback") == "fallback"
    assert _json_object('{"x": 1}') == {"x": 1}
    with pytest.raises(ValueError):
        _json_object("[]")
    result = _from_findings([{"path": "x", "message": "warning", "severity": "warning"}, {}])
    assert len(result.warnings) == 1 and len(result.errors) == 1
    assert _error("x", "bad", "code").errors[0].code == "code"
    assert _secret_references({"a": {"$secret": "one"}, "b": [{"$secret": "two"}]}) == [("$.a", "one"), ("$.b[0]", "two")]
    assert _secret_references("plain") == []
    assert portable_contract_schema("review-schema")["title"] == "Portable review schema"
    assert portable_contract_schema("pipeline-bundle")["title"] == "Portable pipeline bundle"
    with pytest.raises(ValueError, match="Unsupported"):
        portable_contract_schema("nope")


def test_dependencies_and_secret_alias_findings() -> None:
    conn = Mock()
    cursor = Mock()
    cursor.fetchone.return_value = {"id": "schema-v1"}
    conn.execute.return_value = cursor
    validator = StoredSourceValidator(conn, runtime_config={"pipeline_secrets": {"configured": "value"}})
    dependencies = validator._dependencies_from_definition({"tasks": {"extract": {"params": {"schema_version_id": "schema-v1"}}, "bad": "task"}})
    assert dependencies["extract"]["id"] == "schema-v1"
    assert validator._dependencies_from_definition({"tasks": []}) == {}
    result = validator._facade_result(
        {"source": "pipeline", "findings": [{"path": "x", "message": "bad", "code": "x"}]},
        definition={"params": {"api_key": {"$secret": "missing"}}},
    )
    assert any(item.code == "pipeline-secret-alias-unconfigured" for item in result.errors)


def test_stored_validator_valid_rows_and_all_sources() -> None:
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def __iter__(self):
            return iter(self.rows)

    class Conn:
        def execute(self, query, *_args):
            if "FROM pipeline_versions" in query and "WHERE t.status" in query:
                return Cursor([{"id": "pv1"}])
            if "SELECT template_key FROM pipeline_templates" in query:
                return Cursor([{"template_key": "main"}])
            if "SELECT v.id FROM pipeline_versions v" in query:
                return Cursor([{"id": "pv1"}])
            if "SELECT schema_key FROM review_schema_templates" in query:
                return Cursor([{"schema_key": "invoice"}])
            if "SELECT v.version_number FROM review_schema_versions" in query:
                return Cursor([{"version_number": 1}])
            return Cursor([])

    validator = StoredSourceValidator(Conn(), runtime_config={})
    validator.validate_pipeline_version_id = Mock(return_value=ValidationResult())
    validator.validate_pipeline = Mock(return_value=ValidationResult())
    validator.validate_review_schema = Mock(return_value=ValidationResult())
    validator.validate_bindings = Mock(return_value=ValidationResult())
    assert validator.validate_default().is_valid
    assert validator.validate_all().is_valid
    assert validator.validate_pipeline_version_id.call_args.args == ("pv1",)


def test_stored_hash_checks_and_dependency_rows() -> None:
    definition = {"schema_version": 3, "pipeline": ["extract"], "tasks": {"extract": {}}}
    row = {
        "id": "pv1",
        "template_key": "main",
        "version_number": 2,
        "definition_json": json.dumps(definition),
        "content_hash": "wrong",
    }
    conn = Mock()
    cursor = Mock()
    cursor.fetchone.return_value = row
    conn.execute.return_value = cursor
    validator = StoredSourceValidator(conn, runtime_config={})
    assert validator.validate_pipeline_version_id("pv1").errors[0].code == "stored-pipeline-hash-mismatch"

    row["content_hash"] = content_hash(definition)
    dep_cursor = Mock()
    dep_cursor.fetchall.return_value = [{"task_key": "review", "id": "schema-v1"}]
    conn.execute.side_effect = [cursor, dep_cursor]
    validator.facade.validate_pipeline = Mock(
        return_value={"source": "pipeline", "findings": []}
    )
    assert validator.validate_pipeline_version_id("pv1").is_valid


def test_review_schema_hash_and_binding_findings(tmp_path: Path) -> None:
    schema = {"title": "Invoice", "fields": {"supplier": {"type": "string"}}}
    conn = Mock()
    cursor = Mock()
    cursor.fetchone.return_value = {
        "schema_json": json.dumps(schema),
        "version_number": 1,
        "content_hash": "wrong",
        "schema_key": "invoice",
    }
    conn.execute.return_value = cursor
    validator = StoredSourceValidator(conn, runtime_config={})
    assert validator.validate_review_schema("invoice", version_number=1).errors[0].code == "stored-review-schema-hash-mismatch"

    existing = tmp_path / "existing"
    nested = existing / "nested"
    nested.mkdir(parents=True)
    cursor.fetchall.return_value = [
        {"id": "one", "folder_path": str(existing), "enabled": 1, "status": "inactive"},
        {"id": "two", "folder_path": str(nested), "enabled": 1, "status": "active"},
        {"id": "three", "folder_path": str(tmp_path / "missing"), "enabled": 1, "status": "active"},
    ]
    findings = validator.validate_bindings()
    codes = {finding.code for finding in findings.errors}
    assert {"binding-pipeline-inactive", "binding-folder-overlap", "binding-folder-unavailable"} <= codes


def test_portable_file_runtime_review_pipeline_and_coordinate_branches(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime.yaml"
    runtime.write_text("pipeline: []\n", encoding="utf-8")
    result = validate_portable_file(runtime, kind="runtime")
    assert isinstance(result, ValidationResult)

    review = tmp_path / "review.yaml"
    review.write_text("schema: []\n", encoding="utf-8")
    assert validate_portable_file(review, kind="review-schema").errors[0].code == "portable-review-schema-invalid"
    assert validate_portable_file(runtime, kind="unknown").errors[0].code == "portable-kind"

    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text("not: a bundle\n", encoding="utf-8")
    assert validate_portable_file(pipeline, kind="pipeline").errors[0].code == "portable-pipeline-invalid"

    valid_document = {"kind": "pipeline-bundle", "format_version": 1, "template": {}, "definition": {"schema_version": 3, "pipeline": [], "tasks": {}}, "dependencies": {}}
    monkeypatch.setattr(
        "tools.config_check.stored_validator.load_document",
        lambda _path: valid_document,
    )
    monkeypatch.setattr(
        "tools.config_check.stored_validator.import_pipeline_bundle",
        lambda document, resolve_coordinate=None: (document["definition"], {}),
    )
    monkeypatch.setattr(
        "modules.services.validation_facade.ValidationFacade.validate_pipeline",
        lambda *_args, **_kwargs: {"findings": []},
    )
    assert validate_portable_file(pipeline, kind="pipeline").is_valid


def test_stored_validator_remaining_success_paths(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "readonly.sqlite"
    raw = sqlite3.connect(db)
    raw.execute("CREATE TABLE schema_migrations(version INTEGER)")
    raw.execute("INSERT INTO schema_migrations VALUES (?)", (SCHEMA_VERSION,))
    for table in (
        "pipeline_templates", "pipeline_drafts", "pipeline_versions",
        "review_schema_templates", "review_schema_drafts", "review_schema_versions",
        "pipeline_version_schema_dependencies", "watch_folder_bindings",
    ):
        raw.execute(f"CREATE TABLE {table}(name TEXT)")
    raw.commit()
    raw.close()
    with open_readonly_database(db) as conn:
        assert validate_database_schema(conn).is_valid

    definition = {"schema_version": 3, "pipeline": [], "tasks": {}}
    conn = Mock()
    draft_cursor = Mock()
    draft_cursor.fetchone.return_value = {
        "definition_json": json.dumps(definition), "revision": 4, "template_key": "main"
    }
    version_cursor = Mock()
    version_cursor.fetchone.return_value = {"id": "pv1"}
    conn.execute.side_effect = [draft_cursor, version_cursor]
    validator = StoredSourceValidator(conn, runtime_config={})
    validator.facade.validate_pipeline = Mock(return_value={"findings": []})
    assert validator.validate_pipeline("main", draft=True).is_valid
    validator.validate_pipeline_version_id = Mock(return_value=ValidationResult())
    assert validator.validate_pipeline("main", version_number=1).is_valid

    schema = {"title": "Invoice", "fields": {}}
    schema_cursor = Mock()
    schema_cursor.fetchone.return_value = {
        "schema_json": json.dumps(schema), "version_number": 1,
        "content_hash": content_hash(schema), "schema_key": "invoice",
    }
    validator.conn.execute.side_effect = None
    validator.conn.execute.return_value = schema_cursor
    validator.facade.validate_review_schema = Mock(return_value={"findings": []})
    assert validator.validate_review_schema("invoice", version_number=1).is_valid

    monkeypatch.setattr(
        "tools.config_check.stored_validator.ValidationFacade.validate_review_schema",
        lambda *_args, **_kwargs: {"findings": []},
    )
    review_file = tmp_path / "portable-review.yaml"
    review_file.write_text(
        "schema_key: invoice\nversion: 2\nformat_version: 1\nschema:\n  title: Invoice\n  fields: {}\n",
        encoding="utf-8",
    )
    assert validate_portable_file(review_file, kind="review-schema").is_valid

    coordinate = ReviewSchemaCoordinate("invoice", 1, "hash")
    pipeline_doc = {
        "kind": "pipeline-bundle", "format_version": 1, "template": {},
        "definition": definition, "dependencies": {},
    }
    monkeypatch.setattr(
        "tools.config_check.stored_validator.load_document",
        lambda _path: pipeline_doc,
    )

    class CoordinateConn:
        def execute(self, *_args):
            cursor = Mock()
            cursor.fetchone.return_value = {"id": "sv1", "content_hash": "hash"}
            return cursor

    def import_bundle(document, resolve_coordinate=None):
        assert resolve_coordinate(coordinate) == "sv1"
        assert resolve_coordinate(ReviewSchemaCoordinate("invoice", 1, "other")) is None
        return document["definition"], {}

    monkeypatch.setattr("tools.config_check.stored_validator.import_pipeline_bundle", import_bundle)
    monkeypatch.setattr(
        "tools.config_check.stored_validator.ValidationFacade.validate_pipeline",
        lambda *_args, **_kwargs: {"findings": []},
    )
    assert validate_portable_file(
        tmp_path / "pipeline.yaml", kind="pipeline", conn=CoordinateConn()
    ).is_valid

    monkeypatch.setattr(
        "tools.config_check.stored_validator.load_document",
        lambda _path: (_ for _ in ()).throw(OSError("cannot read")),
    )
    assert validate_portable_file(tmp_path / "pipeline.yaml", kind="pipeline").errors[0].code == "portable-file-invalid"

    tasks_definition = {
        "schema_version": 3,
        "pipeline": [],
        "tasks": {"review": {"params": {"schema_version_id": "sv1"}}, "scalar": "bad"},
    }
    monkeypatch.setattr(
        "tools.config_check.stored_validator.load_document",
        lambda _path: {**pipeline_doc, "definition": tasks_definition},
    )

    def import_bundle_without_conn(document, resolve_coordinate=None):
        assert resolve_coordinate is None
        return document["definition"], {}

    monkeypatch.setattr(
        "tools.config_check.stored_validator.import_pipeline_bundle",
        import_bundle_without_conn,
    )
    captured = {}

    def trace(frame, event, arg):
        if frame.f_code.co_name == "validate_portable_file" and event == "line":
            resolver = frame.f_locals.get("resolve_coordinate")
            if resolver is not None:
                captured["resolver"] = resolver
        return trace

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        assert validate_portable_file(tmp_path / "pipeline.yaml", kind="pipeline").is_valid
    finally:
        sys.settrace(previous)
    assert captured["resolver"](ReviewSchemaCoordinate("invoice", 1, "hash")) is None
    assert isinstance(portable_contract_schema("runtime"), dict)


def test_portable_pipeline_dependency_mapping_is_reported(tmp_path: Path, monkeypatch) -> None:
    definition = {
        "schema_version": 3,
        "pipeline": [],
        "tasks": {"review": {"params": {"schema_version_id": "sv1"}}},
    }
    monkeypatch.setattr(
        "tools.config_check.stored_validator.load_document",
        lambda _path: {"kind": "pipeline-bundle", "definition": definition},
    )
    monkeypatch.setattr(
        "tools.config_check.stored_validator.import_pipeline_bundle",
        lambda document, resolve_coordinate=None: (document["definition"], {}),
    )
    monkeypatch.setattr(
        "tools.config_check.stored_validator.ValidationFacade.validate_pipeline",
        lambda *_args, **_kwargs: {"findings": []},
    )
    assert validate_portable_file(tmp_path / "pipeline.yaml", kind="pipeline").is_valid
