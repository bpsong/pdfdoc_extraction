"""Tests for sequential multi-folder watch coordination."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import time
from unittest.mock import Mock

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.ingress_binding_service import IngressBindingService
from modules.services.watch_folder_coordinator import WatchFolderCoordinator
import modules.services.watch_folder_coordinator as coordinator_module
from test.helpers_sqlite import TempConfig
from test.services.test_ingestion_assignment_service import publish_pipeline


class FakeProcessor:
    def __init__(self):
        self.calls = []

    def process_file(self, **kwargs):
        self.calls.append(kwargs)
        return True


class RetryingProcessor(FakeProcessor):
    def process_file(self, **kwargs):
        self.calls.append(kwargs)
        return len(self.calls) >= 3


def build_context(tmp_path):
    processing = tmp_path / "processing"
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "watch_folder": {
                "processing_dir": str(processing),
                "polling_interval": 0.01,
            },
            "pipeline_secrets": {"test-api": "runtime-secret"},
        },
    )
    initialize_database(config)
    return config


def test_two_folders_ingest_to_different_exact_versions(tmp_path):
    config = build_context(tmp_path)
    first_folder = tmp_path / "first"
    second_folder = tmp_path / "second"
    first_folder.mkdir()
    second_folder.mkdir()
    with connect(config) as conn:
        _, first_version = publish_pipeline(conn, key="first")
        _, second_version = publish_pipeline(conn, key="second")
        bindings = IngressBindingService(conn, config)
        first_binding = bindings.create(
            folder_path=str(first_folder),
            pipeline_version_id=first_version["id"],
            enabled=True,
            user="admin",
        )
        second_binding = bindings.create(
            folder_path=str(second_folder),
            pipeline_version_id=second_version["id"],
            enabled=True,
            user="admin",
        )
    (first_folder / "one.pdf").write_bytes(b"%PDF-1.4\none")
    (second_folder / "two.pdf").write_bytes(b"%PDF-1.4\ntwo")
    processor = FakeProcessor()

    assert WatchFolderCoordinator(config, processor).scan_once() == 2

    with connect(config) as conn:
        batches = conn.execute(
            "SELECT * FROM batches ORDER BY ingress_binding_id"
        ).fetchall()
    assignments = {
        row["ingress_binding_id"]: row["pipeline_version_id"] for row in batches
    }
    assert assignments[first_binding["id"]] == first_version["id"]
    assert assignments[second_binding["id"]] == second_version["id"]
    assert processor.calls == []
    with connect(config) as conn:
        jobs = conn.execute("SELECT * FROM processing_jobs").fetchall()
    assert len(jobs) == 2
    assert {job["status"] for job in jobs} == {"queued"}


def test_binding_change_affects_only_files_claimed_after_reconciliation(tmp_path):
    config = build_context(tmp_path)
    folder = tmp_path / "incoming"
    folder.mkdir()
    with connect(config) as conn:
        _, first_version = publish_pipeline(conn, key="first")
        _, second_version = publish_pipeline(conn, key="second")
        service = IngressBindingService(conn, config)
        binding = service.create(
            folder_path=str(folder),
            pipeline_version_id=first_version["id"],
            enabled=True,
            user="admin",
        )
    processor = FakeProcessor()
    coordinator = WatchFolderCoordinator(config, processor)
    (folder / "before.pdf").write_bytes(b"%PDF-1.4\nbefore")
    assert coordinator.scan_once() == 1

    with connect(config) as conn:
        IngressBindingService(conn, config).update(
            binding["id"],
            pipeline_version_id=second_version["id"],
            user="admin",
        )
    (folder / "after.pdf").write_bytes(b"%PDF-1.4\nafter")
    assert coordinator.scan_once() == 1

    with connect(config) as conn:
        versions = [
            row["pipeline_version_id"]
            for row in conn.execute(
                "SELECT pipeline_version_id FROM batches ORDER BY created_at"
            ).fetchall()
        ]
    assert versions == [first_version["id"], second_version["id"]]


def test_inaccessible_and_invalid_bindings_do_not_block_other_folders(tmp_path):
    config = build_context(tmp_path)
    good = tmp_path / "good"
    bad = tmp_path / "bad"
    good.mkdir()
    bad.mkdir()
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="pipeline")
        service = IngressBindingService(conn, config)
        service.create(
            folder_path=str(good),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
        bad_binding = service.create(
            folder_path=str(bad),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
    bad.rmdir()
    (good / "invalid.pdf").write_bytes(b"not-pdf")
    (good / "valid.pdf").write_bytes(b"%PDF-1.4\n")
    processor = FakeProcessor()
    coordinator = WatchFolderCoordinator(config, processor)

    assert coordinator.scan_once() == 1
    assert coordinator.scan_once() == 0
    assert processor.calls == []
    with connect(config) as conn:
        row = conn.execute(
            "SELECT enabled FROM watch_folder_bindings WHERE id = ?",
            (bad_binding["id"],),
        ).fetchone()
    assert row["enabled"] == 1


def test_inaccessible_binding_reports_degraded_ingestion(tmp_path):
    config = build_context(tmp_path)
    missing = tmp_path / "missing"
    missing.mkdir()
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="health-pipeline")
        IngressBindingService(conn, config).create(
            folder_path=str(missing),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
    missing.rmdir()
    reporter = Mock()
    coordinator = WatchFolderCoordinator(
        config,
        FakeProcessor(),
        health_reporter=reporter,
    )

    assert coordinator.scan_once() == 0

    reporter.set_status.assert_called_once_with(
        "degraded", {"binding_issue_count": 1}
    )


def test_disabled_binding_is_reconciled_without_claiming_new_files(tmp_path):
    config = build_context(tmp_path)
    folder = tmp_path / "incoming"
    folder.mkdir()
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="pipeline")
        service = IngressBindingService(conn, config)
        binding = service.create(
            folder_path=str(folder),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
    coordinator = WatchFolderCoordinator(config, FakeProcessor())
    with connect(config) as conn:
        IngressBindingService(conn, config).update(
            binding["id"], enabled=False, user="admin"
        )
    pending = folder / "pending.pdf"
    pending.write_bytes(b"%PDF-1.4\n")

    assert coordinator.scan_once() == 0
    assert pending.exists()


def test_processing_is_deferred_to_the_worker_and_stop_is_coordinator_owned(tmp_path):
    config = build_context(tmp_path)
    folder = tmp_path / "incoming"
    folder.mkdir()
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="pipeline")
        IngressBindingService(conn, config).create(
            folder_path=str(folder),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
    (folder / "retry.pdf").write_bytes(b"%PDF-1.4\n")
    processor = RetryingProcessor()
    coordinator = WatchFolderCoordinator(config, processor)

    assert coordinator.scan_once() == 1
    assert processor.calls == []
    with connect(config) as conn:
        job = conn.execute("SELECT * FROM processing_jobs").fetchone()
    assert job["status"] == "queued"
    coordinator.stop()
    assert coordinator.stop_event.is_set()


def test_scan_binding_handles_listing_errors_and_repeated_claim_failures(tmp_path, monkeypatch):
    config = build_context(tmp_path)
    folder = tmp_path / "incoming"
    folder.mkdir()
    coordinator = WatchFolderCoordinator(config, FakeProcessor())
    binding = {"id": "binding-1", "folder_path": str(folder), "enabled": True}

    def fail_iterdir():
        raise OSError("unreadable")

    monkeypatch.setattr(type(folder), "iterdir", lambda _path: fail_iterdir())
    assert coordinator._scan_binding(binding) == 0

    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(coordinator_module.shutil, "move", lambda *_args: (_ for _ in ()).throw(OSError("locked")))
    assert coordinator._claim_and_process(source, {"id": "binding-1"}) is False


def test_claim_restores_file_when_assignment_fails(tmp_path, monkeypatch):
    config = build_context(tmp_path)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")
    coordinator = WatchFolderCoordinator(config, FakeProcessor())

    monkeypatch.setattr(
        coordinator_module.IngestionAssignmentService,
        "create_batch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    assert coordinator._claim_and_process(source, {"id": "binding-1", "pipeline_version_id": "v1"}) is False
    assert source.exists()


def test_claim_marks_document_failed_after_processor_exhaustion(tmp_path, monkeypatch):
    config = build_context(tmp_path)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")

    class FailedProcessor:
        def process_file(self, **_kwargs):
            return False

    coordinator = WatchFolderCoordinator(config, FailedProcessor())
    coordinator.retry_attempts = 1
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="pipeline")
        binding = IngressBindingService(conn, config).create(
            folder_path=str(tmp_path),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
    assert coordinator._claim_and_process(
        source,
        {"id": binding["id"], "pipeline_version_id": version["id"]},
    ) is True
    with connect(config) as conn:
        row = conn.execute("SELECT status FROM documents ORDER BY created_at DESC LIMIT 1").fetchone()
        job = conn.execute("SELECT status FROM processing_jobs ORDER BY created_at DESC LIMIT 1").fetchone()
    assert row["status"] == "queued"
    assert job["status"] == "queued"


def test_restore_claim_handles_existing_source_and_move_errors(tmp_path, monkeypatch):
    destination = tmp_path / "processing.pdf"
    source = tmp_path / "source.pdf"
    destination.write_bytes(b"data")
    source.write_bytes(b"already there")
    WatchFolderCoordinator._restore_claim(destination, source)
    assert destination.exists()

    source.unlink()
    monkeypatch.setattr(coordinator_module.shutil, "move", lambda *_args: (_ for _ in ()).throw(OSError("restore failed")))
    WatchFolderCoordinator._restore_claim(destination, source)


def test_start_runs_until_stop_event_is_set(tmp_path, monkeypatch):
    coordinator = WatchFolderCoordinator(build_context(tmp_path), FakeProcessor())
    calls = []
    coordinator.scan_once = lambda: calls.append(time.monotonic()) or 0

    def stop_after_wait(_timeout):
        coordinator.stop_event.set()

    coordinator.stop_event.wait = stop_after_wait
    coordinator.start()
    assert len(calls) == 1


def test_scan_once_and_processor_exception_paths_are_isolated(tmp_path, monkeypatch):
    config = build_context(tmp_path)
    coordinator = WatchFolderCoordinator(config, FakeProcessor())
    coordinator._scan_binding = lambda _binding: (_ for _ in ()).throw(RuntimeError("scan failed"))
    assert coordinator.scan_once() == 0

    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="pipeline")
        binding = IngressBindingService(conn, config).create(
            folder_path=str(tmp_path),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )

    class RaisingProcessor:
        def process_file(self, **_kwargs):
            raise RuntimeError("processor failed")

    coordinator = WatchFolderCoordinator(config, RaisingProcessor())
    coordinator.retry_attempts = 1
    assert coordinator._claim_and_process(
        source,
        {"id": binding["id"], "pipeline_version_id": version["id"]},
    ) is True


def test_scan_once_contains_unexpected_binding_failures(tmp_path, monkeypatch):
    config = build_context(tmp_path)
    coordinator = WatchFolderCoordinator(config, FakeProcessor())
    binding = {"id": "binding-1", "enabled": True}
    binding_service = Mock()
    binding_service.list.return_value = [binding]
    monkeypatch.setattr(coordinator_module, "connect", lambda _config: nullcontext(object()))
    monkeypatch.setattr(coordinator_module, "IngressBindingService", lambda *_args: binding_service)
    coordinator._scan_binding = Mock(side_effect=RuntimeError("unexpected scan"))
    assert coordinator.scan_once() == 0
