"""Workflow loader module.

This module is responsible for:
- Dynamically loading task classes defined in configuration.
- Constructing a Prefect flow that orchestrates execution of configured steps.
- Managing execution lifecycle with robust error handling and status updates.
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
from modules.status_manager import StatusManager
from modules.base_task import BaseTask
from modules.exceptions import TaskError
from standard_step.housekeeping.cleanup_task import CleanupTask

class WorkflowLoader:
    """Dynamically builds and runs a Prefect-based workflow from configuration.

    This loader depends on external managers for configuration, shutdown, and status:
    - ConfigManager: provides access to the pipeline and task definitions.
    - ShutdownManager: performs a graceful shutdown when unrecoverable errors occur.
    - StatusManager: records status updates for pipeline start, per-step completion/failure,
      and final pipeline outcome.

    The loader imports task classes at runtime based on config (module + class),
    instantiates them, wraps their run methods as Prefect tasks, and wires them
    into a Prefect flow function. It updates statuses after each step and handles
    on-error behavior, then appends and executes a housekeeping step with status updates.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config_manager: ConfigManager):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(config_manager)
        return cls._instance

    def _init(self, config_manager: ConfigManager):
        """Internal initializer for the singleton instance."""
        self.config_manager = config_manager
        self.cfg = config_manager.get_all()
        self.task_defs = self.cfg.get("tasks", {})
        self.logger = logging.getLogger(__name__)
        self.shutdown_manager = ShutdownManager()
        self.status_manager = StatusManager(self.config_manager)

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
            TypeError: If the resolved class does not inherit from BaseTask.
            SystemExit: If any error occurs during import or attribute access; the
                error is logged, shutdown is triggered, and the process exits.
        """
        try:
            module = importlib.import_module(module_name)
            task_class = getattr(module, class_name)
            if not issubclass(task_class, BaseTask):
                raise TypeError(f"'{class_name}' in '{module_name}' is not a subclass of BaseTask.")
            return task_class
        except Exception as e:
            self.logger.critical(f"Failed to import task class '{module_name}.{class_name}': {e}")
            self.shutdown_manager.shutdown()
            raise SystemExit(1)

    def load_workflow(self) -> Callable[[Dict[str, Any]], Any] | None:
        """Build and return a Prefect flow function for the configured pipeline.

        Purpose:
            Validate pipeline configuration, iterate over configured steps, wrap
            each task's run() as a Prefect @task (with NO_CACHE), execute steps
            sequentially while updating statuses, and finally run a housekeeping
            task with appropriate status updates.

        Returns:
            A Prefect flow function named "Dynamic PDF Processing Flow" that accepts
            initial_context: Dict[str, Any] and returns the final context.

        Notes:
            - Pipeline validation: ensures the 'pipeline' config is a list of task keys.
            - Iteration: for each step, imports and instantiates the configured task
              class, calls on_start(context), executes run(context) via a wrapped
              Prefect task, and propagates the resulting context.
            - Status updates: sets "Pipeline Started" at the beginning; per-step
              updates include "Task Completed: {task_name}" on success or
              "Task Failed: {task_name}" on errors, with error details recorded.
            - Error behavior: if step config specifies on_error == "stop", the
              pipeline stops after logging and status update; otherwise it continues.
            - Housekeeping: executes a mandatory "housekeeping_task" if present in
              'tasks' with its own status updates, setting final pipeline status to
              either "Pipeline Completed Successfully" or "Pipeline Completed with Errors".
        """
        pipeline_config = self.cfg.get("pipeline", [])
        if not isinstance(pipeline_config, list):
            self.logger.critical("Pipeline configuration must be a list of task names.")
            self.shutdown_manager.shutdown()
            return None

        @flow(name="Dynamic PDF Processing Flow")
        def dynamic_flow(initial_context: Dict[str, Any]):
            current_context = initial_context
            self.status_manager.update_status(current_context.get("id", "unknown"), "Pipeline Started")

            for task_key in pipeline_config:
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

                try:
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

                    if current_context.get("error"):
                        self.status_manager.update_status(current_context.get("id", "unknown"),
                                                          f"Task Failed: {task_name}",
                                                          error=current_context["error"])
                        if on_error == "stop":
                            self.logger.critical(f"Stopping pipeline due to error in task '{task_name}'.")
                            break
                        else:
                            self.logger.warning(f"Continuing pipeline despite error in task '{task_name}'.")
                    else:
                        self.status_manager.update_status(current_context.get("id", "unknown"),
                                                          f"Task Completed: {task_name}")

                except TaskError as e:
                    self.logger.error(f"Task '{task_name}' failed with TaskError: {e}")
                    current_context["error"] = str(e)
                    current_context["error_step"] = task_name
                    self.status_manager.update_status(current_context.get("id", "unknown"),
                                                      f"Task Failed: {task_name}",
                                                      error=str(e))
                    if on_error == "stop":
                        self.logger.critical(f"Stopping pipeline due to TaskError in task '{task_name}'.")
                        break
                except Exception as e:
                    self.logger.error(f"Unexpected error in task '{task_name}': {e}")
                    current_context["error"] = f"Unexpected error: {e}"
                    current_context["error_step"] = task_name
                    self.status_manager.update_status(current_context.get("id", "unknown"),
                                                      f"Task Failed: {task_name}",
                                                      error=f"Unexpected error: {e}")
                    if on_error == "stop":
                        self.logger.critical(f"Stopping pipeline due to unexpected error in task '{task_name}'.")
                        break

            # Execute mandatory housekeeping task
            self.logger.info("Executing mandatory housekeeping task.")
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

                if final_context.get("error"):
                    self.status_manager.update_status(final_context.get("id", "unknown"),
                                                      "Pipeline Completed with Errors",
                                                      error=final_context["error"])
                else:
                    self.status_manager.update_status(final_context.get("id", "unknown"),
                                                      "Pipeline Completed Successfully")
                return final_context
            except Exception as e:
                self.logger.critical(f"Housekeeping task failed: {e}")
                self.status_manager.update_status(current_context.get("id", "unknown"),
                                                  "Pipeline Completed with Critical Housekeeping Error",
                                                  error=str(e))
                return final_context if 'final_context' in locals() else current_context
        return dynamic_flow