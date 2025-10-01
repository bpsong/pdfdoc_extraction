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
  log_format: "%(asctime)s %(levelname)s %(name)s %(message)s"

tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: "your_llama_cloud_api_key"
      agent_id: "your_agent_id"
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
from typing import Optional
import sys  # Import sys module
from pathlib import Path
import threading
import time
import logging.handlers

import uvicorn
import subprocess
import shlex
import os as _os

# Add the current directory to the Python path to ensure modules are discoverable
sys.path.append(str(Path(__file__).parent))

from modules.workflow_loader import WorkflowLoader
from modules.config_manager import ConfigManager
from modules.shutdown_manager import ShutdownManager
from modules.watch_folder_monitor import WatchFolderMonitor
from modules.file_processor import FileProcessor
from modules.workflow_manager import WorkflowManager

from modules.logging_config import setup_logging

# Initialize a basic logger reference; real configuration happens in setup_logging()
logger = logging.getLogger(__name__)


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


def start_web_server(config: ConfigManager, logger: logging.Logger):
    """Spawn Uvicorn as a subprocess with configured host, port, and reload options.

    Args:
        config (ConfigManager): Configuration manager instance.
        logger (logging.Logger): Logger instance for logging.

    Returns:
        tuple: (subprocess.Popen, file handle) for the Uvicorn process and log file.

    Raises:
        Exception: If subprocess creation fails.
    """
    host = config.get("web.host") or "127.0.0.1"
    port = int(config.get("web.port") or 8000)
    use_reload_env = _os.getenv("USE_RELOAD", "false").lower()
    use_reload = use_reload_env in ("1", "true", "yes", "on")

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

        process = subprocess.Popen(
            cmd,
            shell=False,
            # Do not redirect stdout/stderr so subprocess log records are handled
            # by the application's logging configuration (console + file handlers).
            cwd=str(Path(__file__).parent),  # ensure project root
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
    # Use centralized logging setup from modules.logging_config
    setup_logging(wrap_stdout_utf8=True)

    # Initialize ShutdownManager singleton
    shutdown_manager = ShutdownManager()

    # Initialize WatchFolderMonitor (temporarily to get _retry_file_operation)
    # This instance is temporary and will be re-initialized with the correct callback
    temp_watch_folder_monitor = WatchFolderMonitor(config_manager, None, None)  # Pass None for callback and retry_func initially

    # Instantiate WorkflowManager
    workflow_manager = WorkflowManager(config_manager)

    # Initialize FileProcessor with config_manager, the retry function, and workflow_manager
    file_processor = FileProcessor(config_manager, temp_watch_folder_monitor._retry_file_operation, workflow_manager)

    # Define a wrapper function to pass the source to process_file
    def watch_folder_process_callback(filepath: str, unique_id: str, source: str, original_filename: Optional[str] = None):
        logger.info("Watch folder callback received",
                    extra={"unique_id": unique_id, "file_path": filepath, "source": source})
        file_processor.process_file(filepath, unique_id, source=source, original_filename=original_filename)

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

    # Initialize and start the WatchFolderMonitor with the actual file processing callback
    watch_folder_monitor = WatchFolderMonitor(config_manager, watch_folder_process_callback, temp_watch_folder_monitor._retry_file_operation)
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
                    logger.error(f"Uvicorn subprocess exited with code {ret}. Check logs at {config_manager.get('logging.log_file', 'app.log')}")
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
