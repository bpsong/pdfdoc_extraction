"""Pinned pipeline definition and workflow execution tests."""

from __future__ import annotations

import json

import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import TaskRunRepository
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.pipeline_definition_service import (
    PipelineDefinitionError,
    PipelineDefinitionService,
)
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.review_service import ReviewService, ReviewServiceError
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.workflow_loader import WorkflowLoader
from modules.workflow_manager import WorkflowManager
from test.helpers_sqlite import TempConfig
from test.workflow.test_workflow_task_run_tracking import _patch_prefect


def publish_definition(conn, definition, *, key="pipeline", aliases=None):
    service = PipelineTemplateService(
        conn, configured_secret_aliases=set(aliases or [])
    )
    created = service.create_template(
        template_key=key,
        name=key.title(),
        initial_definition=definition,
        user="admin",
    )
    version = service.publish(
        created["template"]["id"], expected_revision=1, user="admin"
    )["version"]
    service.update_template(created["template"]["id"], status="active", user="admin")
    return version


def extraction_definition(marker):
    return {
        "schema_version": 1,
        "pipeline": ["extract"],
        "tasks": {
            "extract": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
                "label": marker,
                "params": {
                    "api_key": {"$secret": "extract-api"},
                    "fields": {
                        "supplier": {"alias": "Supplier", "type": "str"}
                    },
                },
                "on_error": "stop",
            }
        },
    }


def test_definition_load_resolves_secrets_and_exact_archived_schema(tmp_path):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"pipeline_secrets": {"extract-api": "runtime-secret"}},
    )
    initialize_database(config)
    with connect(config) as conn:
        schemas = ReviewSchemaVersionService(conn)
        schema_template = schemas.create_template(
            schema_key="invoice-review",
            name="Invoice",
            initial_schema={"fields": {"supplier": {"type": "string"}}},
            user="admin",
        )
        schema_version = schemas.publish(
            schema_template["template"]["id"], expected_revision=1, user="admin"
        )["version"]
        schemas.update_template(
            schema_template["template"]["id"], status="active", user="admin"
        )
        definition = {
            "schema_version": 1,
            "pipeline": ["extract", "review"],
            "tasks": {
                "extract": {
                    "module": "standard_step.extraction.extract_pdf",
                    "class": "ExtractPdfTask",
                    "params": {
                        "api_key": {"$secret": "extract-api"},
                        "fields": {
                            "supplier": {"alias": "Supplier", "type": "str"}
                        },
                    },
                },
                "review": {
                    "module": "standard_step.review.review_gate",
                    "class": "ReviewGateTask",
                    "params": {
                        "schema_version_id": schema_version["id"],
                        "confidence": {"field_threshold": 0.8},
                        "review_scope": {"mode": "document"},
                    },
                },
            },
        }
        pipeline = publish_definition(
            conn, definition, aliases={"extract-api"}
        )
        revised = schemas.save_draft(
            schema_template["template"]["id"],
            expected_revision=2,
            schema={
                "fields": {
                    "supplier": {"type": "string"},
                    "invoice_number": {"type": "string"},
                }
            },
            user="admin",
        )
        newer_schema = schemas.publish(
            schema_template["template"]["id"],
            expected_revision=revised["revision"],
            user="admin",
        )["version"]
        schemas.update_template(
            schema_template["template"]["id"], status="inactive", user="admin"
        )
        schemas.update_template(
            schema_template["template"]["id"], status="archived", user="admin"
        )

        executable = PipelineDefinitionService(conn, config).load_version(
            pipeline["id"]
        )

        assert executable.tasks["extract"]["params"]["api_key"] == "runtime-secret"
        assert executable.tasks["review"]["params"]["_review_schema"][
            "fields"
        ]["supplier"]["type"] == "string"
        assert "invoice_number" not in executable.tasks["review"]["params"][
            "_review_schema"
        ]["fields"]
        assert newer_schema["id"] != schema_version["id"]
        with pytest.raises(TypeError):
            json.dumps(executable.definition)

    missing_secret = TempConfig(tmp_path / "app.sqlite3")
    with connect(missing_secret) as conn:
        with pytest.raises(PipelineDefinitionError):
            PipelineDefinitionService(conn, missing_secret).load_version(
                pipeline["id"]
            )


