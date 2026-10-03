"""Regression checks for visual-server startup and cleanup."""

import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import pytest

from test.helpers_visual import running_visual_server


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_noisy_startup_reaches_ready_and_is_reaped(tmp_path: Path) -> None:
    port = _free_port()
    script = (
        "import socket,sys,time; "
        "sys.stderr.buffer.write(b'x' * 131072); sys.stderr.flush(); "
        "s=socket.socket(); s.bind(('127.0.0.1', int(sys.argv[1]))); "
        "s.listen(); time.sleep(60)"
    )
    log_path = tmp_path / "server.log"
    with running_visual_server(
        [sys.executable, "-c", script, str(port)], cwd=tmp_path,
        env=os.environ.copy(), host="127.0.0.1", port=port,
        log_path=log_path, startup_timeout=10,
    ) as process:
        assert process.poll() is None
        assert log_path.stat().st_size >= 131072
    assert process.poll() is not None


def test_early_exit_reports_log_without_echoing_output(tmp_path: Path) -> None:
    sentinel = "SYNTHETIC_OUTPUT_MUST_STAY_IN_LOG"
    log_path = tmp_path / "server.log"
    with pytest.raises(RuntimeError, match="exited with code 7") as failure:
        with running_visual_server(
            [sys.executable, "-c", f"import sys; print('{sentinel}', file=sys.stderr); sys.exit(7)"],
            cwd=tmp_path, env=os.environ.copy(), host="127.0.0.1",
            port=_free_port(), log_path=log_path, startup_timeout=10,
        ):
            pytest.fail("Exited server must not become ready")
    assert sentinel not in str(failure.value)
    assert str(log_path) in str(failure.value)
    assert sentinel in log_path.read_text()


def test_timeout_reaps_the_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    processes: list[subprocess.Popen[bytes]] = []
    original_popen = subprocess.Popen

    def record_process(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr("test.helpers_visual.subprocess.Popen", record_process)
    with pytest.raises(RuntimeError, match="did not start within"):
        with running_visual_server(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=tmp_path, env=os.environ.copy(), host="127.0.0.1",
            port=_free_port(), log_path=tmp_path / "server.log", startup_timeout=0.2,
        ):
            pytest.fail("Unready server must not become ready")
    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_test_failure_reaps_a_ready_child(tmp_path: Path) -> None:
    port = _free_port()
    script = (
        "import socket,sys,time; s=socket.socket(); "
        "s.bind(('127.0.0.1',int(sys.argv[1]))); s.listen(); time.sleep(60)"
    )
    with pytest.raises(LookupError, match="Synthetic test failure"):
        with running_visual_server(
            [sys.executable, "-c", script, str(port)], cwd=tmp_path,
            env=os.environ.copy(), host="127.0.0.1", port=port,
            log_path=tmp_path / "server.log", startup_timeout=10,
        ) as process:
            raise LookupError("Synthetic test failure")
    assert process.poll() is not None
