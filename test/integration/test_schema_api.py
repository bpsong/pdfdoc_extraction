from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.migrations import initialize_database
from test.helpers_sqlite import TempConfig, initialize_test_users


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
    initialize_test_users(config)

    def fake_get_dependencies():
        return config, _FakeAuth(), None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app = FastAPI()
    app.include_router(api_router.build_router())
    app.dependency_overrides[api_router.get_current_user] = lambda: user
    return TestClient(app), config


def test_schema_api_reads_and_validates_files_but_rejects_legacy_mutations(
    tmp_path,
    monkeypatch,
) -> None:
    client, config = _client(tmp_path, monkeypatch)
    schema = {
        "title": "Invoice",
        "description": "Invoice review schema",
        "fields": {
            "supplier": {"type": "string", "label": "Supplier", "required": True},
            "total": {"type": "number", "required": True},
        },
    }

    schema_path = Path(config.get("schema.directories")[0]) / "invoice.yaml"
    schema_path.write_text(
        """
title: Invoice
description: Invoice review schema
fields:
  supplier:
    type: string
    label: Supplier
    required: true
  total:
    type: number
    required: true
""".lstrip(),
        encoding="utf-8",
    )

    create_response = client.post("/api/schemas", json={"name": "copy.yaml", "schema": schema})
    assert create_response.status_code == 410
    assert "/api/admin/review-schemas" in create_response.json()["detail"]

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
    assert update_response.status_code == 410
    assert "/api/admin/review-schemas/{template_id}/draft" in update_response.json()["detail"]

    duplicate_response = client.post("/api/schemas/invoice.yaml/duplicate", json={"new_name": "invoice_copy.yaml"})
    assert duplicate_response.status_code == 410
    assert "versioned review-schema template" in duplicate_response.json()["detail"]
    assert schema_path.exists()
    assert not (schema_path.parent / "invoice_copy.yaml").exists()


def test_schema_api_requires_admin_user(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch, user="operator")

    response = client.get("/api/schemas")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_schema_api_rejects_invalid_pattern_and_length_range(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/schemas/invalid.yaml/validate",
        json={
            "schema": {
                "title": "Invalid",
                "fields": {
                    "supplier": {
                        "type": "string",
                        "pattern": "[",
                        "min_length": 10,
                        "max_length": 2,
                    }
                },
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert {finding["path"] for finding in payload["findings"]} == {
        "supplier.pattern",
        "supplier.min_length",
    }


def test_schema_pattern_test_api_reports_match_and_syntax_errors(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    matching = client.post(
        "/api/schemas/pattern-test",
        json={"pattern": r"^[A-Z]{2}\d{3}$", "example": "AB123"},
    )
    invalid = client.post(
        "/api/schemas/pattern-test",
        json={"pattern": "[", "example": "AB123"},
    )

    assert matching.status_code == 200
    assert matching.json() == {"valid": True, "matches": True, "error": None}
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False
    assert "Invalid regular expression" in invalid.json()["error"]


def test_schema_api_rejects_absolute_path_outside_schema_directory(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    outside_schema = tmp_path / "outside.yaml"
    outside_schema.write_text(
        """
title: Outside
fields:
  total:
    type: float
""",
        encoding="utf-8",
    )

    response = client.get(f"/api/schemas/{quote(str(outside_schema), safe='')}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Schema not found"


def test_legacy_schema_update_returns_actionable_versioned_endpoint(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    schema = {
        "title": "Invoice",
        "fields": {"supplier": {"type": "string", "required": True}},
    }

    response = client.put("/api/schemas/invoice.yaml", json={"schema": schema})

    assert response.status_code == 410
    assert response.json()["detail"].endswith(
        "Use /api/admin/review-schemas/{template_id}/draft."
    )
