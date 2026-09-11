"""
Main entry point for the PDF Processing Application.

This module handles:
- Command-line argument parsing for configuration and server options.
- Configuration loading and validation via ConfigManager.
- Logging setup based on configuration.
- Initialization of core components: ShutdownManager, WatchFolderCoordinator, WorkflowManager, FileProcessor.
- Starting the web server (Uvicorn) as a subprocess with configured host, port, and reload options.
- Starting the watch folder monitor to process incoming files.
- Graceful shutdown handling on keyboard interrupt, including stopping the monitor and terminating the web server.
- Invoking ShutdownManager shutdown and exiting cleanly.

Usage:
    python main.py [--config-path PATH] [--no-web]

Arguments:
    --config-path: Optional path to a custom configuration YAML file.
    --no-web: Flag to disable starting the web server.

Notes:
 - Logging is configured with console and rotating file handlers.
 - The watch folder monitor uses a callback to process files via FileProcessor.
 - The web server runs asynchronously in a subprocess.
 - The main thread supervises the web server and handles shutdown signals.

Example configuration:
web:
  host: "127.0.0.1"
  port: 8000
  secret_key: "your_secret_key"
  upload_dir: "web_upload"

watch_folder:
  dir: "watch_folder"
  validate_pdf_header: true
  processing_dir: "processing"

authentication:
  username: "admin"
  password_hash: "$2b$12$example_hash_for_secure_password"

logging:
  log_file: "app.log"
  log_level: "INFO"
  

tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: "your_llama_cloud_api_key"
      configuration_id: "your_extract_v2_configuration_id"
      fields:
        supplier_name:
          alias: "Supplier name"
          type: "str"
        invoice_amount:
          alias: "Invoice Amount"
          type: "float"
    on_error: stop

pipeline:
  - extract_document_data
"""
import argparse
import os
import logging
import sys  # Import sys module
from pathlib import Path
import time
import logging.handlers
import signal
import warnings
import threading
import uuid

import subprocess
import shlex
import os as _os

# Add the current directory to the Python path to ensure modules are discoverable
sys.path.append(str(Path(__file__).parent))

# Ensure Prefect and any spawned subprocesses inherit a warning filter that silences
# pydantic_settings' noisy "ignored config key" messages related to unused TOML sources.
_warning_filter = "ignore::UserWarning:pydantic_settings.main"
existing_warning_env = os.environ.get("PYTHONWARNINGS", "")
if _warning_filter not in existing_warning_env.split(","):
    os.environ["PYTHONWARNINGS"] = ",".join(filter(None, [existing_warning_env, _warning_filter]))
warnings.filterwarnings(
    "ignore",
    message=r"Config key `.*` is set in model_config but will be ignored because no .+ source is configured.*",
    module="pydantic_settings.main",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"Config key `pyproject_toml_table_header` is set in model_config but will be ignored because no PyprojectTomlConfigSettingsSource source is configured.*",
    category=UserWarning,
)

from modules.config_manager import ConfigManager
from modules.config_protocol import ConfigProvider
from modules.shutdown_manager import ShutdownManager
from modules.file_processor import FileProcessor
from modules.workflow_manager import WorkflowManager
from modules.services.watch_folder_coordinator import WatchFolderCoordinator
from modules.services.startup_service import run_startup_checks
from modules.services.runtime_health_service import (
    RuntimeHealthReporter,
    RuntimeHealthService,
)

from modules.logging_config import resolve_log_path, setup_bootstrap_logging, setup_logging

# Initialize a basic logger reference; real configuration happens in setup_logging()
logger = logging.getLogger(__name__)


def _should_use_reload(env: dict[str, str] | None = None) -> bool:
    """Return whether Uvicorn reload should be enabled for the current environment."""
    env_values = env if env is not None else _os.environ
    reload_value = env_values.get("USE_RELOAD", "false").lower()
    reload_requested = reload_value in ("1", "true", "yes", "on")
    app_env = (
        env_values.get("APP_ENV")
        or env_values.get("ENV")
        or env_values.get("ENVIRONMENT")
        or ""
    ).lower()
    if app_env in {"prod", "production"}:
        return False
    return reload_requested


