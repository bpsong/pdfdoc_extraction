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
        editorTab: "properties",
        editingFieldSchema: null,
        fieldSchemaKind: null,
        fieldSchemaDraft: null,
        directoryBrowser: null,
        csvMetadata: {},
        advancedParamsError: "",
        objectJsonError: "",
        removeConfirmIndex: null,
        validation: null,
        dirty: false,
        paramsInvalid: false,
        providerModes: {},
        providerModeDrafts: {},
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
    const saveDraftButton = document.getElementById("pipeline-save-draft-button");
    const publishHelp = document.getElementById("pipeline-publish-help");

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

    function withoutHousekeeping(model) {
        const copy = clone(model || { steps: [] });
        copy.steps = stepsOf(copy).filter((step) => taskKind(step) !== "housekeeping");
        return copy;
    }

    function stepType(step) {
        const moduleName = String(step.module || "");
        const className = String(step.class || "");
        if (moduleName.includes(".extraction.") || className === "ExtractPdfTask") {
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

    function kindLabel(kind) {
        const labels = {
            split: "Split",
            extract: "Extract",
            review: "Review",
            storage: "Storage",
            rules: "Rules",
            archive: "Archive",
            context: "Context",
            housekeeping: "Cleanup",
            task: "Task",
        };
        return labels[kind] || "Task";
    }

    function taskIcon(kind) {
        const icons = {
            split: "S",
            extract: "E",
            review: "R",
            storage: "D",
            rules: "M",
            archive: "A",
            context: "N",
            housekeeping: "C",
            task: "T",
        };
        return icons[kind] || "T";
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
        yamlPreview.textContent = `${renderYamlValue(redactSecretsForDisplay(draftConfigForPreview()), 0)}\n`;
    }

    function secretKey(key) {
        return /(api[_-]?key|password|secret|token|credential)/i.test(String(key || ""));
    }

    function redactSecretsForDisplay(value) {
        if (Array.isArray(value)) {
            return value.map((item) => redactSecretsForDisplay(item));
        }
        if (value && typeof value === "object") {
            const redacted = {};
            Object.entries(value).forEach(([key, item]) => {
                redacted[key] = secretKey(key) ? "[REDACTED]" : redactSecretsForDisplay(item);
            });
            return redacted;
        }
        return value;
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
            .filter((task) => task.import_status === "ok" && task.class_name !== "CleanupTask" && !String(task.module || "").includes(".housekeeping."))
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

    function taskKind(step) {
        const moduleName = String(step && step.module || "");
        const className = String(step && step.class || "");
        if (className === "LlamaCloudSplitTask" || moduleName.includes(".split.")) {
            return "split";
        }
        if (className === "ExtractPdfTask" || moduleName.includes(".extraction.")) {
            return "extract";
        }
        if (className === "ReviewGateTask" || moduleName.includes(".review.")) {
            return "review";
        }
        if (moduleName.includes(".storage.")) {
            return "storage";
        }
        if (moduleName.includes(".rules.")) {
            return "rules";
        }
        if (moduleName.includes(".archiver.")) {
            return "archive";
        }
        if (moduleName.includes(".context.")) {
            return "context";
        }
        if (moduleName.includes(".housekeeping.") || className === "CleanupTask") {
            return "housekeeping";
        }
        return "task";
    }

    function pathAttr(path) {
        return escapeHtml(JSON.stringify(path));
    }

    function getParam(params, path, fallback) {
        let current = params || {};
        for (const segment of path) {
            if (!current || typeof current !== "object" || !(segment in current)) {
                return fallback;
            }
            current = current[segment];
        }
        return current === undefined ? fallback : current;
    }

    function setParam(params, path, value) {
        let current = params;
        path.slice(0, -1).forEach((segment, index) => {
            if (!current[segment] || typeof current[segment] !== "object") {
                current[segment] = typeof path[index + 1] === "number" ? [] : {};
            }
            current = current[segment];
        });
        current[path[path.length - 1]] = value;
    }

    function deleteParam(params, path) {
        let current = params;
        path.slice(0, -1).forEach((segment) => {
            current = current && current[segment];
        });
        if (current && typeof current === "object") {
            delete current[path[path.length - 1]];
        }
    }

    function parseControlValue(field) {
        const type = field.dataset.paramType || "string";
        if (type === "checkbox") {
            return field.checked;
        }
        if (type === "number") {
            const value = Number(field.value);
            return Number.isFinite(value) ? value : 0;
        }
        if (type === "nullable-boolean") {
            if (field.value === "true") {
                return true;
            }
            if (field.value === "false") {
                return false;
            }
            return null;
        }
        if (type === "csv-list") {
            return field.value.split(",").map((item) => item.trim()).filter(Boolean);
        }
        if (type === "json") {
            return JSON.parse(field.value || "{}");
        }
        return field.value;
    }

    function controlValue(value) {
        return escapeHtml(value === null || value === undefined ? "" : value);
    }

    function numberValue(value) {
        if (typeof value === "number" && Number.isFinite(value)) {
            return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)));
        }
        if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) {
            const numeric = Number(value);
            return Number.isInteger(numeric) ? String(numeric) : String(Number(numeric.toFixed(6)));
        }
        return value === null || value === undefined ? "" : String(value);
    }

    function textControl(label, path, value, options) {
        const opts = options || {};
        const inputClass = opts.mono ? "input input-bordered input-sm font-mono" : "input input-bordered input-sm";
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <input class="${inputClass}" data-param-path="${pathAttr(path)}" ${opts.paramType ? `data-param-type="${escapeHtml(opts.paramType)}"` : ""} value="${controlValue(value)}" ${opts.readonly ? "readonly" : ""}>
                ${opts.hint ? `<span class="text-xs text-base-content/50 mt-1">${escapeHtml(opts.hint)}</span>` : ""}
                ${opts.findings || ""}
            </label>
        `;
    }

    function secretControl(label, path, value) {
        const configured = Boolean(value);
        return `
            <label class="form-control min-w-0">
                <span class="label-text">${escapeHtml(label)}</span>
                <div class="relative min-w-0">
                    <input class="input input-bordered input-sm w-full min-w-0 pr-10 font-mono" type="password" autocomplete="off" data-secret-input data-param-path="${pathAttr(path)}" value="${controlValue(value)}">
                    <button class="btn btn-ghost btn-xs btn-circle absolute right-1 top-1" type="button" aria-label="Show ${escapeHtml(label)}" title="Show ${escapeHtml(label)}" data-param-action="toggle-secret">Show</button>
                </div>
                <span class="text-xs text-base-content/50 mt-1">${configured ? "Hidden by default. Leave unchanged to keep the saved value." : "No value configured."}</span>
            </label>
        `;
    }

    function numberControl(label, path, value, attrs, findings) {
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <input class="input input-bordered input-sm" type="number" data-param-type="number" data-param-path="${pathAttr(path)}" value="${escapeHtml(numberValue(value))}" ${attrs || ""}>
                ${findings || ""}
            </label>
        `;
    }

    function checkboxControl(label, path, value, hint) {
        return `
            <label class="label cursor-pointer justify-start gap-3 rounded-lg border border-base-300 bg-base-100 px-3">
                <input class="toggle toggle-sm" type="checkbox" data-param-type="checkbox" data-param-path="${pathAttr(path)}" ${value ? "checked" : ""}>
                <span>
                    <span class="label-text block">${escapeHtml(label)}</span>
                    ${hint ? `<span class="text-xs text-base-content/50">${escapeHtml(hint)}</span>` : ""}
                </span>
            </label>
        `;
    }

    function selectControl(label, path, value, options, hint, findings, paramType) {
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <select class="select select-bordered select-sm" data-param-path="${pathAttr(path)}" ${paramType ? `data-param-type="${escapeHtml(paramType)}"` : ""}>
                    ${options.map((option) => `
                        <option value="${escapeHtml(option.value)}" ${String(value ?? "") === String(option.value) ? "selected" : ""} ${option.disabled ? "disabled" : ""}>${escapeHtml(option.label)}</option>
                    `).join("")}
                </select>
                ${hint ? `<span class="text-xs text-base-content/50 mt-1">${escapeHtml(hint)}</span>` : ""}
                ${findings || ""}
            </label>
        `;
    }

    function nullableBooleanControl(label, path, value) {
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <select class="select select-bordered select-sm" data-param-type="nullable-boolean" data-param-path="${pathAttr(path)}">
                    <option value="" ${value === null || value === undefined ? "selected" : ""}>Default</option>
                    <option value="true" ${value === true ? "selected" : ""}>Yes</option>
                    <option value="false" ${value === false ? "selected" : ""}>No</option>
                </select>
            </label>
        `;
    }

    function textareaControl(label, path, value, options) {
        const opts = options || {};
        return `
            <label class="form-control ${opts.full ? "md:col-span-2" : ""}">
                <span class="label-text">${escapeHtml(label)}</span>
                <textarea class="textarea textarea-bordered text-sm ${opts.mono ? "font-mono" : ""}" data-param-path="${pathAttr(path)}" ${opts.paramType ? `data-param-type="${escapeHtml(opts.paramType)}"` : ""}>${escapeHtml(value || "")}</textarea>
                ${opts.findings || ""}
            </label>
        `;
    }

    function directoryControl(label, path, value, options) {
        const opts = options || {};
        const current = value || "";
        return `
            <div class="directory-control">
                <label class="form-control min-w-0">
                    <span class="label-text">${escapeHtml(label)}</span>
                    <div class="join w-full">
                        <input class="input input-bordered input-sm join-item min-w-0 flex-1 font-mono" data-param-path="${pathAttr(path)}" value="${controlValue(current)}">
                        <button class="btn btn-outline btn-sm join-item" type="button" data-param-action="open-directory-browser" data-param-path="${pathAttr(path)}" data-current-path="${escapeHtml(current || ".")}">Browse</button>
                    </div>
                    ${opts.hint ? `<span class="text-xs text-base-content/50 mt-1">${escapeHtml(opts.hint)}</span>` : ""}
                    ${opts.findings || ""}
                </label>
            </div>
        `;
    }

    function fileControl(label, path, value, extensions, options) {
        const opts = options || {};
        const current = value || "";
        return `
            <div class="directory-control">
                <label class="form-control min-w-0">
                    <span class="label-text">${escapeHtml(label)}</span>
                    <div class="join w-full">
                        <input class="input input-bordered input-sm join-item min-w-0 flex-1 font-mono" data-param-path="${pathAttr(path)}" value="${controlValue(current)}">
                        <button class="btn btn-outline btn-sm join-item" type="button" data-param-action="open-file-browser" data-param-path="${pathAttr(path)}" data-current-path="${escapeHtml(current)}" data-start-path="${escapeHtml(opts.startPath || ".")}" data-extensions="${escapeHtml(extensions || "")}">Browse</button>
                    </div>
                    ${opts.hint ? `<span class="text-xs text-base-content/50 mt-1">${escapeHtml(opts.hint)}</span>` : ""}
                    ${opts.findings || ""}
                </label>
            </div>
        `;
    }

    function section(title, body) {
        return `
            <div class="rounded-lg border border-base-300 bg-base-100 p-3">
                <h3 class="text-sm font-semibold mb-3">${escapeHtml(title)}</h3>
                ${body}
            </div>
        `;
    }

    function detailsSection(title, body, open) {
        return `
            <details class="rounded-lg border border-base-300 bg-base-100" ${open ? "open" : ""}>
                <summary class="cursor-pointer px-3 py-3 text-sm font-semibold">${escapeHtml(title)}</summary>
                <div class="space-y-3 border-t border-base-300 p-3">
                    ${body}
                </div>
            </details>
        `;
    }

    function directoryBrowserPanel() {
        const browser = state.directoryBrowser;
        if (!browser || !browser.open) {
            return "";
        }
        const listing = browser.listing || {};
        const directories = Array.isArray(listing.directories) ? listing.directories : [];
        const files = Array.isArray(listing.files) ? listing.files : [];
        const fileMode = browser.mode === "file";
        return `
            <div class="directory-browser-backdrop" role="presentation">
                <aside class="directory-browser-drawer" role="dialog" aria-modal="true" aria-labelledby="directory-browser-title">
                    <header class="directory-browser-header">
                        <div class="min-w-0">
                            <h3 id="directory-browser-title" class="text-base font-semibold">${fileMode ? "Select file" : "Select output directory"}</h3>
                            <p class="mt-1 truncate font-mono text-xs text-base-content/55">${escapeHtml(listing.current || browser.current || ".")}</p>
                        </div>
                        <button class="btn btn-ghost btn-circle btn-sm" type="button" aria-label="Close directory browser" data-param-action="close-directory-browser">Close</button>
                    </header>
                    <div class="directory-browser-body">
                        ${browser.error ? `<div class="alert alert-error py-2 text-xs">${escapeHtml(browser.error)}</div>` : ""}
                        <div class="directory-browser-toolbar">
                            ${fileMode ? "" : `<button class="btn btn-outline btn-sm" type="button" data-param-action="select-current-directory" ${browser.loading ? "disabled" : ""}>Use current</button>`}
                            <button class="btn btn-ghost btn-sm" type="button" data-param-action="browse-directory-up" ${!listing.parent || browser.loading ? "disabled" : ""}>Up</button>
                        </div>
                        <div class="directory-browser-list">
                            ${browser.loading ? '<div class="empty-panel">Loading directories</div>' : ""}
                            ${!browser.loading && directories.map((entry) => `
                                <button class="directory-row" type="button" data-param-action="browse-directory" data-directory-path="${escapeHtml(entry.path)}">
                                    <span class="directory-row-icon">/</span>
                                    <span class="min-w-0 truncate">${escapeHtml(entry.name)}</span>
                                </button>
                            `).join("")}
                            ${!browser.loading && files.map((entry) => `
                                <button class="directory-row" type="button" data-param-action="select-file" data-file-path="${escapeHtml(entry.path)}">
                                    <span class="directory-row-icon">F</span>
                                    <span class="min-w-0 truncate">${escapeHtml(entry.name)}</span>
                                </button>
                            `).join("")}
                            ${!browser.loading && !directories.length && !files.length ? `<div class="empty-panel">${fileMode ? "No matching files" : "No child directories"}</div>` : ""}
                        </div>
                        ${fileMode ? "" : `<div class="directory-create-row">
                            <input class="input input-bordered input-sm min-w-0 flex-1" id="pipeline-new-directory-name" value="${controlValue(browser.newDirectory || "")}" placeholder="New folder name">
                            <button class="btn btn-outline btn-sm" type="button" data-param-action="create-directory">Create</button>
                        </div>`}
                    </div>
                    <footer class="directory-browser-footer">
                        <button class="btn btn-ghost btn-sm" type="button" data-param-action="close-directory-browser">Cancel</button>
                        ${fileMode ? "" : '<button class="btn btn-primary btn-sm" type="button" data-param-action="select-current-directory">Select</button>'}
                    </footer>
                </aside>
            </div>
        `;
    }

    function unwrapOptionalType(type) {
        const text = String(type || "str").trim();
        const match = text.match(/^Optional\[(.*)\]$/);
        return match ? match[1].trim() : text;
    }

    function isRequiredType(type) {
        const text = String(type || "str").trim();
        return !(text.startsWith("Optional[") && text.endsWith("]"));
    }

    function withRequiredState(type, required) {
        const base = unwrapOptionalType(type || "str");
        return required ? base : `Optional[${base}]`;
    }

    function extractionFieldControls(step, hint) {
        const params = step.params || {};
        const fields = params.fields && typeof params.fields === "object" && !Array.isArray(params.fields) ? params.fields : {};
        const fieldEntries = Object.entries(fields);
        const tableKeys = fieldEntries.filter(([, field]) => field && (field.is_table || unwrapOptionalType(field.type) === "List[Any]")).map(([key]) => key);
        const typeOptions = [
            { value: "str", label: "Text" },
            { value: "int", label: "Integer" },
            { value: "float", label: "Number" },
            { value: "bool", label: "Yes / No" },
            { value: "List[str]", label: "List of text" },
            { value: "List[int]", label: "List of integers" },
            { value: "List[float]", label: "List of numbers" },
            { value: "List[bool]", label: "List of yes / no" },
            { value: "Dict[str, Any]", label: "Object with defined fields" },
            { value: "List[Any]", label: "List of objects" },
        ];
        const controls = fieldEntries.map(([fieldKey, field]) => {
            const fieldValue = field && typeof field === "object" ? field : {};
            const fieldType = fieldValue.type || "str";
            const baseType = unwrapOptionalType(fieldType);
            const required = isRequiredType(fieldType);
            const isTable = baseType === "List[Any]" || Boolean(fieldValue.is_table);
            const isObject = baseType === "Dict[str, Any]";
            const tableBlocked = !isTable && tableKeys.length >= 1;
            const itemFields = fieldValue.item_fields && typeof fieldValue.item_fields === "object" ? fieldValue.item_fields : {};
            const objectFields = fieldValue.object_fields && typeof fieldValue.object_fields === "object" ? fieldValue.object_fields : {};
            const schemaFields = isTable ? itemFields : objectFields;
            const schemaControls = isTable || isObject ? `
                <div class="row-schema-summary md:col-span-2">
                    <div>
                        <div class="text-xs font-semibold">${isTable ? "Row schema" : "Object properties"}</div>
                        <div class="mt-0.5 text-xs text-base-content/55">${Object.keys(schemaFields).length} flat ${isTable ? "row fields" : "properties"} defined</div>
                    </div>
                    <button class="btn btn-outline btn-xs" type="button" data-param-action="edit-field-schema" data-field-key="${escapeHtml(fieldKey)}" data-schema-kind="${isTable ? "row" : "object"}">Edit ${isTable ? "row schema" : "object properties"}</button>
                </div>
            ` : "";
            const renderedTypeOptions = typeOptions.some((option) => option.value === baseType)
                ? typeOptions
                : [{ value: baseType, label: `Legacy type (${baseType})`, disabled: true }, ...typeOptions];
            return `
                <div class="field-editor">
                    <div class="property-field-grid">
                        <label class="form-control">
                            <span class="label-text">Field key</span>
                            <input class="input input-bordered input-sm font-mono" data-param-action="rename-extract-field" data-field-key="${escapeHtml(fieldKey)}" value="${escapeHtml(fieldKey)}">
                        </label>
                        ${textControl("Alias", ["fields", fieldKey, "alias"], fieldValue.alias || "")}
                        <label class="form-control">
                            <span class="label-text">Type</span>
                            <select class="select select-bordered select-sm" data-param-action="field-type" data-field-key="${escapeHtml(fieldKey)}" data-required="${required ? "true" : "false"}">
                                ${renderedTypeOptions.map((option) => `<option value="${escapeHtml(option.value)}" ${baseType === option.value ? "selected" : ""} ${(option.value === "List[Any]" && tableBlocked) || option.disabled ? "disabled" : ""}>${escapeHtml(option.label)}</option>`).join("")}
                            </select>
                            <span class="mt-1 text-xs text-base-content/50">Python type: ${escapeHtml(withRequiredState(baseType, required))}${isTable ? " · flat row objects" : ""}</span>
                        </label>
                        <button class="btn btn-ghost btn-square btn-sm self-end text-error" type="button" title="Remove field" data-param-action="remove-extract-field" data-field-key="${escapeHtml(fieldKey)}">Remove</button>
                    </div>
                    ${inlineFindings(step, `fields.${fieldKey}`, true)}
                    <div class="mt-3 grid gap-3 md:grid-cols-2">
                        <label class="label cursor-pointer justify-start gap-3 rounded-lg border border-base-300 px-3">
                            <input class="checkbox checkbox-sm" type="checkbox" data-param-action="field-required" data-field-key="${escapeHtml(fieldKey)}" ${required ? "checked" : ""}>
                            <span>
                                <span class="label-text block">Required field</span>
                                <span class="text-xs text-base-content/50">${required ? "Must be returned" : "May be omitted"}</span>
                            </span>
                        </label>
                        ${textareaControl("Extraction guidance", ["fields", fieldKey, "description"], fieldValue.description || "", { full: true })}
                        ${schemaControls}
                    </div>
                    ${tableBlocked ? '<div class="mt-2 text-xs text-base-content/55">Only one List of objects field can be configured.</div>' : ""}
                </div>
            `;
        }).join("");
        return `${tableKeys.length > 1 ? '<div class="alert alert-error py-2 text-xs">Only one table field is supported. Change extra fields to a scalar type.</div>' : ""}${section("Extraction fields", `
            <div class="flex justify-between items-center gap-3 mb-3">
                <p class="text-xs text-base-content/60">${escapeHtml(hint || "Define scalar fields and one optional table-style field without editing JSON.")}</p>
                <button class="btn btn-outline btn-xs" type="button" data-param-action="add-extract-field">Add field</button>
            </div>
            <div class="space-y-3">${controls || '<div class="empty-panel">No extraction fields configured</div>'}</div>
        `)}`;
    }

    function structuredFieldSchemaDrawer(step) {
        const fieldKey = state.editingFieldSchema;
        const schemaKind = state.fieldSchemaKind;
        if (!fieldKey || !schemaKind || !step) {
            return "";
        }
        const fieldConfig = getParam(step.params || {}, ["fields", fieldKey], null);
        if (!fieldConfig || typeof fieldConfig !== "object") {
            state.editingFieldSchema = null;
            state.fieldSchemaKind = null;
            state.fieldSchemaDraft = null;
            return "";
        }
        const configKey = schemaKind === "object" ? "object_fields" : "item_fields";
        const configuredFields = state.fieldSchemaDraft && typeof state.fieldSchemaDraft === "object"
            ? state.fieldSchemaDraft
            : (fieldConfig[configKey] && typeof fieldConfig[configKey] === "object" ? fieldConfig[configKey] : {});
        const fieldOptions = [
            { value: "str", label: "Text" },
            { value: "int", label: "Integer" },
            { value: "float", label: "Number" },
            { value: "bool", label: "Yes / No" },
        ];
        const rows = Object.entries(configuredFields).map(([itemKey, itemField]) => {
            const itemConfig = itemField && typeof itemField === "object" ? itemField : {};
            const baseType = fieldOptions.some((option) => option.value === unwrapOptionalType(itemConfig.type)) ? unwrapOptionalType(itemConfig.type) : "str";
            const required = isRequiredType(itemConfig.type || "str");
            return `
                <div class="row-schema-field">
                    <input class="input input-bordered input-sm min-w-0 font-mono" aria-label="Field key" data-param-action="rename-schema-draft-field" data-item-key="${escapeHtml(itemKey)}" value="${escapeHtml(itemKey)}">
                    <select class="select select-bordered select-sm min-w-0" data-param-action="schema-draft-field-type" data-item-key="${escapeHtml(itemKey)}" data-required="${required ? "true" : "false"}">
                        ${fieldOptions.map((option) => `<option value="${escapeHtml(option.value)}" ${baseType === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
                    </select>
                    <label class="row-required-toggle">
                        <input class="checkbox checkbox-primary checkbox-sm" type="checkbox" aria-label="Required field" data-param-action="schema-draft-field-required" data-item-key="${escapeHtml(itemKey)}" ${required ? "checked" : ""}>
                    </label>
                    <button class="btn btn-ghost btn-square btn-sm text-error" type="button" aria-label="Remove field" data-param-action="remove-schema-draft-field" data-item-key="${escapeHtml(itemKey)}">Remove</button>
                    <input class="input input-bordered input-sm col-span-full min-w-0" aria-label="Field alias" placeholder="Field alias" data-param-action="schema-draft-alias" data-item-key="${escapeHtml(itemKey)}" value="${controlValue(itemConfig.alias || "")}">
                    <input class="input input-bordered input-sm col-span-full min-w-0" aria-label="Field guidance" placeholder="Extraction guidance (optional)" data-param-action="schema-draft-guidance" data-item-key="${escapeHtml(itemKey)}" value="${controlValue(itemConfig.description || "")}">
                </div>
            `;
        }).join("");
        const preview = Object.fromEntries(Object.entries(configuredFields).map(([itemKey, itemField]) => [itemKey, sampleValueForType(itemField && itemField.type)]));
        const invalidKeys = Object.keys(configuredFields).some((key) => !String(key).trim()) || new Set(Object.keys(configuredFields)).size !== Object.keys(configuredFields).length;
        const isObject = schemaKind === "object";
        return `
            <div class="row-schema-backdrop" role="presentation">
                <aside class="row-schema-drawer" role="dialog" aria-modal="true" aria-labelledby="field-schema-title">
                    <header class="row-schema-header">
                        <div>
                            <h3 id="field-schema-title" class="text-base font-semibold">${isObject ? "Object properties" : "Row schema"} - <span class="font-mono">${escapeHtml(fieldKey)}</span></h3>
                            <p class="mt-1 text-xs text-base-content/55">Define the flat ${isObject ? "properties in this object" : "columns for each object in the list"}.</p>
                        </div>
                        <button class="btn btn-ghost btn-circle btn-sm" type="button" aria-label="Close field schema" data-param-action="close-field-schema">Close</button>
                    </header>
                    <div class="row-schema-body">
                        <div class="row-schema-notice"><span>${isObject ? "This is a flat object" : "Each row is a flat object"}. Nested objects or lists are not supported.</span></div>
                        <div class="row-schema-table">
                            <div class="row-schema-columns" aria-hidden="true"><span>Field key</span><span>Type</span><span>Required</span><span>Actions</span></div>
                            ${rows || '<div class="empty-panel m-3">No fields yet. Add the first field to define the object.</div>'}
                        </div>
                        ${invalidKeys ? '<div class="mt-2 text-xs text-error">Field keys must be unique and cannot be empty.</div>' : ""}
                        <button class="btn btn-outline btn-sm mt-3" type="button" data-param-action="add-schema-draft-field">Add field</button>
                        <div class="mt-8">
                            <div class="text-sm font-semibold">Object preview</div>
                            <div class="mt-1 text-xs text-base-content/55">Sample values using the configured types</div>
                            <pre class="row-schema-preview">${escapeHtml(JSON.stringify(preview, null, 2))}</pre>
                        </div>
                    </div>
                    <footer class="row-schema-footer">
                        <button class="btn btn-ghost btn-sm" type="button" data-param-action="cancel-field-schema">Cancel</button>
                        <button class="btn btn-primary btn-sm" type="button" data-param-action="save-field-schema" ${invalidKeys || !Object.keys(configuredFields).length ? "disabled" : ""}>Done</button>
                    </footer>
                </aside>
            </div>
        `;
    }

    function sampleValueForType(type) {
        const baseType = unwrapOptionalType(type);
        if (baseType === "int") {
            return 1;
        }
        if (baseType === "float") {
            return 1.25;
        }
        if (baseType === "bool") {
            return true;
        }
        return "text";
    }

    function inlineFindings(step, path, prefix) {
        const expected = `tasks.${step.key}.params.${path}`;
        const matches = selectedTaskFindings(step).filter((finding) => {
            const findingPath = String(finding.path || "");
            return prefix ? findingPath.startsWith(expected) : findingPath === expected;
        });
        return matches.map((finding) => `
            <div class="mt-1 text-xs ${finding.severity === "error" ? "text-error" : "text-warning"}">
                ${escapeHtml(finding.message || "Invalid value")}
            </div>
        `).join("");
    }

    function splitControls(step) {
        const params = step.params || {};
        const categories = Array.isArray(params.categories) ? params.categories : [];
        const failLevels = Array.isArray(params.fail_on_confidence_levels) ? params.fail_on_confidence_levels : [];
        const policy = params.allow_uncategorized || "include";
        const mode = state.providerModes[step.key] || (params.configuration_id ? "saved" : "inline");
        const policyHints = {
            include: "Keep pages that the splitter cannot classify.",
            forbid: "Treat any unclassified page as a split failure.",
            omit: "Leave unclassified pages out of generated PDFs.",
        };
        return `
            <div class="space-y-3">
                ${checkboxControl("Enable document splitting", ["enabled"], params.enabled !== false, "This runtime switch is separate from including the task in the pipeline.")}
                ${secretControl("API key", ["api_key"], params.api_key || "")}
                <label class="form-control">
                    <span class="label-text">Split configuration</span>
                    <select class="select select-bordered select-sm" data-param-action="provider-mode" data-provider-kind="split">
                        <option value="inline" ${mode === "inline" ? "selected" : ""}>Define categories here</option>
                        <option value="saved" ${mode === "saved" ? "selected" : ""}>Use saved LlamaCloud configuration</option>
                    </select>
                </label>
                ${mode === "saved" ? textControl("LlamaCloud configuration ID", ["configuration_id"], params.configuration_id || "", { mono: true, findings: inlineFindings(step, "configuration_id") }) : ""}
                ${mode === "inline" ? selectControl("When pages cannot be categorized", ["allow_uncategorized"], policy, [
                    { value: "include", label: "Keep uncategorized pages" },
                    { value: "forbid", label: "Stop the split" },
                    { value: "omit", label: "Skip uncategorized pages" },
                ], policyHints[policy]) : ""}
                ${directoryControl("Split output directory", ["split_dir"], params.split_dir || "", { hint: "Child PDFs created by this task are written here.", findings: inlineFindings(step, "split_dir") })}
                ${section("Stop on confidence levels", `
                    <p class="mb-3 text-xs text-base-content/55">The split fails when any result reports a selected confidence level.</p>
                    <div class="grid gap-2 sm:grid-cols-3">
                        ${["high", "medium", "low"].map((level) => `
                            <label class="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-2 text-sm ${failLevels.includes(level) ? "border-primary bg-primary/5" : "border-base-300"}">
                                <input class="checkbox checkbox-sm" type="checkbox" data-param-action="split-confidence-level" value="${level}" ${failLevels.includes(level) ? "checked" : ""}>
                                <span class="capitalize">${level}</span>
                            </label>
                        `).join("")}
                    </div>
                `)}
                ${checkboxControl("Stop on unknown categories", ["fail_on_unknown_category"], params.fail_on_unknown_category !== false, params.fail_on_unknown_category !== false ? "Only configured category names are accepted." : "Unknown category names are allowed.")}
                ${mode === "inline" ? section("Document categories", `
                    <div class="mb-3 flex items-start justify-between gap-3">
                        <p class="text-xs text-base-content/55">Define every document type the splitter should recognize.</p>
                        <button class="btn btn-outline btn-xs" type="button" data-param-action="add-split-category">Add category</button>
                    </div>
                    <div class="space-y-3">
                        ${categories.map((category, index) => `
                            <div class="rounded-md border border-base-300 p-3">
                                <div class="mb-2 flex items-center justify-between">
                                    <span class="text-xs font-semibold uppercase text-base-content/60">Category ${index + 1}</span>
                                    <button class="btn btn-ghost btn-xs text-error" type="button" data-param-action="remove-split-category" data-category-index="${index}">Remove</button>
                                </div>
                                <div class="space-y-3">
                                    ${textControl("Category name", ["categories", index, "name"], category && category.name || "")}
                                    ${textareaControl("What belongs in this category?", ["categories", index, "description"], category && category.description || "")}
                                </div>
                            </div>
                        `).join("") || '<div class="empty-panel">No inline categories. Provide a configuration ID or add a category.</div>'}
                    </div>
                `) : ""}
                ${textControl("Allowed category names (optional)", ["allowed_categories"], Array.isArray(params.allowed_categories) ? params.allowed_categories.join(", ") : "", { hint: mode === "saved" ? "Comma-separated local allow-list. Leave blank to accept provider category names except blank, other, or uncategorized." : "Comma-separated allow-list. Leave blank to use the category names above.", paramType: "csv-list" })}
                ${detailsSection("Advanced provider settings", `
                    <div class="grid gap-3 md:grid-cols-2">
                        ${textControl("Project ID (optional)", ["project_id"], params.project_id || "", { mono: true })}
                        ${textControl("Organization ID (optional)", ["organization_id"], params.organization_id || "", { mono: true })}
                        ${numberControl("Polling interval (seconds)", ["poll_interval_seconds"], params.poll_interval_seconds ?? 1, 'min="0.1" step="0.1"')}
                        ${numberControl("Timeout (seconds)", ["timeout_seconds"], params.timeout_seconds ?? 7200, 'min="1" step="1"')}
                    </div>
                `)}
            </div>
        `;
    }

    function extractControls(step) {
        const params = step.params || {};
        const mode = state.providerModes[step.key] || (params.configuration_id ? "saved" : "inline");
        const supportedTiers = ["agentic", "cost_effective"];
        const tier = params.tier || "agentic";
        const tierOptions = supportedTiers.includes(tier)
            ? [{ value: "agentic", label: "Agentic" }, { value: "cost_effective", label: "Cost effective" }]
            : [{ value: tier, label: `Unsupported legacy value: ${tier}` }, { value: "agentic", label: "Agentic" }, { value: "cost_effective", label: "Cost effective" }];
        return `
            <div class="space-y-3">
                ${secretControl("API key", ["api_key"], params.api_key || "")}
                <label class="form-control">
                    <span class="label-text">Extraction configuration</span>
                    <select class="select select-bordered select-sm" data-param-action="provider-mode" data-provider-kind="extract">
                        <option value="inline" ${mode === "inline" ? "selected" : ""}>Define extraction here</option>
                        <option value="saved" ${mode === "saved" ? "selected" : ""}>Use saved LlamaCloud configuration</option>
                    </select>
                </label>
                ${mode === "saved" ? textControl("LlamaCloud configuration ID", ["configuration_id"], params.configuration_id || "", { mono: true, findings: inlineFindings(step, "configuration_id") }) : ""}
                ${mode === "inline" ? `
                    <div class="grid gap-3 md:grid-cols-2">
                        ${selectControl("Tier", ["tier"], tier, tierOptions)}
                        ${selectControl("Target", ["extraction_target"], params.extraction_target || "per_doc", [
                            { value: "per_doc", label: "Per document" },
                            { value: "per_page", label: "Per page" },
                            { value: "per_table_row", label: "Per table row" },
                        ])}
                    </div>
                    ${checkboxControl("Request confidence scores", ["confidence_scores"], params.confidence_scores !== false)}
                    ${detailsSection("Advanced inline extraction settings", `
                        ${textControl("Parse tier (optional)", ["parse_tier"], params.parse_tier || "")}
                        ${selectControl("Source citations", ["cite_sources"], params.cite_sources === true ? "true" : params.cite_sources === false ? "false" : "", [
                            { value: "", label: "Use provider default" },
                            { value: "true", label: "Request citations" },
                            { value: "false", label: "Do not request citations" },
                        ], "Use provider default unless this pipeline needs an explicit setting.", "", "nullable-boolean")}
                    `)}
                ` : ""}
                ${detailsSection("Advanced provider settings", `
                    <div class="grid gap-3 md:grid-cols-2">
                        ${textControl("Project ID (optional)", ["project_id"], params.project_id || "", { mono: true })}
                        ${textControl("Organization ID (optional)", ["organization_id"], params.organization_id || "", { mono: true })}
                        ${numberControl("Polling interval (seconds)", ["poll_interval_seconds"], params.poll_interval_seconds ?? 2, 'min="0.1" step="0.1"')}
                        ${numberControl("Timeout (seconds)", ["timeout_seconds"], params.timeout_seconds ?? 1800, 'min="1" step="1"')}
                    </div>
                `)}
                ${extractionFieldControls(step, mode === "saved" ? "Define the local field mapping used to normalize saved-configuration results for review and storage." : "Define the inline provider schema and local field mapping.")}
                ${structuredFieldSchemaDrawer(step)}
            </div>
        `;
    }

    function extractionFieldNames() {
        const extract = stepsOf(state.draft).find((step) => taskKind(step) === "extract");
        const fields = extract && extract.params && extract.params.fields;
        return fields && typeof fields === "object" && !Array.isArray(fields) ? Object.keys(fields) : [];
    }

    function availableFilenameTokens() {
        return [...new Set(["id", "nanoid", "filename", "source", "original_filename", "file_path", ...extractionFieldNames()])];
    }

    function filenameBuilder(step, path, value) {
        return `
            <div class="rounded-lg border border-base-300 bg-base-100 p-3">
                ${textControl("Filename template", path, value || "", { mono: true })}
                <div class="mt-3 rounded-md bg-base-200 px-3 py-2">
                    <div class="text-xs font-semibold uppercase text-base-content/60">Preview</div>
                    <div class="mt-1 break-all font-mono text-xs">${escapeHtml(value || "No filename template yet")}</div>
                </div>
                <label class="form-control mt-3">
                    <span class="label-text text-xs font-semibold">Insert a token</span>
                    <input class="input input-bordered input-sm" data-token-search placeholder="Find a field or context token">
                </label>
                <div class="mt-2 flex flex-wrap gap-1" data-token-list>
                    ${availableFilenameTokens().map((token) => `<button class="btn btn-outline btn-xs h-auto min-h-7 font-mono" type="button" data-param-action="insert-filename-token" data-token="${escapeHtml(token)}" data-param-path="${pathAttr(path)}">{${escapeHtml(token)}}</button>`).join("")}
                </div>
                ${inlineFindings(step, path.join("."))}
            </div>
        `;
    }

    function objectJsonControl(label, path, value, hint) {
        return `
            <div>
                <label class="form-control">
                    <span class="label-text">${escapeHtml(label)}</span>
                    <textarea class="textarea textarea-bordered min-h-32 font-mono text-xs" data-object-json-editor data-object-json-path="${pathAttr(path)}">${escapeHtml(JSON.stringify(value || {}, null, 2))}</textarea>
                </label>
                ${hint ? `<div class="mt-1 text-xs text-base-content/55">${escapeHtml(hint)}</div>` : ""}
                ${state.objectJsonError ? `<div class="mt-1 text-xs text-error">${escapeHtml(state.objectJsonError)}</div>` : ""}
                <button class="btn btn-outline btn-xs mt-2" type="button" data-param-action="apply-object-json" data-param-path="${pathAttr(path)}">Apply field override</button>
            </div>
        `;
    }

    function storageControls(step) {
        const params = step.params || {};
        const isCsv = step.class === "StoreMetadataAsCsv";
        const isPdf = step.class === "StoreFileToLocaldrive";
        const dirParam = isPdf ? "files_dir" : "data_dir";
        const nested = isCsv && params.storage && typeof params.storage === "object" ? params.storage : null;
        const pathRoot = nested ? ["storage"] : [];
        const directory = nested ? nested.data_dir : params[dirParam];
        const filename = nested ? nested.filename : params.filename;
        const overrideFields = isCsv && params.extraction && params.extraction.fields && typeof params.extraction.fields === "object" ? params.extraction.fields : null;
        return `
            <div class="space-y-3">
                ${isCsv ? `<label class="flex items-start gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-3"><input class="toggle toggle-sm" type="checkbox" data-param-action="toggle-nested-storage" ${nested ? "checked" : ""}><span><span class="block text-sm font-medium">Use nested storage overrides</span><span class="mt-1 block text-xs text-base-content/55">Compatibility format: storage.data_dir and storage.filename.</span></span></label>` : ""}
                ${directoryControl(isPdf ? "PDF output directory" : "Data output directory", [...pathRoot, dirParam], directory || "", { findings: inlineFindings(step, `${pathRoot.length ? "storage." : ""}${dirParam}`) })}
                ${filenameBuilder(step, [...pathRoot, "filename"], filename || "")}
                ${isCsv ? detailsSection("CSV extraction-field override", `
                    <label class="flex items-start gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-3"><input class="toggle toggle-sm" type="checkbox" data-param-action="toggle-storage-extraction" ${overrideFields ? "checked" : ""}><span><span class="block text-sm font-medium">Use task-specific field definitions</span><span class="mt-1 block text-xs text-base-content/55">Normally the CSV task reuses fields from Extract document data.</span></span></label>
                    ${overrideFields ? objectJsonControl("Field definitions", ["extraction", "fields"], overrideFields, "Advanced compatibility setting for this storage task only.") : ""}
                `) : ""}
            </div>
        `;
    }

    function thresholdMapControl(label, hint, path, value, keyOptions) {
        const entries = Object.entries(value && typeof value === "object" ? value : {});
        return section(label, `
            <div class="mb-3 flex items-start justify-between gap-3">
                <p class="text-xs text-base-content/55">${escapeHtml(hint)}</p>
                <button class="btn btn-outline btn-xs" type="button" data-param-action="add-threshold" data-map-path="${pathAttr(path)}" data-key-options="${escapeHtml(JSON.stringify(keyOptions || []))}">Add</button>
            </div>
            <div class="space-y-2">
                ${entries.map(([key, threshold]) => `
                    <div class="threshold-row">
                        ${keyOptions && keyOptions.length ? `<label class="form-control"><span class="label-text">Field</span><select class="select select-bordered select-sm" data-param-action="rename-threshold-key" data-map-path="${pathAttr(path)}" data-old-key="${escapeHtml(key)}">${[...new Set([key, ...keyOptions])].map((option) => `<option value="${escapeHtml(option)}" ${option === key ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select></label>` : `<label class="form-control"><span class="label-text">Document type</span><input class="input input-bordered input-sm font-mono" data-param-action="rename-threshold-key" data-map-path="${pathAttr(path)}" data-old-key="${escapeHtml(key)}" value="${escapeHtml(key)}"></label>`}
                        ${numberControl("Threshold", [...path, key], threshold, 'min="0" max="1" step="0.01"')}
                        <button class="btn btn-ghost btn-sm self-end text-error" type="button" data-param-action="remove-threshold" data-map-path="${pathAttr(path)}" data-key="${escapeHtml(key)}">Remove</button>
                    </div>
                `).join("") || '<div class="empty-panel py-3">No overrides. The default threshold applies.</div>'}
            </div>
        `);
    }

    function reviewControls(step) {
        const params = step.params || {};
        const splitLevels = Array.isArray(params.split_confidence_levels_requiring_review) ? params.split_confidence_levels_requiring_review : [];
        const percent = Math.round(Number(params.confidence_threshold ?? 0.8) * 100);
        const reviewScope = params.review_scope || "low_confidence_fields";
        const reviewScopeOptions = [
            { value: "document", label: "Entire document" },
            { value: "low_confidence_fields", label: "Low-confidence fields" },
        ];
        if (!["document", "low_confidence_fields"].includes(reviewScope)) {
            reviewScopeOptions.unshift({ value: reviewScope, label: `Legacy scope: ${reviewScope}` });
        }
        return `
            <div class="space-y-3">
                <div class="rounded-lg border border-info/20 bg-info/10 p-3 text-sm">Threshold priority is field override, then document type, then the default threshold.</div>
                <fieldset class="rounded-lg border border-base-300 bg-base-100 p-3">
                    <div class="flex items-center justify-between gap-3"><legend class="text-xs">Confidence threshold</legend><label class="flex items-center gap-1 text-sm font-semibold"><input class="input input-bordered input-xs w-20 text-right" type="number" min="0" max="100" step="1" value="${percent}" data-param-action="confidence-percent"><span>%</span></label></div>
                    <input class="range range-primary range-sm mt-3" type="range" min="0" max="100" step="1" value="${percent}" data-param-action="confidence-percent" aria-label="Confidence threshold slider">
                    <p class="mt-2 text-xs text-base-content/55">Send results below ${percent}% confidence for review.</p>
                </fieldset>
                ${thresholdMapControl("Field threshold overrides", "Set a stricter or more permissive score for individual extraction fields.", ["field_threshold_overrides"], params.field_threshold_overrides, extractionFieldNames())}
                ${thresholdMapControl("Document-type thresholds", "Applied when a field has no field-specific override.", ["per_document_type_thresholds"], params.per_document_type_thresholds, [])}
                ${section("Review split confidence levels", `<p class="mb-3 text-xs text-base-content/55">Pause when the upstream split result reports a selected level.</p><div class="grid grid-cols-3 gap-2">${["high", "medium", "low"].map((level) => `<label class="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-2 text-sm ${splitLevels.includes(level) ? "border-primary bg-primary/5" : "border-base-300"}"><input class="checkbox checkbox-sm" type="checkbox" data-param-action="review-split-level" value="${level}" ${splitLevels.includes(level) ? "checked" : ""}><span class="capitalize">${level}</span></label>`).join("")}</div>`)}
                ${fileControl("Schema file (optional)", ["schema_file"], params.schema_file || "", ".yaml,.yml", { startPath: "schemas", findings: inlineFindings(step, "schema_file") })}
                ${textControl("Queue", ["queue_name"], params.queue_name || "default_review")}
                ${selectControl("Reviewer editing scope", ["review_scope"], reviewScope, reviewScopeOptions, "Review conditions below determine when review is required.")}
                ${checkboxControl("Review when confidence is missing", ["require_review_when_missing_confidence"], params.require_review_when_missing_confidence !== false)}
                ${checkboxControl("Review missing required fields", ["require_review_for_missing_required_fields"], params.require_review_for_missing_required_fields !== false, "Schema-required fields trigger review when absent.")}
                ${checkboxControl("Always require review", ["always_review"], Boolean(params.always_review), "Pause every document regardless of confidence and schema results.")}
                ${checkboxControl("Allow editing high-confidence fields", ["allow_operator_to_edit_high_confidence_fields"], params.allow_operator_to_edit_high_confidence_fields !== false, "Reviewers may correct fields that did not trigger the gate.")}
            </div>
        `;
    }

    function rulesControls(step) {
        const params = step.params || {};
        const info = state.csvMetadata[params.reference_file] || {};
        const columns = Array.isArray(info.columns) ? info.columns : [];
        const clauses = params.csv_match && Array.isArray(params.csv_match.clauses) ? params.csv_match.clauses : [];
        const contextFields = [...new Set([...extractionFieldNames(), "id", "nanoid", "filename", "source", "original_filename", "file_path"])];
        const optionHtml = (values, current) => [...new Set([current || "", ...values])].map((value) => `<option value="${escapeHtml(value)}" ${value === current ? "selected" : ""}>${escapeHtml(value || "Select...")}</option>`).join("");
        return `
            <div class="space-y-3">
                ${fileControl("Reference CSV", ["reference_file"], params.reference_file || "", ".csv", { startPath: "reference_file", findings: inlineFindings(step, "reference_file") })}
                ${columns.length ? `<div class="text-xs text-base-content/60">${columns.length} CSV columns loaded.</div>` : ""}
                <label class="form-control"><span class="label-text">Update field</span><select class="select select-bordered select-sm" data-param-path="${pathAttr(["update_field"])}">${optionHtml(columns, params.update_field || "")}</select>${inlineFindings(step, "update_field")}</label>
                ${textControl("Write value", ["write_value"], params.write_value || "")}
                <div class="rounded-lg border border-primary/20 bg-primary/5 p-3"><div class="text-xs font-semibold uppercase text-primary">Rule outcome</div><p class="mt-1 text-sm">If all ${clauses.length || "configured"} ${clauses.length === 1 ? "condition matches" : "conditions match"}, set <code class="font-semibold">${escapeHtml(params.update_field || "the selected field")}</code> to <code class="font-semibold">${escapeHtml(params.write_value || "the configured value")}</code>.</p></div>
                ${checkboxControl("Backup reference CSV before write", ["backup"], params.backup !== false)}
                ${section("Match conditions", `
                    <div class="mb-3 flex items-center justify-between gap-3"><p class="text-xs text-base-content/55">Every condition must match (AND).</p><button class="btn btn-outline btn-xs" type="button" data-param-action="add-rule-clause" ${clauses.length >= 5 ? "disabled" : ""}>Add clause</button></div>
                    <div class="space-y-2">${clauses.map((clause, index) => `
                        <div class="rounded-md border border-base-300 p-2">
                            <div class="mb-2 text-xs font-semibold text-base-content/60">Condition ${index + 1}</div>
                            <div class="rule-clause-grid">
                                <label class="form-control"><span class="label-text">CSV column</span><select class="select select-bordered select-sm" data-param-path="${pathAttr(["csv_match", "clauses", index, "column"])}">${optionHtml(columns, clause.column || "")}</select></label>
                                <label class="form-control"><span class="label-text">From context</span><select class="select select-bordered select-sm" data-param-path="${pathAttr(["csv_match", "clauses", index, "from_context"])}">${optionHtml(contextFields, clause.from_context || "")}</select></label>
                                <button class="btn btn-ghost btn-sm self-end text-error" type="button" data-param-action="remove-rule-clause" data-clause-index="${index}" ${clauses.length <= 1 ? "disabled" : ""}>Remove</button>
                            </div>
                            <div class="mt-2 max-w-xs"><label class="form-control"><span class="label-text">Comparison type</span><select class="select select-bordered select-sm" data-param-action="rule-comparison" data-clause-index="${index}"><option value="auto" ${clause.number === undefined || clause.number === null ? "selected" : ""}>Auto-detect</option><option value="text" ${clause.number === false ? "selected" : ""}>Text comparison</option><option value="number" ${clause.number === true ? "selected" : ""}>Numeric comparison</option></select></label></div>
                            ${inlineFindings(step, `csv_match.clauses[${index}]`, true)}
                        </div>
                    `).join("") || '<div class="empty-panel">Add a match condition.</div>'}</div>
                `)}
            </div>
        `;
    }

    function taskSpecificControls(step) {
        const kind = taskKind(step);
        if (kind === "split") {
            return splitControls(step);
        }
        if (kind === "extract") {
            return extractControls(step);
        }
        if (kind === "review") {
            return reviewControls(step);
        }
        if (kind === "storage") {
            return storageControls(step);
        }
        if (kind === "rules") {
            return rulesControls(step);
        }
        if (kind === "archive") {
            return `<div class="space-y-3"><div class="rounded-lg border border-info/20 bg-info/10 p-3 text-sm">The original source PDF is copied here with a safe, unique filename. The source file remains in place.</div>${directoryControl("Archive directory", ["archive_dir"], (step.params || {}).archive_dir || "", { findings: inlineFindings(step, "archive_dir") })}</div>`;
        }
        if (kind === "context") {
            return numberControl("Nanoid length", ["length"], (step.params || {}).length ?? 12, 'min="5" max="21" step="1" required', inlineFindings(step, "length"));
        }
        return '<div class="empty-panel">No task-specific form exists for this task. Use advanced params JSON below.</div>';
    }

    function selectedTaskFindings(step) {
        const findings = state.validation && Array.isArray(state.validation.findings)
            ? state.validation.findings
            : [];
        return findings.filter((finding) => {
            const path = String(finding.path || "");
            return path.startsWith(`tasks.${step.key}`) || path.startsWith(`steps.${state.selectedIndex}.`);
        });
    }

    function taskIssuesPanel(step) {
        const findings = selectedTaskFindings(step);
        if (!findings.length) {
            return '<div class="empty-panel">No validation issues for this task</div>';
        }
        return `
            <div class="space-y-2">
                ${findings.map((finding) => `
                    <div class="rounded-lg border ${finding.severity === "error" ? "border-error/40 bg-error/10" : "border-warning/40 bg-warning/10"} p-3">
                        <div class="flex flex-wrap items-center gap-2">
                            <span class="badge badge-sm ${finding.severity === "error" ? "badge-error" : "badge-warning"}">${escapeHtml(finding.severity)}</span>
                            <span class="font-mono text-xs">${escapeHtml(finding.code || "")}</span>
                        </div>
                        <div class="mt-2 text-sm">${escapeHtml(finding.message || "")}</div>
                        <div class="mt-1 font-mono text-xs text-base-content/55">${escapeHtml(finding.path || "")}</div>
                    </div>
                `).join("")}
            </div>
        `;
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
        const kind = taskKind(step);
        const taskFindings = selectedTaskFindings(step);
        const taskErrorCount = taskFindings.filter((finding) => finding.severity === "error").length;
        editorBody.innerHTML = `
            <div class="pipeline-property-shell">
                <div class="property-pane-heading">
                    <div class="flex min-w-0 items-center gap-3">
                        <span class="property-kind-icon">${escapeHtml(taskIcon(kind))}</span>
                        <div class="min-w-0">
                            <h3 class="truncate text-base font-semibold">${escapeHtml(step.label || step.key)}</h3>
                            <p class="truncate font-mono text-xs text-base-content/60">${escapeHtml(step.key)}</p>
                        </div>
                    </div>
                    <span class="badge badge-sm badge-outline">${escapeHtml(kindLabel(kind))}</span>
                </div>
                <div class="property-tabs" role="tablist" aria-label="Selected task">
                    <button class="property-tab ${state.editorTab === "properties" ? "active" : ""}" type="button" data-editor-tab="properties" role="tab" aria-selected="${state.editorTab === "properties"}">Properties</button>
                    <button class="property-tab ${state.editorTab === "issues" ? "active" : ""}" type="button" data-editor-tab="issues" role="tab" aria-selected="${state.editorTab === "issues"}">Issues${taskErrorCount ? ` (${taskErrorCount})` : ""}</button>
                </div>
                ${state.editorTab === "issues" ? taskIssuesPanel(step) : `
                    <div class="space-y-4">
                        <div class="pipeline-form-grid">
                            <label class="form-control">
                                <span class="label-text">Label</span>
                                <input class="input input-bordered input-sm" data-step-field="label" value="${escapeHtml(step.label || "")}">
                            </label>
                            <label class="form-control">
                                <span class="label-text">Key</span>
                                <input class="input input-bordered input-sm font-mono" data-step-field="key" value="${escapeHtml(step.key)}">
                            </label>
                            <label class="form-control">
                                <span class="label-text">If this task fails</span>
                                <select class="select select-bordered select-sm" data-step-field="on_error">
                                    <option value="" ${!step.on_error ? "selected" : ""}>Default runtime behavior</option>
                                    <option value="stop" ${step.on_error === "stop" ? "selected" : ""}>Stop the pipeline</option>
                                    <option value="continue" ${step.on_error === "continue" ? "selected" : ""}>Continue to the next task</option>
                                </select>
                                <span class="text-xs text-base-content/50 mt-1">${step.on_error === "continue" ? "Later tasks will run even if this task fails." : "No later tasks will run after this failure."}</span>
                            </label>
                            <label class="label cursor-pointer justify-start gap-3 rounded-lg border border-base-300 px-3 py-2">
                                <input class="toggle toggle-sm" type="checkbox" data-step-field="enabled" ${step.enabled !== false ? "checked" : ""}>
                                <span class="label-text">Enabled in pipeline</span>
                            </label>
                        </div>
                        <div class="task-control-panel">
                            <div class="mb-2 text-xs font-semibold uppercase text-base-content/60">Task-specific controls</div>
                            ${taskSpecificControls(step)}
                        </div>
                        ${detailsSection("Implementation", `
                            <div class="grid gap-3 md:grid-cols-2">
                                <label class="form-control">
                                    <span class="label-text">Module</span>
                                    <input class="input input-bordered input-sm bg-base-200 font-mono" value="${escapeHtml(step.module || "")}" readonly>
                                </label>
                                <label class="form-control">
                                    <span class="label-text">Class</span>
                                    <input class="input input-bordered input-sm bg-base-200 font-mono" value="${escapeHtml(step.class || "")}" readonly>
                                </label>
                            </div>
                        `)}
                        <details class="rounded-lg border border-base-300 bg-base-100">
                            <summary class="cursor-pointer px-3 py-3 text-sm font-semibold">Advanced params JSON</summary>
                            <div class="space-y-2 p-3 border-t border-base-300">
                                <textarea class="textarea textarea-bordered font-mono text-xs pipeline-params-editor" data-advanced-params>${escapeHtml(JSON.stringify(step.params || {}, null, 2))}</textarea>
                                <p class="text-xs text-base-content/50 mt-2">Use this only for params that do not yet have form controls.</p>
                                ${state.advancedParamsError ? `<div class="text-xs text-error">${escapeHtml(state.advancedParamsError)}</div>` : ""}
                                <button class="btn btn-outline btn-xs" type="button" data-param-action="apply-advanced-params">Apply parameters</button>
                            </div>
                        </details>
                        <div class="grid grid-cols-2 gap-2">
                            <button class="btn btn-outline btn-sm" type="button" data-param-action="duplicate-task">Duplicate</button>
                            <button class="btn btn-outline btn-error btn-sm" type="button" data-param-action="confirm-remove-task">Remove</button>
                        </div>
                        ${state.removeConfirmIndex === state.selectedIndex ? `<div class="rounded-lg border border-error/30 bg-error/10 p-3" role="alert"><div class="text-sm font-semibold">Remove ${escapeHtml(step.label || step.key)}?</div><p class="mt-1 text-xs text-base-content/65">This removes the task and its settings from the draft pipeline.</p><div class="mt-3 flex justify-end gap-2"><button class="btn btn-ghost btn-xs" type="button" data-param-action="cancel-remove-task">Cancel</button><button class="btn btn-error btn-xs" type="button" data-param-action="remove-selected-task">Confirm remove</button></div></div>` : ""}
                        ${directoryBrowserPanel()}
                    </div>
                `}
            </div>
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
        publishButton.disabled = !state.validation || errors > 0 || state.dirty || state.paramsInvalid;
        saveDraftButton.disabled = state.paramsInvalid;
        if (state.paramsInvalid) {
            publishHelp.textContent = "Fix invalid Params JSON before saving or publishing.";
        } else if (state.dirty) {
            publishHelp.textContent = "Save Draft, then Validate, before publishing.";
        } else if (!state.validation) {
            publishHelp.textContent = "Validate the saved draft before publishing.";
        } else if (errors > 0) {
            publishHelp.textContent = "Resolve blocking validation findings before publishing.";
        } else {
            publishHelp.textContent = "Draft is validated and ready to publish.";
        }

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
            .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
            .toLowerCase();
    }

    function defaultParamsForClass(className) {
        const defaults = {
            LlamaCloudSplitTask: { enabled: true, api_key: "", allow_uncategorized: "include", split_dir: "processing/split", fail_on_confidence_levels: ["low"], fail_on_unknown_category: true, allowed_categories: [], poll_interval_seconds: 1, timeout_seconds: 7200, categories: [{ name: "invoice", description: "A single invoice document." }] },
            ExtractPdfTask: { api_key: "", tier: "agentic", extraction_target: "per_doc", confidence_scores: true, poll_interval_seconds: 2, timeout_seconds: 1800, fields: {} },
            AssignNanoidTask: { length: 10 },
            StoreMetadataAsCsv: { data_dir: "data", filename: "{id}" },
            StoreMetadataAsJson: { data_dir: "data", filename: "{id}" },
            StoreFileToLocaldrive: { files_dir: "files", filename: "{id}" },
            UpdateReferenceTask: { reference_file: "reference_file/reference_file.csv", update_field: "MATCHED", write_value: "match_all", backup: true, csv_match: { type: "column_equals_all", clauses: [{ column: "", from_context: "" }] } },
            ReviewGateTask: { confidence_threshold: 0.8, per_document_type_thresholds: {}, field_threshold_overrides: {}, split_confidence_levels_requiring_review: [], require_review_when_missing_confidence: true, require_review_for_missing_required_fields: true, always_review: false, queue_name: "default_review", review_scope: "low_confidence_fields", allow_operator_to_edit_high_confidence_fields: true, resume_policy: "next_task" },
            ArchivePdfTask: { archive_dir: "archive_folder" },
        };
        return clone(defaults[className] || {});
    }

    async function loadPipelineConfig() {
        const payload = await window.DocFlow.apiGet("/api/admin/pipeline");
        state.active = withoutHousekeeping(payload.active && payload.active.model);
        state.draft = withoutHousekeeping(payload.draft ? payload.draft.model : payload.active && payload.active.model);
        state.catalog = (payload.catalog && payload.catalog.tasks) || [];
        state.selectedIndex = stepsOf(state.draft).length ? 0 : -1;
        state.validation = null;
        state.dirty = false;
        state.paramsInvalid = false;
        state.providerModes = {};
        state.providerModeDrafts = {};
        diffPreview.textContent = "No diff loaded";
        render();
    }

    async function saveDraft() {
        if (state.paramsInvalid) {
            window.DocFlow.showToast("Fix invalid Params JSON before saving.", "warning");
            return;
        }
        const payload = await window.DocFlow.apiPut("/api/admin/pipeline/draft", { model: state.draft });
        state.draft = clone(payload.draft.model);
        state.dirty = false;
        window.DocFlow.showToast("Draft saved", "success");
        render();
    }

    async function validateDraftPipeline() {
        if (state.paramsInvalid) {
            window.DocFlow.showToast("Fix invalid Params JSON before validating.", "warning");
            return;
        }
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
        if (!window.confirm("Publish this draft pipeline as the live configuration?")) {
            return;
        }
        const payload = await window.DocFlow.apiPost("/api/admin/pipeline/publish", { model: state.draft });
        state.active = clone(payload.active && payload.active.model);
        state.draft = clone(payload.active && payload.active.model);
        state.validation = payload.validation || null;
        state.dirty = false;
        state.providerModes = {};
        state.providerModeDrafts = {};
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
            params: defaultParamsForClass(selected.class_name),
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
                state.paramsInvalid = false;
            } catch (err) {
                const error = document.getElementById("pipeline-params-error");
                if (error) {
                    error.textContent = err.message || "Invalid JSON";
                    error.classList.remove("hidden");
                }
                state.paramsInvalid = true;
                renderValidation();
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

    function paramsForSelected() {
        const step = selectedStep();
        if (!step) {
            return null;
        }
        if (!step.params || typeof step.params !== "object" || Array.isArray(step.params)) {
            step.params = {};
        }
        return step.params;
    }

    function uniqueObjectKey(base, object, oldKey) {
        let key = String(base || "field").replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "field";
        const used = new Set(Object.keys(object || {}).filter((item) => item !== oldKey));
        const root = key;
        let suffix = 2;
        while (used.has(key)) {
            key = `${root}_${suffix}`;
            suffix += 1;
        }
        return key;
    }

    function setParamsError(message) {
        const error = document.getElementById("pipeline-params-error");
        if (!error) {
            return;
        }
        if (message) {
            error.textContent = message;
            error.classList.remove("hidden");
            state.paramsInvalid = true;
        } else {
            error.textContent = "";
            error.classList.add("hidden");
            state.paramsInvalid = false;
        }
        renderValidation();
    }

    function updateParamControl(field) {
        const params = paramsForSelected();
        if (!params) {
            return;
        }
        try {
            if (typeof field.checkValidity === "function" && !field.checkValidity()) {
                setParamsError(field.validationMessage || "Invalid parameter value");
                return;
            }
            const path = JSON.parse(field.dataset.paramPath || "[]");
            setParam(params, path, parseControlValue(field));
            setParamsError("");
            markDirty();
            if (path.join(".") === "reference_file") {
                loadCsvMetadata(field.value).catch(() => {});
            }
        } catch (err) {
            setParamsError(err.message || "Invalid parameter value");
        }
    }

    function browserStartPath(value) {
        const text = String(value || ".").replace(/\\/g, "/").trim();
        if (!text || /^[A-Za-z]:\//.test(text) || text.startsWith("/") || text.includes("..")) {
            return ".";
        }
        return text;
    }

    async function loadDirectoryBrowser(path) {
        if (!state.directoryBrowser) {
            return;
        }
        state.directoryBrowser.current = path || ".";
        state.directoryBrowser.loading = true;
        state.directoryBrowser.error = "";
        render();
        try {
            const endpoint = state.directoryBrowser.mode === "file" ? "/api/admin/pipeline/files" : "/api/admin/pipeline/directories";
            const extensions = state.directoryBrowser.mode === "file" ? `&extensions=${encodeURIComponent(state.directoryBrowser.extensions || "")}` : "";
            const payload = await window.DocFlow.apiGet(`${endpoint}?path=${encodeURIComponent(path || ".")}${extensions}`);
            if (!state.directoryBrowser) {
                return;
            }
            state.directoryBrowser.listing = payload;
            state.directoryBrowser.current = payload.current || path || ".";
            state.directoryBrowser.loading = false;
            state.directoryBrowser.error = "";
        } catch (error) {
            if (!state.directoryBrowser) {
                return;
            }
            state.directoryBrowser.loading = false;
            state.directoryBrowser.error = error.message || "Unable to browse directories";
        }
        render();
    }

    function openDirectoryBrowser(button) {
        let path = [];
        try {
            path = JSON.parse(button.dataset.paramPath || "[]");
        } catch (error) {
            path = [];
        }
        const current = browserStartPath(button.dataset.currentPath || getParam(paramsForSelected(), path, "."));
        state.directoryBrowser = {
            open: true,
            mode: "directory",
            path,
            current,
            listing: null,
            loading: true,
            error: "",
            newDirectory: "",
        };
        loadDirectoryBrowser(current).catch((error) => window.DocFlow.showToast(error.message, "error"));
    }

    function openFileBrowser(button) {
        let path = [];
        try {
            path = JSON.parse(button.dataset.paramPath || "[]");
        } catch (error) {
            path = [];
        }
        const currentValue = String(button.dataset.currentPath || "").replace(/\\/g, "/");
        const parent = currentValue.includes("/") ? currentValue.split("/").slice(0, -1).join("/") : button.dataset.startPath || ".";
        state.directoryBrowser = {
            open: true,
            mode: "file",
            path,
            current: browserStartPath(parent || "."),
            extensions: button.dataset.extensions || "",
            listing: null,
            loading: true,
            error: "",
        };
        loadDirectoryBrowser(state.directoryBrowser.current).catch((error) => window.DocFlow.showToast(error.message, "error"));
    }

    async function loadCsvMetadata(path) {
        if (!path) {
            return;
        }
        try {
            const payload = await window.DocFlow.apiGet(`/api/admin/pipeline/csv-metadata?path=${encodeURIComponent(path)}`);
            state.csvMetadata[path] = payload;
            render();
        } catch (error) {
            state.csvMetadata[path] = { columns: [], error: error.message || "Unable to read CSV header" };
            render();
        }
    }

    function selectFile(path) {
        const browser = state.directoryBrowser;
        const params = paramsForSelected();
        if (!browser || !params) {
            return;
        }
        setParam(params, browser.path, path);
        state.directoryBrowser = null;
        markDirty();
        if (path.toLowerCase().endsWith(".csv")) {
            loadCsvMetadata(path).catch(() => {});
        }
    }

    async function createDirectoryFromBrowser() {
        const browser = state.directoryBrowser;
        if (!browser) {
            return;
        }
        const input = document.getElementById("pipeline-new-directory-name");
        const rawName = input ? input.value.trim() : "";
        const safeName = rawName.replace(/[\\/:*?"<>|]+/g, "_").replace(/^_+|_+$/g, "");
        if (!safeName) {
            browser.error = "Enter a folder name.";
            render();
            return;
        }
        const parent = browser.listing && browser.listing.current ? browser.listing.current : browser.current || ".";
        const path = parent === "." ? safeName : `${parent}/${safeName}`;
        try {
            const payload = await window.DocFlow.apiPost("/api/admin/pipeline/directories", { path });
            await loadDirectoryBrowser(payload.path || path);
        } catch (error) {
            browser.error = error.message || "Unable to create directory";
            render();
        }
    }

    function selectCurrentDirectory() {
        const browser = state.directoryBrowser;
        const params = paramsForSelected();
        if (!browser || !params) {
            return;
        }
        const selected = browser.listing && browser.listing.current ? browser.listing.current : browser.current || ".";
        setParam(params, browser.path, selected);
        state.directoryBrowser = null;
        setParamsError("");
        markDirty();
    }

    function updateArrayToggle(path, value, checked) {
        const params = paramsForSelected();
        if (!params) {
            return;
        }
        const current = getParam(params, path, []);
        const list = Array.isArray(current) ? current.filter((item) => item !== value) : [];
        if (checked) {
            list.push(value);
        }
        setParam(params, path, list);
        markDirty();
    }

    function ensureExtractFields(params) {
        if (!params.fields || typeof params.fields !== "object" || Array.isArray(params.fields)) {
            params.fields = {};
        }
        return params.fields;
    }

    function handleParamActionClick(button) {
        const params = paramsForSelected();
        if (!params) {
            return false;
        }
        const action = button.dataset.paramAction;
        if (action === "toggle-secret") {
            const wrapper = button.parentElement;
            const input = wrapper && wrapper.querySelector("[data-secret-input]");
            if (input) {
                const visible = input.type === "text";
                input.type = visible ? "password" : "text";
                button.textContent = visible ? "Show" : "Hide";
                button.setAttribute("aria-label", `${visible ? "Show" : "Hide"} secret`);
            }
            return true;
        }
        if (action === "open-directory-browser") {
            openDirectoryBrowser(button);
            return true;
        }
        if (action === "open-file-browser") {
            openFileBrowser(button);
            return true;
        }
        if (action === "select-file") {
            selectFile(button.dataset.filePath || "");
            return true;
        }
        if (action === "close-directory-browser") {
            state.directoryBrowser = null;
            render();
            return true;
        }
        if (action === "browse-directory") {
            loadDirectoryBrowser(button.dataset.directoryPath || ".").catch((error) => window.DocFlow.showToast(error.message, "error"));
            return true;
        }
        if (action === "browse-directory-up") {
            const parent = state.directoryBrowser && state.directoryBrowser.listing && state.directoryBrowser.listing.parent;
            if (parent) {
                loadDirectoryBrowser(parent).catch((error) => window.DocFlow.showToast(error.message, "error"));
            }
            return true;
        }
        if (action === "select-current-directory") {
            selectCurrentDirectory();
            return true;
        }
        if (action === "create-directory") {
            createDirectoryFromBrowser().catch((error) => window.DocFlow.showToast(error.message, "error"));
            return true;
        }
        if (action === "add-extract-field") {
            const fields = ensureExtractFields(params);
            fields[uniqueObjectKey("new_field", fields)] = { alias: "New field", type: "str" };
            markDirty();
            return true;
        }
        if (action === "remove-extract-field") {
            const fields = ensureExtractFields(params);
            delete fields[button.dataset.fieldKey];
            markDirty();
            return true;
        }
        if (action === "add-table-field") {
            const fields = ensureExtractFields(params);
            const field = fields[button.dataset.fieldKey] || {};
            field.is_table = true;
            field.type = withRequiredState("List[Any]", isRequiredType(field.type));
            field.item_fields = field.item_fields && typeof field.item_fields === "object" ? field.item_fields : {};
            field.item_fields[uniqueObjectKey("new_field", field.item_fields)] = { alias: "New field", type: "str" };
            fields[button.dataset.fieldKey] = field;
            markDirty();
            return true;
        }
        if (action === "edit-field-schema") {
            const schemaKind = button.dataset.schemaKind === "object" ? "object" : "row";
            const configKey = schemaKind === "object" ? "object_fields" : "item_fields";
            state.editingFieldSchema = button.dataset.fieldKey;
            state.fieldSchemaKind = schemaKind;
            state.fieldSchemaDraft = clone(getParam(params, ["fields", button.dataset.fieldKey, configKey], {}));
            render();
            return true;
        }
        if (action === "close-field-schema" || action === "cancel-field-schema") {
            state.editingFieldSchema = null;
            state.fieldSchemaKind = null;
            state.fieldSchemaDraft = null;
            render();
            return true;
        }
        if (action === "save-field-schema") {
            const keys = Object.keys(state.fieldSchemaDraft || {});
            if (!keys.length || keys.some((key) => !key.trim()) || new Set(keys).size !== keys.length) {
                return true;
            }
            const configKey = state.fieldSchemaKind === "object" ? "object_fields" : "item_fields";
            setParam(params, ["fields", state.editingFieldSchema, configKey], clone(state.fieldSchemaDraft || {}));
            state.editingFieldSchema = null;
            state.fieldSchemaKind = null;
            state.fieldSchemaDraft = null;
            markDirty();
            return true;
        }
        if (action === "add-schema-draft-field") {
            const draft = state.fieldSchemaDraft || {};
            draft[uniqueObjectKey("new_field", draft)] = { alias: "New field", type: "str" };
            state.fieldSchemaDraft = draft;
            render();
            return true;
        }
        if (action === "remove-schema-draft-field") {
            delete state.fieldSchemaDraft[button.dataset.itemKey];
            render();
            return true;
        }
        if (action === "remove-table-field") {
            const field = getParam(params, ["fields", button.dataset.fieldKey], {});
            if (field && field.item_fields) {
                delete field.item_fields[button.dataset.itemKey];
            }
            markDirty();
            return true;
        }
        if (action === "add-split-category") {
            const categories = Array.isArray(params.categories) ? params.categories : [];
            categories.push({ name: "new_category", description: "" });
            params.categories = categories;
            markDirty();
            return true;
        }
        if (action === "remove-split-category") {
            const categories = Array.isArray(params.categories) ? params.categories : [];
            categories.splice(Number(button.dataset.categoryIndex), 1);
            params.categories = categories;
            markDirty();
            return true;
        }
        if (action === "insert-filename-token") {
            let path = [];
            try { path = JSON.parse(button.dataset.paramPath || "[]"); } catch (error) { path = []; }
            setParam(params, path, `${getParam(params, path, "") || ""}{${button.dataset.token || ""}}`);
            markDirty();
            return true;
        }
        if (action === "toggle-nested-storage") {
            if (button.checked) {
                params.storage = { data_dir: params.data_dir || "data", filename: params.filename || "{id}" };
                delete params.data_dir;
                delete params.filename;
            } else {
                params.data_dir = params.storage && params.storage.data_dir || "data";
                params.filename = params.storage && params.storage.filename || "{id}";
                delete params.storage;
            }
            markDirty();
            return true;
        }
        if (action === "toggle-storage-extraction") {
            if (button.checked) {
                const extractStep = stepsOf(state.draft).find((item) => taskKind(item) === "extract");
                const sourceFields = extractStep && extractStep.params && extractStep.params.fields || {};
                params.extraction = { fields: clone(sourceFields) };
            } else {
                delete params.extraction;
            }
            markDirty();
            return true;
        }
        if (action === "apply-object-json") {
            const editor = editorBody.querySelector("[data-object-json-editor]");
            try {
                const parsed = JSON.parse(editor ? editor.value : "{}");
                if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Value must be an object.");
                let path = [];
                try { path = JSON.parse(button.dataset.paramPath || "[]"); } catch (error) { path = []; }
                setParam(params, path, parsed);
                state.objectJsonError = "";
                markDirty();
            } catch (error) {
                state.objectJsonError = error.message || "Invalid JSON object.";
                render();
            }
            return true;
        }
        if (action === "add-threshold") {
            const path = JSON.parse(button.dataset.mapPath || "[]");
            const values = getParam(params, path, {});
            const options = JSON.parse(button.dataset.keyOptions || "[]");
            let key = options.find((option) => !(option in values)) || "new_key";
            key = uniqueObjectKey(key, values);
            values[key] = 0.8;
            setParam(params, path, values);
            markDirty();
            return true;
        }
        if (action === "remove-threshold") {
            const values = getParam(params, JSON.parse(button.dataset.mapPath || "[]"), {});
            delete values[button.dataset.key];
            markDirty();
            return true;
        }
        if (action === "add-rule-clause") {
            const match = params.csv_match && typeof params.csv_match === "object" ? params.csv_match : { type: "column_equals_all", clauses: [] };
            match.type = "column_equals_all";
            match.clauses = Array.isArray(match.clauses) ? match.clauses : [];
            if (match.clauses.length < 5) match.clauses.push({ column: "", from_context: "" });
            params.csv_match = match;
            markDirty();
            return true;
        }
        if (action === "remove-rule-clause") {
            const clauses = getParam(params, ["csv_match", "clauses"], []);
            if (clauses.length > 1) clauses.splice(Number(button.dataset.clauseIndex), 1);
            markDirty();
            return true;
        }
        if (action === "apply-advanced-params") {
            const editor = editorBody.querySelector("[data-advanced-params]");
            try {
                const parsed = JSON.parse(editor ? editor.value : "{}");
                if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Parameters must be a JSON object.");
                selectedStep().params = parsed;
                state.advancedParamsError = "";
                state.paramsInvalid = false;
                markDirty();
            } catch (error) {
                state.advancedParamsError = error.message || "Invalid JSON object.";
                state.paramsInvalid = true;
                render();
            }
            return true;
        }
        if (action === "duplicate-task") {
            const copy = clone(selectedStep());
            copy.key = uniqueKey(`${copy.key}_copy`);
            copy.label = `${copy.label || copy.key} copy`;
            stepsOf(state.draft).splice(state.selectedIndex + 1, 0, copy);
            state.selectedIndex += 1;
            markDirty();
            return true;
        }
        if (action === "confirm-remove-task") {
            state.removeConfirmIndex = state.selectedIndex;
            render();
            return true;
        }
        if (action === "cancel-remove-task") {
            state.removeConfirmIndex = null;
            render();
            return true;
        }
        if (action === "remove-selected-task") {
            const index = state.selectedIndex;
            state.removeConfirmIndex = null;
            deleteTask(index);
            return true;
        }
        return false;
    }

    function handleParamActionChange(field) {
        const params = paramsForSelected();
        if (!params) {
            return false;
        }
        const action = field.dataset.paramAction;
        if (action === "rename-extract-field") {
            const fields = ensureExtractFields(params);
            const oldKey = field.dataset.fieldKey;
            const newKey = uniqueObjectKey(field.value, fields, oldKey);
            if (newKey !== oldKey) {
                fields[newKey] = fields[oldKey] || { alias: "New field", type: "str" };
                delete fields[oldKey];
            }
            markDirty();
            return true;
        }
        if (action === "field-type") {
            const fieldConfig = getParam(params, ["fields", field.dataset.fieldKey], {});
            const required = field.dataset.required !== "false";
            fieldConfig.type = withRequiredState(field.value, required);
            const baseType = unwrapOptionalType(fieldConfig.type);
            fieldConfig.is_table = baseType === "List[Any]";
            if (fieldConfig.is_table && (!fieldConfig.item_fields || typeof fieldConfig.item_fields !== "object")) {
                fieldConfig.item_fields = {};
            }
            if (!fieldConfig.is_table) {
                delete fieldConfig.is_table;
                delete fieldConfig.item_fields;
            }
            if (baseType === "Dict[str, Any]" && (!fieldConfig.object_fields || typeof fieldConfig.object_fields !== "object")) {
                fieldConfig.object_fields = {};
            }
            if (baseType !== "Dict[str, Any]") {
                delete fieldConfig.object_fields;
            }
            setParam(params, ["fields", field.dataset.fieldKey], fieldConfig);
            if (baseType === "List[Any]" || baseType === "Dict[str, Any]") {
                state.editingFieldSchema = field.dataset.fieldKey;
                state.fieldSchemaKind = baseType === "List[Any]" ? "row" : "object";
                state.fieldSchemaDraft = clone(baseType === "List[Any]" ? fieldConfig.item_fields || {} : fieldConfig.object_fields || {});
            }
            markDirty();
            return true;
        }
        if (action === "field-required") {
            const fieldConfig = getParam(params, ["fields", field.dataset.fieldKey], {});
            fieldConfig.type = withRequiredState(fieldConfig.type || "str", field.checked);
            setParam(params, ["fields", field.dataset.fieldKey], fieldConfig);
            markDirty();
            return true;
        }
        if (action === "rename-schema-draft-field") {
            const itemFields = state.fieldSchemaDraft || {};
            const oldKey = field.dataset.itemKey;
            const newKey = uniqueObjectKey(field.value, itemFields, oldKey);
            if (newKey !== oldKey) {
                const oldDefaultAlias = oldKey.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
                itemFields[newKey] = itemFields[oldKey] || { alias: "New field", type: "str" };
                delete itemFields[oldKey];
                if (itemFields[newKey] && (!itemFields[newKey].alias || itemFields[newKey].alias === "New field" || itemFields[newKey].alias === oldDefaultAlias)) {
                    itemFields[newKey].alias = newKey.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
                }
            }
            state.fieldSchemaDraft = itemFields;
            render();
            return true;
        }
        if (action === "schema-draft-field-type") {
            const itemConfig = state.fieldSchemaDraft[field.dataset.itemKey] || {};
            const required = field.dataset.required !== "false";
            itemConfig.type = withRequiredState(field.value, required);
            state.fieldSchemaDraft[field.dataset.itemKey] = itemConfig;
            render();
            return true;
        }
        if (action === "schema-draft-field-required") {
            const itemConfig = state.fieldSchemaDraft[field.dataset.itemKey] || {};
            itemConfig.type = withRequiredState(itemConfig.type || "str", field.checked);
            state.fieldSchemaDraft[field.dataset.itemKey] = itemConfig;
            render();
            return true;
        }
        if (action === "schema-draft-alias") {
            const itemConfig = state.fieldSchemaDraft[field.dataset.itemKey] || {};
            itemConfig.alias = field.value;
            state.fieldSchemaDraft[field.dataset.itemKey] = itemConfig;
            render();
            return true;
        }
        if (action === "schema-draft-guidance") {
            const itemConfig = state.fieldSchemaDraft[field.dataset.itemKey] || {};
            if (field.value) itemConfig.description = field.value;
            else delete itemConfig.description;
            state.fieldSchemaDraft[field.dataset.itemKey] = itemConfig;
            render();
            return true;
        }
        if (action === "rename-threshold-key") {
            const path = JSON.parse(field.dataset.mapPath || "[]");
            const values = getParam(params, path, {});
            const oldKey = field.dataset.oldKey;
            const newKey = uniqueObjectKey(field.value, values, oldKey);
            if (newKey !== oldKey) {
                values[newKey] = values[oldKey];
                delete values[oldKey];
            }
            markDirty();
            return true;
        }
        if (action === "rule-comparison") {
            const clause = getParam(params, ["csv_match", "clauses", Number(field.dataset.clauseIndex)], {});
            if (field.value === "auto") delete clause.number;
            else clause.number = field.value === "number";
            markDirty();
            return true;
        }
        if (action === "confidence-percent") {
            const percent = Math.max(0, Math.min(100, Number(field.value)));
            params.confidence_threshold = percent / 100;
            markDirty();
            return true;
        }
        if (action === "provider-mode") {
            const step = selectedStep();
            if (!step) {
                return true;
            }
            const kind = field.dataset.providerKind;
            const draft = state.providerModeDrafts[step.key] || {};
            state.providerModes[step.key] = field.value;
            if (field.value === "saved") {
                if (kind === "split") {
                    draft.inline = {
                        categories: clone(Array.isArray(params.categories) ? params.categories : []),
                        allow_uncategorized: params.allow_uncategorized || "include",
                    };
                    delete params.categories;
                    delete params.allow_uncategorized;
                } else if (kind === "extract") {
                    draft.inline = {};
                    for (const key of ["tier", "parse_tier", "extraction_target", "cite_sources", "confidence_scores"]) {
                        if (Object.prototype.hasOwnProperty.call(params, key)) {
                            draft.inline[key] = clone(params[key]);
                            delete params[key];
                        }
                    }
                }
            } else {
                delete params.configuration_id;
                if (kind === "split") {
                    params.categories = clone(draft.inline && draft.inline.categories || [{ name: "invoice", description: "A single invoice document." }]);
                    params.allow_uncategorized = draft.inline && draft.inline.allow_uncategorized || "include";
                } else if (kind === "extract") {
                    Object.assign(params, clone(draft.inline || {
                        tier: "agentic",
                        extraction_target: "per_doc",
                        confidence_scores: true,
                    }));
                }
            }
            state.providerModeDrafts[step.key] = draft;
            markDirty();
            return true;
        }
        if (action === "split-confidence-level") {
            updateArrayToggle(["fail_on_confidence_levels"], field.value, field.checked);
            return true;
        }
        if (action === "review-split-level") {
            updateArrayToggle(["split_confidence_levels_requiring_review"], field.value, field.checked);
            return true;
        }
        return false;
    }

    workspace.addEventListener("click", (event) => {
        const actionButton = event.target.closest("[data-param-action]");
        if (actionButton && handleParamActionClick(actionButton)) {
            return;
        }

        const tabButton = event.target.closest("[data-editor-tab]");
        if (tabButton) {
            state.editorTab = tabButton.dataset.editorTab || "properties";
            render();
            return;
        }

        const selectButton = event.target.closest("[data-select-step]");
        if (selectButton) {
            state.selectedIndex = Number(selectButton.dataset.selectStep);
            state.editorTab = "properties";
            state.editingFieldSchema = null;
            state.fieldSchemaKind = null;
            state.fieldSchemaDraft = null;
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
            state.selectedIndex = Number(deleteButton.dataset.deleteStep);
            state.removeConfirmIndex = state.selectedIndex;
            state.editorTab = "properties";
            render();
        }
    });

    workspace.addEventListener("change", (event) => {
        const actionField = event.target.closest("[data-param-action]");
        if (actionField && handleParamActionChange(actionField)) {
            return;
        }

        const paramField = event.target.closest("[data-param-path]");
        if (paramField) {
            updateParamControl(paramField);
            return;
        }

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

    workspace.addEventListener("input", (event) => {
        const search = event.target.closest("[data-token-search]");
        if (!search) {
            return;
        }
        const query = search.value.trim().toLowerCase();
        const container = search.closest(".rounded-lg");
        if (!container) {
            return;
        }
        container.querySelectorAll("[data-token]").forEach((button) => {
            button.classList.toggle("hidden", query && !String(button.dataset.token || "").toLowerCase().includes(query));
        });
    });

    workspace.addEventListener("blur", (event) => {
        const field = event.target.closest("[data-step-field]");
        if (field && field.tagName === "TEXTAREA") {
            updateSelectedField(field.dataset.stepField, field.value);
        }
    }, true);

    document.getElementById("pipeline-refresh-button").addEventListener("click", () => {
        if (state.dirty && !window.confirm("Discard unsaved draft changes and refresh?")) {
            return;
        }
        loadPipelineConfig().catch((error) => window.DocFlow.showToast(error.message, "error"));
    });
    document.getElementById("pipeline-reset-button").addEventListener("click", () => {
        if (!window.confirm("Reset the draft pipeline to the active configuration?")) {
            return;
        }
        state.draft = clone(state.active);
        state.selectedIndex = stepsOf(state.draft).length ? 0 : -1;
        state.validation = null;
        state.dirty = true;
        state.paramsInvalid = false;
        state.providerModes = {};
        state.providerModeDrafts = {};
        diffPreview.textContent = "No diff loaded";
        render();
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
    window.addEventListener("beforeunload", (event) => {
        if (!state.dirty) {
            return;
        }
        event.preventDefault();
        event.returnValue = "";
    });
    document.addEventListener("click", (event) => {
        const link = event.target.closest("a[href]");
        if (!link || !state.dirty || link.target || link.href === window.location.href) {
            return;
        }
        if (!window.confirm("Leave this page and discard unsaved pipeline changes?")) {
            event.preventDefault();
        }
    });

    loadPipelineConfig().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load pipeline", "error");
    });
})();
