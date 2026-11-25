"""Configure and publish a CSV lookup through the real pipeline editor."""

from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, expect

from modules.db.connection import managed_connect
from modules.db.repositories import DocumentRepository, ReviewRepository
from modules.services.csv_reference_lookup import CSV_LOOKUP_TASK
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.processing_worker import ProcessingWorker
from test.helpers_assertions import require_present
from test.helpers_business_validation_workflow import offline_invoice_workflows, write_synthetic_pdf
from test.helpers_lookup_visual import EVIDENCE, VIEWPORTS, capture_lookup, login_lookup, lookup_browser, lookup_config
from test.integration.test_lookup_exports import AMBIGUOUS_REGISTER, INVOICE, assert_lookup_exports, lookup_export_definition
from test.integration.test_lookup_pipeline import _add_gate, _definition


def _fill(control: Locator, value: str) -> None:
    control.fill(value)
    control.press("Tab")


def _configure_lookup(page: Page, current_step_count: int, *, output_field: str) -> Locator:
    add_task = page.locator("#pipeline-add-task-select")
    lookup_option = add_task.locator(f'option[value$="{CSV_LOOKUP_TASK[1]}"]')
    expect(lookup_option).to_have_count(1)
    add_task.select_option(require_present(lookup_option.get_attribute("value")))
    page.locator("#pipeline-add-task-button").click()
    editor = page.locator("[data-lookup-controls]")
    expect(editor.get_by_label("Comparison mode")).to_have_value("case_sensitive")
    for index in range(current_step_count, 1, -1):
        page.locator(f'[data-move-step="{index}"][data-direction="-1"]').click()
    _fill(editor.get_by_label("Reference CSV"), "register.csv")
    first = editor.get_by_role("group", name="Clause 1")
    _fill(first.get_by_label("Extracted field"), "tax")
    _fill(first.get_by_label("CSV column"), "Tax")
    editor.get_by_role("button", name="Add clause").click()
    second = editor.get_by_role("group", name="Clause 2")
    _fill(second.get_by_label("Extracted field"), "supplier")
    _fill(second.get_by_label("CSV column"), "Name")
    second.get_by_label("Comparison mode").select_option("case_insensitive")
    expect(second.get_by_label("Comparison mode")).to_be_focused()
    mapping = editor.get_by_role("group", name="Mapping 1")
    _fill(mapping.get_by_label("CSV column"), "Code")
    _fill(mapping.get_by_label("Output field"), output_field)
    return editor


def _publish_editor_draft(page: Page) -> str:
    page.locator("#pipeline-validate-button").click()
    publish = page.locator("#pipeline-publish-button")
    expect(publish).to_be_enabled()
    publish.click()
    with page.expect_response(lambda response: response.url.endswith("/publish")) as published:
        page.get_by_role("button", name="Publish version").click()
    assert published.value.status == 200, published.value.json()
    version = published.value.json()["version"]
    expect(page.locator("#pipeline-version-history")).to_contain_text(f"latest v{version['version_number']}")
    expect(page.locator("#pipeline-add-task-button")).to_be_enabled()
    return version["id"]


@pytest.mark.parametrize(("viewport", "width", "height"), VIEWPORTS, ids=["desktop", "mobile"])
def test_lookup_editor_validation_and_publication(tmp_path: Path, viewport: str, width: int, height: int) -> None:
    config = lookup_config(tmp_path)
    (tmp_path / "register.csv").write_text("Tax,Name,Code\n00123,Acme,00042\n", encoding="utf-8")
    definition = _definition(tmp_path)
    definition["tasks"]["extract"]["params"]["fields"]["invoice_number"] = {"type": "str", "alias": "Invoice number"}
    _add_gate(config, definition)
    definition["pipeline"].remove("lookup")
    del definition["tasks"]["lookup"]
    with managed_connect(config) as conn:
        template = PipelineTemplateService(conn).create_template(
            template_key="supplier-lookup", name="Supplier lookup", user="admin", initial_definition=definition,
        )["template"]
    template_id = template["id"]

    with lookup_browser(tmp_path, width, height, admin=True) as (page, base):
        page.goto(base + "/app/admin/pipeline")
        page.locator("#pipeline-template-select").select_option(template_id)
        editor = _configure_lookup(page, len(definition["pipeline"]), output_field="invoice_number")
        first = editor.get_by_role("group", name="Clause 1")
        second = editor.get_by_role("group", name="Clause 2")
        mapping = editor.get_by_role("group", name="Mapping 1")
        required = editor.get_by_label("Require a resolved lookup before release")
        required.uncheck()
        editor.get_by_label("Multiple matches").select_option("continue")
        expect(editor.get_by_label("No match")).to_have_value("review")
        editor.get_by_label("Multiple matches").select_option("fail")
        required.check()
        expect(editor.get_by_label("Multiple matches")).to_have_value("fail")
        with page.expect_response(lambda response: response.url.endswith("/draft/validate")) as validation:
            page.locator("#pipeline-validate-button").click()
        findings = validation.value.json()["findings"]
        collision = next(finding for finding in findings if finding["code"] == "lookup-field-collision")
        error = mapping.get_by_text("Return field conflicts with an extraction or lookup field.")
        expect(page.locator("#pipeline-publish-help")).to_contain_text("Resolve blocking")
        assert error.count() == 1, (collision, mapping.inner_text())
        expect(error).to_be_visible()
        expect(page.locator("#pipeline-publish-button")).to_be_disabled()
        error.scroll_into_view_if_needed()
        capture_lookup(page, f"editor-validation-{viewport}")
        _fill(mapping.get_by_label("Output field"), "supplier_id")
        with page.expect_response(lambda response: response.url.endswith("/draft")) as saved:
            page.locator("#pipeline-save-draft-button").click()
        assert saved.value.status == 200
        _publish_editor_draft(page)
        page.reload()
        expect(page.locator("#pipeline-template-select")).to_have_value(template_id)
        expect(page.locator("#pipeline-add-task-button")).to_be_enabled()
        page.locator("[data-select-step='1']").click()
        expect(first.get_by_label("Comparison mode")).to_have_value("case_sensitive")
        expect(second.get_by_label("Comparison mode")).to_have_value("case_insensitive")
        expect(mapping.get_by_label("Output field")).to_have_value("supplier_id")
        expect(editor.get_by_label("Reference CSV")).to_have_value("register.csv")
        expect(editor.get_by_label("Multiple matches")).to_have_value("fail")


