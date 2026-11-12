"""Real browser acceptance through actual local resume and registered exports."""

import csv
import json
import os
from pathlib import Path
import socket
import sys
from typing import Any, Iterator

import pytest

from test.helpers_assertions import require_present
from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader
import yaml

from modules.db.connection import managed_connect
from modules.db.repositories import DocumentRepository, TaskRunRepository
from modules.services.review_service import ReviewService
from modules.services.startup_migration_service import initialize_database
from test.helpers_business_validation_workflow import (
    create_invoice_workflow, offline_invoice_workflows, run_invoice_workflow,
)
from test.helpers_sqlite import TempConfig, initialize_test_users
from test.helpers_visual import add_business_rule, running_visual_server


@pytest.fixture
def acceptance_app(tmp_path: Path) -> Iterator[dict[str, Any]]:
    for folder in ('uploads', 'watch', 'schemas', 'processing'):
        (tmp_path / folder).mkdir()
    (tmp_path / 'app.log').touch()
    values = {
        'database': {'path': str(tmp_path / 'state.sqlite3')},
        'web': {'upload_dir': str(tmp_path / 'uploads'), 'secret_key': 'synthetic-phase5-key'},
        'watch_folder': {'dir': str(tmp_path / 'watch'), 'processing_dir': str(tmp_path / 'processing')},
        'schema': {'directories': [str(tmp_path / 'schemas')]},
        'logging': {'log_file': str(tmp_path / 'app.log')},
        'pipeline_secrets': {'synthetic-extract': 'synthetic-unused-value'},
        'ui': {'admin_enabled': True}, 'pipeline': [], 'tasks': {},
    }
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(yaml.safe_dump(values), encoding='utf-8')
    config = TempConfig(tmp_path / 'state.sqlite3', values)
    initialize_database(config)
    initialize_test_users(config)
    case = create_invoice_workflow(config, tmp_path / 'uploads', extended_rules=True)
    with offline_invoice_workflows(case['source_values']):
        paused = run_invoice_workflow(config, case)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(CONFIG_PATH=str(config_path), APP_ENV='development', ENV='development', ENVIRONMENT='development',
               DOCFLOW_STDIO_CAPTURED='1', PREFECT_LOGGING_TO_API_ENABLED='false')
    server = ('from test.helpers_business_validation_workflow import offline_invoice_workflows\n'
              'import uvicorn\nwith offline_invoice_workflows():\n'
              f"    uvicorn.run('web.server:app', host='127.0.0.1', port={port}, log_level='warning')\n")
    with running_visual_server([sys.executable, '-c', server], cwd=Path(__file__).resolve().parents[2],
                               env=env, host='127.0.0.1', port=port, log_path=tmp_path / 'server.log'):
        yield {'base': f'http://127.0.0.1:{port}', 'review': paused['review_item_id'], 'config': config, 'case': case}


