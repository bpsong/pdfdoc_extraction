"""Bounded subprocess lifecycle for isolated visual-test servers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import socket
import subprocess
import time
from typing import Iterator, Mapping


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    """Reap the child on success, startup failure, or test failure."""
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


@contextmanager
def running_visual_server(
    command: list[str], *, cwd: Path, env: Mapping[str, str],
    host: str, port: int, log_path: Path, startup_timeout: float = 60,
) -> Iterator[subprocess.Popen[bytes]]:
    """Wait for a server without blocking its diagnostic output.

    Send stdout and stderr to a file rather than an unread pipe. Failure
    messages identify the log without copying potentially sensitive output
    or the child environment into the pytest traceback.
    """
    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=log_file, stderr=log_file,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + startup_timeout
            while time.monotonic() < deadline:
                return_code = process.poll()
                if return_code is not None:
                    raise RuntimeError(
                        f"Visual test server exited with code {return_code}; "
                        f"startup log: {log_path}"
                    )
                try:
                    with socket.create_connection((host, port), timeout=0.5):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(
                    f"Visual test server did not start within {startup_timeout:g}s; "
                    f"startup log: {log_path}"
                )
            yield process
        finally:
            _stop_process(process)
