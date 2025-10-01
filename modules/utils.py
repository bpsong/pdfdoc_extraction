"""Utility helpers for robust file handling and path management.

This module provides:
- A retry decorator for transient I/O operations.
- Windows long-path normalization to avoid MAX_PATH (260) issues.
- Safe filename sanitization for Windows filesystems.
- UUID-based filename generation that preserves extensions.
- Unique filepath generation by incrementing numeric suffixes.
- A minimal PDF header check utility with retry support.

Deprecation Note:
- No deprecations identified in current codebase.
"""
from pathlib import Path
import time
import functools
import logging
import os
import sys
import uuid
import re


def retry_io(max_attempts: int = 3, delay: float = 0.2, exceptions: tuple = (OSError, PermissionError)):
    """Retry a function on specified exceptions, intended for transient I/O failures.

    This is a decorator factory. Apply it to file or OS operations that may
    intermittently fail (e.g., file locks), and it will retry with a fixed delay.

    Args:
        max_attempts (int): Maximum number of attempts before giving up. Defaults to 3.
        delay (float): Sleep duration (seconds) between attempts. Defaults to 0.2.
        exceptions (tuple[type[BaseException], ...]): Exception types that trigger a retry.
            Defaults to (OSError, PermissionError).

    Returns:
        Callable: A decorator that wraps the target function with retry logic.

    Raises:
        Exception: Re-raises the last caught exception after max_attempts are exhausted.

    Notes:
        - Logs a warning for each failed attempt via the logging module.
        - Sleeps for 'delay' seconds between retries.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempts += 1
                    logging.warning(f"[retry_io] Attempt {attempts} failed: {e}")
                    if attempts >= max_attempts:
                        raise
                    time.sleep(delay)
        return wrapper
    return decorator


def windows_long_path(path: str) -> str:
    """Normalize to Windows long-path form when needed.

    On Windows, converts absolute paths whose length is ≥ 260 characters to use
    the long-path prefix. UNC paths are converted to the \\?\\UNC\\ form. On
    non-Windows platforms, returns the input path unchanged.

    Args:
        path (str | bytes | os.PathLike): Input path.

    Returns:
        str: Normalized long path on Windows if needed; otherwise the absolute
            or original path (non-Windows).

    Notes:
        - If the path already has the \\?\\ prefix, it is returned unchanged.
        - UNC paths (starting with \\\\) are converted to \\?\\UNC\\ prefix.
        - This function is effectively a no-op on non-Windows platforms.
    """
    if sys.platform == "win32":
        abs_path = os.path.abspath(path)
        if len(abs_path) >= 260:
            # If path already has long path prefix, return as is
            if abs_path.startswith('\\\\?\\'):
                return abs_path
            # Convert to long path format
            # For UNC paths, prefix with \\?\UNC\
            if abs_path.startswith('\\\\'):
                return '\\\\?\\UNC\\' + abs_path.lstrip('\\')
            else:
                return '\\\\?\\' + abs_path
        else:
            return abs_path
    else:
        return path


def preprocess_filename_value(value) -> str:
    """Preprocess a value for filename formatting, handling empty/null values.
    
    Args:
        value: The value to preprocess. Can be any type.
        
    Returns:
        str: Processed string value. Returns "none" for null/empty values,
             otherwise converts to string and returns.
    """
    if value is None:
        return "none"
    if isinstance(value, str) and not value.strip():
        return "none"
    return str(value)


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for Windows filesystems while preserving extension.

    Steps performed:
      1. Split base name and extension.
      2. Remove control characters and Windows-illegal symbols: <>:"/\\|?*.
      3. Trim whitespace and leading/trailing underscores.
      4. If empty after cleaning, substitute a short UUID-based name.
      5. Enforce max length (255) including extension by truncating base.

    Args:
        filename (str): Input filename to sanitize.

    Returns:
        str: A sanitized filename safe for Windows paths.

    Notes:
        - Removes ASCII control characters (0x00–0x1F) and Windows-illegal characters.
        - Preserves the original extension.
        - Enforces a 255-character total limit; base is truncated if necessary.
        - Falls back to a UUID-derived base when the cleaned name is empty.
    """
    import uuid
    base, ext = os.path.splitext(filename)
    # Remove control characters and Windows-illegal characters
    invalid_chars_pattern = r'[\x00-\x1F<>:"/\\|?*]+'
    base = re.sub(invalid_chars_pattern, '', base).strip()
    base = base.strip('_')
    # If the base is empty after sanitization, use a default name with UUID
    if not base:
        base = f"file_{uuid.uuid4().hex[:8]}"
    # Truncate base if filename is too long (max 255 chars for Windows, including extension)
    max_filename_length = 255
    allowed_base_length = max_filename_length - len(ext)
    if len(base + ext) > max_filename_length:
        base = base[:allowed_base_length]
    sanitized_filename = f"{base}{ext}"
    return sanitized_filename


def generate_uuid_filename(original_filename: str) -> str:
    """Generate a new filename using a UUID while preserving the original extension.

    Args:
        original_filename (str): Source filename whose extension should be kept.

    Returns:
        str: A new filename of the form '{uuid}{ext}' where ext is from original_filename.
    """
    _, ext = os.path.splitext(original_filename)
    return f"{uuid.uuid4()}{ext}"


