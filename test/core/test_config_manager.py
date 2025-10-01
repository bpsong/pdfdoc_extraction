import pytest
import os
import sys
import yaml
import logging
from unittest.mock import patch, MagicMock
from tempfile import TemporaryDirectory, NamedTemporaryFile
from pathlib import Path

# Adjust the path to import ConfigManager from modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.config_manager import ConfigManager

# Fixture for a temporary directory
@pytest.fixture
def temp_dir():
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

# Helper function to write a config file
def write_config_file(path: Path, content: dict):
    with open(path, 'w') as f:
        yaml.dump(content, f)

# Helper function to create a dummy file
def create_dummy_file(path: Path):
    path.write_text("dummy content")

# Helper function to create a dummy directory
def create_dummy_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

# Reset ConfigManager singleton before each test
@pytest.fixture(autouse=True)
def reset_config_manager_singleton():
    ConfigManager._instance = None
    yield

# --- Test Cases ---

def test_initialization_and_loading_valid_config(temp_dir):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')},
        'pipeline': {
            'steps': [
                {'name': 'step1', 'input_dir': str(temp_dir / 'pipeline_input')},
                {'name': 'step2', 'output_file': str(temp_dir / 'pipeline_output.txt')}
            ]
        }
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()
    (temp_dir / 'pipeline_input').mkdir()
    
    # Create necessary files for dynamic paths
    create_dummy_file(temp_dir / 'pipeline_output.txt')
    # Create log file required by dynamic validation (_file keys)
    create_dummy_file(temp_dir / 'logs' / 'app.log')

    manager = ConfigManager(config_path)
    assert manager.config == config_content
    assert ConfigManager._instance is not None

def test_singleton_behavior(temp_dir):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')}
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()
    # Create log file required by dynamic validation
    create_dummy_file(temp_dir / 'logs' / 'app.log')

    manager1 = ConfigManager(config_path)
    manager2 = ConfigManager(config_path)
    assert manager1 is manager2
    assert manager1.config == manager2.config

def test_get_method_retrieves_values_correctly(temp_dir):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')},
        'level1': {
            'level2': {
                'key': 'value',
                'number': 123
            }
        },
        'list_key': [1, 2, 3]
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()
    
    # Create log file required by dynamic validation
    create_dummy_file(temp_dir / 'logs' / 'app.log')
    
    manager = ConfigManager(config_path)

    assert manager.get('level1.level2.key') == 'value'
    assert manager.get('level1.level2.number') == 123
    assert manager.get('list_key') == [1, 2, 3]

def test_get_method_returns_default_when_keys_missing(temp_dir):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')},
        'level1': {'key': 'value'}
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()
    
    # Create log file required by dynamic validation
    create_dummy_file(temp_dir / 'logs' / 'app.log')
    
    manager = ConfigManager(config_path)

    assert manager.get('non_existent_key') is None
    assert manager.get('non_existent_key', 'default_value') == 'default_value'
    assert manager.get('level1.non_existent_key', 0) == 0
    assert manager.get('level1.key') == 'value' # Ensure existing keys still work

# --- Error Handling on Config Loading ---

def test_missing_config_file_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    config_path = temp_dir / 'non_existent_config.yaml'
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    # Updated assertion to match actual log message
    assert "Error reading configuration file" in caplog.text

def test_invalid_yaml_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    config_path = temp_dir / 'invalid.yaml'
    with open(config_path, 'w') as f:
        f.write("key: - value\n  another_key:") # Invalid YAML
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    assert "Invalid YAML in configuration file" in caplog.text

def test_config_root_not_a_dictionary_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    config_path = temp_dir / 'not_dict.yaml'
    with open(config_path, 'w') as f:
        f.write("- item1\n- item2") # Root is a list, not a dictionary
    
    # Create necessary directories for static paths to allow validation to proceed
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    assert "Configuration file root must be a dictionary" in caplog.text

# --- Static Path Validations ---

def test_web_upload_dir_is_file_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads_file')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')}
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for other static paths
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()
    create_dummy_file(temp_dir / 'uploads_file') # This should be a directory, not a file

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    # Updated message to current implementation wording
    assert "Static path invalid: 'web.upload_dir'" in caplog.text

def test_watch_folder_dir_is_file_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch_file')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')}
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for other static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'logs').mkdir()
    create_dummy_file(temp_dir / 'watch_file') # This should be a directory, not a file

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    # Updated to reflect static validation for watch_folder.dir
    assert "Static path invalid: 'watch_folder.dir'" in caplog.text

def test_logging_log_file_parent_is_file_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs_file' / 'app.log')}
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for other static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    create_dummy_file(temp_dir / 'logs_file') # This should be a directory, not a file
    
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    # Updated to match current dynamic validation wording for _file check
    assert "does not exist or isn’t a file" in caplog.text

