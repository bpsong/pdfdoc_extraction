"""Browser regressions for pipeline metadata saves and unsaved draft edits."""

from __future__ import annotations

from typing import Iterator

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from test.visual.test_schema_review_visual import visual_app


@pytest.fixture()
def page(visual_app: dict[str, str]) -> Iterator[Page]:
    """Log in to the isolated app and report browser script/resource errors."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        browser_page = context.new_page()
        errors: list[str] = []
        browser_page.on("pageerror", lambda error: errors.append(str(error)))
        browser_page.on("response", lambda response: errors.append(
            f"{response.status}: {response.url}"
        ) if response.status >= 400 else None)
        browser_page.route("**/favicon.ico", lambda route: route.fulfill(status=204))
        browser_page.goto(f"{visual_app['base_url']}/login")
        browser_page.locator('select[name="username"]').select_option("admin")
        browser_page.locator('input[name="password"]').fill("password123")
        browser_page.locator('button[type="submit"]').click()
        browser_page.wait_for_url("**/app/upload")
        try:
            yield browser_page
            assert not errors
        finally:
            context.close()
            browser.close()


def _open_pipeline(page: Page, visual_app: dict[str, str]) -> str:
    """Select the synthetic published pipeline and wait for its editor."""
    template_id = visual_app["active_template_id"]
    page.goto(f"{visual_app['base_url']}/app/admin/pipeline")
    page.locator("#pipeline-template-select").select_option(template_id)
    expect(page.locator("#pipeline-template-status")).to_have_value("active")
    expect(page.locator("#pipeline-watch-summary")).to_contain_text("watch folders use")
    expect(page.locator("#pipeline-editor-body [data-step-field='label']")).to_be_visible()
    return template_id


def test_pipeline_rename_preserves_unsaved_draft_and_selected_step(
    page: Page, visual_app: dict[str, str],
) -> None:
    template_id = _open_pipeline(page, visual_app)
    page.locator("[data-select-step='1']").click()
    label = page.locator("#pipeline-editor-body [data-step-field='label']")
    label.fill("Unsaved extraction label")
    label.press("Tab")
    expect(page.locator("#pipeline-publish-help")).to_contain_text("Save Draft")
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))

    with page.expect_response(
        lambda response: response.request.method == "PATCH"
        and response.url.endswith(f"/pipeline-templates/{template_id}")
    ) as saved:
        page.locator("#pipeline-template-name").fill("Renamed synthetic pipeline")
        page.locator("#pipeline-template-name").press("Tab")

    assert saved.value.status == 200
    expect(page.locator("#pipeline-template-select option:checked")).to_contain_text(
        "Renamed synthetic pipeline"
    )
    expect(label).to_have_value("Unsaved extraction label")
    expect(page.locator("#pipeline-publish-help")).to_contain_text("Save Draft")
    assert not any(
        "/task-catalog" in url or "/watch-folder-bindings" in url
        for url in requests
    )
    persisted = page.request.get(
        f"{visual_app['base_url']}/api/admin/pipeline-templates/{template_id}"
    ).json()
    assert persisted["template"]["name"] == "Renamed synthetic pipeline"
    saved_tasks = persisted["draft"]["definition"]["tasks"]
    assert saved_tasks["extract_invoice_fields"]["label"] != "Unsaved extraction label"
    page.once("dialog", lambda dialog: dialog.accept())
    page.reload()
    page.locator("#pipeline-template-select").select_option(template_id)
    expect(page.locator("#pipeline-template-name")).to_have_value(
        "Renamed synthetic pipeline"
    )


def test_pipeline_metadata_save_does_not_depend_on_editor_reload(
    page: Page, visual_app: dict[str, str],
) -> None:
    template_id = _open_pipeline(page, visual_app)
    # The initial editor loaded successfully; later auxiliary reads are unavailable.
    page.route("**/api/admin/task-catalog", lambda route: route.abort())
    page.route("**/api/admin/watch-folder-bindings", lambda route: route.abort())
    page.evaluate("""() => {
        window.metadataToasts = [];
        window.DocFlow.showToast = (message, kind) => window.metadataToasts.push([message, kind]);
    }""")

    with page.expect_response(
        lambda response: response.request.method == "PATCH"
        and response.url.endswith(f"/pipeline-templates/{template_id}")
    ) as saved:
        page.locator("#pipeline-template-description").fill("Updated synthetic description")
        page.locator("#pipeline-template-description").press("Tab")

    assert saved.value.status == 200
    page.wait_for_function("window.metadataToasts.some(([, kind]) => kind === 'success')")
    expect(page.locator("#pipeline-template-description")).to_have_value(
        "Updated synthetic description"
    )
    expect(page.locator("#pipeline-template-select option:checked")).to_contain_text(
        saved.value.json()["template"]["name"]
    )
    toasts = page.evaluate("window.metadataToasts")
    assert ["Pipeline details saved", "success"] in toasts
    assert not any(kind == "error" for _, kind in toasts)


@pytest.mark.parametrize("reactivate", [False, True])
def test_pipeline_availability_preserves_unsaved_draft(
    page: Page, visual_app: dict[str, str], reactivate: bool,
) -> None:
    """Availability changes retain unsaved edits and the selected task."""
    _open_pipeline(page, visual_app)
    page.locator("[data-select-step='1']").click()
    label = page.locator("#pipeline-editor-body [data-step-field='label']")
    label.fill("Unsaved availability edit")
    label.press("Tab")
    page.locator("#pipeline-template-status").select_option("inactive")
    expect(page.locator("#pipeline-template-activate")).to_be_enabled()
    if reactivate:
        page.locator("#pipeline-template-activate").click()
        expect(page.locator("#pipeline-template-activate")).to_have_text("Active for uploads")
    expect(label).to_have_value("Unsaved availability edit")
    expect(page.locator("#pipeline-publish-help")).to_contain_text("Save Draft")
    page.evaluate("""() => {
        window.availabilityToasts = [];
        window.DocFlow.showToast = (message, kind) => window.availabilityToasts.push([message, kind]);
    }""")
    page.locator("#pipeline-archive-button").click()
    assert ["Save or discard draft changes before archiving this pipeline.", "warning"] in page.evaluate("window.availabilityToasts")
    expect(page.locator("#pipeline-lifecycle-dialog")).to_have_js_property("open", False)
    if not reactivate:
        page.locator("#pipeline-template-activate").click()
        expect(page.locator("#pipeline-template-activate")).to_have_text("Active for uploads")
