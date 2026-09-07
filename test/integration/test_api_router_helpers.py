"""Unit tests for API-router helpers and background upload orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sqlite3

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import modules.api_router as router
from modules.auth_utils import AuthError


class ConfigStub:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        value = self.values
        for part in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part, default)
        return value

    def get_all(self):
        return self.values


def _request(headers=None, cookies=None, client=None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": b"",
        "client": client,
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)
    if cookies:
        request._cookies = cookies
    return request


def test_router_path_and_payload_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert router._as_string_list(None) == []
    assert router._as_string_list("") == []
    assert router._as_string_list("admin") == ["admin"]
    assert router._as_string_list(("a", 2, "")) == ["a", "2"]
    assert router._as_string_list(3) == []
    assert router._iter_config_directory_values({"a_dir": "x", "nested": [{"b_dir": "y"}]}) == ["x", "y"]

    config = ConfigStub({"web": {"upload_dir": str(tmp_path)}, "watch_folder": {"dir": str(tmp_path), "processing_dir": ""}, "other": {"data_dir": str(tmp_path)}})
    roots = router._configured_pdf_roots(config, {"extra_dir": str(tmp_path)})
    assert roots == [tmp_path.resolve()]
    file_path = tmp_path / "x.pdf"
    file_path.write_bytes(b"%PDF")
    assert router._path_is_within_roots(file_path, roots)
    assert router._safe_pdf_candidate(str(file_path), roots) == file_path.resolve()
    assert router._safe_pdf_candidate(str(tmp_path.parent / "x.pdf"), roots) is None
    assert router._safe_pdf_candidate(str(tmp_path / "missing.pdf"), roots) is None

    monkeypatch.setattr(Path, "resolve", Mock(side_effect=OSError("bad path")))
    assert router._configured_pdf_roots(config) == []
    assert router._safe_pdf_candidate("x.pdf", [tmp_path]) is None


def test_router_auth_token_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    class Auth:
        def get_current_user(self, token):
            if token == "ok":
                return "admin"
            raise AuthError("expired token")

    with pytest.raises(HTTPException, match="Not authenticated"):
        router.get_current_user(None, Auth())
    with pytest.raises(HTTPException, match="expired token"):
        router.get_current_user("bad", Auth())
    assert router.get_current_user("ok", Auth()) == "admin"

    bearer = router.CookieOrHeaderTokenBearer()
    import asyncio
    assert asyncio.run(bearer(_request(headers={"Authorization": "Bearer abc"}))) == "abc"
    assert asyncio.run(bearer(_request(cookies={"access_token": "cookie"}))) == "cookie"
    assert asyncio.run(bearer(_request())) is None


def test_legacy_background_upload_helper_is_removed() -> None:
    assert not hasattr(router, "process_file_in_background")


def _router_helpers() -> dict[str, object]:
    helpers: dict[str, object] = {}
    for route in router.build_router().routes:
        endpoint = getattr(route, "endpoint", None)
        for cell in endpoint.__closure__ or ():
            value = cell.cell_contents
            if callable(value) and getattr(value, "__name__", "").startswith("_"):
                helpers[value.__name__] = value
    for value in list(helpers.values()):
        for cell in getattr(value, "__closure__", ()) or ():
            nested = cell.cell_contents
            if callable(nested) and getattr(nested, "__name__", "").startswith("_"):
                helpers[nested.__name__] = nested
    return helpers


def _body_request(body: bytes, content_type: str) -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"content-type", content_type.encode())],
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
        "client": ("127.0.0.1", 1),
    }
    return Request(scope, receive)


def _run(awaitable):
    return asyncio.run(awaitable)


def test_router_versioned_body_helpers() -> None:
    helpers = _router_helpers()
    assert "_parse_multipart_uploads" not in helpers
    assert "_multipart_scalar_values" not in helpers
    with pytest.raises(HTTPException, match="positive integer"):
        helpers["_required_revision"]({"expected_revision": 0})
    assert helpers["_required_revision"]({"expected_revision": 2}) == 2
    with pytest.raises(HTTPException, match="already exists"):
        helpers["_raise_versioned_error"](sqlite3.IntegrityError("duplicate"))
    with pytest.raises(RuntimeError):
        helpers["_raise_versioned_error"](RuntimeError("unexpected"))
def test_router_body_and_path_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    helpers = _router_helpers()
    assert "_multipart_scalar_values" not in helpers
    with pytest.raises(HTTPException, match="Invalid JSON"):
        _run(helpers["_json_body"](_body_request(b"{", "application/json")))
    assert _run(helpers["_json_body"](_body_request(b"", "application/json"))) == {}

    with pytest.raises(HTTPException, match="exceeds 1 MiB"):
        _run(helpers["_versioned_import_body"](_body_request(b"x" * (1_048_576 + 1), "application/json")))
    with pytest.raises(HTTPException, match="UTF-8"):
        _run(helpers["_versioned_import_body"](_body_request(b"\xff", "application/json")))
    with pytest.raises(HTTPException, match="Invalid JSON import"):
        _run(helpers["_versioned_import_body"](_body_request(b"{", "application/json")))
    assert _run(helpers["_versioned_import_body"](_body_request(b'{"content":"pipeline"}', "application/json"))) == "pipeline"

    with pytest.raises(HTTPException, match="Pipeline model"):
        helpers["_pipeline_model_payload"]({"model": []})
    assert helpers["_pipeline_model_payload"]({}) is None
    assert helpers["_secret_aliases"](ConfigStub({"pipeline_secrets": {"key": "secret"}})) == {"key"}
    with pytest.raises(HTTPException, match="Schema payload"):
        helpers["_schema_payload"]({"schema": []})
    assert helpers["_schema_payload"]({"name": "x", "fields": {}})["fields"] == {}

    config = ConfigStub({},)
    config._config_path = tmp_path / "config.yaml"
    child = tmp_path / "child"
    child.mkdir()
    (child / "data.csv").write_text("name,amount\nAlice,1\n", encoding="utf-8")
    (child / "notes.txt").write_text("x", encoding="utf-8")
    assert helpers["_pipeline_directory_listing"](config, ".")["current"] == "."
    assert helpers["_pipeline_file_listing"](config, "child", "csv")["files"][0]["name"] == "data.csv"
    outside_dir = child / "outside"
    outside_dir.mkdir()
    outside_file = child / "evil.csv"
    outside_file.write_text("x\n", encoding="utf-8")
    original_resolve = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda path: tmp_path.parent if path.name in {"outside", "evil.csv"} else original_resolve(path),
    )
    assert helpers["_pipeline_directory_listing"](config, "child")["directories"] == []
    assert [item["name"] for item in helpers["_pipeline_file_listing"](config, "child", "csv")["files"]] == ["data.csv"]
    monkeypatch.setattr(Path, "resolve", original_resolve)
    assert helpers["_pipeline_csv_metadata"](config, "child/data.csv")["columns"] == ["name", "amount"]
    with pytest.raises(HTTPException, match="CSV file not found"):
        helpers["_pipeline_csv_metadata"](config, "child/missing.csv")
    with pytest.raises(HTTPException, match="Path must reference"):
        helpers["_pipeline_csv_metadata"](config, "child/notes.txt")
    with pytest.raises(HTTPException, match="Directory not found"):
        helpers["_pipeline_directory_listing"](config, "missing")
    with pytest.raises(HTTPException, match="project-relative"):
        helpers["_pipeline_browser_path"](config, "../outside")


def test_router_remaining_nested_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    helpers = _router_helpers()
    assert "_parse_multipart_upload" not in helpers
    with pytest.raises(HTTPException, match="JSON or YAML"):
        _run(helpers["_versioned_import_body"](_body_request(b"x", "text/plain")))
    assert _run(helpers["_versioned_import_body"](_body_request(b"plain", "text/yaml"))) == "plain"

    admin_service = Mock()
    monkeypatch.setattr(router, "VersionedAdminService", lambda *args, **kwargs: admin_service)
    assert helpers["_versioned_admin_service"](ConfigStub({}), object()) is admin_service
    with pytest.raises(HTTPException, match="missing"):
        helpers["_raise_versioned_error"](KeyError("missing"))
    with pytest.raises(HTTPException, match="409"):
        helpers["_raise_versioned_error"](
            router.PipelineTemplateConflictError("stale", current={"secret": "x"})
        )
    with pytest.raises(HTTPException, match="422"):
        helpers["_raise_versioned_error"](
            router.ReviewSchemaValidationError({"findings": []})
        )
    assert helpers["_validation_summary"](
        [{"severity": "error"}, {"level": "warning"}, {"severity": "info"}]
    ) == {"errors": 1, "warnings": 1, "info": 1}

    reviews = Mock()
    reviews.list_queue.return_value = [
        {"id": "closed", "status": "completed", "metadata_json": "{}"},
        {"id": "open", "status": "pending", "metadata_json": '{"schema_file":"schema.yaml"}'},
        {"id": "other", "status": "in_review", "metadata_json": '{"schema_file":"other.yaml"}'},
    ]
    monkeypatch.setattr(router, "connect", lambda config: __import__("contextlib").nullcontext(object()))
    monkeypatch.setattr(router, "ReviewRepository", lambda conn: reviews)
    warning = helpers["_schema_active_review_warning"]("schema.yaml", ConfigStub({}))
    assert warning["active_review_count"] == 1
    assert helpers["_schema_active_review_warning"]("missing.yaml", ConfigStub({})) is None

    audit_service = Mock()
    monkeypatch.setattr(router, "AuditService", lambda conn: audit_service)
    helpers["_append_admin_audit"](
        ConfigStub({}), event_type="admin_test", user="admin", after={"ok": True}
    )
    audit_service.append_event.assert_called_once()

    with pytest.raises(HTTPException, match="Path is outside"):
        original_resolve = Path.resolve
        calls = {"count": 0}
        def resolve_outside(path):
            calls["count"] += 1
            return tmp_path.parent if calls["count"] == 2 else original_resolve(path)
        monkeypatch.setattr(Path, "resolve", resolve_outside)
        helpers["_pipeline_browser_path"](ConfigStub({"_config_path": str(tmp_path / "config.yaml")}), "child")

    csv_file = tmp_path / "bad.csv"
    csv_file.write_text("data", encoding="utf-8")
    config = ConfigStub({})
    config._config_path = tmp_path / "config.yaml"
    with pytest.raises(HTTPException, match="Unable to read CSV"):
        monkeypatch.setattr(Path, "open", Mock(side_effect=OSError("read")))
        helpers["_pipeline_csv_metadata"](config, "bad.csv")
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportOptionalMemberAccess=false
