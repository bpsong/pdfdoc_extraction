/** Accessible business-check summary and annotations, independent of source mode. */

import { pointerParts } from './validation.js?v=generic-rules-1';

const OUTCOMES = {passed: 'Passed', failed: 'Check failed', not_evaluated: 'Cannot evaluate', error: 'Validation error', skipped: 'Skipped', disabled: 'Disabled', not_applicable: 'Not applicable'};
const outcomeKey = (check) => check.status === 'skipped' ? check.code === 'disabled' ? 'disabled' : 'not_applicable' : check.status;

export function scrollReviewTarget(target, block = 'center') {
    // Nested scrolling containers can align a target behind the mobile header.
    target.scrollIntoView({block, inline: 'nearest', behavior: 'auto'});
    const header = target.closest('main')?.querySelector(':scope > header');
    if (!header || window.getComputedStyle(header).position !== 'sticky') return;
    const top = header.getBoundingClientRect().bottom + 12;
    for (let parent = target.parentElement; parent && target.getBoundingClientRect().top < top; parent = parent.parentElement) {
        if (parent.scrollHeight > parent.clientHeight) {
            parent.scrollTop += target.getBoundingClientRect().top - top;
        }
    }
}

export function createReviewValidationView(elements, model, validation) {
    const {fieldsContainer, validationPanel, validationStatus, validationSummary,
        validationDetails, validationList, revalidateButton} = elements;

    function node(tag, className, text) {
        const item = document.createElement(tag);
        if (className) item.className = className;
        if (text !== undefined) item.textContent = text;
        return item;
    }

    function checkTitle(check) {
        const name = validation.current().labels?.[check.validator] || check.validator || 'Business check';
        return `${name} (${check.rule_id})${check.row_index !== null && check.row_index !== undefined ? ` · Row ${check.row_index + 1}` : ''}`;
    }

    function checkText(check) {
        const evidence = [['Expected', check.expected], ['Actual', check.actual], ['Difference', check.difference]]
            .filter(([_label, value]) => value !== null && value !== undefined)
            .map(([label, value]) => `${label}: ${value}`).join(' · ');
        return [check.message, evidence].filter(Boolean).join(' ');
    }

    function clearAnnotations() {
        fieldsContainer.querySelectorAll('.review-business-inline, .review-business-row-findings').forEach((item) => item.remove());
        fieldsContainer.querySelectorAll('[data-business-described]').forEach((input) => {
            const owned = new Set(input.dataset.businessDescribed.split(' '));
            const ids = (input.getAttribute('aria-describedby') || '').split(' ').filter((id) => id && !owned.has(id));
            if (ids.length) input.setAttribute('aria-describedby', ids.join(' '));
            else input.removeAttribute('aria-describedby');
            delete input.dataset.businessDescribed;
        });
        fieldsContainer.querySelectorAll('.review-business-warning, .review-business-blocking').forEach((item) => {
            item.classList.remove('review-business-warning', 'review-business-blocking');
        });
    }

    function render() {
        const result = validation.current();
        clearAnnotations();
        validationPanel.hidden = !result.enabled;
        revalidateButton.hidden = !result.enabled;
        revalidateButton.disabled = !validation.canCheck();
        revalidateButton.textContent = result.pending ? 'Checking…' : 'Revalidate';
        revalidateButton.setAttribute('aria-busy', String(result.pending));
        if (!result.enabled) return;
        validationPanel.dataset.validationState = result.phase;
        validationList.replaceChildren();
        const current = result.phase === 'current';
        const evaluationError = result.report?.evaluation_status === 'error' || result.report?.checks.some((check) => check.status === 'error');
        const states = {current: result.accepted ? 'Accepted report' : evaluationError ? 'Validation error — retry checks' : 'Current values checked', stale: 'Values changed — revalidation needed',
            checking: 'Checking current values…', error: 'Checks unavailable'};
        validationStatus.textContent = states[result.phase] || 'Checks unavailable';
        if (!current) {
            validationSummary.textContent = result.message || (result.phase === 'checking'
                ? 'Your edits are retained while checks run.'
                : 'Previous findings no longer describe these edits. Revalidate to refresh them; completion checks the values again.');
            validationDetails.hidden = true;
            return;
        }
        const checks = result.report?.checks || [];
        const counts = Object.fromEntries(Object.keys(OUTCOMES).map((status) => [status, checks.filter((check) => outcomeKey(check) === status).length]));
        const findings = checks.filter((check) => !['passed', 'skipped'].includes(check.status));
        const schemaErrors = result.schemaErrors || [];
        const blocking = result.report.has_blocking_findings || schemaErrors.length;
        validationSummary.textContent = `${counts.passed} passed · ${counts.failed} failed · ${counts.not_evaluated} cannot evaluate · ${counts.error} errors · ${counts.disabled} disabled${counts.not_applicable ? ` · ${counts.not_applicable} not applicable` : ''}.`
            + (schemaErrors.length ? ` ${schemaErrors.length} form errors.` : '')
            + (result.accepted ? ' This report was recorded at completion.' : blocking
                ? ' Resolve blocking findings before completion. Drafts can still be saved.'
                : findings.length ? ' Warnings allow completion. Drafts can still be saved.' : ' No business findings prevent completion.');
        validationPanel.dataset.blocking = String(Boolean(blocking));
        validationDetails.hidden = !checks.length && !schemaErrors.length;
        const targets = new Map(Array.from(fieldsContainer.querySelectorAll('[data-validation-path]'),
            (item) => [item.dataset.validationPath, item]));

        function targetFor(pointer) {
            while (pointer) {
                if (targets.has(pointer)) return targets.get(pointer);
                pointer = pointer.slice(0, pointer.lastIndexOf('/'));
            }
            return null;
        }

        function annotate(check, id, text) {
            const locations = new Set();
            for (const pointer of check.field_paths || []) {
                const target = targetFor(pointer);
                if (!target) continue;
                const blockingCheck = check.severity === 'blocking' || check.status === 'error';
                target.classList.add(blockingCheck ? 'review-business-blocking' : 'review-business-warning');
                target.querySelectorAll('input, select, textarea').forEach((input) => {
                    const descriptions = new Set((input.getAttribute('aria-describedby') || '').split(' ').filter(Boolean));
                    const owned = new Set((input.dataset.businessDescribed || '').split(' ').filter(Boolean));
                    descriptions.add(id);
                    owned.add(id);
                    input.setAttribute('aria-describedby', [...descriptions].join(' '));
                    input.dataset.businessDescribed = [...owned].join(' ');
                });
                locations.add(target.closest('tr[data-validation-row]') || target);
            }
            for (const target of locations) {
                const content = node('div', 'review-business-inline', text);
                content.dataset.businessRule = check.rule_id;
                content.dataset.severity = check.severity === 'blocking' || check.status === 'error' ? 'blocking' : 'warning';
                if (target.tagName === 'TR') {
                    let row = target.nextElementSibling;
                    if (!row?.classList.contains('review-business-row-findings')) {
                        row = node('tr', 'review-business-row-findings');
                        const cell = node('td');
                        cell.colSpan = target.cells.length;
                        row.appendChild(cell);
                        target.after(row);
                    }
                    row.firstElementChild.appendChild(content);
                } else target.appendChild(content);
            }
            return locations;
        }

        // Passing/disabled outcomes stay compact: one entry per configured rule.
        const groups = new Map();
        for (const check of checks) {
            const group = groups.get(check.rule_id) || {title: checkTitle({...check, row_index: null}), counts: {}};
            const outcome = outcomeKey(check);
            group.counts[outcome] = (group.counts[outcome] || 0) + 1;
            groups.set(check.rule_id, group);
        }
        for (const group of groups.values()) {
            validationList.appendChild(node('li', 'review-business-rule-summary',
                `${group.title}: ${Object.entries(group.counts).map(([status, count]) => `${OUTCOMES[status] || status} ${count}`).join(' · ')}`));
        }
        const visibleFindings = findings.slice(0, 100);
        for (const [index, check] of visibleFindings.entries()) {
            const id = `review-business-finding-${index}`;
            const item = node('li', 'review-business-finding');
            item.id = id;
            const text = `${checkTitle(check)} · ${check.status === 'error' || check.severity === 'blocking' ? 'Blocking' : 'Warning'} · ${OUTCOMES[check.status] || check.status}. ${checkText(check)}`;
            item.appendChild(node('p', '', text));
            validationList.appendChild(item);
            const locations = annotate(check, id, text);
            if (locations.size) {
                const pointer = (['sum_equals:v1', 'date_order:v1'].includes(check.validator) ? check.field_paths?.at(-1)
                    : check.validator === 'required_if:v1' ? check.field_paths?.[1] : check.field_paths?.[0]) || check.field_paths?.[0] || '';
                const path = pointerParts(pointer);
                const field = model.fieldForSchemaPath(path);
                const control = targetFor(pointer)?.querySelector('input, select, textarea');
                const label = control?.getAttribute('aria-label') || (field ? model.fieldLabel(field) : path.join(' / ') || 'field');
                const link = node('button', 'review-business-location', `Go to ${label}`);
                link.type = 'button';
                link.addEventListener('click', () => {
                    const target = targetFor(pointer);
                    if (!target) return;
                    scrollReviewTarget(target);
                    const input = target.querySelector('input:not(:disabled), select:not(:disabled), textarea:not(:disabled)');
                    if (input) input.focus({preventScroll: true});
                    else { target.tabIndex = -1; target.focus({preventScroll: true}); }
                });
                item.appendChild(link);
            }
        }
        if (findings.length > visibleFindings.length) validationList.appendChild(node('li', '',
            `Showing the first ${visibleFindings.length} of ${findings.length} findings. Correct values and revalidate to refresh the list.`));
        for (const error of schemaErrors) validationList.appendChild(node('li', 'review-business-finding',
            `Form field ${error.path || ''}: ${error.message || 'Check the value.'}`));
    }

    return {render, scrollToSummary: () => scrollReviewTarget(validationPanel, 'start')};
}
