from __future__ import annotations

from importlib.metadata import version

from packaging.version import Version


def test_starlette_version_includes_windows_staticfiles_unc_fix() -> None:
    """Guard against Starlette versions affected by GHSA-wqp7-x3pw-xc5r."""
    assert Version(version("starlette")) >= Version("1.1.0")
