"""Existing audit events survive the processing-retention schema upgrade."""
import sqlite3
from pathlib import Path

import pytest

from modules.db.connection import connect
from modules.db.migrations import upgrade_processing_cleanup_audit
from modules.services.startup_migration_service import initialize_database
from test.helpers_sqlite import TempConfig, seed_pipeline
from test.helpers_cleanup import seed_history


def test_legacy_audit_migration_retains_rowids_payloads_and_references(tmp_path: Path) -> None:
    config = TempConfig(tmp_path / "migration.sqlite3")
    initialize_database(config)
    version = seed_pipeline(config)
    with connect(config) as conn:
        seed_history(conn, tmp_path, version["template_id"], version["id"])
        conn.execute("ALTER TABLE audit_events RENAME TO saved_audits")
        conn.execute("""CREATE TABLE audit_events (
            id TEXT PRIMARY KEY, batch_id TEXT REFERENCES batches(id),
            document_id TEXT REFERENCES documents(id), review_item_id TEXT REFERENCES review_items(id),
            user TEXT, event_type TEXT NOT NULL, event_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn.execute("INSERT INTO audit_events SELECT * FROM saved_audits")
        conn.execute("DROP TABLE saved_audits")
        conn.commit()
        before = [tuple(row) for row in conn.execute("SELECT rowid,* FROM audit_events")]
        conn.execute("DELETE FROM schema_migrations WHERE version=9")
        conn.execute("INSERT INTO schema_migrations VALUES (8,'synthetic')")
        conn.execute("DROP TABLE pipeline_cleanup_previews")
        conn.commit()
        initialize_database(config)
        upgrade_processing_cleanup_audit(conn)
        assert before == [tuple(row) for row in conn.execute("SELECT rowid,* FROM audit_events")]
        assert not conn.execute("PRAGMA foreign_key_list(audit_events)").fetchall()
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 9
        assert conn.execute("SELECT COUNT(*) FROM pipeline_cleanup_previews").fetchone()[0] == 0


def test_migration_rolls_back_when_retained_foreign_keys_are_invalid() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript("""CREATE TABLE batches(id TEXT PRIMARY KEY);
        CREATE TABLE audit_events(id TEXT PRIMARY KEY,batch_id TEXT REFERENCES batches(id),
          document_id TEXT,review_item_id TEXT,user TEXT,event_type TEXT NOT NULL,event_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE invalid_reference(batch_id TEXT REFERENCES batches(id));
        INSERT INTO invalid_reference VALUES ('missing');
        INSERT INTO audit_events VALUES ('audit',NULL,NULL,NULL,'admin','test','{}','2020');""")
    with pytest.raises(RuntimeError):
        upgrade_processing_cleanup_audit(conn)
    assert conn.execute("PRAGMA foreign_key_list(audit_events)").fetchall()
    assert conn.execute("SELECT id FROM audit_events").fetchone()[0] == "audit"
    assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='audit_events_next'").fetchall()
    conn.close()
