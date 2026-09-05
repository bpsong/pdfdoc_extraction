"""Exercise the read/export/version endpoints around the versioned admin APIs."""

from __future__ import annotations

import modules.api_router as api_router
from test.integration.test_versioned_pipeline_api import _admin_client as pipeline_client, _definition
from test.integration.test_versioned_schema_api import _admin_client as schema_client


def test_review_schema_admin_read_and_export_routes(tmp_path, monkeypatch) -> None:
    client, _ = schema_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/admin/review-schemas",
        json={"schema_key": "matrix", "name": "Matrix"},
    ).json()
    template_id = created["template"]["id"]
    client.put(
        f"/api/admin/review-schemas/{template_id}/draft",
        json={"expected_revision": 1, "schema": {"fields": {"name": {"type": "string"}}}},
    )
    published = client.post(
        f"/api/admin/review-schemas/{template_id}/publish",
        json={"expected_revision": 2},
    ).json()
    version_id = published["version"]["id"]

    assert client.get("/api/admin/review-schemas").status_code == 200
    assert client.get(f"/api/admin/review-schemas/{template_id}").status_code == 200
    assert client.get(f"/api/admin/review-schemas/{template_id}/draft").status_code == 200
    assert client.get(f"/api/admin/review-schemas/{template_id}/draft/export").status_code == 200
    assert client.get(f"/api/admin/review-schemas/{template_id}/draft/export?format=json").headers["content-type"].startswith("application/json")
    assert client.get(f"/api/admin/review-schemas/{template_id}/versions/{version_id}").status_code == 200
    assert client.get(f"/api/admin/review-schemas/{template_id}/versions/{version_id}/export").status_code == 200


def test_pipeline_template_admin_read_validate_diff_and_export_routes(tmp_path, monkeypatch) -> None:
    client, _ = pipeline_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/admin/pipeline-templates",
        json={"template_key": "matrix", "name": "Matrix", "definition": _definition()},
    ).json()
    template_id = created["template"]["id"]
    assert client.get("/api/admin/pipeline-templates").status_code == 200
    assert client.get("/api/admin/pipeline-templates/schema-versions").status_code == 200
    assert client.get(f"/api/admin/pipeline-templates/{template_id}").status_code == 200
    assert client.get(f"/api/admin/pipeline-templates/{template_id}/draft").status_code == 200
    assert client.get(f"/api/admin/pipeline-templates/{template_id}/draft/export").status_code == 200
    assert client.get(f"/api/admin/pipeline-templates/{template_id}/draft/export?format=json").status_code == 200
    assert client.patch(f"/api/admin/pipeline-templates/{template_id}", json={"description": "updated"}).status_code == 200
    assert client.post(f"/api/admin/pipeline-templates/{template_id}/draft/validate", json={}).status_code == 200
    published = client.post(f"/api/admin/pipeline-templates/{template_id}/publish", json={"expected_revision": 1}).json()
    version_id = published["version"]["id"]
    assert client.get(f"/api/admin/pipeline-templates/{template_id}/versions").status_code == 200
    assert client.get(f"/api/admin/pipeline-templates/{template_id}/versions/{version_id}").status_code == 200
    assert client.get(f"/api/admin/pipeline-templates/{template_id}/versions/{version_id}/export").status_code == 200
    assert client.get(f"/api/admin/pipeline-templates/{template_id}/diff").status_code == 200


def test_versioned_schema_routes_translate_service_failures(tmp_path, monkeypatch) -> None:
    client, _ = schema_client(tmp_path, monkeypatch)
    created = client.post("/api/admin/review-schemas", json={"schema_key": "errors", "name": "Errors"}).json()
    template_id = created["template"]["id"]

    class Exploding:
        def __init__(self, *args, **kwargs):
            raise ValueError("service failure")

    monkeypatch.setattr(api_router, "ReviewSchemaVersionService", Exploding)
    monkeypatch.setattr(api_router, "VersionedAdminService", Exploding)
    routes = [
        ("get", f"/api/admin/review-schemas/{template_id}"),
        ("patch", f"/api/admin/review-schemas/{template_id}"),
        ("get", f"/api/admin/review-schemas/{template_id}/draft"),
        ("post", f"/api/admin/review-schemas/{template_id}/draft/validate"),
        ("post", f"/api/admin/review-schemas/{template_id}/draft/import?expected_revision=1"),
        ("get", f"/api/admin/review-schemas/{template_id}/draft/export"),
        ("post", f"/api/admin/review-schemas/{template_id}/publish"),
        ("get", f"/api/admin/review-schemas/{template_id}/versions"),
        ("get", f"/api/admin/review-schemas/{template_id}/versions/v1"),
        ("get", f"/api/admin/review-schemas/{template_id}/versions/v1/export"),
        ("get", f"/api/admin/review-schemas/{template_id}/usage"),
    ]
    for method, path in routes:
        kwargs = {"json": {"expected_revision": 1}} if method in {"post", "patch"} else {}
        if "import" in path:
            kwargs = {"content": "kind: review-schema-draft", "headers": {"content-type": "application/yaml"}}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code >= 400, path


def test_versioned_pipeline_routes_translate_service_failures(tmp_path, monkeypatch) -> None:
    client, _ = pipeline_client(tmp_path, monkeypatch)
    created = client.post("/api/admin/pipeline-templates", json={"template_key": "errors", "name": "Errors", "definition": _definition()}).json()
    template_id = created["template"]["id"]

    class Exploding:
        def __init__(self, *args, **kwargs):
            raise ValueError("service failure")

    monkeypatch.setattr(api_router, "PipelineTemplateService", Exploding)
    monkeypatch.setattr(api_router, "VersionedAdminService", Exploding)
    routes = [
        ("get", f"/api/admin/pipeline-templates/{template_id}"),
        ("patch", f"/api/admin/pipeline-templates/{template_id}"),
        ("post", f"/api/admin/pipeline-templates/{template_id}/clone"),
        ("get", f"/api/admin/pipeline-templates/{template_id}/draft"),
        ("put", f"/api/admin/pipeline-templates/{template_id}/draft"),
        ("post", f"/api/admin/pipeline-templates/{template_id}/draft/validate"),
        ("post", f"/api/admin/pipeline-templates/{template_id}/draft/import?expected_revision=1"),
        ("get", f"/api/admin/pipeline-templates/{template_id}/draft/export"),
        ("get", f"/api/admin/pipeline-templates/{template_id}/diff"),
        ("post", f"/api/admin/pipeline-templates/{template_id}/publish"),
        ("get", f"/api/admin/pipeline-templates/{template_id}/versions"),
        ("get", f"/api/admin/pipeline-templates/{template_id}/versions/v1"),
        ("get", f"/api/admin/pipeline-templates/{template_id}/versions/v1/export"),
    ]
    for method, path in routes:
        kwargs = {"json": {"expected_revision": 1, "definition": _definition()}} if method in {"post", "put", "patch"} else {}
        if "import" in path:
            kwargs = {"content": "kind: pipeline", "headers": {"content-type": "application/yaml"}}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code >= 400, path
