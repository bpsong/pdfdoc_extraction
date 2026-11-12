"""Real browsers author neutral rules and accept unrelated document types."""

from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import sys
import time
from typing import Any, Iterator

from playwright.sync_api import Page, expect, sync_playwright
import pytest
import yaml

from modules.db.connection import managed_connect
from modules.db.repositories import DocumentRepository, TaskRunRepository
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.startup_migration_service import initialize_database
from test.helpers_assertions import require_present
from test.helpers_business_validation_workflow import offline_invoice_workflows, run_invoice_workflow
from test.helpers_generic_business_validation import create_generic_workflow, document_scenario
from test.helpers_sqlite import TempConfig, initialize_test_users
from test.helpers_visual import add_business_rule, running_visual_server


@pytest.fixture
def generic_app(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[dict[str, Any]]:
    kind = getattr(request, 'param', 'shipping')
    scenario = document_scenario(kind)
    for name in ('uploads', 'watch', 'processing'):
        (tmp_path / name).mkdir()
    (tmp_path / 'app.log').touch()
    values = {
        'database': {'path': str(tmp_path / 'state.sqlite3')},
        'web': {'upload_dir': str(tmp_path / 'uploads'), 'secret_key': 'synthetic-generic-browser-key'},
        'watch_folder': {'dir': str(tmp_path / 'watch'), 'processing_dir': str(tmp_path / 'processing')},
        'logging': {'log_file': str(tmp_path / 'app.log')},
        'pipeline_secrets': {'synthetic-extract': 'unused-synthetic'}, 'pipeline': [], 'tasks': {},
    }
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(values), encoding='utf-8')
    config = TempConfig(tmp_path / 'state.sqlite3', values)
    initialize_database(config)
    initialize_test_users(config)
    schema = deepcopy(scenario['schema'])
    del schema['business_validation']
    with managed_connect(config) as conn:
        form = ReviewSchemaVersionService(conn).create_template(
            schema_key=f'generic-{kind}', name=f'Synthetic {kind}', initial_schema=schema, user='admin')['template']
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {**os.environ, 'CONFIG_PATH': str(path), 'APP_ENV': 'development', 'ENV': 'development',
           'ENVIRONMENT': 'development', 'DOCFLOW_STDIO_CAPTURED': '1', 'PREFECT_LOGGING_TO_API_ENABLED': 'false'}
    server = ('from test.helpers_business_validation_workflow import offline_invoice_workflows\n'
              'import uvicorn\n'
              f"with offline_invoice_workflows({scenario['source_values']!r}):\n"
              f"    uvicorn.run('web.server:app', host='127.0.0.1', port={port}, log_level='warning')\n")
    with running_visual_server([sys.executable, '-c', server], cwd=Path(__file__).resolve().parents[2],
                               env=env, host='127.0.0.1', port=port, log_path=tmp_path / 'server.log'):
        yield {'url': f'http://127.0.0.1:{port}', 'config': config, 'form': form,
               'scenario': scenario, 'kind': kind, 'directory': tmp_path / 'uploads'}


def login(page: Page, url: str, user: str) -> None:
    page.goto(url + '/login')
    page.locator('select[name="username"]').select_option(user)
    page.locator('input[name="password"]').fill('AdminPassword1!' if user == 'admin' else 'OperatorPass1!')
    page.get_by_role('button', name='Login', exact=True).click()
    page.wait_for_url('**/app/upload')


