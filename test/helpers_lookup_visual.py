"""Isolated production app and Chromium helpers for CSV lookup acceptance."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import sys
from typing import Iterator

from playwright.sync_api import Page, sync_playwright
import yaml

from modules.services.startup_migration_service import initialize_database
from test.helpers_sqlite import TempConfig, initialize_test_users
from test.helpers_visual import running_visual_server


ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = [("desktop", 1366, 768), ("mobile", 390, 844)]
EVIDENCE = ROOT / "output" / "playwright" / "r3-phase5"


def lookup_config(root: Path) -> TempConfig:
    for directory in ("uploads", "watch", "schemas", "processing"):
        (root / directory).mkdir()
    (root / "app.log").touch()
    values = {
        "database": {"path": str(root / "state.sqlite3")},
        "auth": {"roles_enabled": True, "default_admin_users": ["admin"]},
        "web": {"upload_dir": str(root / "uploads"), "secret_key": "synthetic-r3-test"},
        "watch_folder": {"dir": str(root / "watch"), "processing_dir": str(root / "processing")},
        "schema": {"directories": [str(root / "schemas")]},
        "logging": {"log_file": str(root / "app.log")},
        "pipeline_secrets": {"extract": "synthetic-unused-value"},
        "ui": {"admin_enabled": True}, "pipeline": [], "tasks": {},
    }
    (root / "config.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")
    config = TempConfig(root / "state.sqlite3", values)
    initialize_database(config)
    initialize_test_users(config)
    return config


@contextmanager
def lookup_browser(root: Path, width: int, height: int, *, admin: bool) -> Iterator[tuple[Page, str]]:
    """Open the authenticated UI against a temporary SQLite deployment."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(CONFIG_PATH=str(root / "config.yaml"), APP_ENV="development", ENV="development",
               ENVIRONMENT="development", DOCFLOW_STDIO_CAPTURED="1", PREFECT_LOGGING_TO_API_ENABLED="false")
    server = ("from test.helpers_business_validation_workflow import offline_invoice_workflows\n"
              "import uvicorn\nwith offline_invoice_workflows():\n"
              f"    uvicorn.run('web.server:app', host='127.0.0.1', port={port}, log_level='warning')\n")
    base = f"http://127.0.0.1:{port}"
    with running_visual_server([sys.executable, "-c", server], cwd=ROOT, env=env, host="127.0.0.1",
                               port=port, log_path=root / "server.log"), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            login_lookup(page, base, admin=admin)
            yield page, base
            assert not errors
        finally:
            browser.close()


def login_lookup(page: Page, base: str, *, admin: bool) -> None:
    """Log in as the selected synthetic account through the real form."""
    page.goto(base + "/login")
    page.locator('select[name="username"]').select_option("admin" if admin else "operator")
    page.locator('input[name="password"]').fill("AdminPassword1!" if admin else "OperatorPass1!")
    page.get_by_role("button", name="Login", exact=True).click()
    page.wait_for_url("**/app/upload")


def capture_lookup(page: Page, name: str, *, directory: Path = EVIDENCE) -> None:
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    directory.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(directory / f"{name}.png"))
