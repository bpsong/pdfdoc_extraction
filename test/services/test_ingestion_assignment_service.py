"""Tests for exact-version ingestion assignment."""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository
from modules.services.ingestion_assignment_service import (
    IngestionAssignmentError,
    IngestionAssignmentService,
)
from modules.services.pipeline_definition_service import PipelineDefinitionError
import modules.services.ingestion_assignment_service as assignment_module
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


def test_available_versions_filter_role_and_keep_only_latest_version(context):
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
    assert [item["pipeline_version_id"] for item in admin] == [second["id"]]
    assert admin[0]["version_number"] == 2
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


def test_assignment_defensive_selection_and_mismatched_root_paths(context, monkeypatch):
    _, conn, service = context
    with pytest.raises(IngestionAssignmentError, match="must be selected"):
        service.resolve_selection("", role="operator")
    with pytest.raises(IngestionAssignmentError, match="must be selected"):
        service.resolve_selection(None, role="operator")

    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {
        "id": "v1",
        "template_id": "t1",
        "template_key": "key",
        "name": "Name",
        "template_status": "active",
        "operator_selectable": 1,
        "document_type": None,
        "operator_instructions": "",
    }
    isolated = IngestionAssignmentService(connection, context[0])
    with pytest.raises(IngestionAssignmentError, match="Unknown ingestion role"):
        isolated.resolve_selection("v1", role="guest")

    monkeypatch.setattr(
        assignment_module,
        "PipelineDefinitionService",
        lambda *args: Mock(load_version=Mock(side_effect=PipelineDefinitionError("wrong"))),
    )
    connection.execute.return_value.fetchall.return_value = [{"id": "bad"}]
    assert isolated.available_versions(role="admin") == []

    summary = {
        "pipeline_version_id": "v1",
        "pipeline_template_id": "t1",
        "template_key": "key",
        "name": "Name",
        "version_number": 1,
    }
    service.resolve_selection = Mock(return_value=summary)
    monkeypatch.setattr(assignment_module, "immediate_transaction", lambda _conn: nullcontext())
    monkeypatch.setattr(
        assignment_module,
        "BatchService",
        lambda _conn: Mock(
            create_ingestion_batch_with_documents=Mock(
                return_value={
                    "batch": {"id": "b", "pipeline_template_id": "t1", "pipeline_version_id": "v1"},
                    "documents": [{"id": "d", "pipeline_template_id": "wrong", "pipeline_version_id": "v1"}],
                }
            )
        ),
    )
    with pytest.raises(IngestionAssignmentError, match="does not match"):
        service.create_batch(
            pipeline_version_id="v1",
            role="system",
            source="web",
            assignment_source="upload",
            files=[],
            user="admin",
        )