@pytest.mark.parametrize('generic_app', ['shipping', 'insurance'], indirect=True)
def test_author_publish_bind_review_and_export_generic_documents(generic_app: dict[str, Any], tmp_path: Path) -> None:
    app = generic_app
    kind = app['kind']
    evidence = Path(os.environ.get('GENERIC_RULES_EVIDENCE_DIR', str(tmp_path / 'evidence'))) / kind
    evidence.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(ignore_default_args=['--hide-scrollbars'])
        try:
            admin = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors: list[str] = []
            admin.on('pageerror', lambda error: errors.append(str(error)))
            login(admin, app['url'], 'admin')
            admin.goto(app['url'] + '/app/schemas')
            expect(admin.locator('#schema-business-catalog-status')).to_contain_text('5 reusable')
            expect(admin.get_by_role('button', name='Retry rule catalog', exact=True)).to_be_hidden()
            admin.get_by_role('button', name='Add rule', exact=True).click()
            expect(admin.locator('[data-add-business-rule]')).to_have_count(5)
            expect(admin.locator('#schema-business-picker')).to_have_css('opacity', '1')
            expect(admin.locator('#schema-business-picker .modal-box')).to_have_css('transform', 'matrix(1, 0, 0, 1, 0, 0)')
            admin.screenshot(path=str(evidence / '00-pattern-picker.png'), animations='disabled')
            admin.get_by_label('Find a rule pattern', exact=True).fill('Compare numbers')
            expect(admin.locator('[data-add-business-rule]')).to_have_count(1)
            admin.get_by_label('Find a rule pattern', exact=True).press('Tab')
            admin.keyboard.press('Enter')
            expect(admin.locator('.business-rule-card')).to_have_count(1)
            if kind == 'shipping':
                admin.get_by_label('Rule 1: Apply to', exact=True).select_option('rows')
                admin.get_by_label('Rule 1: Repeating group', exact=True).select_option('/packages')
                admin.get_by_label('Rule 1: Left value: field', exact=True).select_option('/delivered')
                admin.get_by_label('Rule 1: Compare with: field', exact=True).select_option('/ordered')
            else:
                admin.get_by_label('Rule 1: Left value: field', exact=True).select_option('/covered')
                admin.get_by_label('Rule 1: Compare with: field', exact=True).select_option('/limit')
                add_business_rule(admin, 'date_order:v1')
                admin.get_by_label('Rule 2: Earlier date field', exact=True).select_option('/effective')
                admin.get_by_label('Rule 2: Later date field', exact=True).select_option('/expiry')
                admin.get_by_label('Rule 2: Severity', exact=True).select_option('blocking')
                add_business_rule(admin, 'required_if:v1')
                admin.get_by_label('Rule 3: Condition field', exact=True).select_option('/has_endorsement')
                admin.get_by_label('Rule 3: Equals value', exact=True).select_option('true')
                admin.get_by_label('Rule 3: Required fields', exact=True).select_option(['/endorsement'])
                admin.get_by_label('Rule 3: Severity', exact=True).select_option('blocking')
            admin.get_by_label('Rule 1: Compare with: source', exact=True).select_option('constant')
            admin.get_by_label('Rule 1: Compare with: constant', exact=True).fill('5.01')
            admin.get_by_label('Rule 1: Operator', exact=True).select_option('eq')
            admin.get_by_label('Rule 1: Allowed difference', exact=True).fill('0.01')
            admin.get_by_label('Rule 1: Operator', exact=True).select_option('lte')
            expect(admin.get_by_label('Rule 1: Allowed difference', exact=True)).to_have_count(0)
            admin.get_by_label('Rule 1: Compare with: source', exact=True).select_option('field')
            admin.get_by_label('Rule 1: Compare with: field', exact=True).select_option('/ordered' if kind == 'shipping' else '/limit')
            admin.get_by_label('Rule 1: Severity', exact=True).select_option('blocking')
            assert 'invoice' not in admin.locator('.schema-business-validation').inner_text().lower()
            admin.locator('#schema-business-title').scroll_into_view_if_needed()
            admin.screenshot(path=str(evidence / '01-author-desktop.png'), animations='disabled')
            admin.set_viewport_size({'width': 390, 'height': 844})
            admin.locator('.business-rule-card').first.scroll_into_view_if_needed()
            admin.screenshot(path=str(evidence / '02-author-mobile.png'), animations='disabled')
            assert admin.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            with admin.expect_response(lambda response: response.url.endswith('/publish')) as published:
                admin.get_by_role('button', name='Publish', exact=True).click()
            assert published.value.status == 200
            version = published.value.json()['version']
            saved_schema = deepcopy(version['schema'])
            admin.reload()
            expect(admin.locator('#schema-version-history')).to_contain_text('Version 1')
            endpoint = f"{app['url']}/api/admin/review-schemas/{app['form']['id']}"
            assert admin.request.get(endpoint).json()['draft']['schema'] == saved_schema
            case = create_generic_workflow(app['config'], app['directory'], kind, schema_version=version)
            with offline_invoice_workflows(case['source_values']):
                paused = run_invoice_workflow(app['config'], case)
            assert paused['pipeline_state'] == 'paused'
            operator_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            operator = operator_context.new_page()
            operator.on('pageerror', lambda error: errors.append(str(error)))
            login(operator, app['url'], 'operator')
            assert operator.request.get(app['url'] + '/api/admin/business-validators').status == 403
            review_url = f"{app['url']}/app/review/{paused['review_item_id']}"
            operator.goto(review_url)
            expect(operator.locator('#review-pdf-body canvas')).to_be_visible()
            operator.locator('#review-claim-button').click()
            with operator.expect_response(lambda response: response.url.endswith('/complete')) as blocked:
                operator.locator('#review-complete-button').click()
            assert blocked.value.status == 422 and not case['output'].exists()
            expect(operator.locator('#review-validation-details')).to_contain_text('Compare numbers')
            expect(operator.locator('#review-complete-button')).to_be_enabled()
            operator.locator('#review-validation-details').evaluate('(element) => {element.open = true;}')
            operator.screenshot(path=str(evidence / '03-blocked-review.png'), animations='disabled')
            if kind == 'shipping':
                operator.locator('input[data-field-path="packages.0.delivered"]').fill('5')
            else:
                operator.locator('input[data-field-path="expiry"]').fill('2027-11-01')
                operator.locator('input[data-field-path="endorsement"]').fill('ENDORSEMENT-1')
            with operator.expect_response(lambda response: response.url.endswith('/revalidate')) as checked:
                operator.get_by_role('button', name='Revalidate', exact=True).click()
            assert checked.value.status == 200
            expect(operator.locator('#review-validation-summary')).to_contain_text('0 failed')
            with operator.expect_response(lambda response: response.url.endswith('/draft')):
                operator.locator('#review-save-button').click()
            operator.reload()
            expect(operator.locator('#review-validation-summary')).to_contain_text('0 failed')
            operator.set_viewport_size({'width': 390, 'height': 844})
            operator.locator('#review-validation-panel').scroll_into_view_if_needed()
            operator.screenshot(path=str(evidence / '04-passing-review-mobile.png'), animations='disabled')
            assert operator.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            with operator.expect_response(lambda response: response.url.endswith('/complete')) as accepted:
                operator.locator('#review-complete-button').click()
            assert accepted.value.status == 200
            operator.wait_for_url('**/app/review')
            operator.goto(review_url)
            expect(operator.locator('#review-validation-status')).to_contain_text('Accepted')
            expect(operator.locator('#review-pdf-body canvas')).to_be_visible()
            operator.locator('#review-validation-panel').scroll_into_view_if_needed()
            operator.screenshot(path=str(evidence / '05-accepted-review-mobile.png'), animations='disabled')
            assert not errors
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                with managed_connect(app['config']) as conn:
                    if require_present(DocumentRepository(conn).get(case['document']['id']))['status'] == 'completed':
                        break
                time.sleep(0.1)
            else:
                pytest.fail('Synthetic downstream workflow did not complete.')
            assert json.loads(next(case['output'].glob('*.json')).read_text(encoding='utf-8')) == case['accepted_values']
            with managed_connect(app['config']) as conn:
                runs = TaskRunRepository(conn).list_by_document(case['document']['id'])
                assert len([run for run in runs if run['task_key'] == 'extract']) == 1
            assert len(list(case['output'].iterdir())) == 3
            assert admin.request.get(endpoint).json()['draft']['schema'] == saved_schema
        finally:
            browser.close()


