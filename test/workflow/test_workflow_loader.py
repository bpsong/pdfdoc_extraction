import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from modules.workflow_loader import WorkflowLoader
from modules.config_manager import ConfigManager
from modules.shutdown_manager import ShutdownManager
from modules.status_manager import StatusManager
import yaml

@pytest.fixture(autouse=True)
def reset_singletons():
    # Reset ConfigManager, StatusManager, and WorkflowLoader singletons before each test
    ConfigManager._instance = None
    StatusManager._instance = None
    WorkflowLoader._instance = None
    yield

@pytest.fixture
def config_path():
    return "test/data/workflow_loader_config.yaml"

@pytest.fixture
def initial_context():
    return {"id": "testfile123", "data": {}}

@pytest.fixture(autouse=True)
def mock_all_dependencies(mocker, config_path):
    # Mock ConfigManager's critical exits
    mocker.patch('modules.config_manager.sys.exit')
    mocker.patch('modules.config_manager.logging.Logger.critical')

    # Mock ShutdownManager's shutdown method
    mocker.patch.object(ShutdownManager, 'shutdown')

    # Mock StatusManager methods
    mocker.patch.object(StatusManager, 'update_status')
    mocker.patch.object(StatusManager, 'get_status')

    # Load the test config directly for mocking ConfigManager.get
    with open(config_path, 'r') as f:
        test_config_data = yaml.safe_load(f)

    # Create a mock ConfigManager instance
    mock_config_manager = MagicMock(spec=ConfigManager)
    def mock_get(key, default=None):
        if key == "all":
            return test_config_data
        return test_config_data.get(key, default)
    mock_config_manager.get.side_effect = mock_get
    mock_config_manager.get_all.return_value = test_config_data # Mock get_all for the new ConfigManager method

    # Instantiate WorkflowLoader *here* after all mocks are set up
    loader = WorkflowLoader(mock_config_manager)

    # Test-only: Patch the Prefect `task` decorator used in modules.workflow_loader
    # so wrapped task functions return a plain dict with a 'result' key. In the
    # application runtime Prefect wraps tasks and returns futures; in unit tests
    # we stub this behavior to run synchronously and make results deterministic.
    # This keeps the test fixture isolated from Prefect's runtime and avoids
    # spawning temporary Prefect servers during unit tests.
    def _fake_prefect_task(*dargs, **dkwargs):
        def _decorator(fn):
            def _wrapped(*args, **kwargs):
                res = fn(*args, **kwargs)
                # Prefect wrapped tasks sometimes return futures; tests expect
                # either a dict with 'result' or a direct dict. Return a dict
                # with 'result' to make loader.select the result branch.
                return {"result": res or {}}
            return _wrapped
        return _decorator

    mocker.patch('modules.workflow_loader.task', _fake_prefect_task)
    # Test-only: Patch the Prefect `flow` decorator used in modules.workflow_loader
    # to be a no-op so the flow function is returned directly and executed
    # synchronously within the test process. This prevents Prefect from
    # starting a temporary server during unit tests.
    def _fake_prefect_flow(*dargs, **dkwargs):
        def _decorator(fn):
            return fn
        return _decorator

    mocker.patch('modules.workflow_loader.flow', _fake_prefect_flow)

    # Test-only: Patch `get_run_logger` used inside wrapped tasks to return a
    # lightweight dummy logger. When tasks call logger.info/debug in production
    # they rely on Prefect's run context; in tests we provide a no-op logger to
    # avoid requiring Prefect runtime context.
    class _DummyLogger:
        def info(self, *args, **kwargs):
            return None
        def debug(self, *args, **kwargs):
            return None
        def warning(self, *args, **kwargs):
            return None
        def error(self, *args, **kwargs):
            return None

    mocker.patch('modules.workflow_loader.get_run_logger', lambda: _DummyLogger())

    # Define mock task classes with constructor accepting config_manager
    class MockExtractionTask:
        def __init__(self, config_manager, **params):
            self.config_manager = config_manager
            self.params = params
        def on_start(self, context):
            pass  # No-op for testing
        def run(self, context):
            context.setdefault('data', {})
            context['data']['extracted'] = True
            return context
        def validate_required_fields(self, context):
            pass
    
    class MockStorageTask:
        def __init__(self, config_manager, **params):
            self.config_manager = config_manager
            self.params = params
        def on_start(self, context):
            pass  # No-op for testing
        def run(self, context):
            context.setdefault('data', {})
            context['data']['stored'] = True
            return context
        def validate_required_fields(self, context):
            pass
    
    class MockCleanupTask:
        def __init__(self, config_manager, **params):
            self.config_manager = config_manager
            self.params = params
        def on_start(self, context):
            pass  # No-op for testing
        def run(self, context):
            context.setdefault('data', {})
            context['data']['cleaned_up'] = True # Add a flag to verify cleanup task ran
            return context
        def validate_required_fields(self, context):
            pass

    # Mock the direct import of CleanupTask to use our MockCleanupTask
    mocker.patch('modules.workflow_loader.CleanupTask', MockCleanupTask)

    def mock_import_task_class_side_effect(module_name, class_name): # Accept both module_name and class_name
        # Map config task names to mock classes
        class_name_mapping = {
            "MockExtractionTask": MockExtractionTask,
            "MockStorageTask": MockStorageTask,
            "MockCleanupTask": MockCleanupTask,
        }

        # Handle the actual task names from the config
        if class_name in class_name_mapping:
            return class_name_mapping[class_name]
        elif class_name == "UnrealTask":  # For import error test
            raise ImportError(f"Module {module_name}.{class_name} not found")
        elif class_name == "ErrorTask":  # For error test
            class ErrorTask:
                def __init__(self, config_manager, **params):
                    self.config_manager = config_manager
                    self.params = params
                def on_start(self, context):
                    pass
                def run(self, context):
                    context.setdefault('data', {})
                    context['data']['error'] = "Simulated Error"
                    context['error'] = "Simulated Error"  # Set top-level error to trigger stop logic
                    context['error_step'] = "error_task"
                    return context
                def validate_required_fields(self, context):
                    pass
            return ErrorTask
        else:
            # Default for other unmocked imports, if any
            class DefaultTask:
                def __init__(self, config_manager, **params):
                    self.config_manager = config_manager
                    self.params = params
                def on_start(self, context):
                    pass
                def run(self, context):
                    context.setdefault('data', {})
                    return context
                def validate_required_fields(self, context):
                    pass
            return DefaultTask

    # Patch _import_task_class method on the instance, not the class
    mocker.patch.object(loader, '_import_task_class', side_effect=mock_import_task_class_side_effect)

    return loader, test_config_data # Return both loader and test_config_data

