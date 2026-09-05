"""Browser-rendered checks for the operator feedback improvements."""

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page

from test.visual.test_schema_review_visual import page, visual_app


EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "output" / "playwright" / "phase16"


def _capture(page: Page, name: str) -> None:
    """Save a non-blank screenshot for the reviewed operator state."""

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    screenshot = page.screenshot(path=str(EVIDENCE_DIR / f"{name}.png"), full_page=True)
    assert len(screenshot) > 10_000


def test_operator_feedback_surfaces_render_desktop_and_mobile(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Verify accessible feedback markup and confidence labels in real pages."""

    page.set_viewport_size({"width": 1366, "height": 900})
    page.goto(f"{visual_app['base_url']}/app/upload")
    page.locator("#pipeline-version-list input[name='pipeline-version']").first.wait_for()
    assert page.locator("#app-announcement-region[role='status']").count() == 1
    assert page.locator("#upload-progress-bar[aria-label='Upload progress']").count() == 1
    assert page.locator("#upload-drop-zone[role='button']").count() == 1
    assert page.locator("#cancel-upload-button").count() == 1
    assert page.locator("details.context-help").count() == 1
    assert page.locator("#upload-progress-region").is_hidden()
    _capture(page, "01-upload-feedback-desktop")

    page.goto(f"{visual_app['base_url']}/app/batches/{visual_app['batch_id']}")
    page.locator("#pipeline-assignment-summary strong").wait_for()
    assert page.locator("#processing-progress-region[aria-busy='false']").count() == 1
    assert page.locator("#processing-table-region[aria-busy='false']").count() == 1
    assert page.locator("#processing-table-body[aria-busy='false']").count() == 1
    assert page.locator("#processing-table-region.app-queue-table-region").count() == 1
    assert page.locator("#processing-table-region thead th").count() == 6
    _capture(page, "02-processing-feedback-desktop")

    page.set_viewport_size({"width": 390, "height": 900})
    _capture(page, "03-processing-feedback-mobile")

    page.goto(f"{visual_app['base_url']}/app/review")
    page.locator("#review-queue-body .badge").first.wait_for()
    assert page.locator(".app-filter-bar").count() == 1
    assert page.locator("#review-queue-region.app-queue-table-region").count() == 1
    _capture(page, "04-review-queue-desktop")

    page.goto(
        f"{visual_app['base_url']}/app/documents/"
        f"{visual_app['extraction_document_id']}/extraction"
    )
    page.locator("#extraction-fields-table-body .badge").first.wait_for()
    badge_text = " ".join(page.locator("#extraction-fields-table-body .badge").all_text_contents())
    assert "confidence" in badge_text.lower()
    assert page.locator("details.context-help").count() == 1
    _capture(page, "05-extraction-confidence-labels")
