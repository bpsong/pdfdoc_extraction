from __future__ import annotations

from typing import Any, cast
from unittest.mock import Mock

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from starlette.routing import Route

import web.server as web_server
import modules.api_router as api_router
from modules.auth_utils import AuthError


TOKEN = "test-token"


class FakeConfig:
    """Config stub for UI route tests."""

    def __init__(
        self,
        *,
        admin_users: list[str] | None = None,
        cors_allowed_origins: list[str] | None = None,
        allowed_hosts: list[str] | None = None,
        production_docs_enabled: bool = False,
    ) -> None:
        self.values: dict[str, Any] = {
            "database": {"run_migrations_on_startup": False},
            "web": {
                "cors_allowed_origins": cors_allowed_origins or [],
                "allowed_hosts": allowed_hosts or [],
                "production_docs_enabled": production_docs_enabled,
            },
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

    def is_admin(self, username: str) -> bool:
        """Treat the configured admin identity as privileged."""
        return username == "admin"


def build_client(
    monkeypatch,
    *,
    username: str = "operator",
    admin_users: list[str] | None = None,
    cors_allowed_origins: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
    production_docs_enabled: bool = False,
) -> TestClient:
    config = FakeConfig(
        admin_users=admin_users,
        cors_allowed_origins=cors_allowed_origins,
        allowed_hosts=allowed_hosts,
        production_docs_enabled=production_docs_enabled,
    )
    auth = FakeAuth(username)

    def fake_get_dependencies():
        return config, auth, None, None, None

    monkeypatch.setattr(web_server, "get_dependencies", fake_get_dependencies)
    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    monkeypatch.setattr(api_router, "is_admin_user", lambda candidate, _config: candidate == "admin")
    app = web_server.create_app()
    return TestClient(app)


def authenticate(client: TestClient) -> None:
    client.cookies.set("access_token", TOKEN)


def test_app_lifespan_runs_shutdown_manager(monkeypatch) -> None:
    shutdown_manager = Mock()
    monkeypatch.setattr(web_server, "ShutdownManager", lambda: shutdown_manager)
    client = build_client(monkeypatch)

    with client:
        pass

    shutdown_manager.shutdown.assert_called_once_with()


def test_security_headers_are_added(monkeypatch) -> None:
    client = build_client(monkeypatch)

    response = client.get("/login")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["permissions-policy"]
    assert response.headers["content-security-policy"] == (
        "default-src 'self'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'; frame-src 'self'; img-src 'self' data:; "
        "object-src 'none'; script-src 'self'; style-src 'self'"
    )
    assert "cdn.tailwindcss.com" not in response.text
    assert "cdn.jsdelivr.net" not in response.text
    assert "/static/css/vendor.css" in response.text


def test_static_assets_are_served_with_patched_starlette(monkeypatch) -> None:
    client = build_client(monkeypatch)

    response = client.get("/static/css/vendor.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_pdf_security_headers_allow_same_origin_preview(monkeypatch) -> None:
    client = build_client(monkeypatch)
    cast(FastAPI, client.app).add_api_route(
        "/test-preview.pdf",
        lambda: Response(content=b"%PDF-1.4\n", media_type="application/pdf"),
    )

    response = client.get("/test-preview.pdf")

    assert response.status_code == 200
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" not in response.headers["content-security-policy"]


def test_unknown_host_is_rejected(monkeypatch) -> None:
    client = build_client(monkeypatch)

    response = client.get("/login", headers={"Host": "untrusted.example"})

    assert response.status_code == 400


def test_production_disables_api_docs(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    client = build_client(monkeypatch, allowed_hosts=["testserver"])

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_production_requires_explicit_allowed_hosts(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    try:
        build_client(monkeypatch)
    except RuntimeError as exc:
        assert "web.allowed_hosts" in str(exc)
    else:
        raise AssertionError("Production app accepted an empty host allowlist")


def test_app_routes_require_authentication(monkeypatch) -> None:
    client = build_client(monkeypatch)

    response = client.get("/app/upload", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_cors_is_disabled_by_default_for_same_origin_app(monkeypatch) -> None:
    client = build_client(monkeypatch)

    response = client.options(
        "/api/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_explicit_configured_origin(monkeypatch) -> None:
    client = build_client(
        monkeypatch,
        cors_allowed_origins=["https://trusted.example"],
    )

    response = client.options(
        "/api/login",
        headers={
            "Origin": "https://trusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://trusted.example"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_unconfigured_origin(monkeypatch) -> None:
    client = build_client(
        monkeypatch,
        cors_allowed_origins=["https://trusted.example"],
    )

    response = client.options(
        "/api/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_app_root_redirects_to_upload_for_authenticated_user(monkeypatch) -> None:
    client = build_client(monkeypatch)
    authenticate(client)

    response = client.get("/app", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app/upload"


def test_authenticated_app_page_sets_missing_csrf_cookie(monkeypatch) -> None:
    client = build_client(monkeypatch)
    authenticate(client)

    response = client.get("/app/upload")

    assert response.status_code == 200
    assert "csrf_token" in response.cookies


def test_removed_page_routes_are_not_registered_for_get(monkeypatch) -> None:
    client = build_client(monkeypatch)

    get_paths = {
        route.path
        for route in cast(FastAPI, client.app).routes
        if isinstance(route, Route) and "GET" in (route.methods or set())
    }

    assert "/dashboard" not in get_paths
    assert "/upload" not in get_paths


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
        ("/app/failures", "Failures"),
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
        assert 'data-nav-label="Overview"' not in response.text
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


def test_failures_page_includes_operator_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="operator", admin_users=["admin"])
    authenticate(client)

    response = client.get("/app/failures")

    assert response.status_code == 200
    assert 'id="failures-workspace"' in response.text
    assert "/static/js/failures.js" in response.text


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


def test_config_validation_page_includes_task_23_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    response = client.get("/app/settings/validation")

    assert response.status_code == 200
    assert 'id="config-validation-workspace"' in response.text
    assert "/static/js/config_validation.js" in response.text
    assert "Validate Config File" in response.text
    assert "Validate Pipeline" in response.text


def test_task_catalog_page_includes_task_20_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    response = client.get("/app/admin/tasks")

    assert response.status_code == 200
    assert 'id="task-catalog-workspace"' in response.text
    assert "/static/js/task_catalog.js" in response.text


def test_pipeline_config_page_includes_task_34_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    response = client.get("/app/admin/pipeline")

    assert response.status_code == 200
    assert 'id="pipeline-config-workspace"' in response.text
    assert 'id="pipeline-publish-button"' in response.text
    assert response.text.count('class="admin-panel ') == 7
    assert response.text.count('class="admin-panel-header"') == 6
    assert "/static/js/pipeline_config.js?v=task34" in response.text


def test_review_gate_and_split_pages_redirect_to_pipeline(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    review_gate = client.get("/app/admin/review-gate", follow_redirects=False)
    split_settings = client.get("/app/admin/split", follow_redirects=False)

    assert review_gate.status_code == 307
    assert review_gate.headers["location"] == "/app/admin/pipeline"
    assert split_settings.status_code == 307
    assert split_settings.headers["location"] == "/app/admin/pipeline"


def test_reports_page_includes_task_25_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="operator", admin_users=["admin"])
    authenticate(client)

    response = client.get("/app/reports")

    assert response.status_code == 200
    assert 'id="reports-workspace"' in response.text
    assert 'id="batch-detail-modal"' in response.text
    assert "/static/js/reports.js" in response.text


def test_settings_page_includes_task_25_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="operator", admin_users=["admin"])
    authenticate(client)

    response = client.get("/app/settings")

    assert response.status_code == 200
    assert 'id="settings-workspace"' in response.text
    assert "/static/js/settings.js" in response.text


def test_admin_dashboard_audit_and_users_pages_include_assets(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    dashboard = client.get("/app/admin")
    audit = client.get("/app/admin/audit")
    users = client.get("/app/admin/users")

    assert dashboard.status_code == 200
    assert 'id="admin-dashboard-workspace"' in dashboard.text
    assert "/static/js/admin.js" in dashboard.text
    assert audit.status_code == 200
    assert 'id="admin-audit-workspace"' in audit.text
    assert users.status_code == 200
    assert 'id="user-management"' in users.text
    assert "Current admin password" in users.text
    assert "Current Operator password" in users.text
    assert "/static/js/admin_users.js" in users.text
    assert "/static/js/admin_audit.js" in audit.text
