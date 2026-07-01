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
        "/app/admin/audit": "Admin Audit",
    }

    for route, title in expected_titles.items():
        response = client.get(route)
        assert response.status_code == 200, route
        assert title in response.text
        assert "Admin Home" in response.text
        assert 'href="/app/admin/pipeline"' in response.text
        assert 'href="/app/settings/validation"' in response.text


def test_removed_review_simulator_surfaces_are_not_available(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    dashboard = client.get("/app/admin")

    assert client.get("/app/admin/dry-run").status_code == 404
    assert client.post("/api/admin/dry-run", json={}).status_code == 404
    assert "Review Simulator" not in dashboard.text
    assert ">Tools</div>" not in dashboard.text


def test_demoted_admin_config_routes_redirect_to_pipeline(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    for route in ("/app/admin/review-gate", "/app/admin/split"):
        response = client.get(route, follow_redirects=False)
        assert response.status_code == 307, route
        assert response.headers["location"] == "/app/admin/pipeline"


def test_admin_fallback_uses_configured_single_user_when_admin_list_is_empty(monkeypatch) -> None:
    client: TestClient = build_client(monkeypatch, username="admin", admin_users=[])
    authenticate(client)

    response = client.get("/app/admin")

    assert response.status_code == 200
    assert "Admin Home" in response.text


def test_admin_task_catalog_api_requires_admin(monkeypatch) -> None:
    client = build_client(monkeypatch, username="operator", admin_users=["admin"])
    authenticate(client)

    response = client.get("/api/admin/task-catalog")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_admin_task_catalog_api_returns_catalog(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)

    response = client.get("/api/admin/task-catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total"] >= 1
    assert any(task["class_name"] == "ReviewGateTask" for task in payload["tasks"])
