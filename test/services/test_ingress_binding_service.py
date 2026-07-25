"""Tests for watch-folder binding path and lifecycle policy."""

from __future__ import annotations

import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.ingress_binding_service import (
    IngressBindingConflictError,
    IngressBindingService,
)
from test.helpers_sqlite import TempConfig
from test.services.test_ingestion_assignment_service import publish_pipeline


@pytest.fixture
def context(tmp_path):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "watch_folder": {"processing_dir": str(tmp_path / "processing")},
            "pipeline_secrets": {"test-api": "runtime-secret"},
        },
    )
    initialize_database(config)
    with connect(config) as conn:
        _, version = publish_pipeline(conn, key="invoice")
        yield config, conn, IngressBindingService(conn, config), version


def test_binding_normalizes_relative_windows_path_and_rejects_overlap(
    context, tmp_path
):
    _, _, service, version = context
    parent = tmp_path / "incoming"
    child = parent / "nested"
    child.mkdir(parents=True)

    created = service.create(
        folder_path="incoming\\",
        pipeline_version_id=version["id"],
        enabled=True,
        user="admin",
    )
    assert created["normalized_path"].endswith("incoming")

    with pytest.raises(IngressBindingConflictError, match="nests"):
        service.create(
            folder_path=str(child),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
    with pytest.raises(IngressBindingConflictError, match="nests"):
        service.create(
            folder_path=str(parent).upper(),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )


def test_binding_rejects_drive_root_missing_and_file_paths(context, tmp_path):
    _, _, service, version = context
    regular_file = tmp_path / "not-a-folder"
    regular_file.write_text("test", encoding="utf-8")

    with pytest.raises(IngressBindingConflictError, match="drive root"):
        service.create(
            folder_path=tmp_path.anchor,
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
    with pytest.raises(IngressBindingConflictError, match="does not exist"):
        service.create(
            folder_path=str(tmp_path / "missing"),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )
    with pytest.raises(IngressBindingConflictError, match="not a directory"):
        service.create(
            folder_path=str(regular_file),
            pipeline_version_id=version["id"],
            enabled=True,
            user="admin",
        )


def test_binding_enable_requires_active_template_but_disabled_history_survives(
    context, tmp_path
):
    _, conn, service, version = context
    folder = tmp_path / "incoming"
    folder.mkdir()
    template_id = version["template_id"]
    conn.execute(
        "UPDATE pipeline_templates SET status = 'inactive' WHERE id = ?",
        (template_id,),
    )
    conn.commit()

    disabled = service.create(
        folder_path=str(folder),
        pipeline_version_id=version["id"],
        enabled=False,
        user="admin",
    )
    with pytest.raises(IngressBindingConflictError):
        service.update(disabled["id"], enabled=True, user="admin")


def test_referenced_binding_cannot_be_deleted(context, tmp_path):
    config, conn, service, version = context
    folder = tmp_path / "incoming"
    folder.mkdir()
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    binding = service.create(
        folder_path=str(folder),
        pipeline_version_id=version["id"],
        enabled=True,
        user="admin",
    )
    IngestionAssignmentService(conn, config).create_batch(
        pipeline_version_id=version["id"],
        role="system",
        source="watch_folder",
        assignment_source="watch_folder",
        ingress_binding_id=binding["id"],
        files=[
            {
                "file_path": str(pdf),
                "original_filename": pdf.name,
                "status": "processing",
            }
        ],
        user=None,
    )

    with pytest.raises(IngressBindingConflictError, match="cannot be deleted"):
        service.delete(binding["id"], user="admin")
