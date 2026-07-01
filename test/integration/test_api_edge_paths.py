import asyncio
import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import modules.api_router as api
from modules.auth_utils import (
    AuthenticationSetupRequired,
    AuthError,
    LoginRateLimitError,
)
from modules.services.review_service import ReviewServiceError
from modules.services.admin_settings_service import AdminSettingsError
from modules.services.pipeline_config_service import PipelineConfigError
from modules.services.user_service import UserServiceError


class Config:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def get_all(self):
        return self.values


def _route(name):
    return next(route.endpoint for route in api.build_router().routes if route.name == name)


def _request(body=b"", content_type="application/json", client=("127.0.0.1", 1234)):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    headers = [(b"content-type", content_type.encode())]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": headers,
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
        "client": client,
    }
    return Request(scope, receive)


def _run(awaitable):
    return asyncio.run(awaitable)


def test_top_level_api_helpers_cover_edge_values(tmp_path, monkeypatch):
    assert api.convert_to_singapore_time(None) == ""
    assert api.convert_to_singapore_time("2026-01-01T00:00:00Z").endswith("GMT+8")
    assert api.convert_to_singapore_time("invalid") == "invalid"
    assert api._as_string_list(None) == []
    assert api._as_string_list("") == []
    assert api._as_string_list(("admin", "", 1)) == ["admin", "1"]
    assert api._as_string_list(1) == []
    assert api._confidence_band(None) == "missing"
    assert api._confidence_band("invalid") == "missing"
    assert api._confidence_band(0.8) == "medium"
    assert api._iter_config_directory_values(
        [{"output_dir": str(tmp_path)}, {"nested": [{"archive_dir": "archive"}]}]
    ) == [str(tmp_path), "archive"]

    config = Config({"ui.admin_enabled": False})
    assert api.is_admin_user("admin", config) is False

    root = tmp_path / "root"
    root.mkdir()
    pdf = root / "file.pdf"
    pdf.write_bytes(b"%PDF-")
    assert api._safe_pdf_candidate(None, [root]) is None
    assert api._safe_pdf_candidate(pdf, [root]) == pdf.resolve()
    assert api._safe_pdf_candidate(tmp_path / "outside.pdf", [root]) is None

    auth = Mock()
    auth.get_current_user.side_effect = AuthError("bad token")
    with pytest.raises(HTTPException) as exc_info:
        api.get_current_user("token", auth)
    assert exc_info.value.status_code == 401


def test_login_body_parsing_success_and_failure_paths(monkeypatch):
    auth = Mock(token_exp_minutes=5)
    auth.login.return_value = "token"
    monkeypatch.setattr(
        api,
        "get_dependencies",
        lambda: (Config(), auth, None, None, None),
    )
    endpoint = _route("login")

    result = _run(
        endpoint(
            _request(
                b"username=admin&password=secret",
                "application/x-www-form-urlencoded",
            )
        )
    )
    assert result.access_token == "token"
    assert result.expires_in == 300

    for body, content_type in [
        (b"", "application/json"),
        (b"{", "application/json"),
        (b"anything", "text/plain"),
    ]:
        with pytest.raises(HTTPException) as exc_info:
            _run(endpoint(_request(body, content_type)))
        assert exc_info.value.status_code == 400

    auth.login.side_effect = AuthenticationSetupRequired("setup users")
    with pytest.raises(HTTPException) as exc_info:
        _run(endpoint(_request(json.dumps({"username": "a", "password": "b"}).encode())))
    assert exc_info.value.status_code == 503

    auth.login.side_effect = LoginRateLimitError("limited")
    with pytest.raises(HTTPException) as exc_info:
        _run(endpoint(_request(json.dumps({"username": "a", "password": "b"}).encode())))
    assert exc_info.value.status_code == 429


