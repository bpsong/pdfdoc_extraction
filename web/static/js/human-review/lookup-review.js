/** Manage provisional CSV lookup decisions and render their server evidence. */

import { reviewPointer } from './validation.js?v=r3-lookup-1';

const MODES = {case_sensitive: "Case-sensitive text", case_insensitive: "Case-insensitive text", numeric: "Numeric"};
const OUTCOMES = {matched: "Unique match", no_match: "No match", multiple_matches: "Multiple matches"};
const ISSUES = {
    reference_changed: "The CSV changed or the original file is unavailable. Adopt the current file to check the edited inputs.",
    reference_unavailable: "The current CSV could not be used. Ask an administrator to check the reference file, then revalidate.",
    stale_lookup_selection: "The candidate evidence changed. Revalidate before choosing a record again.",
    invalid_lookup_resolution: "This record cannot supply all returned text. Revalidate and choose a complete record.",
    lookup_action_unavailable: "This lookup no longer needs that decision. Revalidate to refresh the evidence.",
};

export function createLookupReview(panel, state, model, revalidate) {
    const status = panel.querySelector("[role=status]");
    const results = panel.querySelector("[data-lookup-results]");
    const escape = model.escapeHtml;
    const actions = new Map();
    const adoptions = new Map();
    const choices = new Map();
    const signatures = new Map();
    const staleLookups = new Set();
    let review = null;
    let previewToken = null;
    let pending = false;
    let conflict = false;
    let message = "";

    const active = () => Boolean(review?.lookups?.length);
    const canEdit = () => model.hasOwnLock() && !model.isComplete() && Date.parse(state.lock.expires_at) > Date.now()
        && !state.completionPending && !state.savingDraft && !conflict;
    const signature = (lookup) => JSON.stringify(lookup.inputs.map(({field}) => state.values[field]));
    const isStale = (lookup) => staleLookups.has(lookup.task_key);

    function recordEvidence(payload) {
        review = payload;
        signatures.clear();
        staleLookups.clear();
        for (const lookup of review?.lookups || []) signatures.set(lookup.task_key, signature(lookup));
    }

    function load(payload) {
        actions.clear();
        adoptions.clear();
        choices.clear();
        previewToken = null;
        pending = false;
        conflict = false;
        message = "";
        recordEvidence(payload.lookup_review);
    }

    function changed() {
        if (!active()) return;
        previewToken = null;
        pending = false;
        message = "";
        for (const lookup of review.lookups) {
            if (signatures.get(lookup.task_key) === signature(lookup)) continue;
            staleLookups.add(lookup.task_key);
            actions.delete(lookup.task_key);
            choices.delete(lookup.task_key);
        }
    }

    function request(completing = false) {
        if (!active()) return {};
        return {
            lookup_actions: Object.fromEntries(actions),
            reference_adoptions: Object.fromEntries(adoptions),
            ...(completing ? {lookup_preview_token: previewToken} : {}),
        };
    }

    function accept(payload) {
        pending = false;
        if (!payload?.preview_token) {
            message = "The lookup check returned no preview. Revalidate again.";
            return;
        }
        for (const lookup of payload.lookups) {
            if (lookup.evaluation_token !== review.lookups.find(({task_key}) => task_key === lookup.task_key)?.evaluation_token) {
                choices.delete(lookup.task_key);
            }
            if (lookup.issue) actions.delete(lookup.task_key);
        }
        recordEvidence(payload);
        previewToken = payload.preview_token;
    }

    function fail(error) {
        if (!active()) return;
        pending = false;
        previewToken = null;
        if (error.detail?.lookup_review) {
            accept(error.detail.lookup_review);
            previewToken = null;
            message = "Lookup evidence changed. Review the results and revalidate.";
        } else {
            conflict = error.status === 409;
            message = conflict ? "The review or claim changed. Keep a copy of your edits before reloading."
                : "Lookup checks could not be completed. Try Revalidate again.";
        }
    }

    function start() {
        pending = true;
        previewToken = null;
        message = "";
    }

    function canComplete() {
        return !active() || (canEdit() && !pending && Boolean(previewToken) && !review.blocked);
    }

    function shown(value) {
        return escape(value === "" ? "(blank)" : model.formatValue(value));
    }

    function valuesList(values) {
        return `<dl class="review-lookup-values">${Object.entries(values).map(([field, value]) =>
            `<div><dt>${escape(field)}</dt><dd>${shown(value)}</dd></div>`).join("")}</dl>`;
    }

    function returnedText(lookup, stale) {
        const values = stale ? {} : lookup.returned_values;
        const absent = stale ? "Revalidation needed" : lookup.state === "skipped" ? "Omitted" : "Pending";
        return `<h5>Returned text · Read-only</h5><dl class="review-lookup-values">${lookup.return_fields.map((field) =>
            `<div data-validation-path="${escape(reviewPointer([field]))}"><dt>${escape(field)}</dt>
                <dd>${Object.hasOwn(values, field) ? shown(values[field]) : absent}</dd></div>`).join("")}</dl>`;
    }

    function candidateList(lookup, index, editable, choice) {
        if (!lookup.candidates.length) return "";
        return `<fieldset class="review-lookup-candidates"><legend>Candidate records</legend>
            <div class="review-lookup-candidate-list" role="region" aria-label="Records for ${escape(lookup.task_key)}" tabindex="0">
            ${lookup.candidates.map((candidate) => `
                <div class="review-lookup-candidate">
                    ${editable ? `<label><input type="radio" name="lookup-candidate-${index}" data-lookup-input="record" value="${candidate.record_number}" ${choice.record === candidate.record_number ? "checked" : ""}> Record ${candidate.record_number}</label>`
                : `<strong>Record ${candidate.record_number}${lookup.selected_record_number === candidate.record_number ? " (selected)" : ""}</strong>`}
                    <ul>${candidate.match_evidence.map((evidence) => `<li>${escape(evidence.column)} for ${escape(evidence.field)} · ${shown(evidence.reference_value)}</li>`).join("")}</ul>
                    ${valuesList(candidate.values)}
                </div>`).join("")}
            </div>
        </fieldset>`;
    }

    function resolutionControls(canSelect, canSkip, canAdopt, choice) {
        if (!canSelect && !canSkip && !canAdopt) return "";
        return `<form class="review-lookup-resolution" data-lookup-form>
            <label>${canAdopt ? "Reason for using the current file" : "Reason for this decision"}
                <input class="input input-bordered input-sm" data-lookup-input="reason" maxlength="1000" required value="${escape(choice.reason || "")}">
            </label>
            <div class="review-lookup-actions">
                ${canSelect ? '<button class="btn btn-primary btn-sm" type="submit" value="select">Use selected record</button>' : ""}
                ${canSkip ? '<button class="btn btn-outline btn-sm" type="submit" value="skip">Skip lookup</button>' : ""}
                ${canAdopt ? '<button class="btn btn-primary btn-sm" type="submit" value="adopt">Use current reference file</button>' : ""}
            </div>
        </form>`;
    }

    function lookupCard(lookup, index) {
        const stale = isStale(lookup);
        const editable = canEdit() && !pending && !stale;
        const choice = choices.get(lookup.task_key) || {};
        const action = actions.get(lookup.task_key);
        const adoption = adoptions.get(lookup.task_key);
        const canSelect = editable && lookup.can_select;
        const canSkip = editable && lookup.can_skip;
        const canAdopt = editable && lookup.issue === "reference_changed";
        const issue = stale ? "Match inputs changed. Revalidate to see current evidence." : ISSUES[lookup.issue];
        const outcome = lookup.state === "matched" && lookup.outcome !== "matched" ? "Matched by reviewer"
            : lookup.state === "skipped" ? "Skipped" : OUTCOMES[lookup.outcome];
        return `<article class="review-lookup-card" data-lookup-index="${index}">
            <div class="review-business-heading"><h4>${escape(lookup.task_key)}</h4><strong>${lookup.required ? "Required" : "Optional"} · ${outcome}${lookup.blocked ? " · Blocks completion" : ""}</strong></div>
            ${issue ? `<p class="review-lookup-notice">${issue}</p>` : ""}
            <h5>Match inputs</h5>
            <ul class="review-lookup-inputs">${lookup.inputs.map((input) => `<li>
                <strong>${escape(input.field)}</strong> → ${escape(input.column)}
                <span>${MODES[input.mode]} · Original ${shown(input.original)}${input.issue ? ` · ${escape(input.issue)}` : ""}</span>
            </li>`).join("")}</ul>
            ${stale ? "" : `
                ${lookup.candidates_truncated ? `<p class="review-lookup-notice">Showing ${lookup.candidates.length} of ${lookup.match_count} matches. Correct a match input or ask an administrator to narrow the register before selecting a record.</p>` : ""}
                ${!lookup.issue && lookup.state === "pending" && lookup.outcome === "no_match" ? "<p>Correct a match input in the review fields, then revalidate.</p>" : ""}
                ${lookup.state === "pending" && !lookup.issue ? candidateList(lookup, index, canSelect, choice) : ""}
            `}
            ${returnedText(lookup, stale)}
            ${lookup.selected_record_number != null && !stale && !lookup.issue ? `<p>Selected record ${lookup.selected_record_number}</p>` : ""}
            ${model.isComplete() && lookup.actor ? `<p>Decision by ${escape(lookup.actor)}${lookup.reason ? ` · ${escape(lookup.reason)}` : ""}</p>` : ""}
            ${action && !lookup.issue ? `<p>Proposed decision · ${escape(action.reason)}</p>
                <button class="btn btn-ghost btn-sm" type="button" data-lookup-reset="decision" ${editable ? "" : "disabled"}>Undo lookup decision</button>` : ""}
            ${adoption ? `<p>Proposed file adoption · ${escape(adoption)}</p>
                <button class="btn btn-ghost btn-sm" type="button" data-lookup-reset="adoption" ${editable ? "" : "disabled"}>Undo file adoption</button>` : ""}
            ${resolutionControls(canSelect, canSkip, canAdopt, choice)}
        </article>`;
    }

    function render() {
        panel.hidden = !active();
        if (!active()) return;
        const focused = document.activeElement;
        const card = focused?.closest("[data-lookup-index]");
        const controls = "input, button, [tabindex='0']";
        const controlIndex = card ? [...card.querySelectorAll(controls)].indexOf(focused) : -1;
        const validationPath = card && focused.dataset.validationPath;
        const text = model.isComplete() ? "Accepted lookup evidence" : message || (pending ? "Checking lookup evidence…"
            : review.blocked ? "Resolve lookup issues to complete review" : previewToken ? "Lookup evidence checked"
                : "Revalidate before completing review");
        if (status.textContent !== text) status.textContent = text;
        panel.dataset.blocking = String(review.blocked && !model.isComplete());
        results.innerHTML = review.lookups.map(lookupCard).join("");
        if (controlIndex >= 0) {
            const replacement = results.children[Number(card.dataset.lookupIndex)]?.querySelectorAll(controls)[controlIndex];
            const sameControl = replacement?.outerHTML === focused.outerHTML;
            (sameControl && !replacement.disabled ? replacement : status).focus({ preventScroll: true });
        } else if (validationPath) {
            const replacement = [...results.querySelectorAll('[data-validation-path]')]
                .find((item) => item.dataset.validationPath === validationPath);
            if (replacement) {
                replacement.tabIndex = -1;
                replacement.focus({ preventScroll: true });
            }
        }
    }

    function formContext(target) {
        const card = target.closest("[data-lookup-index]");
        return {card, lookup: review?.lookups[Number(card?.dataset.lookupIndex)]};
    }

    results.addEventListener("input", ({target}) => {
        const {lookup} = formContext(target);
        if (!lookup || !target.dataset.lookupInput) return;
        const key = lookup.task_key;
        const choice = choices.get(key) || {};
        if (target.dataset.lookupInput === "record") choice.record = Number(target.value);
        else {
            choice.reason = target.value;
            target.setCustomValidity("");
        }
        choices.set(key, choice);
    });

    results.addEventListener("submit", (event) => {
        event.preventDefault();
        const {card, lookup} = formContext(event.target);
        if (!lookup || pending || !canEdit() || isStale(lookup)) return;
        const key = lookup.task_key;
        const action = event.submitter?.value;
        const reasonInput = event.target.querySelector('[data-lookup-input="reason"]');
        const reason = reasonInput.value.trim();
        if (!reason) {
            reasonInput.setCustomValidity("Enter a reason for this decision.");
            reasonInput.reportValidity();
            return;
        }
        if (action === "adopt" && lookup.issue === "reference_changed") {
            adoptions.set(key, reason);
            actions.delete(key);
        } else if ((action === "select" && lookup.can_select) || (action === "skip" && lookup.can_skip)) {
            const selected = card.querySelector('[data-lookup-input="record"]:checked');
            if (action === "select" && !selected) {
                message = "Choose a candidate record before applying your decision.";
                render();
                results.children[Number(card.dataset.lookupIndex)]?.querySelector('input[type="radio"]')?.focus();
                return;
            }
            actions.set(key, {action, reason, evaluation_token: lookup.evaluation_token,
                ...(selected && action === "select" ? {record_number: Number(selected.value)} : {})});
        } else return;
        choices.delete(key);
        revalidate();
    });

    results.addEventListener("click", ({target}) => {
        const button = target.closest("[data-lookup-reset]");
        if (!button || pending || !canEdit()) return;
        const {lookup} = formContext(button);
        actions.delete(lookup.task_key);
        if (button.dataset.lookupReset === "adoption") adoptions.delete(lookup.task_key);
        revalidate();
    });

    return { active, load, changed, request, start, accept, fail, canComplete, render,
        canCheck: () => active() && canEdit() && !pending, pending: () => pending, focusStatus: () => status.focus() };
}