def generate_unique_filepath(directory: Path, base_filename: str, extension: str) -> Path:
    """Return a unique filepath in a directory by incrementing a numeric suffix.

    Starts with 'base_filename{extension}'. If that exists, tries
    'base_filename_1{extension}', 'base_filename_2{extension}', etc., until a
    non-existent path is found.

    Args:
        directory (Path): Target directory for the file path.
        base_filename (str): Base filename without extension.
        extension (str): File extension including leading dot (e.g., '.csv').

    Returns:
        Path: A path pointing to a filename not currently existing in 'directory'.

    Notes:
        - This function does not create the file; it only computes a unique path.
        - There is a potential race if another process creates the same path after
          this function returns; callers writing files should handle such races.
    """
    counter = 0
    unique_filename = f"{base_filename}{extension}"
    output_path = directory / unique_filename

    while output_path.exists():
        counter += 1
        unique_filename = f"{base_filename}_{counter}{extension}"
        output_path = directory / unique_filename
    return output_path


from typing import Optional, List, Tuple, Any

def is_pdf_header(file_path: str, read_size: int = 5, attempts: int = 1, delay: float = 0.0, logger: Optional[logging.Logger] = None) -> bool:
    """Check whether a file begins with the PDF magic bytes '%PDF-'.

    This utility centralizes the minimal PDF header check and supports an optional
    retry loop. It returns True if the first `read_size` bytes equal b'%PDF-'.

    Args:
        file_path (str): Path to the file to check.
        read_size (int): Number of bytes to read from the start of the file. Defaults to 5.
        attempts (int): Number of read attempts (for handling partial writes). Defaults to 1.
        delay (float): Delay in seconds between attempts. Defaults to 0.0.
        logger (logging.Logger | None): Optional logger to emit warnings. If None, uses module logger.

    Returns:
        bool: True if header matches b'%PDF-'; False otherwise.

    Notes:
        - Any I/O error during read will cause a retry (if attempts > 1) and a warning log.
        - This is a minimal validation and not a substitute for full PDF parsing.
    """
    mod_logger = logger or logging.getLogger(__name__)
    expected = b'%PDF-'
    for attempt in range(1, max(1, attempts) + 1):
        try:
            with open(file_path, 'rb') as f:
                header = f.read(read_size)
            if header == expected:
                return True
            else:
                mod_logger.warning(f"Attempt {attempt}: Invalid PDF header {header!r} in file {file_path}")
        except Exception as e:
            mod_logger.warning(f"Attempt {attempt}: Error reading file {file_path}: {e}")
        if attempt < attempts and delay > 0:
            time.sleep(delay)
    return False


def normalize_field_path(field: str, default_root: str = "data", allowed_roots: Optional[List[str]] = None) -> Tuple[str, bool]:
    """Normalize a field path by adding default root prefix for bare names.

    Args:
        field (str): The field name or path to normalize.
        default_root (str): The default root to prefix bare names with. Defaults to "data".
        allowed_roots (Optional[List[str]]): List of allowed root segments for validation.
            If provided and the explicit path's first segment is not in allowed_roots,
            still returns unchanged but marks as explicit.

    Returns:
        Tuple[str, bool]: A tuple containing:
            - normalized_path (str): The normalized field path
            - was_bare_name (bool): True if the original field was a bare name (no dots),
              False if it was an explicit path

    Raises:
        ValueError: If field is empty or not a string.

    Examples:
        >>> normalize_field_path("purchase_order_number")
        ("data.purchase_order_number", True)
        >>> normalize_field_path("data.purchase_order_number")
        ("data.purchase_order_number", False)
        >>> normalize_field_path("line_items.0.sku")
        ("data.line_items.0.sku", True)
    """
    if not isinstance(field, str):
        raise ValueError(f"Field must be a string, got {type(field).__name__}")

    if not field:
        raise ValueError("Field cannot be empty")

    # If field contains a dot, treat it as an explicit path
    if "." in field:
        # Optional validation: check if first segment is in allowed_roots
        if allowed_roots is not None:
            first_segment = field.split(".")[0]
            if first_segment not in allowed_roots:
                # Still return unchanged, but mark as explicit
                pass

        return field, False

    # If field contains no dot, prefix with default_root
    normalized_path = f"{default_root}.{field}"
    return normalized_path, True


def resolve_field(payload: dict, field_path: str) -> Tuple[Any, bool]:
    """Resolve a field value from a nested dict/list structure using dot notation.

    Args:
        payload (dict): The dictionary structure to navigate.
        field_path (str): Dot-separated path to the field (e.g., "data.items.0.sku").

    Returns:
        Tuple[Any, bool]: A tuple containing:
            - value (Any): The resolved value, or None if not found
            - exists (bool): True if the field exists, False otherwise

    Examples:
        >>> payload = {"data": {"po": "PO123"}}
        >>> resolve_field(payload, "data.po")
        ("PO123", True)
        >>> resolve_field(payload, "data.missing")
        (None, False)
        >>> payload = {"data": {"items": [{"sku": "X"}]}}
        >>> resolve_field(payload, "data.items.0.sku")
        ("X", True)
    """
    if not isinstance(payload, dict):
        return None, False

    if not field_path:
        return None, False

    current = payload
    segments = field_path.split(".")

    try:
        for segment in segments:
            if isinstance(current, dict):
                if segment not in current:
                    return None, False
                current = current[segment]
            elif isinstance(current, (list, tuple)):
                # Try to parse segment as integer index
                try:
                    index = int(segment)
                    if index < 0 or index >= len(current):
                        return None, False
                    current = current[index]
                except ValueError:
                    # Segment is not a valid integer index
                    return None, False
            else:
                # Current node is neither dict nor list/tuple
                return None, False

        return current, True

    except (KeyError, IndexError, TypeError):
        return None, False