def test_four_rule_templates_correct_save_accept_resume_and_export(
    acceptance_app: dict[str, Any], tmp_path: Path,
) -> None:
    app = acceptance_app
    case = app['case']
    evidence = Path(os.environ.get('R4_PHASE5_EVIDENCE_DIR', str(tmp_path / 'evidence')))
    evidence.mkdir(parents=True, exist_ok=True)
    assert 'Subtotal before discount and tax: 50.00' in PdfReader(case['source']).pages[0].extract_text()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors: list[str] = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(app['base'] + '/login')
            page.locator('input[name="password"]').fill('AdminPassword1!')
            page.get_by_role('button', name='Login', exact=True).click()
            page.wait_for_url('**/app/upload')
            page.goto(f"{app['base']}/app/review/{app['review']}")
            expect(page.locator('.docflow-pdf-page-total')).to_have_text('1', timeout=15000)
            expect(page.locator('#review-pdf-body canvas')).to_be_visible()
            summary = page.locator('#review-validation-summary')
            expect(summary).to_contain_text('4 failed')
            expect(summary).to_contain_text('1 passed')
            page.locator('#review-validation-details').evaluate('element => element.open = true')
            expect(page.locator('#review-validation-details')).to_contain_text('Date order')
            expect(page.locator('#review-validation-details')).to_contain_text('Require fields when a condition matches')
            page.screenshot(path=str(evidence / 'integrated-failures-desktop.png'))
            page.locator('#review-claim-button').click()
            page.locator('input[data-field-path="invoice_number"]').fill('INV-OK')
            page.locator('input[data-field-path="items.0.line_total"]').fill('30')
            page.locator('input[data-field-path="issued"]').fill('2026-10-01')
            page.locator('input[data-field-path="due"]').fill('2026-10-30')
            condition = page.locator('select[data-field-path="has_po"]')
            condition.select_option('false')
            with page.expect_response(lambda response: response.url.endswith('/revalidate')):
                page.get_by_role('button', name='Revalidate', exact=True).click()
            expect(summary).to_contain_text('1 not applicable')
            expect(summary).to_contain_text('4 passed')
            condition.select_option('true')
            with page.expect_response(lambda response: response.url.endswith('/complete')) as blocked:
                page.locator('#review-complete-button').click()
            assert blocked.value.status == 422
            expect(summary).to_contain_text('1 failed')
            expect(page.locator('.review-field-row[data-field-path="po_number"]')).to_contain_text('required')
            page.locator('input[data-field-path="po_number"]').fill('PO-OK')
            with page.expect_response(lambda response: response.url.endswith('/draft')):
                page.locator('#review-save-button').click()
            page.reload()
            expect(page.locator('input[data-field-path="po_number"]')).to_have_value('PO-OK')
            expect(summary).to_contain_text('5 passed')
            with page.expect_response(lambda response: response.url.endswith('/revalidate')) as checked:
                page.get_by_role('button', name='Revalidate', exact=True).click()
            assert checked.value.status == 200
            expect(page.locator('#review-validation-status')).to_have_text('Current values checked')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#review-validation-status').scroll_into_view_if_needed()
            page.screenshot(path=str(evidence / 'integrated-passing-mobile.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            with page.expect_response(lambda response: response.url.endswith('/complete')) as accepted:
                page.locator('#review-complete-button').click()
            assert accepted.value.status == 200
            # Completion redirects asynchronously after the response headers.
            page.wait_for_url('**/app/review')
            page.goto(f"{app['base']}/app/review/{app['review']}")
            expect(page.locator('#review-validation-status')).to_contain_text('Accepted')
            expect(summary).to_contain_text('5 passed')
            page.set_viewport_size({'width': 1440, 'height': 1000})
            expect(page.locator('#review-pdf-body canvas')).to_be_visible()
            page.screenshot(path=str(evidence / 'integrated-accepted-desktop.png'))
            assert not errors
        finally:
            browser.close()
    exported = json.loads((case['output'] / 'INV-OK.json').read_text(encoding='utf-8'))
    assert exported['Items'] == case['accepted_values']['items']
    assert exported['po_number'] == 'PO-OK' and exported['issued'] == '2026-10-01'
    with (case['output'] / 'INV-OK.csv').open(newline='', encoding='utf-8') as file:
        assert [row['item_line_total'] for row in csv.DictReader(file)] == ['30', '20']
    assert (case['output'] / 'INV-OK.pdf').read_bytes() == case['source'].read_bytes()
    with managed_connect(app['config']) as conn:
        assert require_present(DocumentRepository(conn).get(case['document']['id']))['status'] == 'completed'
        runs = TaskRunRepository(conn).list_by_document(case['document']['id'])
        assert [run['task_key'] for run in runs] == ['extract', 'review', 'json', 'csv', 'pdf', 'cleanup_task']
        assert all(run['status'] == 'completed' for run in runs)
        assert {run['pipeline_version_id'] for run in runs} == {case['pipeline']['id']}
        report = require_present(ReviewService(conn, app['config']).get_detail(app['review']))['metadata']['business_validation']['accepted']
        assert report['schema_version_id'] == case['schema_version']['id']
        assert len(report['checks']) == 5 and not report['has_blocking_findings']


def test_author_date_and_typed_conditional_rules_publish_and_reopen(
    acceptance_app: dict[str, Any], tmp_path: Path,
) -> None:
    app = acceptance_app
    evidence = Path(os.environ.get('R4_PHASE5_EVIDENCE_DIR', str(tmp_path / 'evidence')))
    evidence.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('dialog', lambda dialog: dialog.accept())
            page.goto(app['base'] + '/login')
            page.locator('input[name="password"]').fill('AdminPassword1!')
            page.get_by_role('button', name='Login', exact=True).click()
            page.wait_for_url('**/app/upload')
            page.goto(app['base'] + '/app/schemas')
            expect(page.locator('.business-rule-card')).to_have_count(4)
            add_business_rule(page, 'date_order:v1')
            page.get_by_label('Rule 5: Earlier date field', exact=True).select_option('/issued')
            page.get_by_label('Rule 5: Later date field', exact=True).select_option('/due')
            page.get_by_label('Rule 5: Allow same day', exact=True).uncheck()
            add_business_rule(page, 'required_if:v1')
            page.get_by_label('Rule 6: Condition field', exact=True).select_option('/has_po')
            page.get_by_label('Rule 6: Equals value', exact=True).select_option('true')
            page.get_by_label('Rule 6: Required fields', exact=True).select_option(['/po_number', '/invoice_number'])
            page.get_by_label('Rule 6: Severity', exact=True).select_option('blocking')
            with page.expect_response(lambda response: response.url.endswith('/publish')) as published:
                page.get_by_role('button', name='Publish', exact=True).click()
            assert published.value.status == 200
            page.reload()
            expect(page.get_by_label('Rule 5: Allow same day', exact=True)).not_to_be_checked()
            expect(page.get_by_label('Rule 6: Equals value', exact=True)).to_have_value('true')
            expect(page.get_by_label('Rule 6: Required fields', exact=True)).to_have_values(['/invoice_number', '/po_number'])
            endpoint = f"{app['base']}/api/admin/review-schemas/{app['case']['form']['id']}"
            persisted = page.request.get(endpoint).json()
            rules = persisted['draft']['schema']['business_validation']['rules']
            assert rules[4]['validator'] == 'date_order:v1' and rules[4]['allow_equal'] is False
            assert rules[5]['equals'] is True and rules[5]['required'] == ['/invoice_number', '/po_number']
            expect(page.locator('#schema-version-history')).to_contain_text('Version 1')
            expect(page.locator('#schema-version-history')).to_contain_text('Version 2')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('.business-rule-card').last.scroll_into_view_if_needed()
            page.screenshot(path=str(evidence / 'conditional-authoring-mobile.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        finally:
            browser.close()