def test_catalog_failure_retry_keeps_existing_draft(generic_app: dict[str, Any]) -> None:
    app = generic_app
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            login(page, app['url'], 'admin')
            endpoint = f"{app['url']}/api/admin/review-schemas/{app['form']['id']}"
            schema = app['scenario']['schema']
            csrf = require_present(next(cookie.get('value') for cookie in page.context.cookies()
                                        if cookie.get('name') == 'csrf_token'))
            assert page.request.put(endpoint + '/draft', data={'expected_revision': 1, 'schema': schema},
                                    headers={'X-CSRF-Token': csrf}).status == 200
            before = page.request.get(endpoint).json()['draft']
            page.route('**/api/admin/business-validators', lambda route: route.fulfill(status=503, json={'detail': 'Synthetic unavailable'}))
            page.goto(app['url'] + '/app/schemas')
            expect(page.get_by_role('button', name='Add rule', exact=True)).to_be_disabled()
            expect(page.locator('#schema-business-catalog-status')).to_contain_text('Existing configuration is retained')
            expect(page.locator('.business-rule-card')).to_have_count(len(schema['business_validation']['rules']))
            page.unroute('**/api/admin/business-validators')
            page.get_by_role('button', name='Retry rule catalog', exact=True).click()
            expect(page.get_by_role('button', name='Add rule', exact=True)).to_be_enabled()
            expect(page.get_by_role('button', name='Retry rule catalog', exact=True)).to_be_hidden()
            expect(page.get_by_label('Rule 1: Operator', exact=True)).to_have_value('lte')
            after = page.request.get(endpoint).json()['draft']
            assert before['schema'] == after['schema'] and before['content_hash'] == after['content_hash']
            expect(page.locator('#schema-detail-title')).not_to_contain_text('* ')
        finally:
            browser.close()


