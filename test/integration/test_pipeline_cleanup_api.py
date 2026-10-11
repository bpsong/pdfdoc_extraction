"""Administrative archive and cleanup API contracts."""
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI

import modules.api_router as api_router
from modules.db.connection import connect
from modules.services.ingestion_assignment_service import IngestionAssignmentService, IngestionAssignmentError
from test.helpers_cleanup import CUTOFF, seed_history
from test.integration.test_versioned_pipeline_api import _admin_client


def test_archive_then_cleanup_keeps_definition_and_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, config = _admin_client(tmp_path, monkeypatch)
    with connect(config) as conn:
        template = dict(conn.execute("SELECT * FROM pipeline_templates WHERE id=(SELECT template_id FROM pipeline_versions WHERE id=?)", (config.pipeline_version_id,)).fetchone())
        data = seed_history(conn, tmp_path, template["id"], config.pipeline_version_id)
    url = f"/api/admin/pipeline-templates/{template['id']}"
    assert client.get(url + "/archive-preview").json()["can_archive"] is False
    assert client.post(url + "/archive", json={"confirmation_name": template["name"]}).status_code == 409
    assert client.patch(url, json={"status": "inactive"}).status_code == 200
    assert client.get(url + "/archive-preview").json()["can_archive"] is True
    assert client.post(url + "/archive", json={"confirmation_name": "wrong"}).status_code == 400
    assert client.post(url + "/archive", json={"confirmation_name": template["name"]}).status_code == 200
    assert template["id"] not in [row["id"] for row in client.get("/api/admin/pipeline-templates").json()["templates"]]
    assert template["id"] in [row["id"] for row in client.get("/api/admin/pipeline-templates?include_archived=true").json()["templates"]]
    assert client.patch(url, json={"status": "active"}).status_code == 409
    assert client.post(url + "/cleanup-preview", json={"cutoff_date": "invalid"}).status_code == 400
    preview = client.post(url + "/cleanup-preview", json={"cutoff_date": CUTOFF}).json()
    confirmation = {"preview_id": preview["preview_id"], "confirmation_name": template["name"]}
    assert client.post(url + "/cleanup", json={**confirmation, "confirmation_name": "wrong"}).status_code == 400
    response = client.post(url + "/cleanup", json=confirmation)
    assert response.status_code == 200
    assert response.json()["deleted"]["documents"] == 1
    assert response.json()["files_deleted"] == 0
    assert data["file_path"].exists()
    assert client.get(url).status_code == 200
    assert client.get(f"/api/upload-submissions/{data['receipt']}").json() == {"status": "purged"}
    assert client.post(url + "/cleanup", json=confirmation).status_code == 409
    assert client.post("/api/admin/pipeline-templates/missing/cleanup-preview", json={"cutoff_date": CUTOFF}).status_code == 404


@pytest.mark.parametrize("action", ["archive-preview", "archive", "cleanup-preview", "cleanup"])
def test_lifecycle_actions_require_admin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    client, _ = _admin_client(tmp_path, monkeypatch)
    cast(FastAPI, client.app).dependency_overrides[api_router.get_current_user] = lambda: "operator"
    url = f"/api/admin/pipeline-templates/any/{action}"
    result = client.get(url) if action == "archive-preview" else client.post(url, json={})
    assert result.status_code == 403


@pytest.mark.parametrize("payload", [{}, {"cutoff_date": None}, {"cutoff_date": 20260101},
                                     {"cutoff_date": True}, {"cutoff_date": []}, {"cutoff_date": {}}])
def test_cleanup_preview_rejects_non_text_cutoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict,
) -> None:
    client, config = _admin_client(tmp_path, monkeypatch)
    with connect(config) as conn:
        template_id = conn.execute(
            "SELECT template_id FROM pipeline_versions WHERE id=?", (config.pipeline_version_id,),
        ).fetchone()[0]
    response = client.post(f"/api/admin/pipeline-templates/{template_id}/cleanup-preview", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Choose a valid cutoff date (YYYY-MM-DD)."
    with connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pipeline_cleanup_previews").fetchone()[0] == 0


def test_cleanup_rechecks_claimed_work_and_keeps_every_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, config = _admin_client(tmp_path, monkeypatch)
    with connect(config) as conn:
        template = dict(conn.execute("SELECT * FROM pipeline_templates LIMIT 1").fetchone())
        data = seed_history(conn, tmp_path, template["id"], config.pipeline_version_id)
    url = f"/api/admin/pipeline-templates/{template['id']}"
    preview = client.post(url + "/cleanup-preview", json={"cutoff_date": CUTOFF}).json()
    with connect(config) as conn:
        conn.execute("UPDATE processing_jobs SET status='running' WHERE id=?", (data["job"],))
    result = client.post(url + "/cleanup", json={"preview_id": preview["preview_id"], "confirmation_name": template["name"]})
    assert result.status_code == 409
    with connect(config) as conn:
        assert conn.execute("SELECT 1 FROM documents WHERE id=?", (data["document_id"],)).fetchone()
        assert conn.execute("SELECT 1 FROM audit_events WHERE id=?", (data["audit"],)).fetchone()


def test_cleanup_receipt_cannot_recreate_old_submission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, config = _admin_client(tmp_path, monkeypatch)
    with connect(config) as conn:
        template = dict(conn.execute("SELECT * FROM pipeline_templates LIMIT 1").fetchone())
        data = seed_history(conn, tmp_path, template["id"], config.pipeline_version_id)
    url = f"/api/admin/pipeline-templates/{template['id']}"
    preview = client.post(url + "/cleanup-preview", json={"cutoff_date": CUTOFF}).json()
    assert client.post(url + "/cleanup", json={"preview_id": preview["preview_id"], "confirmation_name": template["name"]}).status_code == 200
    with connect(config) as conn:
        with pytest.raises(IngestionAssignmentError, match="cleaned up"):
            IngestionAssignmentService(conn, config).create_batch(
                pipeline_version_id=config.pipeline_version_id, role="admin", source="web", assignment_source="upload",
                files=[], user="admin", submission_id=data["receipt"], fingerprint="synthetic-fingerprint",
            )
        assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 0


@pytest.mark.parametrize("action", ["archive-preview", "archive", "cleanup-preview", "cleanup"])
def test_lifecycle_actions_require_authentication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    client, _ = _admin_client(tmp_path, monkeypatch)
    cast(FastAPI, client.app).dependency_overrides.pop(api_router.get_current_user)
    url = f"/api/admin/pipeline-templates/any/{action}"
    result = client.get(url) if action == "archive-preview" else client.post(url, json={})
    assert result.status_code == 401
