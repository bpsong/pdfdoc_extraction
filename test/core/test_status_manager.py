import pytest
import json
import os
import sys
import threading
from unittest.mock import Mock
import shutil

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.status_manager import StatusManager

# Reset the StatusManager singleton before each test to avoid interference
@pytest.fixture(autouse=True)
def reset_status_manager():
    StatusManager._instance = None

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # Setup mock ConfigManager with get method returning test_processing_folder
    mock_config = Mock()
    # Use a temporary directory to ensure clean test isolation
    import tempfile
    test_dir = tempfile.mkdtemp(prefix='test_processing_folder')
    # Set up the mock to return the test directory for watch_folder.processing_dir
    mock_config.get.side_effect = lambda key, default=None: test_dir if key == 'watch_folder.processing_dir' else default
    # Store the actual path for test assertions
    mock_config.test_dir = test_dir
    yield mock_config
    # Cleanup after tests
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

def test_create_status_creates_file_with_correct_content(setup_and_teardown):
    sm = StatusManager(setup_and_teardown)
    unique_id = "uuid-1234"
    original_filename = "file1.pdf"
    source = "web_upload"
    file_path = "/some/path/file1.pdf"

    sm.create_status(unique_id, original_filename, source, file_path)

    status_file = os.path.join(setup_and_teardown.test_dir, f'{unique_id}.txt')
    assert os.path.exists(status_file), "Status file was not created"

    with open(status_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert data['id'] == unique_id
    assert data['original_filename'] == original_filename
    assert data['source'] == source
    assert data['file'] == "file1.pdf"
    assert data['status'] == "Pending"
    assert 'created' in data['timestamps']
    assert 'pending' in data['timestamps']
    assert data['error'] is None
    assert isinstance(data['details'], dict)

def test_update_status_updates_existing_file(setup_and_teardown):
    sm = StatusManager(setup_and_teardown)
    unique_id = "uuid-5678"
    original_filename = "file2.pdf"
    source = "watch_folder"
    file_path = "/some/path/file2.pdf"

    sm.create_status(unique_id, original_filename, source, file_path)

    sm.update_status(unique_id, status="Processing", step="Step1")
    sm.update_status(unique_id, status="Completed", step="Step2", error=None, details={"key": "value"})

    status_file = os.path.join(setup_and_teardown.test_dir, f'{unique_id}.txt')
    with open(status_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert data['status'] == "Completed"
    assert 'Step1' in data['timestamps']
    assert 'Step2' in data['timestamps']
    assert data['error'] is None
    assert data['details'].get('key') == "value"

def test_update_status_creates_file_if_missing(setup_and_teardown):
    sm = StatusManager(setup_and_teardown)
    unique_id = "missingfile"
    # Ensure no status file exists
    status_file = os.path.join(setup_and_teardown.test_dir, f'{unique_id}.txt')
    if os.path.exists(status_file):
        os.remove(status_file)

    sm.update_status(unique_id, status="Error", error="Test error")

    assert os.path.exists(status_file), "Status file was not created on update"

    with open(status_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert data['status'] == "Error"
    assert data['error'] == "Test error"

def test_get_status_returns_correct_data(setup_and_teardown):
    sm = StatusManager(setup_and_teardown)
    unique_id = "uuid-91011"
    original_filename = "file3.pdf"
    source = "web_upload"
    file_path = "/some/path/file3.pdf"

    sm.create_status(unique_id, original_filename, source, file_path)

    status = sm.get_status(unique_id)
    assert status is not None
    assert status['id'] == unique_id

def test_get_status_returns_none_if_file_missing(setup_and_teardown):
    sm = StatusManager(setup_and_teardown)
    unique_id = "nonexistent"
    status_file = os.path.join(setup_and_teardown.test_dir, f'{unique_id}.txt')
    if os.path.exists(status_file):
        os.remove(status_file)

    status = sm.get_status(unique_id)
    assert status is None

def test_cleanup_status_files_removes_completed_and_error(setup_and_teardown):
    sm = StatusManager(setup_and_teardown)
    # Create files with different statuses
    files = {
        "completed.txt": {"status": "Completed"},
        "error.txt": {"status": "Error"},
        "pending.txt": {"status": "Pending"},
        "other.txt": {"status": "Other"}
    }
    for filename, content in files.items():
        path = os.path.join(setup_and_teardown.test_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f)

    sm.cleanup_status_files()

    remaining_files = os.listdir(setup_and_teardown.test_dir)
    assert "pending.txt" in remaining_files
    assert "other.txt" in remaining_files
    assert "completed.txt" not in remaining_files
    assert "error.txt" not in remaining_files

def test_thread_safety_of_updates(setup_and_teardown):
    sm = StatusManager(setup_and_teardown)
    unique_id = "uuid-thread"
    original_filename = "threadsafe.pdf"
    source = "web_upload"
    file_path = "/some/path/threadsafe.pdf"

    sm.create_status(unique_id, original_filename, source, file_path)

    def update_status():
        for _ in range(10):
            sm.update_status(unique_id, status="Processing", step="ThreadTest")

    threads = [threading.Thread(target=update_status) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    status_file = os.path.join(setup_and_teardown.test_dir, f'{unique_id}.txt')
    with open(status_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert data['status'] == "Processing"
    assert 'ThreadTest' in data['timestamps']

if __name__ == "__main__":
    pytest.main()