"""Browser check for the admin validation page using synthetic secrets."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import bcrypt
import pytest
import yaml

from modules.db.connection import connect
from modules.db.repositories import UserRepository
from modules.services.startup_migration_service import initialize_database
from test.helpers_sqlite import TempConfig


pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


SYNTHETIC_SECRET = "SYNTHETIC_CONFIG_SECRET_MUST_NOT_RENDER"
TEST_PASSWORD = "SyntheticVisualPass27!"
EVIDENCE_PATH = Path(__file__).resolve().parents[2] / "output" / "playwright" / "security_validation.png"


@pytest.fixture()
def validation_server(tmp_path: Path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    config_path = tmp_path / "config.yaml"
    for directory in ("uploads", "watch", "schemas"):
        (tmp_path / directory).mkdir()
    values = {
        "database": {"path": str(tmp_path / "app.sqlite3"), "run_migrations_on_startup": True},
        "web": {
            "host": "127.0.0.1",
            "port": port,
            "secret_key": "synthetic-visual-signing-key",
            "upload_dir": str(tmp_path / "uploads"),
        },
        "watch_folder": {"dir": str(tmp_path / "watch"), "processing_dir": str(tmp_path / "processing")},
        "schema": {"directories": [str(tmp_path / "schemas")]},
        "ui": {"admin_enabled": True},
        "pipeline_secrets": {"provider": SYNTHETIC_SECRET},
        "custom_steps": {
            "enabled": True,
            "registry": {
                "fake_extract": {
                    "module": "custom_step.extraction.fake_extract",
                    "class": "FakeExtractTask",
                }
            },
        },
        "pipeline": ["extract"],
        "tasks": {
            "extract": {
                "module": "custom_step.extraction.fake_extract",
                "class": "FakeExtractTask",
                "params": {
                    "api_key": {"$secret": "provider"},
                    "fields": {"invoice_number": {"type": "str", "alias": "Invoice number"}},
                },
                "on_error": "stop",
            }
        },
    }
    config_path.write_text(yaml.safe_dump(values), encoding="utf-8")
    config = TempConfig(tmp_path / "app.sqlite3", values)
    config._config_path = config_path
    initialize_database(config)
    password_hash = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt(rounds=12)).decode()
    with connect(config) as conn:
        UserRepository(conn).initialize({"admin": password_hash, "operator": password_hash})

    env = os.environ.copy()
    env["CONFIG_PATH"] = str(config_path)
    env["APP_ENV"] = "development"
    env["DOCFLOW_STDIO_CAPTURED"] = "1"
    env["PREFECT_LOGGING_TO_API_ENABLED"] = "false"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web.server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError("Synthetic validation server exited early")
                time.sleep(0.25)
        else:
            raise RuntimeError("Synthetic validation server did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def test_validation_page_and_api_hide_secrets_from_admin_and_operator(validation_server: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for username in ("admin", "operator"):
            context = browser.new_context(viewport={"width": 1366, "height": 900})
            page = context.new_page()
            page.goto(f"{validation_server}/login")
            page.locator('select[name="username"]').select_option(username)
            page.locator('input[name="password"]').fill(TEST_PASSWORD)
            page.locator('button[type="submit"]').click()
            page.wait_for_url("**/app/upload")
            response = page.request.get(f"{validation_server}/api/config/validation")
            if username == "admin":
                assert response.status == 200
                assert SYNTHETIC_SECRET not in response.text()
                page.goto(f"{validation_server}/app/settings/validation")
                page.wait_for_function("document.querySelector('#validation-errors-count')?.textContent === '0'")
                page.locator("#validation-raw-toggle").click()
                assert page.locator("#validation-raw-json").is_visible()
                assert "[REDACTED]" in page.locator("#validation-raw-json").inner_text()
                assert SYNTHETIC_SECRET not in page.locator("body").inner_text()
                EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
                assert len(page.screenshot(path=str(EVIDENCE_PATH), full_page=True)) > 10_000
            else:
                assert response.status == 403
                denied = page.goto(f"{validation_server}/app/settings/validation")
                assert denied is not None and denied.status == 403
            context.close()
        browser.close()
