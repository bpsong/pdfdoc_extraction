"""API coverage for versioned pipeline-template administration."""

from pathlib import Path
from typing import cast

import pytest
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


def _glm_definition():
    return {
        "schema_version": 1,
        "pipeline": ["glm_extract"],
        "tasks": {
            "glm_extract": {
                "label": "Local GLM-OCR extract",
                "module": "standard_step.extraction.glm_ocr_extract",
                "class": "GlmOcrExtractTask",
                "params": {
                    "ollama_host": "http://127.0.0.1:11434",
                    "model": "glm-ocr:latest",
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


def test_pipeline_rename_preserves_identity_draft_and_published_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _admin_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/admin/pipeline-templates",
        json={
            "template_key": "rename-invoices",
            "name": "Original invoices",
            "definition": _definition(),
        },
    ).json()
    template_id = created["template"]["id"]
    published = client.post(
        f"/api/admin/pipeline-templates/{template_id}/publish",
        json={"expected_revision": 1},
    ).json()
    version_url = (
        f"/api/admin/pipeline-templates/{template_id}/versions/"
        f"{published['version']['id']}"
    )
    original_version = client.get(version_url).json()
    original_draft = client.get(
        f"/api/admin/pipeline-templates/{template_id}/draft"
    ).json()

    renamed = client.patch(
        f"/api/admin/pipeline-templates/{template_id}",
        json={"name": "Renamed invoices"},
    )

    assert renamed.status_code == 200
    assert renamed.json()["template"]["name"] == "Renamed invoices"
    assert renamed.json()["template"]["id"] == template_id
    assert renamed.json()["template"]["template_key"] == "rename-invoices"
    assert client.get(version_url).json() == original_version
    assert client.get(
        f"/api/admin/pipeline-templates/{template_id}/draft"
    ).json() == original_draft
    summaries = client.get("/api/admin/pipeline-templates").json()["templates"]
    summary = next(item for item in summaries if item["id"] == template_id)
    assert summary["name"] == "Renamed invoices"


def test_operator_cannot_publish_glm_task_configuration(tmp_path, monkeypatch):
    client, _ = _admin_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/admin/pipeline-templates",
        json={
            "template_key": "glm-secure-publish",
            "name": "GLM secure publish",
            "definition": _glm_definition(),
        },
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]
    cast(FastAPI, client.app).dependency_overrides[api_router.get_current_user] = (
        lambda: "operator"
    )

    response = client.post(
        f"/api/admin/pipeline-templates/{template_id}/publish",
        json={"expected_revision": 1},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"