def parse_args():
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments with attributes 'config_path' and 'no_web'.
    """
    parser = argparse.ArgumentParser(description="PDF Processing Application")
    parser.add_argument("--config-path", type=str, help="Specify a custom path to the config file.")
    parser.add_argument("--no-web", action="store_true", help="Do not start the web server")
    return parser.parse_args()


def resolve_config_path(args) -> Path:
    """Resolve the configuration file path from CLI args or environment.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.

    Returns:
        Path: Resolved absolute path to the configuration YAML file.
    """
    if args.config_path:
        return Path(args.config_path).resolve()
    env_config_path = os.getenv("CONFIG_PATH")
    if env_config_path:
        return Path(env_config_path).resolve()
    return (Path(__file__).parent / "config.yaml").resolve()


def start_web_server(
    config: ConfigProvider,
    logger: logging.Logger,
    *,
    run_id: str | None = None,
    expected_components: tuple[str, ...] = (),
):
    """Spawn Uvicorn as a subprocess with configured host, port, and reload options.

    Args:
        config: Configuration provider used to resolve server settings.
        logger (logging.Logger): Logger instance for logging.

    Returns:
        tuple: (subprocess.Popen, file handle) for the Uvicorn process and log file.

    Raises:
        Exception: If subprocess creation fails.
    """
    host = config.get("web.host") or "127.0.0.1"
    port = int(config.get("web.port") or 8000)
    use_reload = _should_use_reload()
    if not use_reload and _os.getenv("USE_RELOAD", "false").lower() in ("1", "true", "yes", "on"):
        logger.warning("Uvicorn reload requested but disabled in production environment")

    # Build command
    base_cmd = f'{shlex.quote(sys.executable)} -m uvicorn web.server:app --host {shlex.quote(str(host))} --port {shlex.quote(str(port))}'
    if use_reload:
        base_cmd += " --reload"

    logger.info(f"Spawning Uvicorn: {base_cmd}")
    log_file_path = resolve_log_path(config, process_role="web")
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    uvicorn_log = open(log_file_path, mode="a", encoding="utf-8", buffering=1)

    try:
        # Build command as a list to avoid Windows shell parsing issues
        cmd = [
            sys.executable,
            "-m", "uvicorn",
            "web.server:app",
            "--host", str(host),
            "--port", str(port),
        ]
        if use_reload:
            cmd.append("--reload")

        # Ensure the web process reads the same resolved config path
        child_env = os.environ.copy()
        child_env["DOCFLOW_PROCESS_ROLE"] = "web"
        child_env["DOCFLOW_STDIO_CAPTURED"] = "1"
        child_env["DOCFLOW_STARTUP_MODE"] = "verify"
        if run_id:
            child_env["DOCFLOW_RUN_ID"] = run_id
        if expected_components:
            child_env["DOCFLOW_EXPECTED_COMPONENTS"] = ",".join(expected_components)
        try:
            resolved_cfg = getattr(config, "_config_path", None)
            if resolved_cfg:
                child_env["CONFIG_PATH"] = str(resolved_cfg)
        except Exception:
            pass

        creation_flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        )
        process = subprocess.Popen(
            cmd,
            shell=False,
            stdout=uvicorn_log,
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).parent),  # ensure project root
            env=child_env,
            creationflags=creation_flags,
        )
        logger.info(f"Uvicorn subprocess started with PID {process.pid}, listening on http://{host}:{port}")
        return process, uvicorn_log
    except Exception as e:
        try:
            uvicorn_log.close()
        except Exception:
            pass
        logger.exception(f"Failed to spawn Uvicorn subprocess: {e}")
        raise


def start_processing_worker(
    config: ConfigProvider,
    logger: logging.Logger,
    *,
    run_id: str | None = None,
    expected_components: tuple[str, ...] = (),
):
    """Spawn the durable worker with the same resolved deployment config."""
    child_env = os.environ.copy()
    resolved_cfg = getattr(config, "_config_path", None)
    if resolved_cfg:
        child_env["CONFIG_PATH"] = str(resolved_cfg)
    child_env["DOCFLOW_PROCESS_ROLE"] = "worker"
    child_env["DOCFLOW_STARTUP_MODE"] = "verify"
    if run_id:
        child_env["DOCFLOW_RUN_ID"] = run_id
    if expected_components:
        child_env["DOCFLOW_EXPECTED_COMPONENTS"] = ",".join(expected_components)
    cmd = [
        sys.executable,
        "-m",
        "tools.processing_worker",
        "--config-path",
        str(resolved_cfg) if resolved_cfg else "config.yaml",
    ]
    logger.info("Spawning durable processing worker")
    creation_flags = (
        subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    )
    return subprocess.Popen(
        cmd,
        shell=False,
        cwd=str(Path(__file__).parent),
        env=child_env,
        creationflags=creation_flags,
    )


def wait_for_runtime_readiness(
    config: ConfigProvider,
    run_id: str,
    expected_components: tuple[str, ...],
    *,
    processes: dict[str, subprocess.Popen],
    watch_thread: threading.Thread,
) -> dict[str, object]:
    """Wait a bounded time for fresh health from every required component."""
    timeout = max(
        1.0,
        float(config.get("runtime_health.startup_timeout_seconds", 30) or 30),
    )
    deadline = time.monotonic() + timeout
    service = RuntimeHealthService(config, run_id)
    last_snapshot: dict[str, object] = {}
    while time.monotonic() < deadline:
        for component, process in processes.items():
            return_code = process.poll()
            if return_code is not None:
                record_runtime_failure(
                    service,
                    component,
                    details={"exit_code": return_code, "phase": "startup"},
                )
                raise RuntimeError(
                    f"{component} exited during startup with code {return_code}"
                )
        if not watch_thread.is_alive():
            raise RuntimeError("watch-folder coordinator exited during startup")
        last_snapshot = service.snapshot(expected_components)
        if bool(last_snapshot.get("ready")):
            return last_snapshot
        time.sleep(0.1)
    missing = last_snapshot.get("missing_components", [])
    unhealthy = last_snapshot.get("unhealthy_components", [])
    raise RuntimeError(
        "Runtime readiness timed out. "
        f"missing={missing} unhealthy={unhealthy}"
    )


def record_runtime_failure(
    service: RuntimeHealthService,
    component: str,
    *,
    details: dict[str, object],
) -> None:
    """Persist a component failure without masking supervision behavior."""
    try:
        service.record(component, "failed", details=details)
    except Exception:
        logger.exception(
            "Failed to persist component failure: component=%s", component
        )


def terminate_process_tree(
    process: subprocess.Popen,
    *,
    name: str,
    logger: logging.Logger,
    timeout: float = 10,
) -> None:
    """Stop a child and its descendants, with a bounded forced fallback."""
    if process.poll() is not None:
        return
    logger.info("Stopping %s process tree (PID %s)", name, process.pid)
    try:
        if os.name == "nt":
            os.kill(process.pid, signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        process.wait(timeout=timeout)
        return
    except (OSError, subprocess.SubprocessError, TimeoutError):
        logger.warning("Graceful %s shutdown timed out; forcing termination", name)

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    else:
        process.kill()
    process.wait(timeout=timeout)


def main():
    """Main entry point for the application.

    Parses arguments, loads configuration, sets up logging, initializes components,
    starts the web server and watch folder monitor, and handles graceful shutdown.
    """
    # Parse CLI args
    args = parse_args()

    # Determine the config path
    resolved_config_path = resolve_config_path(args)

    setup_bootstrap_logging(process_role="supervisor")

    # Initialize ConfigManager singleton with the resolved path
    config_manager = ConfigManager(config_path=resolved_config_path)
    setup_logging(
        config_manager,
        process_role="supervisor",
        wrap_stdout_utf8=True,
    )
    try:
        run_startup_checks(config_manager, migration_mode="migrate")
    except Exception as exc:
        logger.critical(
            "Application startup checks failed; startup is blocked. "
            "failure_type=%s",
            type(exc).__name__,
        )
        sys.exit(1)

    shutdown_manager = ShutdownManager()
    run_id = uuid.uuid4().hex
    expected_components = ("supervisor", "worker", "watch_folder")
    if not args.no_web:
        expected_components += ("web",)
    supervisor_reporter = RuntimeHealthReporter(
        config_manager, run_id, "supervisor"
    )
    watch_reporter = RuntimeHealthReporter(
        config_manager, run_id, "watch_folder"
    )
    worker_proc = None
    uvicorn_proc = None
    uvicorn_log_handle = None
    watch_coordinator = None
    watch_thread = None
    exit_code = 0
    monitor_failure: list[BaseException] = []

    try:
        supervisor_reporter.start(status="starting")
        workflow_manager = WorkflowManager(config_manager)
        file_processor = FileProcessor(config_manager, None, workflow_manager)

        worker_proc = start_processing_worker(
            config_manager,
            logger,
            run_id=run_id,
            expected_components=expected_components,
        )

        if not args.no_web:
            uvicorn_proc, uvicorn_log_handle = start_web_server(
                config_manager,
                logger,
                run_id=run_id,
                expected_components=expected_components,
            )
        else:
            logger.info("Web server disabled via --no-web")

        watch_coordinator = WatchFolderCoordinator(
            config_manager,
            file_processor,
            health_reporter=watch_reporter,
        )

        def run_watch_folder_coordinator() -> None:
            """Capture coordinator failures for the supervisor."""
            try:
                watch_reporter.start(status="ready")
                watch_coordinator.start()
            except BaseException as exc:
                monitor_failure.append(exc)
                logger.exception("Watch folder monitoring stopped unexpectedly")
                watch_reporter.stop(status="failed")

        watch_thread = threading.Thread(
            target=run_watch_folder_coordinator,
            name="watch-folder-coordinator",
            daemon=True,
        )
        watch_thread.start()
        supervisor_reporter.set_status("ready")

        processes = {"worker": worker_proc}
        if uvicorn_proc is not None:
            processes["web"] = uvicorn_proc
        wait_for_runtime_readiness(
            config_manager,
            run_id,
            expected_components,
            processes=processes,
            watch_thread=watch_thread,
        )
        logger.info("Application runtime is ready: run_id=%s", run_id)
        runtime_health = RuntimeHealthService(config_manager, run_id)

        while True:
            if monitor_failure or not watch_thread.is_alive():
                if not monitor_failure:
                    watch_reporter.set_status(
                        "failed", {"reason": "coordinator_exited"}
                    )
                logger.error("Watch-folder coordinator exited unexpectedly")
                exit_code = 1
                break
            if uvicorn_proc is not None and uvicorn_proc.poll() is not None:
                record_runtime_failure(
                    runtime_health,
                    "web",
                    details={
                        "exit_code": uvicorn_proc.returncode,
                        "phase": "runtime",
                    },
                )
                logger.error(
                    "Uvicorn subprocess exited unexpectedly with code %s",
                    uvicorn_proc.returncode,
                )
                exit_code = 1
                break
            if worker_proc.poll() is not None:
                record_runtime_failure(
                    runtime_health,
                    "worker",
                    details={
                        "exit_code": worker_proc.returncode,
                        "phase": "runtime",
                    },
                )
                logger.error(
                    "Durable processing worker exited unexpectedly with code %s",
                    worker_proc.returncode,
                )
                exit_code = 1
                break
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    except Exception as exc:
        exit_code = 1
        logger.exception(
            "Application startup or supervision failed: failure_type=%s",
            type(exc).__name__,
        )
    finally:
        try:
            supervisor_reporter.set_status("stopping")
        except Exception:
            logger.exception("Failed to record supervisor stopping state")
        if watch_coordinator is not None:
            try:
                watch_coordinator.stop()
            except Exception as exc:
                logger.warning("Error while stopping watch-folder coordinator: %s", exc)
        if watch_thread is not None and watch_thread.is_alive():
            watch_thread.join(timeout=10)
        try:
            watch_reporter.stop()
        except Exception:
            logger.exception("Failed to stop watch-folder health reporter")
        if uvicorn_proc is not None:
            try:
                terminate_process_tree(
                    uvicorn_proc, name="web", logger=logger
                )
            except Exception as exc:
                exit_code = 1
                logger.warning("Error while terminating web process tree: %s", exc)
            finally:
                if uvicorn_log_handle is not None:
                    try:
                        uvicorn_log_handle.flush()
                        uvicorn_log_handle.close()
                    except Exception:
                        pass
        if worker_proc is not None:
            try:
                terminate_process_tree(
                    worker_proc, name="worker", logger=logger
                )
            except Exception as exc:
                exit_code = 1
                logger.warning("Error while terminating worker process tree: %s", exc)
        try:
            supervisor_reporter.stop(status="failed" if exit_code else "stopped")
        finally:
            shutdown_manager.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
