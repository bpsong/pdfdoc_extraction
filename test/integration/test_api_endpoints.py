from pathlib import Path
from typing import Callable
from unittest.mock import patch, MagicMock

import bcrypt
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

import modules.api_router as api_router
from web.server import create_app
from modules.auth_utils import AuthUtils, AuthError
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository
from modules.services.batch_service import BatchService
from test.helpers_sqlite import TempConfig


TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature"


@pytest.fixture
def client(mock_auth):
    """Full web app TestClient (HTML routes, cookie-based auth)."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def api_client(monkeypatch, mock_auth):
    """API-only TestClient that mounts only the API router (returns JSON tokens)."""
    from fastapi import FastAPI
    from modules.api_router import build_router

    app = FastAPI()
    app.include_router(build_router())
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_auth(monkeypatch):
    """
    Patch AuthUtils to avoid real bcrypt/jwt dependencies in unit tests.
    """
    class FakeAuth(AuthUtils):  # type: ignore
        def __init__(self, *args, **kwargs):
            # minimal fields for test
            self.settings = type("S", (), {"token_exp_minutes": 30, "username": "admin"})
            self.secret_key = "your_secret_key"
            self.algorithm = "HS256"
            self.token_exp_minutes = 30

        def login(self, username: str, password: str, client_id: str | None = None) -> str:
            if username == "admin" and password == "secret":
                # Return a dummy JWT-like token (router accepts it during tests via patched decode)
                return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature"
            raise AuthError("Invalid credentials")

        def decode_token(self, token: str):
            if token == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature":
                return {"sub": "admin"}
            raise AuthError("Invalid token")

        def get_current_user(self, token: str) -> str:
            if token == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature":
                return "admin"
            raise AuthError("Invalid token")

    monkeypatch.setattr("web.server.AuthUtils", FakeAuth)
    monkeypatch.setattr("modules.api_router.AuthUtils", FakeAuth)
    return FakeAuth


def _sqlite_api_config(
    monkeypatch,
    tmp_path: Path,
    auth_cls: Callable[[], AuthUtils],
) -> TempConfig:
    """Route API dependencies to a migrated temporary SQLite database."""
    config = TempConfig(tmp_path / "app.sqlite3", {})
    initialize_database(config)
    auth = auth_cls()
    monkeypatch.setattr(api_router, "get_dependencies", lambda: (config, auth, None, None, None))
    return config


def _create_api_document(
    config: TempConfig,
    tmp_path: Path,
    *,
    document_id: str,
    original_filename: str,
    source: str = "web",
    status: str = "processing",
) -> dict:
    """Seed one SQLite-backed document for legacy compatibility API tests."""
    source_file = tmp_path / original_filename
    source_file.write_bytes(b"%PDF-1.4\n")
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source=source,
            file_path=str(source_file),
            original_filename=original_filename,
            document_id=document_id,
        )
        DocumentRepository(conn).update_status(document_id, status)
    return created


def test_login_success_returns_redirect_and_cookie(client, mock_auth):
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/upload"
    # Check cookie is set
    cookies = resp.cookies
    assert "access_token" in cookies
    assert "csrf_token" in cookies


def test_login_failure_returns_login_page_with_error(client, mock_auth):
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # On failure web UI renders the login form again.
    assert resp.status_code == 200
    assert 'form action="/auth/login"' in resp.text


def test_api_login_rate_limit_returns_429(monkeypatch, tmp_path: Path):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "database": {"run_migrations_on_startup": False},
            "authentication": {
                "username": "admin",
                "password_hash": password_hash,
            },
            "web": {
                "secret_key": "test-secret-key-with-enough-entropy",
                "token_exp_minutes": 30,
            },
            "auth": {
                "login_max_failed_attempts": 2,
                "login_window_seconds": 600,
                "login_cooldown_seconds": 600,
            },
        },
    )
    auth = AuthUtils(config)
    AuthUtils.reset_login_rate_limits()
    monkeypatch.setattr(api_router, "get_dependencies", lambda: (config, auth, None, None, None))

    app = FastAPI()
    app.include_router(api_router.build_router())
    with TestClient(app) as local_client:
        first = local_client.post("/api/login", json={"username": "admin", "password": "wrong"})
        second = local_client.post("/api/login", json={"username": "admin", "password": "wrong"})
        blocked = local_client.post("/api/login", json={"username": "admin", "password": "wrong"})

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many failed login attempts. Try again later."


def test_browser_login_rate_limit_renders_429(monkeypatch, tmp_path: Path):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "database": {"run_migrations_on_startup": False},
            "authentication": {
                "username": "admin",
                "password_hash": password_hash,
            },
            "web": {
                "secret_key": "test-secret-key-with-enough-entropy",
                "token_exp_minutes": 30,
            },
            "auth": {
                "login_max_failed_attempts": 2,
                "login_window_seconds": 600,
                "login_cooldown_seconds": 600,
                "roles_enabled": True,
                "default_admin_users": ["admin"],
            },
            "ui": {
                "app_name": "DocFlow AI",
                "admin_enabled": True,
            },
        },
    )
    auth = AuthUtils(config)
    AuthUtils.reset_login_rate_limits()

    def fake_get_dependencies():
        return config, auth, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    monkeypatch.setattr("web.server.get_dependencies", fake_get_dependencies)

    app = create_app()
    with TestClient(app) as local_client:
        first = local_client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        second = local_client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        blocked = local_client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert blocked.status_code == 429
    assert "Too many failed login attempts. Try again later." in blocked.text


def test_upload_requires_auth(api_client):
    # no auth header -> API should return 401 Unauthorized
    files = {"file": ("test.pdf", b"%PDF- dummy", "application/pdf")}
    resp = api_client.post("/upload", files=files)
    assert resp.status_code == 401


@patch("modules.api_router.FileProcessor")
def test_upload_pdf_success_redirects_to_processing(mock_fp_cls, api_client, mock_auth):
    # The legacy API upload endpoint schedules processing and returns a redirect to the app workflow page.
    mock_fp = MagicMock()
    mock_fp.process_file.return_value = None
    mock_fp_cls.return_value = mock_fp

    files = {"file": ("test.pdf", b"%PDF- dummy", "application/pdf")}
    resp = api_client.post("/upload", files=files, headers={"Authorization": f"Bearer {TOKEN}"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/processing"


def test_list_files_requires_auth(api_client):
    resp = api_client.get("/api/files")
    assert resp.status_code == 401


def test_list_files_returns_list(api_client, mock_auth, tmp_path: Path, monkeypatch):
    config = _sqlite_api_config(monkeypatch, tmp_path, mock_auth)
    _create_api_document(
        config,
        tmp_path,
        document_id="a",
        original_filename="A.pdf",
        source="web",
        status="processing",
    )
    _create_api_document(
        config,
        tmp_path,
        document_id="b",
        original_filename="B.pdf",
        source="watch_folder",
        status="completed",
    )

    resp = api_client.get("/api/files", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    ids = {item["file_id"] for item in data}
    assert ids == {"a", "b"}
    assert {item["details"] for item in data} == {None}


def test_get_status_requires_auth(api_client):
    resp = api_client.get("/api/status/abc")
    assert resp.status_code == 401


def test_get_status_not_found_returns_404(api_client, mock_auth, tmp_path: Path, monkeypatch):
    _sqlite_api_config(monkeypatch, tmp_path, mock_auth)

    resp = api_client.get("/api/status/unknown", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 404


def test_get_status_success_returns_payload(api_client, mock_auth, tmp_path: Path, monkeypatch):
    config = _sqlite_api_config(monkeypatch, tmp_path, mock_auth)
    _create_api_document(
        config,
        tmp_path,
        document_id="abc",
        original_filename="Test.pdf",
        source="web",
        status="processing",
    )

    resp = api_client.get("/api/status/abc", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["file_id"] == "abc"
    assert payload["original_name"] == "Test.pdf"
    assert payload["status"] == "processing"
    assert payload["details"]["legacy_endpoint"] is True
    assert payload["details"]["state_source"] == "sqlite"
    assert payload["details"]["document"]["id"] == "abc"
    assert payload["details"]["files"][0]["file_type"] == "source_original"
