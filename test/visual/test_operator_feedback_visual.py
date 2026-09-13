"""Browser-rendered checks for the operator feedback improvements."""

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect

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
    page.locator("#processing-progress-region[aria-busy='false']").wait_for()
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


def test_review_completion_vocabulary_and_independent_panes(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Keep review actions visible and distinguish reviewed fields from model confidence."""

    page.set_viewport_size({"width": 1366, "height": 900})
    page.goto(f"{visual_app['base_url']}/app/review/{visual_app['review_id']}")
    page.locator("#review-fields-container .review-field-row").first.wait_for()
    divider = page.locator("#review-pane-divider")
    assert divider.is_visible()
    assert divider.get_attribute("role") == "separator"
    initial_percent = int(divider.get_attribute("aria-valuenow") or "0")
    divider.focus()
    divider.press("ArrowLeft")
    assert int(divider.get_attribute("aria-valuenow") or "0") == initial_percent - 3

    editor_scroll = page.locator(".review-editor-scroll")
    editor_scroll.evaluate("node => { node.scrollTop = node.scrollHeight; }")
    assert editor_scroll.evaluate("node => node.scrollTop > 0")
    assert page.locator("#review-complete-button").evaluate(
        "node => { const box = node.getBoundingClientRect(); return box.top >= 0 && box.bottom <= innerHeight; }"
    )
    assert page.locator("#review-pdf-body").evaluate(
        "node => node.getBoundingClientRect().bottom <= innerHeight"
    )
    _capture(page, "06-review-independent-panes")

    saved_split = page.evaluate("localStorage.getItem('docflow.review.pdfPanePercent')")
    page.set_viewport_size({"width": 390, "height": 900})
    page.wait_for_function("() => !document.querySelector('#review-pane-divider').getBoundingClientRect().width")
    assert page.evaluate("localStorage.getItem('docflow.review.pdfPanePercent')") == saved_split
    page.set_viewport_size({"width": 1366, "height": 900})
    page.wait_for_function(
        "value => document.querySelector('#review-pane-divider').getAttribute('aria-valuenow') === value",
        arg=saved_split,
    )

    page.evaluate("document.body.classList.remove('sidebar-collapsed')")
    page.set_viewport_size({"width": 950, "height": 768})
    page.locator('#human-review-workspace.is-narrow').wait_for()
    assert page.locator('.review-editor-panel').evaluate(
        "node => node.getBoundingClientRect().right <= innerWidth"
    )
    page.locator('#human-review-workspace').evaluate('node => node.scrollTop = node.scrollHeight')
    _capture(page, '12-review-narrow-desktop')
    page.evaluate("document.body.classList.add('sidebar-collapsed')")

    page.set_viewport_size({"width": 1024, "height": 768})
    divider.press("End")
    assert page.evaluate(
        "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
    )
    page.set_viewport_size({"width": 1366, "height": 900})

    page.goto(
        f"{visual_app['base_url']}/app/review/"
        f"{visual_app['completed_review_id']}"
    )
    page.locator("#review-completion-banner").wait_for()
    assert page.get_by_text("Review complete.", exact=True).count() >= 1
    assert page.get_by_text("no further review action is required", exact=False).count() == 1
    assert page.get_by_text("No model confidence", exact=True).count() >= 1
    assert page.locator("#review-fields-container .review-input-invalid").count() == 0
    assert page.locator("#review-fields-container .highlight").count() == 0
    _capture(page, "07-completed-review-vocabulary")

    page.goto(
        f"{visual_app['base_url']}/app/documents/"
        f"{visual_app['completed_document_id']}/extraction"
    )
    page.locator("#extraction-review-summary").wait_for()
    assert page.get_by_text("Human review complete.", exact=True).count() == 1
    assert page.locator("#extraction-fields-table-body").get_by_text(
        "Reviewed", exact=True
    ).count() == 1
    assert page.locator("#extraction-fields-table-body").get_by_text(
        "Corrected", exact=True
    ).count() == 1
    assert page.locator("#extraction-fields-table-body").get_by_text(
        "Required", exact=True
    ).count() == 0
    assert page.locator("#extraction-fields-table-body").get_by_text(
        "No model confidence", exact=True
    ).count() == 1
    _capture(page, "08-extraction-reviewed-vocabulary")

    page.set_viewport_size({"width": 1265, "height": 712})
    page.goto(
        f"{visual_app['base_url']}/app/review/"
        f"{visual_app['completed_review_id']}"
    )
    page.locator("#review-completion-banner").wait_for()
    _capture(page, "10-completed-review-audit-viewport")

    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{visual_app['base_url']}/app/review/{visual_app['review_id']}")
    page.locator("#review-fields-container .review-field-row").first.wait_for()
    page.locator(".docflow-pdf-page canvas").first.wait_for()
    assert not page.locator("#review-pane-divider").is_visible()
    assert page.locator("#review-complete-button").evaluate(
        "node => node.getBoundingClientRect().right <= innerWidth"
    )
    assert page.evaluate(
        "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
    )
    panel_header = page.locator(".review-editor-panel > .panel-header")
    assert panel_header.evaluate(
        "node => node.scrollWidth <= node.clientWidth + 1"
    )
    _capture(page, "09-review-stacked-mobile")


def test_review_completion_shows_pending_feedback(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Show durable progress feedback while the synchronous completion request waits."""

    page.set_viewport_size({"width": 1366, "height": 900})
    page.goto(f"{visual_app['base_url']}/app/review/{visual_app['review_id']}")
    page.locator("#review-fields-container .review-field-row").first.wait_for()
    page.locator("#review-claim-button").click()
    page.locator("#review-complete-button:not([disabled])").wait_for()

    page.evaluate(
        """() => {
            const originalApiPost = window.DocFlow.apiPost;
            window.DocFlow.apiPost = async (url, payload) => {
                if (url.includes('/complete')) {
                    await new Promise(resolve => setTimeout(resolve, 5000));
                    return {review_item_id: 'review', status: 'completed', resume_triggered: true};
                }
                return originalApiPost(url, payload);
            };
        }"""
    )
    page.locator("#review-complete-button").click(no_wait_after=True)
    page.locator("#review-action-status").wait_for()
    assert page.locator("#review-complete-button").inner_text().startswith("Saving review")
    assert page.locator("#review-action-status").inner_text().startswith(
        "Saving review and finishing workflow"
    )
    assert page.locator("#review-complete-button").get_attribute("aria-busy") == "true"
    _capture(page, "11-review-completion-pending")


def test_review_queue_actionable_views(page: Page, visual_app: dict[str, str]) -> None:
    """Switch active/history views and retain server sorting and page size."""
    page.goto(f"{visual_app['base_url']}/app/review")
    page.locator('#review-queue-region[aria-busy="false"]').wait_for()
    assert page.locator('#review-queue-body').get_by_text('Completed', exact=True).count() == 0
    page.locator('#review-page-size').select_option('10')
    page.locator('[data-review-sort="document"]').click()
    page.locator('#review-queue-region[aria-busy="false"]').wait_for()
    assert page.locator('[data-review-sort="document"]').locator('..').get_attribute('aria-sort') == 'ascending'
    page.locator('[data-filter="completed"]').click()
    page.locator('#review-queue-region[aria-busy="false"]').wait_for()
    assert page.locator('#review-queue-body').get_by_text('Completed', exact=True).count() >= 1
    assert page.locator('#review-ownership').is_hidden()
    assert page.locator('#review-page-size').input_value() == '10'
    _capture(page, '13-review-queue-history')
    page.set_viewport_size({"width": 390, "height": 900})
    _capture(page, '14-review-queue-mobile')


def test_badges_and_desktop_pane_reflow(page: Page, visual_app: dict[str, str]) -> None:
    """Keep badge text and field controls inside narrow panes on wide desktops."""
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{visual_app['base_url']}/app/review/{visual_app['review_id']}")
    page.locator("#review-fields-container .review-field-row").first.wait_for()
    divider = page.locator("#review-pane-divider")
    divider.focus()
    divider.press("End")
    page.wait_for_function("() => document.querySelector('.review-editor-panel').clientWidth < 832")
    assert page.locator('.review-field-row').evaluate_all("""rows => rows.every(row => {
        const input = row.querySelector('input, textarea, select');
        if (!input) return true;
        const r = row.getBoundingClientRect(), b = input.getBoundingClientRect();
        return b.left >= r.left && b.right <= r.right + 1;
    })""")
    assert page.locator('#review-fields-container .badge').evaluate_all("""badges => badges.every(b => {
        const style = getComputedStyle(b);
        return b.clientHeight >= parseFloat(style.lineHeight) && b.scrollWidth <= b.clientWidth + 1;
    })""")
    _capture(page, '15-badges-wide-desktop-narrow-pane')
    page.set_viewport_size({"width": 1100, "height": 900})
    _capture(page, '16-badges-compact-desktop')


def test_compact_numbered_upload(page: Page, visual_app: dict[str, str]) -> None:
    """Keep pipeline details optional and selection independent of disclosure."""
    page.goto(f"{visual_app['base_url']}/app/upload")
    radio = page.locator("input[name='pipeline-version']").first
    radio.wait_for()
    assert page.get_by_role('heading', name='1. Select a pipeline').is_visible()
    assert page.get_by_role('heading', name='2. Upload PDFs').is_visible()
    assert page.get_by_role('button', name='3. Start processing', exact=True).is_visible()
    assert page.locator("input[name='pipeline-version']:checked").count() == 0
    details = page.locator('.upload-pipeline-details').first
    details.locator('summary').click()
    assert details.get_attribute('open') is not None
    assert page.locator("input[name='pipeline-version']:checked").count() == 0
    assert details.get_by_text('Published', exact=False).is_visible()
    radio.check()
    assert page.locator("input[name='pipeline-version']:checked").count() == 1
    assert page.locator('#start-processing-button').is_disabled()
    assert page.locator('.upload-pipeline-card').first.evaluate('node => node.getBoundingClientRect().height < 150')
    _capture(page, '17-compact-upload-desktop')
    page.set_viewport_size({"width": 390, "height": 900})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    _capture(page, '18-compact-upload-mobile')


def test_batch_failure_guidance(page: Page, visual_app: dict[str, str]) -> None:
    """Guide users to existing details without adding recovery requests."""
    payload = {
        "batch": {"id": visual_app["batch_id"], "status": "completed_with_errors"},
        "pipeline": {"name": "Synthetic invoice pipeline", "template_key": "test", "version_number": 1},
        "documents": [
            {"id": "failed-doc", "original_filename": "failed-invoice.pdf", "status": "failed"},
            {"id": "task-failed-doc", "original_filename": "long-invoice-" + "x" * 100 + ".pdf", "status": "completed", "task_runs": [{"status": "failed"}]},
            {"id": "good-doc", "original_filename": "successful-invoice.pdf", "status": "completed"},
        ],
    }
    endpoint = f"**/api/batches/{visual_app['batch_id']}/processing-state"
    page.route(endpoint, lambda route: route.fulfill(json=payload))
    page.goto(f"{visual_app['base_url']}/app/batches/{visual_app['batch_id']}")
    notice = page.locator('#processing-failure-notice')
    expect(notice).to_be_visible()
    expect(notice).to_contain_text('2 documents have recorded failures')
    assert notice.get_by_role('link').count() == 2
    assert notice.get_by_role('link').first.get_attribute('href') == '/app/failures?document_id=failed-doc'
    assert 'successful-invoice' not in notice.inner_text()
    _capture(page, '19-batch-failure-guidance-desktop')
    page.set_viewport_size({"width": 390, "height": 900})
    assert notice.evaluate('el => el.scrollWidth <= el.clientWidth + 1')
    _capture(page, '20-batch-failure-guidance-mobile')
    payload['documents'] = [payload['documents'][0]]
    page.reload()
    expect(notice).to_contain_text('1 document has recorded failures')
    payload['documents'] = []
    page.reload()
    expect(page.locator('#processing-progress-region')).to_have_attribute('aria-busy', 'false')
    expect(notice).to_be_hidden()
