"""API tests for required exact pipeline selection during upload."""

from __future__ import annotations

from pathlib import Path

from modules.db.connection import connect
from modules.services.pipeline_template_service import PipelineTemplateService
from test.integration.test_batch_upload_api import build_client


def test_available_pipeline_versions_are_redacted_and_ordered(tmp_path, monkeypatch):
    client, config, _ = build_client(tmp_path, monkeypatch)

    response = client.get("/api/pipelines/available?source=upload")

    assert response.status_code == 200
    pipelines = response.json()["pipelines"]
    assert pipelines[0]["pipeline_version_id"] == config.pipeline_version_id
    assert pipelines[0]["step_count"] == 1
    assert "definition" not in pipelines[0]
    assert "tasks" not in pipelines[0]


def test_upload_requires_exactly_one_pipeline_version_before_writes(
    tmp_path, monkeypatch
):
    client, config, workflow = build_client(tmp_path, monkeypatch)

    missing = client.post(
        "/api/batches/upload",
        files=[
            ("files", ("invoice.pdf", b"%PDF-1.4\n", "application/pdf")),
        ],
    )
    repeated = client.post(
        "/api/batches/upload",
        files=[
            ("pipeline_version_id", (None, config.pipeline_version_id)),
            ("pipeline_version_id", (None, config.pipeline_version_id)),
            ("files", ("invoice.pdf", b"%PDF-1.4\n", "application/pdf")),
        ],
    )

    assert missing.status_code == 400
    assert repeated.status_code == 400
    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 0
    assert list(Path(config.get("watch_folder.processing_dir")).glob("*.pdf")) == []
    assert workflow.calls == []


def test_upload_rejects_unknown_or_operator_hidden_version(tmp_path, monkeypatch):
    client, config, workflow = build_client(tmp_path, monkeypatch)
    unknown = client.post(
        "/api/batches/upload",
        data={"pipeline_version_id": "unknown"},
        files=[
            ("files", ("invoice.pdf", b"%PDF-1.4\n", "application/pdf")),
        ],
    )

    with connect(config) as conn:
        version = conn.execute(
            "SELECT template_id FROM pipeline_versions WHERE id = ?",
            (config.pipeline_version_id,),
        ).fetchone()
        PipelineTemplateService(conn).update_template(
            version["template_id"], operator_selectable=False, user="admin"
        )

    forbidden = client.post(
        "/api/batches/upload",
        data={"pipeline_version_id": config.pipeline_version_id},
        files=[
            ("files", ("invoice.pdf", b"%PDF-1.4\n", "application/pdf")),
        ],
    )

    assert unknown.status_code == 400
    assert forbidden.status_code == 403
    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 0
    assert workflow.calls == []
