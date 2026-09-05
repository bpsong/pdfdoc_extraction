import argparse
import io
import logging
import logging.handlers
import runpy
import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, mock_open

import pytest

import main
from modules import logging_config
from modules.file_processor import FileProcessor
from modules.shutdown_manager import ShutdownManager
from modules.watch_folder_monitor import WatchFolderMonitor
from tools import processing_worker as processing_worker_cli


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
    assert result_log is opened.return_value
    assert opened.call_args.args[0] == tmp_path / "uvicorn.web.log"
    command = popen.call_args.args[0]
    assert command[-1] == "--reload"
    assert popen.call_args.kwargs["env"]["CONFIG_PATH"] == str(config_path)
    assert popen.call_args.kwargs["env"]["DOCFLOW_PROCESS_ROLE"] == "web"
    assert popen.call_args.kwargs["env"]["DOCFLOW_STDIO_CAPTURED"] == "1"
    assert popen.call_args.kwargs["env"]["DOCFLOW_STARTUP_MODE"] == "verify"
    assert popen.call_args.kwargs["stdout"] is opened.return_value
    assert popen.call_args.kwargs["stderr"] is main.subprocess.STDOUT
    assert popen.call_args.kwargs["creationflags"] == main.subprocess.CREATE_NEW_PROCESS_GROUP


def test_start_web_server_closes_log_when_spawn_fails(monkeypatch):
    log_handle = Mock()
    monkeypatch.setattr("builtins.open", Mock(return_value=log_handle))
    monkeypatch.setattr(main.subprocess, "Popen", Mock(side_effect=OSError("spawn failed")))

    with pytest.raises(OSError, match="spawn failed"):
        main.start_web_server(DictConfig({}), logging.getLogger("test"))

    log_handle.close.assert_called_once_with()


