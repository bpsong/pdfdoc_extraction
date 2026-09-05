"""Focused tests for run-scoped runtime health and heartbeats."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.runtime_health_service import (
    RuntimeHealthReporter,
    RuntimeHealthService,
)
from test.helpers_sqlite import TempConfig


EXPECTED = ("supervisor", "worker", "watch_folder", "web")


def build_config(tmp_path):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "runtime_health": {
                "heartbeat_interval_seconds": 0.05,
                "stale_after_seconds": 0.15,
            }
        },
    )
    initialize_database(config)
    return config


def test_busy_worker_and_degraded_watch_folder_remain_ready(tmp_path):
    service = RuntimeHealthService(build_config(tmp_path), "run-current")
    service.record("supervisor", "ready", process_id=1)
    service.record("worker", "busy", process_id=2, details={"job_id": "job-1"})
    service.record(
        "watch_folder",
        "degraded",
        process_id=1,
        details={"binding_issue_count": 1},
    )
    service.record("web", "ready", process_id=3)

    snapshot = service.snapshot(EXPECTED)

    assert snapshot["ready"] is True
    assert snapshot["components"]["worker"]["status"] == "busy"
    assert snapshot["components"]["watch_folder"]["status"] == "degraded"
    assert snapshot["components"]["watch_folder"]["details"] == {
        "binding_issue_count": 1
    }


def test_previous_run_records_do_not_satisfy_current_readiness(tmp_path):
    config = build_config(tmp_path)
    previous = RuntimeHealthService(config, "run-previous")
    for component in EXPECTED:
        previous.record(component, "ready", process_id=1)

    snapshot = RuntimeHealthService(config, "run-current").snapshot(EXPECTED)

    assert snapshot["ready"] is False
    assert snapshot["missing_components"] == list(EXPECTED)


def test_supervisor_failure_update_preserves_component_reported_pid(tmp_path):
    service = RuntimeHealthService(build_config(tmp_path), "run-current")
    service.record("worker", "ready", process_id=77)

    service.record(
        "worker",
        "failed",
        details={"exit_code": 1, "phase": "runtime"},
    )

    worker = service.snapshot(("worker",))["components"]["worker"]
    assert worker["status"] == "failed"
    assert worker["process_id"] == 77
    assert worker["details"] == {"exit_code": 1, "phase": "runtime"}


def test_stale_heartbeat_blocks_readiness(tmp_path):
    config = build_config(tmp_path)
    service = RuntimeHealthService(config, "run-current")
    service.record("worker", "ready", process_id=2)
    stale = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    with connect(config) as conn:
        conn.execute(
            "UPDATE runtime_component_health SET last_heartbeat_at = ?",
            (stale,),
        )
        conn.commit()

    snapshot = service.snapshot(("worker",))

    assert snapshot["ready"] is False
    assert snapshot["components"]["worker"]["status"] == "stale"
    assert snapshot["unhealthy_components"] == ["worker"]


def test_reporter_refreshes_busy_health_independently(tmp_path):
    config = build_config(tmp_path)
    reporter = RuntimeHealthReporter(config, "run-current", "worker", process_id=7)
    reporter.start(status="ready")
    reporter.set_status("busy", {"job_id": "long-job"})
    with connect(config) as conn:
        first = conn.execute(
            "SELECT last_heartbeat_at FROM runtime_component_health"
        ).fetchone()[0]

    time.sleep(0.12)

    with connect(config) as conn:
        second = conn.execute(
            "SELECT last_heartbeat_at, status FROM runtime_component_health"
        ).fetchone()
    reporter.stop()
    assert second[0] > first
    assert second[1] == "busy"
