from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
import bcrypt

from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import (
    DocumentRepository,
    ExtractionRepository,
    ReviewRepository,
    TaskRunRepository,
    UserRepository,
)
from modules.services.batch_service import BatchService
from modules.services.ingress_binding_service import IngressBindingService
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from test.helpers_sqlite import TempConfig


pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, sync_playwright


PASSWORD_HASH = "$2b$12$uG.SmnQ76mGiPy0wyztZkO4e/hoV3lo/3J8PEXITLC9ckfF3B3qAm"
PHASE14_SECRET_SENTINEL = "PHASE14_SYNTHETIC_SECRET_MUST_NOT_RENDER"
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "output" / "playwright" / "phase14"


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
        "pipeline_secrets": {"phase14-provider": PHASE14_SECRET_SENTINEL},
        "tasks": {},
        "pipeline": [],
    }
    (tmp_path / "watch").mkdir()
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def _phase14_pipeline_definition(
    schema_version_id: str, tmp_path: Path
) -> dict[str, Any]:
    """Return a long synthetic pipeline with an exact review-schema dependency."""
    fields = {
        "supplier": {"alias": "Supplier", "type": "str"},
        "invoice_amount": {"alias": "Invoice amount", "type": "float"},
        "approved": {"alias": "Approved", "type": "bool"},
        "reviewed_at": {"alias": "Reviewed at", "type": "str"},
        "address": {"alias": "Address", "type": "Any"},
        "tags": {"alias": "Tags", "type": "List[str]"},
        "line_items": {
            "alias": "Line items",
            "type": "List[Any]",
            "item_fields": {
                "sku": {"alias": "SKU", "type": "str"},
                "quantity": {"alias": "Quantity", "type": "int"},
                "unit_price": {"alias": "Unit price", "type": "float"},
            },
        },
    }
    return {
        "schema_version": 1,
        "pipeline": [
            "split_documents",
            "extract_invoice_fields",
            "review_low_confidence_fields",
            "store_structured_metadata",
        ],
        "tasks": {
            "split_documents": {
                "label": "Split multi-document package into synthetic child documents",
                "module": "standard_step.split.llamacloud_split",
                "class": "LlamaCloudSplitTask",
                "params": {
                    "enabled": True,
                    "api_key": {"$secret": "phase14-provider"},
                    "categories": [{"name": "invoice"}, {"name": "receipt"}],
                    "split_dir": str(tmp_path / "synthetic_split"),
                },
            },
            "extract_invoice_fields": {
                "label": "Extract every configured invoice field with confidence",
                "module": "standard_step.extraction.extract_pdf",
                "class": "ExtractPdfTask",
                "params": {
                    "api_key": {"$secret": "phase14-provider"},
                    "fields": fields,
                },
            },
            "review_low_confidence_fields": {
                "label": "Review low-confidence fields using the exact published form",
                "module": "standard_step.review.review_gate",
                "class": "ReviewGateTask",
                "params": {
                    "confidence_threshold": 0.9,
                    "review_scope": "low_confidence_fields",
                    "schema_version_id": schema_version_id,
                },
            },
            "store_structured_metadata": {
                "label": "Store approved structured metadata as JSON",
                "module": "standard_step.storage.store_metadata_as_json",
                "class": "StoreMetadataAsJson",
                "params": {
                    "data_dir": str(tmp_path / "synthetic_output"),
                    "filename": "{supplier}",
                },
                "on_error": "continue",
            },
        },
    }


