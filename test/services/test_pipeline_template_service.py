"""Lifecycle tests for SQLite-backed pipeline template versions."""

from __future__ import annotations

import sqlite3

import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.pipeline_template_service import (
    PipelineTemplateConflictError,
    PipelineTemplateService,
    PipelineTemplateValidationError,
)
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.validation_facade import ValidationFacade
from test.helpers_sqlite import TempConfig


@pytest.fixture
def context(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    with connect(config) as conn:
        service = PipelineTemplateService(
            conn,
            validation=ValidationFacade(config),
            configured_secret_aliases={"extract-api"},
        )
        yield conn, service


def extraction_definition(label="Extract"):
    return {
        "schema_version": 1,
        "pipeline": ["extract"],
        "tasks": {
            "extract": {
                "label": label,
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
                "params": {
                    "api_key": {"$secret": "extract-api"},
                    "fields": {"supplier": {"alias": "Supplier", "type": "str"}},
                },
                "on_error": "stop",
            }
        },
    }


def review_definition(schema_version_id):
    definition = extraction_definition()
    definition["pipeline"].append("review")
    definition["tasks"]["review"] = {
        "module": "standard_step.review.review_gate",
        "class": "ReviewGateTask",
        "params": {
            "confidence_threshold": 0.8,
            "review_scope": "low_confidence_fields",
            "schema_version_id": schema_version_id,
        },
    }
    return definition


def glm_review_definition(schema_version_id):
    fields = {
        "supplier": {"alias": "Supplier", "type": "str"},
    }
    return {
        "schema_version": 1,
        "pipeline": ["glm_extract", "review", "store_csv"],
        "tasks": {
            "glm_extract": {
                "module": "standard_step.extraction.glm_ocr_extract",
                "class": "GlmOcrExtractTask",
                "params": {
                    "ollama_host": "http://127.0.0.1:11434",
                    "model": "glm-ocr:latest",
                    "document_instructions": "",
                    "dpi": 216,
                    "num_ctx": 8192,
                    "num_predict": 2048,
                    "timeout_seconds": 300,
                    "fields": fields,
                },
                "on_error": "stop",
            },
            "review": {
                "module": "standard_step.review.review_gate",
                "class": "ReviewGateTask",
                "params": {
                    "confidence_threshold": 0.8,
                    "schema_version_id": schema_version_id,
                },
                "on_error": "stop",
            },
            "store_csv": {
                "module": "standard_step.storage.store_metadata_as_csv",
                "class": "StoreMetadataAsCsv",
                "params": {
                    "data_dir": "data",
                    "filename": "{supplier}.csv",
                    "extraction": {"fields": fields},
                },
                "on_error": "stop",
            },
        },
    }


def create_active_schema(conn):
    service = ReviewSchemaVersionService(conn)
    created = service.create_template(
        schema_key="invoice-review",
        name="Invoice review",
        initial_schema={
            "fields": {"supplier": {"type": "string", "label": "Supplier"}}
        },
        user="admin",
    )
    published = service.publish(
        created["template"]["id"], expected_revision=1, user="admin"
    )
    service.update_template(
        created["template"]["id"], status="active", user="admin"
    )
    return published["version"]["id"]


def test_two_templates_publish_independently_and_load_exact_versions(context):
    _, service = context
    one = service.create_template(
        template_key="invoice",
        name="Invoice",
        initial_definition=extraction_definition("Invoice extract"),
        user="admin",
    )
    two = service.create_template(
        template_key="receipt",
        name="Receipt",
        initial_definition=extraction_definition("Receipt extract"),
        user="admin",
    )
    first = service.publish(one["template"]["id"], expected_revision=1, user="admin")
    second = service.publish(two["template"]["id"], expected_revision=1, user="admin")

    assert service.load_version(first["version"]["id"])["definition"]["tasks"][
        "extract"
    ]["label"] == "Invoice extract"
    assert service.load_version(second["version"]["id"])["definition"]["tasks"][
        "extract"
    ]["label"] == "Receipt extract"
    assert first["version"]["version_number"] == second["version"]["version_number"] == 1


def test_pipeline_draft_conflict_monotonic_publish_and_unchanged_rejection(context):
    _, service = context
    created = service.create_template(
        template_key="invoice",
        name="Invoice",
        initial_definition=extraction_definition(),
        user="admin",
    )
    template_id = created["template"]["id"]
    first = service.publish(template_id, expected_revision=1, user="admin")
    saved = service.save_draft(
        template_id,
        expected_revision=2,
        definition=extraction_definition("Extract v2"),
        user="admin",
    )
    with pytest.raises(PipelineTemplateConflictError) as error:
        service.save_draft(
            template_id,
            expected_revision=2,
            definition=extraction_definition("stale"),
            user="admin",
        )
    assert error.value.current is not None
    assert error.value.current["revision"] == saved["revision"]

    second = service.publish(
        template_id, expected_revision=saved["revision"], user="admin"
    )
    assert first["version"]["version_number"] == 1
    assert second["version"]["version_number"] == 2
    with pytest.raises(PipelineTemplateConflictError, match="no changes"):
        service.publish(
            template_id,
            expected_revision=second["draft"]["revision"],
            user="admin",
        )


def test_pipeline_publication_persists_exact_active_schema_dependency(context):
    conn, service = context
    schema_version_id = create_active_schema(conn)
    created = service.create_template(
        template_key="invoice",
        name="Invoice",
        initial_definition=review_definition(schema_version_id),
        user="admin",
    )
    published = service.publish(
        created["template"]["id"], expected_revision=1, user="admin"
    )
    loaded = service.load_version(published["version"]["id"])

    assert loaded["schema_dependencies"] == {"review": schema_version_id}
    dependency = conn.execute(
        """
        SELECT * FROM pipeline_version_schema_dependencies
        WHERE pipeline_version_id = ?
        """,
        (published["version"]["id"],),
    ).fetchone()
    assert dependency["schema_version_id"] == schema_version_id


def test_pipeline_publication_rejects_missing_or_inactive_schema(context):
    conn, service = context
    missing = service.create_template(
        template_key="missing-schema",
        name="Missing schema",
        initial_definition=review_definition("not-a-version"),
        user="admin",
    )
    with pytest.raises(PipelineTemplateValidationError):
        service.publish(
            missing["template"]["id"], expected_revision=1, user="admin"
        )

    schemas = ReviewSchemaVersionService(conn)
    created = schemas.create_template(
        schema_key="inactive-review",
        name="Inactive",
        initial_schema={"fields": {}},
        user="admin",
    )
    version = schemas.publish(
        created["template"]["id"], expected_revision=1, user="admin"
    )["version"]
    inactive = service.create_template(
        template_key="inactive-schema",
        name="Inactive schema",
        initial_definition=review_definition(version["id"]),
        user="admin",
    )
    with pytest.raises(PipelineTemplateValidationError):
        service.publish(
            inactive["template"]["id"], expected_revision=1, user="admin"
        )


def test_pipeline_lifecycle_operator_selection_clone_and_archived_load(context):
    _, service = context
    created = service.create_template(
        template_key="invoice",
        name="Invoice",
        operator_selectable=False,
        initial_definition=extraction_definition(),
        user="admin",
    )
    template_id = created["template"]["id"]
    with pytest.raises(PipelineTemplateConflictError, match="published"):
        service.update_template(template_id, status="active", user="admin")

    published = service.publish(template_id, expected_revision=1, user="admin")
    service.update_template(template_id, status="active", user="admin")
    assert service.list_operator_selectable() == []
    service.update_template(
        template_id, operator_selectable=True, user="admin"
    )
    assert service.list_operator_selectable()[0]["id"] == template_id

    cloned = service.clone(
        template_id, template_key="invoice-copy", name="Invoice copy", user="admin"
    )
    assert cloned["template"]["status"] == "inactive"
    assert service.versions.list_for_owner(cloned["template"]["id"]) == []
    assert cloned["draft"]["definition"] == extraction_definition()

    service.update_template(template_id, status="inactive", user="admin")
    service.update_template(template_id, status="archived", user="admin")
    assert service.load_version(published["version"]["id"])["id"] == published["version"]["id"]


def test_pipeline_key_and_versions_immutable_and_diff_export_redacted(context):
    conn, service = context
    created = service.create_template(
        template_key="invoice",
        name="Invoice",
        initial_definition=extraction_definition(),
        user="admin",
    )
    published = service.publish(
        created["template"]["id"], expected_revision=1, user="admin"
    )
    with pytest.raises(sqlite3.IntegrityError, match="key is immutable"):
        conn.execute(
            "UPDATE pipeline_templates SET template_key = 'changed' WHERE id = ?",
            (created["template"]["id"],),
        )
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute(
            "DELETE FROM pipeline_versions WHERE id = ?",
            (published["version"]["id"],),
        )
    conn.rollback()

    service.save_draft(
        created["template"]["id"],
        expected_revision=published["draft"]["revision"],
        definition=extraction_definition("Changed"),
        user="admin",
    )
    diff = service.diff(created["template"]["id"])["text"]
    exported = service.export_version(published["version"]["id"], user="admin")
    assert '"label": "Changed"' in diff
    assert "actual-secret-value" not in diff
    assert "configured-secret-reference" not in diff
    assert '"$secret": "extract-api"' in exported
    assert "actual-secret-value" not in exported


def test_literal_or_unconfigured_secrets_block_publication(context):
    _, service = context
    literal = extraction_definition()
    literal["tasks"]["extract"]["params"]["api_key"] = "actual-secret-value"
    created = service.create_template(
        template_key="literal-secret",
        name="Literal",
        initial_definition=literal,
        user="admin",
    )
    with pytest.raises(PipelineTemplateValidationError):
        service.publish(
            created["template"]["id"], expected_revision=1, user="admin"
        )

    reference = extraction_definition()
    reference["tasks"]["extract"]["params"]["api_key"] = {"$secret": "unknown"}
    created = service.create_template(
        template_key="unknown-secret",
        name="Unknown",
        initial_definition=reference,
        user="admin",
    )
    with pytest.raises(PipelineTemplateValidationError):
        service.publish(
            created["template"]["id"], expected_revision=1, user="admin"
        )


def test_pipeline_publication_rolls_back_version_when_dependency_insert_fails(
    context, monkeypatch
):
    conn, service = context
    schema_version_id = create_active_schema(conn)
    created = service.create_template(
        template_key="rollback",
        name="Rollback",
        initial_definition=review_definition(schema_version_id),
        user="admin",
    )

    def fail_dependency(**kwargs):
        raise RuntimeError("synthetic dependency failure")

    monkeypatch.setattr(service.dependencies, "create", fail_dependency)
    with pytest.raises(RuntimeError, match="synthetic"):
        service.publish(
            created["template"]["id"], expected_revision=1, user="admin"
        )

    assert service.versions.list_for_owner(created["template"]["id"]) == []
    assert service.drafts.get(created["template"]["id"])["revision"] == 1


def test_pipeline_rejects_review_fields_not_produced_by_extraction(context):
    conn, service = context
    schemas = ReviewSchemaVersionService(conn)
    created_schema = schemas.create_template(
        schema_key="mismatch-review",
        name="Mismatch",
        initial_schema={"fields": {"unknown": {"type": "string"}}},
        user="admin",
    )
    schema_version = schemas.publish(
        created_schema["template"]["id"], expected_revision=1, user="admin"
    )["version"]
    schemas.update_template(
        created_schema["template"]["id"], status="active", user="admin"
    )
    created = service.create_template(
        template_key="mismatch",
        name="Mismatch",
        initial_definition=review_definition(schema_version["id"]),
        user="admin",
    )
    with pytest.raises(PipelineTemplateValidationError) as error:
        service.publish(
            created["template"]["id"], expected_revision=1, user="admin"
        )
    assert any(
        item["code"] == "pipeline-schema-extraction-mismatch"
        for item in error.value.result["findings"]
    )


def test_glm_fields_satisfy_review_schema_and_publish_exact_csv_reuse(context):
    conn, service = context
    schema_version_id = create_active_schema(conn)
    definition = glm_review_definition(schema_version_id)
    created = service.create_template(
        template_key="glm-invoice",
        name="GLM invoice",
        initial_definition=definition,
        user="admin",
    )

    published = service.publish(
        created["template"]["id"], expected_revision=1, user="admin"
    )
    loaded = service.load_version(published["version"]["id"])["definition"]

    assert loaded["tasks"]["glm_extract"]["params"] == definition["tasks"][
        "glm_extract"
    ]["params"]
    assert loaded["tasks"]["store_csv"]["params"]["extraction"]["fields"] == {
        "supplier": {"alias": "Supplier", "type": "str"}
    }
    assert "api_key" not in loaded["tasks"]["glm_extract"]["params"]
