"""Isolated real PDF.js rendering and boundary interaction coverage."""

import os
from pathlib import Path
import socket
import sys

import pytest
import yaml

from test.helpers_sqlite import initialize_test_users
from test.helpers_visual import running_visual_server
from test.integration.test_manual_split import manual_case
from test.visual.test_schema_review_visual import _write_config


def test_manual_pdf_vertical_pages_draft_markers_and_mobile(manual_case, tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    config, start, _ = manual_case
    _, result = start(4)
    initialize_test_users(config)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    path = _write_config(tmp_path, port, schemas)
    values = yaml.safe_load(path.read_text())
    values["database"]["path"] = config.get("database.path")
    values["watch_folder"]["processing_dir"] = str(tmp_path)
    path.write_text(yaml.safe_dump(values), encoding="utf-8")
    env = {**os.environ, "CONFIG_PATH": str(path), "DOCFLOW_STARTUP_MODE": "verify"}
    root = Path(__file__).resolve().parents[2]
    with running_visual_server([sys.executable, "-m", "uvicorn", "web.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=root, env=env, host="127.0.0.1", port=port, log_path=tmp_path / "server.log"):
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            requests = []
            page.on("request", lambda request: requests.append(request.url))
            page.goto(f"http://127.0.0.1:{port}/login")
            page.locator("#username").select_option("admin")
            page.locator("#password").fill("AdminPassword1!")
            page.locator("button[type=submit]").click()
            page.wait_for_url("**/app/upload")
            page.goto(f"http://127.0.0.1:{port}/app/review/{result['review_item_id']}")
            page.locator("#split-pdf-status").filter(has_text="All pages").wait_for()
            assert page.locator(".manual-page").count() == 4
            assert page.locator("[data-boundary]").count() == 3
            assert not page.locator("#split-retry").is_visible()
            page.locator("#split-claim").click()
            page.locator('[data-boundary="1"]').check()
            page.locator('[data-boundary="3"]').check()
            assert page.locator(".manual-plan-document").count() == 3
            assert page.locator('[data-jump="3"]').inner_text().startswith("2")
            assert page.locator(".manual-boundary.selected .manual-marker").all_text_contents() == ["1", "2"]
            page.locator("#split-save").click()
            page.locator("#split-status").filter(has_text="Draft saved").wait_for()
            page.reload()
            page.locator("#split-pdf-status").filter(has_text="All pages").wait_for()
            assert page.locator('[data-boundary="1"]').is_checked()
            assert page.locator('[data-boundary="3"]').is_checked()
            page.locator('[data-boundary="3"]').focus()
            page.keyboard.press("Space")
            assert not page.locator('[data-boundary="3"]').is_checked()
            assert page.locator(".manual-plan-document").count() == 2
            page.locator("#split-save").click()
            page.locator("#split-status").filter(has_text="Draft saved").wait_for()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert all(url.startswith(f"http://127.0.0.1:{port}/") for url in requests)

            # A second tab saves while this tab has unsaved boundaries. Renewing
            # the shared user's claim must not upgrade this stale draft revision.
            page.set_viewport_size({"width": 1600, "height": 1000})
            page.locator('[data-boundary="2"]').check()
            from modules.db.connection import connect
            from modules.services.manual_split_service import ManualSplitReviewService
            with connect(config) as conn:
                service = ManualSplitReviewService(conn, config)
                revision = service.detail(result["review_item_id"])["revision"]
                service.save(result["review_item_id"], "admin", {
                    "boundaries": [3], "expected_revision": revision,
                })
            page.locator("#split-claim").click()
            page.locator("#split-status").filter(has_text="changed in another session").wait_for()
            assert page.locator("#split-save").is_disabled()
            assert page.locator("#split-complete").is_disabled()
            assert page.locator('[data-boundary="2"]').is_checked()
            page.locator("#split-claim").click()
            page.locator("#split-status").filter(has_text="changed in another session").wait_for()
            assert page.locator("#split-complete").is_disabled()
            with connect(config) as conn:
                assert ManualSplitReviewService(conn, config).detail(result["review_item_id"])["boundaries"] == [3]

            page.once("dialog", lambda dialog: dialog.accept())
            page.reload()
            page.locator("#split-pdf-status").filter(has_text="All pages").wait_for()

            # Leave the accepted decision pending to represent slow background
            # processing. The UI must acknowledge it without waiting for a flow.
            def accept_without_finishing(route):
                import json
                with connect(config) as conn:
                    accepted = ManualSplitReviewService(conn, config).save(
                        result["review_item_id"], "admin", route.request.post_data_json,
                        complete=True,
                    )
                route.fulfill(status=202, content_type="application/json", body=json.dumps({
                    **accepted, "resume_scheduled": True,
                }))

            page.route("**/split/complete", accept_without_finishing)
            page.locator("#split-complete").click()
            page.locator("#split-status").filter(has_text="continue in the background").wait_for()
            assert page.locator("#split-complete").inner_text() == "Decision saved"
            assert page.locator("#split-complete").is_disabled()
            assert page.locator("#split-progress").is_visible()
            assert page.locator("#split-progress").get_attribute("href").startswith("/app/batches/")
            assert "Applying decision" not in page.locator("#manual-split-workspace").inner_text()
            with connect(config) as conn:
                assert ManualSplitReviewService(conn, config).detail(result["review_item_id"])["phase"] == "pending"
            browser.close()