def test_no_rules_author_publish_review_draft_and_export_without_catalog(
    generic_app: dict[str, Any], tmp_path: Path,
) -> None:
    app = generic_app
    evidence = Path(os.environ.get('GENERIC_RULES_EVIDENCE_DIR', str(tmp_path / 'evidence'))) / 'no-rules'
    evidence.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(ignore_default_args=['--hide-scrollbars'])
        try:
            admin = browser.new_page()
            login(admin, app['url'], 'admin')
            admin.route('**/api/admin/business-validators', lambda route: route.fulfill(status=503, json={'detail': 'Unavailable'}))
            admin.goto(app['url'] + '/app/schemas')
            expect(admin.locator('#schema-business-catalog-status')).to_contain_text('could not be loaded')
            expect(admin.locator('.business-rule-card')).to_have_count(0)
            expect(admin.locator('#schema-business-rules')).to_contain_text('No business rules configured')
            with admin.expect_response(lambda response: response.url.endswith('/publish')) as published:
                admin.get_by_role('button', name='Publish', exact=True).click()
            assert published.value.status == 200
            version = published.value.json()['version']
            assert version['format_version'] == 1 and 'business_validation' not in version['schema']
            case = create_generic_workflow(app['config'], app['directory'], 'shipping', schema_version=version)
            with offline_invoice_workflows(case['source_values']):
                paused = run_invoice_workflow(app['config'], case)
            assert paused['pipeline_state'] == 'paused'
            operator_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            operator = operator_context.new_page()
            errors: list[str] = []
            catalog_requests: list[str] = []
            operator.on('pageerror', lambda error: errors.append(str(error)))
            operator.on('request', lambda request: catalog_requests.append(request.url)
                        if request.url.endswith('/api/admin/business-validators') else None)
            login(operator, app['url'], 'operator')
            review_endpoint = f"{app['url']}/api/review/items/{paused['review_item_id']}"
            review_url = f"{app['url']}/app/review/{paused['review_item_id']}"
            operator.goto(review_url)
            expect(operator.locator('#review-pdf-body canvas')).to_be_visible()
            expect(operator.locator('#review-validation-panel')).to_be_hidden()
            expect(operator.locator('#review-revalidate-button')).to_be_hidden()
            operator.locator('#review-claim-button').click()
            expect(operator.locator('input[data-field-path="reference"]')).to_be_enabled()
            csrf = require_present(next(cookie.get('value') for cookie in operator.context.cookies()
                                        if cookie.get('name') == 'csrf_token'))
            rejected = operator.request.post(review_endpoint + '/complete',
                data={'corrections': {'reference': ''}}, headers={'X-CSRF-Token': csrf})
            assert rejected.status == 409 and 'schema validation' in rejected.json()['detail']
            assert not case['output'].exists()
            operator.locator('input[data-field-path="packages.0.delivered"]').fill('5')
            with operator.expect_response(lambda response: response.url.endswith('/draft')) as saved:
                operator.locator('#review-save-button').click()
            assert saved.value.status == 200
            operator.reload()
            expect(operator.locator('input[data-field-path="packages.0.delivered"]')).to_have_value('5')
            expect(operator.locator('#review-validation-panel')).to_be_hidden()
            operator.screenshot(path=str(evidence / '01-review-desktop.png'), animations='disabled')
            operator.set_viewport_size({'width': 390, 'height': 844})
            operator.locator('input[data-field-path="reference"]').scroll_into_view_if_needed()
            operator.screenshot(path=str(evidence / '02-review-mobile.png'), animations='disabled')
            assert operator.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            with operator.expect_response(lambda response: response.url.endswith('/complete')) as completed:
                operator.locator('#review-complete-button').click()
            assert completed.value.status == 200
            operator.wait_for_url('**/app/review')
            assert operator.request.get(review_endpoint).json()['business_validation'] is None
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                with managed_connect(app['config']) as conn:
                    if require_present(DocumentRepository(conn).get(case['document']['id']))['status'] == 'completed':
                        break
                time.sleep(0.1)
            else:
                pytest.fail('No-rules downstream workflow did not complete.')
            assert json.loads(next(case['output'].glob('*.json')).read_text(encoding='utf-8')) == case['accepted_values']
            assert len(list(case['output'].iterdir())) == 3
            assert not errors and not catalog_requests
        finally:
            browser.close()
