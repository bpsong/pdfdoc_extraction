"""API coverage for SQLite-backed versioned review schemas."""

from typing import cast

from fastapi import FastAPI

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.repositories import UserRepository
from test.integration.test_batch_upload_api import build_client


def _admin_client(tmp_path, monkeypatch):
    client, config, _ = build_client(tmp_path, monkeypatch)
    with connect(config) as conn:
        UserRepository(conn).initialize(
            {"admin": "test-only", "operator": "test-only"}
        )
    cast(FastAPI, client.app).dependency_overrides[
        api_router.get_current_user
    ] = lambda: "admin"
    return client, config


def test_schema_template_draft_publish_history_usage_and_conflict(
    tmp_path, monkeypatch
):
    client, _ = _admin_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/admin/review-schemas",
        json={"schema_key": "invoice-review", "name": "Invoice review"},
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    saved = client.put(
        f"/api/admin/review-schemas/{template_id}/draft",
        json={
            "expected_revision": 1,
            "schema": {
                "fields": {"supplier": {"type": "string", "label": "Supplier"}}
            },
        },
    )
    assert saved.status_code == 200
    stale = client.put(
        f"/api/admin/review-schemas/{template_id}/draft",
        json={"expected_revision": 1, "schema": {"fields": {}}},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["current"]["revision"] == 2

    validated = client.post(
        f"/api/admin/review-schemas/{template_id}/draft/validate", json={}
    )
    published = client.post(
        f"/api/admin/review-schemas/{template_id}/publish",
        json={"expected_revision": 2},
    )
    assert validated.status_code == 200
    assert validated.json()["valid"] is True
    assert published.status_code == 200

    activated = client.patch(
        f"/api/admin/review-schemas/{template_id}", json={"status": "active"}
    )
    history = client.get(
        f"/api/admin/review-schemas/{template_id}/versions"
    )
    usage = client.get(f"/api/admin/review-schemas/{template_id}/usage")
    assert activated.status_code == 200
    assert history.json()["versions"][0]["version_number"] == 1
    assert usage.json()["dependency_count"] == 0


def test_schema_import_is_bounded_draft_only_and_legacy_write_is_gone(
    tmp_path, monkeypatch
):
    client, _ = _admin_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/admin/review-schemas",
        json={"schema_key": "imported", "name": "Imported"},
    ).json()
    template_id = created["template"]["id"]
    content = """
kind: review-schema-draft
format_version: 1
schema_key: imported
schema:
  fields:
    amount:
      type: number
      label: Amount
"""
    imported = client.post(
        f"/api/admin/review-schemas/{template_id}/draft/import?expected_revision=1",
        content=content,
        headers={"content-type": "application/yaml"},
    )
    unsupported = client.post(
        f"/api/admin/review-schemas/{template_id}/draft/import?expected_revision=2",
        content=content,
        headers={"content-type": "text/plain"},
    )
    legacy = client.post(
        "/api/schemas", json={"name": "legacy.yaml", "schema": {"fields": {}}}
    )

    assert imported.status_code == 200
    assert imported.json()["published"] is False
    assert unsupported.status_code == 415
    assert legacy.status_code == 410
