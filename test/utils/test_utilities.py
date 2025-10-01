"""Merged tests for utility helper functions (field path helpers + PDF header tests)."""

import builtins
from io import BytesIO
import pytest
import logging
from typing import Any, cast
from modules import utils
from modules.utils import normalize_field_path, resolve_field


def _make_open_mock(data: bytes):
    def _open(file, mode='rb'):
        # Return a file-like object supporting read() and __enter__/__exit__
        bio = BytesIO(data)
        class Ctx:
            def __enter__(self):
                return bio
            def __exit__(self, exc_type, exc, tb):
                return False
        return Ctx()
    return _open


# Field Path Helpers Tests
class TestNormalizeFieldPath:
    """Test cases for normalize_field_path function."""

    def test_normalize_bare_name(self):
        """Test that bare names get prefixed with default root."""
        result, was_bare = normalize_field_path("purchase_order_number")
        assert result == "data.purchase_order_number"
        assert was_bare is True

    def test_normalize_explicit_path(self):
        """Test that explicit paths are returned unchanged."""
        result, was_bare = normalize_field_path("data.purchase_order_number")
        assert result == "data.purchase_order_number"
        assert was_bare is False

    def test_normalize_nested_array(self):
        """Test that paths with numeric segments work correctly."""
        result, was_bare = normalize_field_path("line_items.0.sku")
        assert result == "line_items.0.sku"  # Should be treated as explicit path due to dots
        assert was_bare is False

    def test_empty_field_raises_value_error(self):
        """Test that empty field raises ValueError."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            normalize_field_path("")

    def test_non_string_field_raises_value_error(self):
        """Test that non-string field raises ValueError."""
        with pytest.raises(ValueError, match="Field must be a string"):
            normalize_field_path(cast(Any, 123))

    def test_with_custom_default_root(self):
        """Test with custom default root."""
        result, was_bare = normalize_field_path("field_name", default_root="metadata")
        assert result == "metadata.field_name"
        assert was_bare is True

    def test_with_allowed_roots_validation(self):
        """Test with allowed_roots parameter."""
        allowed = ["data", "metadata"]
        # Valid root should work
        result, was_bare = normalize_field_path("data.field", allowed_roots=allowed)
        assert result == "data.field"
        assert was_bare is False

        # Invalid root should still return unchanged
        result, was_bare = normalize_field_path("invalid.field", allowed_roots=allowed)
        assert result == "invalid.field"
        assert was_bare is False


class TestResolveField:
    """Test cases for resolve_field function."""

    def test_resolve_field_existing(self):
        """Test resolving an existing field."""
        payload = {"data": {"po": "PO123"}}
        value, exists = resolve_field(payload, "data.po")
        assert value == "PO123"
        assert exists is True

    def test_resolve_field_missing(self):
        """Test resolving a missing field."""
        payload = {"data": {"po": "PO123"}}
        value, exists = resolve_field(payload, "data.missing")
        assert value is None
        assert exists is False

    def test_resolve_array_index(self):
        """Test resolving array index."""
        payload = {"data": {"items": [{"sku": "X"}]}}
        value, exists = resolve_field(payload, "data.items.0.sku")
        assert value == "X"
        assert exists is True

    def test_invalid_inputs(self):
        """Test with invalid inputs."""
        # Non-dict payload
        value, exists = resolve_field(cast(Any, "not a dict"), "field")
        assert value is None
        assert exists is False

        # Empty field path
        payload = {"data": {"field": "value"}}
        value, exists = resolve_field(payload, "")
        assert value is None
        assert exists is False

    def test_array_index_out_of_range(self):
        """Test array index out of range."""
        payload = {"data": {"items": [{"sku": "X"}]}}
        value, exists = resolve_field(payload, "data.items.1.sku")
        assert value is None
        assert exists is False

    def test_invalid_array_index(self):
        """Test invalid array index (non-integer)."""
        payload = {"data": {"items": [{"sku": "X"}]}}
        value, exists = resolve_field(payload, "data.items.invalid.sku")
        assert value is None
        assert exists is False

    def test_deeply_nested_path(self):
        """Test deeply nested path resolution."""
        payload = {
            "data": {
                "order": {
                    "line_items": [
                        {
                            "product": {
                                "details": {
                                    "sku": "ABC123"
                                }
                            }
                        }
                    ]
                }
            }
        }
        value, exists = resolve_field(payload, "data.order.line_items.0.product.details.sku")
        assert value == "ABC123"
        assert exists is True

    def test_missing_intermediate_key(self):
        """Test missing intermediate key in path."""
        payload = {"data": {"existing": "value"}}
        value, exists = resolve_field(payload, "data.missing.intermediate.field")
        assert value is None
        assert exists is False


# PDF Header Tests
def test_is_pdf_header_valid(monkeypatch, caplog):
    # Simulate a file that starts with b'%PDF-'
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(builtins, "open", _make_open_mock(b"%PDF-1.7 rest"))
    assert utils.is_pdf_header("dummy.pdf") is True
    # No warning should be emitted for valid header
    assert not any("Invalid PDF header" in r.message for r in caplog.records)

def test_is_pdf_header_invalid(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(builtins, "open", _make_open_mock(b"NOTPDFDATA"))
    assert utils.is_pdf_header("dummy.pdf", read_size=5, attempts=1) is False
    # Should have logged a warning about invalid header
    assert any("Invalid PDF header" in r.message for r in caplog.records)

def test_is_pdf_header_retries_on_ioerror(monkeypatch, caplog):
    # Simulate open raising an IOError on first two attempts, then returning a valid header
    calls = {"count": 0}
    def open_side_effect(path, mode='rb'):
        calls["count"] += 1
        if calls["count"] < 3:
            raise IOError("temporary failure")
        return _make_open_mock(b"%PDF-1.5 rest")(path, mode)
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(builtins, "open", open_side_effect)
    # attempts=3 should allow it to succeed on the 3rd attempt
    assert utils.is_pdf_header("dummy.pdf", read_size=5, attempts=3, delay=0.0) is True
    # Ensure we logged the I/O errors as warnings
    assert any("Error reading file" in r.message for r in caplog.records)

def test_is_pdf_header_handles_exceptions(monkeypatch, caplog):
    # Simulate open always raising an exception
    def open_fail(path, mode='rb'):
        raise ValueError("boom")
    monkeypatch.setattr(builtins, "open", open_fail)
    caplog.set_level(logging.WARNING)
    assert utils.is_pdf_header("dummy.pdf", read_size=5, attempts=2, delay=0.0) is False
    assert any("Error reading file" in r.message for r in caplog.records)