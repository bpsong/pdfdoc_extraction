"""Focused tests for legacy migration helpers and defensive branches."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

import modules.services.legacy_versioned_config_migration as migration
from modules.services.legacy_versioned_config_migration import (
    LegacyVersionedConfigMigration,
    LegacyVersionedConfigMigrationError,
)


class ConfigStub:
    def __init__(self, values=None, path=None):
        self.values = values or {}
        self._config_path = path

    def get(self, key, default=None):
        value = self.values
        for part in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part, default)
        return value

    def get_all(self):
        return self.values


def _bare(config=None):
    obj = object.__new__(LegacyVersionedConfigMigration)
    obj.original_config = config or {}
    obj.updated_config = dict(obj.original_config)
    obj.schema_sources = {}
    obj.skipped_schema_files = []
    obj.config_path = None
    obj.config_replaced = False
    obj.original_bytes = None
    obj.original_mode = None
    return obj


def test_migration_pure_helpers_cover_aliases_and_file_formats(tmp_path: Path) -> None:
    assert migration._terminal_status("pipeline-completed-successfully")
    assert migration._terminal_status("completed_with_error")
    assert not migration._terminal_status("still-running")
    assert migration._slug("123 ???", fallback="schema") == "schema-123"
    assert migration._slug("!!!", fallback="schema") == "schema"

    json_file = tmp_path / "schema.json"
    json_file.write_text(json.dumps({"title": "JSON"}), encoding="utf-8")
    yaml_file = tmp_path / "schema.yaml"
    yaml_file.write_text("title: YAML\n", encoding="utf-8")
    assert migration._load_schema_file(json_file)["title"] == "JSON"
    assert migration._load_schema_file(yaml_file)["title"] == "YAML"
    yaml_file.write_text("- not an object\n", encoding="utf-8")
    with pytest.raises(ValueError, match="root"):
        migration._load_schema_file(yaml_file)


def test_raw_config_fallbacks_and_atomic_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file_path = tmp_path / "config.yaml"
    file_path.write_text("items: [1]\n", encoding="utf-8")
    assert migration._raw_config(ConfigStub(path=file_path)) == {"items": [1]}
    assert migration._raw_config(ConfigStub({"all": {"value": 1}})) == {"all": {"value": 1}}
    fallback = ConfigStub({"pipeline": ["x"], "tasks": {"x": {}}, "pipeline_secrets": {"s": 1}}, path=tmp_path / "missing.yaml")
    assert migration._raw_config(fallback)["pipeline"] == ["x"]

    bad = tmp_path / "bad.yaml"
    bad.write_text("- scalar\n", encoding="utf-8")
    with pytest.raises(LegacyVersionedConfigMigrationError, match="root"):
        migration._raw_config(ConfigStub(path=bad))

    output = tmp_path / "nested" / "out.yaml"
    migration._write_atomic(output, b"hello", None)
    assert output.read_bytes() == b"hello"

    fallback = ConfigStub({"pipeline": ["p"], "tasks": {"p": {}}, "pipeline_secrets": {"key": "value"}})
    fallback.get_all = lambda: []
    assert migration._raw_config(fallback) == {
        "pipeline": ["p"], "tasks": {"p": {}}, "pipeline_secrets": {"key": "value"}
    }


def test_atomic_write_cleans_temporary_file_after_replace_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "out.yaml"
    monkeypatch.setattr(migration.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        migration._write_atomic(output, b"x", None)
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_tolerates_cleanup_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "out.yaml"
    monkeypatch.setattr(migration.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace failed")))
    monkeypatch.setattr(Path, "unlink", Mock(side_effect=OSError("locked")))
    with pytest.raises(OSError, match="replace failed"):
        migration._write_atomic(output, b"x", None)


def test_legacy_definition_and_secret_extraction_validation() -> None:
    with pytest.raises(LegacyVersionedConfigMigrationError):
        _bare({"pipeline": "bad", "tasks": {}})._legacy_definition()
    with pytest.raises(LegacyVersionedConfigMigrationError):
        _bare({"pipeline": [""], "tasks": {}})._legacy_definition()
    with pytest.raises(LegacyVersionedConfigMigrationError):
        _bare({"pipeline": ["missing"], "tasks": {}})._legacy_definition()
    assert _bare({"pipeline": [], "tasks": {}})._legacy_definition() is None

    obj = _bare()
    secrets = {"existing": "value", "default-processing-task-params-key": "old"}
    tasks = {"task": {"params": {"api_key": "new", "token": {"$secret": "existing"}, "values": ["x", {"password": "p2"}]}}}
    transformed = obj._extract_task_secrets(tasks, secrets)
    assert transformed["task"]["params"]["token"] == {"$secret": "existing"}
    assert transformed["task"]["params"]["api_key"]["$secret"]
    with pytest.raises(LegacyVersionedConfigMigrationError, match="deployment"):
        obj._extract_task_secrets({"t": {"api_key": {"$secret": "missing"}}}, secrets)


def test_schema_hash_and_snapshot_helpers() -> None:
    obj = _bare()
    assert obj._find_schema_hashes({"schema_hash": "a", "nested": [{"schema_version": "b"}]}) == {"a", "b"}
    assert obj._find_schema_hashes("scalar") == set()
    steps = [{"key": "a", "module": "m", "class": "C", "on_error": None}, "bad"]
    assert obj._snapshot_signature({"steps": steps}) == [("a", "m", "C", None)]
    assert obj._snapshot_signature({"steps": "bad"}) == []
    assert not obj._valid_legacy_snapshot(None, [])
    assert not obj._valid_legacy_snapshot({"content_hash": "x", "steps": "bad"}, [])
    snapshot = {"steps": [{"position": 1, "key": "a", "module": "m", "class": "C", "on_error": None, "label": "A"}]}
    legacy_basis = "1:a:m:C:"
    snapshot["content_hash"] = migration.hashlib.sha256(legacy_basis.encode()).hexdigest()
    assert obj._valid_legacy_snapshot(snapshot, obj._snapshot_signature(snapshot))


def test_reference_schema_path_errors_and_runtime_config_application(tmp_path: Path) -> None:
    obj = _bare({"pipeline": ["review"], "tasks": {"review": {"class": "ReviewGateTask", "params": {"schema_file": "missing.yaml"}}}})
    obj.conn = SimpleNamespace(execute=lambda *_args: SimpleNamespace(fetchone=lambda: None))
    obj.schema_service = SimpleNamespace(_resolve_schema_path=lambda _name: None)
    with pytest.raises(LegacyVersionedConfigMigrationError, match="schema file"):
        obj._referenced_schema_paths(obj._legacy_definition())

    obj = _bare({"pipeline": ["review"], "tasks": {"review": {"class": "ReviewGateTask", "params": {"schema_version_id": "v1"}}}})
    obj.conn = SimpleNamespace(execute=lambda *_args: SimpleNamespace(fetchone=lambda: None))
    with pytest.raises(LegacyVersionedConfigMigrationError, match="schema version"):
        obj._referenced_schema_paths(obj._legacy_definition())

    config = ConfigStub({"pipeline": ["old"], "tasks": {"old": {}}, "pipeline_secrets": {}})
    obj = _bare(config.values)
    obj.config = config
    obj.apply_runtime_config()
    assert config.values["pipeline"] == ["old"]


def test_migration_reference_discovery_and_transform_defensive_paths(tmp_path: Path, monkeypatch) -> None:
    obj = _bare()
    obj.conn = Mock()
    obj.schema_service = Mock()
    assert obj._referenced_schema_paths(None) == set()
    obj.schema_service._resolve_schema_path.side_effect = OSError("bad path")
    definition = {"pipeline": ["review"], "tasks": {"review": {"class": "ReviewGateTask", "params": {"schema_file": "schema.yaml"}}}}
    with pytest.raises(LegacyVersionedConfigMigrationError, match="schema file"):
        obj._referenced_schema_paths(definition)
    obj.schema_service._resolve_schema_path.side_effect = None
    obj.schema_service._resolve_schema_path.return_value = None
    with pytest.raises(LegacyVersionedConfigMigrationError, match="no legacy schema"):
        obj._referenced_schema_paths({"pipeline": ["review"], "tasks": {"review": {"class": "ReviewGateTask", "params": {}}}})
    assert obj._transform_definition(None) is None
    obj.schema_service._resolve_schema_path.return_value = None
    with pytest.raises(LegacyVersionedConfigMigrationError, match="dependency"):
        obj._transform_definition(definition)

    unreadable = tmp_path / "schemas"
    unreadable.mkdir()
    obj.schema_service.schema_directories.return_value = [unreadable]
    original_iterdir = type(unreadable).iterdir
    monkeypatch.setattr(type(unreadable), "iterdir", lambda _path: (_ for _ in ()).throw(OSError("list")))
    assert obj._discover_schema_files() == []

    schema_file = tmp_path / "schema.json"
    schema_file.write_text('{"title": "Schema"}', encoding="utf-8")
    monkeypatch.setattr(type(unreadable), "iterdir", original_iterdir)
    obj.schema_service.schema_directories.return_value = [tmp_path]
    monkeypatch.setattr(migration, "_canonical_path", Mock(side_effect=OSError("resolve")))
    assert obj._discover_schema_files() == []


def test_migration_schema_import_collision_and_partial_state_paths(tmp_path: Path, monkeypatch) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text('{"title": "Schema", "fields": {}}', encoding="utf-8")
    schema = {"title": "Schema", "fields": {}}
    obj = _bare()
    obj.conn = Mock()
    obj.conn.execute.return_value.fetchall.return_value = [{"schema_key": "schema"}]
    obj.validation = Mock()
    obj.validation.validate_review_schema.return_value = {"valid": True}
    obj._discover_schema_files = Mock(return_value=[("schema", schema_path)])

    fake = Mock()
    fake.templates.get_by_key.side_effect = [
        {"id": "old"},
        None,
        None,
    ]
    fake.versions.list_for_owner.return_value = []
    fake.create_template.return_value = {"template": {"id": "new", "status": "active"}}
    fake.publish.return_value = {"version": {"id": "v1", "content_hash": migration.content_hash(schema)}}
    monkeypatch.setattr(migration, "ReviewSchemaVersionService", lambda _conn: fake)
    obj._import_schemas(set())
    assert "schema" in obj.schema_sources

    obj = _bare()
    obj.conn = Mock()
    obj.conn.execute.return_value.fetchall.return_value = [{"schema_key": "schema"}]
    obj.validation = Mock()
    obj.validation.validate_review_schema.return_value = {"valid": True}
    obj._discover_schema_files = Mock(return_value=[("schema", schema_path)])
    conflict = Mock()
    conflict.templates.get_by_key.return_value = {"id": "old"}
    conflict.versions.list_for_owner.return_value = [{"content_hash": "wrong"}]
    monkeypatch.setattr(migration, "ReviewSchemaVersionService", lambda _conn: conflict)
    with pytest.raises(LegacyVersionedConfigMigrationError, match="conflicts"):
        obj._import_schemas(set())

    inconsistent = Mock()
    inconsistent.templates.get_by_key.return_value = {"id": "old"}
    inconsistent.versions.list_for_owner.return_value = [{"id": "v1", "content_hash": migration.content_hash(schema)}]
    inconsistent.load_version.return_value = {"id": "v1", "content_hash": migration.content_hash(schema)}
    inconsistent.drafts.get.return_value = None
    monkeypatch.setattr(migration, "ReviewSchemaVersionService", lambda _conn: inconsistent)
    with pytest.raises(LegacyVersionedConfigMigrationError, match="inconsistent draft"):
        obj._import_schemas(set())

    obj._discover_schema_files.return_value = []
    with pytest.raises(LegacyVersionedConfigMigrationError, match="could not be imported"):
        obj._import_schemas({"missing"})


def test_migration_default_pipeline_partial_states(tmp_path: Path, monkeypatch) -> None:
    definition = {"schema_version": 1, "pipeline": [], "tasks": {}}
    expected = migration.content_hash(definition)

    class FakePipelineService:
        def __init__(self, *_args, **_kwargs):
            self.templates = Mock()
            self.versions = Mock()
            self.drafts = Mock()
            self.publish = Mock()
            self.update_template = Mock()

    obj = _bare()
    obj.conn = Mock()
    fake = FakePipelineService()
    fake.templates.get_by_key.return_value = {"id": "t", "status": "active"}
    fake.versions.list_for_owner.return_value = [{"content_hash": "wrong"}]
    monkeypatch.setattr(migration, "PipelineTemplateService", lambda *_args, **_kwargs: fake)
    with pytest.raises(LegacyVersionedConfigMigrationError, match="conflicts"):
        obj._ensure_default_pipeline(definition)

    fake.versions.list_for_owner.return_value = [{"id": "v", "content_hash": expected}]
    fake.load_version = Mock(return_value={"id": "v", "content_hash": expected, "display_snapshot": {}})
    fake.drafts.get.return_value = None
    with pytest.raises(LegacyVersionedConfigMigrationError, match="inconsistent"):
        obj._ensure_default_pipeline(definition)

    fake.versions.list_for_owner.return_value = []
    fake.drafts.get.return_value = None
    with pytest.raises(LegacyVersionedConfigMigrationError, match="conflicts"):
        obj._ensure_default_pipeline(definition)

    fake.drafts.get.return_value = {"content_hash": expected, "revision": 1}
    fake.publish.return_value = {"version": {"id": "v", "content_hash": expected, "display_snapshot": {}}}
    fake.templates.get_by_key.return_value = {"id": "t", "status": "inactive"}
    from modules.services.pipeline_template_service import PipelineTemplateConflictError
    fake.update_template.side_effect = PipelineTemplateConflictError("cannot activate")
    with pytest.raises(LegacyVersionedConfigMigrationError, match="activated"):
        obj._ensure_default_pipeline(definition)


def test_migration_invariants_and_backfill_guards() -> None:
    obj = _bare()

    def cursor(value):
        return SimpleNamespace(fetchone=lambda: value, fetchall=lambda: [])

    for index, message in enumerate((
        "Batch and document", "Task-run pipeline", "Split-child", "Review-item", "Foreign-key"
    )):
        obj.conn = Mock()
        cursors = [cursor(None)] * 5
        if index < 4:
            cursors[index] = cursor({"bad": 1})
        else:
            cursors[4] = SimpleNamespace(fetchone=lambda: None, fetchall=lambda: [("bad",)])
        obj.conn.execute.side_effect = cursors
        with pytest.raises(LegacyVersionedConfigMigrationError, match=message):
            obj._verify_invariants()

    obj.conn = Mock()
    obj.conn.execute.return_value.fetchone.return_value = None
    assert obj._has_unassigned_work() is False
    obj.conn.execute.return_value.fetchone.return_value = {"id": "b"}
    assert obj._has_unassigned_work() is True
    obj.conn.execute.return_value = []
    assert obj._config_versions_fingerprint() == []

    obj.schema_sources = {"schema": {"version": {"id": "v", "content_hash": "current"}, "legacy_hash": "legacy"}}
    obj.conn.execute.return_value = SimpleNamespace(fetchall=lambda: [{"task_key": "other", "output_json": "{}"}])
    obj._verify_task_run_schema_hashes(batch_id="b", terminal=False, dependencies={"review": "v"})

    obj.conn.execute.return_value = SimpleNamespace(fetchall=lambda: [{"id": "item", "task_key": None, "metadata_json": "{}"}])
    with pytest.raises(LegacyVersionedConfigMigrationError, match="ambiguous"):
        obj._backfill_review_items(batch_id="b", terminal=False, dependencies={"review": "v1", "other": "v2"})
    obj.conn.execute.return_value = SimpleNamespace(fetchall=lambda: [{"id": "item", "task_key": None, "metadata_json": '{"schema_hash":"wrong"}'}])
    obj.schema_sources = {"schema": {"version": {"id": "v1", "content_hash": "current"}, "legacy_hash": "legacy"}}
    obj._backfill_review_items(batch_id="b", terminal=True, dependencies={"review": "v1"})

    obj.config_path = None
    obj._replace_config_if_needed()
    assert obj._valid_legacy_snapshot({"content_hash": "x", "steps": []}, [("different",)]) is False


def test_migration_runtime_and_partial_state_guards(tmp_path: Path, monkeypatch) -> None:
    obj = _bare()
    obj.config = SimpleNamespace(
        config={},
        _values={},
    )
    obj.updated_config = {
        "pipeline": ["new"],
        "tasks": {"new": {}},
        "pipeline_secrets": {"key": "value"},
    }
    obj.apply_runtime_config()
    assert obj.config.config["pipeline"] == ["new"]
    assert obj.config._values["pipeline_secrets"] == {"key": "value"}

    monkeypatch.setattr(migration, "_write_atomic", Mock(side_effect=OSError("compensation")))
    obj.config_path = tmp_path / "config.yaml"
    obj.original_bytes = b"old"
    obj.config_replaced = True
    with pytest.raises(LegacyVersionedConfigMigrationError, match="compensation"):
        obj.compensate_config()

    obj = _bare()
    obj._legacy_definition = Mock(return_value=None)
    obj._referenced_schema_paths = Mock(return_value=set())
    obj._import_schemas = Mock()
    obj._transform_definition = Mock(return_value=None)
    obj._has_unassigned_work = Mock(return_value=True)
    obj.conn = Mock()
    obj._config_versions_fingerprint = Mock(return_value=[])
    with pytest.raises(LegacyVersionedConfigMigrationError, match="active pipeline definition"):
        obj.run()

    obj = _bare()
    obj._legacy_definition = Mock(return_value={"pipeline": [], "tasks": {}})
    obj._referenced_schema_paths = Mock(return_value=set())
    obj._import_schemas = Mock()
    obj._transform_definition = Mock(return_value={"pipeline": [], "tasks": {}})
    obj._ensure_default_pipeline = Mock(return_value={"version_id": "v1", "display_snapshot": {}})
    obj._gate_and_backfill = Mock()
    obj._verify_invariants = Mock()
    obj._config_versions_fingerprint = Mock(side_effect=[[], [("changed",)]])
    obj.conn = Mock()
    with pytest.raises(LegacyVersionedConfigMigrationError, match="history changed"):
        obj.run()


def test_migration_discovery_secret_collision_and_terminal_skips(tmp_path: Path, monkeypatch) -> None:
    obj = _bare()
    obj.schema_service = Mock()
    not_directory = tmp_path / "schema.json"
    not_directory.write_text("{}", encoding="utf-8")
    obj.schema_service.schema_directories.return_value = [not_directory]
    assert obj._discover_schema_files() == []

    directory = tmp_path / "schemas"
    directory.mkdir()
    (directory / "ignore.txt").write_text("x", encoding="utf-8")
    (directory / "nested.json").mkdir()
    obj.schema_service.schema_directories.return_value = [directory]
    assert obj._discover_schema_files() == []

    secrets = {"default-processing-t-params-api-key": "old"}
    transformed = obj._extract_task_secrets(
        {"t": {"params": {"api_key": "new"}}}, secrets
    )
    assert transformed["t"]["params"]["api_key"]["$secret"].endswith("-2")

    obj.conn = Mock()
    obj.conn.execute.side_effect = [
        [{"id": "batch", "pipeline_version_id": "already"}],
        SimpleNamespace(fetchall=lambda: []),
    ]
    obj._gate_and_backfill(
        {"template_id": "t", "version_id": "v", "display_snapshot": {}}
    )

    obj.conn.execute.side_effect = None
    obj.conn.execute.return_value = SimpleNamespace(
        fetchall=lambda: [{"id": "item", "task_key": None, "metadata_json": "{}"}]
    )
    obj._backfill_review_items(
        batch_id="b", terminal=True, dependencies={"review": "v1", "other": "v2"}
    )
