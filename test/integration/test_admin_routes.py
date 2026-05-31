from __future__ import annotations

from fastapi.testclient import TestClient

from test.integration.test_new_ui_routes import authenticate, build_client


ADMIN_ROUTES = [
    "/app/admin",
    "/app/schemas",
    "/app/schemas/invoice",
    "/app/settings/validation",
    "/app/admin/pipeline",
    "/app/admin/tasks",
    "/app/admin/review-gate",
    "/app/admin/split",
    "/app/admin/audit",
    "/app/admin/dry-run",
]


def test_operator_cannot_access_admin_app_routes(monkeypatch) -> None:
    client = build_client(monkeypatch, username="operator", admin_users=["admin"])
    authenticate(client)

    for route in ADMIN_ROUTES:
        response = client.get(route)
        assert response.status_code == 403, route
        assert response.json()["detail"] == "Admin role required"


def test_admin_can_access_admin_app_routes(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    expected_titles = {
        "/app/admin": "Admin",
        "/app/schemas": "Schema Editor",
        "/app/schemas/invoice": "Schema Editor",
        "/app/settings/validation": "Validation Center",
        "/app/admin/pipeline": "Pipeline",
        "/app/admin/tasks": "Task Catalog",
        "/app/admin/review-gate": "Review Gate",
        "/app/admin/split": "Split Settings",
        "/app/admin/audit": "Admin Audit",
        "/app/admin/dry-run": "Pipeline Dry Run",
    }

    for route, title in expected_titles.items():
        response = client.get(route)
        assert response.status_code == 200, route
        assert title in response.text
        assert "Admin Home" in response.text
        assert 'href="/app/admin/pipeline"' in response.text
        assert 'href="/app/settings/validation"' in response.text


def test_admin_fallback_uses_configured_single_user_when_admin_list_is_empty(monkeypatch) -> None:
    client: TestClient = build_client(monkeypatch, username="admin", admin_users=[])
    authenticate(client)

    response = client.get("/app/admin")

    assert response.status_code == 200
    assert "Admin Home" in response.text
