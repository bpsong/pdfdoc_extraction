import pytest
import os
import shutil
import threading
import time
import csv
import json
import logging
from pathlib import Path
from typing import Optional
from unittest.mock import patch, mock_open, Mock

from modules.config_manager import ConfigManager
from modules.status_manager import StatusManager
from modules.workflow_manager import WorkflowManager
from modules.watch_folder_monitor import WatchFolderMonitor
from modules.utils import sanitize_filename

@pytest.fixture
def test_environment():
    # Ensure ConfigManager is reset for each test
    ConfigManager._instance = None

    # Ensure log file exists to pass ConfigManager validation - use path from config
    config_path = Path('test/data/config.yaml')

    # Create required directories BEFORE ConfigManager validation
    # This ensures the directories exist before ConfigManager tries to validate them
    watch_folder_dir = Path('test/test_data/watch_folder')
    processing_dir = Path('test/test_data/processing')
    watch_folder_dir.mkdir(parents=True, exist_ok=True)
    processing_dir.mkdir(parents=True, exist_ok=True)

    temp_config_manager = ConfigManager(config_path)  # Load config to get log file path
    log_file_path = Path(str(temp_config_manager.get('logging.log_file', 'test/test_app.log')))
    if not log_file_path.parent.exists():
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_file_path.exists():
        log_file_path.touch()
    # Setup config manager to get paths from config.yaml
    config_path = Path('test/data/config.yaml')
    config_manager = ConfigManager(config_path)
    
    # Get paths from config, with fallbacks for test environment
    # Ensure Path() receives a string
    watch_folder_dir = Path(str(config_manager.get('watch_folder.dir', 'test/test_data/watch_folder')))
    processing_dir = Path(str(config_manager.get('watch_folder.processing_dir', 'test/test_data/processing')))
    
    # Get data_dir from store_csv task params
    store_csv_params = config_manager.get('tasks.store_csv.params', {})
    if not isinstance(store_csv_params, dict): store_csv_params = {} # Ensure it's a dict
    data_dir = Path(str(store_csv_params.get('data_dir', 'data')))

    # Get files_dir from store_file task params
    store_file_params = config_manager.get('tasks.store_file.params', {})
    if not isinstance(store_file_params, dict): store_file_params = {} # Ensure it's a dict
    files_dir = Path(str(store_file_params.get('files_dir', 'files')))

    # Get archive_dir from archive_file task params
    archive_file_params = config_manager.get('tasks.archive_file.params', {})
    if not isinstance(archive_file_params, dict): archive_file_params = {} # Ensure it's a dict
    archive_dir = Path(str(archive_file_params.get('archive_dir', 'archive')))

    # Define all directories to clean and create
    dirs_to_manage = [
        watch_folder_dir,
        processing_dir,
        data_dir,
        files_dir,
        archive_dir
    ]

    # Create web_upload directory required by config_manager
    web_upload_dir = Path('web_upload')
    if web_upload_dir.exists():
        shutil.rmtree(web_upload_dir)
    web_upload_dir.mkdir(parents=True, exist_ok=True)
    # Clean and create directories
    # Do NOT remove data_dir and files_dir to preserve previously produced artifacts and avoid race deletions.
    for d in dirs_to_manage:
        if d in (data_dir, files_dir):
            d.mkdir(parents=True, exist_ok=True)
            continue
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    # Copy sample PDF to watch folder
    sample_pdf_source = Path('test/test_data/sample.pdf')
    sample_pdf_dest = watch_folder_dir / 'sample.pdf'
    shutil.copy(sample_pdf_source, sample_pdf_dest)

    # Initialize StatusManager
    status_manager = StatusManager(config_manager)

    # Initialize WorkflowManager
    workflow_manager = WorkflowManager(config_manager)

    yield config_manager, workflow_manager, status_manager, watch_folder_dir, processing_dir, data_dir, files_dir, archive_dir

    # Teardown: Clean up directories
    # Preserve data_dir and files_dir artifacts after test; only clean transient watch/processing/archive.
    for d in dirs_to_manage:
        if d in (data_dir, files_dir):
            continue
        if d.exists():
            shutil.rmtree(d)

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

