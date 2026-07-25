"""Tests for exact-version ingestion assignment."""

from __future__ import annotations

import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository
from modules.services.ingestion_assignment_service import (
    IngestionAssignmentError,
    IngestionAssignmentService,
)
from modules.services.pipeline_template_service import PipelineTemplateService
from test.helpers_sqlite import TempConfig


def publish_pipeline(conn, *, key, selectable=True):
    templates = PipelineTemplateService(
        conn, configured_secret_aliases={"test-api"}
    )
    definition = {
        "schema_version": 1,
        "pipeline": ["extract"],
        "tasks": {
            "extract": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
                "params": {
                    "api_key": {"$secret": "test-api"},
                    "fields": {
                        "supplier": {"alias": "Supplier", "type": "str"}
                    },
                },
            }
        },
    }
    created = templates.create_template(
        template_key=key,
        name=key.title(),
        operator_selectable=selectable,
        initial_definition=definition,
        user="admin",
    )
    published = templates.publish(
        created["template"]["id"], expected_revision=1, user="admin"
    )
    templates.update_template(
        created["template"]["id"], status="active", user="admin"
    )
    return created["template"], published["version"]


@pytest.fixture
def context(tmp_path):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"pipeline_secrets": {"test-api": "runtime-secret"}},
    )
    initialize_database(config)
    with connect(config) as conn:
        yield config, conn, IngestionAssignmentService(conn, config)


def test_available_versions_filter_role_and_keep_all_versions(context):
    _, conn, service = context
    template, first = publish_pipeline(conn, key="invoice", selectable=False)
    templates = PipelineTemplateService(
        conn, configured_secret_aliases={"test-api"}
    )
    second_definition = dict(first["definition"])
    second_definition["tasks"] = {
        **first["definition"]["tasks"],
        "extract": {
            **first["definition"]["tasks"]["extract"],
            "label": "Version 2",
        },
    }
    draft = templates.save_draft(
        template["id"],
        expected_revision=2,
        definition=second_definition,
        user="admin",
    )
    second = templates.publish(
        template["id"], expected_revision=draft["revision"], user="admin"
    )["version"]

    assert service.available_versions(role="operator") == []
    admin = service.available_versions(role="admin")
    assert [item["pipeline_version_id"] for item in admin] == [
        second["id"],
        first["id"],
    ]
    assert all("definition" not in item for item in admin)


def test_create_batch_pins_batch_roots_artifacts_and_audit(context, tmp_path):
    _, conn, service = context
    template, version = publish_pipeline(conn, key="invoice")
    files = []
    for index in range(2):
        path = tmp_path / f"{index}.pdf"
        path.write_bytes(b"%PDF-1.4")
        files.append(
            {
                "document_id": f"doc-{index}",
                "file_path": str(path),
                "original_filename": path.name,
                "status": "queued",
            }
        )

    created = service.create_batch(
        pipeline_version_id=version["id"],
        role="operator",
        source="web",
        assignment_source="upload",
        files=files,
        user="operator",
    )

    assert created["batch"]["pipeline_template_id"] == template["id"]
    assert created["batch"]["pipeline_version_id"] == version["id"]
    assert {
        document["pipeline_version_id"] for document in created["documents"]
    } == {version["id"]}
    assert conn.execute("SELECT COUNT(*) FROM document_files").fetchone()[0] == 2
    event = conn.execute(
        "SELECT event_json FROM audit_events WHERE event_type = "
        "'ingestion.pipeline.assigned'"
    ).fetchone()
    assert event is not None
    assert "definition" not in event["event_json"]


def test_create_batch_rolls_back_all_rows_on_artifact_failure(
    context, tmp_path, monkeypatch
):
    _, conn, service = context
    _, version = publish_pipeline(conn, key="invoice")
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        DocumentRepository,
        "add_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("artifact")),
    )
    with pytest.raises(RuntimeError, match="artifact"):
        service.create_batch(
            pipeline_version_id=version["id"],
            role="operator",
            source="web",
            assignment_source="upload",
            files=[
                {
                    "file_path": str(path),
                    "original_filename": path.name,
                    "status": "queued",
                }
            ],
            user="operator",
        )

    assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_selection_rejects_inactive_and_operator_hidden_versions(context):
    config, conn, service = context
    hidden, version = publish_pipeline(conn, key="hidden", selectable=False)
    with pytest.raises(IngestionAssignmentError, match="operators"):
        service.resolve_selection(version["id"], role="operator")

    config._values["pipeline_secrets"] = {}
    with pytest.raises(IngestionAssignmentError, match="unavailable or invalid"):
        service.resolve_selection(version["id"], role="admin")
    config._values["pipeline_secrets"] = {"test-api": "runtime-secret"}

    PipelineTemplateService(conn).update_template(
        hidden["id"], status="inactive", user="admin"
    )
    with pytest.raises(IngestionAssignmentError, match="not active"):
        service.resolve_selection(version["id"], role="admin")

    PipelineTemplateService(conn).update_template(
        hidden["id"], status="archived", user="admin"
    )
    with pytest.raises(IngestionAssignmentError, match="not active"):
        service.resolve_selection(version["id"], role="admin")
