"""Regression checks for the production PDF review viewer."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pdf_viewer_renders_only_the_active_page() -> None:
    """Keep large source PDFs from becoming one long rendered document."""

    source = (ROOT / "web/static/js/pdf_viewer.js").read_text(encoding="utf-8")

    assert "async function renderPage(pageNumberValue" in source
    assert "pagesRoot.replaceChildren(pageElementNode);" in source
    assert "state.pages = [{ element: pageElementNode, highlightLayer, viewport }];" in source
    assert "for (let pageNumberValue = 1; pageNumberValue <= state.pdf.numPages" not in source
    assert 'aria-label="Previous page" disabled' in source
    assert 'aria-label="Next page" disabled' in source
    assert 'class="docflow-pdf-page-input"' in source
    assert "function submitPageInput()" in source
    assert 'pageInput.addEventListener("change", submitPageInput);' in source
    assert '<span class="sr-only">Page number</span>' not in source
    assert "docflow-pdf-page-readout" not in source


def test_pdf_viewer_jumps_to_and_centers_selected_source_locations() -> None:
    """Selecting field evidence should render its page before centering it."""

    source = (ROOT / "web/static/js/pdf_viewer.js").read_text(encoding="utf-8")

    assert "state.pendingPage = firstPage;" in source
    assert "renderPage(firstPage, { behavior: \"auto\", center: true })" in source
    assert "const bounds = selectedBounds();" in source
    assert "const boundsCenterX = bounds ? (bounds.left + bounds.right) / 2" in source
    assert "const boundsCenterY = bounds ? (bounds.top + bounds.bottom) / 2" in source
    assert "if (state.pdf && state.currentPage !== pageNumberValue)" in source


def test_pdf_viewer_keeps_location_centering_automatic_without_a_toolbar_button() -> None:
    """Avoid exposing a control that is usually a no-op at the scroll boundary."""

    source = (ROOT / "web/static/js/pdf_viewer.js").read_text(encoding="utf-8")

    assert "docflow-pdf-center" not in source
    assert "centerSelected({ behavior: \"auto\" })" in source


def test_human_review_invalidates_the_pdf_viewer_cache_after_navigation_change() -> None:
    """Ensure browsers load the single-page viewer implementation."""

    template = (ROOT / "web/templates/human_review.html").read_text(encoding="utf-8")

    assert "pdf_viewer.js?v=pdf-pager-input-2" in template
