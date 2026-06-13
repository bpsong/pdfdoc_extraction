"""Workflow loader module.

This module is responsible for:
- Dynamically loading task classes defined in configuration.
- Constructing a Prefect flow that orchestrates execution of configured steps.
- Managing execution lifecycle with robust error handling and SQLite task runs.
- Ensuring a mandatory housekeeping step executes at the end of the pipeline.
"""

import importlib
import logging
import sys
import threading
from typing import Dict, Any, Callable, Type, cast, Union

from prefect import flow, task, get_run_logger
from prefect.futures import PrefectFuture
from prefect.cache_policies import NO_CACHE

from modules.config_manager import ConfigManager
from modules.shutdown_manager import ShutdownManager
from modules.base_task import BaseTask
from modules.db.connection import connect
from modules.exceptions import TaskError
from modules.services.fan_in_service import FanInService
from modules.services.task_registry_service import ApprovedTaskRegistry, TaskApprovalError
from modules.services.workflow_state_service import WorkflowStateService
from standard_step.housekeeping.cleanup_task import CleanupTask

class WorkflowLoader:
    """Dynamically builds and runs a Prefect-based workflow from configuration.

    This loader depends on external managers for configuration, shutdown, and state:
    - ConfigManager: provides access to the pipeline and task definitions.
    - ShutdownManager: performs a graceful shutdown when unrecoverable errors occur.
    - WorkflowStateService: records SQLite task-run start, completion, pause,
      failure, and current document pointer state.

    The loader imports task classes at runtime based on config (module + class),
    instantiates them, wraps their run methods as Prefect tasks, and wires them
    into a Prefect flow function. It updates SQLite task runs after each step and handles
    on-error behavior, then appends and executes a housekeeping step.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config_manager: ConfigManager):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init(config_manager)
            elif getattr(cls._instance, "config_manager", None) is not config_manager:
                cls._instance._init(config_manager)
        return cls._instance

    def _init(self, config_manager: ConfigManager):
        """Internal initializer for the singleton instance."""
        self.config_manager = config_manager
        self.cfg = config_manager.get_all()
        self.task_defs = self.cfg.get("tasks", {})
        self.logger = logging.getLogger(__name__)
        self.shutdown_manager = ShutdownManager()

    def _import_task_class(self, module_name: str, class_name: str) -> Type[BaseTask]:
        """Import and validate a task class specified by module and class name.

        Purpose:
            Dynamically import the task class and ensure it inherits from BaseTask.

        Args:
            module_name: The dotted-path of the module to import.
            class_name: The name of the class within the module.

        Returns:
            The imported class object, guaranteed to be a subclass of BaseTask.

        Raises:
            TaskApprovalError: If the module/class pair is not approved for import.
            TypeError: If the resolved class does not inherit from BaseTask.
            SystemExit: If any error occurs during import or attribute access; the
                error is logged, shutdown is triggered, and the process exits.
        """
        try:
            ApprovedTaskRegistry(self.config_manager).assert_approved(module_name, class_name)
            module = importlib.import_module(module_name)
            task_class = getattr(module, class_name)
            if not issubclass(task_class, BaseTask):
                raise TypeError(f"'{class_name}' in '{module_name}' is not a subclass of BaseTask.")
            return task_class
        except TaskApprovalError as e:
            self.logger.critical(str(e))
            self.shutdown_manager.shutdown()
            raise SystemExit(1)
        except Exception as e:
            self.logger.critical(f"Failed to import task class '{module_name}.{class_name}': {e}")
            self.shutdown_manager.shutdown()
            raise SystemExit(1)

    @staticmethod
    def _context_summary(context: Dict[str, Any]) -> Dict[str, Any]:
        """Return a compact, JSON-friendly task run summary."""
        data = context.get("data")
        metadata = context.get("metadata")
        return {
            "id": context.get("id"),
            "batch_id": context.get("batch_id"),
            "document_id": context.get("document_id"),
            "file_path": context.get("file_path"),
            "pipeline_state": context.get("pipeline_state"),
            "review_item_id": context.get("review_item_id"),
            "error": context.get("error"),
            "error_step": context.get("error_step"),
            "data_keys": sorted(data.keys()) if isinstance(data, dict) else [],
            "metadata_keys": sorted(metadata.keys()) if isinstance(metadata, dict) else [],
        }

    def _state_service(self, context: Dict[str, Any]) -> WorkflowStateService | None:
        """Create a workflow state service when SQLite document context exists."""
        if not context.get("batch_id") or not context.get("document_id"):
            return None
        conn = connect(self.config_manager)
        return WorkflowStateService(conn, pipeline=self.cfg.get("pipeline", []))

    def load_workflow(self, start_task_index: int = 0) -> Callable[[Dict[str, Any]], Any] | None:
        """Build and return a Prefect flow function for the configured pipeline.

        Purpose:
            Validate pipeline configuration, iterate over configured steps, wrap
            each task's run() as a Prefect @task (with NO_CACHE), execute steps
            sequentially while updating SQLite task runs, and finally run a
            housekeeping task before fan-in finalization.

        Returns:
            A Prefect flow function named "Dynamic PDF Processing Flow" that accepts
            initial_context: Dict[str, Any] and returns the final context.

        Notes:
            - Pipeline validation: ensures the 'pipeline' config is a list of task keys.
            - Iteration: for each step, imports and instantiates the configured task
              class, calls on_start(context), executes run(context) via a wrapped
              Prefect task, and propagates the resulting context.
            - Error behavior: if step config specifies on_error == "stop", the
              pipeline stops after logging and status update; otherwise it continues.
            - Housekeeping: executes a mandatory cleanup task before leaf fan-in.
        """
        pipeline_config = self.cfg.get("pipeline", [])
        if not isinstance(pipeline_config, list):
            self.logger.critical("Pipeline configuration must be a list of task names.")
            self.shutdown_manager.shutdown()
            return None

        @flow(name="Dynamic PDF Processing Flow")
        def dynamic_flow(initial_context: Dict[str, Any]):
            current_context = initial_context
            effective_start_index = int(current_context.pop("start_task_index", start_task_index) or 0)

            for task_index, task_key in enumerate(pipeline_config):
                if task_index < effective_start_index:
                    continue
                step_cfg = self.task_defs.get(task_key)
                if not step_cfg:
                    self.logger.critical(f"Unknown pipeline step: '{task_key}' not found in 'tasks' definition.")
                    self.shutdown_manager.shutdown()
                    return current_context

                task_name = task_key # Use the key as the task name
                module_name = step_cfg.get("module")
                class_name = step_cfg.get("class")
                params = step_cfg.get("params", {})
                on_error = step_cfg.get("on_error", "stop")

                if not module_name or not class_name:
                    self.logger.critical(f"Task '{task_name}' missing 'module' or 'class' path.")
                    self.shutdown_manager.shutdown()
                    return current_context

                self.logger.info(f"Loading task '{task_name}' from '{module_name}.{class_name}'")

                task_run_id = None
                state_service = None
                try:
                    state_service = self._state_service(current_context)
                    if state_service is not None:
                        task_run = state_service.start_task(
                            batch_id=str(current_context["batch_id"]),
                            document_id=str(current_context["document_id"]),
                            task_key=task_key,
                            task_index=task_index,
                            module_name=str(module_name),
                            class_name=str(class_name),
                            input_data=self._context_summary(current_context),
                        )
                        task_run_id = task_run["id"]
                        current_context["task_run_id"] = task_run_id
                        current_context["current_task_key"] = task_key
                        current_context["current_task_index"] = task_index

                    # Import and instantiate the task class, passing config_manager and params
                    task_class = self._import_task_class(module_name, class_name)
                    task_instance = cast(BaseTask, task_class(config_manager=self.config_manager, **params))

                    # Call on_start with context
                    task_instance.on_start(current_context)

                    # Wrap the run method as a Prefect task with NO_CACHE to avoid serialization errors
                    @task(name=f"{task_name}_run", retries=1, retry_delay_seconds=3, cache_policy=NO_CACHE)
                    def wrapped_run_task(context: dict):
                        logger = get_run_logger()
                        logger.info(f"--> Running {task_name}")
                        result = task_instance.run(context)
                        return result or {}

                    # Execute task and get PrefectFuture
                    task_future = wrapped_run_task(current_context)
                    # Await the future result asynchronously
                    if callable(getattr(task_future, "result", None)):
                        current_context = cast(PrefectFuture, task_future).result()
                    elif isinstance(task_future, dict) and "result" in task_future:
                        current_context = task_future["result"]
                    else:
                        current_context = current_context

                    if task_run_id:
                        current_context["task_run_id"] = task_run_id

                    output_summary = self._context_summary(current_context)
                    if current_context.get("pipeline_state") == "fan_out":
                        current_context.setdefault("fan_out_start_task_index", task_index + 1)
                        if state_service is not None and task_run_id:
                            state_service.complete_task(task_run_id, output_summary)
                        self.logger.info("Pipeline fan-out after task '%s'.", task_name)
                        return current_context

                    if current_context.get("pipeline_state") == "paused":
                        if state_service is not None and task_run_id:
                            state_service.pause_task(task_run_id, output_summary)
                            state_service.pause_document(str(current_context["document_id"]))
                            FanInService(state_service.conn).finalize_leaf(current_context)
                        self.logger.info("Pipeline paused after task '%s'.", task_name)
                        return current_context

                    if current_context.get("error"):
                        if state_service is not None and task_run_id:
                            state_service.fail_task(task_run_id, str(current_context["error"]), output_summary)
                        if on_error == "stop":
                            self.logger.critical(f"Stopping pipeline due to error in task '{task_name}'.")
                            break
                        else:
                            self.logger.warning(f"Continuing pipeline despite error in task '{task_name}'.")
                    else:
                        if state_service is not None and task_run_id:
                            state_service.complete_task(task_run_id, output_summary)

                except TaskError as e:
                    self.logger.error(f"Task '{task_name}' failed with TaskError: {e}")
                    current_context["error"] = str(e)
                    current_context["error_step"] = task_name
                    if state_service is not None and task_run_id:
                        state_service.fail_task(task_run_id, str(e), self._context_summary(current_context))
                    if on_error == "stop":
                        self.logger.critical(f"Stopping pipeline due to TaskError in task '{task_name}'.")
                        break
                except SystemExit as e:
                    self.logger.error(f"Task '{task_name}' setup failed: {e}")
                    current_context["error"] = f"Task setup failed: {e}"
                    current_context["error_step"] = task_name
                    if state_service is not None and task_run_id:
                        state_service.fail_task(task_run_id, str(current_context["error"]), self._context_summary(current_context))
                    raise
                except Exception as e:
                    self.logger.error(f"Unexpected error in task '{task_name}': {e}")
                    current_context["error"] = f"Unexpected error: {e}"
                    current_context["error_step"] = task_name
                    if state_service is not None and task_run_id:
                        state_service.fail_task(task_run_id, str(e), self._context_summary(current_context))
                    if on_error == "stop":
                        self.logger.critical(f"Stopping pipeline due to unexpected error in task '{task_name}'.")
                        break
                finally:
                    if state_service is not None:
                        state_service.conn.close()

            # Execute mandatory housekeeping task
            self.logger.info("Executing mandatory housekeeping task.")
            final_context = current_context
            try:
                housekeeping_task_instance = CleanupTask(config_manager=self.config_manager)
                housekeeping_task_instance.on_start(current_context)

                @task(name="cleanup_task_run", retries=1, retry_delay_seconds=3, cache_policy=NO_CACHE)
                def wrapped_housekeeping_run_task(context: dict):
                    logger = get_run_logger()
                    logger.info("--> Running cleanup_task")
                    result = housekeeping_task_instance.run(context)
                    return result or {}

                final_future = wrapped_housekeeping_run_task(current_context)
                if callable(getattr(final_future, "result", None)):
                    final_context = cast(PrefectFuture, final_future).result()
                elif isinstance(final_future, dict) and "result" in final_future:
                    final_context = final_future["result"]
                else:
                    final_context = current_context

                self._finalize_leaf(final_context)
                return final_context
            except Exception as e:
                self.logger.critical(f"Housekeeping task failed: {e}")
                current_context["error"] = str(e)
                self._finalize_leaf(current_context)
                return final_context
        return dynamic_flow

    def _finalize_leaf(self, context: Dict[str, Any]) -> None:
        """Run fan-in finalization for SQLite-backed leaf contexts."""
        if context.get("pipeline_state") == "fan_out":
            return
        if not context.get("document_id") and not context.get("id"):
            return
        try:
            with connect(self.config_manager) as conn:
                FanInService(conn).finalize_leaf(context)
        except Exception:
            self.logger.exception("Fan-in finalization failed for %s", context.get("document_id") or context.get("id"))