def test_editor_publication_drives_operator_upload_review_and_exports(tmp_path: Path) -> None:
    config = lookup_config(tmp_path)
    reference = tmp_path / "register.csv"
    reference.write_bytes(AMBIGUOUS_REGISTER)
    source = tmp_path / "synthetic-release-invoice.pdf"
    write_synthetic_pdf(source, ["SYNTHETIC RELEASE INVOICE", "Tax ID: 00123", "Supplier: Acme"])
    definition = lookup_export_definition(tmp_path)
    _add_gate(config, definition)
    definition["pipeline"].remove("lookup")
    del definition["tasks"]["lookup"]
    with managed_connect(config) as conn:
        template = PipelineTemplateService(conn).create_template(
            template_key="release-lookup", name="Release lookup", user="admin", initial_definition=definition,
        )["template"]

    with lookup_browser(tmp_path, 1366, 768, admin=True) as (page, base):
        page.goto(base + "/app/admin/pipeline")
        page.locator("#pipeline-template-select").select_option(template["id"])
        editor = _configure_lookup(page, len(definition["pipeline"]), output_field="supplier_id")
        expect(editor.get_by_label("Multiple matches")).to_have_value("review")
        version_id = _publish_editor_draft(page)
        page.get_by_role("button", name="Activate for uploads").click()
        expect(page.get_by_role("button", name="Active for uploads")).to_be_visible()

        page.goto(base + "/logout")
        login_lookup(page, base, admin=False)
        page.locator(f'input[name="pipeline-version"][value="{version_id}"]').check()
        page.locator("#pdf-file-input").set_input_files(source)
        with page.expect_response(lambda response: response.url.endswith("/api/batches/upload")) as uploaded:
            page.locator("#start-processing-button").click()
        assert uploaded.value.ok
        page.wait_for_url("**/app/batches/*")
        batch_id = page.url.rsplit("/", 1)[-1]
        with managed_connect(config) as conn:
            (document,) = DocumentRepository(conn).list_by_batch(batch_id)
        assert document["pipeline_version_id"] == version_id
        document_id = document["id"]
        with offline_invoice_workflows(INVOICE) as extractions:
            assert ProcessingWorker(config).run_once()
            assert [call["document_id"] for call in extractions] == [document_id]
        assert not (tmp_path / "exports").exists()
        with managed_connect(config) as conn:
            review = require_present(ReviewRepository(conn).find_latest_for_document(document_id, review_kind="extraction"))

        page.goto(f"{base}/app/review/{review['id']}")
        expect(page.locator("#review-pdf-body canvas")).to_be_visible()
        page.locator("#review-claim-button").click()
        panel = page.locator("#review-lookup-panel")
        panel.get_by_role("radio", name="Record 2", exact=True).check()
        panel.get_by_role("textbox", name="Reason for this decision").fill("Confirmed synthetic register record 2")
        panel.get_by_role("button", name="Use selected record").click()
        expect(panel).to_contain_text("Matched by reviewer")
        with page.expect_response(lambda response: response.url.endswith("/complete")) as completed:
            page.get_by_role("button", name="Complete Review", exact=True).click()
        assert completed.value.ok
        completion = completed.value.request.post_data_json
        assert completion is not None and completion["lookup_preview_token"]
        page.wait_for_url("**/app/review")
        page.goto(f"{base}/app/review/{review['id']}")
        expect(page.locator("#review-lookup-status")).to_have_text("Accepted lookup evidence")
        expect(panel).to_contain_text("00042")
        expect(page.locator("#review-pdf-body canvas")).to_be_visible()
        capture_lookup(page, "published-lookup-accepted", directory=EVIDENCE.with_name("r3-phase6"))

    assert_lookup_exports(config, document_id, version_id, tmp_path / "exports", source.read_bytes(),
                          {**INVOICE, "supplier_id": "00042"}, filename_value="00042")
    assert reference.read_bytes() == AMBIGUOUS_REGISTER
