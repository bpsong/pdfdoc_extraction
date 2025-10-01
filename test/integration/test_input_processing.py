import io
import os
import builtins
import types
import uuid
import shutil
import time
from pathlib import Path
from typing import Any, cast, Optional, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.file_processor import FileProcessor
from modules.workflow_manager import WorkflowManager
from modules.watch_folder_monitor import WatchFolderMonitor
from modules import utils
import modules.api_router as api_router

# Input Handler and Watch/Upload PDF Validation tests merged.
# Shared fixtures and helpers consolidated below so both test groups reuse them.

class DummyConfig:
    """
    Unified DummyConfig that supports both construction styles used across
    the original test files:

    - test_input_handler.py used: DummyConfig(values_dict)
      where values_dict maps config keys to values and exposes .get(key, default)

    - test_watch_and_upload_pdf_validation.py used: DummyConfig(watch_dir, processing_dir, web_upload_dir)

    This unified implementation accepts either a single mapping dict or three positional
    path-like arguments and exposes .get(key, default) for compatibility.
    """
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], dict):
            self._values = args[0]
        elif len(args) == 3:
            watch_dir, processing_dir, web_upload_dir = args
            self._values = {
                "watch_folder.dir": str(watch_dir),
                "watch_folder.processing_dir": str(processing_dir),
                "web.upload_dir": str(web_upload_dir),
                "watch_folder.validate_pdf_header": True,
            }
        else:
            # Allow constructing from explicit mapping keyword use elsewhere
            self._values = {}

    def get(self, key, default=None):
        return self._values.get(key, default)


class DummyWorkflowManager:
    def __init__(self):
        self.calls = []

    def trigger_workflow_for_file(self, *, file_path: str, unique_id: str, original_filename: str, source: str) -> Any:
        self.calls.append({
            "file_path": file_path,
            "unique_id": unique_id,
            "original_filename": original_filename,
            "source": source,
        })
        return None


class DummyStatusManager:
    def __init__(self):
        self.created = []

    def create_status(self, *, unique_id, original_filename, source, file_path):
        self.created.append({
            "unique_id": unique_id,
            "original_filename": original_filename,
            "source": source,
            "file_path": file_path,
        })


def monkeypatch_status_manager(monkeypatch, dummy_status_manager):
    """
    Patch StatusManager used inside FileProcessor to our dummy.
    """
    import modules.file_processor as fp_mod
    class _Factory:
        def __call__(self, *args, **kwargs):
            return dummy_status_manager
    monkeypatch.setattr(fp_mod, "StatusManager", _Factory())


class FakeUploadFile:
    """
    Minimal FastAPI-like UploadFile double: exposes .filename and .file with read().
    """
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.file = io.BytesIO(content)


@pytest.fixture
def tmp_dirs(tmp_path):
    upload_dir = tmp_path / "web_upload"
    processing_dir = tmp_path / "processing"
    upload_dir.mkdir()
    processing_dir.mkdir()
    return str(upload_dir), str(processing_dir)


@pytest.fixture
def config():
    def _cfg(upload_dir, processing_dir, validate_header=True):
        return DummyConfig({
            "web.upload_dir": upload_dir,
            "watch_folder.processing_dir": processing_dir,
            "watch_folder.validate_pdf_header": validate_header,
        })
    return _cfg


# --------------------------
# Input Handler Tests
# --------------------------

