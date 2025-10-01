"""Custom exceptions used by the pipeline.

This module defines standardized exception types for the processing pipeline.
Use these exceptions to communicate task and workflow failures in a consistent,
machine- and human-readable way across modules.
"""


class TaskError(Exception):
    """Standardized error type for task and workflow failures.

    TaskError provides a consistent way to signal failures that occur within
    individual tasks or across the workflow execution. It is intended to be
    raised by task implementations and propagated up the pipeline, where it can
    be logged, surfaced to status managers, or used to control flow.

    Typical usage:
      - Raise when a task encounters a recoverable/expected failure condition.
      - Wrap lower-level exceptions to normalize error reporting across tasks.
      - Catch upstream to update task status and produce a uniform error message.

    The error message provided at construction is stored and exposed via
    the instance's `message` attribute and is included in the string
    representation.

    Troubleshooting:
        - Common Issue: TaskError propagation fails to update status. Resolution: Ensure exception handlers properly catch TaskError and call status_manager.update_task_status() with appropriate error information.
        - Common Issue: Generic error messages lack context. Resolution: Always provide descriptive messages when raising TaskError, including task name, file being processed, and specific failure reason.
        - Common Issue: TaskError not being logged properly. Resolution: Verify logging configuration includes ERROR level logging and that exception handlers include proper logging statements.
        - Common Issue: TaskError causes workflow to hang. Resolution: Implement proper exception handling in workflow manager to ensure tasks are marked as failed and workflow continues with remaining tasks.
    """

    def __init__(self, message: str):
        """Initialize a TaskError with a descriptive message.

        Args:
            message: Human-readable description of the task or workflow failure.

        Notes:
            The provided message is stored on the instance (`self.message`) and
            also passed to the base Exception to preserve standard behavior.
        """
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        """Return a formatted error string with a class-specific prefix.

        Returns:
            A string formatted as "TaskError: {message}" which includes the
            class name prefix followed by the original message.
        """
        return f"TaskError: {self.message}"