@pytest.mark.parametrize("pipeline_slice", [
    slice(0, 2),  # Valid tasks: mock_extraction_task, mock_storage_task
    slice(0, 1),  # Single valid task: mock_extraction_task
])
def test_valid_flow_execution_param(initial_context, mock_all_dependencies, pipeline_slice):
    loader, test_config_data = mock_all_dependencies

    # Temporarily modify the pipeline in test_config_data for this test
    original_pipeline_names = test_config_data["pipeline"]
    test_config_data["pipeline"] = original_pipeline_names[pipeline_slice]

    # Update the loader's config to use the modified pipeline
    loader.cfg = test_config_data
    # Ensure task_defs reflects the modified config (tests mutate the config in-place)
    loader.task_defs = loader.cfg.get("tasks", {})

    flow = loader.load_workflow()
    assert flow is not None, "Flow should not be None for valid configuration"

    result_context = flow(initial_context)
    assert result_context.get("data", {}).get("extracted") is True
    if len(test_config_data["pipeline"]) > 1:
        assert result_context.get("data", {}).get("stored") is True
    assert result_context.get("data", {}).get("cleaned_up") is True # Assert cleanup task ran

@pytest.mark.parametrize("pipeline_indices", [
    [0, 4],  # Extraction and error task (indices from the full pipeline)
])
def test_flow_stops_on_error_param(initial_context, mock_all_dependencies, pipeline_indices):
    loader, test_config_data = mock_all_dependencies

    # Temporarily modify the pipeline in test_config_data for this test
    original_pipeline_names = test_config_data["pipeline"]
    test_config_data["pipeline"] = [original_pipeline_names[i] for i in pipeline_indices]

    # Update the loader's config to use the modified pipeline
    loader.cfg = test_config_data
    # Ensure task_defs reflects the modified config (tests mutate the config in-place)
    loader.task_defs = loader.cfg.get("tasks", {})

    flow = loader.load_workflow()

    result_context = flow(initial_context)
    assert "error" in result_context.get("data", {})
    assert "stored" not in result_context.get("data", {})
    assert "cleaned_up" in result_context.get("data", {})  # Housekeeping should still run

