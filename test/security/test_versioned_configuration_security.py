"""Cross-surface security regression tests for versioned configuration."""

from __future__ import annotations

import logging
from typing import cast

from fastapi import FastAPI

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.repositories import TaskRunRepository, UserRepository
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.pipeline_definition_service import PipelineDefinitionService
from modules.workflow_loader import WorkflowLoader
from test.integration.test_batch_upload_api import build_client
from test.workflow.test_workflow_task_run_tracking import _patch_prefect


def test_resolved_secret_stays_in_memory_only_across_runtime_api_audit_and_logs(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    sentinel = "PHASE13-RUNTIME-SECRET-DO-NOT-PERSIST"
    client, config, _ = build_client(tmp_path, monkeypatch)
    config._values["pipeline_secrets"]["test-api"] = sentinel
    with connect(config) as conn:
        UserRepository(conn).initialize(
            {"admin": "test-only", "operator": "test-only"}
        )
        version = conn.execute(
            """
            SELECT v.id, v.template_id
            FROM pipeline_versions v
            WHERE v.id = ?
            """,
            (config.pipeline_version_id,),
        ).fetchone()
        source = tmp_path / "secret-scan.pdf"
        source.write_bytes(b"%PDF-1.4\nphase-13")
        created = IngestionAssignmentService(conn, config).create_batch(
            pipeline_version_id=version["id"],
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
        executable = PipelineDefinitionService(conn, config).load_for_document(
            created["documents"][0]["id"]
        )

    resolved_values: list[str] = []

    class RuntimeTask:
        def __init__(self, config_manager, **params):
            if "api_key" in params:
                resolved_values.append(params["api_key"])

        def on_start(self, context):
            return None

        def run(self, context):
            return context

    class CleanupTask(RuntimeTask):
        pass

    caplog.set_level(logging.DEBUG)
    _patch_prefect(monkeypatch)
    monkeypatch.setattr("modules.workflow_loader.CleanupTask", CleanupTask)
    monkeypatch.setattr(
        WorkflowLoader,
        "_import_task_class",
        lambda self, module_name, class_name: RuntimeTask,
    )
    document = created["documents"][0]
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
            "file_path": str(source),
        }
    )
    assert resolved_values == [sentinel]

    cast(FastAPI, client.app).dependency_overrides[
        api_router.get_current_user
    ] = lambda: "admin"
    responses = [
        client.get("/api/pipelines/available?source=upload"),
        client.get("/api/admin/pipeline-templates?include_archived=true"),
        client.get(f"/api/admin/pipeline-templates/{version['template_id']}"),
        client.get(
            f"/api/admin/pipeline-templates/{version['template_id']}/versions/{version['id']}"
        ),
        client.get(
            f"/api/admin/pipeline-templates/{version['template_id']}/draft/export"
        ),
        client.get(
            f"/api/admin/pipeline-templates/{version['template_id']}/diff"
        ),
        client.get("/api/admin/audit"),
        client.get("/api/admin/pipeline-templates/unknown"),
    ]
    assert all(response.status_code in {200, 404} for response in responses)
    assert sentinel not in "\n".join(response.text for response in responses)

    with connect(config) as conn:
        persisted_text = "\n".join(
            [
                *[
                    str(row["definition_json"])
                    for row in conn.execute(
                        "SELECT definition_json FROM pipeline_versions"
                    ).fetchall()
                ],
                *[
                    str(row["definition_json"])
                    for row in conn.execute(
                        "SELECT definition_json FROM pipeline_drafts"
                    ).fetchall()
                ],
                *[
                    str(row["event_json"])
                    for row in conn.execute(
                        "SELECT event_json FROM audit_events"
                    ).fetchall()
                ],
                *[
                    f"{row.get('output_json', '')}\n{row.get('error', '')}"
                    for row in TaskRunRepository(conn).list_by_document(
                        document["id"]
                    )
                ],
            ]
        )
    assert sentinel not in persisted_text
    assert sentinel not in caplog.text


def test_untrusted_draft_and_module_inputs_cannot_be_selected_or_executed(
    tmp_path,
    monkeypatch,
) -> None:
    client, config, workflow = build_client(tmp_path, monkeypatch)
    with connect(config) as conn:
        UserRepository(conn).initialize(
            {"admin": "test-only", "operator": "test-only"}
        )
        template = conn.execute(
            "SELECT id FROM pipeline_templates LIMIT 1"
        ).fetchone()

    draft_upload = client.post(
        "/api/batches/upload",
        data={"pipeline_version_id": template["id"]},
        files=[
            (
                "files",
                ("draft.pdf", b"%PDF-1.4\n", "application/pdf"),
            )
        ],
    )
    assert draft_upload.status_code == 400
    assert workflow.calls == []

    cast(FastAPI, client.app).dependency_overrides[
        api_router.get_current_user
    ] = lambda: "admin"
    untrusted = client.post(
        "/api/admin/pipeline-templates",
        json={
            "template_key": "untrusted",
            "name": "Untrusted",
            "definition": {
                "schema_version": 1,
                "pipeline": ["run"],
                "tasks": {
                    "run": {
                        "module": "os",
                        "class": "system",
                        "params": {"expression": "__import__('os').system('x')"},
                    }
                },
            },
        },
    )
    assert untrusted.status_code == 200
    untrusted_id = untrusted.json()["template"]["id"]
    validation = client.post(
        f"/api/admin/pipeline-templates/{untrusted_id}/draft/validate",
        json={},
    )
    publication = client.post(
        f"/api/admin/pipeline-templates/{untrusted_id}/publish",
        json={"expected_revision": 1},
    )

    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert publication.status_code == 422
    assert "pipeline-task-not-approved" in {
        finding["code"]
        for finding in publication.json()["detail"]["findings"]
    }
    with connect(config) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM pipeline_versions WHERE template_id = ?",
            (untrusted_id,),
        ).fetchone()[0] == 0
