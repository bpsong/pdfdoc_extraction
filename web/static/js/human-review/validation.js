/** Track which server findings belong to the current values and pinned form. */

export function reviewPointer(parts) {
    return '/' + parts.map((part) => String(part).replace(/~/g, '~0').replace(/\//g, '~1')).join('/');
}

export function pointerParts(pointer) {
    return pointer.startsWith('/')
        ? pointer.slice(1).split('/').map((part) => part.replace(/~1/g, '/').replace(/~0/g, '~')) : [];
}

function valueSignature(value) {
    return JSON.stringify(value, (_key, item) => item && typeof item === 'object' && !Array.isArray(item)
        ? Object.fromEntries(Object.keys(item).sort().map((key) => [key, item[key]])) : item);
}

export function createReviewValidation(state, model, onChange = () => {}) {
    let sequence = 0;
    let edit = 0;
    let identity = {};
    let result = {enabled: false, phase: 'none', report: null, schemaErrors: [], pending: false};

    function matches(report, revision, accepted = false) {
        return report && Array.isArray(report.checks)
            && report.schema_version_id === identity.schema
            && report.schema_hash === identity.hash
            && report.document_id === identity.document
            && (accepted || report.review_revision === revision);
    }

    function load(payload) {
        sequence += 1;
        edit += 1;
        identity = {schema: payload.schema?.name, hash: payload.schema?.hash, document: payload.document?.id};
        const enabled = Boolean(payload.schema?.business_validation || payload.business_validation);
        const accepted = Boolean(model.isComplete());
        const report = payload.business_validation;
        result = {enabled, phase: enabled ? 'current' : 'none', report: null, labels: payload.business_validation_labels || {},
            schemaErrors: [], pending: false, accepted, conflict: false, message: ''};
        if (enabled) {
            if (matches(report, state.reviewRevision, accepted)) result.report = report;
            else {
                result.phase = 'error';
                result.message = 'Checks are unavailable for this form and these values. Reload the review.';
            }
        }
        onChange();
    }

    function changed() {
        if (!result.enabled) return;
        edit += 1;
        result = {...result, phase: 'stale', pending: false, message: ''};
        onChange();
    }

    function capture(checking = false) {
        const ticket = {id: ++sequence, edit, revision: state.reviewRevision, signature: valueSignature(state.values)};
        if (result.enabled) {
            result = {...result, pending: checking, phase: checking ? 'checking' : result.phase === 'checking' ? 'stale' : result.phase};
            onChange();
        }
        return ticket;
    }

    function isCurrent(ticket) {
        return ticket.id === sequence && ticket.edit === edit && ticket.revision === state.reviewRevision
            && ticket.signature === valueSignature(state.values) && !model.isComplete();
    }

    function accept(ticket, payload) {
        if (!isCurrent(ticket)) return false;
        if (payload.request_revision !== ticket.id || payload.review_revision !== ticket.revision
                || !matches(payload.business_validation, ticket.revision)) {
            result = {...result, phase: 'error', pending: false,
                message: 'The check response does not match the current review. Revalidate or reload.'};
        } else {
            result = {...result, phase: 'current', pending: false, report: payload.business_validation,
                labels: payload.business_validation_labels || result.labels || {},
                schemaErrors: payload.schema_errors || [], message: ''};
        }
        onChange();
        return true;
    }

    function fail(ticket, error) {
        if (!isCurrent(ticket)) return false;
        const conflict = error.status === 409;
        result = {...result, phase: 'error', pending: false, conflict,
            message: conflict
                ? 'The review or claim changed. Your edits are retained; keep a copy before reloading.'
                : 'Checks could not be completed. Your edits are retained. Try Revalidate again.'};
        onChange();
        return true;
    }

    function completionFailure(ticket, error) {
        const report = error.detail?.business_validation;
        if (report) return accept(ticket, {request_revision: ticket.id, review_revision: report.review_revision,
            business_validation: report, schema_errors: report.schema_errors || []});
        return fail(ticket, error);
    }

    function canCheck() {
        const expiry = Date.parse(state.lock?.expires_at || '');
        return result.enabled && model.hasOwnLock() && !model.isComplete() && !state.completionPending && !state.savingDraft
            && !result.pending && !result.conflict && Number.isFinite(expiry) && expiry > Date.now();
    }

    return {load, changed, capture, accept, fail, completionFailure, canCheck, current: () => result};
}
