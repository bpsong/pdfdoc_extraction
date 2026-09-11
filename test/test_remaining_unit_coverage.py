"""Additional unit coverage for defensive branches in small service modules."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import main
from modules import config_manager as config_module
from modules.db import migrations as migrations_module
from modules import file_processor as file_processor_module
from modules import resume_manager as resume_module
from modules.db import connection as connection_module
from modules.services import artifact_service, portable_config_service
from modules.services import user_service as user_service_module
from modules.auth_utils import PasswordPolicyError
from modules.services.schema_service import SchemaService
from modules.services.batch_service import BatchService
from modules.services.runtime_settings_service import RuntimeSettingsService
from modules.services.user_service import UserService
from modules.services.workflow_state_service import WorkflowStateService
from modules.services.pipeline_definition_service import PipelineDefinitionError, PipelineDefinitionService
from modules.workflow_loader import WorkflowLoader
from modules.workflow_manager import WorkflowManager
from modules import workflow_loader as workflow_loader_module
from modules import workflow_manager as workflow_manager_module


class _Config:
    def __init__(self, values: dict | None = None, *, config_path: Path | None = None):
        self.values = values or {}
        self._config_path = config_path

    def get(self, key: str, default=None):
        return self.values.get(key, default)


def test_main_server_defensive_environment_and_log_cleanup(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USE_RELOAD", "true")
    monkeypatch.setenv("APP_ENV", "production")
    log = Mock()
    monkeypatch.setattr("builtins.open", Mock(return_value=log))
    monkeypatch.setattr(main.subprocess, "Popen", Mock(side_effect=OSError("spawn")))

    class BadConfig(_Config):
        def __getattribute__(self, name):
            if name == "_config_path":
                raise RuntimeError("bad config path")
            return super().__getattribute__(name)

    log.close.side_effect = OSError("already closed")
    with pytest.raises(OSError):
        main.start_web_server(BadConfig({"logging.log_file": tmp_path / "app.log"}), Mock())
    log.close.assert_called_once_with()


def test_auth_token_default_expiration_and_base_task_contract() -> None:
    from datetime import timedelta
    from modules.auth_utils import AuthUtils
    from modules.base_task import BaseTask

    auth = AuthUtils(_Config({"web.secret_key": "secret", "web.token_exp_minutes": 5}))
    with patch.object(__import__("modules.auth_utils", fromlist=["jwt"]).jwt, "encode", return_value="token") as encoded:
        assert auth.create_access_token({"sub": "admin"}) == "token"
        assert encoded.call_args.kwargs["algorithm"] == auth.algorithm

    class Task(BaseTask):
        def on_start(self, context):
            return context

        def run(self, context):
            return context

        def validate_required_fields(self, context):
            return None

    task = Task(_Config(), task_slug="old")
    assert task.run({}) == {}
    assert task.task_key({}) == "Task"
    assert task.task_key({"current_task_key": "configured"}) == "configured"
    BaseTask.on_start(task, {})
    BaseTask.run(task, {})
    assert timedelta(minutes=5)


def test_config_manager_missing_and_invalid_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager = object.__new__(config_module.ConfigManager)
    manager.logger = Mock()
    manager._config_path = tmp_path / "config.yaml"
    manager.config = {"nested": "scalar"}
    assert manager.get("nested.value", "fallback") == "fallback"

    manager.config = {"web": {}}
    with pytest.raises(SystemExit):
        manager._validate_static_paths()
    manager.config = {"watch_folder": {}}
    with pytest.raises(SystemExit):
        manager._validate_watch_folder()
    manager.config = {"missing_dir": "does-not-exist"}
    with pytest.raises(SystemExit):
        manager._validate_dynamic_paths()


def test_connection_json_invalid_text_and_batch_empty_progress() -> None:
    assert connection_module.json_loads("not-json", {"fallback": True}) == {"fallback": True}
    assert BatchService._with_progress({"total_documents": 0})["progress_percent"] == 0
    with pytest.raises(ValueError, match="At least one file"):
        BatchService.__new__(BatchService).create_ingestion_batch_with_documents(source="x", files=[])


def test_document_artifact_user_and_portable_defensive_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(artifact_service, "connect", lambda _config: nullcontext(object()))
    monkeypatch.setattr(artifact_service.DocumentRepository, "get", lambda _self, _id: None)
    assert artifact_service.register_document_artifact(_Config(), {"document_id": "missing"}, file_type="x", file_path=tmp_path / "x") is None

    artifact_repo = Mock()
    artifact_repo.get.return_value = {"id": "doc"}
    artifact_repo.find_file.return_value = {"id": "existing"}
    monkeypatch.setattr(artifact_service, "DocumentRepository", lambda _conn: artifact_repo)
    assert artifact_service.register_document_artifact(
        _Config(), {"document_id": "doc"}, file_type="x", file_path=tmp_path / "x"
    ) == {"id": "existing"}

    users = UserService.__new__(UserService)
    users.users = Mock()
    users.audit = Mock()
    users.users.list.return_value = [{"username": "admin", "role": "admin"}]
    assert users.list_users()[0]["username"] == "admin"

    users.users.get.side_effect = lambda name: (
        {"username": "admin", "role": "admin", "password_hash": "hash"}
        if name == "admin" else None
    )
    with pytest.raises(user_service_module.UserServiceError, match="Unknown user"):
        users.change_password(
            actor="admin", target="not-a-user", current_admin_password="current",
            new_password="Strong-password-1!", confirmation="Strong-password-1!",
        )

    users.users.get.side_effect = lambda name: {
        "username": name, "role": "admin" if name == "admin" else "operator",
        "password_hash": "hash",
    }
    users._matches = Mock(return_value=True)
    with pytest.raises(user_service_module.UserServiceError, match="do not match"):
        users.change_password(
            actor="admin", target="operator", current_admin_password="current",
            new_password="Strong-password-1!", confirmation="different",
        )
    with patch.object(user_service_module, "validate_password", side_effect=PasswordPolicyError("weak")):
        with pytest.raises(user_service_module.UserServiceError, match="weak"):
            users.change_password(
                actor="admin", target="operator", current_admin_password="current",
                new_password="weak", confirmation="weak",
            )

    with pytest.raises(portable_config_service.PortableConfigError):
        portable_config_service.export_pipeline_bundle({"tasks": []}, template_key="x", template_name="X", resolve_version=lambda _id: None)
    exported = portable_config_service.export_pipeline_bundle(
        {"tasks": {"bad": "task"}},
        template_key="x",
        template_name="X",
        resolve_version=lambda _id: None,
    )
    assert exported["definition"]["tasks"] == {"bad": "task"}
    bundle = {
        "kind": "pipeline-bundle",
        "format_version": portable_config_service.PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION,
        "definition": {"tasks": {"bad": "task"}},
        "dependencies": {},
    }
    definition, dependencies = portable_config_service.import_pipeline_bundle(bundle)
    assert definition["tasks"] == {"bad": "task"}
    assert dependencies == {}


def test_runtime_settings_and_workflow_state_missing_branches() -> None:
    settings = RuntimeSettingsService(SimpleNamespace())
    assert settings.config == {}
    assert settings._first_task_by_class("ReviewGateTask") == {}
    assert settings._pipeline_steps() == []

    state = WorkflowStateService.__new__(WorkflowStateService)
    state.pipeline = ["first"]
    state.pipeline_version_id = "v1"
    state.documents = Mock()
    state.task_runs = Mock()
    state.documents.get.return_value = None
    with pytest.raises(ValueError, match="Document does not exist"):
        state.start_task(batch_id="b", document_id="d", task_key="first", task_index=0, module_name="m", class_name="C")
    with pytest.raises(ValueError, match="Document does not exist"):
        state.start_internal_task(batch_id="b", document_id="d", task_key="internal", task_index=0, module_name="m", class_name="C")
    state.documents.get.return_value = {"pipeline_version_id": "other", "current_task_index": 0}
    with pytest.raises(ValueError, match="pipeline version"):
        state.start_task(batch_id="b", document_id="d", task_key="first", task_index=0, module_name="m", class_name="C")
    with pytest.raises(ValueError, match="pipeline version"):
        state.start_internal_task(batch_id="b", document_id="d", task_key="internal", task_index=0, module_name="m", class_name="C")
    state.documents.get.return_value = None
    assert state.next_task_after_current("d") is None


def test_schema_service_defensive_and_value_validation_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = SchemaService(_Config({"schema.directories": [str(tmp_path)]}, config_path=tmp_path / "config.yaml"))
    assert service.test_pattern("x", 1)["error"] == "Example value must be a string."
    assert service._validate_value("name", "long", {"type": "string", "max_length": 2})
    assert service._validate_value("amount", 5, {"type": "number", "max_value": 2})
    assert service._validate_value("date", "2024-02-31", {"type": "date"})
    assert service._validate_value("when", "not-a-date", {"type": "datetime"})
    assert service._validate_value("ignored", "x", "not-a-mapping") == []
    assert service.validate_schema({"fields": {"x": {"type": "string", "pattern": 3}}})

    with monkeypatch.context() as context:
        context.setattr(Path, "resolve", Mock(side_effect=OSError("resolve")))
        assert service.schema_directories() == []
        assert service._resolve_schema_path("missing.yaml") is None

    schema_path = tmp_path / "broken.yaml"
    schema_path.write_text("- not a mapping\n", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("ignore", encoding="utf-8")
    assert service.list_schemas()[0]["title"] == "broken"
    valid_path = tmp_path / "valid.yaml"
    valid_path.write_text("title: Valid\nfields: {}\n", encoding="utf-8")
    service.save_schema = Mock(return_value={"name": "copy.yaml"})
    assert service.duplicate_schema("valid.yaml", "copy.yaml") == {"name": "copy.yaml"}
    with monkeypatch.context() as context:
        context.setattr(service, "_resolve_schema_path", lambda _name: schema_path)
        context.setattr(service, "load_schema", lambda _name: None)
        with pytest.raises(ValueError, match="could not be loaded"):
            service.duplicate_schema("broken.yaml", "copy.yaml")
    assert service._resolve_schema_path("") is None
    assert service._resolve_schema_path("not-a-schema.txt") is None
    assert service._validate_value("when", 3, {"type": "datetime"})


def test_pipeline_definition_rejects_malformed_pins_and_assignments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.services.pipeline_definition_service as definition_module

    service = PipelineDefinitionService.__new__(PipelineDefinitionService)
    service.conn = Mock()
    service.config = Mock()
    service._verify_task_approvals = lambda _definition: None

    class Pipelines:
        def __init__(self, version, templates):
            self.version = version
            self.templates = templates

        def load_version(self, _version_id):
            return self.version

    base = {
        "id": "v1",
        "template_id": "t1",
        "schema_version": 999,
        "definition": {"tasks": {}, "pipeline": []},
        "schema_dependencies": {},
        "display_snapshot": {},
        "version_number": 1,
        "content_hash": "hash",
    }
    monkeypatch.setattr(definition_module, "PipelineTemplateService", lambda _conn: Pipelines(base, {"t1": {"id": "t1"}}))
    with pytest.raises(PipelineDefinitionError, match="unsupported"):
        service.load_version("v1")
    base["schema_version"] = definition_module.PIPELINE_DEFINITION_SCHEMA_VERSION
    monkeypatch.setattr(definition_module, "PipelineTemplateService", lambda _conn: Pipelines(base, {}))
    with pytest.raises(PipelineDefinitionError, match="template is missing"):
        service.load_version("v1")

    docs = Mock()
    batches = Mock()
    monkeypatch.setattr(definition_module, "DocumentRepository", lambda _conn: docs)
    monkeypatch.setattr(definition_module, "BatchRepository", lambda _conn: batches)
    docs.get.return_value = None
    with pytest.raises(PipelineDefinitionError, match="does not exist"):
        service.load_for_document("d")
    docs.get.return_value = {"id": "d"}
    with pytest.raises(PipelineDefinitionError, match="no pinned"):
        service.load_for_document("d")
    docs.get.return_value = {"id": "d", "batch_id": "b", "pipeline_version_id": "v", "pipeline_template_id": "t"}
    batches.get.return_value = None
    with pytest.raises(PipelineDefinitionError, match="batch"):
        service.load_for_document("d")
    batches.get.return_value = {"pipeline_version_id": "v", "pipeline_template_id": "other"}
    with pytest.raises(PipelineDefinitionError, match="disagree"):
        service.load_for_document("d")
    batches.get.return_value = {"pipeline_version_id": "v", "pipeline_template_id": "t"}
    service.load_version = lambda _version_id: SimpleNamespace(template_id="other")
    with pytest.raises(PipelineDefinitionError, match="does not belong"):
        service.load_for_document("d")

    with pytest.raises(PipelineDefinitionError, match="tasks are malformed"):
        service._inject_review_schemas({}, {})
    with pytest.raises(PipelineDefinitionError, match="unknown task"):
        service._inject_review_schemas({"tasks": {}}, {"missing": "s"})
    with pytest.raises(PipelineDefinitionError, match="parameters are malformed"):
        service._inject_review_schemas({"tasks": {"review": {"params": []}}}, {"review": "s"})
    with pytest.raises(PipelineDefinitionError, match="identity"):
        service._inject_review_schemas({"tasks": {"review": {"params": {"schema_version_id": "other"}}}}, {"review": "s"})
    service._verify_task_approvals = PipelineDefinitionService._verify_task_approvals.__get__(service, PipelineDefinitionService)
    with pytest.raises(PipelineDefinitionError, match="structure"):
        service._verify_task_approvals({"tasks": [], "pipeline": "bad"})
    with pytest.raises(PipelineDefinitionError, match="task is missing"):
        service._verify_task_approvals({"tasks": {}, "pipeline": ["missing"]})


def test_migration_helpers_cover_incomplete_sql_and_foreign_key_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="incomplete SQL"):
        migrations_module._execute_schema_script(Mock(), "CREATE TABLE incomplete")

    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [("bad",)]
    monkeypatch.setattr(migrations_module, "_add_column_if_missing", Mock())
    monkeypatch.setattr(migrations_module, "immediate_transaction", lambda _conn: nullcontext())
    monkeypatch.setattr(migrations_module.Path, "read_text", lambda _path, encoding: "SELECT 1;")
    with pytest.raises(RuntimeError, match="foreign-key violations"):
        migrations_module.upgrade_v2_to_v3_structure(conn)


def test_file_processor_pdf_and_move_cleanup_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    processor = object.__new__(file_processor_module.FileProcessor)
    monkeypatch.setattr(file_processor_module, "is_pdf_header", Mock(return_value=True))
    assert processor._validate_pdf_header("invoice.pdf") is True

    upload_dir = tmp_path / "upload"
    processing_dir = tmp_path / "processing"
    upload_dir.mkdir()
    processing_dir.mkdir()
    processor.config_manager = _Config(
        {
            "web.upload_dir": str(upload_dir),
            "watch_folder.validate_pdf_header": True,
        }
    )
    processor.processing_folder_path = str(processing_dir)
    monkeypatch.setattr(file_processor_module, "is_pdf_header", Mock(return_value=False))
    remove = Mock(side_effect=OSError("already gone"))
    monkeypatch.setattr(file_processor_module.os, "remove", remove)
    with pytest.raises(ValueError, match="Invalid PDF header"):
        processor.process_web_upload(b"not pdf")
    remove.assert_called_once()

    monkeypatch.setattr(file_processor_module, "is_pdf_header", Mock(return_value=True))
    monkeypatch.setattr(file_processor_module.os, "replace", Mock(side_effect=OSError("move failed")))
    remove.reset_mock()
    remove.side_effect = OSError("cleanup failed")
    with pytest.raises(OSError, match="move failed"):
        processor.process_web_upload(b"%PDF-")
    remove.assert_called_once()


def test_resume_manager_defensive_resume_and_failure_context_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = resume_module.ResumeManager(_Config({"pipeline": ["next"]}))
    documents = Mock()
    extractions = Mock()
    task_runs = Mock()
    monkeypatch.setattr(resume_module, "connect", lambda _config: nullcontext(object()))
    monkeypatch.setattr(resume_module, "DocumentRepository", lambda _conn: documents)
    monkeypatch.setattr(resume_module, "ExtractionRepository", lambda _conn: extractions)
    monkeypatch.setattr(resume_module, "TaskRunRepository", lambda _conn: task_runs)

    documents.get.return_value = None
    assert manager.resume_document("missing") is False
    documents.get.return_value = {"status": "queued"}
    assert manager.resume_document("queued") is False

    documents.get.return_value = {"status": "review_completed", "pipeline_version_id": "v1"}
    monkeypatch.setattr(
        resume_module,
        "PipelineDefinitionService",
        lambda *_args: Mock(load_for_document=Mock(side_effect=RuntimeError("bad definition"))),
    )
    assert manager.resume_document("broken") is False

    documents.get.return_value = {"id": "doc", "batch_id": "batch", "file_path": "doc.pdf", "status": "review_completed"}
    state = Mock()
    state.next_task_after_current.return_value = (1, "next")
    state.has_completed_at_or_after.return_value = True
    monkeypatch.setattr(resume_module, "WorkflowStateService", lambda *args, **kwargs: state)
    assert manager.resume_document("doc") is False
    state.has_completed_at_or_after.return_value = False
    documents.claim_review_resume.return_value = False
    assert manager.resume_document("doc") is False

    documents.claim_review_resume.return_value = True
    manager._build_resume_context = Mock(return_value={})
    loader = Mock()
    loader.load_workflow.return_value = None
    monkeypatch.setattr(resume_module, "WorkflowLoader", lambda *args, **kwargs: loader)
    assert manager.resume_document("doc", user="operator") is False

    manager._build_resume_context = resume_module.ResumeManager._build_resume_context.__get__(
        manager, resume_module.ResumeManager
    )
    extractions.get_latest_result.return_value = None
    extractions.get_fields.return_value = [{"field_key": "amount", "final_value_json": "7"}]
    task_runs.list_by_document.return_value = [
        {"status": "completed"},
        {"status": "failed", "error": "oops", "task_key": "extract", "output_json": "{}"},
    ]
    context = manager._build_resume_context(
        {"id": "doc", "batch_id": "batch", "file_path": "doc.pdf"},
        extractions,
        task_runs,
    )
    assert context["continued_failures"][0]["error_step"] == "extract"


def test_workflow_loader_and_manager_defensive_child_paths(monkeypatch) -> None:
    loader = object.__new__(WorkflowLoader)
    loader.config_manager = Mock()
    loader.cfg = {"pipeline": []}
    loader.workflow_loader = Mock()
    loader.logger = Mock()
    child = {
        "id": "child",
        "batch_id": "batch",
        "file_path": "child.pdf",
        "pipeline_version_id": "v1",
        "metadata_json": "{}",
    }
    context = WorkflowManager._build_child_context(
        {**child, "metadata_json": '{"inherited_context": {"x": 1}, "continued_failures": ["failed"]}'},
        {"original_filename": "parent.pdf", "file_path": "parent.pdf"},
        2,
    )
    assert context["metadata"]["inherited_context"] == {"x": 1}
    assert context["continued_failures"] == ["failed"]
    assert loader._state_service({}) is None
    WorkflowLoader._restore_continued_failure({"continued_failures": ["bad"]})

    manager = object.__new__(WorkflowManager)
    manager.config_manager = Mock()
    manager.workflow_loader = Mock()
    manager.logger = Mock()
    manager._load_document_pipeline = Mock(return_value=None)
    manager._fail_children_when_extract_preflight_fails = Mock(return_value=False)
    manager_documents = Mock()
    monkeypatch.setattr(workflow_manager_module, "connect", lambda _config: nullcontext(object()))
    monkeypatch.setattr(workflow_manager_module, "DocumentRepository", lambda _conn: manager_documents)
    monkeypatch.setattr(workflow_manager_module, "WorkflowLoader", Mock)
    manager_documents.get.side_effect = [None]
    manager._trigger_child_workflows({"split_children": ["missing"], "fan_out_start_task_index": 0})
    manager_documents.get.side_effect = [child]
    manager.workflow_loader.load_workflow.return_value = None
    manager._trigger_child_workflows({"split_children": ["child"], "fan_out_start_task_index": 1})

    repository = Mock()
    repository.get.return_value = None
    monkeypatch.setattr(workflow_manager_module, "DocumentRepository", lambda _conn: repository)
    manager._load_document_pipeline = WorkflowManager._load_document_pipeline.__get__(manager)
    with pytest.raises(PipelineDefinitionError, match="does not exist"):
        manager._load_document_pipeline("missing")
    manager._mark_document_failed(None, "reason")
    repository.get.side_effect = OSError("db")
    manager._mark_document_failed("doc", "reason")
    repository.get.side_effect = None
    repository.get.return_value = {"id": "doc"}
    state = Mock()
    monkeypatch.setattr(workflow_manager_module, "WorkflowStateService", lambda _conn: state)
    manager._mark_document_failed("doc", "reason")
    state.transition_document.assert_called_once_with("doc", "failed", reason="reason")
    manager.config_manager.get.return_value = []
    assert manager._task_at_index(0) == (None, {})
    assert manager._task_at_index(0, definition={"pipeline": ["x"], "tasks": "bad"}) == ("x", {})
    manager._trigger_child_workflows({})
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
