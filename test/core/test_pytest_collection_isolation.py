"""Collection must not read or initialize the developer's deployment."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("existing", [False, True])
def test_collection_ignores_external_config(tmp_path: Path, existing: bool) -> None:
    """Even invalid or missing CONFIG_PATH input cannot affect test imports."""
    external = tmp_path / "deployment.yaml"
    invalid = "invalid: [synthetic-private-marker\n"
    if existing:
        external.write_text(invalid, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--tb=short",
         "test/integration/test_new_ui_routes.py"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "CONFIG_PATH": str(external)},
        capture_output=True, text=True, timeout=60, check=False,
    )
    # Do not include subprocess output: third-party diagnostics may be sensitive.
    assert result.returncode == 0
    assert "tests collected" in result.stdout
    assert external.exists() is existing
    if existing:
        assert external.read_text(encoding="utf-8") == invalid
