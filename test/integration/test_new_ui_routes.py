from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import web.server as web_server
import modules.api_router as api_router
from modules.auth_utils import AuthError


TOKEN = "test-token"


class FakeConfig:
    """Config stub for UI route tests."""

    def __init__(self, *, admin_users: list[str] | None = None) -> None:
        self.values: dict[str, Any] = {
            "database": {"run_migrations_on_startup": False},
            "ui": {
                "app_name": "DocFlow AI",
                "admin_enabled": True,
                "operator_sidebar": ["upload", "review", "reports", "settings"],
            },
            "auth": {
                "roles_enabled": True,
                "default_admin_users": admin_users or [],
            },
            "authentication": {"username": "admin"},
        }

    def get(self, key: str, default: Any = None) -> Any:
        value: Any = self.values
        for part in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part, default)
        return value


class FakeAuth:
    """Auth stub that maps one fixed cookie token to a username."""

    def __init__(self, username: str) -> None:
        self.username = username
        self.token_exp_minutes = 30

    def get_current_user(self, token: str) -> str:
        if token == TOKEN:
            return self.username
        raise AuthError("Invalid token")


def build_client(monkeypatch, *, username: str = "operator", admin_users: list[str] | None = None) -> TestClient:
    config = FakeConfig(admin_users=admin_users)
    auth = FakeAuth(username)

    def fake_get_dependencies():
        return config, auth, None, None, None

    monkeypatch.setattr(web_server, "get_dependencies", fake_get_dependencies)
    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app = web_server.create_app()
    return TestClient(app)


def authenticate(client: TestClient) -> None:
    client.cookies.set("access_token", TOKEN)


def test_app_routes_require_authentication(monkeypatch) -> None:
    client = build_client(monkeypatch)

    response = client.get("/app/upload", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_app_root_redirects_to_upload_for_authenticated_user(monkeypatch) -> None:
    client = build_client(monkeypatch)
    authenticate(client)

    response = client.get("/app", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app/upload"


def test_operator_app_routes_render_shared_shell_without_admin_navigation(monkeypatch) -> None:
    client = build_client(monkeypatch, username="operator", admin_users=["admin"])
    authenticate(client)

    routes = [
        ("/app/upload", "Upload &amp; Process"),
        ("/app/processing", "Processing Overview"),
        ("/app/batches/batch-1", "Processing Overview"),
        ("/app/batches/batch-1/split-results", "Split Results"),
        ("/app/documents/doc-1/extraction", "Extraction Results"),
        ("/app/review", "Review Queue"),
        ("/app/review/review-1", "Human Review"),
        ("/app/reports", "Reports"),
        ("/app/settings", "Settings"),
    ]

    for route, title in routes:
        response = client.get(route)
        assert response.status_code == 200, route
        assert title in response.text
        assert "DocFlow AI" in response.text
        assert 'href="/app/upload"' in response.text
        assert 'href="/app/review"' in response.text
        assert "Admin Home" not in response.text
        assert 'href="/app/admin' not in response.text


def test_upload_processing_and_split_pages_include_task_16_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="operator", admin_users=["admin"])
    authenticate(client)

    upload = client.get("/app/upload")
    processing = client.get("/app/batches/batch-1")
    split_results = client.get("/app/batches/batch-1/split-results")

    assert upload.status_code == 200
    assert 'id="upload-drop-zone"' in upload.text
    assert "/static/js/upload_process.js" in upload.text
    assert processing.status_code == 200
    assert 'id="processing-workspace"' in processing.text
    assert "/static/js/processing_overview.js" in processing.text
    assert split_results.status_code == 200
    assert 'id="split-results-workspace"' in split_results.text
    assert "/static/js/split_results.js" in split_results.text


def test_extraction_results_page_includes_task_18_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="operator", admin_users=["admin"])
    authenticate(client)

    response = client.get("/app/documents/doc-1/extraction")

    assert response.status_code == 200
    assert 'id="extraction-results-workspace"' in response.text
    assert "/static/js/extraction_results.js" in response.text


def test_review_pages_include_task_19_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="operator", admin_users=["admin"])
    authenticate(client)

    queue = client.get("/app/review")
    review = client.get("/app/review/review-1")

    assert queue.status_code == 200
    assert 'id="review-queue-workspace"' in queue.text
    assert "/static/js/review_queue.js" in queue.text
    assert review.status_code == 200
    assert 'id="human-review-workspace"' in review.text
    assert "/static/js/pdf_viewer.js" in review.text
    assert "/static/js/human_review.js" in review.text


def test_schema_editor_page_includes_task_17_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    response = client.get("/app/schemas")

    assert response.status_code == 200
    assert 'id="schema-editor-workspace"' in response.text
    assert "/static/js/schema_editor.js" in response.text


def test_task_catalog_page_includes_task_20_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    response = client.get("/app/admin/tasks")

    assert response.status_code == 200
    assert 'id="task-catalog-workspace"' in response.text
    assert "/static/js/task_catalog.js" in response.text
