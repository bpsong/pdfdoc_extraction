"""Additional coverage for web-server helpers and authentication branches."""

from __future__ import annotations

import sys
from typing import Any, cast
from unittest.mock import Mock

import pytest
from starlette.requests import Request

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import web.server as web_server
from modules.auth_utils import AuthenticationSetupRequired, AuthError, LoginRateLimitError
from test.integration.test_new_ui_routes import authenticate, build_client


class ConfigStub:
    def __init__(self, values: dict[str, Any]):
        self.values = values

    def get(self, key: str, default: Any = None) -> Any:
        value: Any = self.values
        for part in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part, default)
        return value


def test_server_config_helpers_cover_string_list_and_production_rules(monkeypatch) -> None:
    assert web_server._cors_allowed_origins(ConfigStub({"web": {"cors_allowed_origins": " a, ,b "}})) == ["a", "b"]
    assert web_server._cors_allowed_origins(ConfigStub({"web": {"cors_allowed_origins": ["a", " ", 3]}})) == ["a", "3"]
    assert web_server._cors_allowed_origins(ConfigStub({"web": {"cors_allowed_origins": 3}})) == []
    assert web_server._allowed_hosts(ConfigStub({"web": {"allowed_hosts": 3}}), False)[-1] == "testserver"
    assert web_server._allowed_hosts(ConfigStub({"web": {"allowed_hosts": " a, b "}}), True) == ["a", "b"]
    assert "testserver" in web_server._allowed_hosts(ConfigStub({"web": {"host": "custom"}}), False)
    try:
        web_server._allowed_hosts(ConfigStub({"web": {"allowed_hosts": ["*"]}}), True)
    except RuntimeError as exc:
        assert "explicit hostnames" in str(exc)
    else:
        raise AssertionError("wildcard production host was accepted")
    captured: dict[str, Any] = {}
    previous_trace = sys.gettrace()

    def trace(frame, event, _arg):
        if frame.f_code.co_name == "create_app":
            for name in ("_as_string_list", "_client_identifier"):
                if name in frame.f_locals:
                    captured[name] = frame.f_locals[name]
        return trace

    sys.settrace(trace)
    try:
        app = build_client(monkeypatch).app
    finally:
        sys.settrace(previous_trace)
    monkeypatch.setenv("APP_ENV", "production")
    assert web_server._is_production() is True
    assert captured["_as_string_list"](None) == []
    assert captured["_as_string_list"]("") == []
    assert captured["_as_string_list"](("a", "", 2)) == ["a", "2"]
    assert captured["_as_string_list"](object()) == []
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": None})
    assert captured["_client_identifier"](request) == "unknown"


def test_server_login_form_and_json_error_variants(monkeypatch) -> None:
    client = build_client(monkeypatch)
    assert client.post("/login", data={}).status_code == 200
    assert client.post("/login", content=b"not-json", headers={"content-type": "application/json"}).status_code == 200
    assert client.post("/login", content=b"{}", headers={"content-type": "application/json"}).status_code == 200
    assert client.post("/login", content=b"x=1", headers={"content-type": "text/plain"}).status_code == 200

    class AuthStub:
        token_exp_minutes = 10

        def __init__(self, failure=None):
            self.failure = failure

        def login(self, *_args, **_kwargs):
            if self.failure:
                raise self.failure
            return "token"

        def get_current_user(self, token):
            return "admin" if token == "token" else (_ for _ in ()).throw(AuthError("token invalid"))

        def is_admin(self, _username):
            return True

    config = ConfigStub({"ui": {"admin_enabled": True}})
    auth = AuthStub()
    monkeypatch.setattr(web_server, "get_dependencies", lambda: (config, auth, None, None, None))
    success = client.post("/login", data={"username": "admin", "password": "pw"}, follow_redirects=False)
    assert success.status_code == 303
    assert "access_token" in success.cookies

    for failure, expected in ((AuthenticationSetupRequired("setup"), 503), (LoginRateLimitError(), 429), (AuthError("bad"), 200)):
        monkeypatch.setattr(web_server, "get_dependencies", lambda failure=failure: (config, AuthStub(failure), None, None, None))
        response = client.post("/login", data={"username": "admin", "password": "pw"})
        assert response.status_code == expected


def test_server_redirect_and_logout_routes(monkeypatch) -> None:
    client = build_client(monkeypatch)
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    authenticate(client)
    assert client.get("/", follow_redirects=False).headers["location"] == "/app/upload"
    assert client.get("/login", follow_redirects=False).headers["location"] == "/app/upload"
    assert client.post("/auth/login", data={}).status_code == 200
    logout = client.get("/logout", follow_redirects=False)
    assert logout.status_code == 307
    assert logout.headers["location"] == "/login"

    client.cookies.set("access_token", "invalid")
    assert client.get("/app/upload", follow_redirects=False).status_code == 307


def test_server_startup_failure_prevents_app_creation(monkeypatch) -> None:
    startup_checks = Mock(side_effect=RuntimeError("startup failure"))

    with pytest.raises(RuntimeError, match="startup failure"):
        build_client(monkeypatch, startup_checks=startup_checks)


def test_server_admin_schema_route_and_json_http_exception(monkeypatch) -> None:
    client = build_client(monkeypatch, username="admin", admin_users=["admin"])
    authenticate(client)
    response = client.get("/app/schemas/example")
    assert response.status_code == 200
    assert "Review Form Editor" in response.text

    app = cast(FastAPI, client.app)

    async def bad_route():
        raise HTTPException(status_code=418, detail=None)

    app.add_api_route("/test-http-error", bad_route)
    response = client.get("/test-http-error")
    assert response.status_code == 418
    assert "detail" in response.json()
# pyright: reportArgumentType=false
