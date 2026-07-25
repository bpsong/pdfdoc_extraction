"""Database contract tests for versioned pipeline and review configuration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database, prepare_versioned_config_schema
from modules.db.repositories import (
    PipelineDraftRepository,
    PipelineTemplateRepository,
    PipelineVersionRepository,
)
from modules.services.versioned_config_contracts import canonical_json_text, content_hash


class TempConfig:
    def __init__(self, config_path: Path, db_path: Path) -> None:
        self._config_path = config_path
        self._values = {"database.path": str(db_path)}

    def get(self, key, default=None):
        return self._values.get(key, default)


@pytest.fixture
def conn(tmp_path):
    config = TempConfig(tmp_path / "config.yaml", tmp_path / "state.sqlite3")
    initialize_database(config)
    with connect(config) as connection:
        yield connection


def test_initialize_creates_versioned_tables_columns_and_indexes(conn):
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {
        "review_schema_templates",
        "review_schema_versions",
        "review_schema_drafts",
        "pipeline_templates",
        "pipeline_versions",
        "pipeline_drafts",
        "pipeline_version_schema_dependencies",
        "watch_folder_bindings",
    } <= tables

    batch_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(batches)").fetchall()
    }
    assert {
        "pipeline_template_id",
        "pipeline_version_id",
        "pipeline_assignment_source",
        "ingress_binding_id",
    } <= batch_columns

    index_names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    }
    assert "idx_pipeline_versions_template" in index_names
    assert "idx_review_schema_versions_template" in index_names


def test_prepare_upgrades_a_legacy_database_idempotently(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    legacy = sqlite3.connect(db_path)
    legacy.row_factory = sqlite3.Row
    legacy.executescript(
        """
        CREATE TABLE batches (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, original_filename TEXT,
            status TEXT NOT NULL, total_documents INTEGER NOT NULL DEFAULT 0,
            completed_documents INTEGER NOT NULL DEFAULT 0,
            failed_documents INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        """
    )
    prepare_versioned_config_schema(legacy)
    prepare_versioned_config_schema(legacy)
    columns = {
        row["name"] for row in legacy.execute("PRAGMA table_info(batches)").fetchall()
    }
    legacy.close()

    assert "pipeline_version_id" in columns
    assert "pipeline_assignment_source" in columns


def test_published_pipeline_rows_and_template_key_are_immutable(conn):
    templates = PipelineTemplateRepository(conn)
    drafts = PipelineDraftRepository(conn)
    versions = PipelineVersionRepository(conn)
    definition = {"schema_version": 1, "pipeline": ["extract"]}
    encoded = canonical_json_text(definition)

    template = templates.create(
        template_key="invoice",
        name="Invoice",
        description="",
        document_type="invoice",
        operator_instructions="",
        status="inactive",
        operator_selectable=True,
        user="admin",
    )
    drafts.create(
        template_id=template["id"],
        definition_json=encoded,
        content_hash=content_hash(definition),
        user="admin",
    )
    version = versions.create(
        template_id=template["id"],
        version_number=1,
        schema_version=1,
        definition_json=encoded,
        content_hash=content_hash(definition),
        display_snapshot_json="{}",
        validation_summary_json="{}",
        user="admin",
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute(
            "UPDATE pipeline_versions SET definition_json = '{}' WHERE id = ?",
            (version["id"],),
        )
    conn.rollback()

    with pytest.raises(sqlite3.IntegrityError, match="key is immutable"):
        conn.execute(
            "UPDATE pipeline_templates SET template_key = 'changed' WHERE id = ?",
            (template["id"],),
        )
    conn.rollback()


def test_pipeline_assignment_cannot_be_changed_after_it_is_set(conn):
    now = "2026-07-25T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO pipeline_templates(
            id, template_key, name, status, created_at, updated_at
        ) VALUES ('template', 'invoice', 'Invoice', 'inactive', ?, ?)
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO pipeline_versions(
            id, template_id, version_number, schema_version, definition_json,
            content_hash, display_snapshot_json, published_at
        ) VALUES ('version', 'template', 1, 1, '{}', 'hash', '{}', ?)
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO batches(
            id, source, status, pipeline_template_id, pipeline_version_id,
            pipeline_assignment_source, created_at, updated_at
        ) VALUES ('batch', 'upload', 'pending', 'template', 'version', 'upload', ?, ?)
        """,
        (now, now),
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="assignment is immutable"):
        conn.execute(
            "UPDATE batches SET pipeline_version_id = NULL WHERE id = 'batch'"
        )
    conn.rollback()


def test_draft_base_version_must_belong_to_same_template(conn):
    now = "2026-07-25T00:00:00+00:00"
    for template_id, key in (("one", "one"), ("two", "two")):
        conn.execute(
            """
            INSERT INTO pipeline_templates(
                id, template_key, name, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'inactive', ?, ?)
            """,
            (template_id, key, key, now, now),
        )
    conn.execute(
        """
        INSERT INTO pipeline_versions(
            id, template_id, version_number, schema_version, definition_json,
            content_hash, display_snapshot_json, published_at
        ) VALUES ('one-v1', 'one', 1, 1, '{}', 'hash', '{}', ?)
        """,
        (now,),
    )
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute(
            """
            INSERT INTO pipeline_drafts(
                template_id, revision, base_version_id, definition_json,
                content_hash, updated_at
            ) VALUES ('two', 1, 'one-v1', '{}', 'hash', ?)
            """,
            (now,),
        )
    conn.rollback()
