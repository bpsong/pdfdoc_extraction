import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from web.server import create_app
from modules.auth_utils import AuthUtils, AuthError


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

        def login(self, username: str, password: str) -> str:
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


def test_login_success_returns_redirect_and_cookie(client, mock_auth):
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    # Check cookie is set
    cookies = resp.cookies
    assert "access_token" in cookies


def test_login_failure_returns_login_page_with_error(client, mock_auth):
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # On failure web UI renders the login form again.
    assert resp.status_code == 200
    assert 'form action="/auth/login"' in resp.text


def test_upload_requires_auth(api_client):
    # no auth header -> API should return 401 Unauthorized
    files = {"file": ("test.pdf", b"%PDF- dummy", "application/pdf")}
    resp = api_client.post("/upload", files=files)
    assert resp.status_code == 401


@patch("modules.api_router.FileProcessor")
def test_upload_pdf_success_redirects_to_dashboard(mock_fp_cls, api_client, mock_auth):
    # The API upload endpoint schedules background processing and returns a redirect to /dashboard
    mock_fp = MagicMock()
    mock_fp.process_file.return_value = None
    mock_fp_cls.return_value = mock_fp

    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature"
    files = {"file": ("test.pdf", b"%PDF- dummy", "application/pdf")}
    resp = api_client.post("/upload", files=files, headers={"Authorization": f"Bearer {token}"}, follow_redirects=False)
    # API router's upload returns RedirectResponse to /dashboard
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


def test_list_files_requires_auth(api_client):
    resp = api_client.get("/api/files")
    assert resp.status_code == 401


@patch("modules.api_router.os.listdir")
@patch("modules.api_router.open")
@patch("modules.api_router.os.path.isdir")
def test_list_files_returns_list(mock_isdir, mock_open, mock_listdir, api_client, mock_auth, tmp_path: Path):
    mock_isdir.return_value = True
    mock_listdir.return_value = ["a.txt", "b.txt", "ignore.pdf"]

    file_data = {
        "a.txt": {
            "id": "a",
            "original_filename": "A.pdf",
            "status": "Pending",
            "timestamps": {"created": "t1", "pending": "t1"},
            "error": None,
        },
        "b.txt": {
            "id": "b",
            "original_filename": "B.pdf",
            "status": "Completed",
            "timestamps": {"created": "t2", "pending": "t3"},
            "error": None,
        },
    }

    def fake_open(path, mode="r", encoding=None):
        name = Path(path).name
        content = json.dumps(file_data[name])
        m = MagicMock()
        m.__enter__.return_value = MagicMock(read=MagicMock(return_value=content))
        return m

    mock_open.side_effect = fake_open

    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature"
    resp = api_client.get("/api/files", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    ids = {item["file_id"] for item in data}
    assert ids == {"a", "b"}


def test_get_status_requires_auth(api_client):
    resp = api_client.get("/api/status/abc")
    assert resp.status_code == 401


@patch("modules.api_router.StatusManager")
def test_get_status_not_found_returns_404(mock_sm_cls, api_client, mock_auth):
    mock_sm = MagicMock()
    mock_sm.get_status.return_value = None
    mock_sm_cls.return_value = mock_sm

    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature"
    resp = api_client.get("/api/status/unknown", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@patch("modules.api_router.StatusManager")
def test_get_status_success_returns_payload(mock_sm_cls, api_client, mock_auth):
    mock_sm = MagicMock()
    mock_sm.get_status.return_value = {
        "id": "abc",
        "original_filename": "Test.pdf",
        "status": "Pending",
        "timestamps": {"created": "t1", "pending": "t1"},
        "error": None,
    }
    mock_sm_cls.return_value = mock_sm

    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature"
    resp = api_client.get("/api/status/abc", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["file_id"] == "abc"
    assert payload["original_name"] == "Test.pdf"
    assert payload["status"] == "Pending"