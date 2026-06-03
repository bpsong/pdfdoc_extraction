from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.migrations import initialize_database
from test.helpers_sqlite import TempConfig


def _config(tmp_path: Path) -> TempConfig:
    split_dir = tmp_path / "split"
    upload_dir = tmp_path / "uploads"
    processing_dir = tmp_path / "processing"
    watch_dir = tmp_path / "watch"
    for directory in (split_dir, upload_dir, processing_dir, watch_dir):
        directory.mkdir()

    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "auth": {"roles_enabled": True, "default_admin_users": ["admin"]},
            "authentication": {"username": "admin"},
            "ui": {"app_name": "DocFlow AI", "page_size": 50, "admin_enabled": True},
            "web": {"upload_dir": str(upload_dir)},
            "watch_folder": {
                "dir": str(watch_dir),
                "processing_dir": str(processing_dir),
            },
            "review": {"lock_timeout_minutes": 45, "default_queue_name": "priority_review"},
            "app_storage": {
                "split_dir": str(split_dir),
                "exports_dir": str(tmp_path / "exports"),
                "nested": {
                    "access_token": "storage-access-token",
                    "safe_label": "storage",
                },
            },
            "tasks": {
                "split": {
                    "module": "standard_step.split.llamacloud_split",
                    "class": "LlamaCloudSplitTask",
                    "params": {
                        "enabled": True,
                        "api_key": "llx-secret",
                        "categories": [{"name": "invoice", "description": "Invoices"}],
                        "allow_uncategorized": "omit",
                        "split_dir": str(split_dir),
                    },
                },
                "extract": {
                    "module": "standard_step.extraction.extract_pdf_v2",
                    "class": "ExtractPdfV2Task",
                    "params": {
                        "api_key": "extract-secret",
                        "headers": {"Authorization": "Bearer extract-token"},
                        "fields": {"supplier": {"alias": "Supplier", "type": "str"}},
                    },
                },
                "review": {
                    "module": "standard_step.review.review_gate",
                    "class": "ReviewGateTask",
                    "params": {
                        "confidence_threshold": 0.91,
                        "review_scope": "document",
                        "always_review": True,
                        "field_threshold_overrides": {"total": 0.96},
                        "per_document_type_thresholds": {"invoice": 0.88},
                        "schema_file": "invoice.yaml",
                    },
                },
            },
            "pipeline": ["split", "extract", "review"],
        },
    )
    initialize_database(config)
    return config


def _client(monkeypatch: pytest.MonkeyPatch, config: TempConfig, *, username: str) -> TestClient:
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies() -> tuple[Any, None, None, None, None]:
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: username
    return TestClient(app)


@pytest.mark.parametrize("username", ["operator", "admin"])
def test_settings_api_returns_non_secret_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    username: str,
) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config, username=username)

    response = client.get("/api/settings")

    assert response.status_code == 200
    body = response.text
    for secret in (
        "llx-secret",
        "extract-secret",
        "Bearer extract-token",
        "storage-access-token",
    ):
        assert secret not in body
    assert "[REDACTED]" in body

    payload = response.json()
    assert payload["secrets_redacted"] is True
    assert payload["application"]["page_size"] == 50
    assert payload["paths"]["watch_folder_dir"] == str(tmp_path / "watch")
    assert payload["paths"]["processing_dir"] == str(tmp_path / "processing")
    assert payload["paths"]["upload_dir"] == str(tmp_path / "uploads")
    assert payload["paths"]["app_storage"]["nested"]["access_token"] == "[REDACTED]"

    assert payload["review"]["lock_timeout_minutes"] == 45
    assert payload["review"]["default_queue_name"] == "priority_review"
    assert payload["review"]["review_gate"] == {
        "configured": True,
        "task_key": "review",
        "confidence_threshold": 0.91,
        "review_scope": "document",
        "always_review": True,
        "field_threshold_overrides": {"total": 0.96},
        "per_document_type_thresholds": {"invoice": 0.88},
        "schema_file": "invoice.yaml",
    }

    assert payload["split"]["configured"] is True
    assert payload["split"]["enabled"] is True
    assert payload["split"]["categories_count"] == 1
    assert payload["split"]["api_key_configured"] is True

    steps = {step["key"]: step for step in payload["pipeline"]}
    assert steps["split"]["params"]["api_key"] == "[REDACTED]"
    assert steps["extract"]["params"]["api_key"] == "[REDACTED]"
    assert steps["extract"]["params"]["headers"]["Authorization"] == "[REDACTED]"
    assert steps["review"]["params"]["schema_file"] == "invoice.yaml"
