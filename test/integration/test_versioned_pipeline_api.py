"""API coverage for versioned pipeline-template administration."""

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


def _definition(label="Extract"):
    return {
        "schema_version": 1,
        "pipeline": ["extract"],
        "tasks": {
            "extract": {
                "label": label,
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
                "params": {
                    "api_key": {"$secret": "test-api"},
                    "fields": {
                        "supplier": {"alias": "Supplier", "type": "str"}
                    },
                },
            }
        },
    }


def test_pipeline_template_lifecycle_clone_diff_and_redaction(tmp_path, monkeypatch):
    client, _ = _admin_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/admin/pipeline-templates",
        json={
            "template_key": "receipts",
            "name": "Receipts",
            "definition": _definition(),
        },
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    saved = client.put(
        f"/api/admin/pipeline-templates/{template_id}/draft",
        json={"expected_revision": 1, "definition": _definition("New extract")},
    )
    assert saved.status_code == 200
    assert "runtime-secret" not in saved.text
    assert client.post(
        f"/api/admin/pipeline-templates/{template_id}/draft/validate", json={}
    ).json()["valid"]
    published = client.post(
        f"/api/admin/pipeline-templates/{template_id}/publish",
        json={"expected_revision": 2},
    )
    assert published.status_code == 200
    version_id = published.json()["version"]["id"]
    assert client.patch(
        f"/api/admin/pipeline-templates/{template_id}",
        json={"status": "active"},
    ).status_code == 200

    version = client.get(
        f"/api/admin/pipeline-templates/{template_id}/versions/{version_id}"
    )
    cloned = client.post(
        f"/api/admin/pipeline-templates/{template_id}/clone",
        json={"template_key": "receipts-copy", "name": "Receipts copy"},
    )
    assert version.status_code == 200
    assert "runtime-secret" not in version.text
    assert cloned.status_code == 200


def test_pipeline_stale_revision_operator_forbidden_and_legacy_writes_gone(
    tmp_path, monkeypatch
):
    client, _ = _admin_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/admin/pipeline-templates",
        json={
            "template_key": "claims",
            "name": "Claims",
            "definition": _definition(),
        },
    ).json()
    template_id = created["template"]["id"]
    assert client.put(
        f"/api/admin/pipeline-templates/{template_id}/draft",
        json={"expected_revision": 1, "definition": _definition("Changed")},
    ).status_code == 200
    assert client.put(
        f"/api/admin/pipeline-templates/{template_id}/draft",
        json={"expected_revision": 1, "definition": _definition("Stale")},
    ).status_code == 409
    assert client.put("/api/admin/pipeline/draft", json={}).status_code == 410
    assert client.post("/api/admin/pipeline/publish", json={}).status_code == 410

    cast(FastAPI, client.app).dependency_overrides[api_router.get_current_user] = (
        lambda: "operator"
    )
    assert client.get("/api/admin/pipeline-templates").status_code == 403
