"""API coverage for administrator-managed watch-folder bindings."""

from __future__ import annotations

from modules.db.connection import connect
from modules.db.repositories import UserRepository
import modules.api_router as api_router
from test.integration.test_batch_upload_api import build_client


def _admin_client(tmp_path, monkeypatch):
    client, config, _ = build_client(tmp_path, monkeypatch)
    with connect(config) as conn:
        UserRepository(conn).initialize(
            {"admin": "test-only", "operator": "test-only"}
        )
    client.app.dependency_overrides[api_router.get_current_user] = lambda: "admin"
    return client, config


def test_binding_api_create_list_conflict_and_delete(tmp_path, monkeypatch):
    client, config = _admin_client(tmp_path, monkeypatch)
    first = tmp_path / "first"
    nested = first / "nested"
    nested.mkdir(parents=True)

    created = client.post(
        "/api/admin/watch-folder-bindings",
        json={
            "folder_path": str(first),
            "pipeline_version_id": config.pipeline_version_id,
            "enabled": True,
        },
    )

    assert created.status_code == 200
    payload = created.json()
    assert payload["accessible"] is True
    assert payload["validation_findings"] == []
    assert payload["pipeline"]["version_number"] == 1

    conflict = client.post(
        "/api/admin/watch-folder-bindings",
        json={
            "folder_path": str(nested),
            "pipeline_version_id": config.pipeline_version_id,
            "enabled": True,
        },
    )
    assert conflict.status_code == 409

    listed = client.get("/api/admin/watch-folder-bindings")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["bindings"]] == [payload["id"]]

    deleted = client.delete(
        f"/api/admin/watch-folder-bindings/{payload['id']}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_binding_api_enforces_admin_role_and_cookie_csrf(tmp_path, monkeypatch):
    client, config = _admin_client(tmp_path, monkeypatch)
    folder = tmp_path / "incoming"
    folder.mkdir()
    body = {
        "folder_path": str(folder),
        "pipeline_version_id": config.pipeline_version_id,
        "enabled": True,
    }

    client.app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    assert client.post("/api/admin/watch-folder-bindings", json=body).status_code == 403

    client.app.dependency_overrides[api_router.get_current_user] = lambda: "admin"
    client.cookies.set("access_token", "browser-token")
    client.cookies.set("csrf_token", "csrf-test-token")
    missing = client.post("/api/admin/watch-folder-bindings", json=body)
    accepted = client.post(
        "/api/admin/watch-folder-bindings",
        json=body,
        headers={"x-csrf-token": "csrf-test-token"},
    )

    assert missing.status_code == 403
    assert accepted.status_code == 200