# --- Dynamic Path Validations ---

def test_dynamic_path_validation_missing_dir_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    """
    Ensure that when a *_dir dynamic path points to a non-existent directory,
    ConfigManager logs critical and exits. Because _precreate_required_directories()
    will attempt to create *_dir directories before validation, we use a path
    that cannot be created (e.g., invalid characters on Windows) to force failure.
    """
    # On Windows, characters like "?" are invalid in folder names
    invalid_dir_name = "non_existent_pipeline_input?invalid"
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')},
        'pipeline': {
            'steps': [
                {'name': 'step1', 'input_dir': str(temp_dir / invalid_dir_name)}
            ]
        }
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()
    # Create log file required by dynamic validation
    create_dummy_file(temp_dir / 'logs' / 'app.log')
    
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    # Accept either pre-create failure or dynamic validation message
    assert ("Could not create directory" in caplog.text) or ("does not exist or isn’t a directory" in caplog.text)

def test_dynamic_path_validation_dir_is_file_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')},
        'pipeline': {
            'steps': [
                {'name': 'step1', 'input_dir': str(temp_dir / 'pipeline_input_file')}
            ]
        }
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()
    # Create log file required by dynamic validation
    create_dummy_file(temp_dir / 'logs' / 'app.log')
    create_dummy_file(temp_dir / 'pipeline_input_file') # This should be a directory, not a file
    
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    # The pre-create step may attempt to mkdir and fail because a file exists with that name.
    # Accept either the dynamic validation message or the precreate failure.
    assert ("does not exist or isn’t a directory" in caplog.text) or ("Could not create directory" in caplog.text)

def test_dynamic_path_validation_missing_file_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')},
        'pipeline': {
            'steps': [
                {'name': 'step1', 'output_file': str(temp_dir / 'non_existent_output.txt')}
            ]
        }
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()
    # Create log file required by dynamic validation
    create_dummy_file(temp_dir / 'logs' / 'app.log')
    
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    # Updated to match current dynamic validation message
    assert "does not exist or isn’t a file" in caplog.text

def test_dynamic_path_validation_file_is_dir_triggers_critical_log_and_sys_exit(temp_dir, caplog):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')},
        'pipeline': {
            'steps': [
                {'name': 'step1', 'output_file': str(temp_dir / 'output_dir')}
            ]
        }
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()
    # Create log file required by dynamic validation
    create_dummy_file(temp_dir / 'logs' / 'app.log')
    create_dummy_dir(temp_dir / 'output_dir') # This should be a file, not a directory

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        ConfigManager(config_path)
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 1
    # Updated wording in implementation
    assert "does not exist or isn’t a file" in caplog.text

def test_dynamic_path_validation_with_list_in_pipeline(temp_dir, caplog):
    config_content = {
        'web': {'upload_dir': str(temp_dir / 'uploads')},
        'watch_folder': {'dir': str(temp_dir / 'watch')},
        'logging': {'log_file': str(temp_dir / 'logs' / 'app.log')},
        'pipeline': [
            {'name': 'step1', 'module': 'standard_step.storage.store_metadata_as_csv', 'class': 'StoreMetadataAsCsvTask', 'params': {'data_dir': str(temp_dir / 'pipeline_data_list')}},
            {'name': 'step2', 'module': 'standard_step.storage.store_file_to_localdrive', 'class': 'StoreFileToLocalDriveTask', 'params': {'files_dir': str(temp_dir / 'pipeline_files_list')}}
        ],
        'tasks': {
            'step1': {'module': 'standard_step.storage.store_metadata_as_csv', 'class': 'StoreMetadataAsCsvTask', 'params': {'data_dir': str(temp_dir / 'pipeline_data_list')}},
            'step2': {'module': 'standard_step.storage.store_file_to_localdrive', 'class': 'StoreFileToLocalDriveTask', 'params': {'files_dir': str(temp_dir / 'pipeline_files_list')}}
        }
    }
    config_path = temp_dir / 'config.yaml'
    write_config_file(config_path, config_content)

    # Create necessary directories for static paths
    (temp_dir / 'uploads').mkdir()
    (temp_dir / 'watch').mkdir()
    (temp_dir / 'logs').mkdir()

    # Create necessary directories for dynamic paths in the list
    (temp_dir / 'pipeline_data_list').mkdir()
    (temp_dir / 'pipeline_files_list').mkdir()
    # Create log file required by dynamic validation
    create_dummy_file(temp_dir / 'logs' / 'app.log')
    
    manager = ConfigManager(config_path)
    assert manager.config == config_content
    # Ensure no dynamic validation error messages present (updated wording)
    assert "does not exist or isn’t a directory" not in caplog.text
    assert "does not exist or isn’t a file" not in caplog.text
