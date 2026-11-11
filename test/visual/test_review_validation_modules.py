"""Browser-independent lifecycle checks for current, stale, and concurrent reports."""

import pytest

from test.visual.test_human_review_modules import _run_module


SETUP = """
const state = {reviewRevision: 'revision', values: {items: [{amount: 30}], subtotal: 30},
    lock: {expires_at: '2099-01-01T00:00:00Z'}, completionPending: false};
let complete = false, own = true;
const model = {hasOwnLock: () => own, isComplete: () => complete};
const report = {schema_version_id: 'schema', schema_hash: 'hash', document_id: 'document',
    review_revision: 'revision', checks: [{rule_id: 'sum', status: 'passed'}]};
const payload = {schema: {name: 'schema', hash: 'hash', business_validation: {rules: []}},
    document: {id: 'document'}, business_validation: report};
const lifecycle = module.createReviewValidation(state, model);
lifecycle.load(payload);
const reply = ticket => ({request_revision: ticket.id, review_revision: ticket.revision,
    business_validation: structuredClone(report), schema_errors: []});
"""


def test_pointer_escaping_preserves_nested_keys_and_indices() -> None:
    result = _run_module("validation.js", """
        const parts = ['a/b', 'til~de', 'with.dot', 0, 'value'];
        return {pointer: module.reviewPointer(parts), parts: module.pointerParts(module.reviewPointer(parts))};
    """)
    assert result == {"pointer": "/a~1b/til~0de/with.dot/0/value", "parts": ["a/b", "til~de", "with.dot", "0", "value"]}


def test_load_accepts_draft_report_and_completed_report_without_enabling_edits() -> None:
    result = _run_module("validation.js", SETUP + """
        const initial = {phase: lifecycle.current().phase, canCheck: lifecycle.canCheck()};
        complete = true;
        state.reviewRevision = 'completed-revision';
        lifecycle.load(payload);
        return {initial, accepted: lifecycle.current().accepted, phase: lifecycle.current().phase,
            canCheck: lifecycle.canCheck()};
    """)
    assert result == {"initial": {"phase": "current", "canCheck": True}, "accepted": True, "phase": "current", "canCheck": False}


@pytest.mark.parametrize("action", ["value", "add", "remove"])
def test_changes_invalidate_results_and_discard_pending_response(action: str) -> None:
    mutation = {"value": "state.values.subtotal = 50;", "add": "state.values.items.push({amount: 5});",
                "remove": "state.values.items.splice(0, 1);"}[action]
    result = _run_module("validation.js", SETUP + """
        const ticket = lifecycle.capture(true);
    """ + mutation + """
        lifecycle.changed();
        const values = JSON.stringify(state.values);
        const accepted = lifecycle.accept(ticket, reply(ticket));
        return {accepted, phase: lifecycle.current().phase, canCheck: lifecycle.canCheck(),
            unchanged: values === JSON.stringify(state.values)};
    """)
    assert result == {"accepted": False, "phase": "stale", "canCheck": True, "unchanged": True}


def test_out_of_order_responses_and_failures_cannot_replace_newer_results() -> None:
    result = _run_module("validation.js", SETUP + """
        const first = lifecycle.capture(true);
        const second = lifecycle.capture(true);
        const newer = reply(second);
        newer.business_validation.checks = [{status: 'failed', rule_id: 'latest'}];
        lifecycle.accept(second, newer);
        const staleSuccess = lifecycle.accept(first, reply(first));
        const staleError = lifecycle.fail(first, {status: 409});
        return {staleSuccess, staleError, phase: lifecycle.current().phase,
            rule: lifecycle.current().report.checks[0].rule_id};
    """)
    assert result == {"staleSuccess": False, "staleError": False, "phase": "current", "rule": "latest"}


@pytest.mark.parametrize("wrong", ["request", "revision", "schema", "hash", "document"])
def test_response_identity_must_match_current_form_request_and_source(wrong: str) -> None:
    mutation = {"request": "response.request_revision += 1;", "revision": "response.review_revision = 'other';",
                "schema": "response.business_validation.schema_version_id = 'other';",
                "hash": "response.business_validation.schema_hash = 'other';",
                "document": "response.business_validation.document_id = 'other';"}[wrong]
    result = _run_module("validation.js", SETUP + """
        const ticket = lifecycle.capture(true);
        const response = reply(ticket);
    """ + mutation + """
        lifecycle.accept(ticket, response);
        return lifecycle.current().phase;
    """)
    assert result == "error"


def test_load_or_source_change_invalidates_old_requests() -> None:
    result = _run_module("validation.js", SETUP + """
        const old = lifecycle.capture(true);
        lifecycle.load(payload);
        const ignoredLoad = !lifecycle.accept(old, reply(old));
        const current = lifecycle.capture(true);
        state.reviewRevision = 'new-source';
        return {ignoredLoad, ignoredSource: !lifecycle.accept(current, reply(current))};
    """)
    assert result == {"ignoredLoad": True, "ignoredSource": True}


def test_completion_findings_are_applied_and_conflicts_require_reload() -> None:
    result = _run_module("validation.js", SETUP + """
        const ticket = lifecycle.capture();
        const blocked = {...report, checks: [{rule_id: 'sum', status: 'failed'}]};
        lifecycle.completionFailure(ticket, {status: 422, detail: {business_validation: blocked}});
        const status = lifecycle.current().report.checks[0].status;
        lifecycle.fail(lifecycle.capture(true), {status: 409});
        lifecycle.changed();
        return {status, canCheck: lifecycle.canCheck(), conflict: lifecycle.current().conflict,
            unchanged: state.values.subtotal === 30};
    """)
    assert result == {"status": "failed", "canCheck": False, "conflict": True, "unchanged": True}


@pytest.mark.parametrize("mode", ["other_owner", "expired", "completed", "completing", "saving", "no_rules"])
def test_readonly_or_unavailable_actions_cannot_revalidate(mode: str) -> None:
    mutation = {"other_owner": "own = false;", "expired": "state.lock.expires_at = '2000-01-01';",
                "completed": "complete = true;", "completing": "state.completionPending = true;",
                "saving": "state.savingDraft = true;", "no_rules": "lifecycle.load({});"}[mode]
    result = _run_module("validation.js", SETUP + mutation + "return lifecycle.canCheck();")
    assert result is False


def test_network_error_does_not_show_passing_report_as_current_and_can_retry() -> None:
    result = _run_module("validation.js", SETUP + """
        lifecycle.fail(lifecycle.capture(true), {status: 503});
        const error = {phase: lifecycle.current().phase, canCheck: lifecycle.canCheck()};
        const retry = lifecycle.capture(true);
        lifecycle.accept(retry, reply(retry));
        return {error, phase: lifecycle.current().phase};
    """)
    assert result == {"error": {"phase": "error", "canCheck": True}, "phase": "current"}
