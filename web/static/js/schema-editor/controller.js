import { createSchemaModel, emptySchema } from "./model.js?v=controller-modularization-5d";
import { createSchemaEditorApi } from "./api.js?v=controller-modularization-5d";
import { createSchemaEditorView } from "./view.js?v=controller-modularization-5d";

(function () {
    "use strict";

    const workspace = document.getElementById("schema-editor-workspace");
    if (!workspace) {
        return;
    }
    const api = createSchemaEditorApi(window.DocFlow);

    const schemaList = document.getElementById("schema-list");
    const schemaSearchInput = document.getElementById("schema-search-input");
    const schemaCount = document.getElementById("schema-count");
    const detailTitle = document.getElementById("schema-detail-title");
    const detailHash = document.getElementById("schema-detail-hash");
    const nameInput = document.getElementById("schema-name-input");
    const titleInput = document.getElementById("schema-title-input");
    const descriptionInput = document.getElementById("schema-description-input");
    const fieldTree = document.getElementById("schema-field-tree");
    const fieldNavigation = document.getElementById("schema-field-navigation");
    const fieldOutline = document.getElementById("schema-field-outline");
    const fieldSearchInput = document.getElementById("schema-field-search");
    const fieldStatus = document.getElementById("schema-field-status");
    const yamlPreview = document.getElementById("schema-yaml-preview");
    const validationResults = document.getElementById("schema-validation-results");
    const actionGuidance = document.getElementById("schema-action-guidance");
    const warningBox = document.getElementById("schema-warning");
    const identityWarningBox = document.getElementById("schema-identity-warning");
    const errorBox = document.getElementById("schema-error");
    const createButton = document.getElementById("schema-create-button");
    const createModal = document.getElementById("schema-create-modal");
    const createForm = document.getElementById("schema-create-form");
    const createKeyInput = document.getElementById("schema-create-key");
    const createNameInput = document.getElementById("schema-create-name");
    const createCancelButton = document.getElementById("schema-create-cancel");
    const createSubmitButton = document.getElementById("schema-create-submit");
    const createErrorBox = document.getElementById("schema-create-error");
    const duplicateButton = document.getElementById("schema-duplicate-button");
    const saveButton = document.getElementById("schema-save-button");
    const validateButton = document.getElementById("schema-validate-button");
    const importButton = document.getElementById("schema-import-button");
    const importFile = document.getElementById("schema-import-file");
    const exportButton = document.getElementById("schema-export-button");
    const statusSelect = document.getElementById("schema-status-select");
    const revisionLabel = document.getElementById("schema-draft-revision");
    const latestVersionLabel = document.getElementById("schema-latest-version");
    const versionHistory = document.getElementById("schema-version-history");
    const dependencyUsage = document.getElementById("schema-dependency-usage");
    const LAST_SCHEMA_KEY = "docflow.lastSchemaTemplate";
    const fieldTypes = ["string", "number", "integer", "float", "boolean", "date", "datetime", "enum", "object", "array"];
    let schemas = [];
    let currentId = "";
    let currentName = initialSchemaName();
    let currentRevision = 0;
    let currentTemplate = null;
    let currentVersions = [];
    let currentUsage = { dependency_count: 0, dependencies: [] };
    let draft = emptySchema();
    let dirty = false;
    let schemaSearch = "";
    let fieldSearch = "";
    let pendingFindings = [];
    let localFindings = [];
    let serverFindings = [];
    let validationState = "";
    const patternExamples = new Map();
    const patternResults = new Map();

    function closeCreateModal() {
        createModal.classList.add("hidden");
        createModal.classList.remove("flex");
    }

    function readLastSchemaName() {
        try {
            return window.sessionStorage.getItem(LAST_SCHEMA_KEY) || "";
        } catch (error) {
            return "";
        }
    }

    function schemaStem(schemaName) {
        return String(schemaName || "").replace(/\.(?:ya?ml|json)$/i, "");
    }

    function initialSchemaName() {
        const routeName = workspace.dataset.schemaName || "";
        const rememberedName = readLastSchemaName();
        if (!routeName) {
            return rememberedName;
        }
        if (
            rememberedName
            && schemaStem(rememberedName) === schemaStem(routeName)
        ) {
            return rememberedName;
        }
        return routeName;
    }

    function rememberSchemaName(schemaName) {
        try {
            window.sessionStorage.setItem(LAST_SCHEMA_KEY, schemaName);
        } catch (error) {
            // The editor remains functional when browser storage is unavailable.
        }
    }

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function setBox(element, message) {
        element.textContent = message || "";
        element.classList.toggle("hidden", !message);
    }

    function combinedFindings() {
        const findings = [...pendingFindings, ...localFindings, ...serverFindings];
        return findings.filter((finding, index) => (
            findings.findIndex((candidate) => candidate.path === finding.path && candidate.message === finding.message) === index
        ));
    }

    const schemaModel = createSchemaModel(() => draft);
    const { fieldEntries, getFieldContainer, defaultField, uniqueFieldKey, findField, fieldPath } = schemaModel;
    const {
        findingId,
        pathsMatch,
        renderSchemaList,
        renderFieldRows,
        renderPreview,
        renderFieldOutline,
        renderValidationSummary,
        renderActionState,
        renderFieldTreeWithFocusRestore,
        renderMetadata,
    } = createSchemaEditorView({
        schemaList, schemaCount, fieldOutline, fieldNavigation, fieldTree, yamlPreview,
        validationResults, saveButton, validateButton, nameInput, titleInput,
        actionGuidance, detailTitle, detailHash, identityWarningBox,
        duplicateButton, exportButton, statusSelect, revisionLabel,
        latestVersionLabel, versionHistory, dependencyUsage,
    }, {
        escapeHtml, fieldEntries, fieldTypes, combinedFindings, setBox,
        getState: () => ({
            schemas, currentId, schemaSearch, draft, fieldSearch, dirty,
            validationState, patternExamples, patternResults,
            currentName, currentTemplate, currentRevision, currentVersions, currentUsage,
        }),
    });

    function markDirty() {
        dirty = true;
        serverFindings = [];
        validationState = "";
        render();
    }


    function collectClientFindings() {
        return schemaModel.collectClientFindings(nameInput.value, titleInput.value);
    }


    function focusFinding(path) {
        if (path === "name" || path === "title") {
            const input = path === "name" ? nameInput : titleInput;
            input.scrollIntoView({ behavior: "smooth", block: "center" });
            input.focus();
            return;
        }
        const input = Array.from(fieldTree.querySelectorAll("[data-field-path][data-field-prop]"))
            .find((candidate) => pathsMatch(`${candidate.dataset.fieldPath}.${candidate.dataset.fieldProp}`, path));
        if (input) {
            input.scrollIntoView({ behavior: "smooth", block: "center" });
            input.focus();
        }
    }


    async function testPattern(button) {
        const key = button.dataset.testPattern;
        const path = button.dataset.patternPath;
        const prop = button.dataset.patternProp;
        const tester = button.closest("[data-pattern-tester]");
        const exampleInput = tester.querySelector("[data-pattern-example]");
        const resultElement = tester.querySelector("[data-pattern-result]");
        const patternInput = Array.from(fieldTree.querySelectorAll("[data-field-path][data-field-prop]"))
            .find((candidate) => candidate.dataset.fieldPath === path && candidate.dataset.fieldProp === prop);
        const pattern = patternInput ? patternInput.value : "";
        const example = exampleInput.value;
        patternExamples.set(key, example);
        button.disabled = true;
        resultElement.className = "schema-pattern-result";
        resultElement.textContent = "Testing…";
        try {
            const result = await api.testPattern(pattern, example);
            serverFindings = serverFindings.filter((finding) => !pathsMatch(key, finding.path));
            let testResult;
            if (!result.valid) {
                const message = result.error || "Pattern is invalid.";
                serverFindings.push({ path: key, message });
                validationState = "invalid";
                testResult = { tone: "error", message };
            } else if (result.matches) {
                testResult = { tone: "success", message: "Example matches this pattern." };
            } else {
                testResult = { tone: "warning", message: "Example does not match this pattern." };
            }
            patternResults.set(key, testResult);
            render();
            const refreshedResult = fieldTree.querySelector(`[data-pattern-result="${CSS.escape(key)}"]`);
            if (refreshedResult) {
                refreshedResult.focus({ preventScroll: true });
            }
        } catch (error) {
            patternResults.set(key, { tone: "error", message: error.message || "Unable to test pattern." });
            resultElement.className = "schema-pattern-result schema-pattern-result-error";
            resultElement.textContent = error.message || "Unable to test pattern.";
            button.disabled = false;
        }
    }

    function showInlineFinding(input, finding) {
        if (!input || !finding) {
            return;
        }
        const id = findingId(finding.path);
        input.setAttribute("aria-invalid", "true");
        input.setAttribute("aria-describedby", id);
        let message = input.parentElement.querySelector(`#${id}`);
        if (!message) {
            message = document.createElement("span");
            message.id = id;
            message.className = "schema-field-error text-xs text-error";
            input.insertAdjacentElement("afterend", message);
        }
        message.textContent = finding.message;
    }


    function render() {
        localFindings = collectClientFindings();
        renderSchemaList();
        renderMetadata();
        renderFieldTreeWithFocusRestore();
        renderPreview();
        renderFieldOutline();
        renderActionState();
        renderValidationSummary();
    }


    function applySchemaPayload(payload) {
        currentTemplate = payload.template;
        currentId = payload.template.id;
        currentName = payload.template.schema_key;
        currentRevision = payload.draft.revision;
        currentVersions = payload.versions || [];
        currentUsage = payload.usage || { dependency_count: 0, dependencies: [] };
        rememberSchemaName(currentName);
        draft = payload.draft.schema || emptySchema();
        nameInput.value = currentName;
        titleInput.value = draft.title || "";
        descriptionInput.value = draft.description || payload.template.description || "";
        detailHash.dataset.hash = payload.draft.content_hash || "";
        statusSelect.value = payload.template.status || "inactive";
        setBox(warningBox, currentVersions.length ? "Publishing this draft creates a new immutable version. Existing pipelines keep their exact schema version." : "Publish this draft before activating it or selecting it in a pipeline.");
        dirty = false;
        pendingFindings = [];
        localFindings = [];
        serverFindings = [];
        validationState = "";
        patternExamples.clear();
        patternResults.clear();
        fieldStatus.textContent = "";
        render();
    }

    async function loadSchemas() {
        const listPayload = await api.listTemplates();
        schemas = listPayload.templates || [];
        let selected = schemas.find((schema) => schema.id === currentId)
            || schemas.find((schema) => schema.schema_key === currentName)
            || schemas[0];
        if (selected) {
            await loadSchema(selected.id);
        } else {
            currentId = "";
            render();
        }
    }

    function resolveSchemaName(requestedName) {
        if (!requestedName) {
            return "";
        }
        const exact = schemas.find((schema) => schema.name === requestedName);
        if (exact) {
            return exact.name;
        }
        const requestedStem = schemaStem(requestedName);
        const stemMatch = schemas.find(
            (schema) => schemaStem(schema.name) === requestedStem
        );
        return stemMatch ? stemMatch.name : "";
    }

    async function loadSchema(templateId) {
        setBox(errorBox, "");
        const payload = await api.getTemplate(templateId);
        applySchemaPayload(payload);
    }

    async function saveSchema() {
        syncMeta();
        localFindings = collectClientFindings();
        if (pendingFindings.length || localFindings.length) {
            validationState = "invalid";
            render();
            validationResults.focus();
            return;
        }
        if (!currentId) {
            throw new Error("Create a review form template before saving.");
        }
        const submittedKey = nameInput.value.trim();
        if (submittedKey && submittedKey !== currentName) {
            await api.updateTemplate(currentId, { schema_key: submittedKey });
            currentName = submittedKey;
        }
        const result = await api.saveDraft(currentId, currentRevision, draft);
        currentRevision = result.draft.revision;
        dirty = false;
        await loadSchemas();
        if (window.DocFlow) {
            window.DocFlow.showToast("Review form draft saved", "success");
        }
    }

    async function validateSchema() {
        syncMeta();
        localFindings = collectClientFindings();
        if (pendingFindings.length || localFindings.length) {
            serverFindings = [];
            validationState = "invalid";
            render();
            validationResults.focus();
            return;
        }
        if (dirty) {
            await saveSchema();
        }
        const result = await api.validateDraft(currentId);
        serverFindings = result.findings || [];
        validationState = result.valid ? "valid" : "invalid";
        render();
        validationResults.focus();
    }

    function syncMeta() {
        draft.title = titleInput.value.trim();
        draft.description = descriptionInput.value.trim();
        draft.fields = draft.fields || {};
    }

    function addField(path, type) {
        if (schemaModel.addField(path, type)) markDirty();
    }

    function focusFieldAction(pathText, action) {
        const row = fieldTree.querySelector(`[data-row-path="${CSS.escape(pathText)}"]`);
        const preferred = row && row.querySelector(`[data-move-direction="${action}"]`);
        const control = preferred && !preferred.disabled
            ? preferred
            : row && (row.querySelector("[data-move-field]:not([disabled])") || row.querySelector("[data-delete-field]"));
        if (control) {
            let compactEditor = control.closest("details.schema-field-details");
            while (compactEditor) {
                compactEditor.open = true;
                compactEditor = compactEditor.parentElement?.closest("details.schema-field-details");
            }
            control.focus();
        }
    }

    function announceFieldChange(message) {
        fieldStatus.textContent = "";
        window.requestAnimationFrame(() => {
            fieldStatus.textContent = message;
        });
    }

    function moveField(pathText, direction) {
        const result = schemaModel.moveField(pathText, direction);
        if (!result.ok) return false;
        markDirty();
        focusFieldAction(pathText, direction);
        announceFieldChange(`Moved ${result.fieldName} ${direction}.`);
        return true;
    }

    function updateField(pathText, prop, value) {
        const findingPath = `${pathText}.${prop}`;
        pendingFindings = pendingFindings.filter((finding) => finding.path !== findingPath);
        const result = schemaModel.updateField(pathText, prop, value);
        if (result.finding) pendingFindings.push(result.finding);
        if (!result.ok) return false;
        if (prop.endsWith("pattern")) patternResults.delete(findingPath);
        const active = document.activeElement;
        if (result.renamedPath && active?.dataset.fieldPath === pathText && active.dataset.fieldProp === "key") {
            active.dataset.fieldPath = result.renamedPath;
        }
        setBox(errorBox, "");
        markDirty();
        return true;
    }

    function deleteField(pathText) {
        const found = findField(pathText);
        if (!found.container || !found.key || !found.field) return false;
        const fieldName = found.field.label || found.field.title || found.key;
        if (!window.confirm(`Delete field "${fieldName}" from this schema draft?\n\nThe field will be permanently removed when you save the schema.`)) return false;
        const result = schemaModel.removeField(pathText);
        if (!result.ok) return false;
        markDirty();
        if (result.focusPath) {
            const nextInput = fieldTree.querySelector(`[data-row-path="${CSS.escape(result.focusPath)}"] [data-field-prop="key"]`);
            if (nextInput) {
                let compactEditor = nextInput.closest("details.schema-field-details");
                while (compactEditor) {
                    compactEditor.open = true;
                    compactEditor = compactEditor.parentElement?.closest("details.schema-field-details");
                }
                nextInput.focus();
            }
        } else {
            const addControl = result.parentPath
                ? fieldTree.querySelector(`[data-add-child="${CSS.escape(result.parentPath)}"]`)
                : document.querySelector("[data-add-field]");
            addControl?.focus();
        }
        announceFieldChange(`Deleted ${fieldName} from the schema draft.`);
        return true;
    }

    function confirmDiscardChanges() {
        return !dirty || window.confirm("Discard unsaved schema changes?");
    }

    schemaList.addEventListener("click", (event) => {
        const button = event.target.closest("[data-schema-id]");
        if (button && button.dataset.schemaId !== currentId && confirmDiscardChanges()) {
            loadSchema(button.dataset.schemaId).catch((error) => setBox(errorBox, error.message));
        }
    });

    document.querySelectorAll("[data-add-field]").forEach((button) => {
        button.addEventListener("click", () => addField([], button.dataset.addField));
    });

    fieldTree.addEventListener("click", (event) => {
        const testPatternButton = event.target.closest("[data-test-pattern]");
        if (testPatternButton) {
            testPattern(testPatternButton).catch((error) => setBox(errorBox, error.message));
            return;
        }
        const moveButton = event.target.closest("[data-move-field]");
        if (moveButton) {
            moveField(moveButton.dataset.moveField, moveButton.dataset.moveDirection);
            return;
        }
        const deleteButton = event.target.closest("[data-delete-field]");
        if (deleteButton) {
            deleteField(deleteButton.dataset.deleteField);
            return;
        }
        const addButton = event.target.closest("[data-add-child]");
        if (addButton) {
            addField(addButton.dataset.addChild.split(".").filter(Boolean), addButton.dataset.childType || "string");
        }
    });

    fieldTree.addEventListener("input", (event) => {
        const exampleInput = event.target.closest("[data-pattern-example]");
        if (!exampleInput) {
            return;
        }
        patternExamples.set(exampleInput.dataset.patternExample, exampleInput.value);
        const tester = exampleInput.closest("[data-pattern-tester]");
        const resultElement = tester.querySelector("[data-pattern-result]");
        patternResults.delete(exampleInput.dataset.patternExample);
        resultElement.className = "schema-pattern-result";
        resultElement.textContent = "";
    });

    fieldTree.addEventListener("change", (event) => {
        const input = event.target.closest("[data-field-prop]");
        if (!input) {
            return;
        }
        const value = input.type === "checkbox" ? input.checked : input.value;
        const updated = updateField(input.dataset.fieldPath, input.dataset.fieldProp, value);
        if (!updated) {
            dirty = true;
            validationState = "invalid";
            localFindings = collectClientFindings();
            const path = `${input.dataset.fieldPath}.${input.dataset.fieldProp}`;
            showInlineFinding(input, combinedFindings().find((finding) => finding.path === path));
            detailTitle.textContent = detailTitle.textContent.startsWith("* ")
                ? detailTitle.textContent
                : `* ${detailTitle.textContent}`;
            renderActionState();
            renderValidationSummary();
        }
    });

    [titleInput, descriptionInput].forEach((input) => {
        input.addEventListener("input", () => {
            syncMeta();
            markDirty();
        });
    });

    nameInput.addEventListener("input", () => {
        dirty = true;
        serverFindings = [];
        validationState = "";
        render();
    });
    schemaSearchInput.addEventListener("input", (event) => {
        schemaSearch = event.target.value || "";
        renderSchemaList();
    });
    saveButton.addEventListener("click", () => saveSchema().catch((error) => setBox(errorBox, error.message)));
    validateButton.addEventListener("click", () => validateSchema().catch((error) => setBox(errorBox, error.message)));
    createButton.addEventListener("click", () => {
        if (!confirmDiscardChanges()) {
            return;
        }
        setBox(createErrorBox, "");
        createKeyInput.value = "new-review-form";
        createNameInput.value = "New review form";
        createModal.classList.remove("hidden");
        createModal.classList.add("flex");
        createKeyInput.focus();
        createKeyInput.select();
    });
    createCancelButton.addEventListener("click", closeCreateModal);
    createModal.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeCreateModal();
            createButton.focus();
        }
    });
    createForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const schemaKey = createKeyInput.value.trim();
        const name = createNameInput.value.trim() || schemaKey;
        if (!schemaKey) {
            setBox(createErrorBox, "Stable key is required.");
            createKeyInput.focus();
            return;
        }
        setBox(createErrorBox, "");
        createSubmitButton.disabled = true;
        try {
            const result = await api.createTemplate(schemaKey, name, emptySchema());
            currentId = result.template.id;
            currentName = result.template.schema_key;
            closeCreateModal();
            await loadSchemas();
            window.DocFlow.showToast("Review form draft created", "success");
        } catch (error) {
            setBox(createErrorBox, error.message);
        } finally {
            createSubmitButton.disabled = false;
        }
    });
    duplicateButton.addEventListener("click", async () => {
        if (!currentId) {
            return;
        }
        try {
            if (dirty) await saveSchema();
            const result = await api.publishDraft(currentId, currentRevision);
            currentRevision = result.draft.revision;
            await loadSchemas();
            window.DocFlow.showToast("Immutable review form version published", "success");
        } catch (error) {
            const conflict = window.DocFlowVersionedAdmin.conflictMessage(error);
            setBox(errorBox, `${conflict.message}${conflict.reloadRequired ? " Reload before continuing." : ""}`);
        }
    });
    statusSelect.addEventListener("change", async () => {
        if (!currentId) return;
        try {
            await api.updateTemplate(currentId, { status: statusSelect.value });
            await loadSchemas();
        } catch (error) {
            setBox(errorBox, error.message);
            statusSelect.value = currentTemplate.status;
        }
    });
    importButton.addEventListener("click", () => {
        if (currentId) importFile.click();
        else window.DocFlow.showToast("Select a review form before importing.", "warning");
    });
    importFile.addEventListener("change", async () => {
        const file = importFile.files && importFile.files[0];
        if (!file || !currentId) return;
        try {
            await api.importDraft(currentId, currentRevision, file);
            await loadSchemas();
            window.DocFlow.showToast("Imported into the draft; nothing was published.", "success");
        } catch (error) {
            setBox(errorBox, error.message);
        } finally {
            importFile.value = "";
        }
    });
    exportButton.addEventListener("click", () => {
        if (!currentId) return;
        window.location.href = api.exportDraftUrl(currentId);
    });
    window.addEventListener("beforeunload", (event) => {
        if (!dirty) {
            return;
        }
        event.preventDefault();
        event.returnValue = "";
    });
    document.addEventListener("click", (event) => {
        const link = event.target.closest("a[href]");
        if (!link || !dirty || link.target || link.href === window.location.href) {
            return;
        }
        if (!window.confirm("Leave this page and discard unsaved schema changes?")) {
            event.preventDefault();
        }
    });

    fieldOutline.addEventListener("click", (event) => {
        const button = event.target.closest("[data-outline-path]");
        if (!button) {
            return;
        }
        const row = fieldTree.querySelector(`[data-row-path="${CSS.escape(button.dataset.outlinePath)}"]`);
        if (row) {
            const details = row.querySelector(".schema-field-details");
            if (details) {
                details.open = true;
            }
            row.scrollIntoView({ behavior: "smooth", block: "start" });
            const input = row.querySelector("[data-field-prop='key']");
            if (input) {
                input.focus({ preventScroll: true });
            }
        }
    });

    fieldSearchInput.addEventListener("input", (event) => {
        fieldSearch = event.target.value || "";
        renderFieldOutline();
    });

    validationResults.addEventListener("click", (event) => {
        const button = event.target.closest("[data-finding-path]");
        if (button) {
            focusFinding(button.dataset.findingPath);
        }
    });

    loadSchemas().catch((error) => setBox(errorBox, error.message));
})();
