"""
YAML Parser with location tracking for config-check CLI tool.

This module provides a YAMLParser class that can parse YAML files with location
information using ruamel.yaml when available, falling back to PyYAML otherwise.
Designed for the Windows environment with proper path handling.

Future enhancements under consideration include location-backed node lookups
and ruamel round-trip preservation for richer suggestion context.
"""

import logging
from collections.abc import MutableMapping as MutableMappingABC
from pathlib import Path
from typing import Any, MutableMapping, Optional, Tuple

logger = logging.getLogger("config_check.yaml_parser")


class YAMLParser:
    """
    YAML parser with location tracking and graceful fallback handling.

    Uses ruamel.yaml for enhanced location information when available,
    otherwise falls back to PyYAML with best-effort error reporting.
    """

    def __init__(self, prefer_ruamel: bool = True) -> None:
        """
        Initialize the YAML parser with library preference.

        Args:
            prefer_ruamel: Whether to prefer ruamel.yaml for location tracking
        """
        self.prefer_ruamel = prefer_ruamel
        self._yaml_loader = None
        self._use_ruamel = False

        # Try to initialize ruamel.yaml first if preferred
        if prefer_ruamel:
            self._init_ruamel()
        else:
            self._init_pyyaml()

    def _init_ruamel(self) -> None:
        """Initialize ruamel.yaml parser if available."""
        try:
            import ruamel.yaml
            self._yaml_loader = ruamel.yaml.YAML()
            self._use_ruamel = True
            logger.debug("Using ruamel.yaml for enhanced location tracking")
        except ImportError:
            logger.debug("ruamel.yaml not available, falling back to PyYAML")
            self._init_pyyaml()

    def _init_pyyaml(self) -> None:
        """Initialize PyYAML parser as fallback."""
        try:
            import yaml
            self._yaml_loader = yaml
            self._use_ruamel = False
            logger.debug("Using PyYAML for YAML parsing")
        except ImportError as e:
            raise ImportError("Neither ruamel.yaml nor PyYAML is available. Install one of them to use YAML parsing.") from e

    def load(self, path: str) -> Tuple[Optional[MutableMapping[str, Any]], Optional[str]]:
        """
        Parse YAML file at given path.

        Args:
            path: Path to the YAML file (relative or absolute)

        Returns:
            Tuple of (data, error_message):
            - On success: (parsed_dict, None)
            - On error: (None, error_message_with_location)
        """
        try:
            # Resolve to absolute path for consistent error reporting
            resolved_path = Path(path).resolve()

            if self._use_ruamel:
                return self._load_with_ruamel(str(resolved_path))
            else:
                return self._load_with_pyyaml(str(resolved_path))

        except Exception as e:
            return None, f"Failed to read file '{Path(path).resolve()}': {e}"

    def loads(self, content: str, source: str = "<string>") -> Tuple[Optional[MutableMapping[str, Any]], Optional[str]]:
        """
        Parse YAML from string content.

        Args:
            content: YAML content as string
            source: Source identifier for error reporting

        Returns:
            Tuple of (data, error_message):
            - On success: (parsed_dict, None)
            - On error: (None, error_message_with_location)
        """
        try:
            if self._use_ruamel:
                return self._loads_with_ruamel(content, source)
            else:
                return self._loads_with_pyyaml(content, source)

        except Exception as e:
            return None, f"Failed to parse YAML from {source}: {e}"

    def _load_with_ruamel(self, path: str) -> Tuple[Optional[MutableMapping[str, Any]], Optional[str]]:
        """Load YAML file using ruamel.yaml."""
        import ruamel.yaml

        try:
            with open(path, 'r', encoding='utf-8') as f:
                # Use type: ignore to suppress Pylance warnings for dynamic attribute access
                data = self._yaml_loader.load(f)  # type: ignore

            # Validate root is a mapping
            if data is None:
                return None, f"File '{path}' is empty or contains only comments"
            elif not isinstance(data, MutableMappingABC):
                # Try to get location info for error reporting
                try:
                    # Re-parse to get location information for error
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return self._loads_with_ruamel(content, path)
                except Exception:
                    return None, f"Root element in '{path}' must be a mapping (dictionary), got {type(data).__name__}"

            return data, None

        except ruamel.yaml.YAMLError as e:
            # Use getattr with fallback for problem attribute
            line = getattr(e, 'line', 'unknown')
            column = getattr(e, 'column', 'unknown')
            problem = getattr(e, 'problem', str(e))
            return None, f"YAML parse error in '{path}' at line {line}, column {column}: {problem}"
        except Exception as e:
            return None, f"Error reading '{path}': {e}"

    def _load_with_pyyaml(self, path: str) -> Tuple[Optional[MutableMapping[str, Any]], Optional[str]]:
        """Load YAML file using PyYAML."""
        import yaml

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            # Validate root is a mapping
            if data is None:
                return None, f"File '{path}' is empty or contains only comments"
            elif not isinstance(data, MutableMappingABC):
                return None, f"Root element in '{path}' must be a mapping (dictionary), got {type(data).__name__}"

            return data, None

        except yaml.YAMLError as e:
            return None, f"YAML parse error in '{path}': {e}"
        except Exception as e:
            return None, f"Error reading '{path}': {e}"

    def _loads_with_ruamel(self, content: str, source: str) -> Tuple[Optional[MutableMapping[str, Any]], Optional[str]]:
        """Load YAML from string using ruamel.yaml."""
        import ruamel.yaml
        from io import StringIO

        try:
            # Use type: ignore to suppress Pylance warnings for dynamic attribute access
            data = self._yaml_loader.load(StringIO(content))  # type: ignore

            # Validate root is a mapping
            if data is None:
                return None, f"Content '{source}' is empty or contains only comments"
            elif not isinstance(data, MutableMappingABC):
                return None, f"Root element in '{source}' must be a mapping (dictionary), got {type(data).__name__}"

            return data, None

        except ruamel.yaml.YAMLError as e:
            line = getattr(e, 'line', 'unknown')
            column = getattr(e, 'column', 'unknown')
            # Use getattr with fallback for problem attribute
            problem = getattr(e, 'problem', str(e))
            return None, f"YAML parse error in '{source}' at line {line}, column {column}: {problem}"
        except Exception as e:
            return None, f"Error parsing YAML from '{source}': {e}"

    def _loads_with_pyyaml(self, content: str, source: str) -> Tuple[Optional[MutableMapping[str, Any]], Optional[str]]:
        """Load YAML from string using PyYAML."""
        import yaml
        from io import StringIO

        try:
            data = yaml.safe_load(StringIO(content))

            # Validate root is a mapping
            if data is None:
                return None, f"Content '{source}' is empty or contains only comments"
            elif not isinstance(data, MutableMappingABC):
                return None, f"Root element in '{source}' must be a mapping (dictionary), got {type(data).__name__}"

            return data, None

        except yaml.YAMLError as e:
            return None, f"YAML parse error in '{source}': {e}"
        except Exception as e:
            return None, f"Error parsing YAML from '{source}': {e}"