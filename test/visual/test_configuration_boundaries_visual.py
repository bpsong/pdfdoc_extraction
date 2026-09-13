"""Authenticated browser smoke test against a freshly started synthetic app."""

from pathlib import Path

from playwright.sync_api import Page, expect

from test.visual.test_schema_review_visual import page, visual_app


def test_configuration_pages_share_startup_dependencies(
    page: Page, visual_app: dict[str, str],
) -> None:
    evidence = Path(__file__).resolve().parents[2] / "output/playwright/configuration-boundaries"
    evidence.mkdir(parents=True, exist_ok=True)
    for route, name in (
        ("/app/upload", "upload"),
        ("/app/admin", "admin"),
        ("/app/settings/validation", "validation"),
    ):
        response = page.goto(visual_app["base_url"] + route)
        assert response is not None and response.status == 200
        expect(page.locator("h1")).to_be_visible()
        if name == "upload":
            page.locator("#pipeline-version-list input[name='pipeline-version']").first.wait_for()
        if name == "admin":
            expect(page.get_by_text("Loading", exact=True)).to_have_count(0)
            expect(page.get_by_text("Loading settings", exact=True)).to_have_count(0)
        if name == "validation":
            page.locator("#validation-active-button").click()
            expect(page.locator("#validation-source-label")).not_to_contain_text("Loading")
            expect(page.locator("#validation-readiness")).not_to_have_text("Not run")
            expect(page.locator("#validation-active-button")).to_be_enabled()
        page.screenshot(path=str(evidence / f"{name}.png"), full_page=True)
    page.reload()
    expect(page.locator("#validation-active-button")).to_be_visible()
