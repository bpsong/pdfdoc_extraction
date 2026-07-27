"""Cross-cutting Phase 13 scenarios for exact versioned pipeline execution."""

from __future__ import annotations

from typing import Any

import pytest

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository, TaskRunRepository
from modules.resume_manager import ResumeManager
from modules.services.ingestion_assignment_service import (
    IngestionAssignmentError,
    IngestionAssignmentService,
)
from modules.services.pipeline_definition_service import PipelineDefinitionService
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.review_schema_version_service import (
    ReviewSchemaVersionService,
)
from modules.workflow_loader import WorkflowLoader
from test.helpers_sqlite import TempConfig
from test.workflow.test_workflow_task_run_tracking import _patch_prefect


def _definition(schema_version_id: str, marker: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pipeline": ["extract", "review"],
        "tasks": {
            "extract": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
                "params": {
                    "api_key": {"$secret": "phase13-api"},
                    "fields": {
                        "supplier": {"alias": marker, "type": "str"},
                    },
                },
                "on_error": "stop",
            },
            "review": {
                "module": "standard_step.review.review_gate",
                "class": "ReviewGateTask",
                "params": {
                    "schema_version_id": schema_version_id,
                    "confidence": {"field_threshold": 0.8},
                    "review_scope": {"mode": "document"},
                },
                "on_error": "stop",
            },
        },
    }


