from modules.base_task import BaseTask
from typing import Any, Dict

class MockExtractionTask(BaseTask):
    def on_start(self, context: Dict[str, Any]):
        print("MockExtractionTask initialized")
        
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        context['extracted'] = True
        return context
        
    def validate_required_fields(self, context: Dict[str, Any]):
        # For mock, we can skip detailed validation or add a simple check
        pass

class MockStorageTask(BaseTask):
    def on_start(self, context: Dict[str, Any]):
        print("MockStorageTask initialized")
        
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        context['stored'] = True
        return context
        
    def validate_required_fields(self, context: Dict[str, Any]):
        # For mock, we can skip detailed validation or add a simple check
        pass

class ErrorTask(BaseTask):
    def on_start(self, context: Dict[str, Any]):
        pass # No specific start logic for error task
        
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        raise ValueError("Simulated task failure")
        
    def validate_required_fields(self, context: Dict[str, Any]):
        pass # No specific validation for error task