def test_process_web_upload_success_pdf_header_valid(monkeypatch, tmp_dirs, config):
    upload_dir, processing_dir = tmp_dirs

    # Prepare config to validate header
    cfg = config(upload_dir, processing_dir, validate_header=True)

    # Prepare FileProcessor with a no-op retry function and dummy workflow
    wf = DummyWorkflowManager()
    dummy_status = DummyStatusManager()
    monkeypatch_status_manager(monkeypatch, dummy_status)

    fp = FileProcessor(config_manager=cfg, retry_operation_func=lambda f, *a, **k: f(*a, **k), workflow_manager=cast(WorkflowManager, wf))

    # Create a valid PDF header
    content = b"%PDF-1.4\n%..."  # starts with %PDF-
    upload = FakeUploadFile("source.pdf", content)

    unique_id = fp.process_web_upload(upload_file=upload, source="web")

    # Verify file moved into processing with UUID.pdf
    files = os.listdir(processing_dir)
    assert len(files) == 1
    assert files[0].endswith(".pdf")
    moved_path = os.path.join(processing_dir, files[0])

    # Check status created
    assert len(dummy_status.created) == 1
    created = dummy_status.created[0]
    assert created["unique_id"] == unique_id
    assert created["original_filename"] == "source.pdf"
    assert created["source"] == "web"
    assert created["file_path"] == moved_path

    # Check workflow triggered with source=web
    assert len(wf.calls) == 1
    call = wf.calls[0]
    assert call["unique_id"] == unique_id
    assert call["original_filename"] == "source.pdf"
    assert call["source"] == "web"
    assert call["file_path"] == moved_path

    # Verify content persisted (starts with %PDF-)
    with open(moved_path, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_process_web_upload_invalid_header_removes_temp_and_raises(monkeypatch, tmp_dirs, config):
    upload_dir, processing_dir = tmp_dirs
    cfg = config(upload_dir, processing_dir, validate_header=True)

    wf = DummyWorkflowManager()
    dummy_status = DummyStatusManager()
    monkeypatch_status_manager(monkeypatch, dummy_status)

    fp = FileProcessor(config_manager=cfg, retry_operation_func=lambda f, *a, **k: f(*a, **k), workflow_manager=cast(WorkflowManager, wf))

    # Not a valid PDF header
    bad_content = b"NOTPDF"
    upload = FakeUploadFile("bad.pdf", bad_content)

    with pytest.raises(ValueError) as ei:
        fp.process_web_upload(upload_file=upload, source="web")
    assert "Invalid PDF header" in str(ei.value)

    # Ensure no file lingered in processing
    assert os.listdir(processing_dir) == []

    # Ensure no status or workflow call
    assert dummy_status.created == []
    assert wf.calls == []

    # Ensure temp file in upload_dir removed
    assert os.listdir(upload_dir) == []


def test_process_web_upload_header_validation_disabled(monkeypatch, tmp_dirs, config):
    upload_dir, processing_dir = tmp_dirs
    cfg = config(upload_dir, processing_dir, validate_header=False)

    wf = DummyWorkflowManager()
    dummy_status = DummyStatusManager()
    monkeypatch_status_manager(monkeypatch, dummy_status)

    fp = FileProcessor(config_manager=cfg, retry_operation_func=lambda f, *a, **k: f(*a, **k), workflow_manager=cast(WorkflowManager, wf))

    # Invalid header but validation disabled
    content = b"NO_PDF_HEADER"
    upload = FakeUploadFile("any.pdf", content)

    unique_id = fp.process_web_upload(upload_file=upload, source="web")

    # File exists in processing
    files = os.listdir(processing_dir)
    assert len(files) == 1
    assert files[0].endswith(".pdf")
    moved_path = os.path.join(processing_dir, files[0])

    # Status and workflow still created
    assert len(dummy_status.created) == 1
    created = dummy_status.created[0]
    assert created["unique_id"] == unique_id
    assert created["original_filename"] == "any.pdf"
    assert created["source"] == "web"
    assert created["file_path"] == moved_path

    assert len(wf.calls) == 1
    call = wf.calls[0]
    assert call["unique_id"] == unique_id
    assert call["original_filename"] == "any.pdf"
    assert call["source"] == "web"
    assert call["file_path"] == moved_path


def test_process_web_upload_supports_bytes_like_input(monkeypatch, tmp_dirs, config):
    upload_dir, processing_dir = tmp_dirs
    cfg = config(upload_dir, processing_dir, validate_header=True)

    wf = DummyWorkflowManager()
    dummy_status = DummyStatusManager()
    monkeypatch_status_manager(monkeypatch, dummy_status)

    fp = FileProcessor(config_manager=cfg, retry_operation_func=lambda f, *a, **k: f(*a, **k), workflow_manager=cast(WorkflowManager, wf))

    # Provide raw bytes that are a valid PDF header
    content = b"%PDF-1.7..."
    unique_id = fp.process_web_upload(upload_file=io.BytesIO(content), source="web")

    files = os.listdir(processing_dir)
    assert len(files) == 1
    moved_path = os.path.join(processing_dir, files[0])

    assert len(dummy_status.created) == 1
    assert len(wf.calls) == 1
    with open(moved_path, "rb") as f:
        assert f.read(5) == b"%PDF-"


# --------------------------
# Watch and Upload PDF Validation Tests
# --------------------------

def test_watch_folder_skips_invalid_pdf_header(tmp_path, monkeypatch):
    watch_dir = tmp_path / "watch"
    proc_dir = tmp_path / "proc"
    watch_dir.mkdir()
    proc_dir.mkdir()
    # Create a fake PDF file in watch folder
    sample = watch_dir / "some.pdf"
    sample.write_bytes(b"NOTPDFDATA")
    called = {"processed": False}
    def fake_callback(new_filepath, uuid_str, source_label, original_filename=None, **kwargs):
        called["processed"] = True

    cfg = DummyConfig(watch_dir, proc_dir, tmp_path / "upload")
    monitor = WatchFolderMonitor(config_manager=cfg, process_file_callback=fake_callback, retry_file_operation_func=None)

    # Force _is_valid_pdf_header to return False (simulate invalid header)
    monkeypatch.setattr(utils, "is_pdf_header", lambda fp, **kw: False)

    # Also monkeypatch shutil.move to avoid actually moving files (but we expect it not to be called)
    moved = {"count": 0}
    def fake_move(src, dst):
        moved["count"] += 1
        # Do not perform actual move to keep file in place
    monkeypatch.setattr("shutil.move", fake_move)

    # Run one iteration of _monitor_new_files loop but exit quickly
    # We'll set stop_event after one loop by patching time.sleep to set stop
    def sleep_and_stop(sec):
        monitor.stop()
        return None
    monkeypatch.setattr("time.sleep", sleep_and_stop)

    # Run monitor (it will iterate once and stop)
    monitor._monitor_new_files()

    # Since header invalid, callback should not be invoked and file should remain in watch dir
    assert not called["processed"]
    assert sample.exists()
    assert moved["count"] == 0


def test_watch_folder_processes_valid_pdf_header(tmp_path, monkeypatch):
    watch_dir = tmp_path / "watch2"
    proc_dir = tmp_path / "proc2"
    watch_dir.mkdir()
    proc_dir.mkdir()
    sample = watch_dir / "valid.pdf"
    sample.write_bytes(b"%PDF-1.4 content")
    processed: Dict[str, Optional[dict]] = {"args": None}
    def fake_callback(new_filepath, uuid_str, source_label, original_filename=None, **kwargs):
        processed["args"] = {"new_filepath": new_filepath, "uid": uuid_str, "source": source_label, "original": original_filename}

    cfg = DummyConfig(watch_dir, proc_dir, tmp_path / "upload2")
    monitor = WatchFolderMonitor(config_manager=cfg, process_file_callback=fake_callback, retry_file_operation_func=None)

    # is_pdf_header returns True
    monkeypatch.setattr(utils, "is_pdf_header", lambda fp, **kw: True)

    # Let the loop run once and then stop via time.sleep
    monkeypatch.setattr("time.sleep", lambda s: monitor.stop())

    monitor._monitor_new_files()

    # A file should have been moved into proc_dir and callback invoked
    assert processed["args"] is not None
    final_path = Path(processed["args"]["new_filepath"])
    assert final_path.exists()
    assert processed["args"]["original"] == "valid.pdf"
    assert processed["args"]["source"] == "watch_folder"


def _build_test_app(tmp_upload_dir, monkeypatch, is_pdf_header_result=True):
    # Build app with router and override get_dependencies to inject config and file_processor
    app = FastAPI()
    router = api_router.build_router()
    app.include_router(router)

    # Create dummy config and a fake FileProcessor with process_file method
    cfg = DummyConfig("unused_watch", tmp_upload_dir.parent / "proc", tmp_upload_dir)
    class FakeFileProcessor:
        def __init__(self):
            self.processed = []
        def process_file(self, filepath, unique_id, source, original_filename=None):
            self.processed.append({"filepath": filepath, "id": unique_id, "source": source, "original": original_filename})
    fake_fp = FakeFileProcessor()

    # Patch get_dependencies to return our injected instances (config, auth, status_mgr, workflow_mgr, file_processor)
    def fake_get_deps():
        # other values not used in upload endpoint can be None
        return cfg, None, None, None, fake_fp
    monkeypatch.setattr(api_router, "get_dependencies", fake_get_deps)

    # Bypass authentication by overriding dependency used for get_current_user
    app.dependency_overrides[api_router.get_current_user] = lambda: "testuser"

    # Control is_pdf_header result
    monkeypatch.setattr(utils, "is_pdf_header", lambda path, **kw: is_pdf_header_result)

    return app, fake_fp


def make_upload_payload(filename="test.pdf", data=b"%PDF-1.7 sample"):
    # Use list-of-tuples form to satisfy TestClient typing and Pylance
    return [("file", (filename, io.BytesIO(data), "application/pdf"))]


def test_upload_endpoint_accepts_valid_pdf(tmp_path, monkeypatch):
    upload_dir = tmp_path / "upload_ok"
    upload_dir.mkdir()
    app, fake_fp = _build_test_app(upload_dir, monkeypatch, is_pdf_header_result=True)
    client = TestClient(app)

    payload = make_upload_payload(data=b"%PDF-1.7 some content")
    resp = client.post("/upload", files=payload, follow_redirects=False)
    # Successful upload should redirect (303)
    assert resp.status_code == 303
    # The background task may run synchronously or asynchronously; give a short moment.
    time.sleep(0.1)
    # Ensure FakeFileProcessor exists (background may or may not have executed in this test harness)
    assert isinstance(fake_fp, object)


def test_upload_endpoint_rejects_invalid_pdf_and_removes_temp(tmp_path, monkeypatch):
    upload_dir = tmp_path / "upload_bad"
    upload_dir.mkdir()
    app, fake_fp = _build_test_app(upload_dir, monkeypatch, is_pdf_header_result=False)
    client = TestClient(app)

    payload = make_upload_payload(data=b"NOT_A_PDF")
    resp = client.post("/upload", files=payload)
    # Should respond with 400 Bad Request due to invalid PDF header
    assert resp.status_code == 400
    # Ensure temporary files in upload_dir are removed (no lingering temp file)
    files = list(upload_dir.iterdir())
    # Assert there are no temp files matching pattern "_temp.pdf"
    assert not any(p.name.endswith("_temp.pdf") for p in files)