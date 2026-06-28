import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules.file_processor import FileProcessor
from modules.services.config_validation_service import ConfigValidationService
from modules.services.reports_service import (
    ReportsService,
    _duration_display,
    _parse_iso_datetime,
)
from modules.services.runtime_settings_service import RuntimeSettingsService
from modules.services.user_service import UserService, UserServiceError
from modules.watch_folder_monitor import WatchFolderMonitor
from modules import utils


class Config:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def get_all(self):
        return self.values


def test_file_processor_configuration_and_io_failures(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Processing folder"):
        FileProcessor(
            Config({"watch_folder.processing_dir": ""}),
            Mock(),
            Mock(),
        )

    processor = FileProcessor(
        Config(
            {
                "watch_folder.processing_dir": str(tmp_path / "processing"),
                "web.upload_dir": "",
            }
        ),
        Mock(),
        Mock(),
    )
    with pytest.raises(ValueError, match="upload_dir"):
        processor.process_web_upload(b"%PDF-")

    processor.config_manager.values["web.upload_dir"] = str(tmp_path / "upload")
    (tmp_path / "upload").mkdir()
    monkeypatch.setattr("builtins.open", Mock(side_effect=OSError("write failed")))
    with pytest.raises(OSError, match="write failed"):
        processor.process_web_upload(io.BytesIO(b"%PDF-"))

    monkeypatch.undo()
    monkeypatch.setattr(
        "modules.file_processor.initialize_database",
        Mock(side_effect=RuntimeError("database failed")),
    )
    assert processor._create_sqlite_ingestion_state(
        filepath="file.pdf",
        unique_id="id",
        source="web",
        original_filename="file.pdf",
    ) == (None, None)


def test_config_validation_payload_shapes(tmp_path):
    service = ConfigValidationService(
        SimpleNamespace(_config_path=tmp_path / "config.yaml")
    )

    assert service._extra_findings(None) == []
    with pytest.raises(ValueError, match="must be a string"):
        service._extract_config_data({"yaml": 1})
    with pytest.raises(ValueError):
        service._extract_config_data({"yaml": "["})
    with pytest.raises(ValueError, match="must be a mapping"):
        service._extract_config_data({"yaml": "- item"})
    assert service._extract_config_data({"pipeline": [], "tasks": {}})["pipeline"] == []
    with pytest.raises(ValueError, match="must include"):
        service._extract_config_data({})

    finding = {
        "severity": "error",
        "path": "x",
        "code": "x",
        "message": "x",
    }
    assert service._dedupe_findings([finding, finding]) == [finding]


def test_reports_helpers_and_invalid_table():
    connection = Mock()
    service = ReportsService(connection)
    with pytest.raises(ValueError, match="Unsupported report table"):
        service._count("secrets")

    connection.execute.return_value.fetchall.return_value = [
        {"started_at": "bad", "ended_at": "2026-01-01T00:00:00"},
        {
            "started_at": "2026-01-01T01:00:00",
            "ended_at": "2026-01-01T00:00:00",
        },
    ]
    assert service._average_processing_seconds() is None
    assert _parse_iso_datetime(None) is None
    assert _parse_iso_datetime("bad") is None
    assert _duration_display(None) == "n/a"
    assert _duration_display(12) == "12s"
    assert _duration_display(7200) == "2.0h"


def test_runtime_settings_invalid_pipeline_and_redaction():
    service = object.__new__(RuntimeSettingsService)
    service.config_manager = SimpleNamespace()
    service.config = {"tasks": [], "pipeline": "bad"}
    assert service._get("tasks.missing", "default") == "default"
    assert service._pipeline_steps() == []
    assert service._first_task_by_class("ReviewGateTask") == {}

    service.config = {
        "tasks": {"missing": "bad", "task": {"class": "Task", "params": {"api_key": "x"}}},
        "pipeline": [1, "missing", "task"],
    }
    steps = service._pipeline_steps()
    assert steps[0]["configured"] is False
    assert steps[1]["params"]["api_key"] == "[REDACTED]"


def test_user_service_rejection_paths(monkeypatch):
    service = object.__new__(UserService)
    service.users = Mock()
    service.audit = Mock()
    service.users.get.side_effect = [None, None]
    with pytest.raises(UserServiceError, match="Admin role required"):
        service.change_password(
            actor="operator",
            target="admin",
            current_admin_password="x",
            new_password="ValidPassword1!",
            confirmation="ValidPassword1!",
        )

    assert UserService._matches("password", "invalid") is False


def test_user_service_rejects_missing_post_update_user(monkeypatch):
    service = object.__new__(UserService)
    service.users = Mock()
    service.audit = Mock()
    service.users.get.side_effect = [
        {"role": "admin", "password_hash": "admin-hash"},
        {"password_hash": "target-hash"},
        None,
    ]
    monkeypatch.setattr(
        UserService,
        "_matches",
        staticmethod(lambda password, password_hash: password_hash == "admin-hash"),
    )
    monkeypatch.setattr("modules.services.user_service.validate_password", lambda password: None)
    monkeypatch.setattr("modules.services.user_service.bcrypt.hashpw", lambda password, salt: b"new-hash")
    monkeypatch.setattr("modules.services.user_service.bcrypt.gensalt", lambda rounds: b"salt")

    with pytest.raises(UserServiceError, match="Updated user could not be loaded"):
        service.change_password(
            actor="admin",
            target="operator",
            current_admin_password="AdminPassword1!",
            new_password="ReplacementPass2!",
            confirmation="ReplacementPass2!",
        )

    service.users.update_password.assert_called_once_with("operator", "new-hash")
    service.audit.append.assert_not_called()


def test_watch_monitor_start_registers_cleanup(monkeypatch, tmp_path):
    monitor = WatchFolderMonitor(
        Config(
            {
                "watch_folder.dir": str(tmp_path),
                "watch_folder.processing_dir": str(tmp_path),
            }
        ),
        Mock(),
        None,
    )
    shutdown = Mock()
    monkeypatch.setattr(
        "modules.watch_folder_monitor.ShutdownManager",
        lambda: shutdown,
    )
    monitor._process_existing_files = Mock()
    monitor._monitor_new_files = Mock()

    monitor.start()

    shutdown.register_cleanup_task.assert_called_once_with(monitor.stop)
    monitor._process_existing_files.assert_called_once_with()
    monitor._monitor_new_files.assert_called_once_with()


def test_utility_edge_values(monkeypatch, tmp_path):
    assert utils.preprocess_filename_value(None) == "none"
    generated = utils.generate_uuid_filename("file.pdf")
    assert generated.endswith(".pdf")
    assert utils.resolve_field({}, "data.missing") == (None, False)
    assert utils.resolve_field({"data": []}, "data.1") == (None, False)

    attempts = Mock(side_effect=[OSError("busy"), OSError("busy")])
    monkeypatch.setattr("modules.utils.time.sleep", Mock())

    @utils.retry_io(max_attempts=2, delay=0)
    def operation():
        return attempts()

    with pytest.raises(OSError, match="busy"):
        operation()
