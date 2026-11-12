"""Phase 4 production UI acceptance using synthetic local state and providers."""

import os
from pathlib import Path
import socket
import sys
from typing import Any, Iterator

import pytest

from test.helpers_assertions import require_present
from playwright.sync_api import Page, Route, expect, sync_playwright
import yaml

from modules.services.startup_migration_service import initialize_database
from test.helpers_business_validation import invoice_review_schema, seed_business_review
from test.helpers_sqlite import TempConfig, initialize_test_users
from test.helpers_visual import running_visual_server


@pytest.fixture
def validation_app(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[dict[str, Any]]:
    for folder in ('uploads', 'watch', 'schemas', 'processing'):
        (tmp_path / folder).mkdir()
    (tmp_path / 'app.log').touch()
    values = {
        'database': {'path': str(tmp_path / 'state.sqlite3')},
        'web': {'upload_dir': str(tmp_path / 'uploads'), 'secret_key': 'synthetic-phase4-key'},
        'watch_folder': {'dir': str(tmp_path / 'watch'), 'processing_dir': str(tmp_path / 'processing')},
        'schema': {'directories': [str(tmp_path / 'schemas')]},
        'logging': {'log_file': str(tmp_path / 'app.log')},
        'ui': {'admin_enabled': True}, 'pipeline': [], 'tasks': {},
    }
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(yaml.safe_dump(values), encoding='utf-8')
    config = TempConfig(tmp_path / 'state.sqlite3', values)
    initialize_database(config)
    initialize_test_users(config)
    schema = invoice_review_schema()
    mode = getattr(request, 'param', 'rules')
    extracted: dict[str, Any] = {'items': [{'quantity': 3, 'unit_price': 10, 'line_total': 300}], 'subtotal': 30}
    if mode == 'plain':
        del schema['business_validation']
    elif mode == 'nested':
        schema['fields']['totals'] = {'type': 'object', 'properties': {'subtotal': schema['fields'].pop('subtotal')}}
        schema['business_validation']['rules'][1]['target'] = '/totals/subtotal'
        extracted['totals'] = {'subtotal': extracted.pop('subtotal')}
    elif mode == 'missing':
        extracted['items'] = None
    seeded = seed_business_review(config, tmp_path / 'uploads', schema=schema, values=extracted)
    seeded['task'].always_review = True
    seeded['task'].run(seeded['context'])
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(CONFIG_PATH=str(config_path), APP_ENV='development', ENV='development', ENVIRONMENT='development',
               DOCFLOW_STDIO_CAPTURED='1', PREFECT_LOGGING_TO_API_ENABLED='false')
    server = ('from modules.resume_manager import ResumeManager; '
              'ResumeManager.resume_document = lambda *args, **kwargs: False; '
              f"import uvicorn; uvicorn.run('web.server:app', host='127.0.0.1', port={port}, log_level='warning')")
    with running_visual_server([sys.executable, '-c', server], cwd=Path(__file__).resolve().parents[2],
                               env=env, host='127.0.0.1', port=port, log_path=tmp_path / 'server.log'):
        yield {'base': f'http://127.0.0.1:{port}', 'review': seeded['context']['review_item_id'], 'config': config, 'mode': mode}


def login_review(page: Page, app: dict[str, Any], *, operator: bool = False) -> None:
    page.goto(app['base'] + '/login')
    if operator:
        page.locator('select[name="username"]').select_option('operator')
    page.locator('input[name="password"]').fill('OperatorPass1!' if operator else 'AdminPassword1!')
    page.get_by_role('button', name='Login', exact=True).click()
    page.wait_for_url('**/app/upload')
    page.goto(f"{app['base']}/app/review/{app['review']}")
    expect(page.locator('#review-document-title')).to_have_text('synthetic-invoice.pdf')


@pytest.mark.parametrize('validation_app', ['rules', 'plain'], indirect=True)
def test_review_header_fits_when_scrollbar_reserves_viewport_space(validation_app: dict[str, Any]) -> None:
    """Windows scrollbar space must not turn the review UUID into page overflow."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(ignore_default_args=['--hide-scrollbars'])
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            login_review(page, validation_app)
            expect(page.locator('#review-item-badge')).to_have_text(validation_app['review'])
            page.locator('#review-claim-button').click()
            expect(page.locator('#review-release-button')).to_be_enabled()
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('html').evaluate("element => { element.style.scrollbarGutter = 'stable'; }")
            expect(page.locator('#review-pdf-body canvas')).to_be_visible()
            widths = page.evaluate('({client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth})')
            assert widths['client'] < 390
            assert widths['scroll'] <= widths['client']
            page.locator('input[data-field-path="items.0.line_total"]').fill('30')
            with page.expect_response(lambda response: response.url.endswith('/complete')) as accepted:
                page.locator('#review-complete-button').click()
            assert accepted.value.status == 200
            page.wait_for_url('**/app/review')
            page.goto(f"{validation_app['base']}/app/review/{validation_app['review']}")
            expect(page.locator('#review-completion-banner')).to_be_visible()
            page.locator('html').evaluate("element => { element.style.scrollbarGutter = 'stable'; }")
            widths = page.evaluate('({client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth})')
            assert widths['scroll'] <= widths['client']
        finally:
            browser.close()


def checked(page: Page) -> None:
    with page.expect_response(lambda response: response.url.endswith('/revalidate')) as response:
        page.get_by_role('button', name='Revalidate', exact=True).click()
    assert response.value.status == 200
    expect(page.locator('#review-validation-status')).to_have_text('Current values checked')


def test_multiple_rules_stale_async_rows_blocking_warning_drafts_and_mobile(
    validation_app: dict[str, Any], tmp_path: Path,
) -> None:
    evidence = Path(os.environ.get('R4_PHASE4_EVIDENCE_DIR', str(tmp_path / 'evidence')))
    evidence.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            login_review(page, validation_app)
            status = page.locator('#review-validation-status')
            summary = page.locator('#review-validation-summary')
            revalidate = page.get_by_role('button', name='Revalidate', exact=True)
            quantity = page.locator('input[data-field-path="items.0.quantity"]')
            amount = page.locator('input[data-field-path="items.0.line_total"]')
            subtotal = page.locator('input[data-field-path="subtotal"]')
            expect(revalidate).to_be_disabled()
            expect(summary).to_contain_text('2 failed')
            expect(page.locator('.review-business-row-findings')).to_contain_text('Expected: 30.00')
            expect(page.locator('.review-field-row[data-field-path="subtotal"] .review-business-inline')).to_contain_text('Sum rows against a field (subtotal)')
            page.locator('#review-validation-details').evaluate('element => element.open = true')
            page.screenshot(path=str(evidence / 'two-rules-desktop.png'))
            page.locator('#review-claim-button').click()
            expect(revalidate).to_be_enabled()
            expect(quantity).to_have_attribute('aria-describedby', 'review-business-finding-0')
            expect(page.locator('#review-save-button')).to_be_enabled()

            # Keep two real server responses pending and deliver the newer one first.
            pending = []
            def hold(route: Route) -> None:
                response = route.fetch()
                pending.append((route, response.json()))
                page.locator('body').evaluate('(element, count) => element.dataset.heldValidationCount = String(count)', len(pending))
            page.route('**/revalidate', hold)
            quantity.fill('4')
            expect(status).to_contain_text('revalidation needed')
            expect(page.locator('.review-business-inline')).to_have_count(0)
            assert quantity.get_attribute('aria-describedby') is None
            revalidate.click()
            expect(status).to_have_text('Checking current values…')
            quantity.fill('5')
            expect(revalidate).to_be_enabled()
            revalidate.click()
            expect(status).to_have_text('Checking current values…')
            expect(page.locator('body')).to_have_attribute('data-held-validation-count', '2')
            assert len(pending) == 2
            pending.sort(key=lambda entry: entry[1]['request_revision'])
            quantity.focus()
            pending[1][1]['business_validation']['checks'][0]['message'] = '<img src=x onerror="window.injected=true">Literal message'
            pending[1][0].fulfill(json=pending[1][1])
            expect(status).to_have_text('Current values checked')
            expect(page.locator('.review-business-row-findings')).to_contain_text('Expected: 50.00')
            expect(quantity).to_be_focused()
            pending[0][0].fulfill(json=pending[0][1])
            expect(page.locator('.review-business-row-findings')).to_contain_text('Expected: 50.00')
            assert page.locator('img[src="x"]').count() == 0
            assert page.evaluate('window.injected === undefined')
            expect(quantity).to_have_value('5')
            page.unroute('**/revalidate', hold)

            # Source visibility changes must keep the findings and entered values.
            page.locator('#review-source-mode-select').select_option('all')
            expect(quantity).to_have_value('5')
            expect(page.locator('.review-business-row-findings')).to_contain_text('Expected: 50.00')
            page.locator('#review-source-mode-select').select_option('hidden')
            expect(quantity).to_have_attribute('aria-describedby', 'review-business-finding-0')

            # Row changes invalidate old row indices, including an empty collection.
            page.get_by_role('button', name='Add Row', exact=True).click()
            expect(status).to_contain_text('revalidation needed')
            checked(page)
            expect(page.locator('.review-business-row-findings').last).to_contain_text('Row 2')
            expect(summary).to_contain_text('cannot evaluate')
            page.get_by_role('button', name='Remove', exact=True).first.click()
            checked(page)
            expect(page.locator('.review-business-row-findings')).to_contain_text('Row 1')
            expect(page.locator('.review-business-row-findings')).not_to_contain_text('Row 2')
            page.get_by_role('button', name='Remove', exact=True).click()
            checked(page)
            expect(summary).to_contain_text('2 cannot evaluate')
            page.get_by_role('button', name='Add Row', exact=True).click()
            quantity.fill('3')
            page.locator('input[data-field-path="items.0.unit_price"]').fill('10')
            amount.fill('30')
            subtotal.fill('30')
            checked(page)
            expect(summary).to_contain_text('2 passed')
            expect(page.locator('.review-business-inline')).to_have_count(0)
            quantity.fill('')
            checked(page)
            expect(page.locator('.review-business-row-findings')).to_contain_text('Cannot evaluate')
            quantity.fill('3')
            checked(page)

            # Completion must refresh a stale passing report using actual submitted edits.
            amount.fill('31')
            with page.expect_response(lambda response: response.url.endswith('/complete')) as blocked:
                page.locator('#review-complete-button').click()
            assert blocked.value.status == 422
            expect(summary).to_contain_text('2 failed')
            expect(status).to_be_focused()
            expect(amount).to_have_value('31')
            expect(page.locator('#review-save-button')).to_be_enabled()
            saved_responses = []
            def hold_save(route: Route) -> None:
                response = route.fetch()
                saved_responses.append((route, response.json()))
                page.locator('body').evaluate('element => element.dataset.heldSave = "ready"')
            page.route('**/draft', hold_save)
            page.locator('#review-save-button').click()
            expect(page.locator('body')).to_have_attribute('data-held-save', 'ready')
            expect(page.locator('#review-release-button')).to_be_disabled()
            expect(page.locator('#review-complete-button')).to_be_disabled()
            quantity.fill('4')
            saved_responses[0][0].fulfill(json=saved_responses[0][1])
            page.get_by_text('Draft saved', exact=True).wait_for()
            expect(quantity).to_have_value('4')
            expect(status).to_contain_text('revalidation needed')
            page.unroute('**/draft', hold_save)
            quantity.fill('3')
            with page.expect_response(lambda response: response.url.endswith('/draft')):
                page.locator('#review-save-button').click()
            page.reload()
            expect(amount).to_have_value('31')
            expect(summary).to_contain_text('2 failed')

            # A transport error cannot leave an old passing report marked current.
            def unavailable(route: Route) -> None:
                route.fulfill(status=503, json={'detail': 'synthetic check outage'})
            page.route('**/revalidate', unavailable)
            revalidate.click()
            expect(status).to_have_text('Checks unavailable')
            expect(amount).to_have_value('31')
            expect(page.locator('.review-business-inline')).to_have_count(0)
            page.unroute('**/revalidate', unavailable)
            def evaluator_error(route: Route) -> None:
                payload = route.fetch().json()
                payload['business_validation'].update(evaluation_status='error', has_blocking_findings=True)
                payload['business_validation']['checks'] = [{
                    'rule_id': 'evaluator', 'validator': 'evaluator', 'status': 'error', 'code': 'evaluator_unavailable',
                    'severity': 'blocking', 'message': 'Business validation could not be completed.', 'field_paths': [],
                }]
                route.fulfill(json=payload)
            page.route('**/revalidate', evaluator_error)
            with page.expect_response(lambda response: response.url.endswith('/revalidate')):
                revalidate.click()
            expect(status).to_have_text('Validation error — retry checks')
            expect(summary).to_contain_text('1 errors')
            page.unroute('**/revalidate', evaluator_error)
            def disabled_rule(route: Route) -> None:
                payload = route.fetch().json()
                payload['business_validation']['checks'][0].update(status='skipped', code='disabled')
                route.fulfill(json=payload)
            page.route('**/revalidate', disabled_rule)
            checked(page)
            expect(summary).to_contain_text('1 disabled')
            expect(page.locator('.review-business-inline[data-business-rule="item_amount"]')).to_have_count(0)
            page.unroute('**/revalidate', disabled_rule)
            amount.fill('300')
            subtotal.fill('300')
            checked(page)
            expect(summary).to_contain_text('Warnings allow completion')
            expect(summary).to_contain_text('1 passed')
            page.locator('#review-validation-details').evaluate('element => element.open = true')
            page.locator('#review-validation-list button').first.focus()
            page.keyboard.press('Enter')
            expect(quantity).to_be_focused()
            page.set_viewport_size({'width': 390, 'height': 844})
            offset = require_present(page.locator('main > header').bounding_box())['height'] + 12
            expect(page.locator('#human-review-workspace')).to_have_css('--review-scroll-offset', f'{offset:g}px')
            scroll_to = "element => import('/static/js/human-review/validation-view.js?v=generic-rules-1').then(module => module.scrollReviewTarget(element, 'start'))"
            page.locator('#review-validation-panel').evaluate(scroll_to)
            assert require_present(page.locator('#review-validation-title').bounding_box())['y'] >= require_present(page.locator('main > header').bounding_box())['height']
            page.screenshot(path=str(evidence / 'warning-mobile-summary.png'))
            page.locator('.review-business-row-findings').evaluate(scroll_to)
            page.screenshot(path=str(evidence / 'warning-mobile-row.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            completions = []
            def hold_completion(route: Route) -> None:
                response = route.fetch()
                completions.append((route, response.json()))
                page.locator('body').evaluate('element => element.dataset.heldCompletion = "ready"')
            page.route('**/complete', hold_completion)
            page.locator('#review-complete-button').click()
            expect(page.locator('body')).to_have_attribute('data-held-completion', 'ready')
            assert page.locator('#review-fields-container').get_attribute('inert') is not None
            completions[0][0].fulfill(json=completions[0][1])
            page.wait_for_url('**/app/review')
            page.unroute('**/complete', hold_completion)
            page.goto(f"{validation_app['base']}/app/review/{validation_app['review']}")
            expect(status).to_have_text('Accepted report')
            expect(revalidate).to_be_disabled()
            expect(quantity).to_be_disabled()
            assert not errors
        finally:
            browser.close()


@pytest.mark.parametrize('validation_app', ['nested', 'plain', 'missing'], indirect=True)
def test_nested_findings_and_no_rules_compatibility(validation_app: dict[str, Any]) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1366, 'height': 900})
            login_review(page, validation_app)
            panel = page.locator('#review-validation-panel')
            if validation_app['mode'] == 'missing':
                page.locator('#review-claim-button').click()
                with page.expect_request(lambda request: request.url.endswith('/revalidate')) as sent:
                    checked(page)
                assert require_present(sent.value.post_data_json)['corrections'] == {}
                expect(page.locator('#review-validation-summary')).to_contain_text('2 cannot evaluate')
                page.get_by_role('button', name='Add Row', exact=True).click()
                for key, value in [('quantity', '3'), ('unit_price', '10'), ('line_total', '30')]:
                    page.locator(f'input[data-field-path="items.0.{key}"]').fill(value)
                checked(page)
                expect(page.locator('#review-validation-summary')).to_contain_text('2 passed')
            elif panel.is_visible():
                expect(page.locator('.review-field-row[data-field-path="totals.subtotal"] .review-business-inline')).to_contain_text('Sum rows against a field (subtotal)')
                page.locator('#review-claim-button').click()
                page.locator('input[data-field-path="totals.subtotal"]').fill('300')
                checked(page)
                expect(page.locator('#review-validation-summary')).to_contain_text('Warnings allow completion')
                other = browser.new_page()
                login_review(other, validation_app, operator=True)
                expect(other.get_by_role('button', name='Revalidate', exact=True)).to_be_disabled()
                expect(other.locator('input[data-field-path="totals.subtotal"]')).to_be_disabled()
                expect(other.locator('#review-validation-summary')).to_contain_text('2 failed')
            else:
                expect(page.locator('#review-revalidate-button')).to_be_hidden()
                page.locator('#review-claim-button').click()
                page.locator('input[data-field-path="subtotal"]').fill('300')
                page.locator('#review-save-button').click()
                page.get_by_text('Draft saved', exact=True).wait_for()
                expect(panel).to_be_hidden()
                page.locator('#review-complete-button').click()
                page.wait_for_url('**/app/review')
        finally:
            browser.close()
