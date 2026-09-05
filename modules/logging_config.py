"""
Prefect-aligned logging configuration for the PDF document extraction system.
"""
import io
import logging
import logging.handlers
import os
from pathlib import Path
import re
import sys
from typing import Protocol, TextIO

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

_CONSOLE_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)-7s | "
    "%(process_role)s:%(process)d | %(name)s - %(message)s"
)
_TASK_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)-7s | "
    "%(process_role)s:%(process)d | Task run %(task_run_name)r - %(message)s"
)
_FLOW_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)-7s | "
    "%(process_role)s:%(process)d | Flow run %(flow_run_name)r - %(message)s"
)
_CONSOLE_DATEFMT = "%H:%M:%S"
_FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"
_DEFAULT_ROLE = "application"
_VALID_LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


class _LoggingConfig(Protocol):
    """Subset of deployment configuration needed for logging."""

    def get(self, key: str, default: object = None) -> object:
        """Return a deployment setting."""


class _ProcessRoleFilter(logging.Filter):
    """Attach the current process role to every log record."""

    def __init__(self, process_role: str) -> None:
        super().__init__()
        self.process_role = process_role

    def filter(self, record: logging.LogRecord) -> bool:
        record.process_role = self.process_role
        return True


class _NonClosingUTF8Wrapper(io.TextIOWrapper):
    """UTF-8 wrapper that keeps the underlying stream open when closed."""

    def __init__(self, buffer: io.BufferedWriter):
        super().__init__(buffer, encoding="utf-8", line_buffering=True, write_through=True)

    def close(self) -> None:  # pragma: no cover - defensive flush only
        try:
            self.flush()
        except Exception:
            pass


class _NonClosingRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Rotating handler that tolerates writes during interpreter shutdown."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except ValueError:
            return

    def close(self) -> None:  # pragma: no cover - defensive close only
        try:
            super().close()
        except (OSError, ValueError):
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


def _normalize_process_role(process_role: str | None) -> str:
    """Return a safe role label suitable for logs and filenames."""
    normalized = re.sub(
        r"[^a-z0-9_-]+",
        "-",
        str(process_role or _DEFAULT_ROLE).strip().lower(),
    ).strip("-")
    return normalized or _DEFAULT_ROLE


def resolve_log_path(
    config: _LoggingConfig | None = None,
    *,
    process_role: str = _DEFAULT_ROLE,
) -> Path:
    """Resolve the rotating log path for one application process role."""
    configured = config.get("logging.log_file", "app.log") if config else "app.log"
    base_path = Path(str(configured or "app.log"))
    if not base_path.is_absolute():
        config_path = getattr(config, "_config_path", None) if config else None
        base_directory = (
            Path(config_path).resolve().parent if config_path else Path.cwd()
        )
        base_path = base_directory / base_path
    base_path = base_path.resolve()
    role = _normalize_process_role(process_role)
    if role != _DEFAULT_ROLE:
        suffix = base_path.suffix or ".log"
        stem = base_path.stem if base_path.suffix else base_path.name
        base_path = base_path.with_name(f"{stem}.{role}{suffix}")
    return base_path


def _configured_log_level(config: _LoggingConfig | None) -> tuple[int, str | None]:
    """Return the configured level and an invalid value to report, if any."""
    raw_level = config.get("logging.log_level", "INFO") if config else "INFO"
    level_name = str(raw_level or "INFO").strip().upper()
    level = _VALID_LOG_LEVELS.get(level_name)
    if level is None:
        return logging.INFO, level_name
    return level, None


def setup_bootstrap_logging(*, process_role: str) -> logging.Logger:
    """Install stderr logging before deployment configuration is available."""
    role = _normalize_process_role(process_role)
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_ProcessRoleFilter(role))
    handler.setFormatter(_prefect_formatter(datefmt=_CONSOLE_DATEFMT))
    root_logger = logging.getLogger()
    for existing in root_logger.handlers[:]:
        root_logger.removeHandler(existing)
        try:
            existing.close()
        except (OSError, ValueError):
            pass
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    return root_logger


def setup_logging(
    config: _LoggingConfig | None = None,
    *,
    process_role: str = _DEFAULT_ROLE,
    wrap_stdout_utf8: bool = False,
    file_logging: bool = True,
) -> logging.Logger:
    """Configure role-aware root logging from deployment settings."""
    role = _normalize_process_role(process_role)
    level, invalid_level = _configured_log_level(config)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except (OSError, ValueError):
            pass

    file_formatter = _prefect_formatter(datefmt=_FILE_DATEFMT)
    console_formatter = _prefect_formatter(datefmt=_CONSOLE_DATEFMT)
    role_filter = _ProcessRoleFilter(role)

    if file_logging:
        log_path = resolve_log_path(config, process_role=role)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = _NonClosingRotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.addFilter(role_filter)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        except (OSError, ValueError) as exc:  # pragma: no cover
            print(
                f"Warning: Failed to set up {role} file logging: "
                f"{type(exc).__name__}",
                file=sys.stderr,
            )

    console_stream = _resolve_console_stream(wrap_stdout_utf8)
    console_handler = PrefectConsoleHandler(stream=console_stream, styles=_PREFECT_CONSOLE_STYLES)
    console_handler.setLevel(level)
    console_handler.addFilter(role_filter)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    if invalid_level is not None:
        root_logger.warning(
            "Unsupported logging level %r; using INFO.",
            invalid_level,
        )

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