def _seed_visual_state(
    tmp_path: Path, config_path: Path, schema_dir: Path
) -> dict[str, str]:
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
        {
            "schema": {"directories": [str(schema_dir)]},
            "database": {"path": str(tmp_path / "app_state.sqlite3")},
            "pipeline_secrets": {
                "phase14-provider": PHASE14_SECRET_SENTINEL
            },
        },
    )
    config._config_path = config_path
    initialize_database(config)
    with connect(config) as conn:
        UserRepository(conn).initialize({"admin": PASSWORD_HASH, "operator": bcrypt.hashpw(b"OperatorPass1!", bcrypt.gensalt()).decode()})
        schema = yaml.safe_load((schema_dir / "invoice.yaml").read_text(encoding="utf-8"))
        versioned_schemas = ReviewSchemaVersionService(conn)
        created_schema = versioned_schemas.create_template(
            schema_key="invoice",
            name="Visual Invoice",
            description="Visual test schema",
            initial_schema=schema,
            user="admin",
        )
        first_schema = versioned_schemas.publish(
            created_schema["template"]["id"],
            expected_revision=1,
            user="admin",
        )
        versioned_schemas.update_template(
            created_schema["template"]["id"], status="active", user="admin"
        )
        schema_v2 = dict(schema)
        schema_v2["description"] = (
            "Synthetic multi-version review form with long labels and nested fields."
        )
        saved_schema = versioned_schemas.save_draft(
            created_schema["template"]["id"],
            expected_revision=first_schema["draft"]["revision"],
            schema=schema_v2,
            user="admin",
        )
        published_schema = versioned_schemas.publish(
            created_schema["template"]["id"],
            expected_revision=saved_schema["revision"],
            user="admin",
        )

        pipelines = PipelineTemplateService(
            conn, configured_secret_aliases={"phase14-provider"}
        )
        definition = _phase14_pipeline_definition(
            published_schema["version"]["id"], tmp_path
        )
        active = pipelines.create_template(
            template_key="phase14-long-invoice-processing",
            name="Phase 14 Long Invoice Processing Pipeline",
            description="Synthetic active multi-version pipeline for visual testing.",
            document_type="invoice",
            operator_instructions="Choose this exact version for synthetic invoices.",
            operator_selectable=True,
            initial_definition=definition,
            user="admin",
        )
        first_pipeline = pipelines.publish(
            active["template"]["id"], expected_revision=1, user="admin"
        )
        changed_definition = dict(definition)
        changed_definition["tasks"] = dict(definition["tasks"])
        changed_definition["tasks"]["store_structured_metadata"] = {
            **changed_definition["tasks"]["store_structured_metadata"],
            "label": "Store approved structured metadata as JSON (version two)",
        }
        saved_pipeline = pipelines.save_draft(
            active["template"]["id"],
            expected_revision=first_pipeline["draft"]["revision"],
            definition=changed_definition,
            user="admin",
        )
        published_pipeline = pipelines.publish(
            active["template"]["id"],
            expected_revision=saved_pipeline["revision"],
            user="admin",
        )
        pipelines.update_template(
            active["template"]["id"], status="active", user="admin"
        )

        inactive = pipelines.create_template(
            template_key="phase14-inactive-draft",
            name="Phase 14 Inactive Validation Draft",
            description="Synthetic inactive draft used for empty and validation states.",
            initial_definition={
                **definition,
                "tasks": {
                    **definition["tasks"],
                    "extract_invoice_fields": {
                        **definition["tasks"]["extract_invoice_fields"],
                        "params": {
                            **definition["tasks"]["extract_invoice_fields"]["params"],
                            "api_key": {"$secret": "missing-synthetic-alias"},
                        },
                    },
                },
            },
            user="admin",
        )
        inactive_published = pipelines.clone(
            active["template"]["id"],
            template_key="phase14-inactive-published",
            name="Phase 14 Inactive Published Pipeline",
            user="admin",
        )
        pipelines.publish(
            inactive_published["template"]["id"],
            expected_revision=1,
            user="admin",
        )
        archived = pipelines.clone(
            active["template"]["id"],
            template_key="phase14-archived-copy",
            name="Phase 14 Archived Copy",
            user="admin",
        )
        archived_published = pipelines.publish(
            archived["template"]["id"], expected_revision=1, user="admin"
        )
        pipelines.update_template(
            archived["template"]["id"], status="archived", user="admin"
        )

        incoming = tmp_path / "synthetic_incoming"
        incoming.mkdir()
        IngressBindingService(conn, config).create(
            folder_path=str(incoming),
            pipeline_version_id=published_pipeline["version"]["id"],
            enabled=True,
            user="admin",
        )
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
    source_pdf = tmp_path / "web_upload" / "phase14-source-package.pdf"
    child_review_pdf = tmp_path / "web_upload" / "phase14-child-review.pdf"
    child_failed_pdf = tmp_path / "web_upload" / "phase14-child-failed.pdf"
    for path in (source_pdf, child_review_pdf, child_failed_pdf):
        path.write_bytes(b"%PDF-1.4\n% synthetic phase 14 evidence")

    with connect(config) as conn:
        pipeline_template_id = active["template"]["id"]
        pipeline_version_id = published_pipeline["version"]["id"]
        batch = BatchService(conn).create_ingestion_batch(
            source="visual",
            file_path=str(source_pdf),
            original_filename=(
                "phase14-source-package-with-a-deliberately-long-filename.pdf"
            ),
            pipeline_template_id=pipeline_template_id,
            pipeline_version_id=pipeline_version_id,
            pipeline_assignment_source="upload",
        )
        documents = DocumentRepository(conn)
        source_id = batch["document"]["id"]
        documents.update_status(source_id, "split_completed")
        review_child = documents.create_child(
            batch_id=batch["batch"]["id"],
            parent_document_id=source_id,
            file_path=str(child_review_pdf),
            original_filename="phase14-child-requires-review.pdf",
            page_start=1,
            page_end=2,
            split_category="invoice",
            split_confidence="medium",
            status="review_required",
            pipeline_template_id=pipeline_template_id,
            pipeline_version_id=pipeline_version_id,
        )
        failed_child = documents.create_child(
            batch_id=batch["batch"]["id"],
            parent_document_id=source_id,
            file_path=str(child_failed_pdf),
            original_filename="phase14-child-failed.pdf",
            page_start=3,
            page_end=4,
            split_category="receipt",
            split_confidence="low",
            status="failed",
            pipeline_template_id=pipeline_template_id,
            pipeline_version_id=pipeline_version_id,
        )
        runs = TaskRunRepository(conn)
        split_run = runs.create_started(
            batch_id=batch["batch"]["id"],
            document_id=source_id,
            task_key="split_documents",
            task_index=0,
            module_name="standard_step.split.llamacloud_split",
            class_name="LlamaCloudSplitTask",
            pipeline_version_id=pipeline_version_id,
        )
        runs.mark_completed(split_run["id"])
        review_run = runs.create_started(
            batch_id=batch["batch"]["id"],
            document_id=review_child["id"],
            task_key="review_low_confidence_fields",
            task_index=2,
            module_name="standard_step.review.review_gate",
            class_name="ReviewGateTask",
            pipeline_version_id=pipeline_version_id,
        )
        runs.mark_paused(review_run["id"])
        failed_run = runs.create_started(
            batch_id=batch["batch"]["id"],
            document_id=failed_child["id"],
            task_key="extract_invoice_fields",
            task_index=1,
            module_name="standard_step.extraction.extract_pdf",
            class_name="ExtractPdfTask",
            pipeline_version_id=pipeline_version_id,
        )
        runs.mark_failed(failed_run["id"], "Synthetic phase 14 provider failure")

    return {
        "review_id": str(review["id"]),
        "batch_id": str(batch["batch"]["id"]),
        "active_template_id": str(active["template"]["id"]),
        "pipeline_version_id": str(published_pipeline["version"]["id"]),
        "inactive_template_id": str(inactive["template"]["id"]),
        "inactive_published_template_id": str(inactive_published["template"]["id"]),
        "archived_version_id": str(archived_published["version"]["id"]),
    }


