"""
Prefect-aligned logging configuration for the PDF document extraction system.
"""
import io
import logging
import logging.handlers
import os
import sys
import warnings
from typing import TextIO

# Prefect imports trigger pydantic_settings warnings about unused TOML config keys.
# Silence those specific messages while keeping other warnings visible.
warnings.filterwarnings(
    "ignore",
    message=r"Config key `.*` is set in model_config but will be ignored because no .* source is configured.",
    module="pydantic_settings.main",
)

from prefect.logging.formatters import PrefectFormatter
from prefect.logging.handlers import PrefectConsoleHandler

# Prevent Prefect from spawning API log handlers when running locally/tests.
os.environ.setdefault("PREFECT_LOGGING_TO_API_ENABLED", "false")

# Prefect console styles mirror prefect/logging/logging.yml
_PREFECT_CONSOLE_STYLES = {
    "log.web_url": "bright_blue",
    "log.local_url": "bright_blue",
    "log.debug_level": "blue",
    "log.info_level": "cyan",
    "log.warning_level": "yellow3",
    "log.error_level": "red3",
    "log.critical_level": "bright_red",
    "log.completed_state": "green",
    "log.cancelled_state": "yellow3",
    "log.failed_state": "red3",
    "log.crashed_state": "bright_red",
    "log.cached_state": "bright_blue",
    "log.flow_run_name": "magenta",
    "log.flow_name": "bold magenta",
}

_CONSOLE_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s - %(message)s"
_TASK_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-7s | Task run %(task_run_name)r - %(message)s"
_FLOW_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-7s | Flow run %(flow_run_name)r - %(message)s"
_CONSOLE_DATEFMT = "%H:%M:%S"
_FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"


class _NonClosingUTF8Wrapper(io.TextIOWrapper):
    """UTF-8 wrapper that keeps the underlying stream open when closed."""

    def __init__(self, buffer: io.BufferedIOBase):
        super().__init__(buffer, encoding="utf-8", line_buffering=True, write_through=True)

    def close(self) -> None:  # pragma: no cover - defensive flush only
        try:
            self.flush()
        except Exception:
            pass


class _NonClosingRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Rotating handler that tolerates flushes after the stream closes."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except ValueError:
            return

    def close(self) -> None:  # pragma: no cover - defensive flush only
        try:
            self.flush()
        except Exception:
            pass


def _prefect_formatter(*, datefmt: str) -> PrefectFormatter:
    return PrefectFormatter(
        format=_CONSOLE_FORMAT,
        datefmt=datefmt,
        task_run_fmt=_TASK_FORMAT,
        flow_run_fmt=_FLOW_FORMAT,
    )


def _resolve_console_stream(wrap_stdout_utf8: bool) -> TextIO:
    base_stream: TextIO = getattr(sys, "__stdout__", sys.stdout)
    if not wrap_stdout_utf8:
        return base_stream
    buffer = getattr(base_stream, "buffer", None)
    if buffer is None:
        return base_stream
    try:
        return _NonClosingUTF8Wrapper(buffer)
    except Exception:
        return base_stream


def setup_logging(wrap_stdout_utf8: bool = False) -> logging.Logger:
    """Configure root logging using Prefect-style formatting."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    file_formatter = _prefect_formatter(datefmt=_FILE_DATEFMT)
    console_formatter = _prefect_formatter(datefmt=_CONSOLE_DATEFMT)

    try:
        file_handler = _NonClosingRotatingFileHandler(
            "app.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    except Exception as exc:  # pragma: no cover
        print(f"Warning: Failed to set up file logging: {exc}")

    console_stream = _resolve_console_stream(wrap_stdout_utf8)
    console_handler = PrefectConsoleHandler(stream=console_stream, styles=_PREFECT_CONSOLE_STYLES)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Mute noisy loggers that emit during Prefect server shutdown.
    for noisy_name in ("prefect.server.api.server", "httpx"):
        noisy_logger = logging.getLogger(noisy_name)
        noisy_logger.handlers.clear()
        noisy_logger.propagate = False

    logging.captureWarnings(True)
    logging.raiseExceptions = False
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with the centralized Prefect-style setup."""
    return logging.getLogger(name)
