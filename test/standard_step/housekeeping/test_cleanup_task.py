import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from standard_step.housekeeping.cleanup_task import CleanupTask
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError

@pytest.fixture
def config_manager():
    # Provide a dummy ConfigManager instance or mock as needed
    return MagicMock(spec=ConfigManager)

@pytest.fixture
def cleanup_task(config_manager):
    return CleanupTask(config_manager=config_manager, processing_dir=Path("test_processing_dir"))

def test_validate_required_fields_missing_processing_dir(config_manager):
    task = CleanupTask(config_manager=config_manager)
    with patch.object(task, 'processing_dir', None):
        with pytest.raises(TaskError):
            task.validate_required_fields({})

def test_run_successful_cleanup_retains_status_file(tmp_path, cleanup_task):
    # Create a dummy PDF file to delete
    test_file = tmp_path / "testfile.pdf"
    test_file.write_text("dummy content")
    # Create a dummy status file that should be retained
    status_file = tmp_path / "testfile.txt"
    status_file.write_text("status content")

    context = {
        "file_path": str(test_file),
        "id": "1234"
    }
    cleanup_task.params['processing_dir'] = tmp_path
    cleanup_task.logger = MagicMock()

    cleanup_task.run(context)

    # Assert the PDF file is deleted
    assert not test_file.exists()
    # Assert the status file still exists
    assert status_file.exists()
    cleanup_task.logger.info.assert_any_call(f"Removed processed file: {test_file}")

def test_run_missing_file_path_logs_warning(cleanup_task):
    cleanup_task.logger = MagicMock()
    context = {"id": "1234"}
    cleanup_task.run(context)
    cleanup_task.logger.warning.assert_called_with("Missing file_path in context for cleanup. Skipping.")

def test_run_nonexistent_file_logs_warning(tmp_path, cleanup_task):
    cleanup_task.logger = MagicMock()
    fake_file = tmp_path / "nonexistent.pdf"
    context = {"file_path": str(fake_file), "id": "1234"}
    cleanup_task.run(context)
    cleanup_task.logger.warning.assert_called_with(f"File {fake_file} not found for cleanup. Skipping.")

def test_run_file_deletion_failure(tmp_path, cleanup_task):
    test_file = tmp_path / "testfile.pdf"
    test_file.write_text("dummy content")
    context = {"file_path": str(test_file), "id": "1234"}
    cleanup_task.params['processing_dir'] = tmp_path
    cleanup_task.logger = MagicMock()

    # Patch unlink to raise an exception
    with patch.object(Path, "unlink", side_effect=PermissionError("Permission denied")):
        with pytest.raises(TaskError):
            cleanup_task.run(context)
        cleanup_task.logger.error.assert_called()

def test_run_does_not_return_context(tmp_path, cleanup_task):
    test_file = tmp_path / "testfile.pdf"
    test_file.write_text("dummy content")
    context = {"file_path": str(test_file), "id": "1234"}
    cleanup_task.params['processing_dir'] = tmp_path
    result = cleanup_task.run(context)
    assert result is None