def test_json_payload_validation_paths(monkeypatch):
    service = Mock()
    service.normalize_schema.return_value = {}
    service.schema_hash.return_value = "hash"
    monkeypatch.setattr(api, "ConfigValidationService", lambda config: service)
    monkeypatch.setattr(
        api,
        "get_dependencies",
        lambda: (Config(), None, None, None, None),
    )
    endpoint = _route("validate_pipeline_payload")

    with pytest.raises(HTTPException, match="Invalid JSON"):
        _run(endpoint(_request(b"{"), user="user"))
    with pytest.raises(HTTPException, match="must be an object"):
        _run(endpoint(_request(b"[]"), user="user"))

    service.validate_pipeline.side_effect = ValueError("invalid pipeline")
    with pytest.raises(HTTPException) as exc_info:
        _run(endpoint(_request(b"{}"), user="user"))
    assert exc_info.value.status_code == 400


def test_schema_endpoint_error_translation(monkeypatch):
    config = Config()
    service = Mock()
    service.normalize_schema.return_value = {}
    service.schema_hash.return_value = "hash"
    monkeypatch.setattr(api, "SchemaService", lambda config: service)
    monkeypatch.setattr(
        api,
        "get_dependencies",
        lambda: (config, None, None, None, None),
    )
    create = _route("create_schema")
    duplicate = _route("duplicate_schema")
    update = _route("update_schema")

    with pytest.raises(HTTPException, match="Schema name is required"):
        _run(create(_request(b"{}"), user="admin"))

    service.save_schema.side_effect = FileExistsError("exists")
    with pytest.raises(HTTPException) as exc_info:
        _run(create(_request(b'{"name":"schema","schema":{}}'), user="admin"))
    assert exc_info.value.status_code == 409

    service.save_schema.side_effect = ValueError("bad schema")
    with pytest.raises(HTTPException) as exc_info:
        _run(create(_request(b'{"name":"schema","schema":{}}'), user="admin"))
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException, match="New schema name is required"):
        _run(duplicate("schema", _request(b"{}"), user="admin"))

    for error, status_code in [
        (FileExistsError("exists"), 409),
        (FileNotFoundError("missing"), 404),
        (ValueError("bad"), 400),
    ]:
        service.duplicate_schema.side_effect = error
        with pytest.raises(HTTPException) as exc_info:
            _run(
                duplicate(
                    "schema",
                    _request(b'{"new_name":"copy"}'),
                    user="admin",
                )
            )
        assert exc_info.value.status_code == status_code

    service.load_schema.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        _run(update("missing", _request(b"{}"), user="admin"))
    assert exc_info.value.status_code == 404


def test_read_endpoints_translate_missing_records(monkeypatch):
    config = Config()
    connection = Mock()
    monkeypatch.setattr(api, "connect", lambda config: nullcontext(connection))
    monkeypatch.setattr(
        api,
        "get_dependencies",
        lambda: (config, None, None, None, None),
    )

    batch_service = Mock()
    batch_service.get_batch.return_value = None
    monkeypatch.setattr(api, "BatchService", lambda conn: batch_service)
    with pytest.raises(HTTPException, match="Batch not found"):
        _route("get_batch")("batch", user="user")
    with pytest.raises(HTTPException, match="Batch not found"):
        _route("list_batch_documents")("batch", user="user")

    failure_service = Mock()
    failure_service.get_failure.return_value = None
    monkeypatch.setattr(api, "FailureService", lambda conn: failure_service)
    with pytest.raises(HTTPException, match="Failure not found"):
        _route("get_failure_detail")("document", user="user")

    review_service = Mock()
    review_service.get_detail.return_value = None
    monkeypatch.setattr(api, "ReviewService", lambda conn, config: review_service)
    with pytest.raises(HTTPException, match="Review item not found"):
        _route("get_review_item")("review", user="user")


def test_document_field_and_resume_endpoints(monkeypatch):
    config = Config()
    connection = Mock()
    fields = [
        {
            "extracted_value_json": '{"a":1}',
            "corrected_value_json": "null",
            "final_value_json": "2",
            "source_json": "{}",
        }
    ]
    repository = Mock()
    repository.get_fields.return_value = fields
    monkeypatch.setattr(api, "connect", lambda config: nullcontext(connection))
    monkeypatch.setattr(api, "ExtractionRepository", lambda conn: repository)
    monkeypatch.setattr(
        api,
        "get_dependencies",
        lambda: (config, None, None, None, None),
    )

    result = _route("list_document_fields")("document", user="user")
    assert result[0]["extracted_value"] == {"a": 1}
    assert result[0]["final_value"] == 2

    resume = Mock()
    resume.resume_document.return_value = True
    monkeypatch.setattr(api, "ResumeManager", lambda config: resume)
    assert _route("resume_document")("document", user="user") == {"resumed": True}