def test_start_processing_worker_uses_verify_only_startup(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config = DictConfig({}, config_path=config_path)
    process = Mock()
    popen = Mock(return_value=process)
    monkeypatch.setattr(main.subprocess, "Popen", popen)

    assert main.start_processing_worker(config, logging.getLogger("test")) is process

    assert popen.call_args.kwargs["env"]["CONFIG_PATH"] == str(config_path)
    assert popen.call_args.kwargs["env"]["DOCFLOW_PROCESS_ROLE"] == "worker"
    assert popen.call_args.kwargs["env"]["DOCFLOW_STARTUP_MODE"] == "verify"
    assert popen.call_args.kwargs["creationflags"] == main.subprocess.CREATE_NEW_PROCESS_GROUP


def test_child_processes_receive_run_identity(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config = DictConfig(
        {"logging.log_file": tmp_path / "runtime.log"},
        config_path=config_path,
    )
    popen = Mock(return_value=SimpleNamespace(pid=42))
    monkeypatch.setattr(main.subprocess, "Popen", popen)
    monkeypatch.setattr("builtins.open", mock_open())
    expected = ("supervisor", "worker", "watch_folder", "web")

    main.start_web_server(
        config, logging.getLogger("test"), run_id="run-1", expected_components=expected
    )
    web_env = popen.call_args.kwargs["env"]
    main.start_processing_worker(
        config, logging.getLogger("test"), run_id="run-1", expected_components=expected
    )
    worker_env = popen.call_args.kwargs["env"]

    assert web_env["DOCFLOW_RUN_ID"] == worker_env["DOCFLOW_RUN_ID"] == "run-1"
    assert web_env["DOCFLOW_EXPECTED_COMPONENTS"] == ",".join(expected)
    assert worker_env["DOCFLOW_EXPECTED_COMPONENTS"] == ",".join(expected)


def test_readiness_wait_rejects_child_exit(monkeypatch):
    process = Mock()
    process.poll.return_value = 7
    watch_thread = Mock()
    watch_thread.is_alive.return_value = True
    service = Mock()
    monkeypatch.setattr(main, "RuntimeHealthService", lambda *_args: service)

    with pytest.raises(RuntimeError, match="worker exited during startup with code 7"):
        main.wait_for_runtime_readiness(
            DictConfig({"runtime_health.startup_timeout_seconds": 1}),
            "run-1",
            ("worker",),
            processes={"worker": process},
            watch_thread=watch_thread,
        )
    service.record.assert_called_once_with(
        "worker",
        "failed",
        details={"exit_code": 7, "phase": "startup"},
    )


def test_readiness_wait_accepts_fresh_component_snapshot(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    watch_thread = Mock()
    watch_thread.is_alive.return_value = True
    service = Mock()
    service.snapshot.return_value = {"ready": True}
    monkeypatch.setattr(main, "RuntimeHealthService", lambda *_args: service)

    snapshot = main.wait_for_runtime_readiness(
        DictConfig({}),
        "run-1",
        ("worker",),
        processes={"worker": process},
        watch_thread=watch_thread,
    )

    assert snapshot == {"ready": True}


def test_windows_shutdown_targets_entire_process_tree(monkeypatch):
    process = Mock(pid=41)
    process.poll.return_value = None
    run = Mock()
    kill = Mock()
    monkeypatch.setattr(main.os, "name", "nt")
    monkeypatch.setattr(main.subprocess, "run", run)
    monkeypatch.setattr(main.os, "kill", kill)

    main.terminate_process_tree(
        process, name="worker", logger=logging.getLogger("test"), timeout=2
    )

    kill.assert_called_once_with(41, signal.CTRL_BREAK_EVENT)
    run.assert_not_called()
    process.wait.assert_called_once_with(timeout=2)


def test_windows_shutdown_force_kills_process_tree_after_timeout(monkeypatch):
    process = Mock(pid=43)
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("worker", 2), 0]
    run = Mock()
    monkeypatch.setattr(main.os, "name", "nt")
    monkeypatch.setattr(main.os, "kill", Mock())
    monkeypatch.setattr(main.subprocess, "run", run)

    main.terminate_process_tree(
        process, name="worker", logger=logging.getLogger("test"), timeout=2
    )

    assert run.call_args.args[0] == ["taskkill", "/PID", "43", "/T", "/F"]


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
        def __init__(self, config_manager, processor, **_kwargs):
            self.file_processor = processor
            self.stop = Mock()
            monitors.append(self)

        def start(self):
            if self.file_processor is not None:
                self.file_processor.process_file(
                    filepath="processing/a.pdf",
                    unique_id="doc-1",
                    source="watch_folder",
                    original_filename="a.pdf",
                    batch_id="batch-1",
                    document_id="doc-1",
                    create_sqlite_state=False,
                )
            if monitor_start is not None:
                return monitor_start()
            return None

    monkeypatch.setattr(main, "parse_args", lambda: SimpleNamespace(config_path=None, no_web=no_web))
    monkeypatch.setattr(main, "resolve_config_path", lambda args: Path("config.yaml"))
    monkeypatch.setattr(main, "ConfigManager", lambda config_path: config)
    monkeypatch.setattr(main, "setup_bootstrap_logging", Mock())
    monkeypatch.setattr(main, "setup_logging", Mock())
    monkeypatch.setattr(main, "run_startup_checks", Mock())
    reporter = Mock()
    monkeypatch.setattr(main, "RuntimeHealthReporter", lambda *args, **kwargs: reporter)
    monkeypatch.setattr(main, "wait_for_runtime_readiness", Mock(return_value={"ready": True}))
    monkeypatch.setattr(main, "terminate_process_tree", Mock())
    monkeypatch.setattr(main, "ShutdownManager", lambda: shutdown)
    monkeypatch.setattr(main, "WorkflowManager", lambda cfg: workflow)
    monkeypatch.setattr(main, "FileProcessor", lambda *args: file_processor)
    monkeypatch.setattr(main, "WatchFolderCoordinator", FakeMonitor)
    worker = Mock()
    worker.poll.return_value = None
    monkeypatch.setattr(
        main, "start_processing_worker", lambda *args, **kwargs: worker
    )
    if process is not None:
        monkeypatch.setattr(
            main, "start_web_server", lambda *args, **kwargs: (process, Mock())
        )
    return config, shutdown, file_processor, monitors


def test_main_no_web_processes_callback_and_exits(monkeypatch):
    _, shutdown, file_processor, monitors = _patch_main_components(
        monkeypatch,
        no_web=True,
    )

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
    shutdown.shutdown.assert_called_once_with()
    file_processor.process_file.assert_called_once_with(
        filepath="processing/a.pdf",
        unique_id="doc-1",
        source="watch_folder",
        original_filename="a.pdf",
        batch_id="batch-1",
        document_id="doc-1",
        create_sqlite_state=False,
    )
    assert len(monitors) == 1


@pytest.mark.parametrize("return_code", [0, 3])
def test_main_supervises_web_process_and_stops_cleanly(
    monkeypatch,
    return_code,
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
    monkeypatch.setattr(
        main, "start_web_server", lambda *args, **kwargs: (process, log_handle)
    )
    log_method = Mock()
    monkeypatch.setattr(main.logger, "error", log_method)

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
    monitors[-1].stop.assert_called_once_with()
    shutdown.shutdown.assert_called_once_with()
    log_method.assert_called()
    log_handle.flush.assert_called_once_with()
    log_handle.close.assert_called_once_with()


def test_main_waits_once_when_web_process_is_still_running(monkeypatch):
    process = Mock()
    process.poll.side_effect = [None, 0]
    process.wait.return_value = 0
    _, _, _, monitors = _patch_main_components(
        monkeypatch,
        no_web=False,
        process=process,
    )
    monkeypatch.setattr(
        main, "start_web_server", lambda *args, **kwargs: (process, Mock())
    )
    sleep = Mock()
    monkeypatch.setattr(main.time, "sleep", sleep)

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
    monitors[-1].stop.assert_called_once_with()


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
    monkeypatch.setattr(
        main, "start_web_server", lambda *args, **kwargs: (process, log_handle)
    )
    monitors_stop_error = RuntimeError("stop failed")

    original_init = main.WatchFolderCoordinator.__init__

    def init_with_failing_stop(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if self.file_processor is not None:
            self.stop.side_effect = monitors_stop_error

    monkeypatch.setattr(main.WatchFolderCoordinator, "__init__", init_with_failing_stop)

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
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


def test_main_module_entrypoint_executes_main_guard(monkeypatch):
    config = DictConfig({"database.run_migrations_on_startup": False})
    shutdown = Mock()

    class Monitor:
        def __init__(self, *args):
            pass

        def start(self):
            return None

    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse.Namespace(config_path=None, no_web=True),
    )
    monkeypatch.setattr("modules.config_manager.ConfigManager", lambda **kwargs: config)
    monkeypatch.setattr("modules.logging_config.setup_bootstrap_logging", Mock())
    monkeypatch.setattr("modules.logging_config.setup_logging", Mock())
    monkeypatch.setattr("modules.services.startup_service.run_startup_checks", Mock())
    reporter = Mock()
    monkeypatch.setattr(
        "modules.services.runtime_health_service.RuntimeHealthReporter",
        lambda *args, **kwargs: reporter,
    )
    monkeypatch.setattr(
        "__main__.wait_for_runtime_readiness",
        Mock(return_value={"ready": True}),
        raising=False,
    )
    monkeypatch.setattr("modules.shutdown_manager.ShutdownManager", lambda: shutdown)
    monkeypatch.setattr("modules.workflow_manager.WorkflowManager", lambda _config: Mock())
    monkeypatch.setattr("modules.file_processor.FileProcessor", lambda *args: Mock())
    monkeypatch.setattr("modules.services.watch_folder_coordinator.WatchFolderCoordinator", Monitor)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(Path(main.__file__)), run_name="__main__")

    assert exc_info.value.code == 1
    shutdown.shutdown.assert_called_once_with()


def test_worker_configures_logging_before_migration(monkeypatch, tmp_path):
    events = []
    config = DictConfig(
        {"database.run_migrations_on_startup": True},
        config_path=tmp_path / "config.yaml",
    )
    worker = Mock()
    monkeypatch.setattr(
        processing_worker_cli.sys,
        "argv",
        ["processing_worker", "--config-path", str(tmp_path / "config.yaml")],
    )
    monkeypatch.setattr(
        processing_worker_cli,
        "setup_bootstrap_logging",
        lambda **kwargs: events.append("bootstrap-logging"),
    )
    monkeypatch.setattr(
        processing_worker_cli,
        "ConfigManager",
        lambda **kwargs: events.append("config") or config,
    )
    monkeypatch.setattr(
        processing_worker_cli,
        "setup_logging",
        lambda *args, **kwargs: events.append("configured-logging"),
    )
    startup_modes = []
    monkeypatch.setattr(
        processing_worker_cli,
        "run_startup_checks",
        lambda cfg, **kwargs: (
            startup_modes.append(kwargs["migration_mode"]),
            events.append("startup-checks"),
        ),
    )
    monkeypatch.setattr(
        processing_worker_cli,
        "build_worker",
        lambda cfg, **_kwargs: events.append("worker-build") or worker,
    )
    monkeypatch.setattr(
        processing_worker_cli,
        "install_signal_handlers",
        lambda built_worker: events.append("signals"),
    )
    worker.run.side_effect = lambda: events.append("worker-run")

    processing_worker_cli.main()

    assert events == [
        "bootstrap-logging",
        "config",
        "configured-logging",
        "startup-checks",
        "worker-build",
        "signals",
        "worker-run",
    ]
    assert startup_modes == ["verify"]


def test_worker_signal_handlers_request_graceful_stop(monkeypatch):
    worker = Mock()
    handlers = {}
    monkeypatch.setattr(
        processing_worker_cli.signal,
        "signal",
        lambda signum, handler: handlers.setdefault(signum, handler),
    )

    processing_worker_cli.install_signal_handlers(worker)
    handlers[signal.SIGINT](signal.SIGINT, None)
    handlers[signal.SIGTERM](signal.SIGTERM, None)
    if hasattr(signal, "SIGBREAK"):
        handlers[signal.SIGBREAK](signal.SIGBREAK, None)

    expected_calls = 3 if hasattr(signal, "SIGBREAK") else 2
    assert worker.stop.call_count == expected_calls


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
        config = DictConfig(
            {
                "logging.log_file": "logs/runtime.log",
                "logging.log_level": "DEBUG",
            },
            config_path=tmp_path / "config.yaml",
        )
        root = logging_config.setup_logging(config, process_role="supervisor")

    assert root.level == logging.DEBUG
    assert logging_config.resolve_log_path(
        config,
        process_role="supervisor",
    ) == tmp_path / "logs" / "runtime.supervisor.log"
    assert file_handler.setLevel.call_args.args[0] == logging.DEBUG
    assert console_handler.setLevel.call_args.args[0] == logging.DEBUG
    file_handler.addFilter.assert_called_once()
    console_handler.addFilter.assert_called_once()
    file_handler.setFormatter.assert_called_once()
    console_handler.setFormatter.assert_called_once()
    assert logging_config.get_logger("covered").name == "covered"


def test_logging_role_path_preserves_absolute_destination(tmp_path):
    config = DictConfig(
        {"logging.log_file": tmp_path / "service"},
        config_path=tmp_path / "config.yaml",
    )

    assert logging_config.resolve_log_path(
        config,
        process_role="Web Process",
    ) == tmp_path / "service.web-process.log"


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


def test_utf8_wrapper_initializes_and_keeps_buffer_open():
    raw = io.BytesIO()
    wrapper = logging_config._NonClosingUTF8Wrapper(raw)
    wrapper.write("hello")
    wrapper.close()
    assert raw.getvalue() == b"hello"


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
    with pytest.raises(ValueError, match="SQLite batch and document records"):
        processor.process_file(
            "input.pdf",
            "id",
            "web",
            create_sqlite_state=False,
        )

    workflow.trigger_workflow_for_file.side_effect = None
    workflow.trigger_workflow_for_file.return_value = False
    assert processor.process_file(
        "input.pdf",
        "id",
        "web",
        batch_id="batch",
        document_id="document",
        create_sqlite_state=False,
    ) is False


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

    returned_failure = Mock(side_effect=[False, True])
    assert monitor._retry_file_operation(returned_failure, attempts=2, delay=0.01) is True
    assert returned_failure.call_count == 2

    cleanup.reset_mock()
    always_false = Mock(return_value=False)
    assert monitor._retry_file_operation(
        always_false,
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
