"""Maintain a worker claim independently of synchronous workflow execution."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import logging
import sqlite3
from threading import Event, Thread
from typing import Iterator

from modules.config_protocol import ConfigProvider
from modules.db.connection import immediate_transaction, managed_connect
from modules.db.repositories import JobClaim, ProcessingJobRepository


class JobClaimLost(RuntimeError):
    """This execution may no longer dispatch work or commit its result."""


class ProcessingLease:
    """Check and renew a single running attempt using independent SQLite connections."""

    def __init__(self, config: ConfigProvider, claim: JobClaim, seconds: float) -> None:
        self.config = config
        self.claim = claim
        self.seconds = seconds

    @staticmethod
    def deadline(seconds: float) -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    def check(self, conn: sqlite3.Connection | None = None) -> None:
        """Consult SQLite even when the renewal thread has not woken yet."""
        if conn is None:
            with managed_connect(self.config) as connection:
                self.check(connection)
            return
        if not ProcessingJobRepository(conn).owns_claim(self.claim):
            raise JobClaimLost("Processing job claim expired or was replaced.")

    @contextmanager
    def maintain(self) -> Iterator[None]:
        """Keep renewing during graceful shutdown until the active invocation exits."""
        finished = Event()

        def renew() -> None:
            while not finished.wait(self.seconds / 3):
                try:
                    with managed_connect(self.config) as conn:
                        if not ProcessingJobRepository(conn).renew(self.claim, self.deadline(self.seconds)):
                            return
                except sqlite3.OperationalError:
                    logging.getLogger(__name__).warning("Could not renew processing lease", exc_info=True)

        thread = Thread(target=renew, name="processing-lease", daemon=True)
        thread.start()
        try:
            yield
        finally:
            finished.set()
            thread.join()


@contextmanager
def claim_write(conn: sqlite3.Connection, lease: ProcessingLease | None) -> Iterator[None]:
    """Serialize the ownership check and runner state changes against recovery."""
    if lease is None:
        yield
    else:
        with immediate_transaction(conn):
            lease.check(conn)
            yield