def test_review_mutation_errors_are_conflicts(monkeypatch):
    config = Config()
    connection = Mock()
    service = Mock()
    service.claim.side_effect = ReviewServiceError("conflict")
    service.release.side_effect = ReviewServiceError("conflict")
    service.save_draft.side_effect = ReviewServiceError("conflict")
    service.complete.side_effect = ReviewServiceError("conflict")
    monkeypatch.setattr(api, "connect", lambda config: nullcontext(connection))
    monkeypatch.setattr(api, "ReviewService", lambda conn, config: service)
    monkeypatch.setattr(
        api,
        "get_dependencies",
        lambda: (config, None, None, None, None),
    )

    cases = [
        ("claim_review_item", b'{"user":"operator"}'),
        ("release_review_item", b'{"user":"operator"}'),
        ("save_review_draft", b'{"user":"operator","corrections":{}}'),
        ("complete_review_item", b'{"user":"operator","corrections":{}}'),
    ]
    for name, body in cases:
        with pytest.raises(HTTPException) as exc_info:
            _run(_route(name)("review", _request(body), user="operator"))
        assert exc_info.value.status_code == 409


def test_admin_endpoint_success_and_error_translation(monkeypatch):
    config = Config()
    connection = Mock()
    monkeypatch.setattr(api, "connect", lambda config: nullcontext(connection))
    monkeypatch.setattr(api, "require_admin_user", Mock())
    monkeypatch.setattr(
        api,
        "get_dependencies",
        lambda: (config, None, None, None, None),
    )

    users = Mock()
    users.list_users.return_value = [{"username": "admin"}]
    monkeypatch.setattr(api, "UserService", lambda conn: users)
    assert _route("get_admin_users")(user="admin") == {
        "users": [{"username": "admin"}]
    }
    users.change_password.side_effect = UserServiceError("rejected")
    with pytest.raises(HTTPException) as exc_info:
        _run(
            _route("change_admin_user_password")(
                "operator",
                _request(
                    b'{"current_admin_password":"x","new_password":"y","confirmation":"z"}'
                ),
                user="admin",
            )
        )
    assert exc_info.value.status_code == 400

    settings = Mock()
    settings.get_admin_settings.return_value = {"settings": {}}
    monkeypatch.setattr(api, "AdminSettingsService", lambda config, conn: settings)
    assert _route("get_admin_settings")(user="admin") == {"settings": {}}
    settings.update_admin_settings.side_effect = AdminSettingsError("bad settings")
    with pytest.raises(HTTPException) as exc_info:
        _run(_route("update_admin_settings")(_request(b"{}"), user="admin"))
    assert exc_info.value.status_code == 400

def test_admin_pipeline_model_and_service_errors(monkeypatch):
    config = Config()
    connection = Mock()
    service = Mock()
    monkeypatch.setattr(api, "connect", lambda config: nullcontext(connection))
    monkeypatch.setattr(api, "require_admin_user", Mock())
    monkeypatch.setattr(api, "PipelineConfigService", lambda config, conn: service)
    monkeypatch.setattr(
        api,
        "get_dependencies",
        lambda: (config, None, None, None, None),
    )

    service.save_draft.side_effect = PipelineConfigError("draft")
    with pytest.raises(HTTPException) as exc_info:
        _run(
            _route("save_admin_pipeline_draft")(
                _request(b'{"model":{"steps":[]}}'),
                user="admin",
            )
        )
    assert exc_info.value.status_code == 400

    for route_name, method_name in [
        ("diff_admin_pipeline", "diff"),
        ("validate_admin_pipeline", "validate_draft"),
    ]:
        getattr(service, method_name).side_effect = PipelineConfigError("invalid")
        with pytest.raises(HTTPException) as exc_info:
            _run(
                _route(route_name)(
                    _request(b'{"model":{"steps":[]}}'),
                    user="admin",
                )
            )
        assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException, match="must be an object"):
        _run(
            _route("diff_admin_pipeline")(
                _request(b'{"model":[]}'),
                user="admin",
            )
        )
