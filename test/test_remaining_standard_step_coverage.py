"""Focused tests for defensive paths in standard pipeline tasks."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from modules.exceptions import TaskError
from standard_step.archiver.archive_pdf import ArchivePdfTask
from standard_step.context.assign_nanoid import AssignNanoidTask
from standard_step.storage.store_file_to_localdrive import StoreFileToLocaldrive
from standard_step.housekeeping.cleanup_task import CleanupTask
import standard_step.housekeeping.cleanup_task as cleanup_module


class Config:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def get_all(self):
        return self.values


def test_assign_nanoid_missing_config_and_noop_validation() -> None:
    with pytest.raises(TaskError, match="missing"):
        AssignNanoidTask(Config({"assign_nanoid.length": None}), length=None)
    task = AssignNanoidTask(Config(), length=5)
    assert task.validate_required_fields({}) is None


def test_archive_validation_and_failed_reservation_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task = ArchivePdfTask(Config(), archive_dir="")
    task.archive_dir = ""
    with pytest.raises(TaskError, match="not set"):
        task.validate_required_fields({})
    task.archive_dir = str(tmp_path)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-")
    monkeypatch.setattr(task, "_copy_file", Mock(side_effect=OSError("copy")))
    monkeypatch.setattr("standard_step.archiver.archive_pdf.release_reserved_filepath", lambda _path: False)
    result = task.run({"file_path": str(source), "original_filename": "source.pdf"})
    assert "error" in result


def test_store_file_validation_and_format_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task = StoreFileToLocaldrive(Config(), files_dir=str(tmp_path), filename="{missing}")
    task.files_dir = None
    with pytest.raises(TaskError, match="files_dir"):
        task.validate_required_fields({})
    task.files_dir = tmp_path
    task.filename = None
    with pytest.raises(TaskError, match="filename"):
        task.validate_required_fields({})
    task.filename = "{missing}"
    with pytest.raises(TaskError, match="missing key"):
        task.run({"file_path": str(tmp_path / "source.pdf"), "id": "d", "original_filename": "source.pdf"})

    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-")
    task.filename = "output"
    monkeypatch.setattr("standard_step.storage.store_file_to_localdrive.shutil.copy", Mock(side_effect=OSError("copy")))
    monkeypatch.setattr("standard_step.storage.store_file_to_localdrive.release_reserved_filepath", lambda _path: False)
    with pytest.raises(TaskError, match="Failed to store file source.pdf"):
        task.run({"file_path": str(source), "id": "d", "original_filename": "source.pdf"})


def test_cleanup_paths_and_registered_artifact_probe_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task = CleanupTask(Config(), processing_dir=str(tmp_path))
    transient = tmp_path / "transient.pdf"
    transient.write_bytes(b"data")
    assert task.run({"cleanup_paths": [str(transient)]})["cleanup_paths"] == [str(transient)]
    assert not transient.exists()

    artifact = tmp_path / "artifact.pdf"
    artifact.write_bytes(b"data")
    task._is_registered_document_artifact = Mock(return_value=True)
    task.run({"file_path": str(artifact), "document_id": "doc"})
    assert artifact.exists()
    monkeypatch.setattr(cleanup_module, "connect", Mock(side_effect=OSError("db unavailable")))
    task._is_registered_document_artifact = CleanupTask._is_registered_document_artifact.__get__(task)
    assert task._is_registered_document_artifact(artifact, {"document_id": "doc"}) is False
