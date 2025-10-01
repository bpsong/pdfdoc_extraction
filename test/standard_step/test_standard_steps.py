import os
import logging
import pytest
from unittest import mock
from unittest.mock import MagicMock, patch
from standard_step.archiver.archive_pdf import ArchivePdfTask
from modules.exceptions import TaskError
from pathlib import Path

# From assign_nanoid tests
from modules.config_manager import ConfigManager
from standard_step.context.assign_nanoid import AssignNanoidTask, TaskError

# Shared fixtures

@pytest.fixture
def config_manager_mock():
    cm = MagicMock()
    cm.get.return_value = None
    return cm

def make_config_manager(values=None):
    """Return a MagicMock behaving like ConfigManager.get(key, default=None)."""
    values = values or {}
    cm = MagicMock(spec=ConfigManager)
    cm.get.side_effect = lambda key, default=None: values.get(key, default)
    return cm

@pytest.fixture
def context_success():
    return {
        "file_path": "C:/path/to/processed/file.pdf",
        "original_filename": "original file.pdf"
    }

@pytest.fixture
def archive_dir_param():
    return r"C:\archive_dir"


# Archiver Tests
@patch("standard_step.archiver.archive_pdf.windows_long_path", side_effect=lambda x: x)
def test_init_with_param_and_fallback(mock_windows_long_path, config_manager_mock, archive_dir_param):
    # archive_dir provided in params
    task = ArchivePdfTask(config_manager_mock, archive_dir=archive_dir_param)
    assert task.archive_dir == archive_dir_param
    mock_windows_long_path.assert_called_with(archive_dir_param)

    # archive_dir fallback to config manager
    config_manager_mock.get.return_value = r"C:\config_archive_dir"
    task2 = ArchivePdfTask(config_manager_mock)
    assert task2.archive_dir == r"C:\config_archive_dir"
    mock_windows_long_path.assert_called_with(r"C:\config_archive_dir")

    # archive_dir fallback to empty string if none provided
    config_manager_mock.get.return_value = None
    task3 = ArchivePdfTask(config_manager_mock)
    assert task3.archive_dir == ""

@patch("os.path.exists")
@patch("os.path.isdir")
def test_validate_required_fields_success(mock_isdir, mock_exists, config_manager_mock):
    mock_exists.return_value = True
    mock_isdir.return_value = True
    task = ArchivePdfTask(config_manager_mock, archive_dir="C:\\archive_dir")
    # Should not raise
    task.validate_required_fields({})

@patch("os.path.exists")
@patch("os.path.isdir")
def test_validate_required_fields_missing_archive_dir(mock_isdir, mock_exists, config_manager_mock):
    mock_exists.return_value = False
    mock_isdir.return_value = False
    task = ArchivePdfTask(config_manager_mock, archive_dir="")
    with pytest.raises(TaskError):
        task.validate_required_fields({})

@patch("os.path.exists")
@patch("os.path.isdir")
def test_validate_required_fields_nonexistent_dir(mock_isdir, mock_exists, config_manager_mock):
    mock_exists.return_value = False
    mock_isdir.return_value = True
    task = ArchivePdfTask(config_manager_mock, archive_dir="C:\\archive_dir")
    with pytest.raises(TaskError, match="Archive directory does not exist"):
        task.validate_required_fields({})

@patch("os.path.exists")
@patch("os.path.isdir")
def test_validate_required_fields_not_a_dir(mock_isdir, mock_exists, config_manager_mock):
    mock_exists.return_value = True
    mock_isdir.return_value = False
    task = ArchivePdfTask(config_manager_mock, archive_dir="C:\\archive_dir")
    with pytest.raises(TaskError, match="Archive directory path is not a directory"):
        task.validate_required_fields({})

@patch("standard_step.archiver.archive_pdf.windows_long_path", side_effect=lambda x: x)
@patch("standard_step.archiver.archive_pdf.sanitize_filename", side_effect=lambda x: x.replace(" ", "_"))
@patch("standard_step.archiver.archive_pdf.generate_unique_filepath")
@patch("standard_step.archiver.archive_pdf.ArchivePdfTask._copy_file")
def test_run_success(mock_copy_file, mock_generate_unique_filepath, mock_sanitize_filename, mock_windows_long_path, config_manager_mock, context_success):
    archive_dir = Path(r"C:\archive_dir")
    task = ArchivePdfTask(config_manager_mock, archive_dir=str(archive_dir))

    # Setup mocks
    mock_generate_unique_filepath.return_value = archive_dir / "original_file.pdf"

    # Run
    result_context = task.run(context_success)

    # Check that sanitize_filename was called
    mock_sanitize_filename.assert_called_once_with("original file.pdf")

    # Check that generate_unique_filepath was called with correct args
    mock_generate_unique_filepath.assert_called_once()
    args, kwargs = mock_generate_unique_filepath.call_args
    assert args[0] == archive_dir
    assert args[1] == "original_file"
    assert args[2] == ".pdf"

    # Check that windows_long_path was called for src and dst paths
    assert mock_windows_long_path.call_count >= 3  # init + src + dst

    # Check that _copy_file was called with correct src and dst
    mock_copy_file.assert_called_once_with(context_success["file_path"], str(archive_dir / "original_file.pdf"))

    # Check context updated with success message
    assert "data" in result_context
    assert "archive_status" in result_context["data"]
    assert "File archived successfully" in result_context["data"]["archive_status"]

