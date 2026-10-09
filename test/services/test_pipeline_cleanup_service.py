"""Retention eligibility, exact previews, dependency deletion, and audit safety."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterator

import pytest

from modules.db.connection import connect, json_loads, utc_now
from modules.db.repositories import AuditRepository
from modules.services.pipeline_cleanup_service import PipelineCleanupConflictError, PipelineCleanupService
from modules.services.startup_migration_service import initialize_database
from modules.services.upload_submission_service import submission_status
from test.helpers_cleanup import CUTOFF, seed_history
from test.helpers_sqlite import TempConfig, seed_pipeline

CleanupContext = tuple[sqlite3.Connection, PipelineCleanupService, dict[str, Any]]


@pytest.fixture
def context(tmp_path: Path) -> Iterator[CleanupContext]:
    config = TempConfig(tmp_path / "cleanup.sqlite3")
    initialize_database(config)
    version = seed_pipeline(config)
    with closing(connect(config)) as conn:
        yield conn, PipelineCleanupService(conn), version


def _clean(service: PipelineCleanupService, version: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    return service.cleanup(version["template_id"], preview_id=preview["preview_id"], confirmation_name="Test pipeline", user="admin")


def test_cleanup_preserves_pipeline_files_and_original_audits(context: CleanupContext, tmp_path: Path) -> None:
    conn, service, version = context
    data = seed_history(conn, tmp_path, version["template_id"], version["id"], child=True)
    original = dict(conn.execute("SELECT * FROM audit_events WHERE id=?", (data["audit"],)).fetchone())
    preview = service.preview(version["template_id"], cutoff_date=CUTOFF, user="admin")
    assert preview["counts"]["documents"] == 2
    result = _clean(service, version, preview)
    assert result["deleted"]["documents"] == 2
    for table in service.history.SCOPES:
        if table != "upload_submissions":
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert dict(conn.execute("SELECT * FROM audit_events WHERE id=?", (data["audit"],)).fetchone()) == original
    assert conn.execute("SELECT COUNT(*) FROM pipeline_versions").fetchone()[0] == 1
    assert data["file_path"].exists()
    assert submission_status(conn, "admin", data["receipt"]) == {"status": "purged"}
    event = conn.execute("SELECT event_json FROM audit_events WHERE id=?", (result["audit_event_id"],)).fetchone()[0]
    assert json_loads(event)["deleted"] == result["deleted"]
    assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    with pytest.raises(PipelineCleanupConflictError):
        _clean(service, version, preview)


@pytest.mark.parametrize(("table", "change", "reason"), [
    ("documents", "status='processing'", "active_work"),
    ("documents", "status='review_completed'", "active_work"),
    ("documents", "status='split_completed'", "active_work"),
    ("processing_jobs", "status='queued'", "active_work"),
    ("processing_jobs", "status='running'", "active_work"),
    ("task_runs", "status='running'", "active_work"),
    ("task_runs", "status='paused'", "active_work"),
    ("review_items", "status='pending'", "pending_review"),
    ("review_items", "status='in_review'", "pending_review"),
    ("manual_split_decisions", "phase='applying'", "active_work"),
    ("documents", "updated_at='2021-01-01T00:00:00+00:00'", "recent_activity"),
    ("task_runs", "ended_at='2022-01-01T00:00:00+00:00'", "recent_activity"),
    ("review_items", "updated_at='2022-01-01T00:00:00+00:00'", "recent_activity"),
    ("extracted_fields", "updated_at='2022-01-01T00:00:00+00:00'", "recent_activity"),
    ("extraction_results", "created_at='2022-01-01T00:00:00+00:00'", "recent_activity"),
    ("document_files", "created_at='2022-01-01T00:00:00+00:00'", "recent_activity"),
    ("review_locks", "expires_at='2099-01-01T00:00:00+00:00'", "pending_review"),
    ("documents", "updated_at='invalid'", "inconsistent_history"),
])
def test_cleanup_excludes_entire_batch_with_unsafe_history(
    context: CleanupContext, tmp_path: Path, table: str, change: str, reason: str,
) -> None:
    conn, service, version = context
    seed_history(conn, tmp_path, version["template_id"], version["id"])
    conn.execute(f"UPDATE {table} SET {change}")
    conn.commit()
    preview = service.preview(version["template_id"], cutoff_date=CUTOFF, user="admin")
    assert preview["counts"]["batches"] == 0
    assert preview["excluded"][reason]["batches"] == 1
    with pytest.raises(PipelineCleanupConflictError, match="No eligible"):
        _clean(service, version, preview)


def test_cleanup_blocks_active_child_and_keeps_other_pipeline(context: CleanupContext, tmp_path: Path) -> None:
    conn, service, version = context
    data = seed_history(conn, tmp_path, version["template_id"], version["id"], child=True)
    conn.execute("UPDATE documents SET status='processing' WHERE id=?", (data["child"],))
    conn.commit()
    assert service.preview(version["template_id"], cutoff_date=CUTOFF, user="admin")["counts"]["batches"] == 0
    conn.execute("UPDATE documents SET status='completed' WHERE id=?", (data["child"],))
    conn.commit()
    other_config = TempConfig(tmp_path / "cleanup.sqlite3")
    other = seed_pipeline(other_config)
    retained = seed_history(conn, tmp_path, other["template_id"], other["id"])
    _clean(service, version, service.preview(version["template_id"], cutoff_date=CUTOFF, user="admin"))
    assert conn.execute("SELECT id FROM batches").fetchone()[0] == retained["batch_id"]


def test_changed_expired_and_wrong_owner_previews_cannot_delete(context: CleanupContext, tmp_path: Path) -> None:
    conn, service, version = context
    data = seed_history(conn, tmp_path, version["template_id"], version["id"])
    preview = service.preview(version["template_id"], cutoff_date=CUTOFF, user="admin")
    with pytest.raises(PipelineCleanupConflictError):
        service.cleanup(version["template_id"], preview_id=preview["preview_id"], confirmation_name="Test pipeline", user="operator")
    with pytest.raises(ValueError, match="confirmation"):
        service.cleanup(version["template_id"], preview_id=preview["preview_id"], confirmation_name="wrong", user="admin")
    conn.execute("UPDATE extracted_fields SET final_value_json='123' WHERE id=?", (data["field"],))
    conn.commit()
    with pytest.raises(PipelineCleanupConflictError, match="changed"):
        _clean(service, version, preview)
    preview = service.preview(version["template_id"], cutoff_date=CUTOFF, user="admin")
    conn.execute("UPDATE pipeline_cleanup_previews SET expires_at='2020-01-01'")
    conn.commit()
    with pytest.raises(PipelineCleanupConflictError, match="expired"):
        _clean(service, version, preview)
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_cleanup_rolls_back_every_table_and_receipt_if_audit_fails(context: CleanupContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn, service, version = context
    data = seed_history(conn, tmp_path, version["template_id"], version["id"])
    preview = service.preview(version["template_id"], cutoff_date=CUTOFF, user="admin")
    def fail(**kwargs: Any) -> None:
        raise sqlite3.OperationalError("synthetic audit failure")
    monkeypatch.setattr(AuditRepository, "append_uncommitted", lambda self, **kwargs: fail(**kwargs))
    with pytest.raises(sqlite3.OperationalError):
        _clean(service, version, preview)
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    assert submission_status(conn, "admin", data["receipt"])["status"] == "accepted"
    assert service.history.get_preview(preview["preview_id"])


@pytest.mark.parametrize("cutoff", ["invalid", "2099-01-01", "20200101", "", None])
def test_invalid_cutoffs_are_rejected(context: CleanupContext, cutoff: str) -> None:
    _, service, version = context
    with pytest.raises(ValueError):
        service.preview(version["template_id"], cutoff_date=cutoff, user="admin")


def test_cleanup_protects_mixed_pipeline_and_cross_batch_children(context: CleanupContext, tmp_path: Path) -> None:
    conn, service, version = context
    data = seed_history(conn, tmp_path, version["template_id"], version["id"])
    other = seed_pipeline(TempConfig(tmp_path / "cleanup.sqlite3"))
    retained = seed_history(conn, tmp_path, other["template_id"], other["id"])
    conn.execute("UPDATE documents SET parent_document_id=? WHERE id=?", (data["document_id"], retained["document_id"]))
    conn.commit()
    assert service.preview(version["template_id"], cutoff_date=CUTOFF, user="admin")["excluded"]["inconsistent_history"]["batches"] == 1
    assert service.preview(other["template_id"], cutoff_date=CUTOFF, user="admin")["excluded"]["inconsistent_history"]["batches"] == 1
    conn.execute("UPDATE documents SET parent_document_id=NULL WHERE id=?", (retained["document_id"],))
    conn.execute("""INSERT INTO documents(id,batch_id,pipeline_template_id,pipeline_version_id,file_path,status,created_at,updated_at)
        VALUES ('mixed-document',?,?,?,'synthetic.pdf','completed','2020-01-01','2020-01-01')""",
        (retained["batch_id"], version["template_id"], version["id"]))
    conn.commit()
    assert service.preview(other["template_id"], cutoff_date=CUTOFF, user="admin")["counts"]["batches"] == 0


def test_cleanup_rolls_back_when_another_batch_references_a_selected_task(context: CleanupContext, tmp_path: Path) -> None:
    conn, service, version = context
    data = seed_history(conn, tmp_path, version["template_id"], version["id"])
    other = seed_pipeline(TempConfig(tmp_path / "cleanup.sqlite3"))
    retained = seed_history(conn, tmp_path, other["template_id"], other["id"])
    conn.execute("UPDATE extraction_results SET task_run_id=? WHERE id=?", (data["run"], retained["result"]))
    conn.commit()
    preview = service.preview(version["template_id"], cutoff_date=CUTOFF, user="admin")
    with pytest.raises(PipelineCleanupConflictError, match="Retained records"):
        _clean(service, version, preview)
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2
    assert submission_status(conn, "admin", data["receipt"])["status"] == "accepted"
