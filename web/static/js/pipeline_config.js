(function () {
    "use strict";

    const workspace = document.getElementById("pipeline-config-workspace");
    if (!workspace) {
        return;
    }

    const state = {
        active: { steps: [] },
        draft: { steps: [] },
        catalog: [],
        selectedIndex: 0,
        validation: null,
        dirty: false,
    };

    const activeList = document.getElementById("pipeline-active-list");
    const draftList = document.getElementById("pipeline-draft-list");
    const activeSummary = document.getElementById("pipeline-active-summary");
    const draftSummary = document.getElementById("pipeline-draft-summary");
    const editorTitle = document.getElementById("pipeline-editor-title");
    const editorSubtitle = document.getElementById("pipeline-editor-subtitle");
    const editorBody = document.getElementById("pipeline-editor-body");
    const yamlPreview = document.getElementById("pipeline-yaml-preview");
    const validationSummary = document.getElementById("pipeline-validation-summary");
    const validationResults = document.getElementById("pipeline-validation-results");
    const diffPreview = document.getElementById("pipeline-diff-preview");
    const addTaskSelect = document.getElementById("pipeline-add-task-select");
    const publishButton = document.getElementById("pipeline-publish-button");

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value || {}));
    }

    function stepsOf(model) {
        return Array.isArray(model && model.steps) ? model.steps : [];
    }

    function stepType(step) {
        const moduleName = String(step.module || "");
        const className = String(step.class || "");
        if (moduleName.includes(".extraction.") || ["ExtractPdfTask", "ExtractPdfV2Task"].includes(className)) {
            return "extract";
        }
        if (moduleName.includes(".split.") || className === "LlamaCloudSplitTask") {
            return "split";
        }
        if (moduleName === "standard_step.review.review_gate" || className === "ReviewGateTask") {
            return "review";
        }
        return "optional";
    }

    function badgeForStep(step) {
        const type = stepType(step);
        if (type === "extract") {
            return '<span class="badge badge-primary badge-sm">Extract</span>';
        }
        if (type === "split") {
            return '<span class="badge badge-info badge-sm">Split</span>';
        }
        if (type === "review") {
            return '<span class="badge badge-warning badge-sm">Review</span>';
        }
        return '<span class="badge badge-ghost badge-sm">Optional</span>';
    }

    function summaryText(model) {
        const steps = stepsOf(model);
        const enabled = steps.filter((step) => step.enabled !== false).length;
        return `${enabled}/${steps.length} enabled`;
    }

    function renderYamlValue(value, depth) {
        const indent = "  ".repeat(depth);
        if (Array.isArray(value)) {
            if (!value.length) {
                return "[]";
            }
            return value.map((item) => {
                if (item && typeof item === "object") {
                    return `${indent}- ${renderYamlValue(item, depth + 1).trimStart()}`;
                }
                return `${indent}- ${scalarYaml(item)}`;
            }).join("\n");
        }
        if (value && typeof value === "object") {
            const entries = Object.entries(value);
            if (!entries.length) {
                return "{}";
            }
            return entries.map(([key, item]) => {
                if (item && typeof item === "object") {
                    return `${indent}${key}:\n${renderYamlValue(item, depth + 1)}`;
                }
                return `${indent}${key}: ${scalarYaml(item)}`;
            }).join("\n");
        }
        return scalarYaml(value);
    }

    function scalarYaml(value) {
        if (value === null || value === undefined) {
            return "null";
        }
        if (typeof value === "number" || typeof value === "boolean") {
            return String(value);
        }
        const text = String(value);
        if (!text || /[:#{}\[\],&*?|\-<>=!%@`]/.test(text) || /^\s|\s$/.test(text)) {
            return JSON.stringify(text);
        }
        return text;
    }

    function draftConfigForPreview() {
        const tasks = {};
        const pipeline = [];
        stepsOf(state.draft).forEach((step) => {
            tasks[step.key] = {
                module: step.module,
                class: step.class,
                params: step.params || {},
            };
            if (step.on_error) {
                tasks[step.key].on_error = step.on_error;
            }
            if (step.enabled !== false) {
                pipeline.push(step.key);
            }
        });
        return { tasks, pipeline };
    }

    function renderYamlPreview() {
        yamlPreview.textContent = `${renderYamlValue(draftConfigForPreview(), 0)}\n`;
    }

    function renderActiveSteps() {
        activeSummary.textContent = summaryText(state.active);
        const steps = stepsOf(state.active);
        if (!steps.length) {
            activeList.innerHTML = '<div class="empty-panel">No active steps</div>';
            return;
        }
        activeList.innerHTML = steps.map((step, index) => `
            <div class="pipeline-static-step ${step.enabled === false ? "disabled" : ""}">
                <div class="pipeline-step-index">${index + 1}</div>
                <div class="min-w-0">
                    <div class="font-medium truncate">${escapeHtml(step.label || step.key)}</div>
                    <div class="text-xs text-base-content/50 truncate">${escapeHtml(step.key)}</div>
                </div>
                ${badgeForStep(step)}
            </div>
        `).join("");
    }

    function renderDraftSteps() {
        draftSummary.textContent = summaryText(state.draft);
        const steps = stepsOf(state.draft);
        if (!steps.length) {
            draftList.innerHTML = '<div class="empty-panel">No draft steps</div>';
            return;
        }
        draftList.innerHTML = steps.map((step, index) => `
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
                    <button class="btn btn-ghost btn-xs" type="button" data-move-step="${index}" data-direction="-1" ${index === 0 ? "disabled" : ""}>Up</button>
                    <button class="btn btn-ghost btn-xs" type="button" data-move-step="${index}" data-direction="1" ${index === steps.length - 1 ? "disabled" : ""}>Down</button>
                    <label class="label cursor-pointer gap-2 py-0">
                        <input class="toggle toggle-xs" type="checkbox" data-toggle-step="${index}" ${step.enabled !== false ? "checked" : ""}>
                        <span class="label-text text-xs">Enabled</span>
                    </label>
                    <button class="btn btn-ghost btn-xs text-error" type="button" data-delete-step="${index}">Remove</button>
                </div>
            </div>
        `).join("");
    }

    function renderTaskOptions() {
        const options = state.catalog
            .filter((task) => task.import_status === "ok")
            .map((task) => `<option value="${escapeHtml(task.id)}">${escapeHtml(task.label)} - ${escapeHtml(task.category)}</option>`);
        addTaskSelect.innerHTML = '<option value="">Add task</option>' + options.join("");
    }

    function selectedStep() {
        const steps = stepsOf(state.draft);
        if (state.selectedIndex < 0 || state.selectedIndex >= steps.length) {
            state.selectedIndex = steps.length ? 0 : -1;
        }
        return steps[state.selectedIndex] || null;
    }

    function renderEditor() {
        const step = selectedStep();
        if (!step) {
            editorTitle.textContent = "Step Parameters";
            editorSubtitle.textContent = "Select a draft step";
            editorBody.innerHTML = '<div class="empty-panel">No step selected</div>';
            return;
        }
        editorTitle.textContent = step.label || step.key;
        editorSubtitle.textContent = `${step.module}.${step.class}`;
        editorBody.innerHTML = `
            <div class="pipeline-form-grid">
                <label class="form-control">
                    <span class="label-text">Key</span>
                    <input class="input input-bordered input-sm" data-step-field="key" value="${escapeHtml(step.key)}">
                </label>
                <label class="form-control">
                    <span class="label-text">Label</span>
                    <input class="input input-bordered input-sm" data-step-field="label" value="${escapeHtml(step.label || "")}">
                </label>
                <label class="form-control">
                    <span class="label-text">Module</span>
                    <input class="input input-bordered input-sm" data-step-field="module" value="${escapeHtml(step.module || "")}">
                </label>
                <label class="form-control">
                    <span class="label-text">Class</span>
                    <input class="input input-bordered input-sm" data-step-field="class" value="${escapeHtml(step.class || "")}">
                </label>
                <label class="form-control">
                    <span class="label-text">On Error</span>
                    <select class="select select-bordered select-sm" data-step-field="on_error">
                        <option value="" ${!step.on_error ? "selected" : ""}>Default</option>
                        <option value="stop" ${step.on_error === "stop" ? "selected" : ""}>Stop</option>
                        <option value="continue" ${step.on_error === "continue" ? "selected" : ""}>Continue</option>
                    </select>
                </label>
                <label class="label cursor-pointer justify-start gap-3 pt-7">
                    <input class="toggle toggle-sm" type="checkbox" data-step-field="enabled" ${step.enabled !== false ? "checked" : ""}>
                    <span class="label-text">Enabled</span>
                </label>
            </div>
            <label class="form-control">
                <span class="label-text">Params JSON</span>
                <textarea class="textarea textarea-bordered font-mono text-xs pipeline-params-editor" data-step-field="params">${escapeHtml(JSON.stringify(step.params || {}, null, 2))}</textarea>
            </label>
            <div class="alert alert-error hidden text-sm" id="pipeline-params-error"></div>
        `;
    }

    function renderValidation() {
        const findings = state.validation && Array.isArray(state.validation.findings)
            ? state.validation.findings
            : [];
        const errors = findings.filter((finding) => finding.severity === "error").length;
        const warnings = findings.filter((finding) => finding.severity === "warning").length;
        validationSummary.textContent = state.validation
            ? `${errors} blocking, ${warnings} warnings`
            : "Not validated";
        publishButton.disabled = !state.validation || errors > 0 || state.dirty;

        if (!state.validation) {
            validationResults.innerHTML = '<div class="empty-panel">No validation run</div>';
            return;
        }
        if (!findings.length) {
            validationResults.innerHTML = '<div class="alert alert-success text-sm">Pipeline validation passed</div>';
            return;
        }
        validationResults.innerHTML = `
            <div class="overflow-x-auto">
                <table class="table table-sm">
                    <thead><tr><th>Severity</th><th>Code</th><th>Path</th><th>Message</th></tr></thead>
                    <tbody>
                        ${findings.map((finding) => `
                            <tr>
                                <td><span class="badge badge-sm ${finding.severity === "error" ? "badge-error" : "badge-warning"}">${escapeHtml(finding.severity)}</span></td>
                                <td class="font-mono text-xs">${escapeHtml(finding.code)}</td>
                                <td class="font-mono text-xs">${escapeHtml(finding.path)}</td>
                                <td>${escapeHtml(finding.message)}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function render() {
        renderActiveSteps();
        renderDraftSteps();
        renderTaskOptions();
        renderEditor();
        renderYamlPreview();
        renderValidation();
    }

    function markDirty() {
        state.dirty = true;
        state.validation = null;
        render();
    }

    function uniqueKey(base, ignoreIndex) {
        const used = new Set(
            stepsOf(state.draft)
                .filter((step, index) => index !== ignoreIndex)
                .map((step) => step.key)
        );
        let key = String(base || "task").toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "task";
        const root = key;
        let index = 2;
        while (used.has(key)) {
            key = `${root}_${index}`;
            index += 1;
        }
        return key;
    }

    function keyFromClass(className) {
        return String(className || "task")
            .replace(/Task$/, "")
            .replace(/V2$/, "")
            .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
            .toLowerCase();
    }

    async function loadPipelineConfig() {
        const payload = await window.DocFlow.apiGet("/api/admin/pipeline");
        state.active = clone(payload.active && payload.active.model);
        state.draft = clone(payload.draft ? payload.draft.model : payload.active && payload.active.model);
        state.catalog = (payload.catalog && payload.catalog.tasks) || [];
        state.selectedIndex = stepsOf(state.draft).length ? 0 : -1;
        state.validation = null;
        state.dirty = false;
        diffPreview.textContent = "No diff loaded";
        render();
    }

    async function saveDraft() {
        const payload = await window.DocFlow.apiPut("/api/admin/pipeline/draft", { model: state.draft });
        state.draft = clone(payload.draft.model);
        state.dirty = false;
        window.DocFlow.showToast("Draft saved", "success");
        render();
    }

    async function validateDraftPipeline() {
        const validation = await window.DocFlow.apiPost("/api/admin/pipeline/validate", { model: state.draft });
        state.validation = validation;
        state.dirty = false;
        render();
    }

    async function renderPipelineDiff() {
        const diff = await window.DocFlow.apiPost("/api/admin/pipeline/diff", { model: state.draft });
        diffPreview.textContent = diff.text || "No changes";
    }

    async function publishDraftPipeline() {
        if (publishButton.disabled) {
            return;
        }
        const payload = await window.DocFlow.apiPost("/api/admin/pipeline/publish", { model: state.draft });
        state.active = clone(payload.active && payload.active.model);
        state.draft = clone(payload.active && payload.active.model);
        state.validation = payload.validation || null;
        state.dirty = false;
        window.DocFlow.showToast("Pipeline published", "success");
        render();
    }

    function addTaskFromCatalog() {
        const selected = state.catalog.find((task) => task.id === addTaskSelect.value);
        if (!selected) {
            return;
        }
        const key = uniqueKey(selected.configured_keys && selected.configured_keys[0] ? selected.configured_keys[0] : keyFromClass(selected.class_name));
        stepsOf(state.draft).push({
            key,
            label: selected.label,
            module: selected.module,
            class: selected.class_name,
            enabled: true,
            params: {},
            on_error: "stop",
        });
        state.selectedIndex = stepsOf(state.draft).length - 1;
        addTaskSelect.value = "";
        markDirty();
    }

    function moveTask(index, direction) {
        const steps = stepsOf(state.draft);
        const target = index + direction;
        if (target < 0 || target >= steps.length) {
            return;
        }
        [steps[index], steps[target]] = [steps[target], steps[index]];
        state.selectedIndex = target;
        markDirty();
    }

    function deleteTask(index) {
        const steps = stepsOf(state.draft);
        steps.splice(index, 1);
        state.selectedIndex = Math.min(index, steps.length - 1);
        markDirty();
    }

    function updateSelectedField(field, value) {
        const step = selectedStep();
        if (!step) {
            return;
        }
        if (field === "enabled") {
            step.enabled = Boolean(value);
        } else if (field === "params") {
            try {
                step.params = JSON.parse(value || "{}");
                const error = document.getElementById("pipeline-params-error");
                if (error) {
                    error.classList.add("hidden");
                    error.textContent = "";
                }
            } catch (err) {
                const error = document.getElementById("pipeline-params-error");
                if (error) {
                    error.textContent = err.message || "Invalid JSON";
                    error.classList.remove("hidden");
                }
                return;
            }
        } else {
            step[field] = value || (field === "on_error" ? null : "");
            if (field === "key") {
                step.key = uniqueKey(step.key, state.selectedIndex);
            }
        }
        markDirty();
    }

    workspace.addEventListener("click", (event) => {
        const selectButton = event.target.closest("[data-select-step]");
        if (selectButton) {
            state.selectedIndex = Number(selectButton.dataset.selectStep);
            render();
            return;
        }

        const moveButton = event.target.closest("[data-move-step]");
        if (moveButton) {
            moveTask(Number(moveButton.dataset.moveStep), Number(moveButton.dataset.direction));
            return;
        }

        const deleteButton = event.target.closest("[data-delete-step]");
        if (deleteButton) {
            deleteTask(Number(deleteButton.dataset.deleteStep));
        }
    });

    workspace.addEventListener("change", (event) => {
        const toggle = event.target.closest("[data-toggle-step]");
        if (toggle) {
            const step = stepsOf(state.draft)[Number(toggle.dataset.toggleStep)];
            if (step) {
                step.enabled = toggle.checked;
                markDirty();
            }
            return;
        }

        const field = event.target.closest("[data-step-field]");
        if (field) {
            const value = field.type === "checkbox" ? field.checked : field.value;
            updateSelectedField(field.dataset.stepField, value);
        }
    });

    workspace.addEventListener("blur", (event) => {
        const field = event.target.closest("[data-step-field]");
        if (field && field.tagName === "TEXTAREA") {
            updateSelectedField(field.dataset.stepField, field.value);
        }
    }, true);

    document.getElementById("pipeline-refresh-button").addEventListener("click", () => {
        loadPipelineConfig().catch((error) => window.DocFlow.showToast(error.message, "error"));
    });
    document.getElementById("pipeline-save-draft-button").addEventListener("click", () => {
        saveDraft().catch((error) => window.DocFlow.showToast(error.message, "error"));
    });
    document.getElementById("pipeline-validate-button").addEventListener("click", () => {
        validateDraftPipeline().catch((error) => window.DocFlow.showToast(error.message, "error"));
    });
    document.getElementById("pipeline-diff-button").addEventListener("click", () => {
        renderPipelineDiff().catch((error) => window.DocFlow.showToast(error.message, "error"));
    });
    document.getElementById("pipeline-add-task-button").addEventListener("click", addTaskFromCatalog);
    publishButton.addEventListener("click", () => {
        publishDraftPipeline().catch((error) => window.DocFlow.showToast(error.message, "error"));
    });

    loadPipelineConfig().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load pipeline", "error");
    });
})();
