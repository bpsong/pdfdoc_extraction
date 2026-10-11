"""
AssignNanoidTask: A task to generate a unique nanoid string and add it to the shared context.

Follows the standard task creation guidelines:
- Configurable length parameter (5-21, default 10)
- Uses the Python nanoid library for secure ID generation
- Updates context with key "nanoid" inside the "data" dictionary
"""

from typing import Any, Dict

from nanoid import generate
from modules.base_task import BaseTask, TaskError
from modules.config_protocol import ConfigProvider as ConfigManager


class AssignNanoidTask(BaseTask):
    """Generate a unique nanoid string and add it to the shared context."""

    TASK_NAME = "assign_nanoid"

    def __init__(self, config_manager: ConfigManager, **params: Any) -> None:
        """Resolve the ID length and reject values outside the supported range."""
        super().__init__(config_manager, **params)
        # Read length parameter from config or params, default to 10
        length_param = params.get("length")
        if length_param is None:
            length_param = self.config_manager.get("assign_nanoid.length", 10)
        if length_param is None:
            raise TaskError(f"Length parameter for {self.TASK_NAME} is missing")
        try:
            self.length = int(length_param)
        except (ValueError, TypeError):
            raise TaskError(
                f"Invalid length parameter for {self.TASK_NAME}: must be an integer"
            )
        if not (5 <= self.length <= 21):
            raise TaskError(
                f"Length parameter for {self.TASK_NAME} must be between 5 and 21 inclusive"
            )

    def on_start(self, context: Dict[str, Any]) -> None:
        """Initialize shared context containers before generating an ID."""
        self.initialize_context(context)

    def validate_required_fields(self, context: Dict[str, Any]) -> None:
        """Accept any context; ID generation has no input field prerequisites."""
        # No required fields in context for this task
        pass

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate and store a fresh ID in data, replacing any previous nanoid."""
        try:
            # Generate nanoid with specified length using default alphabet
            nanoid_str = generate(size=self.length)

            # This is business data; workflow document and batch IDs retain
            # their existing identities. Every invocation generates a new ID.
            if "data" not in context or not isinstance(context["data"], dict):
                context["data"] = {}
            context["data"]["nanoid"] = nanoid_str
            return context
        except Exception as e:
            context["error"] = str(e)
            context["error_step"] = self.task_key(context)
            raise TaskError(f"Error in {self.task_key(context)}: {e}")
