"""Lifecycle tests for SQLite-backed review schema versions."""

from __future__ import annotations

import sqlite3

import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.review_schema_version_service import (
    ReviewSchemaConflictError,
    ReviewSchemaValidationError,
    ReviewSchemaVersionService,
)
from test.helpers_sqlite import TempConfig


@pytest.fixture
def service(tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    with connect(config) as conn:
        yield ReviewSchemaVersionService(conn)


def valid_schema(label="Supplier"):
    return {
        "title": "Invoice review",
        "fields": {"supplier": {"type": "string", "label": label}},
    }


def test_schema_template_draft_publish_and_exact_load(service):
    created = service.create_template(
        schema_key="invoice-review",
        name="Invoice review",
        initial_schema=valid_schema(),
        user="admin",
    )
    result = service.publish(
        created["template"]["id"],
        expected_revision=1,
        user="admin",
    )
    loaded = service.load_version(result["version"]["id"])

    assert result["version"]["version_number"] == 1
    assert result["draft"]["revision"] == 2
    assert loaded["schema"]["fields"]["supplier"]["label"] == "Supplier"
    assert service.update_template(
        created["template"]["id"], status="active", user="admin"
    )["status"] == "active"


def test_schema_draft_uses_optimistic_concurrency_and_monotonic_versions(service):
    created = service.create_template(
        schema_key="invoice-review",
        name="Invoice review",
        initial_schema=valid_schema(),
        user="admin",
    )
    template_id = created["template"]["id"]
    first = service.publish(template_id, expected_revision=1, user="admin")
    saved = service.save_draft(
        template_id,
        expected_revision=2,
        schema=valid_schema("Vendor"),
        user="admin",
    )

    with pytest.raises(ReviewSchemaConflictError, match="stale"):
        service.save_draft(
            template_id,
            expected_revision=2,
            schema=valid_schema("Wrong"),
            user="admin",
        )

    second = service.publish(
        template_id, expected_revision=saved["revision"], user="admin"
    )
    assert first["version"]["version_number"] == 1
    assert second["version"]["version_number"] == 2


def test_schema_publish_rejects_invalid_or_unchanged_draft(service):
    created = service.create_template(
        schema_key="invalid-review",
        name="Invalid",
        initial_schema={"fields": []},
        user="admin",
    )
    with pytest.raises(ReviewSchemaValidationError):
        service.publish(
            created["template"]["id"], expected_revision=1, user="admin"
        )
    assert service.versions.list_for_owner(created["template"]["id"]) == []

    valid = service.create_template(
        schema_key="valid-review",
        name="Valid",
        initial_schema=valid_schema(),
        user="admin",
    )
    published = service.publish(
        valid["template"]["id"], expected_revision=1, user="admin"
    )
    with pytest.raises(ReviewSchemaConflictError, match="no changes"):
        service.publish(
            valid["template"]["id"],
            expected_revision=published["draft"]["revision"],
            user="admin",
        )


def test_schema_versions_are_immutable_and_exports_round_trip(service):
    created = service.create_template(
        schema_key="invoice-review",
        name="Invoice",
        initial_schema=valid_schema(),
        user="admin",
    )
    published = service.publish(
        created["template"]["id"], expected_revision=1, user="admin"
    )
    version_id = published["version"]["id"]

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        service.conn.execute(
            "DELETE FROM review_schema_versions WHERE id = ?", (version_id,)
        )
    service.conn.rollback()

    exported = service.export_version(version_id)
    imported = service.import_document(exported)
    assert imported == valid_schema()


def test_schema_lifecycle_requires_publication_and_inactive_archive(service):
    created = service.create_template(
        schema_key="invoice-review",
        name="Invoice",
        user="admin",
    )
    template_id = created["template"]["id"]

    with pytest.raises(ReviewSchemaConflictError, match="published"):
        service.update_template(template_id, status="active", user="admin")

    service.publish(template_id, expected_revision=1, user="admin")
    service.update_template(template_id, status="active", user="admin")
    with pytest.raises(ReviewSchemaConflictError, match="inactive"):
        service.update_template(template_id, status="archived", user="admin")
    service.update_template(template_id, status="inactive", user="admin")
    archived = service.update_template(
        template_id, status="archived", user="admin"
    )
    assert archived["archived_at"]
    assert service.load_version(
        service.versions.list_for_owner(template_id)[0]["id"]
    )["schema"]["fields"] == {}
    assert service.list_selectable_versions() == []


def test_schema_import_updates_only_draft_and_payload_validation_uses_exact_version(
    service,
):
    created = service.create_template(
        schema_key="invoice-review",
        name="Invoice",
        initial_schema={"fields": {}},
        user="admin",
    )
    imported = service.import_draft(
        created["template"]["id"],
        expected_revision=1,
        text="""
kind: review-schema
format_version: 1
schema:
  fields:
    supplier:
      type: string
      required: true
""",
        user="admin",
    )
    assert imported["revision"] == 2
    assert service.versions.list_for_owner(created["template"]["id"]) == []
    published = service.publish(
        created["template"]["id"], expected_revision=2, user="admin"
    )
    findings = service.validate_payload(
        published["version"]["id"], {"supplier": ""}
    )
    assert findings[0]["path"] == "supplier"
    audit_events = service.conn.execute(
        "SELECT event_json FROM audit_events ORDER BY created_at"
    ).fetchall()
    assert all("fields" not in row["event_json"] for row in audit_events)
