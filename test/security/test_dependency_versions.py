from __future__ import annotations

import subprocess
import sys
from importlib.metadata import version

from packaging.version import Version


def test_starlette_version_includes_windows_staticfiles_unc_fix() -> None:
    """Guard against Starlette versions affected by GHSA-wqp7-x3pw-xc5r."""
    assert Version(version("starlette")) >= Version("1.1.0")


def test_fastapi_testclient_import_has_no_deprecation_warning() -> None:
    """Require Starlette's preferred test-client transport dependency."""
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-c",
            "from fastapi.testclient import TestClient",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
