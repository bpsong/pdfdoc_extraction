"""Watch-folder lifecycle regression tests with isolated SQLite data."""

from pathlib import Path

import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.ingress_binding_service import IngressBindingConflictError, IngressBindingService
from test.services.test_watch_folder_coordinator import build_context
from test.services.test_ingestion_assignment_service import publish_pipeline
from modules.db.repositories import WatchFolderBindingRepository
from modules.services.watch_folder_coordinator import WatchFolderCoordinator


def test_unbind_retire_and_reuse_path(tmp_path: Path) -> None:
    config = build_context(tmp_path)
    folder = tmp_path / "incoming"
    folder.mkdir()
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="lifecycle")
        service = IngressBindingService(conn, config)
        binding = service.create(folder_path=str(folder), pipeline_version_id=version["id"], enabled=True, user="admin")
        unbound = service.update(binding["id"], action="unbind", expected_revision=1, user="admin")
        assert unbound["state"] == "unbound"
        assert unbound["pipeline_version_id"] is None
        with pytest.raises(IngressBindingConflictError, match="changed"):
            service.update(binding["id"], action="pause", expected_revision=1, user="admin")
        service.update(binding["id"], pipeline_version_id=version["id"], enabled=True, user="admin")
        retired = service.update(binding["id"], action="retire", user="admin")
        assert retired["state"] == "retired"
        assert not retired["enabled"]
        replacement = service.create(folder_path=str(folder), pipeline_version_id=version["id"], enabled=True, user="admin")
        assert replacement["id"] != binding["id"]
        with pytest.raises(IngressBindingConflictError, match="Retired"):
            service.update(binding["id"], action="resume", user="admin")


def test_emergency_actions_and_idempotent_migration(tmp_path: Path) -> None:
    config = build_context(tmp_path)
    folder = tmp_path / "incoming"
    folder.mkdir()
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="emergency")
        service = IngressBindingService(conn, config)
        binding = service.create(folder_path=str(folder), pipeline_version_id=version["id"], enabled=True, user="admin")
        folder.rmdir()
        paused = service.update(binding["id"], action="pause", user="admin")
        assert paused["state"] == "paused"
        service.update(binding["id"], action="unbind", user="admin")
        service.update(binding["id"], action="pause", user="admin")
        service.update(binding["id"], action="retire", user="admin")
    initialize_database(config)
    initialize_database(config)
    with connect(config) as conn:
        row = conn.execute("SELECT * FROM watch_folder_bindings WHERE id = ?", (binding["id"],)).fetchone()
        assert row["retired_at"]
        assert row["revision"] == 5
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_claim_rechecks_pause_and_assignment_and_keeps_history(tmp_path: Path) -> None:
    config = build_context(tmp_path)
    folder = tmp_path / "incoming"
    folder.mkdir()
    with connect(config) as conn:
        _, first = publish_pipeline(conn, key="first")
        _, second = publish_pipeline(conn, key="second")
        service = IngressBindingService(conn, config)
        old = service.create(folder_path=str(folder), pipeline_version_id=first["id"], enabled=True, user="admin")
    coordinator = WatchFolderCoordinator(config)
    source = folder / "synthetic.pdf"
    source.write_bytes(b"%PDF-1.4\nsynthetic")
    with connect(config) as conn:
        IngressBindingService(conn, config).update(old["id"], action="pause", user="admin")
    assert not coordinator._claim_and_process(source, old)
    assert source.exists()
    with connect(config) as conn:
        service = IngressBindingService(conn, config)
        service.update(old["id"], pipeline_version_id=second["id"], enabled=True, user="admin")
    assert coordinator._claim_and_process(source, old)
    with connect(config) as conn:
        service = IngressBindingService(conn, config)
        service.update(old["id"], action="unbind", user="admin")
        service.update(old["id"], action="retire", user="admin")
        batch = conn.execute("SELECT * FROM batches").fetchone()
        assert batch["pipeline_version_id"] == second["id"]
        assert "source_folder" in batch["metadata_json"]
        with pytest.raises(IngressBindingConflictError, match="cannot be deleted"):
            service.delete(old["id"], user="admin")
        assert service.bindings.activity(old["id"])["batches"][0]["id"] == batch["id"]


