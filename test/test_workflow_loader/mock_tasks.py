"""Mock task classes for workflow loader testing."""

from modules.base_task import BaseTask
from modules.config_manager import ConfigManager


class MockExtractionTask(BaseTask):
    """Mock extraction task for testing."""

    def __init__(self, config_manager: ConfigManager, **params):
        super().__init__(config_manager, **params)

    def on_start(self, context):
        pass  # No-op for testing

    def run(self, context):
        context.setdefault('data', {})
        context['data']['extracted'] = True
        return context

    def validate_required_fields(self, context):
        pass


class MockStorageTask(BaseTask):
    """Mock storage task for testing."""

    def __init__(self, config_manager: ConfigManager, **params):
        super().__init__(config_manager, **params)

    def on_start(self, context):
        pass  # No-op for testing

    def run(self, context):
        context.setdefault('data', {})
        context['data']['stored'] = True
        return context

    def validate_required_fields(self, context):
        pass


class MockCleanupTask(BaseTask):
    """Mock cleanup task for testing."""

    def __init__(self, config_manager: ConfigManager, **params):
        super().__init__(config_manager, **params)

    def on_start(self, context):
        pass  # No-op for testing

    def run(self, context):
        context.setdefault('data', {})
        context['data']['cleaned_up'] = True
        return context

    def validate_required_fields(self, context):
        pass


class ErrorTask(BaseTask):
    """Mock error task for testing."""

    def __init__(self, config_manager: ConfigManager, **params):
        super().__init__(config_manager, **params)

    def on_start(self, context):
        pass

    def run(self, context):
        context.setdefault('data', {})
        context['data']['error'] = "Simulated Error"
        return context

    def validate_required_fields(self, context):
        pass