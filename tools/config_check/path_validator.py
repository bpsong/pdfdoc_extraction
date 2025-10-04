"""Path validation logic for config-check.

This module provides comprehensive path validation capabilities specifically designed for
Windows environments, ensuring that all filesystem paths in configuration files are valid,
accessible, and properly formatted.

The path validator handles multiple types of path validation:
- Static directory paths (web.upload_dir)
- Watch folder paths (watch_folder.dir) with strict existence requirements
- Dynamic path discovery for any field ending in '_dir' or '_file'
- Windows-specific path resolution with proper separator handling

Key Features:
- Windows-compatible path resolution with UNC path support
- Environment variable expansion (e.g., %APPDATA%, $HOME)
- Relative path resolution against configurable base directory
- Comprehensive error reporting with specific path context
- Non-destructive validation (no filesystem modifications)
- Support for both absolute and relative path formats

Classes:
    PathIssue: Represents a single path validation finding with error code
    PathValidationResult: Aggregated result containing all path validation findings
    PathValidator: Main validation engine with Windows-specific path handling

Windows Compatibility:
    - Proper handling of Windows path separators (\\ and /)
    - Case-insensitive path comparisons where appropriate
    - Support for Windows drive letters and UNC paths
    - Expansion of Windows environment variables
    - Proper resolution of relative paths on Windows filesystems

Note:
    All path operations are performed safely without modifying the filesystem.
    The validator uses pathlib for cross-platform compatibility while maintaining
    Windows-specific behavior requirements.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass(slots=True)
class PathIssue:
    """Represents a single path validation finding."""

    path: str
    message: str
    code: str = "path"
    details: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class PathValidationResult:
    """Aggregated path validation findings."""

    errors: List[PathIssue]
    warnings: List[PathIssue]


class PathValidator:
    """Validate configuration paths without mutating the filesystem."""

    STATIC_DIR_KEYS = ("web.upload_dir",)
    WATCH_DIR_KEY = "watch_folder.dir"

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else None

    def validate(self, config: Dict[str, Any]) -> PathValidationResult:
        errors: List[PathIssue] = []
        warnings: List[PathIssue] = []

        errors.extend(self._validate_static_paths(config))
        errors.extend(self._validate_watch_folder(config))
        errors.extend(self._validate_dynamic_paths(config))

        return PathValidationResult(errors=errors, warnings=warnings)

    def _validate_static_paths(self, config: Dict[str, Any]) -> List[PathIssue]:
        findings: List[PathIssue] = []
        for key in self.STATIC_DIR_KEYS:
            value = self._get_nested_value(config, key)
            findings.extend(self._validate_directory_value(value, key))
        return findings

    def _validate_watch_folder(self, config: Dict[str, Any]) -> List[PathIssue]:
        findings: List[PathIssue] = []
        value = self._get_nested_value(config, self.WATCH_DIR_KEY)
        if value is None:
            findings.append(
                PathIssue(
                    path=self.WATCH_DIR_KEY,
                    message="watch_folder.dir is required and must point to an existing directory",
                    code="watch-folder-missing-dir",
                    details={"config_key": self.WATCH_DIR_KEY},
                )
            )
            return findings

        issues = self._validate_directory_value(
            value,
            self.WATCH_DIR_KEY,
            allow_creation=False,
            missing_message="watch_folder.dir directory does not exist",
        )

        for issue in issues:
            issue.details = issue.details or {"config_key": self.WATCH_DIR_KEY}
            issue.details.setdefault("config_key", self.WATCH_DIR_KEY)
            if issue.code == "path-missing-dir":
                issue.code = "watch-folder-missing-dir"
                issue.message = "watch_folder.dir directory does not exist"
        findings.extend(issues)
        return findings

    def _validate_dynamic_paths(self, config: Dict[str, Any]) -> List[PathIssue]:
        findings: List[PathIssue] = []

        def _walk(node: Any, trace: str = "") -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    current = f"{trace}.{key}".lstrip(".")
                    lowered_key = key.lower()
                    if current in {self.WATCH_DIR_KEY, *self.STATIC_DIR_KEYS}:
                        # Already handled by dedicated checks
                        pass
                    elif lowered_key.endswith("_dir"):
                        findings.extend(self._validate_directory_value(value, current))
                    elif lowered_key.endswith("_file"):
                        findings.extend(self._validate_file_value(value, current))

                    if isinstance(value, (dict, list)):
                        _walk(value, current)
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    _walk(item, f"{trace}[{index}]")

        _walk(config)
        return findings

    def _validate_directory_value(
        self,
        value: Any,
        config_path: str,
        *,
        allow_creation: bool = False,
        missing_message: Optional[str] = None,
    ) -> List[PathIssue]:
        findings: List[PathIssue] = []

        resolved, error_code, error_message = self._resolve_path(value)
        if error_code:
            details = {"config_key": config_path}
            if resolved is not None:
                details["path"] = str(resolved)
            findings.append(
                PathIssue(
                    path=config_path,
                    message=error_message or "Invalid path value",
                    code=error_code,
                    details=details,
                )
            )
            return findings

        assert resolved is not None  # For type checkers

        if not resolved.exists():
            if allow_creation:
                return findings
            message = missing_message or f"Directory does not exist: {resolved}"
            findings.append(
                PathIssue(
                    path=config_path,
                    message=message,
                    code="path-missing-dir",
                    details={"path": str(resolved), "config_key": config_path},
                )
            )
        elif not resolved.is_dir():
            findings.append(
                PathIssue(
                    path=config_path,
                    message=f"Expected directory but found file: {resolved}",
                    code="path-not-dir",
                    details={"path": str(resolved), "config_key": config_path},
                )
            )
        return findings

    def _validate_file_value(self, value: Any, config_path: str) -> List[PathIssue]:
        findings: List[PathIssue] = []
        resolved, error_code, error_message = self._resolve_path(value)
        if error_code:
            details = {"config_key": config_path}
            if resolved is not None:
                details["path"] = str(resolved)
            findings.append(
                PathIssue(
                    path=config_path,
                    message=error_message or "Invalid path value",
                    code=error_code,
                    details=details,
                )
            )
            return findings

        assert resolved is not None

        if not resolved.exists():
            findings.append(
                PathIssue(
                    path=config_path,
                    message=f"File does not exist: {resolved}",
                    code="path-missing-file",
                    details={"path": str(resolved), "config_key": config_path},
                )
            )
        elif not resolved.is_file():
            findings.append(
                PathIssue(
                    path=config_path,
                    message=f"Expected file but found directory: {resolved}",
                    code="path-not-file",
                    details={"path": str(resolved), "config_key": config_path},
                )
            )
        return findings

    def _resolve_path(
        self, raw_value: Any
    ) -> tuple[Optional[Path], Optional[str], Optional[str]]:
        if raw_value is None:
            return None, "path-value-missing", "Path value is missing"
        if not isinstance(raw_value, str):
            return None, "path-value-type", "Path value must be a string"

        candidate = raw_value.strip()
        if not candidate:
            return None, "path-value-empty", "Path value must not be empty"

        expanded = os.path.expandvars(candidate)
        path = Path(expanded).expanduser()

        base = self.base_dir or Path.cwd()
        if not path.is_absolute():
            path = (base / path).resolve(strict=False)
        else:
            path = path.resolve(strict=False)

        return path, None, None

    @staticmethod
    def _get_nested_value(config: Dict[str, Any], key_path: str) -> Any:
        parts = key_path.split('.')
        current: Any = config
        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current
