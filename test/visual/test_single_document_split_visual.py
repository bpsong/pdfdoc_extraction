"""Authenticated production UI evidence for split continuation and fan-out."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import bcrypt
import pytest
from pypdf import PdfReader

from modules.db.connection import connect
from modules.db.repositories import DocumentRepository, ExtractionRepository, TaskRunRepository, UserRepository
from modules.services.batch_service import BatchService
from modules.services.fan_in_service import FanInService
from standard_step.split.llamacloud_split import LlamaCloudSplitTask
from standard_step.split.llamacloud_split_adapter import SplitResult, SplitSegment
from test.helpers_sqlite import TempConfig
from test.standard_step.split.test_llamacloud_split_task import _write_pdf
from test.visual.test_schema_review_visual import visual_app

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "output" / "playwright" / "single-document-split"


def seed_split_visual_state(state: dict[str, str], directory: Path) -> dict[str, str]:
    """Seed real split decisions and synthetic downstream results in a test DB."""
    directory = Path(state["db_path"]).parent / "processing" / directory.name
    directory.mkdir(parents=True, exist_ok=True)
    config = TempConfig(Path(state["db_path"]))
    sources = []
    for kind, pages in (("single", 1), ("bundle", 4)):
        supplied = os.environ.get(f"DOCFLOW_VISUAL_{kind.upper()}_PDF")
        filename = Path(supplied).name if supplied else (
            "single-invoice.pdf" if kind == "single" else "four-invoices.pdf"
        )
        target = directory / filename
        if supplied:
            shutil.copyfile(supplied, target)
        else:
            _write_pdf(target, pages)
        sources.append(target)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web", file_path=str(sources[0]), original_filename=sources[0].name,
            pipeline_version_id=state["pipeline_version_id"],
        )
        batch_id = created["batch"]["id"]
        roots = [created["document"], DocumentRepository(conn).create_root(
            batch_id=batch_id, file_path=str(sources[1]), original_filename=sources[1].name,
            pipeline_version_id=state["pipeline_version_id"],
        )]
        password = os.environ.get("DOCFLOW_VISUAL_OPERATOR_PASSWORD")
        if password:
            UserRepository(conn).update_password(
                "operator", bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            )

    class Adapter:
        def __init__(self, bundled: bool) -> None:
            self.bundled = bundled

        def split_pdf(self, file_path: str, categories: list[dict[str, Any]]) -> SplitResult:
            page_count = len(PdfReader(file_path).pages)
            groups = [[page] for page in range(1, page_count + 1)] if self.bundled else [list(range(1, page_count + 1))]
            return SplitResult("visual-controlled-job", "completed", [
                SplitSegment("invoice", "high", pages, pages[0], pages[-1], {}) for pages in groups
            ], {})

    for index, root in enumerate(roots):
        task = LlamaCloudSplitTask(
            config, enabled=True, adapter=Adapter(index == 1),
            categories=[{"name": "invoice"}], split_dir=str(directory / "split"),
        )
        context = {"document_id": root["id"], "batch_id": batch_id,
                   "file_path": root["file_path"], "original_filename": root["original_filename"],
                   "current_task_key": "split_documents", "current_task_index": 1}
        result = task.run(context)
        assert not result.get("error")
        with connect(config) as conn:
            documents = DocumentRepository(conn)
            children = documents.list_children(root["id"])
            leaves = children or [root]
            runs = TaskRunRepository(conn)
            split_run = runs.create_started(
                batch_id=batch_id, document_id=root["id"], task_key="split_documents", task_index=1,
                module_name="standard_step.split.llamacloud_split", class_name="LlamaCloudSplitTask",
                pipeline_version_id=state["pipeline_version_id"],
            )
            runs.mark_completed(split_run["id"])
            for leaf in leaves:
                extraction = ExtractionRepository(conn).save_result(
                    document_id=leaf["id"], provider="visual-controlled",
                    data={"supplier": "Synthetic browser check"},
                )
                ExtractionRepository(conn).save_fields(
                    document_id=leaf["id"], extraction_result_id=extraction["id"],
                    fields=[{"field_key": "supplier", "extracted_value": "Synthetic browser check", "confidence": 1.0}],
                )
                extract_run = runs.create_started(
                    batch_id=batch_id, document_id=leaf["id"], task_key="extract_invoice_fields", task_index=2,
                    module_name="standard_step.extraction.extract_pdf", class_name="ExtractPdfTask",
                    pipeline_version_id=state["pipeline_version_id"],
                )
                runs.mark_completed(extract_run["id"])
                FanInService(conn).finalize_leaf({"document_id": leaf["id"]})
    return {"batch_id": str(batch_id), "original_id": str(roots[0]["id"]),
            "original_filename": sources[0].name}


@pytest.fixture(scope="module")
def split_visual_app(visual_app: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    seeded = seed_split_visual_state(visual_app, tmp_path_factory.mktemp("split_visual"))
    return {**visual_app, **seeded}


@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 900}, {"width": 390, "height": 844}])
def test_single_document_and_four_child_results_visual(split_visual_app: dict[str, str], viewport: dict[str, int]) -> None:
    """Check real links, split decisions, PDF preview, and responsive presentation."""
    state = split_visual_app
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=os.environ.get("DOCFLOW_VISUAL_BROWSER_CHANNEL"))
        page = browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(f"{state['base_url']}/login")
        page.locator('select[name="username"]').select_option("operator")
        page.locator('input[name="password"]').fill(os.environ.get("DOCFLOW_VISUAL_OPERATOR_PASSWORD", "OperatorPass1!"))
        page.locator('button[type="submit"]').click()
        page.wait_for_url("**/app/upload")
        page.goto(f"{state['base_url']}/app/batches/{state['batch_id']}/split-results")
        page.get_by_text("No split needed", exact=False).wait_for()
        assert page.locator("#split-documents-created").inner_text() == "4"
        assert page.locator("#split-documents-continuing").inner_text() == "1 original continued"
        assert page.locator("tr.split-child-row.bg-base-200\\/40").count() == 4
        assert "invoice | high confidence" in page.locator("#split-results-table-body").inner_text()
        original_link = page.locator(f'a[href="/app/documents/{state["original_id"]}/extraction"]')
        assert original_link.count() == 1
        original_link.focus()
        assert original_link.evaluate("node => node === document.activeElement")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.locator("#split-results-table-body .badge").first.evaluate(
            "node => node.getBoundingClientRect().height < 40"
        )
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(EVIDENCE_DIR / f"results-{viewport['width']}.png"), full_page=True)
        original_link.click()
        page.wait_for_url(f"**/app/documents/{state['original_id']}/extraction")
        page.locator("#extraction-fields-table-body").get_by_text("Synthetic browser check").first.wait_for()
        page.locator("#extraction-preview-body .docflow-pdf-page canvas").first.wait_for()
        page.screenshot(path=str(EVIDENCE_DIR / f"original-extraction-{viewport['width']}.png"), full_page=True)
        page.goto(f"{state['base_url']}/app/batches/{state['batch_id']}")
        page.get_by_text(state["original_filename"], exact=False).first.wait_for()
        page.screenshot(path=str(EVIDENCE_DIR / f"processing-{viewport['width']}.png"), full_page=True)
        assert not errors
        browser.close()
