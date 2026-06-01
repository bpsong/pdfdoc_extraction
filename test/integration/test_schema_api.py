from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import ReviewRepository, TaskRunRepository
from modules.services.batch_service import BatchService
from test.helpers_sqlite import TempConfig


class _FakeAuth:
    token_exp_minutes = 30


def _client(tmp_path: Path, monkeypatch, *, user: str = "admin") -> tuple[TestClient, TempConfig]:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "schema": {"directories": [str(schema_dir)]},
            "auth": {"roles_enabled": True, "default_admin_users": ["admin"]},
            "ui": {"admin_enabled": True},
            "authentication": {"username": "admin"},
        },
    )
    initialize_database(config)

    def fake_get_dependencies():
        return config, _FakeAuth(), None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app = FastAPI()
    app.include_router(api_router.build_router())
    app.dependency_overrides[api_router.get_current_user] = lambda: user
    return TestClient(app), config


def test_schema_api_create_get_validate_update_and_duplicate(tmp_path, monkeypatch) -> None:
    client, config = _client(tmp_path, monkeypatch)
    schema = {
        "title": "Invoice",
        "description": "Invoice review schema",
        "fields": {
            "supplier": {"type": "string", "label": "Supplier", "required": True},
            "total": {"type": "number", "required": True},
        },
    }

    create_response = client.post("/api/schemas", json={"name": "invoice.yaml", "schema": schema})
    assert create_response.status_code == 200
    assert create_response.json()["schema"]["name"] == "invoice.yaml"

    list_response = client.get("/api/schemas")
    assert list_response.status_code == 200
    assert [item["name"] for item in list_response.json()["schemas"]] == ["invoice.yaml"]

    get_response = client.get("/api/schemas/invoice.yaml")
    assert get_response.status_code == 200
    assert get_response.json()["schema"]["fields"][0]["key"] == "supplier"
    assert "fields:" in get_response.json()["content"]

    validate_response = client.post(
        "/api/schemas/invoice.yaml/validate",
        json={"schema": {"fields": {"status": {"type": "enum"}}}},
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["valid"] is False
    assert validate_response.json()["findings"][0]["path"] == "status.choices"

    updated = {**schema, "fields": {**schema["fields"], "approved": {"type": "boolean"}}}
    update_response = client.put("/api/schemas/invoice.yaml", json={"schema": updated})
    assert update_response.status_code == 200
    assert any(field["key"] == "approved" for field in update_response.json()["schema"]["fields"])

    duplicate_response = client.post("/api/schemas/invoice.yaml/duplicate", json={"new_name": "invoice_copy.yaml"})
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["schema"]["name"] == "invoice_copy.yaml"

    assert (Path(config.get("schema.directories")[0]) / "invoice_copy.yaml").exists()


def test_schema_api_requires_admin_user(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch, user="operator")

    response = client.get("/api/schemas")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_schema_update_reports_active_review_warning(tmp_path, monkeypatch) -> None:
    client, config = _client(tmp_path, monkeypatch)
    schema = {
        "title": "Invoice",
        "fields": {"supplier": {"type": "string", "required": True}},
    }
    assert client.post("/api/schemas", json={"name": "invoice.yaml", "schema": schema}).status_code == 200

    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
        task_run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            task_key="review_gate",
            task_index=1,
            module_name="standard_step.review.review_gate",
            class_name="ReviewGateTask",
        )
        ReviewRepository(conn).create_review_item(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            queue_name="default",
            reason="low_confidence",
            scope="low_confidence_fields",
            created_by_task_run_id=task_run["id"],
            metadata={"schema_file": "invoice.yaml"},
        )

    response = client.put("/api/schemas/invoice.yaml", json={"schema": schema})

    assert response.status_code == 200
    warning: dict[str, Any] = response.json()["active_review_warning"]
    assert warning["active_review_count"] == 1
    assert "Schema changes may affect active review items" in warning["message"]