def test_health_checks_are_non_ingesting_and_do_not_change_revision(tmp_path: Path) -> None:
    config = build_context(tmp_path)
    folder = tmp_path / "incoming"
    folder.mkdir()
    source = folder / "synthetic.pdf"
    source.write_bytes(b"%PDF-1.4\nsynthetic")
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="health")
        service = IngressBindingService(conn, config)
        binding = service.create(folder_path=str(folder), pipeline_version_id=version["id"], enabled=True, user="admin")
        assert service.management_list()[0]["health_status"] == "stale"
        assert service.check_access(str(folder))["ok"]
        assert not service.check_access(str(folder / "missing"))["ok"]
        assert source.exists()
        assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 0
        service.bindings.record_health(binding["id"], issue=None)
        assert service.management_list()[0]["health_status"] == "healthy"
        assert service.bindings.get(binding["id"])["revision"] == 1
        service.bindings.record_health(binding["id"], issue="Cannot list folder")
        assert service.management_list()[0]["health_status"] == "unhealthy"


def test_v6_migration_preserves_referenced_binding(tmp_path: Path) -> None:
    from modules.db.migrations import prepare_versioned_config_schema
    from modules.db.connection import utc_now
    from modules.services.ingestion_assignment_service import IngestionAssignmentService
    from test.helpers_sqlite import TempConfig

    config = TempConfig(tmp_path / "legacy.sqlite3", {"pipeline_secrets": {"test-api": "synthetic"}})
    folder = tmp_path / "incoming"
    folder.mkdir()
    with connect(config) as conn:
        prepare_versioned_config_schema(conn)
        for version_number in (2, 3, 4, 6):
            conn.execute("INSERT INTO schema_migrations VALUES (?,?)", (version_number, utc_now()))
        conn.commit()
        _, version = publish_pipeline(conn, key="migration")
        service = IngressBindingService(conn, config)
        binding = service.create(folder_path=str(folder), pipeline_version_id=version["id"], enabled=True, user="admin")
        source = folder / "migration.pdf"
        source.write_bytes(b"%PDF-1.4\nsynthetic")
        IngestionAssignmentService(conn, config).create_batch(pipeline_version_id=version["id"], role="system", source="watch_folder", assignment_source="watch_folder", files=[{"file_path": str(source), "original_filename": source.name}], user=None, ingress_binding_id=binding["id"])
    initialize_database(config)
    initialize_database(config)
    with connect(config) as conn:
        migrated = WatchFolderBindingRepository(conn).get(binding["id"])
        for key in ("id", "folder_path", "normalized_path", "pipeline_version_id", "enabled", "created_at"):
            assert migrated[key] == binding[key]
        assert migrated["revision"] == 1
        assert conn.execute("SELECT ingress_binding_id FROM batches").fetchone()[0] == binding["id"]
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_frontend_filter_and_validation_helpers() -> None:
    import subprocess

    script = """
    const assert = require('node:assert/strict');
    const {filterBindings, validateForm} = require('./web/static/js/watch_folder_view_models.js');
    const rows = [{folder_path:'C:/Invoices',pipeline:{name:'Invoice'},state:'enabled',health_status:'healthy',update_available:true},
                  {folder_path:'C:/Old',state:'retired',health_status:'retired',update_available:false}];
    assert.equal(filterBindings(rows,{}).length,1);
    assert.equal(filterBindings(rows,{retired:true}).length,2);
    assert.equal(filterBindings(rows,{search:'INVOICE',updates:true,health:'healthy'}).length,1);
    assert.equal(filterBindings(rows,{status:'paused'}).length,0);
    assert.ok(validateForm('', '', '', false));
    assert.ok(validateForm('C:/Invoices', '', '', true));
    assert.equal(validateForm('C:/Invoices', '', '', false),'');
    """
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
