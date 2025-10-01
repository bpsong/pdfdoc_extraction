import os
import sys
import json
import shutil
import threading
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from web.server import create_app
from modules.auth_utils import AuthError
from modules.file_processor import FileProcessor
from modules.status_manager import StatusManager

# Reset the StatusManager singleton before each test to avoid interference
@pytest.fixture(autouse=True)
def reset_status_manager():
    StatusManager._instance = None

# Shared fixture: setup a mock ConfigManager with a temporary processing directory.
@pytest.fixture
def mock_config_manager():
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

# Shared fixture used by StatusManager tests (kept name for compatibility)
@pytest.fixture
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

# Fixture specific to FileProcessor tests: simple mock workflow manager
@pytest.fixture
def mock_workflow_manager():
    return Mock()

# Authentication Tests
@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c

def test_login_success(client, monkeypatch):
    class FakeAuth:
        def __init__(self, *a, **k):
            self.token_exp_minutes = 30
        def login(self, u, p) -> str:
            if u == "admin" and p == "secret":
                return "fake.jwt.token"
            raise Exception("Invalid credentials")

    monkeypatch.setattr("modules.api_router.AuthUtils", FakeAuth)

    resp = client.post("/api/login", data={"username": "admin", "password": "secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "fake.jwt.token"
    assert data["token_type"] == "bearer"
    assert isinstance(data["expires_in"], int) and data["expires_in"] > 0

def test_login_invalid_credentials(client, monkeypatch):
    class FakeAuth:
        def __init__(self, *a, **k):
            self.token_exp_minutes = 30
        def login(self, u, p) -> str:
            # Raise the domain-specific error expected by the router
            raise AuthError("Invalid credentials")

    monkeypatch.setattr("modules.api_router.AuthUtils", FakeAuth)

    resp = client.post("/api/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401

# File Processor Tests
def test_file_processor_initialization_and_process_file(mock_config_manager, mock_workflow_manager):
    # Instantiate FileProcessor with mocks
    retry_func = lambda f, *args, **kwargs: f(*args, **kwargs)  # simple retry function that calls directly
    fp = FileProcessor(mock_config_manager, retry_func, mock_workflow_manager)

    # Patch StatusManager singleton to ensure it uses the injected ConfigManager
    sm = StatusManager(mock_config_manager)

    # Prepare test file path and unique_id
    test_file_path = os.path.join(fp.processing_folder_path, "testfile_uuid.pdf")
    unique_id = "test-uuid-1234"

    # Create an empty test file to simulate existing file
    with open(test_file_path, 'w') as f:
        f.write("Test content")

    # Call process_file and verify it returns True
    result = fp.process_file(test_file_path, unique_id, source="watch_folder", original_filename="testfile_uuid.pdf")
    assert result is True

    # Verify that status file was created by StatusManager
    status_file_path = os.path.join(fp.processing_folder_path, f"{unique_id}.txt")
    assert os.path.exists(status_file_path)

    # Verify workflow_manager.trigger_workflow_for_file was called with expected args
    mock_workflow_manager.trigger_workflow_for_file.assert_called_once()
    call_args = mock_workflow_manager.trigger_workflow_for_file.call_args[1]
    assert call_args['file_path'] == test_file_path
    assert call_args['unique_id'] == unique_id
    assert call_args['original_filename'] == "testfile_uuid.pdf"
    assert call_args['source'] == "watch_folder"

# Status Manager Tests
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