"""Version-2 YAML/state cutover tests for schema migration 3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

import pytest
import yaml

from modules.db.connection import connect, json_loads, utc_now
from modules.db.migrations import initialize_database, prepare_versioned_config_schema
from modules.db.repositories import ReviewRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from modules.services.legacy_versioned_config_migration import (
    LegacyVersionedConfigMigrationError,
)
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.processing_state_service import build_pipeline_snapshot


SECRET_VALUE = "synthetic-migration-secret"


class MigrationConfig:
    """File-backed config provider without ConfigManager singleton behavior."""

    def __init__(self, path: Path) -> None:
        self._config_path = path
        self.config = yaml.safe_load(path.read_text(encoding="utf-8"))

    def get(self, key: str, default=None):
        value = self.config
        for part in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part, default)
        return value

    def get_all(self):
        return self.config


def _schema(title: str = "Invoice") -> dict:
    return {
        "title": title,
        "fields": {"supplier": {"type": "string", "label": "Supplier"}},
    }


def _legacy_config(
    tmp_path: Path,
    *,
    review_tasks: int = 1,
    schema_dirs: list[str] | None = None,
) -> MigrationConfig:
    tasks = {
        "extract": {
            "label": "Extract",
            "module": "standard_step.extraction.extract_pdf",
            "class": "ExtractPdfTask",
            "params": {
                "api_key": SECRET_VALUE,
                "fields": {"supplier": {"alias": "Supplier", "type": "str"}},
            },
            "on_error": "stop",
        }
    }
    pipeline = ["extract"]
    for index in range(review_tasks):
        key = f"review_{index + 1}"
        tasks[key] = {
            "module": "standard_step.review.review_gate",
            "class": "ReviewGateTask",
            "params": {
                "confidence_threshold": 0.8,
                "review_scope": "low_confidence_fields",
                "schema_file": "invoice.yaml",
            },
        }
        pipeline.append(key)
    values = {
        "database": {"path": str(tmp_path / "app.sqlite3")},
        "schema": {"directories": schema_dirs or ["schemas"]},
        "pipeline": pipeline,
        "tasks": tasks,
    }
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(values, sort_keys=False), encoding="utf-8"
    )
    return MigrationConfig(path)


def _prepare_v2(config: MigrationConfig) -> None:
    with connect(config) as conn:
        prepare_versioned_config_schema(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (2, ?)",
            (utc_now(),),
        )
        conn.commit()


def _seed_legacy_batch(
    config: MigrationConfig,
    *,
    status: str,
    snapshot: dict | None,
    schema_hash: str | None = None,
    task_output_hash: str | None = None,
) -> dict:
    source = config._config_path.parent / f"{status}.pdf"
    source.write_bytes(b"%PDF-1.4")
    with connect(config) as conn:
        metadata = {"pipeline_snapshot": snapshot} if snapshot is not None else {}
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(source),
            original_filename=source.name,
            metadata=metadata,
        )
        conn.execute(
            "UPDATE batches SET status = ? WHERE id = ?",
            (status, created["batch"]["id"]),
        )
        conn.execute(
            "UPDATE documents SET status = ? WHERE id = ?",
            (status, created["document"]["id"]),
        )
        task_run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            task_key="review_1",
            task_index=1,
            module_name="standard_step.review.review_gate",
            class_name="ReviewGateTask",
        )
        if task_output_hash:
            TaskRunRepository(conn).mark_paused(
                task_run["id"],
                {"review": {"schema_hash": task_output_hash}},
            )
        review = ReviewRepository(conn).create_review_item(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            queue_name="default",
            reason="low_confidence",
            scope="low_confidence_fields",
            created_by_task_run_id=task_run["id"],
            metadata={
                "schema_file": "invoice.yaml",
                "schema_hash": schema_hash,
            },
        )
        conn.execute(
            """
            INSERT INTO config_versions(
                id, config_type, name, status, content_text, content_hash,
                created_by, created_at, metadata_json
            ) VALUES ('legacy-config', 'pipeline', 'legacy', 'published',
                      '{}', 'legacy-hash', NULL, ?, '{}')
            """,
            (utc_now(),),
        )
        conn.commit()
    return {**created, "review": review, "task_run": task_run}


def test_active_yaml_and_schemas_import_idempotently_with_collisions(
    tmp_path, caplog
):
    first = tmp_path / "schemas-a"
    second = tmp_path / "schemas-b"
    first.mkdir()
    second.mkdir()
    (first / "invoice.yaml").write_text(
        yaml.safe_dump(_schema("Referenced")), encoding="utf-8"
    )
    (second / "invoice.json").write_text(
        json.dumps(_schema("Other")), encoding="utf-8"
    )
    (second / "broken.yaml").write_text("fields: invalid", encoding="utf-8")
    config = _legacy_config(
        tmp_path,
        review_tasks=1,
        schema_dirs=["schemas-a", "schemas-b", "schemas-a"],
    )
    _prepare_v2(config)
    original_mode = stat.S_IMODE(config._config_path.stat().st_mode)
    initialize_database(config)
    first_yaml = config._config_path.read_bytes()
    initialize_database(config)

    with connect(config) as conn:
        pipeline_templates = conn.execute(
            "SELECT * FROM pipeline_templates"
        ).fetchall()
        pipeline_versions = conn.execute(
            "SELECT * FROM pipeline_versions"
        ).fetchall()
        schema_templates = conn.execute(
            "SELECT * FROM review_schema_templates ORDER BY schema_key"
        ).fetchall()
        schema_versions = conn.execute(
            "SELECT * FROM review_schema_versions"
        ).fetchall()
        dependencies = conn.execute(
            "SELECT * FROM pipeline_version_schema_dependencies ORDER BY task_key"
        ).fetchall()
        migration_versions = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations")
        }

    written = yaml.safe_load(first_yaml)
    assert len(pipeline_templates) == len(pipeline_versions) == 1
    assert pipeline_templates[0]["template_key"] == "default-processing"
    assert pipeline_templates[0]["status"] == "active"
    assert {row["schema_key"] for row in schema_templates} == {
        "invoice",
        "invoice-2",
    }
    statuses = {row["schema_key"]: row["status"] for row in schema_templates}
    assert statuses == {"invoice": "active", "invoice-2": "inactive"}
    assert len(schema_versions) == 2
    assert len({row["schema_version_id"] for row in dependencies}) == 1
    assert len(dependencies) == 1
    assert written["tasks"]["extract"]["params"]["api_key"] == {
        "$secret": "default-processing-extract-params-api-key"
    }
    assert (
        written["pipeline_secrets"]["default-processing-extract-params-api-key"]
        == SECRET_VALUE
    )
    assert "schema_file" not in written["tasks"]["review_1"]["params"]
    assert written["tasks"]["review_1"]["params"]["schema_version_id"]
    assert config._config_path.read_bytes() == first_yaml
    assert stat.S_IMODE(config._config_path.stat().st_mode) == original_mode
    assert (first / "invoice.yaml").exists()
    assert (second / "invoice.json").exists()
    assert migration_versions == {2, 3}
    assert SECRET_VALUE not in caplog.text


@pytest.mark.parametrize("schema_text", [None, "fields: invalid"])
def test_missing_or_invalid_referenced_schema_blocks_migration(
    tmp_path, schema_text
):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    if schema_text is not None:
        (schema_dir / "invoice.yaml").write_text(schema_text, encoding="utf-8")
    config = _legacy_config(tmp_path)
    _prepare_v2(config)
    original = config._config_path.read_bytes()

    with pytest.raises(LegacyVersionedConfigMigrationError, match="schema"):
        initialize_database(config)

    with connect(config) as conn:
        assert conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = 3"
        ).fetchone() is None
    assert config._config_path.read_bytes() == original


def test_committed_partial_attempt_with_matching_hash_resumes_without_duplicates(
    tmp_path,
):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "invoice.yaml").write_text(
        yaml.safe_dump(_schema()), encoding="utf-8"
    )
    config = _legacy_config(tmp_path)
    _prepare_v2(config)
    initialize_database(config)
    with connect(config) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = 3")
        conn.commit()
        before = (
            conn.execute("SELECT COUNT(*) FROM pipeline_templates").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM review_schema_templates").fetchone()[0],
        )
    config = MigrationConfig(config._config_path)

    initialize_database(config)

    with connect(config) as conn:
        after = (
            conn.execute("SELECT COUNT(*) FROM pipeline_templates").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM review_schema_templates").fetchone()[0],
        )
        assert conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = 3"
        ).fetchone()
    assert after == before


def test_matching_nonterminal_state_backfills_assignments_and_review_identity(
    tmp_path,
):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    schema_path = schema_dir / "invoice.yaml"
    schema_path.write_text(yaml.safe_dump(_schema()), encoding="utf-8")
    legacy_hash = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    config = _legacy_config(tmp_path)
    _prepare_v2(config)
    snapshot = build_pipeline_snapshot(config)
    created = _seed_legacy_batch(
        config,
        status="review_completed",
        snapshot=snapshot,
        schema_hash=legacy_hash,
    )

    initialize_database(config)

    with connect(config) as conn:
        batch = conn.execute(
            "SELECT * FROM batches WHERE id = ?", (created["batch"]["id"],)
        ).fetchone()
        document = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (created["document"]["id"],)
        ).fetchone()
        task_run = conn.execute(
            "SELECT * FROM task_runs WHERE document_id = ?",
            (created["document"]["id"],),
        ).fetchone()
        review = conn.execute(
            "SELECT * FROM review_items WHERE id = ?",
            (created["review"]["id"],),
        ).fetchone()
        config_history = conn.execute(
            "SELECT id, content_text FROM config_versions"
        ).fetchall()
        audit = conn.execute(
            """
            SELECT * FROM audit_events
            WHERE event_type = 'ingestion.pipeline.legacy_migrated'
            """
        ).fetchone()

    review_metadata = json_loads(review["metadata_json"], {})
    batch_metadata = json_loads(batch["metadata_json"], {})
    assert batch["pipeline_assignment_source"] == "legacy_migration"
    assert batch["pipeline_version_id"] == document["pipeline_version_id"]
    assert task_run["pipeline_version_id"] == document["pipeline_version_id"]
    assert review["review_schema_version_id"]
    assert review_metadata["legacy_schema_hash"] == legacy_hash
    assert review_metadata["schema_hash"] != legacy_hash
    assert batch_metadata["pipeline_migration"]["reproducibility"] == (
        "display_snapshot_matched"
    )
    assert [(row["id"], row["content_text"]) for row in config_history] == [
        ("legacy-config", "{}")
    ]
    assert audit is not None


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "processing",
        "queued",
        "review_required",
        "in_review",
        "review_completed",
        "resuming",
        "split_completed",
    ],
)
def test_every_nonterminal_status_requires_a_matching_snapshot(tmp_path, status):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    schema_path = schema_dir / "invoice.yaml"
    schema_path.write_text(yaml.safe_dump(_schema()), encoding="utf-8")
    config = _legacy_config(tmp_path)
    _prepare_v2(config)
    _seed_legacy_batch(
        config,
        status=status,
        snapshot=None,
        schema_hash=hashlib.sha256(schema_path.read_bytes()).hexdigest(),
    )
    original = config._config_path.read_bytes()

    with pytest.raises(
        LegacyVersionedConfigMigrationError, match="non-terminal legacy batch"
    ):
        initialize_database(config)

    with connect(config) as conn:
        assert conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = 3"
        ).fetchone() is None
        assert conn.execute("SELECT COUNT(*) FROM pipeline_templates").fetchone()[0] == 0
    assert config._config_path.read_bytes() == original


@pytest.mark.parametrize(
    "status", ["completed", "completed_with_errors", "failed", "cancelled"]
)
def test_terminal_history_migrates_without_snapshot_as_derived(tmp_path, status):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "invoice.yaml").write_text(
        yaml.safe_dump(_schema()), encoding="utf-8"
    )
    config = _legacy_config(tmp_path)
    _prepare_v2(config)
    created = _seed_legacy_batch(
        config, status=status, snapshot=None, schema_hash=None
    )

    initialize_database(config)

    with connect(config) as conn:
        batch = conn.execute(
            "SELECT * FROM batches WHERE id = ?", (created["batch"]["id"],)
        ).fetchone()
    metadata = json_loads(batch["metadata_json"], {})
    assert batch["pipeline_version_id"]
    assert metadata["pipeline_migration"]["reproducibility"] == "migration_derived"


def test_mismatched_snapshot_or_review_hash_blocks_cutover(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    schema_path = schema_dir / "invoice.yaml"
    schema_path.write_text(yaml.safe_dump(_schema()), encoding="utf-8")
    config = _legacy_config(tmp_path)
    _prepare_v2(config)
    snapshot = build_pipeline_snapshot(config)
    snapshot["content_hash"] = "0" * 64
    _seed_legacy_batch(
        config,
        status="processing",
        snapshot=snapshot,
        schema_hash=hashlib.sha256(schema_path.read_bytes()).hexdigest(),
    )
    with pytest.raises(LegacyVersionedConfigMigrationError):
        initialize_database(config)

    other = tmp_path / "other"
    other.mkdir()
    other_schema_dir = other / "schemas"
    other_schema_dir.mkdir()
    (other_schema_dir / "invoice.yaml").write_text(
        yaml.safe_dump(_schema()), encoding="utf-8"
    )
    other_config = _legacy_config(other)
    _prepare_v2(other_config)
    _seed_legacy_batch(
        other_config,
        status="processing",
        snapshot=build_pipeline_snapshot(other_config),
        schema_hash="f" * 64,
    )
    with pytest.raises(
        LegacyVersionedConfigMigrationError, match="schema hash"
    ):
        initialize_database(other_config)


def test_mismatched_review_task_output_hash_blocks_cutover(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    schema_path = schema_dir / "invoice.yaml"
    schema_path.write_text(yaml.safe_dump(_schema()), encoding="utf-8")
    legacy_hash = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    config = _legacy_config(tmp_path)
    _prepare_v2(config)
    _seed_legacy_batch(
        config,
        status="processing",
        snapshot=build_pipeline_snapshot(config),
        schema_hash=legacy_hash,
        task_output_hash="e" * 64,
    )

    with pytest.raises(
        LegacyVersionedConfigMigrationError, match="review task schema hash"
    ):
        initialize_database(config)


def test_yaml_is_restored_when_version_recording_fails(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "invoice.yaml").write_text(
        yaml.safe_dump(_schema()), encoding="utf-8"
    )
    config = _legacy_config(tmp_path)
    _prepare_v2(config)
    original = config._config_path.read_bytes()
    with connect(config) as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_schema_v3
            BEFORE INSERT ON schema_migrations
            WHEN NEW.version = 3
            BEGIN
                SELECT RAISE(ABORT, 'synthetic migration failure');
            END
            """
        )
        conn.commit()

    with pytest.raises(Exception, match="synthetic migration failure"):
        initialize_database(config)

    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pipeline_templates").fetchone()[0] == 0
        assert conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = 3"
        ).fetchone() is None
    assert config._config_path.read_bytes() == original


def test_partial_default_template_conflict_blocks_duplicate_import(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "invoice.yaml").write_text(
        yaml.safe_dump(_schema()), encoding="utf-8"
    )
    config = _legacy_config(tmp_path, review_tasks=0)
    _prepare_v2(config)
    conflicting = {
        "schema_version": 1,
        "pipeline": ["extract"],
        "tasks": {
            "extract": {
                "label": "Different",
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
                "params": {
                    "api_key": {"$secret": "existing"},
                    "fields": {
                        "supplier": {"alias": "Supplier", "type": "str"}
                    },
                },
            }
        },
    }
    with connect(config) as conn:
        service = PipelineTemplateService(
            conn, configured_secret_aliases={"existing"}
        )
        created = service.create_template(
            template_key="default-processing",
            name="Default Processing",
            initial_definition=conflicting,
            user=None,
        )
        service.publish(
            created["template"]["id"], expected_revision=1, user=None
        )

    with pytest.raises(LegacyVersionedConfigMigrationError, match="conflicts"):
        initialize_database(config)

    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pipeline_templates").fetchone()[0] == 1
        assert conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = 3"
        ).fetchone() is None
