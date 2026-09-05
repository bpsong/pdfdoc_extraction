import asyncio
import json
from contextlib import nullcontext
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

import modules.api_router as api
from modules.auth_utils import (
    AuthenticationSetupRequired,
    AuthError,
    LoginRateLimitError,
)
from modules.db.migrations import initialize_database
from modules.services.review_service import ReviewServiceError
from modules.services.admin_settings_service import AdminSettingsError
from modules.services.pipeline_config_service import PipelineConfigError
from modules.services.user_service import UserServiceError
from test.helpers_sqlite import TempConfig, initialize_test_users


class Config:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def get_all(self):
        return self.values


def _route(name):
    return next(
        route.endpoint
        for route in api.build_router().routes
        if isinstance(route, APIRoute) and route.name == name
    )


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
    assert api.convert_to_singapore_time(
        "2026-01-01T00:00:00Z"
    ) == "01-01-2026 08:00:00 GMT+8"
    assert api.convert_to_singapore_time(
        "2026-01-01T00:00:00"
    ) == "01-01-2026 08:00:00 GMT+8"
    assert api.convert_to_singapore_time(
        "2026-01-01T00:00:00+08:00"
    ) == "01-01-2026 00:00:00 GMT+8"
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


def test_dependency_resolution_does_not_run_database_migrations(
    tmp_path,
    monkeypatch,
):
    config = Config({"database.run_migrations_on_startup": True})
    auth = object()
    workflow_manager = object()
    file_processor = object()
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setattr(api, "ConfigManager", Mock(return_value=config))
    monkeypatch.setattr(api, "AuthUtils", Mock(return_value=auth))
    monkeypatch.setattr(api, "WorkflowManager", Mock(return_value=workflow_manager))
    monkeypatch.setattr(api, "FileProcessor", Mock(return_value=file_processor))

    dependencies = api.get_dependencies()

    assert dependencies == (
        config,
        auth,
        None,
        workflow_manager,
        file_processor,
    )


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


def test_schema_endpoint_error_translation(monkeypatch, tmp_path):
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    initialize_test_users(config)
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

    for endpoint, args, replacement in [
        (create, (_request(b"{}"),), "/api/admin/review-schemas"),
        (
            duplicate,
            ("schema", _request(b"{}")),
            "versioned review-schema template",
        ),
        (
            update,
            ("schema", _request(b"{}")),
            "/api/admin/review-schemas/{template_id}/draft",
        ),
    ]:
        with pytest.raises(HTTPException) as exc_info:
            _run(endpoint(*args, user="admin"))
        assert exc_info.value.status_code == 410
        assert replacement in str(exc_info.value.detail)


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

    with pytest.raises(HTTPException) as exc_info:
        _run(
            _route("save_admin_pipeline_draft")(
                _request(b'{"model":{"steps":[]}}'),
                user="admin",
            )
        )
    assert exc_info.value.status_code == 410
    assert "/api/admin/pipeline-templates/{template_id}/draft" in str(exc_info.value.detail)

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


def _multipart_part(name: str, payload: bytes, filename: str | None = None):
    return type(
        "Part",
        (),
        {
            "get_content_disposition": lambda self: "form-data",
            "get_param": lambda self, key, header=None: name,
            "get_filename": lambda self: filename,
            "get_payload": lambda self, decode=True: payload,
            "get_content_type": lambda self: "application/pdf" if filename else "text/plain",
        },
    )()


def _install_multipart_parser(monkeypatch, parts):
    message = Mock(iter_parts=lambda: iter(parts))
    monkeypatch.setattr(api, "BytesParser", lambda policy: Mock(parsebytes=lambda body: message))


