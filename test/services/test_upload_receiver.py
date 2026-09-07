"""Tests for bounded streaming multipart upload receiving."""

from pathlib import Path
import asyncio
from concurrent.futures import CancelledError as FutureCancelledError
import pytest

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from modules.services.upload_receiver import (
    MIB,
    MAX_PART_HEADER_BYTES,
    MAX_PART_HEADERS,
    UploadAdmissionController,
    receive_multipart_upload,
    reconcile_upload_files,
    upload_limits,
)
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.batch_service import BatchService


@pytest.mark.parametrize("ending", [b"", b"\r\n--a", b"\r\n--a-"])
def test_incomplete_upload_rejects_all_files_and_closes_spools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ending: bytes
) -> None:
    import starlette.formparsers as parsers

    spools = []
    original = getattr(parsers, "SpooledTemporaryFile")

    def track_spool(*args, **kwargs):
        spool = original(*args, **kwargs)
        spools.append(spool)
        return spool

    monkeypatch.setattr(parsers, "SpooledTemporaryFile", track_spool)
    body = (
        b'--a\r\nContent-Disposition: form-data; name="pipeline_version_id"\r\n\r\nv1'
        b'\r\n--a\r\nContent-Disposition: form-data; name="files"; filename="one.pdf"'
        b'\r\n\r\n%PDF-one\r\n--a\r\nContent-Disposition: form-data; name="files"; filename="two.pdf"'
        b'\r\n\r\n%PDF-two' + ending
    )
    response = build_client(Config(tmp_path)).post(
        "/receive", content=body, headers={"Content-Type": "multipart/form-data; boundary=a"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Incomplete multipart upload"
    assert len(spools) == 2
    assert all(spool.closed for spool in spools)
    assert not list(tmp_path.rglob("*.upload"))


@pytest.mark.parametrize("header", [
    b"X-Long: " + b"x" * MAX_PART_HEADER_BYTES,
    b"X" * MAX_PART_HEADER_BYTES + b": value",
    b"X: v\r\n" * MAX_PART_HEADERS,
])
def test_header_limits_reject_before_consuming_file_body(tmp_path: Path, header: bytes) -> None:
    chunks = [
        b'--a\r\nContent-Disposition: form-data; name="files"; filename="one.pdf"\r\n',
        *[header[i:i + 127] for i in range(0, len(header), 127)],
    ]
    consumed = 0

    async def receive():
        nonlocal consumed
        if consumed == len(chunks):
            raise AssertionError("Oversized headers must be rejected before reading file data")
        chunk = chunks[consumed]
        consumed += 1
        return {"type": "http.request", "body": chunk, "more_body": True}

    request = Request({
        "type": "http", "headers": [(b"content-type", b"multipart/form-data; boundary=a")],
    }, receive)
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(receive_multipart_upload(request, Config(tmp_path)))
    assert getattr(rejected.value, "status_code", None) == 413
    assert not list(tmp_path.rglob("*.upload"))


def test_complete_upload_accepts_boundary_split_across_chunks(tmp_path: Path) -> None:
    body = (
        b'--a\r\nContent-Disposition: form-data; name="pipeline_version_id"\r\n\r\nv1'
        b'\r\n--a\r\nContent-Disposition: form-data; name="files"; filename="one.pdf"'
        b'\r\n\r\n%PDF-one\r\n--a--'
    )
    chunks = iter(bytes([value]) for value in body)

    async def receive():
        chunk = next(chunks, b"")
        return {"type": "http.request", "body": chunk, "more_body": bool(chunk)}

    request = Request({
        "type": "http", "headers": [(b"content-type", b"multipart/form-data; boundary=a")],
    }, receive)
    result = asyncio.run(receive_multipart_upload(request, Config(tmp_path)))
    assert len(result.files) == 1
    assert result.files[0].path.read_bytes() == b"%PDF-one"


class Config:
    def __init__(self, root: Path, **values: int) -> None:
        self.values = {
            "database.path": str(root / "app.sqlite3"),
            "web.upload_dir": str(root / "uploads"),
            "watch_folder.processing_dir": str(root / "processing"),
            **values,
        }

    def get(self, key: str, default=None):
        return self.values.get(key, default)


def build_client(config: Config) -> TestClient:
    app = FastAPI()
    admission = UploadAdmissionController()

    @app.post("/receive")
    async def receive(request: Request):
        if request.headers.get("x-test-strip-content-length") == "1":
            request.scope["headers"] = [
                (name, value)
                for name, value in request.scope["headers"]
                if name.lower() != b"content-length"
            ]
        received = await receive_multipart_upload(request, config, admission)
        result = {
            "pipeline_version_id": received.pipeline_version_id,
            "files": [
                {
                    "filename": item.filename,
                    "size": item.size_bytes,
                    "content": item.path.read_bytes().decode(),
                }
                for item in received.files
            ],
        }
        for item in received.files:
            item.path.unlink()
        return result

    return TestClient(app)


def test_upload_limits_use_bounded_defaults(tmp_path: Path) -> None:
    limits = upload_limits(Config(tmp_path))

    assert limits.max_file_bytes == 50 * MIB
    assert limits.max_files == 20
    assert limits.max_request_bytes == 200 * MIB
    assert limits.max_concurrent_uploads == 2


@pytest.mark.parametrize("mode", ["idle", "trickle", "copy"])
def test_upload_deadlines_release_capacity_and_cleanup(tmp_path, monkeypatch, mode):
    config = Config(tmp_path, **{
        "web.upload_idle_timeout_seconds": 1,
        "web.upload_timeout_seconds": 1 if mode != "idle" else 5,
    })
    admission = UploadAdmissionController()
    body = (b'--a\r\nContent-Disposition: form-data; name="pipeline_version_id"\r\n\r\nv1'
            b'\r\n--a\r\nContent-Disposition: form-data; name="files"; filename="a.pdf"'
            b'\r\n\r\n%PDF-test\r\n--a--\r\n')
    original = UploadFile.read

    async def slow_read(self, size=-1):
        await asyncio.sleep(2)
        return await original(self, size)

    if mode == "copy":
        monkeypatch.setattr(UploadFile, "read", slow_read)

    async def run():
        calls = 0

        async def receive():
            nonlocal calls
            calls += 1
            if mode == "copy":
                return {"type": "http.request", "body": body, "more_body": False}
            if calls == 1:
                return {"type": "http.request", "body": body[:-10], "more_body": True}
            await asyncio.sleep(2 if mode == "idle" else 0.1)
            return {"type": "http.request", "body": b"x", "more_body": True}

        request = Request({"type": "http", "headers": [(b"content-type", b"multipart/form-data; boundary=a")]}, receive)
        with pytest.raises(HTTPException) as error:
            await receive_multipart_upload(request, config, admission)
        assert error.value.status_code == 408
        async with admission.admit(1):
            pass
        assert not list(tmp_path.rglob("*.upload"))

    asyncio.run(run())


def test_receiver_streams_files_and_scalar_in_one_pass(tmp_path: Path) -> None:
    client = build_client(Config(tmp_path))

    response = client.post(
        "/receive",
        data={"pipeline_version_id": "version-1"},
        files=[
            ("files", ("one.pdf", b"%PDF-one", "application/pdf")),
            ("files", ("two.pdf", b"%PDF-two", "application/pdf")),
        ],
    )

    assert response.status_code == 200
    assert response.json() == {
        "pipeline_version_id": "version-1",
        "files": [
            {"filename": "one.pdf", "size": 8, "content": "%PDF-one"},
            {"filename": "two.pdf", "size": 8, "content": "%PDF-two"},
        ],
    }


def test_receiver_spools_large_file_parts_to_disk(tmp_path: Path, monkeypatch) -> None:
    config = Config(
        tmp_path,
        **{"web.max_upload_mb": 3, "web.max_upload_request_mb": 5},
    )
    rolled_states: list[bool] = []
    original_seek = UploadFile.seek

    async def record_spool_state(self, offset: int) -> None:
        rolled_states.append(bool(getattr(self.file, "_rolled", False)))
        await original_seek(self, offset)

    monkeypatch.setattr(UploadFile, "seek", record_spool_state)
    response = build_client(config).post(
        "/receive",
        data={"pipeline_version_id": "version-1"},
        files=[
            ("files", ("large.pdf", b"%PDF-" + b"x" * (2 * MIB), "application/pdf")),
        ],
    )

    assert response.status_code == 200
    assert any(rolled_states)


def test_receiver_rejects_oversized_declared_request_without_staging(
    tmp_path: Path,
) -> None:
    client = build_client(Config(tmp_path, **{"web.max_upload_request_mb": 1}))

    response = client.post(
        "/receive",
        content=b"x",
        headers={
            "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": str(2 * MIB),
        },
    )

    assert response.status_code == 413
    assert not list((tmp_path / "uploads" / ".staging").glob("*.upload"))


def test_receiver_counts_actual_bytes_without_content_length(tmp_path: Path) -> None:
    client = build_client(
        Config(
            tmp_path,
            **{
                "web.max_upload_mb": 2,
                "web.max_upload_request_mb": 1,
            },
        )
    )

    response = client.post(
        "/receive",
        data={"pipeline_version_id": "version-1"},
        files=[("files", ("large.pdf", b"%PDF-" + b"x" * MIB, "application/pdf"))],
        headers={"X-Test-Strip-Content-Length": "1"},
    )

    assert response.status_code == 413
    assert not list((tmp_path / "uploads" / ".staging").glob("*.upload"))


def test_receiver_cleans_staging_when_later_file_is_oversized(tmp_path: Path) -> None:
    client = build_client(Config(tmp_path, **{"web.max_upload_mb": 1}))

    response = client.post(
        "/receive",
        data={"pipeline_version_id": "version-1"},
        files=[
            ("files", ("one.pdf", b"%PDF-one", "application/pdf")),
            ("files", ("large.pdf", b"%PDF-" + b"x" * MIB, "application/pdf")),
        ],
    )

    assert response.status_code == 413
    assert not list((tmp_path / "uploads" / ".staging").glob("*.upload"))


def test_receiver_cleans_staging_when_copy_is_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_read = UploadFile.read
    reads = 0

    async def cancel_after_first_chunk(self, size: int = -1) -> bytes:
        nonlocal reads
        reads += 1
        if reads == 2:
            raise asyncio.CancelledError()
        return await original_read(self, 4)

    monkeypatch.setattr(UploadFile, "read", cancel_after_first_chunk)
    client = build_client(Config(tmp_path))
    with pytest.raises(FutureCancelledError):
        client.post(
            "/receive",
            data={"pipeline_version_id": "version-1"},
            files=[("files", ("one.pdf", b"%PDF-test", "application/pdf"))],
        )

    assert not list((tmp_path / "uploads" / ".staging").glob("*.upload"))


def test_receiver_rejects_duplicate_pipeline_selection(tmp_path: Path) -> None:
    client = build_client(Config(tmp_path))

    response = client.post(
        "/receive",
        files=[
            ("pipeline_version_id", (None, "version-1")),
            ("pipeline_version_id", (None, "version-2")),
            ("files", ("one.pdf", b"%PDF-one", "application/pdf")),
        ],
    )

    assert response.status_code == 400
    assert not list((tmp_path / "uploads" / ".staging").glob("*.upload"))


def test_receiver_rejects_unsupported_file_field(tmp_path: Path) -> None:
    client = build_client(Config(tmp_path))

    response = client.post(
        "/receive",
        data={"pipeline_version_id": "version-1"},
        files=[("attachment", ("one.pdf", b"%PDF-one", "application/pdf"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file field provided"
    assert not list((tmp_path / "uploads" / ".staging").glob("*.upload"))


def test_admission_rejects_when_capacity_is_full() -> None:
    controller = UploadAdmissionController()

    async def exercise() -> None:
        async with controller.admit(1):
            try:
                async with controller.admit(1):
                    raise AssertionError("second admission should not succeed")
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 429
                assert getattr(exc, "headers", None) == {"Retry-After": "1"}

        async with controller.admit(1):
            pass

    import anyio

    anyio.run(exercise)


def test_startup_reconciliation_removes_only_unreferenced_upload_files(
    tmp_path: Path,
) -> None:
    config = Config(tmp_path)
    initialize_database(config)
    processing = Path(config.get("watch_folder.processing_dir"))
    staging = processing / ".upload_staging"
    staging.mkdir(parents=True)
    abandoned = staging / "abandoned.upload"
    abandoned.write_bytes(b"partial")
    referenced = processing / "web-upload-referenced.pdf"
    orphaned = processing / "web-upload-orphaned.pdf"
    watch_file = processing / "watch-document.pdf"
    for path in (referenced, orphaned, watch_file):
        path.write_bytes(b"%PDF-test")

    with connect(config) as conn:
        BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(referenced),
            original_filename="referenced.pdf",
        )
        conn.commit()

    result = reconcile_upload_files(config)

    assert result.staging_removed == 1
    assert result.orphaned_final_removed == 1
    assert result.cleanup_failures == 0
    assert referenced.exists()
    assert watch_file.exists()
    assert not abandoned.exists()
    assert not orphaned.exists()


def test_reconciliation_preserves_files_when_database_cannot_be_checked(
    tmp_path: Path,
) -> None:
    config = Config(tmp_path)
    processing = Path(config.get("watch_folder.processing_dir"))
    staging = processing / ".upload_staging"
    staging.mkdir(parents=True)
    abandoned = staging / "abandoned.upload"
    abandoned.write_bytes(b"partial")

    import sqlite3

    try:
        reconcile_upload_files(config)
        raise AssertionError("missing runtime schema should fail reconciliation")
    except sqlite3.OperationalError:
        pass

    assert abandoned.exists()
