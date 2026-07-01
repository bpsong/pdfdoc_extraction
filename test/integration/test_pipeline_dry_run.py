from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.migrations import initialize_database
from test.helpers_sqlite import TempConfig, initialize_test_users


def _base_config(tmp_path: Path) -> dict[str, Any]:
    export_dir = tmp_path / "exports"
    split_dir = tmp_path / "split"
    export_dir.mkdir(exist_ok=True)
    split_dir.mkdir(exist_ok=True)
    return {
        "auth": {"roles_enabled": True, "default_admin_users": ["admin"]},
        "authentication": {"username": "admin"},
        "ui": {"app_name": "DocFlow AI", "page_size": 25},
        "validation": {
            "config_validation_enabled": True,
            "allow_ui_config_save": False,
            "strict_mode_default": False,
        },
        "review": {"lock_timeout_minutes": 60, "default_queue_name": "default_review"},
        "tasks": {
            "split": {
                "module": "standard_step.split.llamacloud_split",
                "class": "LlamaCloudSplitTask",
                "params": {
                    "enabled": True,
                    "adapter": "mock",
                    "categories": [{"name": "invoice"}],
                    "split_dir": str(split_dir),
                },
            },
            "extract": {
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
                "params": {"fields": {"supplier": {"alias": "Supplier", "type": "str"}}},
            },
            "review": {
                "module": "standard_step.review.review_gate",
                "class": "ReviewGateTask",
                "params": {"confidence_threshold": 0.9},
            },
            "store_json": {
                "module": "standard_step.storage.store_metadata_as_json",
                "class": "StoreMetadataAsJson",
                "params": {"data_dir": str(export_dir), "filename": "{supplier}"},
            },
        },
        "pipeline": ["split", "extract", "review", "store_json"],
    }


def _config(tmp_path: Path) -> TempConfig:
    config = TempConfig(tmp_path / "app.sqlite3", _base_config(tmp_path))
    config._config_path.write_text(yaml.safe_dump(config.get_all(), sort_keys=False), encoding="utf-8")
    initialize_database(config)
    initialize_test_users(config)
    return config


def _client(monkeypatch, config: TempConfig, *, username: str = "admin") -> TestClient:
    app = FastAPI()
    app.include_router(api_router.build_router())

    def fake_get_dependencies():
        return config, None, None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app.dependency_overrides[api_router.get_current_user] = lambda: username
    return TestClient(app)


def test_admin_summary_and_settings_api(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = _client(monkeypatch, config)

    summary = client.get("/api/admin/summary")
    assert summary.status_code == 200
    assert summary.json()["pipeline"]["active"]["enabled_steps"] == 4

    settings = client.put(
        "/api/admin/settings",
        json={"settings": {"ui.page_size": 40, "review.default_queue_name": "priority"}},
    )
    assert settings.status_code == 200
    assert settings.json()["settings"]["ui.page_size"] == 40
