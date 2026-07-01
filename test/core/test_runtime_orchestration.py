import argparse
import io
import logging
import logging.handlers
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, mock_open

import pytest

import main
from modules import logging_config
from modules.file_processor import FileProcessor
from modules.shutdown_manager import ShutdownManager
from modules.watch_folder_monitor import WatchFolderMonitor


class DictConfig:
    def __init__(self, values, *, config_path=None):
        self.values = values
        self._config_path = config_path

    def get(self, key, default=None):
        return self.values.get(key, default)


@pytest.fixture(autouse=True)
def restore_root_logging():
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    yield
    root.handlers = handlers
    root.setLevel(level)


def test_parse_args_and_resolve_config_path_sources(monkeypatch, tmp_path):
    config_path = tmp_path / "cli.yaml"
    monkeypatch.setattr(
        main.sys,
        "argv",
        ["main.py", "--config-path", str(config_path), "--no-web"],
    )

    args = main.parse_args()

    assert args.no_web is True
    assert main.resolve_config_path(args) == config_path.resolve()

    env_path = tmp_path / "env.yaml"
    monkeypatch.setenv("CONFIG_PATH", str(env_path))
    assert main.resolve_config_path(argparse.Namespace(config_path=None)) == env_path.resolve()

    monkeypatch.delenv("CONFIG_PATH")
    assert main.resolve_config_path(argparse.Namespace(config_path=None)).name == "config.yaml"


def test_start_web_server_builds_child_process_environment(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config = DictConfig(
        {
            "web.host": "0.0.0.0",
            "web.port": "9001",
            "logging.log_file": tmp_path / "uvicorn.log",
        },
        config_path=config_path,
    )
    process = SimpleNamespace(pid=42)
    popen = Mock(return_value=process)
    opened = mock_open()
    monkeypatch.setattr(main.subprocess, "Popen", popen)
    monkeypatch.setattr("builtins.open", opened)
    monkeypatch.setenv("USE_RELOAD", "true")
    monkeypatch.setenv("APP_ENV", "development")

    result_process, result_log = main.start_web_server(config, logging.getLogger("test"))

    assert result_process is process
    assert result_log is opened()
    command = popen.call_args.args[0]
    assert command[-1] == "--reload"
    assert popen.call_args.kwargs["env"]["CONFIG_PATH"] == str(config_path)


def test_start_web_server_closes_log_when_spawn_fails(monkeypatch):
    log_handle = Mock()
    monkeypatch.setattr("builtins.open", Mock(return_value=log_handle))
    monkeypatch.setattr(main.subprocess, "Popen", Mock(side_effect=OSError("spawn failed")))

    with pytest.raises(OSError, match="spawn failed"):
        main.start_web_server(DictConfig({}), logging.getLogger("test"))

    log_handle.close.assert_called_once_with()


def _patch_main_components(monkeypatch, *, no_web, monitor_start=None, process=None):
    config = DictConfig(
        {
            "database.run_migrations_on_startup": True,
            "logging.log_file": "runtime.log",
        }
    )
    shutdown = Mock()
    workflow = Mock()
    file_processor = Mock()
    monitors = []

    class FakeMonitor:
        def __init__(self, config_manager, callback, retry_func):
            self.callback = callback
            self._retry_file_operation = Mock()
            self.stop = Mock()
            monitors.append(self)

        def start(self):
            if self.callback is not None:
                self.callback("processing/a.pdf", "doc-1", "watch", "a.pdf")
            if monitor_start is not None:
                return monitor_start()
            return None

    monkeypatch.setattr(main, "parse_args", lambda: SimpleNamespace(config_path=None, no_web=no_web))
    monkeypatch.setattr(main, "resolve_config_path", lambda args: Path("config.yaml"))
    monkeypatch.setattr(main, "ConfigManager", lambda config_path: config)
    monkeypatch.setattr(main, "initialize_database", Mock())
    monkeypatch.setattr(main, "setup_logging", Mock())
    monkeypatch.setattr(main, "validate_startup_task_registry", Mock())
    monkeypatch.setattr(main, "ShutdownManager", lambda: shutdown)
    monkeypatch.setattr(main, "WorkflowManager", lambda cfg: workflow)
    monkeypatch.setattr(main, "FileProcessor", lambda *args: file_processor)
    monkeypatch.setattr(main, "WatchFolderMonitor", FakeMonitor)
    if process is not None:
        monkeypatch.setattr(main, "start_web_server", lambda *args: (process, Mock()))
    return config, shutdown, file_processor, monitors


def test_main_no_web_processes_callback_and_exits(monkeypatch):
    _, shutdown, file_processor, monitors = _patch_main_components(
        monkeypatch,
        no_web=True,
    )

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 0
    shutdown.shutdown.assert_called_once_with()
    file_processor.process_file.assert_called_once_with(
        "processing/a.pdf",
        "doc-1",
        source="watch",
        original_filename="a.pdf",
    )
    assert len(monitors) == 2


@pytest.mark.parametrize("return_code, expected_level", [(0, "info"), (3, "error")])
def test_main_supervises_web_process_and_stops_cleanly(
    monkeypatch,
    return_code,
    expected_level,
):
    process = Mock()
    process.poll.return_value = return_code
    process.wait.return_value = return_code
    _, shutdown, _, monitors = _patch_main_components(
        monkeypatch,
        no_web=False,
        process=process,
    )
    log_handle = Mock()
    monkeypatch.setattr(main, "start_web_server", lambda *args: (process, log_handle))
    log_method = Mock()
    monkeypatch.setattr(main.logger, expected_level, log_method)

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 0
    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=10)
    monitors[-1].stop.assert_called_once_with()
    shutdown.shutdown.assert_called_once_with()
    log_method.assert_called()
    log_handle.flush.assert_called_once_with()
    log_handle.close.assert_called_once_with()