def _publish_schema(
    service: ReviewSchemaVersionService,
    *,
    key: str,
    marker: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    created = service.create_template(
        schema_key=key,
        name=key.title(),
        initial_schema={
            "fields": {
                "supplier": {
                    "type": "string",
                    "label": marker,
                }
            }
        },
        user="admin",
    )
    version = service.publish(
        created["template"]["id"],
        expected_revision=1,
        user="admin",
    )["version"]
    service.update_template(
        created["template"]["id"],
        status="active",
        user="admin",
    )
    return created["template"], version


def _publish_pipeline(
    service: PipelineTemplateService,
    *,
    key: str,
    definition: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    created = service.create_template(
        template_key=key,
        name=key.title(),
        initial_definition=definition,
        user="admin",
    )
    version = service.publish(
        created["template"]["id"],
        expected_revision=1,
        user="admin",
    )["version"]
    service.update_template(
        created["template"]["id"],
        status="active",
        user="admin",
    )
    return created["template"], version


def _assigned_batch(
    service: IngestionAssignmentService,
    tmp_path,
    *,
    filename: str,
    pipeline_version_id: str,
) -> tuple[dict[str, Any], str]:
    source = tmp_path / filename
    source.write_bytes(b"%PDF-1.4\nphase-13")
    created = service.create_batch(
        pipeline_version_id=pipeline_version_id,
        role="operator",
        source="web",
        assignment_source="upload",
        files=[
            {
                "file_path": str(source),
                "original_filename": source.name,
                "status": "queued",
            }
        ],
        user="operator",
    )
    return created, str(source)


def test_independent_templates_stay_pinned_across_publication_and_archival(
    tmp_path,
    monkeypatch,
) -> None:
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"pipeline_secrets": {"phase13-api": "runtime-only-value"}},
    )
    initialize_database(config)
    with connect(config) as conn:
        schemas = ReviewSchemaVersionService(conn)
        alpha_schema, alpha_schema_v1 = _publish_schema(
            schemas,
            key="alpha-review",
            marker="Alpha schema v1",
        )
        _, beta_schema_v1 = _publish_schema(
            schemas,
            key="beta-review",
            marker="Beta schema v1",
        )
        pipelines = PipelineTemplateService(
            conn,
            configured_secret_aliases={"phase13-api"},
        )
        alpha_template, alpha_v1 = _publish_pipeline(
            pipelines,
            key="alpha",
            definition=_definition(alpha_schema_v1["id"], "Alpha v1"),
        )
        _, beta_v1 = _publish_pipeline(
            pipelines,
            key="beta",
            definition=_definition(beta_schema_v1["id"], "Beta v1"),
        )
        ingestion = IngestionAssignmentService(conn, config)
        alpha_batch, alpha_path = _assigned_batch(
            ingestion,
            tmp_path,
            filename="alpha.pdf",
            pipeline_version_id=alpha_v1["id"],
        )
        beta_batch, beta_path = _assigned_batch(
            ingestion,
            tmp_path,
            filename="beta.pdf",
            pipeline_version_id=beta_v1["id"],
        )
        resumable_batch, _ = _assigned_batch(
            ingestion,
            tmp_path,
            filename="alpha-resume.pdf",
            pipeline_version_id=alpha_v1["id"],
        )

    seen_markers: list[str] = []

    class RecordingTask:
        def __init__(self, config_manager, **params):
            self.params = params

        def on_start(self, context):
            return None

        def run(self, context):
            fields = self.params.get("fields", {})
            if fields:
                seen_markers.append(fields["supplier"]["alias"])
            return context

    class CleanupTask(RecordingTask):
        pass

    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    monkeypatch.setattr(
        WorkflowLoader,
        "_import_task_class",
        lambda self, module_name, class_name: RecordingTask,
    )

    for created, path in (
        (alpha_batch, alpha_path),
        (beta_batch, beta_path),
    ):
        document = created["documents"][0]
        with connect(config) as conn:
            executable = PipelineDefinitionService(
                conn,
                config,
            ).load_for_document(document["id"])
        workflow = WorkflowLoader(
            config,
            definition=executable.definition,
            pipeline_version_id=executable.version_id,
            pipeline_template_id=executable.template_id,
        ).load_workflow()
        assert workflow is not None
        workflow(
            {
                "id": document["id"],
                "batch_id": created["batch"]["id"],
                "document_id": document["id"],
                "file_path": path,
            }
        )

    with connect(config) as conn:
        schemas = ReviewSchemaVersionService(conn)
        alpha_schema_draft = schemas.save_draft(
            alpha_schema["id"],
            expected_revision=2,
            schema={
                "fields": {
                    "supplier": {
                        "type": "string",
                        "label": "Alpha schema v2",
                    }
                }
            },
            user="admin",
        )
        alpha_schema_v2 = schemas.publish(
            alpha_schema["id"],
            expected_revision=alpha_schema_draft["revision"],
            user="admin",
        )["version"]
        pipelines = PipelineTemplateService(
            conn,
            configured_secret_aliases={"phase13-api"},
        )
        alpha_draft = pipelines.save_draft(
            alpha_template["id"],
            expected_revision=2,
            definition=_definition(alpha_schema_v2["id"], "Alpha v2"),
            user="admin",
        )
        alpha_v2 = pipelines.publish(
            alpha_template["id"],
            expected_revision=alpha_draft["revision"],
            user="admin",
        )["version"]
        pinned_dependency = conn.execute(
            """
            SELECT schema_version_id
            FROM pipeline_version_schema_dependencies
            WHERE pipeline_version_id = ? AND task_key = 'review'
            """,
            (alpha_v1["id"],),
        ).fetchone()
        assert pinned_dependency["schema_version_id"] == alpha_schema_v1["id"]

        pipelines.update_template(
            alpha_template["id"],
            status="inactive",
            user="admin",
        )
        pipelines.update_template(
            alpha_template["id"],
            status="archived",
            user="admin",
        )
        schemas.update_template(
            alpha_schema["id"],
            status="inactive",
            user="admin",
        )
        schemas.update_template(
            alpha_schema["id"],
            status="archived",
            user="admin",
        )
        ingestion = IngestionAssignmentService(conn, config)
        for version_id in (alpha_v1["id"], alpha_v2["id"]):
            with pytest.raises(IngestionAssignmentError, match="not active"):
                ingestion.resolve_selection(version_id, role="operator")
        assert ingestion.resolve_selection(
            beta_v1["id"],
            role="operator",
        )["pipeline_version_id"] == beta_v1["id"]

        resumable_document = resumable_batch["documents"][0]
        documents = DocumentRepository(conn)
        documents.update_current_task(
            resumable_document["id"],
            0,
            "extract",
        )
        documents.update_status(
            resumable_document["id"],
            "review_completed",
        )

    assert ResumeManager(config).resume_document(
        resumable_document["id"],
        user="operator",
    )
    assert seen_markers == ["Alpha v1", "Beta v1"]

    with connect(config) as conn:
        alpha_runs = TaskRunRepository(conn).list_by_document(
            alpha_batch["documents"][0]["id"]
        )
        beta_runs = TaskRunRepository(conn).list_by_document(
            beta_batch["documents"][0]["id"]
        )
        resumed_runs = TaskRunRepository(conn).list_by_document(
            resumable_document["id"]
        )
    assert {run["pipeline_version_id"] for run in alpha_runs} == {alpha_v1["id"]}
    assert {run["pipeline_version_id"] for run in beta_runs} == {beta_v1["id"]}
    assert {run["pipeline_version_id"] for run in resumed_runs} == {
        alpha_v1["id"]
    }
    assert [run["task_key"] for run in resumed_runs] == ["review", "cleanup_task"]
