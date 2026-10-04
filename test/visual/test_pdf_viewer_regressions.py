"""Regression checks for the production PDF review viewer."""

from pathlib import Path
import json
import subprocess

import pytest


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


@pytest.mark.parametrize("template_name", [
    "human_review.html", "extraction_results.html", "failures.html",
])
def test_document_pages_invalidate_the_pdf_viewer_cache(
    template_name: str,
) -> None:
    """Load provider-neutral evidence messages on every shared viewer page."""

    template = (ROOT / "web/templates" / template_name).read_text(encoding="utf-8")

    assert "pdf_viewer.js?v=pdf-evidence-4" in template


def test_diagnostic_sources_never_become_verified_field_highlights() -> None:
    """Execute the real source normalizer for diagnostic and legacy boxes."""
    script = """
        const fs = require('node:fs');
        const vm = require('node:vm');
        const path = process.argv[1];
        const source = fs.readFileSync(path, 'utf8').replace(
            'const PDFJS_IMPORT = import(PDFJS_MODULE);',
            'const PDFJS_IMPORT = Promise.resolve({});'
        );
        const context = {window:{}};
        vm.runInNewContext(source, context);
        const normalize = context.window.DocFlowPdfViewer.normalizeFieldSource;
        const evidence = {pages:[2], provider_source:{page:2, bounding_boxes:[
            {x:10,y:20,w:30,h:40}
        ]}};
        const diagnostic = normalize({source:{...evidence, box_usage:'diagnostic_only'}}, []);
        const legacy = normalize({source:evidence}, []);
        process.stdout.write(JSON.stringify({diagnostic,legacy}));
    """
    completed = subprocess.run(
        ["node", "-e", script, str(ROOT / "web/static/js/pdf_viewer.js")],
        capture_output=True, text=True, check=True,
    )
    result = json.loads(completed.stdout)
    assert result["diagnostic"]["boxes"] == []
    assert result["diagnostic"]["pages"] == [2]
    assert result["diagnostic"]["locationMode"] == "page_only"
    assert result["diagnostic"]["diagnosticOnly"] is True
    assert len(result["legacy"]["boxes"]) == 1
    assert result["legacy"]["locationMode"] == "bounding_box"
