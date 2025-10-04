"""
Unit tests for YAML parser with location tracking.

Tests the YAMLParser class functionality including:
- Valid YAML parsing
- Invalid YAML error handling
- Root validation (must be mapping)
- Fallback behavior when ruamel.yaml is not available

All tests use in-memory content (loads method) - no file I/O.
"""

import sys
from collections.abc import MutableMapping
from pathlib import Path
from unittest.mock import patch

# Add the tools directory to the path so we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from tools.config_check.yaml_parser import YAMLParser


class TestYAMLParser:
    """Test cases for YAMLParser functionality."""

    def test_load_valid_yaml(self):
        """Test parsing valid YAML with mapping root."""
        parser = YAMLParser()

        valid_yaml = """
        web:
          upload_dir: "./web_upload"
        tasks:
          test_task:
            module: "test.module"
            class: "TestClass"
        pipeline:
          - test_task
        """

        data, error = parser.loads(valid_yaml, source="test1")

        assert error is None, f"Expected no error, got: {error}"
        assert data is not None, "Expected parsed data, got None"
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "web" in data
        assert "tasks" in data
        assert "pipeline" in data

    def test_load_invalid_yaml(self):
        """Test parsing malformed YAML reports error."""
        parser = YAMLParser()

        # YAML with syntax error (unclosed quote)
        invalid_yaml = """
        web:
          upload_dir: "./web_upload"
          invalid_indentation: "unclosed_quote
        tasks:
          test_task:
            module: "test.module"
        """

        data, error = parser.loads(invalid_yaml, source="test_invalid")

        assert data is None, "Expected None data for invalid YAML"
        assert error is not None, "Expected error message for invalid YAML"
        # Should contain either line/column info or "could not" (best-effort)
        error_lower = error.lower()
        assert "line" in error_lower or "column" in error_lower or "could not" in error_lower

    def test_root_not_mapping(self):
        """Test that YAML with non-mapping root reports error."""
        parser = YAMLParser()

        list_yaml = """
        - item1
        - item2
        - item3
        """

        data, error = parser.loads(list_yaml, source="test_list")

        assert data is None, "Expected None data for non-mapping root"
        assert error is not None, "Expected error message for non-mapping root"
        # Should indicate root must be a mapping
        assert "root must be a mapping" in error.lower() or "root element" in error.lower()

    def test_empty_content(self):
        """Test handling of empty or comment-only content."""
        parser = YAMLParser()

        empty_yaml = """
        # This is just a comment
        """

        data, error = parser.loads(empty_yaml, source="test_empty")

        assert data is None, "Expected None data for empty content"
        assert error is not None, "Expected error message for empty content"
        assert "empty" in error.lower() or "comment" in error.lower()

    def test_none_content(self):
        """Test handling of None/empty string content."""
        parser = YAMLParser()

        data, error = parser.loads("", source="test_none")

        assert data is None, "Expected None data for empty string"
        assert error is not None, "Expected error message for empty string"

    def test_ruamel_fallback_to_pyyaml(self):
        """Test that parser works when ruamel is not available (fallback to PyYAML)."""
        # Create parser that doesn't prefer ruamel (forces PyYAML)
        parser = YAMLParser(prefer_ruamel=False)

        valid_yaml = """
        web:
          upload_dir: "./web_upload"
        tasks:
          test_task:
            module: "test.module"
        """

        data, error = parser.loads(valid_yaml, source="test_fallback")

        assert error is None, f"Expected no error with PyYAML fallback, got: {error}"
        assert data is not None, "Expected parsed data with PyYAML fallback"
        assert isinstance(data, dict), f"Expected dict with PyYAML fallback, got {type(data)}"


    def test_accepts_mutable_mapping_root(self):
        'Test that non-dict mutable mappings are accepted as valid root.'
        parser = YAMLParser(prefer_ruamel=False)

        class DummyMapping(MutableMapping):
            def __init__(self, initial):
                self._data = dict(initial)

            def __getitem__(self, key):
                return self._data[key]

            def __setitem__(self, key, value):
                self._data[key] = value

            def __delitem__(self, key):
                del self._data[key]

            def __iter__(self):
                return iter(self._data)

            def __len__(self):
                return len(self._data)

        dummy_mapping = DummyMapping({'web': {'upload_dir': './web_upload'}})

        with patch('yaml.safe_load', return_value=dummy_mapping):
            data, error = parser.loads('ignored: value', source='test_mapping')

        assert error is None, f"Expected no error, got: {error}"
        assert data is dummy_mapping, 'Expected original mapping instance to be returned'


    def test_complex_valid_yaml(self):
        """Test parsing complex but valid YAML structure."""
        parser = YAMLParser()

        complex_yaml = """
        web:
          upload_dir: "./web_upload"
          port: 8080
        watch_folder:
          dir: "./watch"
          recursive: true
        tasks:
          extract_pdf:
            module: "standard_step.extraction.extract_pdf"
            class: "ExtractPdfTask"
            params:
              fields:
                supplier_name:
                  alias: "Supplier Name"
                  type: "str"
          store_json:
            module: "standard_step.storage.store_metadata_as_json"
            class: "StoreMetadataAsJsonTask"
            params:
              data_dir: "./output"
              filename: "{supplier_name}_metadata.json"
        pipeline:
          - extract_pdf
          - store_json
        """

        data, error = parser.loads(complex_yaml, source="test_complex")

        assert error is None, f"Expected no error, got: {error}"
        assert data is not None, "Expected parsed data"
        assert "web" in data
        assert "watch_folder" in data
        assert "tasks" in data
        assert "pipeline" in data
        assert len(data["pipeline"]) == 2



