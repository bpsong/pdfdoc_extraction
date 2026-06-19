from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.migrations import initialize_database
from test.helpers_sqlite import TempConfig, initialize_test_users


BCRYPT_HASH = "$2b$12$eImiTXuWVxfM37uY4JANj.QlsWu1PErG3e1hYzWdG2ZHB5QoLGj7W"


def _base_config(tmp_path: Path) -> dict[str, Any]:
    upload_dir = tmp_path / "uploads"
    watch_dir = tmp_path / "watch"
    schema_dir = tmp_path / "schemas"
    upload_dir.mkdir(exist_ok=True)
    watch_dir.mkdir(exist_ok=True)
    schema_dir.mkdir(exist_ok=True)
    return {
        "web": {"upload_dir": str(upload_dir), "secret_key": "test-secret"},
        "watch_folder": {
            "dir": str(watch_dir),
            "processing_dir": str(tmp_path / "processing"),
        },
        "authentication": {"username": "admin", "password_hash": BCRYPT_HASH},
        "schema": {"directories": [str(schema_dir)]},
        "custom_steps": {
            "enabled": True,
            "registry": {
                "fake_extract": {
                    "module": "custom_step.extraction.fake_extract",
                    "class": "FakeExtractTask",
                }
            },
        },
        "tasks": {
            "extract": {
                "module": "custom_step.extraction.fake_extract",
                "class": "FakeExtractTask",
                "params": {
                    "api_key": "llx-test-key",
                    "fields": {
                        "invoice_number": {
                            "alias": "Invoice number",
                            "type": "str",
                        }
                    },
                },
                "on_error": "stop",
            }
        },
        "pipeline": ["extract"],
    }


def _client(monkeypatch, config: TempConfig, *, username: str = "operator") -> TestClient:
    initialize_database(config)
    initialize_test_users(config)
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: username
    return TestClient(app)


def _codes(payload: dict[str, Any]) -> set[str]:
    return {str(finding.get("code")) for finding in payload["findings"]}


def test_get_config_validation_validates_active_config_file(tmp_path: Path, monkeypatch) -> None:
    values = _base_config(tmp_path)
    config = TempConfig(tmp_path / "app.sqlite3", values)
    config._config_path.write_text(yaml.safe_dump(values), encoding="utf-8")
    client = _client(monkeypatch, config)

    response = client.get("/api/config/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["source"] == str(config._config_path)


def test_post_config_validation_validates_submitted_payload(tmp_path: Path, monkeypatch) -> None:
    values = _base_config(tmp_path)
    values["tasks"]["review"] = {
        "module": "standard_step.review.review_gate",
        "class": "ReviewGateTask",
        "params": {"confidence_threshold": -0.1},
        "on_error": "stop",
    }
    values["pipeline"] = ["extract", "review"]
    config = TempConfig(tmp_path / "app.sqlite3", values)
    client = _client(monkeypatch, config)

    response = client.post("/api/config/validation", json={"config": values})

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert "review-gate-invalid-confidence-threshold" in _codes(payload)


def test_post_pipeline_validate_reports_split_findings(tmp_path: Path, monkeypatch) -> None:
    values = _base_config(tmp_path)
    values["tasks"]["split"] = {
        "module": "standard_step.split.llamacloud_split",
        "class": "LlamaCloudSplitTask",
        "params": {
            "enabled": True,
            "categories": [{"name": "invoice"}],
            "split_dir": str(tmp_path / "split"),
        },
        "on_error": "stop",
    }
    values["pipeline"] = ["split", "extract"]
    config = TempConfig(tmp_path / "app.sqlite3", values)
    client = _client(monkeypatch, config)

    response = client.post("/api/pipeline/validate", json={"config": values})

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert "split-missing-runtime-api-key" in _codes(payload)


def test_validation_endpoints_reject_invalid_payload_shape(tmp_path: Path, monkeypatch) -> None:
    config = TempConfig(tmp_path / "app.sqlite3", _base_config(tmp_path))
    client = _client(monkeypatch, config)

    response = client.post("/api/config/validation", json={"config": "not-a-mapping"})

    assert response.status_code == 400
    assert response.json()["detail"] == "payload.config must be an object"


def test_post_config_validation_accepts_yaml_text_alias(tmp_path: Path, monkeypatch) -> None:
    values = _base_config(tmp_path)
    config = TempConfig(tmp_path / "app.sqlite3", values)
    client = _client(monkeypatch, config)

    response = client.post("/api/config/validation", json={"yaml_text": yaml.safe_dump(values)})

    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_admin_schema_validation_requires_admin(tmp_path: Path, monkeypatch) -> None:
    config = TempConfig(tmp_path / "app.sqlite3", _base_config(tmp_path))
    client = _client(monkeypatch, config, username="operator")

    response = client.get("/api/admin/schemas/validation")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_admin_schema_validation_endpoints_return_summary(tmp_path: Path, monkeypatch) -> None:
    values = _base_config(tmp_path)
    schema_dir = Path(values["schema"]["directories"][0])
    (schema_dir / "invoice.yaml").write_text(
        yaml.safe_dump({"fields": {"invoice_number": {"type": "string"}}}),
        encoding="utf-8",
    )
    (schema_dir / "bad.yaml").write_text(
        yaml.safe_dump({"fields": {"amount": {"type": "money"}}}),
        encoding="utf-8",
    )
    config = TempConfig(tmp_path / "app.sqlite3", values)
    client = _client(monkeypatch, config, username="admin")

    get_response = client.get("/api/admin/schemas/validation")
    post_response = client.post("/api/admin/schemas/validate-all", json={})

    assert get_response.status_code == 200
    assert post_response.status_code == 200
    payload = post_response.json()
    assert payload["valid"] is False
    assert payload["summary"] == {"errors": 1, "warnings": 0, "info": 0}
    assert {schema["name"] for schema in payload["schemas"]} == {"bad.yaml", "invoice.yaml"}
    assert payload["findings"][0]["code"] == "schema-invalid"
