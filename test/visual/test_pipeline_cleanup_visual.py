"""Real-browser lifecycle flows against isolated synthetic SQLite histories."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Iterator

import pytest
from playwright.sync_api import Page, Route, expect, sync_playwright

from modules.db.connection import connect
from modules.services.ingress_binding_service import IngressBindingService
from modules.services.pipeline_template_service import PipelineTemplateService
from test.helpers_cleanup import CUTOFF, seed_history
from test.helpers_sqlite import TempConfig
from test.visual.test_schema_review_visual import visual_app

EVIDENCE = Path(__file__).resolve().parents[2] / "output/playwright/pipeline-cleanup"


def _screenshot(page: Page, name: str) -> None:
    """Capture the settled dialog rather than its opening transition."""
    page.locator("#pipeline-lifecycle-dialog").evaluate("node => Promise.all(node.getAnimations({subtree: true}).map(animation => animation.finished.catch(() => {})))")
    page.screenshot(path=str(EVIDENCE / name))


@pytest.fixture
def page(visual_app: dict[str, str]) -> Iterator[Page]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1366, "height": 950})
        current = context.new_page()
        errors: list[str] = []
        current.on("pageerror", lambda error: errors.append(str(error)))
        current.route("**/favicon.ico", lambda route: route.fulfill(status=204))
        current.goto(f"{visual_app['base_url']}/login")
        current.locator('select[name="username"]').select_option("admin")
        current.locator('input[name="password"]').fill("password123")
        current.locator('button[type="submit"]').click()
        current.wait_for_url("**/app/upload")
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        try:
            yield current
            assert not errors
        finally:
            context.close()
            browser.close()


def _setup(visual_app: dict[str, str], *, enabled_binding: bool = False) -> dict[str, Any]:
    db = Path(visual_app["db_path"])
    config = TempConfig(db, {"pipeline_secrets": {"phase14-provider": "synthetic"}})
    with connect(config) as conn:
        service = PipelineTemplateService(conn, configured_secret_aliases={"phase14-provider"})
        created = service.clone(visual_app["active_template_id"], template_key=f"cleanup-{uuid.uuid4().hex}", name="Cleanup visual pipeline", user="admin")
        template_id = created["template"]["id"]
        version = service.publish(template_id, expected_revision=1, user="admin")["version"]
        service.update_template(template_id, status="active", user="admin")
        binding_id = None
        if enabled_binding:
            folder = db.parent / f"cleanup-watch-{uuid.uuid4().hex}"
            folder.mkdir()
            binding = IngressBindingService(conn, config).create(folder_path=str(folder), pipeline_version_id=version["id"], enabled=True, user="admin")
            binding_id = binding["id"]
        completed = seed_history(conn, db.parent, template_id, version["id"], child=True)
        protected = seed_history(conn, db.parent, template_id, version["id"])
        conn.execute("UPDATE review_items SET status='pending' WHERE id=?", (protected["review"],))
        conn.commit()
        return {"template_id": template_id, "version_id": version["id"], "completed": completed, "protected": protected, "binding_id": binding_id, "config": config}


def _open(page: Page, visual_app: dict[str, str], data: dict[str, Any]) -> None:
    page.goto(f"{visual_app['base_url']}/app/admin/pipeline")
    page.locator("#pipeline-template-select").select_option(data["template_id"])
    expect(page.locator("#pipeline-template-name")).to_have_value("Cleanup visual pipeline")
    expect(page.locator("#pipeline-cleanup-button")).to_be_enabled()


def _preview(page: Page) -> None:
    page.locator("#pipeline-cleanup-button").click()
    page.locator("#pipeline-cleanup-cutoff").fill(CUTOFF)
    page.locator("#pipeline-lifecycle-next").click()
    expect(page.locator("#pipeline-lifecycle-title")).to_contain_text("Confirm cleanup")


def test_archive_blockers_visibility_and_cleanup_desktop(page: Page, visual_app: dict[str, str]) -> None:
    data = _setup(visual_app, enabled_binding=True)
    _open(page, visual_app, data)
    page.locator("#pipeline-archive-button").click()
    expect(page.locator("#pipeline-lifecycle-body")).to_contain_text("Set this pipeline to inactive")
    expect(page.locator("#pipeline-lifecycle-body")).to_contain_text("Pause, reassign")
    expect(page.locator("#pipeline-lifecycle-next")).to_be_disabled()
    _screenshot(page, "archive-blocked-desktop.png")
    page.keyboard.press("Escape")
    expect(page.locator("#pipeline-archive-button")).to_be_focused()
    with connect(data["config"]) as conn:
        IngressBindingService(conn, data["config"]).update(data["binding_id"], action="pause", user="admin")
    page.locator("#pipeline-template-status").select_option("inactive")
    expect(page.locator("#pipeline-template-select option:checked")).to_contain_text("inactive")
    page.locator("#pipeline-archive-button").click()
    expect(page.locator("#pipeline-lifecycle-next")).to_be_enabled()
    expect(page.locator("#pipeline-lifecycle-body")).to_contain_text("Paused")
    page.locator("#pipeline-lifecycle-next").click()
    expect(page.locator("#pipeline-template-status")).to_have_value("archived")
    expect(page.locator("#pipeline-template-status")).to_be_disabled()
    expect(page.locator("#pipeline-show-archived")).to_be_checked()
    _preview(page)
    expect(page.locator("#pipeline-lifecycle-body")).to_contain_text("Pending review or review lock: 1 batches / 1 documents")
    expect(page.locator("#pipeline-lifecycle-next")).to_be_disabled()
    page.locator("#pipeline-cleanup-name").fill("wrong")
    expect(page.locator("#pipeline-lifecycle-next")).to_be_disabled()
    _screenshot(page, "cleanup-preview-desktop.png")
    page.locator("#pipeline-cleanup-name").fill("Cleanup visual pipeline")
    page.locator("#pipeline-lifecycle-next").click()
    expect(page.locator("#pipeline-lifecycle-title")).to_have_text("Processing data cleaned up")
    expect(page.locator("#pipeline-lifecycle-next")).to_be_hidden()
    _screenshot(page, "cleanup-result-desktop.png")
    with connect(data["config"]) as conn:
        assert not conn.execute("SELECT 1 FROM batches WHERE id=?", (data["completed"]["batch_id"],)).fetchone()
        assert conn.execute("SELECT 1 FROM batches WHERE id=?", (data["protected"]["batch_id"],)).fetchone()
        assert conn.execute("SELECT 1 FROM audit_events WHERE id=?", (data["completed"]["audit"],)).fetchone()
    assert data["completed"]["file_path"].exists()
    page.locator("#pipeline-lifecycle-close").click()
    _preview(page)
    page.locator("#pipeline-cleanup-name").fill("Cleanup visual pipeline")
    expect(page.locator("#pipeline-lifecycle-next")).to_be_disabled()
    page.keyboard.press("Escape")
    page.locator("#pipeline-show-archived").uncheck()
    expect(page.locator(f"#pipeline-template-select option[value='{data['template_id']}']")).to_have_count(0)
    page.locator("#pipeline-show-archived").check()
    expect(page.locator(f"#pipeline-template-select option[value='{data['template_id']}']")).to_have_count(1)


def test_cleanup_stale_preview_cancel_and_mobile_layout(page: Page, visual_app: dict[str, str]) -> None:
    data = _setup(visual_app)
    page.set_viewport_size({"width": 390, "height": 844})
    _open(page, visual_app, data)
    _preview(page)
    page.locator("#pipeline-lifecycle-close").click()
    expect(page.locator("#pipeline-cleanup-cutoff")).to_be_visible()
    page.keyboard.press("Escape")
    _preview(page)
    _screenshot(page, "cleanup-preview-mobile.png")
    assert page.locator("#pipeline-lifecycle-dialog .modal-box").evaluate("node => node.scrollWidth <= node.clientWidth")
    with connect(data["config"]) as conn:
        conn.execute("UPDATE processing_jobs SET status='running' WHERE id=?", (data["completed"]["job"],))
    page.locator("#pipeline-cleanup-name").fill("Cleanup visual pipeline")
    page.locator("#pipeline-lifecycle-next").scroll_into_view_if_needed()
    _screenshot(page, "cleanup-confirmation-mobile.png")
    page.locator("#pipeline-lifecycle-next").click()
    expect(page.locator("#pipeline-lifecycle-error")).to_contain_text("Processing data changed")
    expect(page.locator("#pipeline-cleanup-cutoff")).to_be_visible()
    with connect(data["config"]) as conn:
        assert conn.execute("SELECT 1 FROM batches WHERE id=?", (data["completed"]["batch_id"],)).fetchone()


def test_lifecycle_cookie_requests_require_csrf(page: Page, visual_app: dict[str, str]) -> None:
    template = visual_app["active_template_id"]
    for action in ("archive", "cleanup-preview", "cleanup"):
        response = page.request.post(f"{visual_app['base_url']}/api/admin/pipeline-templates/{template}/{action}", data={"cutoff_date": CUTOFF})
        assert response.status == 403


def test_cleaned_upload_receipt_clears_retry_identity_without_resubmission(page: Page, visual_app: dict[str, str]) -> None:
    data = _setup(visual_app)
    with connect(data["config"]) as conn:
        conn.execute("UPDATE upload_submissions SET response_json='{\"purged\":true}' WHERE submission_id=?", (data["completed"]["receipt"],))
    page.evaluate("""id => {
        sessionStorage.setItem('docflow-upload-receipt', JSON.stringify({id, signature: 'old-signature'}));
        sessionStorage.setItem('docflow-upload-identities', JSON.stringify({'old-signature': id}));
    }""", data["completed"]["receipt"])
    submissions: list[str] = []
    page.on("request", lambda request: submissions.append(request.url) if request.method == "POST" and "/batches/upload" in request.url else None)
    page.goto(f"{visual_app['base_url']}/app/upload")
    expect(page.locator("#upload-status")).to_contain_text("Previous upload history was cleaned up")
    assert page.evaluate("sessionStorage.getItem('docflow-upload-receipt')") is None
    assert page.evaluate("JSON.parse(sessionStorage.getItem('docflow-upload-identities'))") == {}
    assert submissions == []


def test_archive_is_confirmed_through_dialog_and_loads_other_archived_choices(page: Page, visual_app: dict[str, str]) -> None:
    data = _setup(visual_app)
    with connect(data["config"]) as conn:
        PipelineTemplateService(conn).update_template(data["template_id"], status="inactive", user="admin")
    _open(page, visual_app, data)
    expect(page.locator('#pipeline-template-status option[value="archived"]')).to_have_js_property("disabled", True)
    all_templates = page.request.get(f"{visual_app['base_url']}/api/admin/pipeline-templates?include_archived=true").json()["templates"]
    archived_ids = [item["id"] for item in all_templates if item["status"] == "archived"]
    assert archived_ids
    page.locator("#pipeline-archive-button").click()
    expect(page.locator("#pipeline-lifecycle-next")).to_be_enabled()
    page.locator("#pipeline-lifecycle-next").click()
    expect(page.locator("#pipeline-lifecycle-dialog")).to_have_js_property("open", False)
    expect(page.locator("#pipeline-show-archived")).to_be_checked()
    for template_id in archived_ids:
        expect(page.locator(f"#pipeline-template-select option[value='{template_id}']")).to_have_count(1)


def test_archived_editor_disables_reset_and_other_mutations(page: Page, visual_app: dict[str, str]) -> None:
    data = _setup(visual_app)
    with connect(data["config"]) as conn:
        service = PipelineTemplateService(conn)
        service.update_template(data["template_id"], status="inactive", user="admin")
        service.update_template(data["template_id"], status="archived", user="admin")
    page.goto(f"{visual_app['base_url']}/app/admin/pipeline")
    page.locator("#pipeline-show-archived").check()
    page.locator("#pipeline-template-select").select_option(data["template_id"])
    expect(page.locator("#pipeline-template-status")).to_have_value("archived")
    for element in ("reset", "save-draft", "validate", "publish", "import", "add-task"):
        expect(page.locator(f"#pipeline-{element}-button")).to_be_disabled()
    expect(page.locator("#pipeline-template-clone")).to_be_enabled()
    expect(page.locator("#pipeline-cleanup-button")).to_be_enabled()


def test_completed_archive_is_successful_when_list_refresh_fails(page: Page, visual_app: dict[str, str]) -> None:
    data = _setup(visual_app)
    with connect(data["config"]) as conn:
        PipelineTemplateService(conn).update_template(data["template_id"], status="inactive", user="admin")
    _open(page, visual_app, data)
    page.locator("#pipeline-archive-button").click()
    expect(page.locator("#pipeline-lifecycle-next")).to_be_enabled()
    page.route("**/api/admin/pipeline-templates?include_archived=true", lambda route: route.abort())
    page.evaluate("""() => {
        window.archiveToasts = [];
        window.DocFlow.showToast = (message, kind) => window.archiveToasts.push([message, kind]);
    }""")
    page.locator("#pipeline-lifecycle-next").click()
    expect(page.locator("#pipeline-lifecycle-dialog")).to_have_js_property("open", False)
    expect(page.locator("#pipeline-template-status")).to_have_value("archived")
    expect(page.locator("#pipeline-reset-button")).to_be_disabled()
    toasts = page.evaluate("window.archiveToasts")
    assert any(kind == "success" for _, kind in toasts)
    assert any("list could not refresh" in message and kind == "warning" for message, kind in toasts)
    assert not any(kind == "error" for _, kind in toasts)


def test_delayed_template_response_cannot_replace_a_newer_selection(page: Page, visual_app: dict[str, str]) -> None:
    first, second = _setup(visual_app), _setup(visual_app)
    with connect(second["config"]) as conn:
        PipelineTemplateService(conn).update_template(second["template_id"], name="Second visual pipeline", user="admin")
    _open(page, visual_app, first)
    first_url = f"{visual_app['base_url']}/api/admin/pipeline-templates/{first['template_id']}"
    first_payload = page.request.get(first_url).json()
    page.locator("#pipeline-template-select").select_option(second["template_id"])
    expect(page.locator("#pipeline-template-name")).to_have_value("Second visual pipeline")
    held: list[Route] = []
    page.route(first_url, lambda route: held.append(route))
    with page.expect_request(first_url):
        page.locator("#pipeline-template-select").select_option(first["template_id"])
    # A second selection finishes while the previous template request is delayed.
    page.locator("#pipeline-template-select").select_option(second["template_id"])
    expect(page.locator("#pipeline-cleanup-button")).to_be_enabled()
    assert held
    held[0].fulfill(json=first_payload)
    page.wait_for_load_state("networkidle")
    expect(page.locator("#pipeline-template-name")).to_have_value("Second visual pipeline")
    page.locator("#pipeline-cleanup-button").click()
    expect(page.locator("#pipeline-lifecycle-title")).to_have_text("Clean up processing data · Second visual pipeline")
