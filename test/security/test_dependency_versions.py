from __future__ import annotations

from importlib.metadata import version

from packaging.version import Version


def test_starlette_version_includes_range_header_dos_fix() -> None:
    """Guard against reintroducing Starlette versions affected by CVE-2025-62727."""
    assert Version(version("starlette")) >= Version("0.49.1")
