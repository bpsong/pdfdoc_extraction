"""CLI tests for read-only SQLite-backed validation sources."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import yaml

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.pipeline_template_service import PipelineTemplateService
from test.helpers_sqlite import TempConfig
from tools.config_check.__main__ import main
from tools.config_check.stored_validator import (
    StoredSourceValidator,
    open_readonly_database,
    validate_database_schema,
)


def _stored_context(tmp_path: Path):
    db_path = tmp_path / "state.sqlite3"
    for directory in ("uploads", "watch", "data", "archive"):
        (tmp_path / directory).mkdir()
    values = {
        "database": {"path": str(db_path)},
        "pipeline_secrets": {"extract-api": "synthetic-secret"},
        "web": {
            "upload_dir": str(tmp_path / "uploads"),
            "secret_key": "synthetic-web-secret",
        },
        "watch_folder": {
            "dir": str(tmp_path / "watch"),
            "recursive": False,
        },
        "tasks": {
            "extract_metadata": {
                "module": "standard_step.extraction.extract_metadata",
                "class": "ExtractMetadata",
                "params": {
                    "api_key": {"$secret": "extract-api"},
                    "configuration_id": "synthetic-config",
                    "fields": {
                        "supplier": {"alias": "Supplier", "type": "str"}
                    },
                },
            },
            "store_json": {
                "module": "standard_step.storage.store_metadata_as_json",
                "class": "StoreMetadataAsJsonTask",
                "params": {
                    "data_dir": str(tmp_path / "data"),
                    "filename": "{supplier}_metadata.json",
                },
            },
            "archive_pdf": {
                "module": "standard_step.housekeeping.archive_pdf",
                "class": "ArchivePdf",
                "params": {"archive_dir": str(tmp_path / "archive")},
            },
        },
        "pipeline": ["extract_metadata", "store_json", "archive_pdf"],
    }
    config = TempConfig(db_path, values)
    initialize_database(config)
    with connect(config) as conn:
        service = PipelineTemplateService(
            conn, configured_secret_aliases={"extract-api"}
        )
        created = service.create_template(
            template_key="invoice",
            name="Invoice",
            initial_definition={
                "schema_version": 1,
                "pipeline": ["extract"],
                "tasks": {
                    "extract": {
                        "module": "standard_step.extraction.extract_pdf",
                        "class": "ExtractPdfTask",
                        "params": {
                            "api_key": {"$secret": "extract-api"},
                            "fields": {
                                "supplier": {
                                    "alias": "Supplier",
                                    "type": "str",
                                }
                            },
                        },
                    }
                },
            },
            user="admin",
        )
        published = service.publish(
            created["template"]["id"], expected_revision=1, user="admin"
        )
        service.update_template(
            created["template"]["id"], status="active", user="admin"
        )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(values), encoding="utf-8")
    return db_path, config_path, created, published


def test_readonly_adapter_validates_targeted_draft_version_and_all(tmp_path):
    db_path, _, created, published = _stored_context(tmp_path)
    before = db_path.stat().st_mtime_ns
    with open_readonly_database(db_path) as conn:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        assert validate_database_schema(conn).is_valid
        validator = StoredSourceValidator(
            conn,
            runtime_config={
                "pipeline_secrets": {"extract-api": "synthetic-secret"}
            },
        )
        assert validator.validate_pipeline("invoice", draft=True).is_valid
        assert validator.validate_pipeline(
            "invoice", version_number=1
        ).is_valid
        assert validator.validate_all().is_valid
        audit_count = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    assert db_path.stat().st_mtime_ns == before
    assert audit_count > 0  # publication audit exists; validation added none


def test_cli_selector_combinations_and_schema_kinds(tmp_path, capsys):
    _, config_path, _, _ = _stored_context(tmp_path)

    assert main(
        [
            "validate",
            "--config",
            str(config_path),
            "--pipeline",
            "invoice",
            "--draft",
        ]
    ) == 2
    assert main(
        [
            "validate",
            "--config",
            str(config_path),
            "--pipeline",
            "invoice",
            "--version",
            "1",
        ]
    ) == 2
    assert main(
        [
            "validate",
            "--config",
            str(config_path),
            "--pipeline",
            "invoice",
        ]
    ) == 64
    assert main(
        [
            "validate",
            "--config",
            str(config_path),
            "--all-stored",
            "--draft",
        ]
    ) == 64
    capsys.readouterr()
    for kind in ("runtime", "pipeline", "review-schema", "pipeline-bundle"):
        assert main(["schema", "--kind", kind]) == 0
        output = capsys.readouterr().out
        assert '"type": "object"' in output


def test_cli_accepts_deployment_yaml_without_legacy_pipeline(tmp_path, capsys):
    _, config_path, _, _ = _stored_context(tmp_path)
    values = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    values.pop("tasks")
    values.pop("pipeline")
    config_path.write_text(yaml.safe_dump(values), encoding="utf-8")

    assert main(
        [
            "validate",
            "--config",
            str(config_path),
            "--pipeline",
            "invoice",
            "--version",
            "1",
        ]
    ) == 0
    assert "no issues found" in capsys.readouterr().out.lower()


def test_missing_and_outdated_database_are_blocking_findings(tmp_path, capsys):
    missing_config = tmp_path / "missing.yaml"
    missing_config.write_text(
        yaml.safe_dump({"database": {"path": str(tmp_path / "missing.sqlite3")}}),
        encoding="utf-8",
    )
    missing_code = main(["validate", "--config", str(missing_config)])
    assert missing_code == 1
    assert "database" in capsys.readouterr().out.lower()

    outdated = tmp_path / "outdated.sqlite3"
    with sqlite3.connect(outdated) as conn:
        conn.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)"
        )
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (2, 'now')"
        )
    outdated_config = tmp_path / "outdated.yaml"
    outdated_config.write_text(
        yaml.safe_dump({"database": {"path": str(outdated)}}),
        encoding="utf-8",
    )
    assert main(["validate", "--config", str(outdated_config)]) == 1
    assert "older than required" in capsys.readouterr().out