@pytest.fixture(scope="module")
def visual_app(tmp_path_factory: pytest.TempPathFactory):
    tmp_path = tmp_path_factory.mktemp("visual_app")
    port = _free_port()
    schema_dir = tmp_path / "schemas"
    config_path = _write_config(tmp_path, port, schema_dir)
    state = _seed_visual_state(tmp_path, config_path, schema_dir)
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

    yield {"base_url": base_url, **state}

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


def _open_schema_field(page: Page, path: str) -> None:
    """Open one compact schema field editor before exercising its controls."""
    page.locator(
        f'[data-row-path="{path}"] > .schema-field-details > summary'
    ).locator("xpath=ancestor::details").evaluate_all(
        "nodes => nodes.forEach(node => { node.open = true; })"
    )


def _computed_style(page: Page, selector: str, properties: list[str]) -> dict[str, str]:
    return page.locator(selector).first.evaluate(
        """(node, names) => {
            const style = getComputedStyle(node);
            return Object.fromEntries(names.map(name => [name, style[name]]));
        }""",
        properties,
    )


def _capture_phase14(page: Page, name: str) -> Path:
    """Save synthetic evidence and reject blank or secret-bearing captures."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / f"{name}.png"
    screenshot = page.screenshot(path=str(target), full_page=True)
    assert len(screenshot) > 10_000
    assert PHASE14_SECRET_SENTINEL not in page.content()
    return target


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


def test_phase14_review_form_history_validation_and_responsive_evidence(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Capture versioned review-form administration with safe synthetic data."""
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto(f"{visual_app['base_url']}/app/schemas/invoice.yaml")
    page.locator("#schema-field-tree .schema-field-row").first.wait_for()
    assert page.locator("#schema-version-history").get_by_text("Version 2").count() == 1
    page.locator('[data-field-prop="array_item_type"]').first.locator(
        "xpath=ancestor::details[1]/summary"
    ).click()
    assert page.locator('[data-field-prop="array_item_type"]').first.is_visible()
    assert page.locator("#schema-field-outline [data-outline-path]").count() >= 7
    _capture_phase14(page, "01-review-form-desktop")
    _assert_no_horizontal_overflow(page)

    maximum_length = page.locator(
        '[data-field-path="supplier"][data-field-prop="max_length"]'
    )
    _open_schema_field(page, "supplier")
    maximum_length.fill("1")
    maximum_length.press("Tab")
    assert page.get_by_text(
        "Min length cannot be greater than max length."
    ).count() >= 1
    assert page.locator("#schema-validation-results").get_attribute("aria-live") in {
        "polite",
        None,
    }
    _capture_phase14(page, "02-review-form-validation-error")

    page.set_viewport_size({"width": 390, "height": 900})
    page.locator("#schema-field-tree").wait_for()
    _capture_phase14(page, "03-review-form-mobile")
    _assert_no_horizontal_overflow(page)


