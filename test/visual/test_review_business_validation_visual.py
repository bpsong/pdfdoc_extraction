"""Phase 3 smoke of the existing review screen with runtime business enforcement."""

import os
from pathlib import Path
import socket
import sys

from playwright.sync_api import expect, sync_playwright
import yaml

from modules.services.startup_migration_service import initialize_database
from test.helpers_business_validation import seed_business_review
from test.helpers_sqlite import TempConfig, initialize_test_users
from test.helpers_visual import running_visual_server


def test_review_claim_save_reload_block_correct_complete_and_mobile(tmp_path):
    for folder in ("uploads", "watch", "schemas", "processing"):
        (tmp_path / folder).mkdir()
    (tmp_path / "app.log").touch()
    values = {
        "database": {"path": str(tmp_path / "state.sqlite3")},
        "web": {"upload_dir": str(tmp_path / "uploads"), "secret_key": "synthetic-r4-browser-key"},
        "watch_folder": {"dir": str(tmp_path / "watch"), "processing_dir": str(tmp_path / "processing")},
        "schema": {"directories": [str(tmp_path / "schemas")]},
        "logging": {"log_file": str(tmp_path / "app.log")},
        "ui": {"admin_enabled": True}, "pipeline": [], "tasks": {},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(values), encoding="utf-8")
    config = TempConfig(tmp_path / "state.sqlite3", values)
    initialize_database(config)
    initialize_test_users(config)
    seeded = seed_business_review(config, tmp_path / "uploads")
    seeded["task"].run(seeded["context"])
    review_id = seeded["context"]["review_item_id"]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(CONFIG_PATH=str(config_path), APP_ENV="development", ENV="development",
               ENVIRONMENT="development", DOCFLOW_STDIO_CAPTURED="1", PREFECT_LOGGING_TO_API_ENABLED="false")
    root = Path(__file__).resolve().parents[2]
    evidence = Path(os.environ.get("R4_VISUAL_EVIDENCE_DIR", str(tmp_path / "evidence")))
    evidence.mkdir(parents=True, exist_ok=True)
    # Resume's commit boundary is covered by service tests. Keep this UI smoke
    # isolated from Prefect's ephemeral orchestration server and provider calls.
    server = (
        "from modules.resume_manager import ResumeManager; "
        "ResumeManager.resume_document = lambda *args, **kwargs: False; "
        "import uvicorn; "
        f"uvicorn.run('web.server:app', host='127.0.0.1', port={port}, log_level='warning')"
    )
    with running_visual_server(
        [sys.executable, "-c", server],
        cwd=root, env=env, host="127.0.0.1", port=port, log_path=tmp_path / "server.log",
    ), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            base = f"http://127.0.0.1:{port}"
            page.goto(base + "/login")
            page.locator('input[name="password"]').fill("AdminPassword1!")
            page.get_by_role("button", name="Login", exact=True).click()
            page.wait_for_url("**/app/upload")
            page.goto(f"{base}/app/review/{review_id}")
            subtotal = page.locator('input[data-field-path="subtotal"]')
            expect(subtotal).to_have_value("30")
            expect(subtotal).to_be_disabled()
            page.locator("#review-claim-button").click()
            expect(subtotal).to_be_enabled()
            with page.expect_response(lambda r: r.url.endswith("/complete") and r.request.method == "POST") as blocked:
                page.locator("#review-complete-button").click()
            assert blocked.value.status == 422
            assert blocked.value.json()["detail"]["code"] == "business_validation_blocked"
            expect(subtotal).to_have_value("30")
            page.screenshot(path=str(evidence / "review-desktop.png"))
            # Make subtotal consistent but retain the nonblocking line warning.
            subtotal.fill("300")
            with page.expect_response(lambda r: r.url.endswith("/draft") and r.request.method == "POST") as saved:
                page.locator("#review-save-button").click()
            assert saved.value.status == 200
            assert not saved.value.json()["business_validation"]["has_blocking_findings"]
            page.reload()
            expect(subtotal).to_have_value("300")
            page.locator("#review-release-button").click()
            expect(subtotal).to_be_disabled()
            page.locator("#review-claim-button").click()
            expect(subtotal).to_be_enabled()
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(evidence / "review-mobile.png"))
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            subtotal.scroll_into_view_if_needed()
            page.screenshot(path=str(evidence / "review-mobile-form.png"))
            page.locator("#review-complete-button").click()
            page.wait_for_url("**/app/review")
            accepted = page.request.get(f"{base}/api/review/items/{review_id}").json()
            assert accepted["review_item"]["status"] == "completed"
            assert [check["status"] for check in accepted["business_validation"]["checks"]] == ["failed", "passed"]
            assert not errors
        finally:
            browser.close()
