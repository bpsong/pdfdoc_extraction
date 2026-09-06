"""Local interprocess ownership and reader/writer locks for upload storage."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import portalocker

from modules.config_protocol import ConfigProvider


class UploadStorageBusy(RuntimeError):
    """Another local process holds incompatible upload-storage access."""


@contextmanager
def _storage_lock(config: ConfigProvider, name: str, *, shared: bool) -> Iterator[None]:
    raw_root = config.get("watch_folder.processing_dir")
    if not raw_root:
        raise ValueError("watch_folder.processing_dir is required for upload storage locking")
    root = Path(str(raw_root)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Keep the file permanently: unlinking it could let two processes lock
    # different files at the same path. The OS releases locks after a crash.
    with (root / name).open("a+b") as handle:
        flags = portalocker.LOCK_SH if shared else portalocker.LOCK_EX
        try:
            portalocker.lock(handle, flags | portalocker.LOCK_NB)
        except portalocker.exceptions.LockException as exc:
            raise UploadStorageBusy(
                "Upload storage is in use by another operation or web process"
            ) from exc
        try:
            yield
        finally:
            portalocker.unlock(handle)


@contextmanager
def upload_storage_access(config: ConfigProvider, *, exclusive: bool = False) -> Iterator[None]:
    """Share access during submission; require exclusive access for reconciliation."""
    with _storage_lock(config, ".upload-storage.lock", shared=not exclusive):
        yield


@contextmanager
def web_process_ownership(config: ConfigProvider) -> Iterator[None]:
    """Enforce one serving web process for a local processing directory."""
    with _storage_lock(config, ".web-process.lock", shared=False):
        yield