def test_phase14_pipeline_admin_versioning_diff_bindings_and_errors(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Capture the multi-template pipeline workspace and defensive states."""
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto(f"{visual_app['base_url']}/app/admin/pipeline")
    page.wait_for_function(
        "() => document.querySelectorAll('#pipeline-template-select option').length >= 4"
    )
    assert page.locator("#pipeline-template-select option").count() >= 4
    page.locator("#pipeline-template-select").select_option(
        visual_app["active_template_id"]
    )
    page.wait_for_function(
        "() => document.querySelector('#pipeline-version-history')?.textContent.includes('2 immutable')"
    )
    page.locator("#pipeline-draft-list .pipeline-step-main").first.wait_for()
    assert page.locator("#pipeline-draft-list .pipeline-step-main").count() == 4
    assert "2 immutable version" in (
        page.locator("#pipeline-version-history").text_content() or ""
    )
    assert page.locator("#pipeline-binding-list").get_by_text(
        "Phase 14 Long Invoice Processing Pipeline"
    ).count() >= 1

    page.locator("#pipeline-draft-list .pipeline-step-main").nth(2).click()
    exact_schema = page.get_by_label("Published review form version")
    exact_schema.wait_for()
    assert exact_schema.input_value()
    page.locator("#pipeline-diff-button").click()
    page.locator("#pipeline-diff-preview").get_by_text("No changes").wait_for()
    _capture_phase14(page, "04-pipeline-admin-desktop")
    _assert_no_horizontal_overflow(page)

    page.set_viewport_size({"width": 1024, "height": 768})
    _capture_phase14(page, "05-pipeline-admin-tablet")
    _assert_no_horizontal_overflow(page)

    page.set_viewport_size({"width": 390, "height": 900})
    _capture_phase14(page, "06-pipeline-admin-mobile")
    _assert_no_horizontal_overflow(page)

    page.evaluate(
        """() => {
            const target = document.querySelector('#pipeline-validation-results');
            target.innerHTML = '<div class="alert alert-error" role="alert">Synthetic server error</div>';
        }"""
    )
    page.get_by_text("Synthetic server error").wait_for()
    _capture_phase14(page, "07-pipeline-admin-server-error")


def test_pipeline_binding_controls_explain_lifecycle_requirements(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Disable bindings until the selected pipeline is published and active."""
    page.goto(f"{visual_app['base_url']}/app/admin/pipeline")
    page.wait_for_function(
        "() => document.querySelectorAll('#pipeline-template-select option').length >= 4"
    )

    page.locator("#pipeline-template-select").select_option(
        visual_app["inactive_template_id"]
    )
    page.get_by_text(
        "To add a watch-folder binding, publish a version first, then activate this pipeline."
    ).wait_for()
    assert page.locator("#pipeline-binding-path").is_disabled()
    assert page.locator("#pipeline-binding-version").is_disabled()
    assert page.locator("#pipeline-binding-add").is_disabled()

    page.locator("#pipeline-template-select").select_option(
        visual_app["inactive_published_template_id"]
    )
    page.get_by_text(
        "To add a watch-folder binding, activate this pipeline first."
    ).wait_for()
    assert page.locator("#pipeline-binding-path").is_disabled()
    assert page.locator("#pipeline-binding-version").is_disabled()
    assert page.locator("#pipeline-binding-add").is_disabled()

    page.locator("#pipeline-template-select").select_option(
        visual_app["active_template_id"]
    )
    page.wait_for_function(
        "() => document.querySelector('#pipeline-binding-version option')?.value === '' && document.querySelectorAll('#pipeline-binding-version option').length > 1"
    )
    assert not page.locator("#pipeline-binding-path").is_disabled()
    assert not page.locator("#pipeline-binding-version").is_disabled()
    assert not page.locator("#pipeline-binding-add").is_disabled()


def test_phase14_upload_selection_validation_and_success(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Verify explicit version selection, file eligibility, and success routing."""
    page.set_viewport_size({"width": 1366, "height": 900})
    page.goto(f"{visual_app['base_url']}/app/upload")
    page.locator('input[name="pipeline-version"]').first.wait_for()
    assert page.locator('input[name="pipeline-version"]:checked').count() == 0
    assert page.locator("#start-processing-button").is_disabled()

    page.locator("#pdf-file-input").set_input_files(
        {
            "name": "unsafe.txt",
            "mimeType": "text/plain",
            "buffer": b"synthetic invalid file",
        }
    )
    assert page.get_by_text("Only PDF files are accepted").count() >= 1
    _capture_phase14(page, "08-upload-invalid-file")
    page.get_by_role("button", name="Remove unsafe.txt").click()

    page.locator("#pdf-file-input").set_input_files(
        {
            "name": "phase14-synthetic-upload.pdf",
            "mimeType": "application/pdf",
            "buffer": b"%PDF-1.4\n% synthetic upload",
        }
    )
    page.locator('input[name="pipeline-version"]').first.check()
    assert page.locator("#start-processing-button").is_enabled()
    _capture_phase14(page, "09-upload-ready")

    page.route(
        "**/api/batches/upload",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=(
                '{"status":"queued","batch_id":"'
                + visual_app["batch_id"]
                + '","document_ids":[]}'
            ),
        ),
    )
    page.locator("#start-processing-button").click()
    page.wait_for_url(f"**/app/batches/{visual_app['batch_id']}")
    page.locator("#pipeline-assignment-summary strong").wait_for()


def test_phase14_processing_identity_split_failure_review_and_reflow(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Capture exact identity and mixed split-child processing states."""
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto(f"{visual_app['base_url']}/app/batches/{visual_app['batch_id']}")
    page.locator("#pipeline-assignment-summary strong").wait_for()
    assert "Phase 14 Long Invoice Processing Pipeline" in (
        page.locator("#pipeline-assignment-summary").text_content() or ""
    )
    assert page.locator("#pipeline-step-list [data-step]").count() >= 5
    assert page.get_by_text("Review Required").count() >= 1
    assert page.get_by_text("Failed", exact=True).count() >= 1
    assert page.locator("#split-results-link").is_visible()
    _capture_phase14(page, "10-processing-mixed-states-desktop")
    _assert_no_horizontal_overflow(page)

    page.set_viewport_size({"width": 1024, "height": 768})
    _capture_phase14(page, "11-processing-mixed-states-tablet")

    page.set_viewport_size({"width": 390, "height": 900})
    _capture_phase14(page, "12-processing-mixed-states-mobile")
    assert page.locator(".overflow-x-auto").count() >= 1


def test_phase14_keyboard_focus_reduced_motion_and_secret_presentation(
    page: Page, visual_app: dict[str, str]
) -> None:
    """Exercise keyboard focus and scan operator surfaces for secret leakage."""
    page.emulate_media(reduced_motion="reduce")
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{visual_app['base_url']}/app/upload")
    page.locator("#pipeline-version-list").wait_for()
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    focused = page.locator(":focus")
    assert focused.count() == 1
    assert focused.evaluate(
        "node => { const s = getComputedStyle(node); return s.outlineStyle !== 'none' || s.boxShadow !== 'none'; }"
    )
    assert page.locator("main").count() == 1
    assert page.locator("h1, h2").count() >= 1
    assert page.locator('[role="radiogroup"][aria-label]').count() == 1
    assert PHASE14_SECRET_SENTINEL not in page.content()
    assert "missing-synthetic-alias" not in page.content()
    _capture_phase14(page, "13-accessibility-keyboard-mobile")


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
    page.locator(".schema-field-details").evaluate_all(
        "nodes => nodes.forEach(node => { node.open = true; })"
    )
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


def test_pipeline_and_schema_field_edits_keep_focus_after_render(
    page: Page, visual_app: dict[str, str]
) -> None:
    page.goto(f"{visual_app['base_url']}/app/admin/pipeline")
    page.wait_for_function(
        "() => document.querySelectorAll('#pipeline-template-select option').length >= 4"
    )
    page.locator("#pipeline-template-select").select_option(
        visual_app["active_template_id"]
    )
    page.wait_for_function(
        "() => document.querySelector('#pipeline-version-history')?.textContent.includes('2 immutable')"
    )
    page.locator("#pipeline-draft-list .pipeline-step-main").nth(1).click()

    field_type = page.locator(
        '[data-param-action="field-type"][data-field-key="supplier"]'
    )
    field_type.locator("xpath=ancestor::details[1]").evaluate("node => { node.open = true; }")
    field_type.wait_for()
    field_type.focus()
    field_type.select_option("int")
    assert field_type.evaluate("node => document.activeElement === node")

    page.locator('[data-param-action="field-type"][data-field-key="supplier"]').locator(
        "xpath=ancestor::details[1]"
    ).evaluate("node => { node.open = true; }")
    alias = page.get_by_label("Alias for supplier")
    alias.focus()
    alias.fill("Supplier legal name")
    alias.evaluate("node => node.setSelectionRange(8, 8)")
    alias.dispatch_event("change")
    assert alias.evaluate("node => document.activeElement === node")
    assert alias.evaluate("node => node.selectionStart") == 8

    page.locator('[data-param-action="rename-extract-field"][data-field-key="supplier"]').locator(
        "xpath=ancestor::details[1]"
    ).evaluate("node => { node.open = true; }")
    field_key = page.locator(
        '[data-param-action="rename-extract-field"][data-field-key="supplier"]'
    )
    field_key.focus()
    field_key.fill("supplier_code")
    field_key.dispatch_event("change")
    renamed_field_key = page.locator(
        '[data-param-action="rename-extract-field"][data-field-key="supplier_code"]'
    )
    assert renamed_field_key.evaluate("node => document.activeElement === node")

    page.goto(f"{visual_app['base_url']}/app/schemas/invoice.yaml")
    page.locator("#schema-field-tree .schema-field-row").first.wait_for()
    _open_schema_field(page, "supplier")
    schema_key = page.locator(
        '[data-field-path="supplier"][data-field-prop="key"]'
    )
    schema_key.focus()
    schema_key.fill("supplier_name")
    schema_key.dispatch_event("change")
    renamed_schema_key = page.locator(
        '[data-field-path="supplier_name"][data-field-prop="key"]'
    )
    assert renamed_schema_key.evaluate("node => document.activeElement === node")

    _open_schema_field(page, "supplier_name")
    help_input = page.locator(
        '[data-field-path="supplier_name"][data-field-prop="help"]'
    )
    help_input.focus()
    help_input.fill("Use the registered supplier name")
    help_input.evaluate("node => node.setSelectionRange(12, 12)")
    help_input.dispatch_event("change")
    assert help_input.evaluate("node => document.activeElement === node")
    assert help_input.evaluate("node => node.selectionStart") == 12


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
    assert page.locator(".pipeline-config-workspace > .admin-panel").count() == 9
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

    assert top_level_paths()[:2] == ["address", "approved"]
    assert page.locator('[data-move-field="address"][data-move-direction="up"]').is_disabled()
    assert page.locator('[data-move-field="tags"][data-move-direction="down"]').is_disabled()
    delete_supplier = page.locator('[data-delete-field="supplier"]')
    assert delete_supplier.text_content() == "Delete field"
    assert "btn-error" in (delete_supplier.get_attribute("class") or "")

    _open_schema_field(page, "address")
    page.locator('[data-move-field="address"][data-move-direction="down"]').click()
    assert top_level_paths()[:2] == ["approved", "address"]
    page.locator("#schema-field-status").wait_for()
    assert page.locator("#schema-field-status").text_content() == "Moved Address down."
    assert page.evaluate("document.activeElement?.dataset.moveField") == "address"
    assert page.evaluate("document.activeElement?.dataset.moveDirection") == "down"
    outline_paths = page.locator("#schema-field-outline [data-outline-path]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.outlinePath)"
    )
    assert outline_paths[:2] == ["approved", "address"]
    preview = page.locator("#schema-yaml-preview").text_content() or ""
    assert preview.index("approved:") < preview.index("address:")

    _open_schema_field(page, "address")
    page.locator('[data-move-field="address"][data-move-direction="up"]').click()
    assert top_level_paths()[:2] == ["address", "approved"]
    assert page.evaluate("document.activeElement?.dataset.moveField") == "address"
    assert page.evaluate("document.activeElement?.dataset.moveDirection") == "down"

    _open_schema_field(page, "line_items.sku")
    page.locator('[data-move-field="line_items.sku"][data-move-direction="up"]').click()
    nested_paths = page.locator(
        '[data-row-path="line_items"] .schema-field-children > .schema-field-row'
    ).evaluate_all("nodes => nodes.map(node => node.dataset.rowPath)")
    assert nested_paths[:2] == ["line_items.sku", "line_items.quantity"]
    assert "line_items" in top_level_paths()
    assert page.evaluate("document.activeElement?.dataset.moveField") == "line_items.sku"
    assert page.evaluate("document.activeElement?.dataset.moveDirection") == "down"

    dialog_messages: list[str] = []

    def dismiss_delete(dialog) -> None:
        dialog_messages.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", dismiss_delete)
    _open_schema_field(page, "approved")
    page.locator('[data-delete-field="approved"]').click()
    assert page.locator('[data-row-path="approved"]').count() == 1
    assert dialog_messages == [
        'Delete field "Approved" from this schema draft?\n\n'
        "The field will be permanently removed when you save the schema."
    ]

    page.once("dialog", lambda dialog: dialog.accept())
    _open_schema_field(page, "approved")
    page.locator('[data-delete-field="approved"]').click()
    assert page.locator('[data-row-path="approved"]').count() == 0
    page.locator("#schema-field-status").wait_for()
    assert page.locator("#schema-field-status").text_content() == "Deleted Approved from the schema draft."
    assert page.evaluate("document.activeElement?.dataset.fieldPath") == "invoice_amount"
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