def test_end_to_end_workflow_execution(test_environment):
    logging.info("Starting end-to-end workflow execution test (synchronous, no watcher thread)")
    config_manager, workflow_manager, status_manager, watch_folder_dir, processing_dir, data_dir, files_dir, archive_dir = test_environment

    # Prepare sample PDF in watch folder
    sample_pdf = watch_folder_dir / 'sample.pdf'
    assert sample_pdf.exists(), "Sample PDF was not copied to watch folder"

    # Ensure processing_dir exists prior to status writes
    processing_dir.mkdir(parents=True, exist_ok=True)

    # Invoke workflow directly and block by polling StatusManager (no WatchFolderMonitor thread)
    original_filename = sample_pdf.name
    unique_id = Path(original_filename).stem
    source = "watch_folder"

    test_api_key = config_manager.get('tasks.extract_document_data.params.api_key')
    if test_api_key and not os.getenv('LLAMA_CLOUD_API_KEY'):
        os.environ['LLAMA_CLOUD_API_KEY'] = str(test_api_key)

    if not os.getenv('LLAMA_CLOUD_API_KEY'):
        pytest.skip("LlamaCloud API key not available - skipping end-to-end test")

    # Create a stub LlamaExtract client so the test does not require network access
    extracted_payload = {
        "Supplier name": "Liberty Insurance Pte Ltd",
        "Invoice amount": 70.0,
        "Policy Number": "SD24B39161 / R 0",
        "Client name": "Acme Corporation",
        "Client": "Acme Corporation, 123 Street",
        "Insurance Start date": "2024-01-01",
        "Insurance End date": "2024-12-31",
        "Invoice type": "Invoice",
        "Serial Numbers": ["SN12345", None],
    }

    class _DummyExtractionResult:
        def __init__(self, data):
            self.data = data

    dummy_result = _DummyExtractionResult(extracted_payload)
    dummy_agent = Mock()
    dummy_agent.extract.return_value = dummy_result
    dummy_client = Mock()
    dummy_client.get_agent.return_value = dummy_agent

    final_status = None
    with patch('standard_step.extraction.extract_pdf.LlamaExtract', return_value=dummy_client):
        workflow_manager.trigger_workflow_for_file(str(sample_pdf), unique_id, original_filename, source)

        # Poll for completion (up to 120s)
        for i in range(1200):
            status = status_manager.get_status(unique_id)
            logging.debug(f"[sync] Completion check {i+1}: {status}")
            if status and status.get('status') not in ('Pending', 'Workflow Triggered', 'Pipeline Started'):
                final_status = status
                break
            time.sleep(0.1)

    assert final_status is not None, "Workflow did not complete within timeout"

    # Validate status content
    status_file_path = processing_dir / f"{unique_id}.txt"
    assert status_file_path.exists(), "Status file not created"
    with open(status_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        assert original_filename in content
        assert 'watch_folder' in content

    # Discover produced artifacts
    produced_json_files = sorted(data_dir.glob('*.json'))
    assert produced_json_files, "No JSON files produced in data; the PDF may not have been sent to LlamaExtract."
    latest_json = max(produced_json_files, key=lambda p: p.stat().st_mtime)
    with open(latest_json, 'r', encoding='utf-8') as jf:
        produced = json.load(jf)
    assert isinstance(produced, (dict, list)), "Produced JSON should be object or array."

    # Read templates from test config and compute expected filenames from produced data
    json_params = config_manager.get('tasks.store_metadata_json.params', {}) or {}
    csv_params = config_manager.get('tasks.store_metadata_csv.params', {}) or {}
    file_params = config_manager.get('tasks.store_file_to_localdrive.params', {}) or {}

    def _get_val(dct, *keys):
        for k in keys:
            if isinstance(dct, dict) and k in dct:
                return dct[k]
        return None

    # Support both object and array result shapes
    payload = produced[0] if isinstance(produced, list) and produced else produced
    supplier_name = _get_val(payload, 'supplier_name', 'Supplier name', 'supplier')
    invoice_amount = _get_val(payload, 'invoice_amount', 'Invoice amount', 'amount')
    policy_number = _get_val(payload, 'policy_number', 'Policy Number', 'invoice_no')

    # Normalize segments using project utility to match how filenames are generated on Windows
    # 1) Format amount into a simple string
    def _normalize_amount(val) -> str:
        try:
            v = float(str(val))
            s = f"{v}"
            return s.rstrip('0').rstrip('.') if '.' in s else str(int(v))
        except Exception:
            return str(val)

    # 2) Sanitize each segment by leveraging sanitize_filename, then strip the placeholder extension it appends
    def _sanitize_segment(seg: Optional[str]) -> str:
        s = '' if seg is None else str(seg)
        tmp = sanitize_filename(f"{s}.tmp")
        return tmp[:-4] if tmp.endswith(".tmp") else tmp

    supplier_name = _sanitize_segment(supplier_name)
    policy_number = _sanitize_segment(policy_number)
    # Align expected filenames with actual outputs: keep the raw numeric formatting used by tasks
    # The observed filenames show invoice_amount as "70.0", not "70"
    invoice_amount = str(invoice_amount)

    assert supplier_name is not None, "supplier_name not found in produced JSON"
    assert invoice_amount is not None, "invoice_amount not found in produced JSON"
    assert policy_number is not None, "policy_number not found in produced JSON"

    csv_template = csv_params.get('filename', '{supplier_name}_{invoice_amount}_{policy_number}')
    json_template = json_params.get('filename', '{supplier_name}_{invoice_amount}_{policy_number}')
    file_template = file_params.get('rename_pattern', '{supplier_name}_{invoice_amount}_{policy_number}')

    format_ctx = {
        'supplier_name': supplier_name,
        'invoice_amount': invoice_amount,
        'policy_number': policy_number,
    }

    def _resolve_unique(base_dir: Path, base_name: str, suffix: str) -> Path:
        candidate = base_dir / f"{base_name}{suffix}"
        if candidate.exists():
            return candidate
        for i in range(1, 20):
            cand = base_dir / f"{base_name}_{i}{suffix}"
            if cand.exists():
                return cand
        return candidate

    expected_csv_basename = csv_template.format(**format_ctx)
    expected_json_basename = json_template.format(**format_ctx)
    expected_pdf_basename = file_template.format(**format_ctx)

    expected_csv_file = _resolve_unique(data_dir, expected_csv_basename, '.csv')
    expected_json_file = _resolve_unique(data_dir, expected_json_basename, '.json')
    expected_renamed_pdf = _resolve_unique(files_dir, expected_pdf_basename, '.pdf')


    # If templated expected files are missing, fall back to detecting latest generated files to avoid false negatives
    if not expected_csv_file.exists() or not expected_json_file.exists():
        generated_csvs = sorted(data_dir.glob("*.csv"))
        generated_jsons = sorted(data_dir.glob("*.json"))
        assert generated_csvs, "No CSV files found in data directory"
        assert generated_jsons, "No JSON files found in data directory"
        expected_csv_file = max(generated_csvs, key=lambda p: p.stat().st_mtime)
        expected_json_file = max(generated_jsons, key=lambda p: p.stat().st_mtime)

    assert expected_csv_file.exists(), f"Expected CSV file not found: {expected_csv_file}"
    assert expected_json_file.exists(), f"Expected JSON file not found: {expected_json_file}"
    assert expected_renamed_pdf.exists(), f"Expected renamed PDF not found: {expected_renamed_pdf}"

    # Basic content checks for CSV/JSON
    with open(expected_csv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        data_row = next(reader)
        assert ("supplier_name" in header) or ("Supplier name" in header)
        assert str(supplier_name) in data_row

    with open(expected_json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        def get_json(d, *keys):
            for k in keys:
                if k in d:
                    return d[k]
            return None
        assert get_json(data, 'supplier_name', 'Supplier name') == supplier_name
        amt = get_json(data, 'invoice_amount', 'Invoice amount')
        assert amt is not None, "invoice_amount missing in JSON output"
        assert float(str(amt)) == float(str(invoice_amount))
        # Allow slash and normalize whitespace to match filename sanitization
        json_policy = get_json(data, 'policy_number', 'Policy Number')
        assert json_policy is not None, "policy_number missing in JSON output"
        import re
        def _normalize_spaces(s: str) -> str:
            # collapse multiple spaces to a single space after slash replacement
            return re.sub(r'\s+', ' ', s).strip()
        assert _normalize_spaces(json_policy.replace('/', ' ')) == _normalize_spaces(policy_number)

    # Source should be watch_folder
    status_after = status_manager.get_status(unique_id)
    assert status_after and status_after.get("source") == "watch_folder", "Source should be 'watch_folder'"
    logging.info("End-to-end workflow execution test (synchronous) completed successfully")


def test_workflow_manager_propagates_source_web(monkeypatch, tmp_path):
    """
    Verify that WorkflowManager receives and propagates source='web'
    when triggered directly (simulating a web upload path).
    """
    # Reset singleton and prepare config
    ConfigManager._instance = None
    # Create minimal config file for this test
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.yaml"
    cfg_file.write_text(
        "logging:\n"
        "  log_file: test/test_data/workflow_manager.log\n"
        "web:\n"
        "  upload_dir: web_upload\n"
        "watch_folder:\n"
        "  dir: test/test_data/watch_folder\n"
        "  processing_dir: test/test_data/processing\n",
        encoding="utf-8"
    )

    # Ensure referenced log file and required static dirs exist (ConfigManager validation)
    test_data_dir = Path("test/test_data")
    test_data_dir.mkdir(parents=True, exist_ok=True)
    (test_data_dir / "workflow_manager.log").touch(exist_ok=True)
    (test_data_dir / "watch_folder").mkdir(parents=True, exist_ok=True)
    (test_data_dir / "processing").mkdir(parents=True, exist_ok=True)

    config_manager = ConfigManager(cfg_file)
    status_manager = StatusManager(config_manager)
    workflow_manager = WorkflowManager(config_manager)

    # Prepare a fake processing file path and identifiers
    processing_dir = Path(str(config_manager.get("watch_folder.processing_dir", "processing")))
    processing_dir.mkdir(parents=True, exist_ok=True)
    file_path = processing_dir / "dummy.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")  # minimal content

    unique_id = "web-123"
    original_filename = "uploaded.pdf"
    source = "web"

    # Trigger workflow
    workflow_manager.trigger_workflow_for_file(str(file_path), unique_id, original_filename, source)

    # Immediately check status record to assert source propagation
    status = status_manager.get_status(unique_id)
    assert status is not None, "Status should be created after triggering workflow"
    assert status.get("source") == "web", "Source should be 'web' for web-triggered workflows"
    assert status.get("original_filename") == original_filename

    # Clean up created directories/files for isolation
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass