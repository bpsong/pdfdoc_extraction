"""Real-browser rule authoring against an isolated production app instance."""

from contextlib import closing
import os
from pathlib import Path
import socket
import sys
from typing import Any, Iterator

import pytest
from playwright.sync_api import expect, sync_playwright
import yaml

from modules.db.connection import connect
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.startup_migration_service import initialize_database
from test.helpers_business_validation import invoice_review_schema
from test.helpers_sqlite import TempConfig, initialize_test_users
from test.helpers_visual import add_business_rule, running_visual_server


@pytest.fixture
def rules_app(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[dict[str, Any]]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
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
    schema = invoice_review_schema()
    del schema["business_validation"]
    alias = getattr(request, 'param', None)
    if alias:
        schema['fields']['approval'] = {'type': 'enum', 'label': 'Approval', alias: [{'label': 'Approved'}]}
    with closing(connect(config)) as conn:
        template = ReviewSchemaVersionService(conn).create_template(
            schema_key="invoice-validation", name=schema["title"],
            initial_schema=schema, user="admin",
        )["template"]
    env = os.environ.copy()
    env.update(CONFIG_PATH=str(config_path), APP_ENV="development", ENV="development",
               ENVIRONMENT="development", DOCFLOW_STDIO_CAPTURED="1",
               PREFECT_LOGGING_TO_API_ENABLED="false")
    root = Path(__file__).resolve().parents[2]
    with running_visual_server(
        [sys.executable, "-m", "uvicorn", "web.server:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=root, env=env, host="127.0.0.1", port=port,
        log_path=tmp_path / "server.log",
    ):
        yield {"url": f"http://127.0.0.1:{port}", "template_id": template["id"]}


@pytest.mark.parametrize('rules_app', ['choices', 'enum'], indirect=True)
def test_conditional_enum_choice_feedback_and_publication(
    rules_app: dict[str, Any], tmp_path: Path,
) -> None:
    evidence = Path(os.environ.get('R4_AUDIT_EVIDENCE_DIR', str(tmp_path / 'evidence')))
    evidence.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors: list[str] = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: dialog.accept())
            page.goto(rules_app['url'] + '/login')
            page.locator('input[name="password"]').fill('AdminPassword1!')
            page.get_by_role('button', name='Login', exact=True).click()
            page.wait_for_url('**/app/upload')
            page.goto(rules_app['url'] + '/app/schemas')
            add_business_rule(page, 'required_if:v1')
            page.get_by_label('Rule 1: Condition field', exact=True).select_option('/approval')
            page.get_by_label('Rule 1: Required fields', exact=True).select_option(['/subtotal'])
            equals = page.get_by_label('Rule 1: Equals value', exact=True)
            equals.fill('Rejected')
            expect(equals).to_have_attribute('aria-invalid', 'true')
            expect(page.get_by_role('button', name='Save draft', exact=True)).to_be_disabled()
            page.get_by_role('button', name='Publish', exact=True).click()
            expect(page.locator('#schema-version-history')).to_contain_text('No published versions')
            equals.fill('Approved')
            expect(equals).not_to_have_attribute('aria-invalid', 'true')
            with page.expect_response(lambda response: response.url.endswith('/publish')) as published:
                page.get_by_role('button', name='Publish', exact=True).click()
            assert published.value.status == 200
            page.reload()
            expect(equals).to_have_value('Approved')
            expect(page.locator('#schema-version-history')).to_contain_text('Version 1')
            page.locator('#schema-business-title').scroll_into_view_if_needed()
            page.screenshot(path=str(evidence / f"enum-conditional-{tmp_path.name}-desktop.png"))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('.business-rule-card').scroll_into_view_if_needed()
            page.screenshot(path=str(evidence / f"enum-conditional-{tmp_path.name}-mobile.png"))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            assert not errors
        finally:
            browser.close()


def test_author_repair_publish_reload_and_mobile_rules(
    rules_app: dict[str, Any], tmp_path: Path,
) -> None:
    evidence = Path(os.environ.get("R4_VISUAL_EVIDENCE_DIR", str(tmp_path / "evidence")))
    evidence.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(f"{rules_app['url']}/login")
            page.locator('input[name="password"]').fill("AdminPassword1!")
            page.get_by_role("button", name="Login", exact=True).click()
            page.wait_for_url("**/app/upload")
            page.goto(f"{rules_app['url']}/app/schemas")
            add_business_rule(page, 'line_amount:v1')
            page.get_by_label('Rule 1: Repeating group', exact=True).select_option('/items')
            for label, field in (("First value field", "/quantity"), ("Second value field", "/unit_price"),
                                 ("Result field", "/line_total")):
                page.get_by_label(f"Rule 1: {label}", exact=True).select_option(field)
            add_business_rule(page, 'sum_equals:v1')
            page.get_by_label('Rule 2: Repeating group', exact=True).select_option('/items')
            page.get_by_label("Rule 2: Value to sum", exact=True).select_option("/line_total")
            page.get_by_label("Rule 2: Target field", exact=True).select_option("/subtotal")
            page.get_by_label("Rule 2: Severity", exact=True).select_option("blocking")
            page.get_by_role("button", name="Move rule 2 up", exact=True).click()
            page.get_by_label("Rule 2: Enabled", exact=True).uncheck()
            tolerance = page.get_by_label("Rule 1: Allowed difference", exact=True)
            tolerance.fill("-1")
            expect(tolerance).to_have_attribute("aria-invalid", "true")
            expect(page.get_by_role("button", name="Save draft", exact=True)).to_be_disabled()
            # Publish must not silently publish the older saved draft when local edits are invalid.
            page.get_by_role("button", name="Publish", exact=True).click()
            expect(page.locator("#schema-version-history")).to_contain_text("No published versions")
            tolerance.fill("0.02")
            page.locator("#schema-business-title").scroll_into_view_if_needed()
            page.screenshot(path=str(evidence / "desktop.png"))

            with page.expect_response(lambda response: response.url.endswith("/draft")
                                      and response.request.method == "PUT") as saved:
                page.get_by_role("button", name="Save draft", exact=True).click()
            assert saved.value.status == 200
            expect(page.locator("#schema-draft-revision")).to_have_text("Draft revision 2")
            with page.expect_response(lambda response: response.url.endswith("/publish")) as published:
                page.get_by_role("button", name="Publish", exact=True).click()
            assert published.value.status == 200
            expect(page.locator("#schema-version-history")).to_contain_text("Version 1")
            page.reload()
            expect(tolerance).to_have_value("0.02")
            expect(page.get_by_label("Rule 2: Enabled", exact=True)).not_to_be_checked()
            api_url = f"{rules_app['url']}/api/admin/review-schemas/{rules_app['template_id']}"
            original = page.request.get(api_url).json()
            assert [rule["validator"] for rule in original["draft"]["schema"]["business_validation"]["rules"]] == ["sum_equals:v1", "line_amount:v1"]

            # The backend's bounded decimal format is stricter than a finite JS number.
            tolerance.fill("1e100")
            with page.expect_response(lambda response: response.url.endswith("/publish")) as rejected:
                page.get_by_role("button", name="Publish", exact=True).click()
            assert rejected.value.status == 422
            expect(tolerance).to_have_attribute("aria-invalid", "true")
            expect(page.locator("#schema-error")).to_contain_text("Publication blocked")
            tolerance.fill("0.02")

            # Rename a bound field and restore it without rewriting rule references.
            key = page.locator('[data-field-path="items.quantity"][data-field-prop="key"]')
            key.evaluate("element => { for (let node=element.parentElement; node; node=node.parentElement) if(node.tagName==='DETAILS') node.open=true; }")
            key.fill("qty")
            key.press("Tab")
            expect(page.get_by_label("Rule 2: First value field", exact=True)).to_have_attribute("aria-invalid", "true")
            renamed = page.locator('[data-field-path="items.qty"][data-field-prop="key"]')
            renamed.evaluate("element => { for (let node=element.parentElement; node; node=node.parentElement) if(node.tagName==='DETAILS') node.open=true; }")
            renamed.fill("quantity")
            renamed.press("Tab")
            expect(page.get_by_label("Rule 2: First value field", exact=True)).not_to_have_attribute("aria-invalid", "true")
            add_business_rule(page, 'sum_equals:v1')
            page.get_by_role("button", name="Delete rule 3", exact=True).click()
            expect(page.locator(".business-rule-card")).to_have_count(2)

            page.set_viewport_size({"width": 390, "height": 844})
            expect(page.get_by_text("Review form draft saved", exact=True)).to_have_count(0)
            page.locator("#schema-business-title").scroll_into_view_if_needed()
            page.screenshot(path=str(evidence / "mobile.png"))
            page.locator(".business-rule-card").first.evaluate("element => element.scrollIntoView({block:'start'})")
            page.screenshot(path=str(evidence / "mobile-rule.png"))
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            # Persist after unrelated field edits, and verify exact rule values survive.
            with page.expect_response(lambda response: response.url.endswith("/draft")
                                      and response.request.method == "PUT"):
                page.get_by_role("button", name="Save draft", exact=True).click()
            current = page.request.get(api_url).json()
            assert current["draft"]["schema"]["business_validation"] == original["draft"]["schema"]["business_validation"]
            assert not errors
        finally:
            browser.close()
