"""
Main entry point for the PDF Processing Application.

This module handles:
- Command-line argument parsing for configuration and server options.
- Configuration loading and validation via ConfigManager.
- Logging setup based on configuration.
- Initialization of core components: ShutdownManager, WatchFolderMonitor, WorkflowManager, FileProcessor.
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
import warnings

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
from modules.db.migrations import initialize_database
from modules.services.task_registry_service import validate_startup_task_registry

from modules.logging_config import setup_logging

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


def start_web_server(config: ConfigProvider, logger: logging.Logger):
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
    log_file_path = config.get("logging.log_file", "app.log") or "app.log"

    # Ensure log_file_path is a string path
    if isinstance(log_file_path, Path):
        log_file_path = str(log_file_path)

    # Open file in append mode (text) and pass as both stdout and stderr
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
        try:
            resolved_cfg = getattr(config, "_config_path", None)
            if resolved_cfg:
                child_env["CONFIG_PATH"] = str(resolved_cfg)
        except Exception:
            pass

        process = subprocess.Popen(
            cmd,
            shell=False,
            # Do not redirect stdout/stderr so subprocess log records are handled
            # by the application's logging configuration (console + file handlers).
            cwd=str(Path(__file__).parent),  # ensure project root
            env=child_env,
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


def main():
    """Main entry point for the application.

    Parses arguments, loads configuration, sets up logging, initializes components,
    starts the web server and watch folder monitor, and handles graceful shutdown.
    """
    # Parse CLI args
    args = parse_args()

    # Determine the config path
    resolved_config_path = resolve_config_path(args)

    # Initialize ConfigManager singleton with the resolved path
    config_manager = ConfigManager(config_path=resolved_config_path)
    if bool(config_manager.get("database.run_migrations_on_startup", True)):
        try:
            initialize_database(config_manager)
        except Exception:
            logger.critical(
                "Database migration failed; startup is blocked before accepting work."
            )
            sys.exit(1)
    # Use centralized logging setup from modules.logging_config
    setup_logging(wrap_stdout_utf8=True)
    validate_startup_task_registry(config_manager)

    # Initialize ShutdownManager singleton
    shutdown_manager = ShutdownManager()

    # Instantiate WorkflowManager
    workflow_manager = WorkflowManager(config_manager)

    # FileProcessor retains a legacy retry dependency but no longer uses it.
    file_processor = FileProcessor(config_manager, None, workflow_manager)

    # Start web server FIRST unless disabled
    uvicorn_proc = None
    uvicorn_log_handle = None
    if not args.no_web:
        try:
            uvicorn_proc, uvicorn_log_handle = start_web_server(config_manager, logger)
        except Exception as e:
            logger.exception(f"Failed to start web server: {e}")
            sys.exit(1)
    else:
        logger.info("Web server disabled via --no-web")

    # One coordinator reconciles all enabled SQLite watch-folder bindings.
    watch_folder_monitor = WatchFolderCoordinator(config_manager, file_processor)
    # Do not return early on KeyboardInterrupt here; handle shutdown in unified block below
    try:
        logger.info("Watch folder monitoring has started. Press Ctrl+C to stop.")
        watch_folder_monitor.start()
        if args.no_web:
            # Exit after watch folder monitor returns when --no-web is set to avoid needing second Ctrl+C
            # Perform shutdown and exit cleanly
            shutdown_manager.shutdown()
            sys.exit(0)
    except Exception as e:
        logger.exception(f"Failed to start watch folder monitor: {e}")
        # If monitor fails to start, still keep web server running; fall through to main loop

    # Keep the main thread alive to allow background monitoring and supervise uvicorn
    try:
        while True:
            if uvicorn_proc is not None:
                ret = uvicorn_proc.poll()
                if ret is not None:
                    log_path = config_manager.get('logging.log_file', 'app.log')
                    if ret == 0:
                        logger.info(f"Uvicorn subprocess exited cleanly with code {ret}. Check logs at {log_path}")
                    else:
                        logger.error(f"Uvicorn subprocess exited with code {ret}. Check logs at {log_path}")
                    break
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    finally:
        # Stop watch folder monitor
        try:
            watch_folder_monitor.stop()
        except Exception as e:
            logger.warning(f"Error while stopping monitor after interrupt: {e}")
        # Terminate uvicorn subprocess
        if uvicorn_proc is not None:
            try:
                logger.info("Terminating Uvicorn subprocess...")
                uvicorn_proc.terminate()
                try:
                    uvicorn_proc.wait(timeout=10)
                except Exception:
                    logger.info("Uvicorn did not exit in time; killing...")
                    uvicorn_proc.kill()
            except Exception as e:
                logger.warning(f"Error while terminating Uvicorn: {e}")
            finally:
                if uvicorn_log_handle is not None:
                    try:
                        uvicorn_log_handle.flush()
                        uvicorn_log_handle.close()
                    except Exception:
                        pass
        # Perform shutdown and exit cleanly
        shutdown_manager.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
