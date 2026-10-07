"""Split PDFs locally at page boundaries selected through the Review Queue."""

from pathlib import Path
from typing import Any

from modules.base_task import BaseTask
from modules.config_protocol import ConfigProvider
from modules.db.connection import managed_connect
from modules.exceptions import TaskError
from modules.services.manual_split_service import ManualSplitService


class ManualSplitTask(BaseTask):
    """Skip one-page PDFs or pause for an operator's local split decision."""

    def __init__(self, config_manager: ConfigProvider, *, enabled: bool = True, split_dir: str = "", queue_name: str = "default_review", **params: Any) -> None:
        super().__init__(config_manager=config_manager, enabled=enabled, split_dir=split_dir, queue_name=queue_name, **params)
        self.enabled, self.split_dir, self.queue_name = enabled, split_dir, queue_name

    def on_start(self, context: dict[str, Any]) -> None:
        self.initialize_context(context)

    def validate_required_fields(self, context: dict[str, Any]) -> None:
        if not self.split_dir or not self.queue_name:
            raise TaskError("ManualSplitTask requires split_dir and queue_name.")
        for key in ("document_id", "batch_id", "pipeline_version_id", "task_run_id", "current_task_key", "file_path"):
            if not context.get(key):
                raise TaskError(f"ManualSplitTask requires {key}.")
        if type(self.enabled) is not bool:
            raise TaskError("ManualSplitTask enabled must be a boolean.")

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        self.initialize_context(context)
        self.validate_required_fields(context)
        try:
            with managed_connect(self.config_manager) as conn:
                return ManualSplitService(conn, self.config_manager).execute(context, enabled=self.enabled, split_dir=Path(self.split_dir), queue_name=self.queue_name)
        except (OSError, ValueError) as exc:
            raise TaskError("Manual split could not read or write the local PDF. Inspect the source and output directory.") from exc
