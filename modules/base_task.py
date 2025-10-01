"""modules.base_task.py

Abstract base for workflow tasks implementing the Railway Programming pattern.
This module defines the BaseTask contract, centralizing error handling and
context management. It standardizes lifecycle hooks (on_start, run,
validate_required_fields) and provides helpers to register errors and
initialize the shared context dictionary used across tasks.
"""

from abc import ABC, abstractmethod
import logging
from modules.exceptions import TaskError
from modules.config_manager import ConfigManager  # Import ConfigManager
from typing import Optional  # Import Optional


class BaseTask(ABC):
    """Abstract base class for all workflow tasks.

    Responsibilities:
      - Define a consistent lifecycle for tasks:
        1) on_start(context): perform setup and early validation.
        2) run(context) -> dict: execute core business logic and return context.
        3) validate_required_fields(context): enforce configuration/context requirements.
      - Provide utility helpers for Railway Programming style error handling:
        - register_error(context, error): record failure details in context.
        - initialize_context(context): ensure required context keys exist.

    Subclasses must implement on_start, run, and validate_required_fields and
    should rely on register_error for standardized error recording.
    """

    def __init__(self, config_manager: ConfigManager, **params):
        """Initialize the task with configuration and parameters.

        Args:
            config_manager: Central configuration manager instance used to
                retrieve settings and shared services across tasks.
            **params: Arbitrary task-specific parameters (e.g., directory paths,
                filenames, API keys). These are captured and stored on the
                instance for use by on_start, run, and validate_required_fields.

        Notes:
            This constructor does not perform validation. Subclasses should
            validate in validate_required_fields or during on_start.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config_manager = config_manager
        self.params = params

        # Keep constructor side-effect free beyond basic field initialization.

    @abstractmethod
    def on_start(self, context: dict):
        """Perform task setup prior to core execution.

        This hook is intended for initializing resources, normalizing context,
        and performing light-weight checks before run() is invoked.

        Args:
            context: Mutable workflow context shared between tasks. Implementations
                may read and update this dictionary, but must not assume keys are
                present unless ensured via initialize_context() or prior checks.
        """
        pass

    @abstractmethod
    def run(self, context: dict) -> dict:  # Changed execute to run to match task classes
        """Execute the core business logic of the task.

        Implementations must read from and update the provided context and
        return the same context (possibly mutated) to pass downstream.

        Args:
            context: Mutable workflow context shared between tasks.

        Returns:
            dict: The updated context dictionary reflecting the outcome of the task.

        Raises:
            TaskError: If a critical failure occurs that should halt the happy path.
                Callers may catch this and use register_error() to record details.
        """
        pass

    @abstractmethod
    def validate_required_fields(self, context: dict):
        """Validate that all required configuration and context fields are present.

        Implementations should raise TaskError when mandatory parameters are
        missing or invalid. Typical checks include configuration values loaded
        via config_manager and preconditions within the context.

        Args:
            context: Current workflow context that may provide values needed for
                validation (e.g., identifiers, file paths).

        Raises:
            TaskError: If any required parameter or precondition is missing/invalid.
        """
        pass

    def register_error(self, context: dict, error: TaskError):
        """Record error information in the context for downstream handling.

        Side Effects:
            - Ensures context['data'] exists.
            - Sets context['error'] to the string representation of the error.
            - Sets context['error_step'] to the current class name to indicate
              the origin of the failure.

        Args:
            context: The mutable workflow context to update with error details.
            error: The TaskError (or subclass) instance to record.
        """
        context.setdefault('data', {})
        context['error'] = str(error)
        context['error_step'] = self.__class__.__name__

    def initialize_context(self, context: dict):
        """Ensure standard keys exist in the shared workflow context.

        This helper idempotently initializes keys required by tasks following
        the Railway Programming pattern.

        Ensured Keys:
            - data: dict container for task outputs and shared state.
            - error: str | None, present even when no error occurred.
            - error_step: str | None, indicates the class name that set error.

        Args:
            context: The mutable workflow context to normalize.

        Side Effects:
            Inserts missing keys with safe defaults without overwriting existing
            values.
        """
        context.setdefault('data', {})
        context.setdefault('error', None)
        context.setdefault('error_step', None)