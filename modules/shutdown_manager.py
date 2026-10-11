"""Singleton shutdown coordinator for registering and executing cleanup tasks.

This module implements a thread-safe, process-wide ShutdownManager that acts as a
central coordinator for graceful application shutdown. Components can register
cleanup tasks (callables with optional arguments) which will be executed during
shutdown in the order they were registered. Logging configuration belongs to the
application; locks serialize callback registration and execution.
"""

import threading
import logging
from typing import Callable, Any


class ShutdownManager:
    """Thread-safe singleton for coordinating application shutdown.

    Creation is lazy, with double-checked locking in __new__ and one-time setup
    in _init. Callers own signal/atexit integration and application logging setup.
    Callbacks run in registration order; ordinary exceptions are logged so later
    callbacks can still run.
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

        Called once by __new__; creates the callback registry and lock and obtains
        a module logger without changing its level, handlers, or formatting.
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

        Registration takes the same lock as execution, so a registration made
        during shutdown waits until the current shutdown call finishes.
        """
        with self._tasks_lock:
            self._cleanup_tasks.append((task_function, args, kwargs))
            self.logger.debug(f"Registered cleanup task: {task_function.__name__}")

    def shutdown(self):
        """Execute all registered cleanup tasks in registration order.

        Iterates over the tasks in the order they were registered and executes
        each one. Any exception raised by a task is logged, and execution
        continues with subsequent tasks.

        The registry is retained, so another call executes the callbacks again.
        Callbacks must not register callbacks or re-enter shutdown: execution
        holds the non-reentrant registry lock throughout.
        """
        self.logger.info("Shutdown initiated. Executing cleanup tasks...")
        # Hold the registry stable while callbacks run. A callback that acquires
        # this same lock (via registration or shutdown) would deadlock.
        with self._tasks_lock:
            for task_function, args, kwargs in self._cleanup_tasks:
                try:
                    self.logger.debug(f"Executing cleanup task: {task_function.__name__}")
                    task_function(*args, **kwargs)
                except Exception as e:
                    self.logger.error(f"Error executing cleanup task {task_function.__name__}: {e}")
        self.logger.info("Shutdown complete. All cleanup tasks executed.")
