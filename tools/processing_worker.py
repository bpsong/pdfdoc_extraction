"""Command-line entry point for the durable processing worker."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from modules.config_manager import ConfigManager
from modules.db.migrations import initialize_database
from modules.logging_config import setup_logging
from modules.services.processing_worker import build_worker


def main() -> None:
    """Load deployment settings and run the durable worker."""
    parser = argparse.ArgumentParser(description="DocFlow durable processing worker")
    parser.add_argument("--config-path", type=str, help="Path to the YAML configuration file")
    args = parser.parse_args()
    config_path = Path(args.config_path or "config.yaml").resolve()
    config = ConfigManager(config_path=config_path)
    if bool(config.get("database.run_migrations_on_startup", True)):
        initialize_database(config)
    setup_logging(wrap_stdout_utf8=True)
    build_worker(config).run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
