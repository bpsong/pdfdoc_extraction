"""
Minimal centralized logging configuration for PDF document extraction system.
Provides clean, readable logs with file rotation and UTF-8 support.

Examples:
    Example YAML configuration for logging setup:
    ```yaml
    logging:
      level: DEBUG
      file: app.log
      format: "%(asctime)s %(levelname)s %(name)s %(message)s"
      handlers:
        - console
        - file
      rotation:
        max_bytes: 10485760  # 10MB
        backup_count: 5
      encoding: utf-8
    ```
"""
import logging
import logging.handlers
import sys
import io


def setup_logging(wrap_stdout_utf8: bool = False) -> logging.Logger:
    """
    Set up centralized logging configuration with clean, readable format.

    Args:
        wrap_stdout_utf8: Whether to wrap stdout for UTF-8 encoding on Windows

    Returns:
        Root logger configured with the specified settings

    Examples:
        Basic usage with default settings:
        >>> logger = setup_logging()

        Usage with UTF-8 stdout wrapping on Windows:
        >>> logger = setup_logging(wrap_stdout_utf8=True)

        Example YAML configuration that this function implements:
        ```yaml
        logging:
          setup:
            wrap_stdout_utf8: false
          handlers:
            console:
              enabled: true
              formatter: "%(asctime)s %(levelname)s %(name)s %(message)s"
            file:
              enabled: true
              filename: app.log
              max_bytes: 10485760
              backup_count: 5
              encoding: utf-8
          root_level: INFO
        ```
    """
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create clean formatter without context clutter
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    # File handler with rotation
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            "app.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Failed to set up file logging: {e}")

    # Console handler for development. Optionally wrap stdout for UTF-8 on Windows.
    if wrap_stdout_utf8:
        try:
            utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
            console_handler = logging.StreamHandler(stream=utf8_stdout)
        except Exception:
            console_handler = logging.StreamHandler(sys.stdout)
    else:
        console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Capture warnings
    logging.captureWarnings(True)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.

    Args:
        name: Logger name

    Returns:
        Configured logger instance

    Examples:
        Get a logger for a specific module:
        >>> logger = get_logger("file_processor")
        >>> logger.info("Processing file")

        Get a logger for a workflow step:
        >>> extraction_logger = get_logger("extraction.pdf_parser")
        >>> extraction_logger.debug("Starting PDF extraction")

        Example YAML configuration for logger hierarchy:
        ```yaml
        logging:
          loggers:
            file_processor:
              level: INFO
              propagate: true
            extraction.pdf_parser:
              level: DEBUG
              propagate: false
            api:
              level: WARNING
              propagate: true
        ```
    """
    return logging.getLogger(name)