@patch("standard_step.archiver.archive_pdf.ArchivePdfTask.register_error")
def test_run_missing_processed_file_path(mock_register_error, config_manager_mock):
    task = ArchivePdfTask(config_manager_mock, archive_dir="C:\\archive_dir")
    context = {"original_filename": "file.pdf"}
    result_context = task.run(context)
    mock_register_error.assert_called_once()
    assert "data" not in result_context or "archive_status" not in result_context.get("data", {})

@patch("standard_step.archiver.archive_pdf.ArchivePdfTask.register_error")
def test_run_missing_original_filename(mock_register_error, config_manager_mock):
    task = ArchivePdfTask(config_manager_mock, archive_dir="C:\\archive_dir")
    context = {"file_path": "C:/file.pdf"}
    result_context = task.run(context)
    mock_register_error.assert_called_once()
    assert "data" not in result_context or "archive_status" not in result_context.get("data", {})

@patch("standard_step.archiver.archive_pdf.ArchivePdfTask.register_error")
@patch("standard_step.archiver.archive_pdf.ArchivePdfTask._copy_file", side_effect=Exception("copy failed"))
def test_run_unexpected_exception(mock_copy_file, mock_register_error, config_manager_mock, context_success):
    task = ArchivePdfTask(config_manager_mock, archive_dir="C:\\archive_dir")
    result_context = task.run(context_success)
    mock_register_error.assert_called_once()
    assert "data" not in result_context or "archive_status" not in result_context.get("data", {})

@patch("standard_step.archiver.archive_pdf.shutil.copy2")
def test_copy_file_retry_logic(mock_copy2, config_manager_mock):
    task = ArchivePdfTask(config_manager_mock, archive_dir="C:\\archive_dir")

    # Setup mock to raise OSError first two times, then succeed
    mock_copy2.side_effect = [OSError("fail1"), OSError("fail2"), None]

    # Should not raise because retry_io decorator retries
    task._copy_file("src", "dst")

    assert mock_copy2.call_count == 3

@patch("logging.getLogger")
def test_logging_calls(mock_get_logger, config_manager_mock):
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger
    task = ArchivePdfTask(config_manager_mock, archive_dir="C:\\archive_dir")

    context = {
        "file_path": "C:/file.pdf",
        "original_filename": "file.pdf"
    }

    task.on_start(context)
    mock_logger.info.assert_any_call(f"Starting ArchivePdfTask with archive_dir: {task.archive_dir}")

    with patch.object(task, "_copy_file") as mock_copy_file:
        mock_copy_file.return_value = None
        task.run(context)
        mock_logger.debug.assert_any_call(f"File path: {context['file_path']}")
        mock_logger.debug.assert_any_call(f"Original filename: {context['original_filename']}")
        mock_logger.info.assert_any_call(mock.ANY)  # Copying file log
        mock_logger.info.assert_any_call(mock.ANY)  # File archived successfully log


# Assign Nanoid Tests
@patch("standard_step.context.assign_nanoid.StatusManager")
@patch("standard_step.context.assign_nanoid.generate")
def test_valid_length_and_context_update(mock_generate, mock_status):
    mock_generate.return_value = "X" * 10
    config = make_config_manager({"assign_nanoid.length": 10})
    task = AssignNanoidTask(config)
    ctx = {}
    result = task.run(ctx)
    assert "data" in result
    assert "nanoid" in result["data"]
    assert len(result["data"]["nanoid"]) == 10


@patch("standard_step.context.assign_nanoid.generate")
def test_boundary_lengths(mock_generate):
    mock_generate.side_effect = lambda size=5: "A" * size
    config = make_config_manager({"assign_nanoid.length": 5})
    task = AssignNanoidTask(config)
    ctx = {}
    task.run(ctx)
    assert "data" in ctx
    assert len(ctx["data"]["nanoid"]) == 5

    mock_generate.side_effect = lambda size=21: "B" * size
    config2 = make_config_manager({"assign_nanoid.length": 21})
    task2 = AssignNanoidTask(config2)
    ctx2 = {}
    task2.run(ctx2)
    assert "data" in ctx2
    assert len(ctx2["data"]["nanoid"]) == 21


def test_invalid_length_values():
    for inval in (4, 22, "notint"):
        with pytest.raises(TaskError):
            AssignNanoidTask(make_config_manager({"assign_nanoid.length": inval}))


@patch("standard_step.context.assign_nanoid.generate")
@patch("standard_step.context.assign_nanoid.StatusManager")
def test_run_handles_exception_and_updates_status(mock_status_manager_cls, mock_generate):
    mock_generate.side_effect = Exception("Generation failed")
    mock_status_manager = MagicMock()
    mock_status_manager_cls.return_value = mock_status_manager

    config = make_config_manager({"assign_nanoid.length": 10})
    task = AssignNanoidTask(config)

    context = {}
    with pytest.raises(TaskError):
        task.run(context)

    mock_status_manager.update_status.assert_any_call(
        str(context.get("id", "unknown")), "failed",
        step=f"Task Failed: {task.TASK_SLUG}", error="Generation failed"
    )