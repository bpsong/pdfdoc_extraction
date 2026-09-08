"""HTTP contracts for watch-folder lifecycle and diagnostics."""

from test.integration.test_watch_folder_binding_api import _admin_client
from test.integration.test_new_ui_routes import build_client, authenticate


def test_management_routes_require_admin(monkeypatch):
    for username, status in (("admin", 200), ("operator", 403)):
        client = build_client(monkeypatch, username=username)
        authenticate(client)
        response = client.get("/app/admin/watch-folders")
        assert response.status_code == status
        if status == 200:
            assert 'id="watch-dialog"' in response.text
            assert '/static/js/watch_folders.js' in response.text


def test_api_lifecycle_revisions_diagnostics_and_history(tmp_path, monkeypatch):
    client, config = _admin_client(tmp_path, monkeypatch)
    folder = tmp_path / "incoming"
    folder.mkdir()
    body = {"folder_path": str(folder), "pipeline_version_id": config.pipeline_version_id, "enabled": True}
    assert client.post("/api/admin/watch-folder-bindings", json={**body, "enabled": "false"}).status_code == 422
    binding = client.post("/api/admin/watch-folder-bindings", json=body).json()
    url = f"/api/admin/watch-folder-bindings/{binding['id']}"
    assert client.patch(url, json={"enabled": "false"}).status_code == 422
    for field in ("action", "folder_path", "pipeline_version_id"):
        assert client.patch(url, json={field: []}).status_code == 422
    assert client.patch(url, json={"action": "pause", "expected_revision": 1}).status_code == 200
    assert client.patch(url, json={"action": "resume", "expected_revision": 1}).status_code == 409
    assert client.post("/api/admin/watch-folder-check", json={"folder_path": str(folder)}).json()["ok"]
    assert client.patch(url, json={"action": "unbind", "expected_revision": 2}).json()["state"] == "unbound"
    assert client.patch(url, json={"action": "retire", "expected_revision": 3}).json()["state"] == "retired"
    assert len(client.get(f"{url}/activity").json()["events"]) == 4
    assert client.get(f"{url}/activity?offset=-1").status_code == 422
    assert client.get(f"{url}/activity?offset=20").json()["events"] == []
    assert client.delete(url).status_code == 200
