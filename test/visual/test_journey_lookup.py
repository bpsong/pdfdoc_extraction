"""Browser regressions for review pickup, batch lookup and template counts."""

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect

from test.visual.test_schema_review_visual import page, visual_app


def test_operator_can_pick_up_review_and_find_batch(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Keep review actions visible and both batch destinations keyboard accessible."""
    base = visual_app["base_url"]
    page.set_viewport_size({"width": 1017, "height": 883})
    page.goto(f"{base}/logout")
    page.get_by_label("Username").select_option("operator")
    page.get_by_label("Password").fill("OperatorPass1!")
    page.get_by_role("button", name="Login").click()
    page.wait_for_url("**/app/upload")
    page.goto(f"{base}/app/review")
    invoice = page.get_by_role("row").filter(has_text="invoice.pdf").first
    claim = invoice.get_by_role("button", name="Claim & review")
    expect(claim).to_be_in_viewport(ratio=1)
    expect(invoice.get_by_text("Supplier, Invoice amount")).to_be_in_viewport()
    expect(invoice.get_by_text("Low confidence", exact=False)).to_be_in_viewport()
    assert page.locator("#review-queue-region").evaluate("(el) => el.scrollLeft") == 0
    claim.click()
    expect(page).to_have_url(f"{base}/app/review/{visual_app['review_id']}")

    page.goto(f"{base}/app/reports")
    batch_id = visual_app["batch_id"]
    row = page.locator("#reports-recent-body").get_by_role("row").filter(has_text=batch_id)
    link = row.get_by_role("link", name="phase14-source-package-with-a-deliberately-long-filename.pdf")
    expect(link).to_have_attribute("href", f"/app/batches/{batch_id}")
    row.get_by_role("button").press("Space")
    expect(page.locator("#batch-detail-modal")).to_be_visible()
    expect(page.locator("#batch-detail-processing-link")).to_have_attribute("href", f"/app/batches/{batch_id}")
    page.get_by_role("button", name="Close", exact=True).click()
    link.press("Enter")
    expect(page).to_have_url(f"{base}/app/batches/{batch_id}")


def test_admin_count_matches_editor_choices(page: Page, visual_app: dict[str, str]) -> None:
    """Count each non-archived template once and link to the same set."""
    base = visual_app["base_url"]
    page.goto(f"{base}/app/admin")
    expect(page.locator("#admin-pipeline-health")).to_have_text("3")
    page.get_by_role("link", name="View active and inactive templates").click()
    templates = page.get_by_role("combobox", name="Pipeline template")
    expect(templates.locator("option")).to_have_count(4)  # Placeholder plus three templates.
