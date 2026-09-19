import {
    clone,
    definitionToModel,
    modelToDefinition,
    stepType,
    stepsOf,
    summaryText,
    taskKind,
    withoutHousekeeping,
} from "./pipeline-config/model.js?v=controller-modularization-4";
import { deleteParam, getParam, setParam } from "./pipeline-config/parameters.js?v=controller-modularization-4";
import { createPipelineApi } from "./pipeline-config/api.js?v=controller-modularization-4";
import { buildPipelineYamlPreview } from "./pipeline-config/preview.js?v=controller-modularization-4";
import { createPipelineWorkspaceView } from "./pipeline-config/workspace-view.js?v=controller-modularization-4";
import { createPipelineTaskEditors } from "./pipeline-config/task-editors.js?v=controller-modularization-4";
import { createPipelineResourceBrowser } from "./pipeline-config/resource-browser.js?v=controller-modularization-4";

(function () {
    "use strict";

    const workspace = document.getElementById("pipeline-config-workspace");
    if (!workspace) {
        return;
    }
    const api = createPipelineApi(window.DocFlow);

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
        templates: [],
        templateId: "",
        template: null,
        revision: 0,
        baseVersionId: null,
        versions: [],
        schemaVersions: [],
        templateDialogMode: "create",
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
    const validateButton = document.getElementById("pipeline-validate-button");
    const publishHelp = document.getElementById("pipeline-publish-help");
    const templateSelect = document.getElementById("pipeline-template-select");
    const templateName = document.getElementById("pipeline-template-name");
    const templateDescription = document.getElementById("pipeline-template-description");
    const templateDocumentType = document.getElementById("pipeline-template-document-type");
    const templateStatus = document.getElementById("pipeline-template-status");
    const templateActivate = document.getElementById("pipeline-template-activate");
    const templateCreate = document.getElementById("pipeline-template-create");
    const templateClone = document.getElementById("pipeline-template-clone");
    const revisionLabel = document.getElementById("pipeline-draft-revision");
    const baseVersionLabel = document.getElementById("pipeline-base-version");
    const versionHistoryLabel = document.getElementById("pipeline-version-history");
    const importButton = document.getElementById("pipeline-import-button");
    const importFile = document.getElementById("pipeline-import-file");
    const exportButton = document.getElementById("pipeline-export-button");
    const templateDialog = document.getElementById("pipeline-template-dialog");
    const templateForm = document.getElementById("pipeline-template-form");
    const templateDialogTitle = document.getElementById("pipeline-template-dialog-title");
    const templateDialogDescription = document.getElementById("pipeline-template-dialog-description");
    const templateDialogKey = document.getElementById("pipeline-template-dialog-key");
    const templateDialogName = document.getElementById("pipeline-template-dialog-name");
    const templateDialogCancel = document.getElementById("pipeline-template-dialog-cancel");
    const templateDialogSubmit = document.getElementById("pipeline-template-dialog-submit");
    const publishDialog = document.getElementById("pipeline-publish-dialog");
    const publishForm = document.getElementById("pipeline-publish-form");
    const publishDialogCancel = document.getElementById("pipeline-publish-dialog-cancel");
    const publishDialogConfirm = document.getElementById("pipeline-publish-dialog-confirm");
    const workspaceView = createPipelineWorkspaceView({
        activeList,
        draftList,
        activeSummary,
        draftSummary,
        validationSummary,
        validationResults,
        addTaskSelect,
        publishButton,
        saveDraftButton,
        validateButton,
        publishHelp,
    }, { escapeHtml, badgeForStep, stepsOf, summaryText });
    const {
        detailsSection,
        directoryBrowserPanel,
        isRequiredType,
        taskSpecificControls,
        unwrapOptionalType,
        withRequiredState,
    } = createPipelineTaskEditors({
        state,
        escapeHtml,
        pathAttr,
        taskKind,
        stepsOf,
        getParam,
        selectedTaskFindings,
        versionLabel: (version, kind) => window.DocFlowVersionedAdmin.versionLabel(version, kind),
    });
    const {
        createDirectoryFromBrowser,
        loadCsvMetadata,
        loadDirectoryBrowser,
        openDirectoryBrowser,
        openFileBrowser,
        selectCurrentDirectory,
        selectFile,
    } = createPipelineResourceBrowser({
        state,
        api,
        render,
        markDirty,
        paramsForSelected,
        setParamsError,
        getParam,
        setParam,
        showError: (error) => window.DocFlow.showToast(error.message, "error"),
        getNewDirectoryName: () => document.getElementById("pipeline-new-directory-name")?.value,
    });

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function templateMetadataPayload(extra = {}) {
        return {
            name: templateName.value.trim(),
            description: templateDescription.value.trim(),
            document_type: templateDocumentType.value.trim() || null,
            ...extra,
        };
    }

    function syncTemplateLifecycleControls() {
        const status = state.template?.status || "inactive";
        const hasPublishedVersion = state.versions.length > 0;
        const canActivate = Boolean(state.templateId) && hasPublishedVersion && status === "inactive";

        templateActivate.disabled = !canActivate;
        if (status === "active") {
            templateActivate.textContent = "Active for uploads";
            templateActivate.title = "This pipeline is available on Upload & Process.";
        } else if (status === "archived") {
            templateActivate.textContent = "Archived";
            templateActivate.title = "Archived templates cannot be activated.";
        } else if (!hasPublishedVersion) {
            templateActivate.textContent = "Publish before activating";
            templateActivate.title = "Publish a version before making this pipeline available on Upload & Process.";
        } else {
            templateActivate.textContent = "Activate for uploads";
            templateActivate.title = "Make this pipeline available on Upload & Process.";
        }
    }

    async function loadBindings() {
        const payload = await api.listWatchFolderBindings();
        const count = (payload.bindings || []).filter(item => item.pipeline_template_id === state.templateId && !item.retired_at).length;
        document.getElementById("pipeline-watch-summary").textContent = `${count} watch folders use this pipeline. Manage watch folders →`;
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

    function selectedStep() {
        const steps = stepsOf(state.draft);
        if (state.selectedIndex < 0 || state.selectedIndex >= steps.length) {
            state.selectedIndex = steps.length ? 0 : -1;
        }
        return steps[state.selectedIndex] || null;
    }

    function pathAttr(path) {
        return escapeHtml(JSON.stringify(path));
    }

    function parseControlValue(field) {
        const type = field.dataset.paramType || "string";
        if (type === "secret-reference") {
            const alias = field.value.trim();
            return alias ? { $secret: alias } : null;
        }
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

    function openTemplateDialog(mode) {
        const cloning = mode === "clone";
        state.templateDialogMode = cloning ? "clone" : "create";
        const sourceKey = state.template && state.template.template_key || "pipeline";
        const sourceName = state.template && state.template.name || "Pipeline";
        templateDialogTitle.textContent = cloning ? "Clone pipeline" : "New pipeline";
        templateDialogDescription.textContent = cloning
            ? "Copy the selected published pipeline into a new template and editable draft."
            : "Create a new pipeline template and editable draft.";
        templateDialogKey.value = cloning ? `${sourceKey}-copy` : "new-pipeline";
        templateDialogName.value = cloning ? `${sourceName} copy` : "New pipeline";
        templateDialogSubmit.textContent = cloning ? "Clone pipeline" : "Create pipeline";
        templateDialog.classList.remove("hidden");
        templateDialog.classList.add("flex");
        templateDialogKey.focus();
        templateDialogKey.select();
    }

    function closeTemplateDialog() {
        templateDialog.classList.add("hidden");
        templateDialog.classList.remove("flex");
    }

    function openPublishDialog() {
        if (publishButton.disabled) {
            return;
        }
        publishDialog.classList.remove("hidden");
        publishDialog.classList.add("flex");
        publishDialogConfirm.focus();
    }

    function closePublishDialog() {
        publishDialog.classList.add("hidden");
        publishDialog.classList.remove("flex");
        publishButton.focus();
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

    function captureEditorFocus() {
        const active = document.activeElement;
        if (!active || !editorBody.contains(active)) {
            return null;
        }

        const tagName = active.tagName.toLowerCase();
        let selector = tagName;
        if (active.dataset.paramAction) {
            selector += `[data-param-action="${CSS.escape(active.dataset.paramAction)}"]`;
            for (const attribute of [
                "field-key",
                "map-path",
                "old-key",
                "category-index",
                "clause-index",
                "item-key",
                "schema-kind",
                "param-path",
            ]) {
                if (active.hasAttribute(`data-${attribute}`)) {
                    selector += `[data-${attribute}="${CSS.escape(active.getAttribute(`data-${attribute}`))}"]`;
                }
            }
        } else if (active.dataset.paramPath) {
            selector += `[data-param-path="${CSS.escape(active.dataset.paramPath)}"]`;
        } else if (active.dataset.stepField) {
            selector += `[data-step-field="${CSS.escape(active.dataset.stepField)}"]`;
        } else {
            return null;
        }

        if (active.hasAttribute("type")) {
            selector += `[type="${CSS.escape(active.getAttribute("type"))}"]`;
        }
        if (["checkbox", "radio"].includes(active.type) && active.hasAttribute("value")) {
            selector += `[value="${CSS.escape(active.getAttribute("value"))}"]`;
        }

        const matches = Array.from(editorBody.querySelectorAll(selector));
        const matchIndex = Math.max(0, matches.indexOf(active));
        const hasSelection = typeof active.selectionStart === "number";
        return {
            selector,
            matchIndex,
            selectionStart: hasSelection ? active.selectionStart : null,
            selectionEnd: hasSelection ? active.selectionEnd : null,
            selectionDirection: hasSelection ? active.selectionDirection : null,
            bodyScrollLeft: editorBody.scrollLeft,
            bodyScrollTop: editorBody.scrollTop,
            windowScrollX: window.scrollX,
            windowScrollY: window.scrollY,
        };
    }

    function renderEditorWithFocusRestore() {
        const focus = captureEditorFocus();
        renderEditor();
        if (!focus) {
            return;
        }

        const matches = editorBody.querySelectorAll(focus.selector);
        const restored = matches[focus.matchIndex] || matches[0];
        if (!restored) {
            return;
        }
        const compactEditor = restored.closest("details.extraction-field-details");
        if (compactEditor) {
            compactEditor.open = true;
        }

        try {
            restored.focus({ preventScroll: true });
        } catch (error) {
            restored.focus();
        }
        if (focus.selectionStart !== null && typeof restored.setSelectionRange === "function") {
            try {
                restored.setSelectionRange(
                    focus.selectionStart,
                    focus.selectionEnd,
                    focus.selectionDirection,
                );
            } catch (error) {
                // Some input types expose selectionStart but reject setSelectionRange.
            }
        }
        editorBody.scrollLeft = focus.bodyScrollLeft;
        editorBody.scrollTop = focus.bodyScrollTop;
        window.scrollTo(focus.windowScrollX, focus.windowScrollY);
    }

    function render() {
        workspaceView.render(state);
        renderEditorWithFocusRestore();
        yamlPreview.textContent = buildPipelineYamlPreview(state.draft);
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
            GlmOcrExtractTask: { ollama_host: "http://127.0.0.1:11434", model: "glm-ocr:latest", document_instructions: "", prompt_style: "detailed", resolution_mode: "document", resolver_model: "qwen3.5:9b-q4_K_M", resolver_max_dimension: 1280, resolver_num_ctx: 18000, resolver_num_predict: 10000, resolver_max_attempts: 2, dpi: 216, num_ctx: 8192, num_predict: 2048, timeout_seconds: 300, fields: {} },
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
        const [listPayload, catalog] = await Promise.all([
            api.listTemplates(),
            api.getTaskCatalog(),
        ]);
        state.templates = listPayload.templates || [];
        if (!state.templateId || !state.templates.some((item) => item.id === state.templateId)) {
            state.templateId = state.templates.length ? state.templates[0].id : "";
        }
        templateSelect.innerHTML = '<option value="">Select a template</option>' + state.templates.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === state.templateId ? "selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.template_key)} · ${escapeHtml(item.status)}</option>`).join("");
        state.catalog = catalog.tasks || [];
        if (!state.templateId) {
            state.template = null;
            state.active = { steps: [] };
            state.draft = { steps: [] };
            state.versions = [];
            templateStatus.value = "inactive";
            templateStatus.disabled = true;
            templateClone.disabled = true;
            templateActivate.disabled = true;
            templateActivate.textContent = "Activate for uploads";
            render();
            return;
        }
        const payload = await api.getTemplate(state.templateId);
        state.template = payload.template;
        state.revision = payload.draft.revision;
        state.baseVersionId = payload.draft.base_version_id;
        state.versions = payload.versions || [];
        state.schemaVersions = payload.schema_versions || [];
        state.draft = withoutHousekeeping(definitionToModel(payload.draft.definition));
        state.active = { steps: [] };
        if (state.baseVersionId) {
            const base = await api.getVersion(state.templateId, state.baseVersionId);
            state.active = withoutHousekeeping(definitionToModel(base.version.definition));
        }
        templateName.value = state.template.name || "";
        templateDescription.value = state.template.description || "";
        templateDocumentType.value = state.template.document_type || "";
        templateStatus.value = state.template.status || "inactive";
        templateStatus.disabled = false;
        templateClone.disabled = !state.versions.length;
        syncTemplateLifecycleControls();
        revisionLabel.textContent = `Draft revision ${state.revision}`;
        baseVersionLabel.textContent = state.baseVersionId ? `Base version ${state.versions.find((item) => item.id === state.baseVersionId)?.version_number || "—"}` : "No published base";
        versionHistoryLabel.textContent = state.versions.length ? `${state.versions.length} immutable version(s); latest v${state.versions[0].version_number}` : "No published versions";
        exportButton.disabled = false;
        state.selectedIndex = stepsOf(state.draft).length ? 0 : -1;
        state.validation = null;
        state.dirty = false;
        state.paramsInvalid = false;
        state.providerModes = {};
        state.providerModeDrafts = {};
        diffPreview.textContent = "No diff loaded";
        render();
        await loadBindings();
    }

    async function saveDraft() {
        if (state.paramsInvalid) {
            window.DocFlow.showToast("Fix invalid Params JSON before saving.", "warning");
            return;
        }
        if (!state.templateId) {
            window.DocFlow.showToast("Select a pipeline template first.", "warning");
            return;
        }
        const selectedKey = selectedStep()?.key;
        const payload = await api.saveDraft(state.templateId, {
            expected_revision: state.revision,
            definition: modelToDefinition(state.draft),
        });
        state.revision = payload.draft.revision;
        state.draft = withoutHousekeeping(definitionToModel(payload.draft.definition));
        state.selectedIndex = stepsOf(state.draft).findIndex((step) => step.key === selectedKey);
        state.dirty = false;
        state.validation = null;
        window.DocFlow.showToast("Draft saved", "success");
        render();
    }

    async function validateDraftPipeline() {
        if (state.paramsInvalid) {
            window.DocFlow.showToast("Fix invalid Params JSON before validating.", "warning");
            return;
        }
        if (state.dirty) await saveDraft();
        const validation = await api.validateDraft(state.templateId);
        state.validation = validation;
        render();
    }

    async function renderPipelineDiff() {
        if (state.dirty) await saveDraft();
        const diff = await api.getDiff(state.templateId);
        diffPreview.textContent = diff.text || "No changes";
    }

    async function publishDraftPipeline() {
        if (publishButton.disabled) {
            return;
        }
        if (state.dirty) await saveDraft();
        await api.publishDraft(state.templateId, state.revision);
        window.DocFlow.showToast("Immutable pipeline version published", "success");
        await loadPipelineConfig();
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
                workspaceView.renderValidation(state);
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
        workspaceView.renderValidation(state);
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
            if (path.join(".") === "resolution_mode") {
                render();
                return;
            }
            if (path.join(".") === "reference_file") {
                loadCsvMetadata(field.value).catch(() => {});
            }
        } catch (err) {
            setParamsError(err.message || "Invalid parameter value");
        }
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
                field.dataset.fieldKey = newKey;
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
            if (baseType !== "str") {
                delete fieldConfig.choices;
                delete fieldConfig.normalizer;
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
        if (action === "field-choices") {
            const fieldConfig = getParam(params, ["fields", field.dataset.fieldKey], {});
            const choices = field.value.split(",").map((value) => value.trim()).filter(Boolean);
            if (choices.length) fieldConfig.choices = [...new Set(choices)];
            else delete fieldConfig.choices;
            setParam(params, ["fields", field.dataset.fieldKey], fieldConfig);
            markDirty();
            return true;
        }
        if (action === "field-normalizer") {
            const fieldConfig = getParam(params, ["fields", field.dataset.fieldKey], {});
            if (field.value) fieldConfig.normalizer = field.value;
            else delete fieldConfig.normalizer;
            setParam(params, ["fields", field.dataset.fieldKey], fieldConfig);
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
            if (unwrapOptionalType(itemConfig.type) !== "str") {
                delete itemConfig.choices;
                delete itemConfig.normalizer;
            }
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
        if (action === "schema-draft-order") {
            const itemConfig = state.fieldSchemaDraft[field.dataset.itemKey] || {};
            const value = Number(field.value);
            if (Number.isInteger(value) && value > 0) itemConfig.schema_order = value;
            else delete itemConfig.schema_order;
            state.fieldSchemaDraft[field.dataset.itemKey] = itemConfig;
            render();
            return true;
        }
        if (action === "schema-draft-choices") {
            const itemConfig = state.fieldSchemaDraft[field.dataset.itemKey] || {};
            const choices = field.value.split(",").map((value) => value.trim()).filter(Boolean);
            if (choices.length) itemConfig.choices = [...new Set(choices)];
            else delete itemConfig.choices;
            state.fieldSchemaDraft[field.dataset.itemKey] = itemConfig;
            render();
            return true;
        }
        if (action === "schema-draft-normalizer") {
            const itemConfig = state.fieldSchemaDraft[field.dataset.itemKey] || {};
            if (field.value) itemConfig.normalizer = field.value;
            else delete itemConfig.normalizer;
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
                field.dataset.oldKey = newKey;
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
        const liveParamField = event.target.closest("textarea[data-param-path], input[data-param-path]:not([type]), input[type='text'][data-param-path]");
        if (liveParamField) {
            updateParamControl(liveParamField);
            return;
        }

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
        if (!window.confirm("Reset this draft to the latest published version? This discards unsaved draft edits and does not change pipeline availability.")) {
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
        openPublishDialog();
    });
    publishDialogCancel.addEventListener("click", closePublishDialog);
    publishDialog.addEventListener("click", (event) => {
        if (event.target === publishDialog && !publishDialogConfirm.disabled) {
            closePublishDialog();
        }
    });
    publishDialog.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !publishDialogConfirm.disabled) {
            closePublishDialog();
        }
    });
    publishForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        publishDialogCancel.disabled = true;
        publishDialogConfirm.disabled = true;
        try {
            await publishDraftPipeline();
            closePublishDialog();
        } catch (error) {
            window.DocFlow.showToast(error.message, "error");
        } finally {
            publishDialogCancel.disabled = false;
            publishDialogConfirm.disabled = false;
        }
    });
    templateSelect.addEventListener("change", () => {
        if (state.dirty && !window.confirm("Discard unsaved draft changes and switch templates?")) {
            templateSelect.value = state.templateId;
            return;
        }
        state.templateId = templateSelect.value;
        state.template = null;
        state.versions = [];
        loadPipelineConfig().catch((error) => window.DocFlow.showToast(error.message, "error"));
    });
    templateCreate.addEventListener("click", () => {
        openTemplateDialog("create");
    });
    templateClone.addEventListener("click", () => {
        if (state.templateId) {
            openTemplateDialog("clone");
        }
    });
    templateDialogCancel.addEventListener("click", () => {
        closeTemplateDialog();
    });
    templateDialog.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeTemplateDialog();
            templateCreate.focus();
        }
    });
    templateForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!templateForm.reportValidity()) {
            return;
        }
        const templateKey = templateDialogKey.value.trim();
        const name = templateDialogName.value.trim() || templateKey;
        const cloning = state.templateDialogMode === "clone";
        if (cloning && !state.templateId) {
            closeTemplateDialog();
            return;
        }
        templateDialogSubmit.disabled = true;
        try {
            const result = cloning
                ? await api.cloneTemplate(state.templateId, templateKey, name)
                : await api.createTemplate(templateKey, name);
            closeTemplateDialog();
            state.templateId = result.template.id;
            await loadPipelineConfig();
        } catch (error) {
            window.DocFlow.showToast(error.message, "error");
        } finally {
            templateDialogSubmit.disabled = false;
        }
    });
    templateStatus.addEventListener("change", async () => {
        if (!state.templateId) return;
        try {
            await api.updateTemplate(
                state.templateId,
                templateMetadataPayload({ status: templateStatus.value }),
            );
            await loadPipelineConfig();
        } catch (error) {
            templateStatus.value = state.template.status;
            window.DocFlow.showToast(error.message, "error");
        }
    });
    templateActivate.addEventListener("click", async () => {
        if (!state.templateId || templateActivate.disabled) return;
        try {
            templateActivate.disabled = true;
            await api.updateTemplate(
                state.templateId,
                templateMetadataPayload({ status: "active" }),
            );
            window.DocFlow.showToast(
                "Pipeline activated. It is now available on Upload & Process.",
                "success",
            );
            await loadPipelineConfig();
        } catch (error) {
            window.DocFlow.showToast(error.message, "error");
            syncTemplateLifecycleControls();
        }
    });
    [templateName, templateDescription, templateDocumentType].forEach((input) => {
        input.addEventListener("change", async () => {
            if (!state.templateId) return;
            try {
                await api.updateTemplate(
                    state.templateId,
                    templateMetadataPayload(),
                );
                await loadPipelineConfig();
            } catch (error) {
                window.DocFlow.showToast(error.message, "error");
            }
        });
    });
    importButton.addEventListener("click", () => {
        if (state.templateId) importFile.click();
        else window.DocFlow.showToast("Select a pipeline template before importing.", "warning");
    });
    importFile.addEventListener("change", async () => {
        const file = importFile.files && importFile.files[0];
        if (!file || !state.templateId) return;
        try {
            await api.importDraft(state.templateId, state.revision, file);
            await loadPipelineConfig();
            window.DocFlow.showToast("Imported into the draft; nothing was published.", "success");
        } catch (error) {
            window.DocFlow.showToast(error.message, "error");
        } finally {
            importFile.value = "";
        }
    });
    exportButton.addEventListener("click", () => {
        if (state.templateId) {
            window.location.href = api.exportDraftUrl(state.templateId);
        }
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
