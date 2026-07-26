"""Operator page contracts for required pipeline-version selection."""

from modules.db.connection import connect
from modules.services.pipeline_template_service import PipelineTemplateService
from test.integration.test_batch_upload_api import build_client as build_api_client
from test.integration.test_new_ui_routes import (
    authenticate,
    build_client as build_page_client,
)


def test_upload_page_requires_explicit_pipeline_selection_contract(monkeypatch):
    client = build_page_client(monkeypatch, username="operator")
    authenticate(client)

    response = client.get("/app/upload")

    assert response.status_code == 200
    assert 'id="pipeline-version-list"' in response.text
    assert "No pipeline is selected automatically" in response.text
    assert 'id="start-processing-button"' in response.text
    assert 'disabled' in response.text
    assert "operator_pipeline_view_models.js" in response.text
    assert "pipeline_secrets" not in response.text


def test_available_list_can_be_empty_without_implicit_fallback(tmp_path, monkeypatch):
    client, config, _ = build_api_client(tmp_path, monkeypatch)
    with connect(config) as conn:
        template_id = conn.execute(
            "SELECT template_id FROM pipeline_versions WHERE id = ?",
            (config.pipeline_version_id,),
        ).fetchone()["template_id"]
        PipelineTemplateService(conn).update_template(
            template_id, status="inactive", user="admin"
        )

    response = client.get("/api/pipelines/available?source=upload")

    assert response.status_code == 200
    assert response.json()["pipelines"] == []
    assert response.json()["source"] == "upload"


def test_processing_page_contains_exact_assignment_presentation(monkeypatch):
    client = build_page_client(monkeypatch, username="operator")
    authenticate(client)

    response = client.get("/app/batches/batch-1")

    assert response.status_code == 200
    assert 'id="pipeline-assignment-summary"' in response.text
    assert "pinned-pipeline-identity" in response.text
    assert "schema content" not in response.text.lower()
