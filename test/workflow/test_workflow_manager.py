import pytest
import os
import shutil
import threading
import time
import csv
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import patch, mock_open, Mock

from modules.config_manager import ConfigManager
from modules.status_manager import StatusManager
from modules.workflow_manager import WorkflowManager
from modules.watch_folder_monitor import WatchFolderMonitor
from modules.utils import sanitize_filename
from test.helpers_sqlite import TempConfig

@pytest.fixture
def watch_folder_monitor_instance():
    config_manager = Mock()
    config_manager.get.side_effect = lambda key: {
        "watch_folder.dir": "test_watch_folder",
        "watch_folder.processing_dir": "test_processing_folder"
    }.get(key, None)
    monitor = WatchFolderMonitor(config_manager, None, None)
    monitor.retry_attempts = 3
    monitor.retry_delay = 0.01  # reduce delay for faster tests
    return monitor

def test_is_valid_pdf_header_retry_success(watch_folder_monitor_instance):
    # Simulate transient failure on first two attempts, success on third
    file_content_sequence = [b'BADHD', b'BADHD', b'%PDF-']
    open_mock = mock_open()
    open_mock.return_value.read = lambda n: file_content_sequence.pop(0)

    with patch("builtins.open", open_mock):
        result = watch_folder_monitor_instance._is_valid_pdf_header("dummy_path")
        assert result is True

def test_is_valid_pdf_header_retry_failure(watch_folder_monitor_instance):
    # Simulate failure on all attempts
    open_mock = mock_open()
    open_mock.return_value.read = lambda n: b'BADHD'

    with patch("builtins.open", open_mock):
        result = watch_folder_monitor_instance._is_valid_pdf_header("dummy_path")
        assert result is False

def test_is_valid_pdf_header_ioerror_retry(watch_folder_monitor_instance):
    # Simulate IOError on first two attempts, success on third
    call_count = {"count": 0}

    def open_side_effect(*args, **kwargs):
        if call_count["count"] < 2:
            call_count["count"] += 1
            raise IOError("File temporarily unavailable")
        else:
            m = mock_open(read_data=b'%PDF-')
            return m()

    with patch("builtins.open", side_effect=open_side_effect):
        result = watch_folder_monitor_instance._is_valid_pdf_header("dummy_path")
        assert result is True