def test_concurrent_documents_use_their_own_definition(tmp_path, monkeypatch):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"pipeline_secrets": {"extract-api": "runtime-secret"}},
    )
    initialize_database(config)
    paths = []
    with connect(config) as conn:
        first = publish_definition(
            conn,
            extraction_definition("first"),
            key="first",
            aliases={"extract-api"},
        )
        second = publish_definition(
            conn,
            extraction_definition("second"),
            key="second",
            aliases={"extract-api"},
        )
        ingestion = IngestionAssignmentService(conn, config)
        for index, version in enumerate((first, second)):
            path = tmp_path / f"{index}.pdf"
            path.write_bytes(b"%PDF-1.4")
            paths.append(path)
            created = ingestion.create_batch(
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
            paths[index] = (path, created)

    seen = []

    def fake_load(self, start_task_index=0):
        marker = self.task_defs["extract"]["label"]

        def run(context):
            seen.append((context["document_id"], marker))
            return context

        return run

    monkeypatch.setattr(WorkflowLoader, "load_workflow", fake_load)
    manager = WorkflowManager(config)
    for path, created in paths:
        document = created["documents"][0]
        assert manager.trigger_workflow_for_file(
            str(path),
            document["id"],
            path.name,
            "web",
            batch_id=created["batch"]["id"],
            document_id=document["id"],
        )

    assert [marker for _, marker in seen] == ["first", "second"]


def test_task_runs_are_attributed_to_document_version(tmp_path, monkeypatch):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"pipeline_secrets": {"extract-api": "runtime-secret"}},
    )
    initialize_database(config)
    with connect(config) as conn:
        version = publish_definition(
            conn,
            extraction_definition("marker"),
            aliases={"extract-api"},
        )
        path = tmp_path / "invoice.pdf"
        path.write_bytes(b"%PDF-1.4")
        created = IngestionAssignmentService(conn, config).create_batch(
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
        executable = PipelineDefinitionService(conn, config).load_for_document(
            created["documents"][0]["id"]
        )

    class StoreTask:
        def __init__(self, config_manager, **params):
            self.params = params

        def on_start(self, context):
            pass

        def run(self, context):
            return context

    class CleanupTask(StoreTask):
        pass

    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    monkeypatch.setattr(
        WorkflowLoader,
        "_import_task_class",
        lambda self, module_name, class_name: StoreTask,
    )
    loader = WorkflowLoader(
        config,
        definition=executable.definition,
        pipeline_version_id=executable.version_id,
        pipeline_template_id=executable.template_id,
    )
    document = created["documents"][0]
    workflow = loader.load_workflow()
    assert workflow is not None
    workflow(
        {
            "id": document["id"],
            "batch_id": created["batch"]["id"],
            "document_id": document["id"],
            "file_path": str(path),
        }
    )

    with connect(config) as conn:
        runs = TaskRunRepository(conn).list_by_document(document["id"])
    assert [run["pipeline_version_id"] for run in runs] == [
        version["id"],
        version["id"],
    ]


def test_review_item_identity_matches_pinned_task_dependency(tmp_path):
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"pipeline_secrets": {"extract-api": "runtime-secret"}},
    )
    initialize_database(config)
    with connect(config) as conn:
        schemas = ReviewSchemaVersionService(conn)
        schema_template = schemas.create_template(
            schema_key="review",
            name="Review",
            initial_schema={"fields": {"supplier": {"type": "string"}}},
            user="admin",
        )
        schema_version = schemas.publish(
            schema_template["template"]["id"], expected_revision=1, user="admin"
        )["version"]
        revised = schemas.save_draft(
            schema_template["template"]["id"],
            expected_revision=2,
            schema={"fields": {"invoice_number": {"type": "string"}}},
            user="admin",
        )
        other_version = schemas.publish(
            schema_template["template"]["id"],
            expected_revision=revised["revision"],
            user="admin",
        )["version"]
        schemas.update_template(
            schema_template["template"]["id"], status="active", user="admin"
        )
        definition = {
            "schema_version": 1,
            "pipeline": ["extract", "review"],
            "tasks": {
                "extract": {
                    "module": "standard_step.extraction.extract_pdf",
                    "class": "ExtractPdfTask",
                    "params": {
                        "api_key": {"$secret": "extract-api"},
                        "fields": {
                            "supplier": {"alias": "Supplier", "type": "str"}
                        },
                    },
                },
                "review": {
                    "module": "standard_step.review.review_gate",
                    "class": "ReviewGateTask",
                    "params": {
                        "schema_version_id": schema_version["id"],
                        "confidence": {"field_threshold": 0.8},
                        "review_scope": {"mode": "document"},
                    },
                },
            },
        }
        pipeline = publish_definition(
            conn, definition, aliases={"extract-api"}
        )
        source = tmp_path / "invoice.pdf"
        source.write_bytes(b"%PDF-1.4")
        created = IngestionAssignmentService(conn, config).create_batch(
            pipeline_version_id=pipeline["id"],
            role="operator",
            source="web",
            assignment_source="upload",
            files=[
                {
                    "file_path": str(source),
                    "original_filename": source.name,
                    "status": "processing",
                }
            ],
            user="operator",
        )
        document = created["documents"][0]
        task_run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=document["id"],
            task_key="review",
            task_index=1,
            module_name="standard_step.review.review_gate",
            class_name="ReviewGateTask",
            pipeline_version_id=pipeline["id"],
        )
        service = ReviewService(conn, config)

        with pytest.raises(ReviewServiceError, match="pinned pipeline dependency"):
            service.create_review_item(
                batch_id=created["batch"]["id"],
                document_id=document["id"],
                queue_name="default",
                reason="low_confidence",
                scope="document",
                created_by_task_run_id=task_run["id"],
                metadata={"schema_hash": other_version["content_hash"]},
                review_schema_version_id=other_version["id"],
            )

        item = service.create_review_item(
            batch_id=created["batch"]["id"],
            document_id=document["id"],
            queue_name="default",
            reason="low_confidence",
            scope="document",
            created_by_task_run_id=task_run["id"],
            metadata={"schema_hash": schema_version["content_hash"]},
            review_schema_version_id=schema_version["id"],
        )
        assert item["review_schema_version_id"] == schema_version["id"]
