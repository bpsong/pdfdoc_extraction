"""
AssignNanoidTask: A task to generate a unique nanoid string and add it to the shared context.

Follows the standard task creation guidelines:
- Configurable length parameter (5-21, default 10)
- Uses the Python nanoid library for secure ID generation
- Updates context with key "nanoid" inside the "data" dictionary
- Emits status updates via StatusManager
"""

from typing import Any, Dict, Optional

from nanoid import generate
from modules.base_task import BaseTask, TaskError
from modules.config_manager import ConfigManager
from modules.status_manager import StatusManager
from modules.utils import sanitize_filename


class AssignNanoidTask(BaseTask):
    TASK_SLUG = "assign_nanoid"

    def __init__(self, config_manager: ConfigManager, **params: Any) -> None:
        super().__init__(config_manager, **params)
        # Read length parameter from config or params, default to 10
        length_param = params.get("length")
        if length_param is None:
            length_param = self.config_manager.get("assign_nanoid.length", 10)
        if length_param is None:
            raise TaskError(f"Length parameter for {self.TASK_SLUG} is missing")
        try:
            self.length = int(length_param)
        except (ValueError, TypeError):
            raise TaskError(f"Invalid length parameter for {self.TASK_SLUG}: must be an integer")
        if not (5 <= self.length <= 21):
            raise TaskError(f"Length parameter for {self.TASK_SLUG} must be between 5 and 21 inclusive")
        self.status_manager = StatusManager(config_manager)

    def on_start(self, context: Dict[str, Any]) -> None:
        try:
            self.status_manager.update_status(
                str(context.get("id", "unknown")),
                "started",
                step=f"Task Started: {self.TASK_SLUG}",
            )
        except Exception:
            # Do not fail task start if status update fails
            pass

    def validate_required_fields(self, context: Dict[str, Any]) -> None:
        # No required fields in context for this task
        pass

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Generate nanoid with specified length using default alphabet
            nanoid_str = generate(size=self.length)

            # Add to context inside the 'data' dictionary
            if "data" not in context or not isinstance(context["data"], dict):
                context["data"] = {}
            context["data"]["nanoid"] = nanoid_str

            self.status_manager.update_status(
                str(context.get("id", "unknown")),
                "success",
                step=f"Task Completed: {self.TASK_SLUG}",
            )
            return context
        except Exception as e:
            try:
                self.status_manager.update_status(
                    str(context.get("id", "unknown")),
                    "failed",
                    step=f"Task Failed: {self.TASK_SLUG}",
                    error=str(e),
                )
            except Exception:
                pass
            context["error"] = str(e)
            context["error_step"] = self.TASK_SLUG
            raise TaskError(f"Error in {self.TASK_SLUG}: {e}")