def test_housekeeping_runs_unconditionally_last(initial_context, mock_all_dependencies):
    """Test that housekeeping runs as the final step regardless of pipeline configuration."""
    loader, test_config_data = mock_all_dependencies

    # Set up a simple pipeline with one task
    test_config_data["pipeline"] = ["mock_extraction_task"]
    loader.cfg = test_config_data
    loader.task_defs = loader.cfg.get("tasks", {})

    flow = loader.load_workflow()
    assert flow is not None

    result_context = flow(initial_context)

    # Verify that housekeeping ran and set the cleaned_up flag
    assert result_context.get("data", {}).get("cleaned_up") is True
    assert result_context.get("data", {}).get("extracted") is True

def test_housekeeping_runs_despite_previous_task_failures(initial_context, mock_all_dependencies):
    """Test that housekeeping executes even when previous tasks fail."""
    loader, test_config_data = mock_all_dependencies

    # Set up pipeline with a failing task followed by a successful task
    test_config_data["pipeline"] = ["error_task", "mock_storage_task"]
    loader.cfg = test_config_data
    loader.task_defs = loader.cfg.get("tasks", {})

    flow = loader.load_workflow()
    assert flow is not None

    result_context = flow(initial_context)

    # Verify that housekeeping ran despite the error in error_task
    assert result_context.get("data", {}).get("cleaned_up") is True
    # The error_task should have set an error
    assert "error" in result_context.get("data", {})
    # The storage_task should not have run due to the error and on_error: stop
    assert "stored" not in result_context.get("data", {})

def test_housekeeping_runs_with_empty_pipeline(initial_context, mock_all_dependencies):
    """Test that housekeeping runs even when pipeline is empty."""
    loader, test_config_data = mock_all_dependencies

    # Set up empty pipeline
    test_config_data["pipeline"] = []
    loader.cfg = test_config_data
    loader.task_defs = loader.cfg.get("tasks", {})

    flow = loader.load_workflow()
    assert flow is not None

    result_context = flow(initial_context)

    # Verify that housekeeping still ran even with no pipeline tasks
    assert result_context.get("data", {}).get("cleaned_up") is True
    # No other task flags should be present
    assert "extracted" not in result_context.get("data", {})
    assert "stored" not in result_context.get("data", {})

def test_housekeeping_execution_order_verification(initial_context, mock_all_dependencies, mocker):
    """Test that housekeeping is the final step in execution order."""
    loader, test_config_data = mock_all_dependencies

    # Track execution order
    execution_order = []

    # Create spy versions of the mock tasks to track execution
    class SpyExtractionTask:
        def __init__(self, config_manager, **params):
            self.config_manager = config_manager
            self.params = params
        def on_start(self, context):
            execution_order.append("extraction_start")
        def run(self, context):
            execution_order.append("extraction_run")
            context.setdefault('data', {})
            context['data']['extracted'] = True
            return context
        def validate_required_fields(self, context):
            pass

    class SpyCleanupTask:
        def __init__(self, config_manager, **params):
            self.config_manager = config_manager
            self.params = params
        def on_start(self, context):
            execution_order.append("cleanup_start")
        def run(self, context):
            execution_order.append("cleanup_run")
            context.setdefault('data', {})
            context['data']['cleaned_up'] = True
            return context
        def validate_required_fields(self, context):
            pass

    # Replace the mock tasks with spy versions
    mocker.patch('modules.workflow_loader.CleanupTask', SpyCleanupTask)

    def spy_import_task_class_side_effect(module_name, class_name):
        if class_name == "MockExtractionTask":
            return SpyExtractionTask
        elif class_name == "MockCleanupTask":
            return SpyCleanupTask
        else:
            # Use default for others
            class DefaultTask:
                def __init__(self, config_manager, **params):
                    self.config_manager = config_manager
                    self.params = params
                def on_start(self, context):
                    pass
                def run(self, context):
                    context.setdefault('data', {})
                    return context
                def validate_required_fields(self, context):
                    pass
            return DefaultTask

    mocker.patch.object(loader, '_import_task_class', side_effect=spy_import_task_class_side_effect)

    # Set up pipeline with extraction task
    test_config_data["pipeline"] = ["mock_extraction_task"]
    loader.cfg = test_config_data
    loader.task_defs = loader.cfg.get("tasks", {})

    flow = loader.load_workflow()
    result_context = flow(initial_context)

    # Verify execution order: extraction should run before cleanup
    assert "extraction_run" in execution_order
    assert "cleanup_run" in execution_order

    # Cleanup should be the last executed step
    extraction_run_index = execution_order.index("extraction_run")
    cleanup_run_index = execution_order.index("cleanup_run")
    assert cleanup_run_index > extraction_run_index

    # Verify final state
    assert result_context.get("data", {}).get("extracted") is True
    assert result_context.get("data", {}).get("cleaned_up") is True