"""Bounded multipart receiving for web-upload requests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
import asyncio
import logging
import sqlite3
from threading import Lock
from typing import AsyncGenerator, AsyncIterator, Awaitable, Callable
import uuid

import anyio
from fastapi import HTTPException, Request, status
from starlette.datastructures import FormData, Headers, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from python_multipart.exceptions import MultipartParseError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request as StarletteRequest

from ..config_manager import ConfigManager
from ..db.connection import connect
from .upload_storage_lock import upload_storage_access

MIB = 1024 * 1024
MAX_SCALAR_BYTES = 4096
MAX_FORM_FIELDS = 10
MAX_PART_HEADER_BYTES = 16 * 1024
MAX_PART_HEADERS = 16
COPY_CHUNK_BYTES = 1024 * 1024
logger = logging.getLogger(__name__)


class _UploadMultipartParser(MultiPartParser):
    """Bound headers before buffering and require a complete multipart message."""

    def __init__(
        self, headers: Headers, stream: AsyncGenerator[bytes, None], limits: UploadLimits
    ) -> None:
        super().__init__(
            headers, stream, max_files=limits.max_files,
            max_fields=MAX_FORM_FIELDS, max_part_size=MAX_SCALAR_BYTES,
        )
        self._header_bytes = 0
        self._header_count = 0
        self._complete = False

    def on_part_begin(self) -> None:
        self._header_bytes = 0
        self._header_count = 0
        super().on_part_begin()

    def _count_header_bytes(self, size: int) -> None:
        self._header_bytes += size
        if self._header_bytes > MAX_PART_HEADER_BYTES:
            raise HTTPException(status_code=413, detail="Multipart headers are too large")

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._count_header_bytes(end - start)
        super().on_header_field(data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._count_header_bytes(end - start)
        super().on_header_value(data, start, end)

    def on_header_end(self) -> None:
        self._header_count += 1
        if self._header_count > MAX_PART_HEADERS:
            raise HTTPException(status_code=413, detail="Too many multipart headers")
        super().on_header_end()

    def on_end(self) -> None:
        self._complete = True
        super().on_end()

    async def parse(self) -> FormData:
        accepted = False
        try:
            form = await super().parse()
            if not self._complete:
                raise HTTPException(status_code=400, detail="Incomplete multipart upload")
            accepted = True
            return form
        except MultiPartException as exc:
            raise HTTPException(status_code=400, detail=exc.message) from exc
        except MultipartParseError as exc:
            raise HTTPException(status_code=400, detail="Invalid multipart upload") from exc
        finally:
            if not accepted:
                # Starlette only closes these for selected parser errors. Include
                # incomplete messages and our early header-limit rejections too.
                for spool in self._files_to_close_on_error:
                    spool.close()


@asynccontextmanager
async def _upload_form(request: StarletteRequest, limits: UploadLimits) -> AsyncIterator[FormData]:
    parser = _UploadMultipartParser(request.headers, request.stream(), limits)
    form = await parser.parse()
    try:
        yield form
    finally:
        with anyio.CancelScope(shield=True):
            await form.close()


@dataclass(frozen=True)
class UploadLimits:
    """Effective limits for one multipart upload request."""

    max_file_bytes: int
    max_files: int
    max_request_bytes: int
    max_concurrent_uploads: int


@dataclass(frozen=True)
class StagedUpload:
    """One received file stored in application-owned staging."""

    filename: str
    content_type: str
    path: Path
    size_bytes: int


@dataclass(frozen=True)
class ReceivedUploadBatch:
    """Validated multipart metadata and staged file references."""

    pipeline_version_id: str
    files: tuple[StagedUpload, ...]


@dataclass(frozen=True)
class UploadReconciliationResult:
    """Counts from one safe upload-file startup reconciliation."""

    staging_removed: int
    orphaned_final_removed: int
    cleanup_failures: int


class UploadAdmissionController:
    """Bound concurrent upload receivers within one web process."""

    def __init__(self) -> None:
        self._active = 0
        self._lock = Lock()

    @asynccontextmanager
    async def admit(self, capacity: int) -> AsyncIterator[None]:
        """Admit immediately or return a retryable capacity response."""
        with self._lock:
            if self._active >= capacity:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Upload capacity is temporarily full. Try again shortly.",
                    headers={"Retry-After": "1"},
                )
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1


def _positive_int(config: ConfigManager, key: str, default: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def upload_limits(config: ConfigManager) -> UploadLimits:
    """Resolve upload limits from deployment configuration."""
    return UploadLimits(
        max_file_bytes=_positive_int(config, "web.max_upload_mb", 50) * MIB,
        max_files=_positive_int(config, "web.max_upload_files", 20),
        max_request_bytes=_positive_int(
            config, "web.max_upload_request_mb", 200
        )
        * MIB,
        max_concurrent_uploads=_positive_int(
            config, "web.max_concurrent_uploads", 2
        ),
    )


def reject_large_content_length(request: Request, limits: UploadLimits) -> None:
    """Reject a declared oversized request before consuming its body."""
    value = request.headers.get("content-length")
    if value is None:
        return
    try:
        content_length = int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Content-Length header") from exc
    if content_length < 0:
        raise HTTPException(status_code=400, detail="Invalid Content-Length header")
    if content_length > limits.max_request_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Upload request is too large.",
        )


def _counting_receive(
    request: Request, max_request_bytes: int, idle_seconds: int = 30
) -> Callable[[], Awaitable[dict]]:
    received = 0

    async def receive() -> dict:
        nonlocal received
        try:
            message = await asyncio.wait_for(request.receive(), timeout=idle_seconds)
        except TimeoutError as exc:
            raise HTTPException(status_code=408, detail="Upload stalled; please retry") from exc
        if message.get("type") == "http.request":
            received += len(message.get("body", b""))
            if received > max_request_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Upload request is too large.",
                )
        return message

    return receive


async def _remove_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            await anyio.Path(path).unlink(missing_ok=True)
        except OSError:
            # The route logs final cleanup failures with request context.
            pass


async def _remove_paths_after_cancellation(paths: list[Path]) -> None:
    """Finish staging cleanup even when the request task is cancelled."""
    with anyio.CancelScope(shield=True):
        await _remove_paths(paths)


async def receive_multipart_upload(
    request: Request,
    config: ConfigManager,
    admission: UploadAdmissionController | None = None,
    *,
    staging_root: Path | None = None,
) -> ReceivedUploadBatch:
    """Bound total receiving and staging time, including slow trickle requests."""
    try:
        async with asyncio.timeout(_positive_int(config, "web.upload_timeout_seconds", 600)):
            return await _receive_multipart_upload(
                request, config, admission, staging_root=staging_root
            )
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail="Upload deadline exceeded; please retry") from exc


async def _receive_multipart_upload(
    request: Request,
    config: ConfigManager,
    admission: UploadAdmissionController | None = None,
    *,
    staging_root: Path | None = None,
) -> ReceivedUploadBatch:
    """Stream multipart input through spooled files into upload staging."""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        raise HTTPException(status_code=400, detail="Unsupported content type")

    limits = upload_limits(config)
    reject_large_content_length(request, limits)
    upload_dir = str(config.get("web.upload_dir") or "")
    if not upload_dir:
        raise HTTPException(status_code=500, detail="Upload directory misconfigured")
    staging_dir = (
        staging_root.resolve()
        if staging_root is not None
        else Path(upload_dir).resolve() / ".staging"
    )
    await anyio.Path(staging_dir).mkdir(parents=True, exist_ok=True)
    staged_paths: list[Path] = []

    @asynccontextmanager
    async def admitted() -> AsyncIterator[None]:
        if admission is None:
            yield
        else:
            async with admission.admit(limits.max_concurrent_uploads):
                yield

    async with admitted():
        bounded_request = StarletteRequest(
            request.scope,
            receive=_counting_receive(
                request, limits.max_request_bytes,
                _positive_int(config, "web.upload_idle_timeout_seconds", 30),
            ),
        )
        try:
            async with _upload_form(bounded_request, limits) as form:
                selections = form.getlist("pipeline_version_id")
                if len(selections) != 1 or not isinstance(selections[0], str):
                    raise HTTPException(
                        status_code=400,
                        detail="Exactly one pipeline_version_id is required",
                    )
                pipeline_version_id = selections[0].strip()
                if not pipeline_version_id or len(pipeline_version_id.encode()) > MAX_SCALAR_BYTES:
                    raise HTTPException(
                        status_code=400,
                        detail="Exactly one pipeline_version_id is required",
                    )

                file_parts = [
                    value
                    for key, value in form.multi_items()
                    if key in {"files", "file"} and isinstance(value, UploadFile)
                ]
                unsupported_file_fields = {
                    key
                    for key, value in form.multi_items()
                    if isinstance(value, UploadFile) and key not in {"files", "file"}
                }
                if unsupported_file_fields:
                    raise HTTPException(
                        status_code=400,
                        detail="Unsupported file field provided",
                    )
                if not file_parts:
                    raise HTTPException(status_code=400, detail="No file field provided")

                staged: list[StagedUpload] = []
                for upload in file_parts:
                    size = int(upload.size or 0)
                    if size > limits.max_file_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail=f"{upload.filename or 'uploaded_file'} is too large.",
                        )
                    target = staging_dir / f"{uuid.uuid4()}.upload"
                    staged_paths.append(target)
                    await upload.seek(0)
                    async with await anyio.open_file(target, "xb") as output:
                        copied = 0
                        while chunk := await upload.read(COPY_CHUNK_BYTES):
                            copied += len(chunk)
                            if copied > limits.max_file_bytes:
                                raise HTTPException(
                                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                                    detail=f"{upload.filename or 'uploaded_file'} is too large.",
                                )
                            await output.write(chunk)
                    staged.append(
                        StagedUpload(
                            filename=upload.filename or "uploaded_file",
                            content_type=upload.content_type or "application/octet-stream",
                            path=target,
                            size_bytes=copied,
                        )
                    )
                return ReceivedUploadBatch(
                    pipeline_version_id=pipeline_version_id,
                    files=tuple(staged),
                )
        except StarletteHTTPException as exc:
            await _remove_paths(staged_paths)
            if str(exc.detail).startswith("Too many files"):
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Too many files uploaded. Maximum file count is {limits.max_files}.",
                ) from exc
            raise
        except asyncio.CancelledError:
            await _remove_paths_after_cancellation(staged_paths)
            raise
        except Exception:
            await _remove_paths(staged_paths)
            raise


def reconcile_upload_files(config: ConfigManager) -> UploadReconciliationResult:
    """Remove upload-owned files left unreferenced by an interrupted web process."""
    processing_dir = str(config.get("watch_folder.processing_dir") or "")
    if not processing_dir:
        return UploadReconciliationResult(0, 0, 0)
    with upload_storage_access(config, exclusive=True):
        return _reconcile_locked_upload_files(config, processing_dir)


def _reconcile_locked_upload_files(
    config: ConfigManager, processing_dir: str
) -> UploadReconciliationResult:
    """Keep the reference snapshot and deletions inside one exclusive lock."""
    processing_root = Path(processing_dir).resolve()
    staging_dir = processing_root / ".upload_staging"

    # Resolve durable references before deleting anything. If SQLite cannot be
    # checked, reconciliation fails closed and leaves every file untouched.
    with connect(config) as conn:
        rows = conn.execute(
            """
            SELECT file_path FROM documents
            UNION
            SELECT file_path FROM document_files
            """
        ).fetchall()
    referenced = {
        str(Path(str(row["file_path"])).resolve()).casefold()
        for row in rows
        if row["file_path"]
    }

    staging_removed = 0
    orphaned_final_removed = 0
    cleanup_failures = 0
    candidates = (
        list(staging_dir.glob("*.upload")) if staging_dir.is_dir() else []
    )
    for path in candidates:
        try:
            path.unlink()
            staging_removed += 1
        except OSError:
            cleanup_failures += 1
            logger.warning("Unable to remove abandoned upload staging file: %s", path)

    if processing_root.is_dir():
        for path in processing_root.glob("web-upload-*.pdf"):
            if str(path.resolve()).casefold() in referenced:
                continue
            try:
                path.unlink()
                orphaned_final_removed += 1
            except OSError:
                cleanup_failures += 1
                logger.warning("Unable to remove orphaned finalized upload: %s", path)

    return UploadReconciliationResult(
        staging_removed=staging_removed,
        orphaned_final_removed=orphaned_final_removed,
        cleanup_failures=cleanup_failures,
    )