def test_upload_and_batch_routes_cover_validation_and_cleanup_branches(tmp_path: Path, monkeypatch) -> None:
    config = Config({"web.upload_dir": str(tmp_path / "uploads"), "watch_folder.processing_dir": str(tmp_path / "processing")})
    Path(config.values["web.upload_dir"]).mkdir()
    processor = Mock()
    monkeypatch.setattr(api, "get_dependencies", lambda: (config, None, None, None, processor))
    upload_route = _route("upload_pdf")
    _install_multipart_parser(monkeypatch, [_multipart_part("file", b"%PDF-1.4", "file.pdf")])
    response = _run(_route("upload_pdf")(_request(b"body", "multipart/form-data; boundary=x"), BackgroundTasks(), user="admin"))
    assert response.status_code == 303

    config.values["web.upload_dir"] = ""
    _install_multipart_parser(monkeypatch, [_multipart_part("file", b"%PDF-1.4", "file.pdf")])
    with pytest.raises(HTTPException, match="not configured"):
        _run(upload_route(_request(b"body", "multipart/form-data; boundary=x"), BackgroundTasks(), user="admin"))

    config.values["web.upload_dir"] = str(tmp_path / "uploads")
    monkeypatch.setattr(api.utils_mod, "is_pdf_header", lambda *args, **kwargs: False)
    _install_multipart_parser(monkeypatch, [_multipart_part("file", b"bad", "bad.pdf")])
    monkeypatch.setattr(api.os, "remove", Mock(side_effect=OSError("locked")))
    with pytest.raises(HTTPException, match="Invalid PDF header"):
        _run(upload_route(_request(b"body", "multipart/form-data; boundary=x"), BackgroundTasks(), user="admin"))
    monkeypatch.setattr(api.utils_mod, "is_pdf_header", Mock(side_effect=OSError("header")))
    _install_multipart_parser(monkeypatch, [_multipart_part("file", b"%PDF-1.4", "file.pdf")])
    with pytest.raises(HTTPException, match="Invalid PDF header"):
        _run(upload_route(_request(b"body", "multipart/form-data; boundary=x"), BackgroundTasks(), user="admin"))

    batch_route = _route("upload_pdf_batch")
    user_repo = Mock()
    user_repo.get.return_value = {"role": "operator"}
    assignment = Mock()
    assignment.resolve_selection.return_value = {"id": "v1"}
    monkeypatch.setattr(api, "UserRepository", lambda _conn: user_repo)
    monkeypatch.setattr(api, "IngestionAssignmentService", lambda *_args: assignment)
    monkeypatch.setattr(api, "connect", lambda _config: nullcontext(object()))
    config.values["watch_folder.processing_dir"] = ""
    _install_multipart_parser(monkeypatch, [_multipart_part("pipeline_version_id", b"v1"), _multipart_part("files", b"%PDF-1.4", "file.pdf")])
    with pytest.raises(HTTPException, match="Processing directory"):
        _run(batch_route(_request(b"body", "multipart/form-data; boundary=x"), BackgroundTasks(), user="operator"))

    config.values["watch_folder.processing_dir"] = str(tmp_path / "processing")
    _install_multipart_parser(monkeypatch, [_multipart_part("pipeline_version_id", b"v1"), _multipart_part("files", b"bad", "bad.pdf")])
    with pytest.raises(HTTPException, match="invalid PDF header"):
        _run(batch_route(_request(b"body", "multipart/form-data; boundary=x"), BackgroundTasks(), user="operator"))

    valid_file = _multipart_part("files", b"%PDF-1.4", "valid.pdf")
    assignment.create_batch.side_effect = api.IngestionAssignmentError("create failed")
    _install_multipart_parser(monkeypatch, [_multipart_part("pipeline_version_id", b"v1"), valid_file])
    monkeypatch.setattr(api.os, "remove", Mock(side_effect=OSError("locked")))
    with pytest.raises(HTTPException, match="create failed"):
        _run(batch_route(_request(b"body", "multipart/form-data; boundary=x"), BackgroundTasks(), user="operator"))
    assignment.create_batch.side_effect = RuntimeError("unexpected")
    _install_multipart_parser(monkeypatch, [_multipart_part("pipeline_version_id", b"v1"), valid_file])
    with pytest.raises(HTTPException, match="unexpected"):
        _run(batch_route(_request(b"body", "multipart/form-data; boundary=x"), BackgroundTasks(), user="operator"))


