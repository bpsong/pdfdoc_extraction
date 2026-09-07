"""Verify storage ownership with independent processes and real OS locks."""

from contextlib import contextmanager
import multiprocessing
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Iterator

import pytest

from modules.services.upload_storage_lock import (
    UploadStorageBusy, upload_storage_access, web_process_ownership,
)
from modules.services.upload_receiver import reconcile_upload_files


class Config:
    def __init__(self, root: str) -> None:
        self.root = root

    def get(self, key: str, default=None):
        return self.root if key == "watch_folder.processing_dir" else default


def _hold(root: str, kind: str, pipe) -> None:
    config = Config(root)
    lock = web_process_ownership(config) if kind == "web" else upload_storage_access(
        config, exclusive=kind == "cleanup"
    )
    with lock:
        pipe.send("locked")
        pipe.recv()


@contextmanager
def held_by_child(root: Path, kind: str) -> Iterator[BaseProcess]:
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_hold, args=(str(root), kind, child))
    process.start()
    child.close()
    try:
        assert parent.poll(15), "Child did not acquire lock"
        assert parent.recv() == "locked"
        yield process
    finally:
        if process.is_alive():
            parent.send("release")
            process.join(10)
        if process.is_alive():
            process.terminate()
            process.join(5)
        parent.close()


def test_uploads_share_access_but_block_cleanup(tmp_path: Path) -> None:
    config = Config(str(tmp_path))
    staged = tmp_path / ".upload_staging" / "active.upload"
    staged.parent.mkdir()
    staged.write_bytes(b"%PDF-active")
    with held_by_child(tmp_path, "upload"):
        with upload_storage_access(config):
            with pytest.raises(UploadStorageBusy):
                reconcile_upload_files(config)
            assert staged.exists()
    with upload_storage_access(config, exclusive=True):
        pass


def test_cleanup_blocks_uploads_and_other_cleanup(tmp_path: Path) -> None:
    config = Config(str(tmp_path))
    with held_by_child(tmp_path, "cleanup"):
        for exclusive in (False, True):
            with pytest.raises(UploadStorageBusy):
                with upload_storage_access(config, exclusive=exclusive):
                    pytest.fail("Conflicting storage access was allowed")


def test_second_web_process_is_rejected_and_crash_releases_ownership(tmp_path: Path) -> None:
    config = Config(str(tmp_path))
    with held_by_child(tmp_path, "web") as process:
        with pytest.raises(UploadStorageBusy):
            with web_process_ownership(config):
                pytest.fail("Second web owner was allowed")
        process.terminate()
        process.join(5)
        with web_process_ownership(config):
            pass
    assert (tmp_path / ".web-process.lock").exists()


def test_upload_crash_releases_storage_access(tmp_path: Path) -> None:
    with held_by_child(tmp_path, "upload") as process:
        process.terminate()
        process.join(5)
        with upload_storage_access(Config(str(tmp_path)), exclusive=True):
            pass
