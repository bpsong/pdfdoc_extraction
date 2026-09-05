"""Command-line entry point for the durable processing worker."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import sys
from types import FrameType

from modules.config_manager import ConfigManager
from modules.logging_config import setup_bootstrap_logging, setup_logging
from modules.services.processing_worker import build_worker
from modules.services.runtime_health_service import RuntimeHealthReporter
from modules.services.startup_service import run_startup_checks


def install_signal_handlers(worker: object) -> None:
    """Translate process signals into a graceful stop after current work."""

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        worker.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_stop)


def main() -> None:
    """Load deployment settings and run the durable worker."""
    parser = argparse.ArgumentParser(description="DocFlow durable processing worker")
    parser.add_argument("--config-path", type=str, help="Path to the YAML configuration file")
    parser.add_argument(
        "--startup-mode",
        choices=("migrate", "verify"),
        default=os.getenv("DOCFLOW_STARTUP_MODE", "verify"),
        help="Migrate as a standalone owner or verify a supervisor-prepared database.",
    )
    args = parser.parse_args()
    setup_bootstrap_logging(process_role="worker")
    config_path = Path(args.config_path or "config.yaml").resolve()
    config = ConfigManager(config_path=config_path)
    setup_logging(config, process_role="worker", wrap_stdout_utf8=True)
    run_startup_checks(config, migration_mode=args.startup_mode)
    run_id = os.getenv("DOCFLOW_RUN_ID", "").strip()
    reporter = (
        RuntimeHealthReporter(config, run_id, "worker") if run_id else None
    )
    failed = False
    try:
        if reporter is not None:
            reporter.start(status="ready")
        worker = build_worker(config, health_reporter=reporter)
        install_signal_handlers(worker)
        worker.run()
    except Exception:
        failed = True
        raise
    finally:
        if reporter is not None:
            reporter.stop(status="failed" if failed else "stopped")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
