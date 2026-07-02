from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
import bcrypt

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository, ExtractionRepository, ReviewRepository, UserRepository
from modules.services.batch_service import BatchService
from test.helpers_sqlite import TempConfig


pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, sync_playwright


PASSWORD_HASH = "$2b$12$uG.SmnQ76mGiPy0wyztZkO4e/hoV3lo/3J8PEXITLC9ckfF3B3qAm"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_config(tmp_path: Path, port: int, schema_dir: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    (tmp_path / "web_upload").mkdir()
    (tmp_path / "app.log").touch()
    config = {
        "database": {"path": str(tmp_path / "app_state.sqlite3"), "run_migrations_on_startup": True},
        "review": {"lock_timeout_minutes": 60, "default_queue_name": "visual_review"},
        "validation": {"config_validation_enabled": True, "allow_ui_config_save": False},
        "ui": {"app_name": "DocFlow AI", "admin_enabled": True, "operator_sidebar": ["upload", "review", "reports", "settings"]},
        "auth": {"roles_enabled": True, "default_admin_users": ["admin"]},
        "web": {"host": "127.0.0.1", "port": port, "secret_key": "visual-test-secret", "upload_dir": str(tmp_path / "web_upload")},
        "watch_folder": {"dir": str(tmp_path / "watch"), "processing_dir": str(tmp_path / "processing")},
        "logging": {"log_file": str(tmp_path / "app.log"), "log_level": "INFO"},
        "schema": {"directories": [str(schema_dir)]},
        "tasks": {},
        "pipeline": [],
    }
    (tmp_path / "watch").mkdir()
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def _seed_visual_state(tmp_path: Path, config_path: Path, schema_dir: Path) -> str:
    schema_dir.mkdir()
    (schema_dir / "invoice.yaml").write_text(
        """
title: Visual Invoice
description: Visual test schema
fields:
  supplier:
    type: string
    label: Supplier
    description: Confirm supplier name exactly as shown on the invoice.
    required: true
    min_length: 2
    pattern: "^A"
    placeholder: Supplier name
  invoice_amount:
    type: number
    label: Invoice amount
    help: Review displays two decimals and increments by 0.01.
    required: true
    min_value: 0
    step: 0.01
    decimal_places: 2
    format: money
  approved:
    type: boolean
    label: Approved
    required: true
  reviewed_at:
    type: datetime
    label: Reviewed at
    description: Browser datetime input should be populated from ISO values.
  address:
    type: object
    label: Address
    description: Billing address details.
    properties:
      city:
        type: string
        label: City
        help: City is imported from the source invoice and is read only.
        readonly: true
  tags:
    type: array
    label: Tags
    items:
      type: enum
      choices: [urgent, standard]
  line_items:
    type: array
    label: Line items
    description: Invoice item table.
    items:
      type: object
      properties:
        sku:
          type: string
          label: SKU
          help: Source SKU cannot be edited.
          readonly: true
        quantity:
          type: integer
          label: Quantity
          min_value: 1
        unit_price:
          type: number
          label: Unit price
          help: Unit price uses cents.
          step: 0.01
          decimal_places: 2
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = TempConfig(
        tmp_path / "app_state.sqlite3",
        {"schema": {"directories": [str(schema_dir)]}, "database": {"path": str(tmp_path / "app_state.sqlite3")}},
    )
    config._config_path = config_path
    initialize_database(config)
    with connect(config) as conn:
        UserRepository(conn).initialize({"admin": PASSWORD_HASH, "operator": bcrypt.hashpw(b"OperatorPass1!", bcrypt.gensalt()).decode()})
    pdf_path = tmp_path / "web_upload" / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% visual test")

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="visual",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
        document_id = created["document"]["id"]
        DocumentRepository(conn).add_file(document_id=document_id, file_type="original_pdf", file_path=str(pdf_path))
        extraction = ExtractionRepository(conn).save_result(document_id=document_id, provider="visual", data={})
        ExtractionRepository(conn).save_fields(
            document_id=document_id,
            extraction_result_id=extraction["id"],
            fields=[
                {"field_key": "supplier", "field_alias": "Supplier", "extracted_value": "Acme", "confidence": 0.61, "requires_review": True},
                {"field_key": "invoice_amount", "field_alias": "Invoice amount", "extracted_value": 70, "confidence": 0.82, "requires_review": True},
                {"field_key": "approved", "field_alias": "Approved", "extracted_value": None, "confidence": 0.8},
                {"field_key": "reviewed_at", "field_alias": "Reviewed at", "extracted_value": "2026-06-12T09:30:00Z", "confidence": 0.95},
                {"field_key": "address", "field_alias": "Address", "extracted_value": {"city": "Singapore"}, "confidence": 0.95},
                {"field_key": "tags", "field_alias": "Tags", "extracted_value": ["urgent"], "confidence": 0.9},
                {
                    "field_key": "line_items",
                    "field_alias": "Line items",
                    "extracted_value": [{"sku": "ABC", "quantity": 2, "unit_price": 4.5}],
                    "confidence": 0.88,
                    "source": {
                        "confidence_details": {
                            "aggregation": "minimum_nested_confidence",
                            "confidence": 0.88,
                            "nested_confidences": {
                                "0.sku": {"confidence": 0.96, "confidence_band": "high"},
                                "0.quantity": {"confidence": 0.88, "confidence_band": "medium"},
                                "0.unit_price": {"confidence": 0.94, "confidence_band": "high"},
                            },
                        }
                    },
                },
            ],
        )
        review = ReviewRepository(conn).create_review_item(
            batch_id=created["batch"]["id"],
            document_id=document_id,
            queue_name="visual_review",
            reason="low_confidence",
            scope="low_confidence_fields",
            metadata={
                "schema_file": "invoice.yaml",
                "highlight_fields": ["invoice_amount"],
                "low_confidence_paths": ["line_items.0.quantity"],
                "editable_fields": ["supplier", "invoice_amount", "approved", "reviewed_at", "address", "tags", "line_items"],
            },
        )
    return str(review["id"])


@pytest.fixture(scope="module")
def visual_app(tmp_path_factory: pytest.TempPathFactory):
    tmp_path = tmp_path_factory.mktemp("visual_app")
    port = _free_port()
    schema_dir = tmp_path / "schemas"
    config_path = _write_config(tmp_path, port, schema_dir)
    review_id = _seed_visual_state(tmp_path, config_path, schema_dir)
    env = os.environ.copy()
    env["CONFIG_PATH"] = str(config_path)
    env["PREFECT_LOGGING_TO_API_ENABLED"] = "false"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web.server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except OSError:
            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr else ""
                raise RuntimeError(f"Visual test server exited early: {stderr}")
            time.sleep(0.25)
    else:
        process.terminate()
        raise RuntimeError("Visual test server did not start")

    yield {"base_url": base_url, "review_id": review_id}

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture()
def page(visual_app: dict[str, str]):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()
        errors: list[str] = []
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(f"{visual_app['base_url']}/login")
        page.locator('select[name="username"]').select_option("admin")
        page.locator('input[name="password"]').fill("password123")
        page.locator('button[type="submit"]').click()
        page.wait_for_url("**/app/upload")
        yield page
        assert not errors
        context.close()
        browser.close()


def _assert_nonblank_screenshot(page: Page) -> None:
    screenshot = page.screenshot(full_page=True)
    assert len(screenshot) > 10_000


def _assert_no_horizontal_overflow(page: Page) -> None:
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 4


def _computed_style(page: Page, selector: str, properties: list[str]) -> dict[str, str]:
    return page.locator(selector).first.evaluate(
        """(node, names) => {
            const style = getComputedStyle(node);
            return Object.fromEntries(names.map(name => [name, style[name]]));
        }""",
        properties,
    )


def test_review_visual_schema_driven_fields_desktop_and_mobile(page: Page, visual_app: dict[str, str]) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{visual_app['base_url']}/app/review/{visual_app['review_id']}")
    page.locator("#review-fields-container .review-field-row").first.wait_for()
    page.locator("body.sidebar-collapsed").wait_for()
    assert page.locator('.nav-link[aria-label="Review Queue"]').get_attribute("title") == "Review Queue"
    assert page.locator('.nav-link[aria-label="Review Queue"]').get_attribute("data-nav-label") == "Review Queue"
    assert page.locator("#review-pdf-fit-width-button").count() == 0
    assert page.locator("#review-pdf-fit-page-button").count() == 0
    assert "zoom=" not in (page.locator(".review-pdf-frame").get_attribute("src") or "")
    page.locator("#review-claim-button").click()
    page.locator("#review-lock-summary").wait_for()
    assert page.locator("#review-claim-button").is_hidden()
    assert page.locator("#review-release-button").is_visible()
    assert page.locator("#review-release-button").is_enabled()
    assert page.locator("#review-lock-banner").is_hidden()
    page.locator('input[data-field-path="invoice_amount"]').wait_for()
    amount = page.locator('input[data-field-path="invoice_amount"]')
    assert amount.input_value() == "70.00"
    assert amount.get_attribute("step") == "0.01"
    assert page.locator("#review-source-mode-select").input_value() == "review"
    amount_row = page.locator('.review-field-row[data-field-path="invoice_amount"]')
    assert amount_row.locator(".review-extracted-value").is_visible()
    assert (amount_row.locator(".review-extracted-value").text_content() or "").startswith("Source: ")
    assert amount_row.locator(".review-field-info").get_attribute("data-tip") == "Review displays two decimals and increments by 0.01."
    assert page.locator("text=Review displays two decimals and increments by 0.01.").count() == 0
    assert page.locator('.review-field-row[data-field-path="reviewed_at"]').get_attribute("class")
    assert "source-hidden" in (
        page.locator('.review-field-row[data-field-path="reviewed_at"]').get_attribute("class") or ""
    )
    assert page.locator('select[data-field-path="approved"]').input_value() == ""
    assert page.locator('input[data-field-path="reviewed_at"]').input_value() == "2026-06-12T09:30"
    assert page.locator('input[data-field-path="address.city"]').is_disabled()
    assert page.locator(".review-object-array-table").is_visible()
    assert page.locator(".review-object-array-table .review-field-info").first.get_attribute("data-tip")
    assert page.locator(".review-object-array-table .review-cell-confidence .badge").filter(has_text="88%").count() == 1
    assert page.locator('td.highlight input[data-field-path="line_items.0.quantity"]').count() == 1
    _assert_nonblank_screenshot(page)
    _assert_no_horizontal_overflow(page)

    page.set_viewport_size({"width": 390, "height": 900})
    page.locator("#review-fields-container").wait_for()
    _assert_nonblank_screenshot(page)


def test_review_visual_source_toggle_and_sidebar_preference(page: Page, visual_app: dict[str, str]) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{visual_app['base_url']}/app/review/{visual_app['review_id']}")
    page.locator("#review-fields-container .review-field-row").first.wait_for()
    page.locator("body.sidebar-collapsed").wait_for()
    if page.locator("#review-claim-button").is_visible() and page.locator("#review-claim-button").is_enabled():
        page.locator("#review-claim-button").click()
        page.locator('input[data-field-path="invoice_amount"]').wait_for()
    page.locator("#review-source-mode-select").select_option("all")
    source_values = page.locator(".review-field-row .review-extracted-value")
    for index in range(source_values.count()):
        assert source_values.nth(index).is_visible()

    page.locator("#review-source-mode-select").select_option("hidden")
    for index in range(source_values.count()):
        assert not source_values.nth(index).is_visible()
    amount_row = page.locator('.review-field-row[data-field-path="invoice_amount"]')
    assert amount_row.locator(".review-source-reveal").is_visible()
    assert (amount_row.locator(".review-source-reveal").text_content() or "").strip() == ""
    assert amount_row.locator(".review-source-reveal").get_attribute("aria-label") == "Show source value for Invoice amount"
    assert page.locator('input[data-field-path="invoice_amount"]').is_enabled()
    amount_row.locator(".review-source-reveal").click()
    assert amount_row.locator(".review-extracted-value").is_visible()
    assert (amount_row.locator(".review-extracted-value").text_content() or "").startswith("Source: ")

    page.locator("#sidebar-collapse-toggle").click()
    assert not page.locator("body").evaluate("body => body.classList.contains('sidebar-collapsed')")
    page.reload()
    page.locator("#review-fields-container .review-field-row").first.wait_for()
    assert not page.locator("body").evaluate("body => body.classList.contains('sidebar-collapsed')")
    assert page.locator("#review-source-mode-select").input_value() == "hidden"
    _assert_no_horizontal_overflow(page)


def test_review_visual_wide_layout_does_not_auto_collapse(page: Page, visual_app: dict[str, str]) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{visual_app['base_url']}/app/review/{visual_app['review_id']}")
    page.locator("#review-fields-container .review-field-row").first.wait_for()
    assert not page.locator("body").evaluate("body => body.classList.contains('sidebar-collapsed')")
    assert page.locator(".review-workspace").evaluate("node => getComputedStyle(node).gridTemplateColumns.split(' ').length") >= 2
    _assert_nonblank_screenshot(page)
    _assert_no_horizontal_overflow(page)


def test_schema_editor_visual_renders_rich_schema_controls(page: Page, visual_app: dict[str, str]) -> None:
    page.goto(f"{visual_app['base_url']}/app/schemas/invoice.yaml")
    page.locator("#schema-field-tree .schema-field-row").first.wait_for()
    assert page.locator("#schema-error").text_content() == ""
    assert page.locator('[data-field-prop="step"]').first.is_visible()
    assert page.locator('[data-field-prop="decimal_places"]').first.is_visible()
    assert page.locator('[data-field-prop="pattern"]').first.is_visible()
    assert page.locator('[data-field-prop="readonly"]').first.is_visible()
    assert page.locator('[data-field-prop="array_item_type"]').first.is_visible()
    _assert_nonblank_screenshot(page)
    _assert_no_horizontal_overflow(page)

    page.set_viewport_size({"width": 390, "height": 900})
    page.locator("#schema-field-tree").wait_for()
    _assert_nonblank_screenshot(page)


def test_admin_panel_styles_match_and_wrap_without_clipping(page: Page, visual_app: dict[str, str]) -> None:
    panel_properties = ["backgroundColor", "borderColor", "borderRadius", "boxShadow", "overflow"]
    header_properties = ["minHeight", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft"]
    title_properties = ["fontSize", "fontWeight", "lineHeight"]

    page.goto(f"{visual_app['base_url']}/app/schemas/invoice.yaml")
    page.locator("#schema-field-tree .schema-field-row").first.wait_for()
    schema_panel = _computed_style(page, ".schema-detail-panel", panel_properties)
    schema_header = _computed_style(page, ".schema-detail-panel .admin-panel-header", header_properties)
    schema_title = _computed_style(page, ".schema-detail-panel .admin-panel-title", title_properties)
    assert page.locator(".schema-editor-workspace > .admin-panel").count() == 3
    assert schema_panel["overflow"] == "visible"

    page.goto(f"{visual_app['base_url']}/app/admin/pipeline")
    page.locator("#pipeline-config-workspace").wait_for()
    pipeline_panel = _computed_style(page, ".pipeline-draft-panel", panel_properties)
    pipeline_header = _computed_style(page, ".pipeline-draft-panel .admin-panel-header", header_properties)
    pipeline_title = _computed_style(page, ".pipeline-draft-panel .admin-panel-title", title_properties)
    assert page.locator(".pipeline-config-workspace > .admin-panel").count() == 7
    assert page.locator(".pipeline-config-workspace > .card").count() == 0
    assert page.locator("#pipeline-reset-button").count() == 1
    assert page.locator("#pipeline-save-draft-button").count() == 1
    assert page.locator("#pipeline-validate-button").count() == 1
    assert page.locator("#pipeline-diff-button").count() == 1
    assert schema_panel == pipeline_panel
    assert schema_header == pipeline_header
    assert schema_title == pipeline_title
    _assert_nonblank_screenshot(page)
    _assert_no_horizontal_overflow(page)

    page.set_viewport_size({"width": 390, "height": 900})
    page.reload()
    page.locator(".pipeline-draft-panel .admin-panel-actions").wait_for()
    assert _computed_style(page, ".pipeline-draft-panel .admin-panel-header", ["flexWrap"])["flexWrap"] == "wrap"
    assert _computed_style(page, ".pipeline-draft-panel .admin-panel-actions", ["width"])["width"] != "auto"
    _assert_nonblank_screenshot(page)
    _assert_no_horizontal_overflow(page)


def test_schema_editor_reorders_and_safely_deletes_fields(page: Page, visual_app: dict[str, str]) -> None:
    page.goto(f"{visual_app['base_url']}/app/schemas/invoice.yaml")
    rows = page.locator("#schema-field-tree > .schema-field-row")
    rows.first.wait_for()

    def top_level_paths() -> list[str]:
        return rows.evaluate_all("nodes => nodes.map(node => node.dataset.rowPath)")

    assert top_level_paths()[:2] == ["supplier", "invoice_amount"]
    assert page.locator('[data-move-field="supplier"][data-move-direction="up"]').is_disabled()
    assert page.locator('[data-move-field="line_items"][data-move-direction="down"]').is_disabled()
    delete_supplier = page.locator('[data-delete-field="supplier"]')
    assert delete_supplier.text_content() == "Delete field"
    assert "btn-error" in (delete_supplier.get_attribute("class") or "")

    page.locator('[data-move-field="supplier"][data-move-direction="down"]').click()
    assert top_level_paths()[:2] == ["invoice_amount", "supplier"]
    page.locator("#schema-field-status").wait_for()
    assert page.locator("#schema-field-status").text_content() == "Moved Supplier down."
    assert page.evaluate("document.activeElement?.dataset.moveField") == "supplier"
    assert page.evaluate("document.activeElement?.dataset.moveDirection") == "down"
    outline_paths = page.locator("#schema-field-outline [data-outline-path]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.outlinePath)"
    )
    assert outline_paths[:2] == ["invoice_amount", "supplier"]
    preview = page.locator("#schema-yaml-preview").text_content() or ""
    assert preview.index("invoice_amount:") < preview.index("supplier:")

    page.locator('[data-move-field="supplier"][data-move-direction="up"]').click()
    assert top_level_paths()[:2] == ["supplier", "invoice_amount"]
    assert page.evaluate("document.activeElement?.dataset.moveField") == "supplier"
    assert page.evaluate("document.activeElement?.dataset.moveDirection") == "down"

    page.locator('[data-move-field="line_items.quantity"][data-move-direction="up"]').click()
    nested_paths = page.locator(
        '[data-row-path="line_items"] .schema-field-children > .schema-field-row'
    ).evaluate_all("nodes => nodes.map(node => node.dataset.rowPath)")
    assert nested_paths[:2] == ["line_items.quantity", "line_items.sku"]
    assert top_level_paths()[-1] == "line_items"
    assert page.evaluate("document.activeElement?.dataset.moveField") == "line_items.quantity"
    assert page.evaluate("document.activeElement?.dataset.moveDirection") == "down"

    dialog_messages: list[str] = []

    def dismiss_delete(dialog) -> None:
        dialog_messages.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", dismiss_delete)
    page.locator('[data-delete-field="approved"]').click()
    assert page.locator('[data-row-path="approved"]').count() == 1
    assert dialog_messages == [
        'Delete field "Approved" from this schema draft?\n\n'
        "The field will be permanently removed when you save the schema."
    ]

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator('[data-delete-field="approved"]').click()
    assert page.locator('[data-row-path="approved"]').count() == 0
    page.locator("#schema-field-status").wait_for()
    assert page.locator("#schema-field-status").text_content() == "Deleted Approved from the schema draft."
    assert page.evaluate("document.activeElement?.dataset.fieldPath") == "reviewed_at"
    assert (page.locator("#schema-detail-title").text_content() or "").startswith("* ")
    _assert_no_horizontal_overflow(page)


def test_operator_visual_login_hides_and_blocks_admin_surfaces(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Verify operator restrictions against the started application."""
    page.goto(f"{visual_app['base_url']}/logout")
    page.wait_for_url("**/login")
    page.locator('select[name="username"]').select_option("operator")
    page.locator('input[name="password"]').fill("OperatorPass1!")
    page.locator('button[type="submit"]').click()
    page.wait_for_url("**/app/upload")

    assert page.locator('nav[aria-label="Admin navigation"]').count() == 0
    assert page.locator('a[href^="/app/admin"]').count() == 0
    assert page.get_by_text("Signed in as operator").count() == 1
    _assert_nonblank_screenshot(page)

    admin_pages = [
        "/app/admin", "/app/admin/users", "/app/admin/pipeline", "/app/admin/tasks",
        "/app/admin/review-gate", "/app/admin/split", "/app/admin/audit",
        "/app/schemas", "/app/settings/validation",
    ]
    page_statuses = [
        page.request.get(f"{visual_app['base_url']}{path}").status for path in admin_pages
    ]
    assert page_statuses == [403] * len(admin_pages)

    admin_apis = [
        "/api/admin/users", "/api/admin/summary", "/api/admin/settings",
        "/api/admin/audit", "/api/admin/pipeline", "/api/admin/review-gate-rules",
        "/api/admin/split-settings", "/api/admin/task-catalog",
        "/api/admin/schemas/validation",
    ]
    api_statuses = [
        page.request.get(f"{visual_app['base_url']}{path}").status for path in admin_apis
    ]
    assert api_statuses == [403] * len(admin_apis)

    csrf_token = next(
        cookie.get("value")
        for cookie in page.context.cookies()
        if cookie.get("name") == "csrf_token"
    )
    assert csrf_token is not None
    mutations = [
        ("PUT", "/api/admin/users/operator/password"),
        ("PUT", "/api/admin/settings"),
        ("PUT", "/api/admin/pipeline/draft"),
        ("POST", "/api/admin/pipeline/diff"),
        ("POST", "/api/admin/pipeline/validate"),
        ("POST", "/api/admin/pipeline/publish"),
        ("PUT", "/api/admin/review-gate-rules"),
        ("PUT", "/api/admin/split-settings"),
        ("POST", "/api/admin/split-settings/test-connection"),
        ("POST", "/api/admin/schemas/validate-all"),
    ]
    mutation_statuses = [
        page.request.fetch(
            f"{visual_app['base_url']}{path}",
            method=method,
            headers={"X-CSRF-Token": csrf_token},
            data={},
        ).status
        for method, path in mutations
    ]
    assert mutation_statuses == [403] * len(mutations)
    _assert_no_horizontal_overflow(page)
