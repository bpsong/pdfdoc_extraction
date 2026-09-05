"""Run-scoped component health reporting and readiness evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from threading import Event, RLock, Thread
from typing import Any, Iterable

from modules.config_protocol import ConfigProvider
from modules.db.connection import connect, json_loads
from modules.db.migrations import SCHEMA_VERSION
from modules.db.repositories import RuntimeComponentHealthRepository


logger = logging.getLogger(__name__)

HEALTHY_COMPONENT_STATUSES = {
    "supervisor": {"ready"},
    "web": {"ready", "busy"},
    "worker": {"ready", "busy"},
    "watch_folder": {"ready", "degraded"},
}
VALID_STATUSES = {
    "starting",
    "ready",
    "busy",
    "degraded",
    "stopping",
    "stopped",
    "failed",
}


def expected_components_from_env(*, no_web: bool = False) -> tuple[str, ...]:
    """Return the expected component names for the current supervised run."""
    configured = os.getenv("DOCFLOW_EXPECTED_COMPONENTS", "")
    if configured:
        return tuple(
            dict.fromkeys(
                item.strip() for item in configured.split(",") if item.strip()
            )
        )
    components = ["supervisor", "worker", "watch_folder"]
    if not no_web:
        components.append("web")
    return tuple(components)


class RuntimeHealthService:
    """Persist heartbeats and evaluate one application run's readiness."""

    def __init__(self, config: ConfigProvider, run_id: str) -> None:
        if not run_id.strip():
            raise ValueError("run_id is required for runtime health")
        self.config = config
        self.run_id = run_id
        interval = max(
            0.1,
            float(config.get("runtime_health.heartbeat_interval_seconds", 2) or 2),
        )
        self.stale_after_seconds = max(
            interval * 2,
            float(config.get("runtime_health.stale_after_seconds", 10) or 10),
        )

    def record(
        self,
        component: str,
        status: str,
        *,
        process_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or refresh one component record for this run."""
        if status not in VALID_STATUSES:
            raise ValueError(f"Unsupported runtime health status: {status}")
        with connect(self.config) as conn:
            return RuntimeComponentHealthRepository(conn).upsert(
                run_id=self.run_id,
                component=component,
                status=status,
                process_id=process_id,
                details=details,
            )

    def snapshot(self, expected_components: Iterable[str]) -> dict[str, Any]:
        """Return detailed database and component readiness for this run."""
        expected = tuple(dict.fromkeys(expected_components))
        database: dict[str, Any]
        rows: list[dict[str, Any]] = []
        try:
            with connect(self.config) as conn:
                version_row = conn.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()
                version = int(version_row[0]) if version_row and version_row[0] is not None else None
                rows = RuntimeComponentHealthRepository(conn).list_for_run(self.run_id)
            database = {
                "status": "ready" if version == SCHEMA_VERSION else "incompatible",
                "schema_version": version,
                "expected_schema_version": SCHEMA_VERSION,
            }
        except Exception as exc:
            logger.warning("Runtime readiness database check failed: %s", type(exc).__name__)
            database = {
                "status": "unavailable",
                "schema_version": None,
                "expected_schema_version": SCHEMA_VERSION,
            }

        now = datetime.now(timezone.utc)
        components: dict[str, dict[str, Any]] = {}
        for row in rows:
            raw_status = str(row["status"])
            heartbeat = str(row["last_heartbeat_at"])
            try:
                age = max(
                    0.0,
                    (now - datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))).total_seconds(),
                )
            except ValueError:
                age = self.stale_after_seconds + 1
            effective_status = (
                "stale"
                if age > self.stale_after_seconds
                and raw_status not in {"stopped", "failed"}
                else raw_status
            )
            components[str(row["component"])] = {
                "status": effective_status,
                "reported_status": raw_status,
                "process_id": row["process_id"],
                "started_at": row["started_at"],
                "last_heartbeat_at": heartbeat,
                "heartbeat_age_seconds": round(age, 3),
                "details": json_loads(row["details_json"], {}),
            }

        missing = [name for name in expected if name not in components]
        unhealthy = [
            name
            for name in expected
            if name in components
            and components[name]["status"]
            not in HEALTHY_COMPONENT_STATUSES.get(name, {"ready", "busy"})
        ]
        ready = database["status"] == "ready" and not missing and not unhealthy
        return {
            "run_id": self.run_id,
            "status": "ready" if ready else "not_ready",
            "ready": ready,
            "database": database,
            "expected_components": list(expected),
            "missing_components": missing,
            "unhealthy_components": unhealthy,
            "components": components,
        }


class RuntimeHealthReporter:
    """Refresh component health on a thread independent of component work."""

    def __init__(
        self,
        config: ConfigProvider,
        run_id: str,
        component: str,
        *,
        process_id: int | None = None,
    ) -> None:
        self.service = RuntimeHealthService(config, run_id)
        self.component = component
        self.process_id = process_id if process_id is not None else os.getpid()
        self.interval = max(
            0.1,
            float(config.get("runtime_health.heartbeat_interval_seconds", 2) or 2),
        )
        self._status = "starting"
        self._details: dict[str, Any] = {}
        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self, *, status: str = "ready") -> None:
        """Write the initial state and begin periodic refreshes."""
        self.set_status(status)
        self._thread = Thread(
            target=self._heartbeat_loop,
            name=f"{self.component}-health-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def set_status(
        self,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Change and immediately persist the reported component state."""
        with self._lock:
            self._status = status
            self._details = dict(details or {})
        self._record_current()

    def stop(self, *, status: str = "stopped") -> None:
        """Stop periodic refreshes and persist a terminal state."""
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.interval * 2))
        try:
            self.set_status(status)
        except Exception:
            logger.exception(
                "Failed to persist terminal runtime health: component=%s",
                self.component,
            )

    def _record_current(self) -> None:
        with self._lock:
            status = self._status
            details = dict(self._details)
        self.service.record(
            self.component,
            status,
            process_id=self.process_id,
            details=details,
        )

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self.interval):
            try:
                self._record_current()
            except Exception:
                logger.exception(
                    "Runtime heartbeat failed: component=%s", self.component
                )
