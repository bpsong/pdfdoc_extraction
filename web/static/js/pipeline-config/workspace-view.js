/** Summary, catalog, and validation rendering for the pipeline workspace. */

export function createPipelineWorkspaceView(elements, helpers) {
    const { escapeHtml, badgeForStep, stepsOf, summaryText } = helpers;

    function renderStepLists(state) {
        const publishedVersion = state.baseVersionId
            ? state.versions.find((version) => version.id === state.baseVersionId)?.version_number
            : null;
        elements.activeSummary.textContent = publishedVersion
            ? `Published v${publishedVersion} · ${summaryText(state.active)} · Read only`
            : "No published version is available";
        const activeSteps = stepsOf(state.active);
        elements.activeList.innerHTML = activeSteps.length ? activeSteps.map((step, index) => `
            <div class="pipeline-static-step ${step.enabled === false ? "disabled" : ""}">
                <div class="pipeline-step-index">${index + 1}</div>
                <div class="min-w-0">
                    <div class="font-medium truncate">${escapeHtml(step.label || step.key)}</div>
                    <div class="text-xs text-base-content/50 truncate">${escapeHtml(step.key)}</div>
                </div>
                ${badgeForStep(step)}
            </div>
        `).join("") : '<div class="empty-panel">No active steps</div>';

        elements.draftSummary.textContent = `Draft r${state.revision || "—"} · ${summaryText(state.draft)} · Publish to make changes live`;
        const draftSteps = stepsOf(state.draft);
        elements.draftList.innerHTML = draftSteps.length ? draftSteps.map((step, index) => `
            <div class="pipeline-draft-step ${index === state.selectedIndex ? "active" : ""} ${step.enabled === false ? "disabled" : ""}" data-step-index="${index}">
                <button class="pipeline-step-main" type="button" data-select-step="${index}">
                    <span class="pipeline-step-index">${index + 1}</span>
                    <span class="min-w-0">
                        <span class="font-medium truncate block">${escapeHtml(step.label || step.key)}</span>
                        <span class="text-xs text-base-content/50 truncate block">${escapeHtml(step.key)}</span>
                    </span>
                    ${badgeForStep(step)}
                </button>
                <div class="pipeline-step-actions">
                    <button class="btn btn-ghost btn-xs" type="button" aria-label="Move ${escapeHtml(step.label || step.key)} up" data-move-step="${index}" data-direction="-1" ${index === 0 ? "disabled" : ""}>Up</button>
                    <button class="btn btn-ghost btn-xs" type="button" aria-label="Move ${escapeHtml(step.label || step.key)} down" data-move-step="${index}" data-direction="1" ${index === draftSteps.length - 1 ? "disabled" : ""}>Down</button>
                    <label class="label cursor-pointer gap-2 py-0">
                        <input class="toggle toggle-xs" type="checkbox" aria-label="Enable ${escapeHtml(step.label || step.key)}" data-toggle-step="${index}" ${step.enabled !== false ? "checked" : ""}>
                        <span class="label-text text-xs">Enabled</span>
                    </label>
                    <button class="btn btn-ghost btn-xs text-error" type="button" aria-label="Remove ${escapeHtml(step.label || step.key)}" data-delete-step="${index}">Remove</button>
                </div>
            </div>
        `).join("") : '<div class="empty-panel">No draft steps</div>';
    }

    function renderTaskOptions(state) {
        const options = state.catalog
            .filter((task) => task.import_status === "ok" && task.class_name !== "CleanupTask" && !String(task.module || "").includes(".housekeeping."))
            .map((task) => `<option value="${escapeHtml(task.id)}">${escapeHtml(task.label)} - ${escapeHtml(task.category)}</option>`);
        elements.addTaskSelect.innerHTML = '<option value="">Add task</option>' + options.join("");
    }

    function renderValidation(state) {
        const findings = state.validation && Array.isArray(state.validation.findings)
            ? state.validation.findings : [];
        const errors = findings.filter((finding) => finding.severity === "error").length;
        const warnings = findings.filter((finding) => finding.severity === "warning").length;
        elements.validationSummary.textContent = state.validation
            ? `${errors} blocking, ${warnings} warnings` : "Not validated";
        elements.publishButton.disabled = !state.validation || errors > 0 || state.dirty || state.paramsInvalid;
        elements.saveDraftButton.disabled = state.paramsInvalid;
        elements.validateButton.disabled = state.paramsInvalid;
        if (state.paramsInvalid) elements.publishHelp.textContent = "Fix invalid Params JSON before saving or publishing.";
        else if (state.dirty) elements.publishHelp.textContent = "Save Draft, then Validate, before publishing.";
        else if (!state.validation) elements.publishHelp.textContent = "Validate the saved draft before publishing.";
        else if (errors > 0) elements.publishHelp.textContent = "Resolve blocking validation findings before publishing.";
        else elements.publishHelp.textContent = "Draft is validated and ready to publish.";

        if (!state.validation) {
            elements.validationResults.innerHTML = '<div class="empty-panel">No validation run</div>';
        } else if (!findings.length) {
            elements.validationResults.innerHTML = '<div class="alert alert-success text-sm">Pipeline validation passed</div>';
        } else {
            elements.validationResults.innerHTML = `
                <div class="overflow-x-auto"><table class="table table-sm">
                    <thead><tr><th>Severity</th><th>Code</th><th>Path</th><th>Message</th></tr></thead>
                    <tbody>${findings.map((finding) => `
                        <tr>
                            <td><span class="badge badge-sm ${finding.severity === "error" ? "badge-error" : "badge-warning"}">${escapeHtml(finding.severity)}</span></td>
                            <td class="font-mono text-xs">${escapeHtml(finding.code)}</td>
                            <td class="font-mono text-xs">${escapeHtml(finding.path)}</td>
                            <td>${escapeHtml(finding.message)}</td>
                        </tr>`).join("")}</tbody>
                </table></div>`;
        }
    }

    return {
        render(state) {
            renderStepLists(state);
            renderTaskOptions(state);
            renderValidation(state);
        },
        renderValidation,
    };
}
