"""Tests for sequential multi-folder watch coordination."""

from __future__ import annotations

from pathlib import Path

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.ingress_binding_service import IngressBindingService
from modules.services.watch_folder_coordinator import WatchFolderCoordinator
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
    assert len(processor.calls) == 2


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
    assert len(processor.calls) == 1
    with connect(config) as conn:
        row = conn.execute(
            "SELECT enabled FROM watch_folder_bindings WHERE id = ?",
            (bad_binding["id"],),
        ).fetchone()
    assert row["enabled"] == 1


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


def test_processing_retries_and_stop_are_coordinator_owned(tmp_path):
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
    assert len(processor.calls) == 3
    assert all(
        Path(call["filepath"]).parent == Path(config.get("watch_folder.processing_dir"))
        for call in processor.calls
    )
    coordinator.stop()
    assert coordinator.stop_event.is_set()