def test_end_to_end_workflow_execution(tmp_path, monkeypatch):
    """Run a pinned pipeline with synthetic extraction and real exports."""
    from modules.db.connection import connect
    from modules.db.migrations import initialize_database
    from modules.services.batch_service import BatchService
    from modules.db.repositories import DocumentRepository, TaskRunRepository
    from test.helpers_sqlite import seed_pipeline, assign_pipeline
    from test.workflow.test_workflow_task_run_tracking import _patch_prefect
    from modules.workflow_loader import WorkflowLoader

    source = tmp_path / "input.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    config = TempConfig(tmp_path / "state.sqlite3", {
        "pipeline": ["extract", "json", "csv", "pdf", "archive"],
        "tasks": {
            "extract": {"module": "tests", "class": "SyntheticExtract", "params": {}},
            "json": {"module": "standard_step.storage.store_metadata_as_json", "class": "StoreMetadataAsJson", "params": {"data_dir": str(tmp_path / "exports"), "filename": "{supplier}"}},
            "csv": {"module": "standard_step.storage.store_metadata_as_csv", "class": "StoreMetadataAsCsv", "params": {"data_dir": str(tmp_path / "exports"), "filename": "{supplier}"}},
            "pdf": {"module": "standard_step.storage.store_file_to_localdrive", "class": "StoreFileToLocaldrive", "params": {"files_dir": str(tmp_path / "files"), "filename": "{supplier}"}},
            "archive": {"module": "standard_step.archiver.archive_pdf", "class": "ArchivePdfTask", "params": {"archive_dir": str(tmp_path / "archive")}},
        },
    })
    initialize_database(config)
    version = seed_pipeline(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(source="web", file_path=str(source), original_filename="input.pdf")
    assign_pipeline(config, created["document"]["id"], version)

    class SyntheticExtract:
        def __init__(self, config_manager, **params):
            pass
        def on_start(self, context):
            pass
        def run(self, context):
            context["data"] = {"supplier": "Synthetic", "amount": 12.5}
            return context

    original_import = WorkflowLoader._import_task_class
    monkeypatch.setattr(WorkflowLoader, "_import_task_class", lambda self, module, cls: SyntheticExtract if cls == "SyntheticExtract" else original_import(self, module, cls))
    _patch_prefect(monkeypatch)
    assert WorkflowManager(config).trigger_workflow_for_file(
        str(source), created["document"]["id"], "input.pdf", "web",
        batch_id=created["batch"]["id"], document_id=created["document"]["id"],
    ) is True
    assert json.loads((tmp_path / "exports" / "Synthetic.json").read_text())["amount"] == 12.5
    with (tmp_path / "exports" / "Synthetic.csv").open(newline="") as stream:
        assert list(csv.DictReader(stream))[0]["supplier"] == "Synthetic"
    assert list((tmp_path / "files").glob("*.pdf"))
    assert list((tmp_path / "archive").glob("*.pdf"))
    with connect(config) as conn:
        assert DocumentRepository(conn).get(created["document"]["id"])["status"] == "completed"
        runs = TaskRunRepository(conn).list_by_document(created["document"]["id"])
        assert [run["task_key"] for run in runs] == ["extract", "json", "csv", "pdf", "archive", "cleanup_task"]
        assert all(run["status"] == "completed" for run in runs)
        assert all(run["pipeline_version_id"] == version["id"] for run in runs)
    assert not list(tmp_path.rglob("*.txt"))


def test_workflow_manager_propagates_source_web(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from modules.workflow_loader import WorkflowLoader
    config = TempConfig(tmp_path / "state.sqlite3")
    manager = WorkflowManager(config)
    captured = {}
    monkeypatch.setattr(manager, "_load_document_pipeline", lambda document_id: SimpleNamespace(definition={"pipeline": [], "tasks": {}}, version_id="v1", template_id="t1"))
    monkeypatch.setattr(WorkflowLoader, "load_workflow", lambda self: lambda context: captured.update(context))
    assert manager.trigger_workflow_for_file("input.pdf", "doc", "uploaded.pdf", "web", batch_id="batch", document_id="doc")
    assert captured["source"] == "web"
    assert captured["original_filename"] == "uploaded.pdf"
    assert captured["pipeline_version_id"] == "v1"
    assert captured["document_id"] == "doc"


def test_split_child_preflight_is_provider_specific_for_llama_and_glm(
    tmp_path, monkeypatch
):
    glm_config = TempConfig(
        tmp_path / "glm.sqlite3",
        {
            "pipeline": ["glm_extract"],
            "tasks": {
                "glm_extract": {
                    "module": "standard_step.extraction.glm_ocr_extract",
                    "class": "GlmOcrExtractTask",
                    "params": {
                        "ollama_host": "http://127.0.0.1:11434",
                        "model": "glm-ocr:latest",
                    },
                }
            },
        },
    )
    glm_manager = WorkflowManager(glm_config)
    preflight = Mock(side_effect=AssertionError("must not call LlamaCloud"))
    monkeypatch.setattr(
        "modules.workflow_manager.preflight_extract_v2_access", preflight
    )

    assert glm_manager._fail_children_when_extract_preflight_fails({}, [], 0, executable=SimpleNamespace(definition=glm_config.get_all())) is False
    preflight.assert_not_called()
    assert glm_manager._is_llamacloud_extract_task(
        glm_config.get("tasks.glm_extract")
    ) is False

    llama_config = TempConfig(
        tmp_path / "llama.sqlite3",
        {
            "pipeline": ["extract"],
            "tasks": {
                "extract": {
                    "module": "standard_step.extraction.extract_pdf",
                    "class": "ExtractPdfTask",
                    "params": {"api_key": "test-key"},
                }
            },
        },
    )
    llama_manager = WorkflowManager(llama_config)
    llama_preflight = Mock(return_value=None)
    monkeypatch.setattr(
        "modules.workflow_manager.preflight_extract_v2_access", llama_preflight
    )

    assert llama_manager._fail_children_when_extract_preflight_fails({}, [], 0, executable=SimpleNamespace(definition=llama_config.get_all())) is False
    llama_preflight.assert_called_once()
    assert llama_manager._is_llamacloud_extract_task(
        llama_config.get("tasks.extract")
    ) is True