def test_main_handles_monitor_and_process_shutdown_failures(monkeypatch):
    process = Mock()
    process.poll.side_effect = KeyboardInterrupt
    process.wait.side_effect = TimeoutError
    process.kill.side_effect = OSError("kill failed")

    def fail_start():
        raise RuntimeError("monitor failed")

    _, shutdown, _, monitors = _patch_main_components(
        monkeypatch,
        no_web=False,
        monitor_start=fail_start,
        process=process,
    )
    log_handle = Mock()
    log_handle.flush.side_effect = OSError("closed")
    monkeypatch.setattr(main, "start_web_server", lambda *args: (process, log_handle))
    monitors_stop_error = RuntimeError("stop failed")

    original_init = main.WatchFolderMonitor.__init__

    def init_with_failing_stop(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if self.callback is not None:
            self.stop.side_effect = monitors_stop_error

    monkeypatch.setattr(main.WatchFolderMonitor, "__init__", init_with_failing_stop)

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 0
    process.kill.assert_called_once_with()
    shutdown.shutdown.assert_called_once_with()


def test_main_exits_when_web_server_cannot_start(monkeypatch):
    _patch_main_components(monkeypatch, no_web=False)
    monkeypatch.setattr(
        main,
        "start_web_server",
        Mock(side_effect=RuntimeError("web failed")),
    )

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1


def test_logging_helpers_cover_stream_and_setup_paths(monkeypatch, tmp_path):
    plain_stream = io.StringIO()
    file_handler = Mock()
    console_handler = Mock()
    with monkeypatch.context() as patch:
        patch.setattr(logging_config.sys, "__stdout__", plain_stream)
        assert logging_config._resolve_console_stream(False) is plain_stream
        assert logging_config._resolve_console_stream(True) is plain_stream

        patch.setattr(
            logging_config,
            "_NonClosingRotatingFileHandler",
            Mock(return_value=file_handler),
        )
        patch.setattr(
            logging_config,
            "PrefectConsoleHandler",
            Mock(return_value=console_handler),
        )
        root = logging_config.setup_logging()

    assert root.level == logging.INFO
    file_handler.setFormatter.assert_called_once()
    console_handler.setFormatter.assert_called_once()
    assert logging_config.get_logger("covered").name == "covered"


def test_logging_stream_wrapper_and_handler_tolerate_errors(monkeypatch):
    base = Mock()
    base.buffer = Mock()
    with monkeypatch.context() as patch:
        patch.setattr(logging_config.sys, "__stdout__", base)
        patch.setattr(
            logging_config,
            "_NonClosingUTF8Wrapper",
            Mock(side_effect=OSError("unsupported")),
        )
        assert logging_config._resolve_console_stream(True) is base

    handler = object.__new__(logging_config._NonClosingRotatingFileHandler)
    monkeypatch.setattr(
        logging.handlers.RotatingFileHandler,
        "emit",
        Mock(side_effect=ValueError("closed")),
    )
    handler.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "x", (), None))


def test_shutdown_manager_continues_after_cleanup_error():
    ShutdownManager._instance = None
    manager = ShutdownManager()
    calls = []

    def fail():
        calls.append("fail")
        raise RuntimeError("expected")

    def succeed(value):
        calls.append(value)

    manager.register_cleanup_task(fail)
    manager.register_cleanup_task(succeed, "success")
    manager.shutdown()

    assert calls == ["fail", "success"]


def test_file_processor_error_and_compatibility_paths(monkeypatch, tmp_path):
    config = DictConfig(
        {
            "watch_folder.processing_dir": str(tmp_path / "processing"),
            "web.upload_dir": str(tmp_path / "upload"),
            "watch_folder.validate_pdf_header": False,
        }
    )
    workflow = Mock()
    workflow.trigger_workflow_for_file.side_effect = [
        TypeError("unexpected keyword argument 'batch_id'"),
        None,
    ]
    processor = FileProcessor(config, Mock(), workflow)

    assert processor.process_file(
        "input.pdf",
        "id",
        "web",
        batch_id="batch",
        document_id="document",
    )
    assert workflow.trigger_workflow_for_file.call_count == 2
    assert "batch_id" not in workflow.trigger_workflow_for_file.call_args.kwargs

    workflow.trigger_workflow_for_file.side_effect = TypeError("internal failure")
    with pytest.raises(TypeError, match="internal failure"):
        processor.process_file(
            "input.pdf",
            "id",
            "web",
            create_sqlite_state=False,
        )


def test_watch_monitor_retry_cleanup_and_loop_exceptions(monkeypatch, tmp_path):
    config = DictConfig(
        {
            "watch_folder.dir": str(tmp_path),
            "watch_folder.processing_dir": str(tmp_path / "processing"),
        }
    )
    monitor = WatchFolderMonitor(config, Mock(), None)
    cleanup = Mock()
    operation = Mock(side_effect=OSError("busy"))
    monkeypatch.setattr("modules.watch_folder_monitor.time.sleep", Mock())

    assert monitor._retry_file_operation(
        operation,
        attempts=2,
        delay=0.01,
        cleanup_func=cleanup,
    ) is False
    cleanup.assert_called_once_with()

    monkeypatch.setattr(
        "modules.watch_folder_monitor.os.listdir",
        Mock(side_effect=[OSError("scan"), KeyboardInterrupt]),
    )
    monitor._monitor_new_files()