def test_remaining_admin_and_document_route_error_branches(monkeypatch) -> None:
    config = Config({})
    connection = Mock()
    monkeypatch.setattr(api, "get_dependencies", lambda: (config, None, None, None, None))
    monkeypatch.setattr(api, "connect", lambda _config: nullcontext(connection))
    monkeypatch.setattr(api, "require_admin_user", Mock())

    with pytest.raises(HTTPException, match="Unsupported pipeline"):
        _route("available_pipelines")(source="other", user="admin")

    binding_service = Mock()
    monkeypatch.setattr(api, "IngressBindingService", lambda *_args: binding_service)
    for method_name, route_name, expected in [
        ("update", "update_watch_folder_binding", 404),
        ("update", "update_watch_folder_binding", 409),
        ("delete", "delete_watch_folder_binding", 404),
        ("delete", "delete_watch_folder_binding", 409),
    ]:
        error = KeyError("missing") if expected == 404 else api.IngressBindingConflictError("conflict")
        getattr(binding_service, method_name).side_effect = error
        endpoint = _route(route_name)
        args = ("b1", _request(b"{}"), "admin") if method_name == "update" else ("b1", "admin")
        with pytest.raises(HTTPException) as exc_info:
            if method_name == "update":
                _run(endpoint(*args))
            else:
                endpoint(*args)
        assert exc_info.value.status_code == expected

    monkeypatch.setattr(api, "UserService", lambda _conn: Mock(change_password=Mock(return_value="admin")))
    changed = _run(_route("change_admin_user_password")("admin", _request(b'{}'), user="admin"))
    assert changed["session_revoked"] is True

    class Exploding:
        def __init__(self, *args, **kwargs):
            raise ValueError("service failure")

    monkeypatch.setattr(api, "ReviewSchemaVersionService", Exploding)
    with pytest.raises(HTTPException):
        _run(_route("create_versioned_review_schema")(_request(b'{"schema_key":"x","name":"X"}'), user="admin"))
    monkeypatch.setattr(api, "PipelineTemplateService", Exploding)
    with pytest.raises(HTTPException):
        _run(_route("create_versioned_pipeline_template")(_request(b'{"template_key":"x","name":"X"}'), user="admin"))

    with pytest.raises(HTTPException, match="schema must be an object"):
        _run(_route("save_versioned_review_schema_draft")("t1", _request(b'{"schema":[]}'), user="admin"))
    with pytest.raises(HTTPException, match="definition must be an object"):
        _run(_route("save_versioned_pipeline_draft")("t1", _request(b'{"definition":[]}'), user="admin"))
    with pytest.raises(HTTPException):
        _run(_route("import_versioned_pipeline_draft")("t1", _request(b"[]", "application/yaml"), expected_revision=1, user="admin"))

    admin = Mock()
    admin.import_pipeline_document.return_value = {"schema_version": 1}
    admin.pipelines.import_draft.return_value = {"id": "draft"}
    monkeypatch.setattr(api, "VersionedAdminService", lambda *_args, **_kwargs: admin)
    imported = _run(_route("import_versioned_pipeline_draft")("t1", _request(b"kind: pipeline", "application/yaml"), expected_revision=1, user="admin"))
    assert imported["published"] is False

    batch_service = Mock()
    batch_service.get_batch.return_value = None
    monkeypatch.setattr(api, "BatchService", lambda _conn: batch_service)
    with pytest.raises(HTTPException, match="Batch not found"):
        _route("get_split_results")("b1", user="admin")
    batch_service.get_batch.return_value = {"id": "b1"}
    docs = Mock()
    docs.list_by_batch.return_value = [
        {"id": "root", "parent_document_id": None},
        {"id": "child", "parent_document_id": "root", "status": "failed", "metadata_json": "{}"},
    ]
    monkeypatch.setattr(api, "DocumentRepository", lambda _conn: docs)
    split = _route("get_split_results")("b1", user="admin")
    assert split["summary"]["failed"] == 1

    docs.get.return_value = None
    with pytest.raises(HTTPException, match="Document not found"):
        _route("get_document_pdf_file")("missing", user="admin")
    docs.get.return_value = {"id": "d1", "file_path": None, "pipeline_version_id": None}
    docs.list_files.return_value = []
    with pytest.raises(HTTPException, match="PDF file not found"):
        _route("get_document_pdf_file")("d1", user="admin")

    docs.get.return_value = {"id": "d1", "file_path": None, "pipeline_version_id": "v1"}
    pipeline_versions = Mock()
    pipeline_versions.get.return_value = {"definition_json": "{}"}
    monkeypatch.setattr(api, "PipelineVersionRepository", lambda _conn: pipeline_versions)
    with pytest.raises(HTTPException, match="PDF file not found"):
        _route("get_document_pdf_file")("d1", user="admin")


def test_schema_audit_payload_helper_is_exercised(monkeypatch):
    captured = {}

    def trace(frame, event, arg):
        if frame.f_code.co_name == "build_router" and event == "line":
            helper = frame.f_locals.get("_schema_audit_payload")
            if helper is not None:
                captured["helper"] = helper
        return trace

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        api.build_router()
    finally:
        sys.settrace(previous)

    service = Mock()
    service.normalize_schema.return_value = {"title": "Invoice", "fields": ["id"]}
    service.schema_hash.return_value = "hash"
    assert captured["helper"]("invoice", service) == {
        "schema_name": "invoice",
        "title": "Invoice",
        "hash": "hash",
        "field_count": 1,
    }


def test_process_background_missing_directory_and_cleanup_failure(monkeypatch, tmp_path):
    config = Config({"watch_folder.processing_dir": ""})
    temp = tmp_path / "temp.pdf"
    temp.write_bytes(b"data")
    monkeypatch.setattr(api, "get_dependencies", lambda: (config, None, None, None, None))
    monkeypatch.setattr(api.os, "remove", Mock(side_effect=OSError("locked")))
    api.process_file_in_background(Mock(), str(temp), "file", "file.pdf")
    assert temp.exists()
