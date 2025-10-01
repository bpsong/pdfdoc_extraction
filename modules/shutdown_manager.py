"""Singleton shutdown coordinator for registering and executing cleanup tasks.

This module implements a thread-safe, process-wide ShutdownManager that acts as a
central coordinator for graceful application shutdown. Components can register
cleanup tasks (callables with optional arguments) which will be executed during
shutdown in the order they were registered. The manager configures its own logger
and uses locking to ensure thread-safe registration and execution.
"""

import threading
import logging
from typing import Callable, Any


class ShutdownManager:
    """Thread-safe singleton for coordinating application shutdown.

    This class enforces singleton semantics using double-checked locking in
    [`ShutdownManager.__new__()`](modules/shutdown_manager.py:10). It defers actual field
    setup to an internal initializer [`ShutdownManager._init()`](modules/shutdown_manager.py:22), which is
    invoked exactly once when the singleton instance is first created.

    The manager allows components to register cleanup tasks that will be executed
    during shutdown. Registration and execution are protected by locks to ensure
    thread safety. A dedicated logger is initialized with a stream handler and a
    standard formatter for consistent logging.

    Notes:
        - Creation is lazy and thread-safe.
        - Cleanup task execution occurs in registration order.
        - Logging is performed for registrations, executions, and errors.

    Troubleshooting:
        - Common Issue: Multiple instances created in multi-threaded environment.
          Resolution: Verify double-checked locking implementation and thread safety.
        - Common Issue: Shutdown hooks not triggering.
          Resolution: Ensure proper atexit and signal handler integration.
        - Common Issue: Resource leaks during shutdown.
          Resolution: Implement proper cleanup in shutdown callbacks and verify execution order.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Create or return the singleton instance with double-checked locking.

        Uses a class-level lock to ensure only one instance is created across
        threads. If an instance already exists, it is returned immediately.

        Returns:
            ShutdownManager: The singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ShutdownManager, cls).__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        """Internal initializer for the singleton instance.

        Initializes internal state, including the cleanup task registry, locks,
        and logger with a stream handler and a standard formatter.

        Side Effects:
            - Initializes the cleanup task list and locks.
            - Configures the `ShutdownManager` logger with handler and format.
            - Sets logger level to DEBUG.

        Notes:
            This method is called exactly once during the first construction of
            the singleton and should not be invoked directly by callers.
        """
        self._cleanup_tasks = []
        self._tasks_lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    def register_cleanup_task(self, task_function: Callable, *args: Any, **kwargs: Any):
        """Register a cleanup task to be executed during shutdown.

        Args:
            task_function (Callable): The callable to invoke on shutdown.
            *args: Positional arguments passed to the task when executed.
            **kwargs: Keyword arguments passed to the task when executed.

        Returns:
            None

        Notes:
            - Thread-safe: registration is guarded by an internal lock.
            - Logging: emits a DEBUG log entry upon successful registration.

        Troubleshooting:
            - Common Issue: Cleanup task not executed during shutdown.
              Resolution: Verify task was registered before shutdown is initiated.
            - Common Issue: Task registration fails silently.
              Resolution: Check logger output for registration confirmation and verify task is callable.
        """
        with self._tasks_lock:
            self._cleanup_tasks.append((task_function, args, kwargs))
            self.logger.debug(f"Registered cleanup task: {task_function.__name__}")

    def shutdown(self):
        """Execute all registered cleanup tasks in registration order.

        Iterates over the tasks in the order they were registered and executes
        each one. Any exception raised by a task is logged, and execution
        continues with subsequent tasks.

        Returns:
            None

        Notes:
            - Thread-safe: execution is guarded by an internal lock.
            - Logging:
                - INFO at start and completion.
                - DEBUG before executing each task.
                - ERROR if a task raises an exception (processing continues).

        Troubleshooting:
            - Common Issue: Graceful shutdown fails due to unhandled signals.
              Resolution: Ensure all signal handlers are registered and atexit integration is properly configured.
            - Common Issue: Resource leaks during shutdown.
              Resolution: Verify cleanup tasks complete execution and handle exceptions properly.
            - Common Issue: Tasks execute out of order.
              Resolution: Check task registration timing and ensure shutdown() is called only once.
        """
        self.logger.info("Shutdown initiated. Executing cleanup tasks...")
        with self._tasks_lock:
            for task_function, args, kwargs in self._cleanup_tasks:
                try:
                    self.logger.debug(f"Executing cleanup task: {task_function.__name__}")
                    task_function(*args, **kwargs)
                except Exception as e:
                    self.logger.error(f"Error executing cleanup task {task_function.__name__}: {e}")
        self.logger.info("Shutdown complete. All cleanup tasks executed.")