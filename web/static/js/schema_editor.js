(function () {
    "use strict";

    const workspace = document.getElementById("schema-editor-workspace");
    if (!workspace) {
        return;
    }

    const schemaList = document.getElementById("schema-list");
    const schemaSearchInput = document.getElementById("schema-search-input");
    const schemaCount = document.getElementById("schema-count");
    const detailTitle = document.getElementById("schema-detail-title");
    const detailHash = document.getElementById("schema-detail-hash");
    const nameInput = document.getElementById("schema-name-input");
    const titleInput = document.getElementById("schema-title-input");
    const descriptionInput = document.getElementById("schema-description-input");
    const fieldTree = document.getElementById("schema-field-tree");
    const fieldOutline = document.getElementById("schema-field-outline");
    const fieldStatus = document.getElementById("schema-field-status");
    const yamlPreview = document.getElementById("schema-yaml-preview");
    const validationResults = document.getElementById("schema-validation-results");
    const actionGuidance = document.getElementById("schema-action-guidance");
    const warningBox = document.getElementById("schema-warning");
    const errorBox = document.getElementById("schema-error");
    const createButton = document.getElementById("schema-create-button");
    const duplicateButton = document.getElementById("schema-duplicate-button");
    const saveButton = document.getElementById("schema-save-button");
    const validateButton = document.getElementById("schema-validate-button");
    const LAST_SCHEMA_KEY = "docflow.lastSchemaName";
    const fieldTypes = ["string", "number", "integer", "float", "boolean", "date", "datetime", "enum", "object", "array"];
    let schemas = [];
    let currentName = initialSchemaName();
    let draft = emptySchema();
    let dirty = false;
    let schemaSearch = "";
    let pendingFindings = [];
    let localFindings = [];
    let serverFindings = [];
    let validationState = "";
    const patternExamples = new Map();
    const patternResults = new Map();

    function emptySchema() {
        return { title: "", description: "", fields: {} };
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

    function findingId(path) {
        return `schema-finding-${String(path).replace(/[^a-zA-Z0-9_-]+/g, "-")}`;
    }

    function combinedFindings() {
        const findings = [...pendingFindings, ...localFindings, ...serverFindings];
        return findings.filter((finding, index) => (
            findings.findIndex((candidate) => candidate.path === finding.path && candidate.message === finding.message) === index
        ));
    }

    function pathsMatch(controlPath, findingPath) {
        return controlPath === findingPath || controlPath === findingPath.replace(/\.items\./g, ".");
    }

    function findingFor(path, prop) {
        const findingPath = prop ? `${path}.${prop}` : path;
        return combinedFindings().find((finding) => pathsMatch(findingPath, finding.path)) || null;
    }

    function fieldErrorMarkup(path, prop) {
        const finding = findingFor(path, prop);
        if (!finding) {
            return "";
        }
        return `<span id="${findingId(finding.path)}" class="schema-field-error text-xs text-error">${escapeHtml(finding.message)}</span>`;
    }

    function invalidAttributes(path, prop) {
        const finding = findingFor(path, prop);
        return finding
            ? ` aria-invalid="true" aria-describedby="${findingId(finding.path)}"`
            : "";
    }

    function patternTester(path, prop, value) {
        const key = `${path}.${prop}`;
        const result = patternResults.get(key);
        const resultClass = result ? ` schema-pattern-result-${result.tone}` : "";
        return `
            <div class="schema-pattern-control">
                ${fieldControl(path, prop, "Pattern", value)}
                <div class="schema-pattern-tester" data-pattern-tester="${escapeHtml(key)}">
                    <label class="form-control">
                        <span class="label-text">Example value</span>
                        <input class="input input-bordered input-xs" type="text" data-pattern-example="${escapeHtml(key)}" value="${escapeHtml(patternExamples.get(key) || "")}" placeholder="Value to test">
                    </label>
                    <button class="btn btn-outline btn-xs" type="button" data-test-pattern="${escapeHtml(key)}" data-pattern-path="${escapeHtml(path)}" data-pattern-prop="${escapeHtml(prop)}">Test pattern</button>
                    <span class="schema-pattern-result${resultClass}" data-pattern-result="${escapeHtml(key)}" role="status" aria-live="polite" tabindex="-1">${escapeHtml(result ? result.message : "")}</span>
                </div>
            </div>
        `;
    }

    function fieldEntries(container) {
        return Object.entries(container || {}).filter(([, config]) => config && typeof config === "object");
    }

    function getFieldContainer(path) {
        let container = draft.fields;
        for (const key of path) {
            const field = container[key];
            if (!field) {
                return null;
            }
            if (field.type === "array") {
                field.items = field.items || { type: "string" };
                if (field.items.type !== "object") {
                    field.items = { type: "object", properties: {} };
                }
                field.items.properties = field.items.properties || {};
                container = field.items.properties;
            } else {
                field.properties = field.properties || {};
                container = field.properties;
            }
        }
        return container;
    }

    function defaultField(type) {
        if (type === "object") {
            return { type, label: "Object", required: false, properties: {} };
        }
        if (type === "array") {
            return { type, label: "Items", required: false, items: { type: "string" } };
        }
        if (type === "enum") {
            return { type, label: "Status", required: false, choices: ["new", "approved"] };
        }
        return { type, label: type.replace("_", " "), required: false };
    }

    function uniqueFieldKey(container, base) {
        let key = base;
        let index = 2;
        while (container[key]) {
            key = `${base}_${index}`;
            index += 1;
        }
        return key;
    }

    function markDirty() {
        dirty = true;
        serverFindings = [];
        validationState = "";
        render();
    }

    function renderSchemaList() {
        schemaCount.textContent = String(schemas.length);
        if (!schemas.length) {
            schemaList.innerHTML = '<div class="empty-panel">No schemas</div>';
            return;
        }
        const visibleSchemas = schemas.filter((schema) => {
            const haystack = [schema.name, schema.title].join(" ").toLowerCase();
            return haystack.includes(schemaSearch.toLowerCase());
        });
        if (!visibleSchemas.length) {
            schemaList.innerHTML = '<div class="empty-panel">No matching schemas</div>';
            return;
        }
        schemaList.innerHTML = visibleSchemas.map((schema) => `
            <button class="schema-list-item ${schema.name === currentName ? "active" : ""}" type="button" data-schema-name="${escapeHtml(schema.name)}">
                <div class="font-medium text-sm truncate">${escapeHtml(schema.title || schema.name)}</div>
                <div class="text-xs text-base-content/50 truncate">${escapeHtml(schema.name)}</div>
            </button>
        `).join("");
    }

    function renderFieldRows(container, path) {
        const entries = fieldEntries(container);
        if (!entries.length && !path.length) {
            return '<div class="empty-panel">No fields</div>';
        }
        return entries.map(([key, config], index) => renderFieldRow(key, config, path, {
            canMoveUp: index > 0,
            canMoveDown: index < entries.length - 1,
        })).join("");
    }

    function fieldControl(path, prop, label, value, type = "text") {
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <input class="input input-bordered input-xs" type="${escapeHtml(type)}" data-field-prop="${escapeHtml(prop)}" data-field-path="${escapeHtml(path)}" value="${escapeHtml(value ?? "")}"${invalidAttributes(path, prop)}>
                ${fieldErrorMarkup(path, prop)}
            </label>
        `;
    }

    function checkboxControl(path, prop, label, checked) {
        return `
            <label class="label cursor-pointer justify-start gap-2">
                <input class="checkbox checkbox-xs" type="checkbox" data-field-prop="${escapeHtml(prop)}" data-field-path="${escapeHtml(path)}" ${checked ? "checked" : ""}>
                <span class="label-text">${escapeHtml(label)}</span>
            </label>
        `;
    }

    function selectControl(path, prop, label, value, options) {
        const optionHtml = options.map((option) => `<option value="${escapeHtml(option)}" ${value === option ? "selected" : ""}>${escapeHtml(option)}</option>`).join("");
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <select class="select select-bordered select-xs" data-field-prop="${escapeHtml(prop)}" data-field-path="${escapeHtml(path)}">${optionHtml}</select>
            </label>
        `;
    }

    function numericControls(config, path, prefix = "") {
        const target = prefix ? config.items || {} : config;
        return `
            ${fieldControl(path, `${prefix}min_value`, "Min value", target.min_value, "number")}
            ${fieldControl(path, `${prefix}max_value`, "Max value", target.max_value, "number")}
            ${fieldControl(path, `${prefix}step`, "Step", target.step, "number")}
            ${fieldControl(path, `${prefix}decimal_places`, "Decimal places", target.decimal_places, "number")}
            ${selectControl(path, `${prefix}format`, "Format", target.format || "", ["", "money"])}
        `;
    }

    function stringControls(config, path, prefix = "") {
        const target = prefix ? config.items || {} : config;
        const patternProp = `${prefix}pattern`;
        return `
            ${fieldControl(path, `${prefix}min_length`, "Min length", target.min_length, "number")}
            ${fieldControl(path, `${prefix}max_length`, "Max length", target.max_length, "number")}
            ${patternTester(path, patternProp, target.pattern)}
            ${fieldControl(path, `${prefix}placeholder`, "Placeholder", target.placeholder)}
            ${checkboxControl(path, `${prefix}multiline`, "Multiline", Boolean(target.multiline))}
        `;
    }

    function choicesText(config) {
        const choices = config.choices || config.enum || [];
        return choices.map((choice) => {
            if (choice && typeof choice === "object") {
                return `${choice.label ?? choice.value}:${choice.value ?? choice.label}`;
            }
            return String(choice);
        }).join(", ");
    }

    function renderArrayItemControls(config, path) {
        const itemTypeValue = itemType(config);
        const itemTypeOptions = ["string", "number", "integer", "float", "boolean", "date", "datetime", "enum", "object"];
        let details = "";
        if (["number", "integer", "float"].includes(itemTypeValue)) {
            details = numericControls(config, path, "items.");
        } else if (itemTypeValue === "string") {
            details = stringControls(config, path, "items.");
        } else if (itemTypeValue === "enum") {
            details = `
                ${fieldControl(path, "items.choices", "Item choices", choicesText(config.items || {}))}
                ${fieldControl(path, "items.default", "Item default", (config.items || {}).default)}
            `;
        } else if (itemTypeValue === "boolean") {
            details = selectControl(path, "items.default", "Item default", String((config.items || {}).default ?? ""), ["", "true", "false"]);
        }
        return `
            ${selectControl(path, "array_item_type", "Items", itemTypeValue, itemTypeOptions)}
            ${details}
        `;
    }

    function defaultControl(config, path) {
        if (config.type === "boolean") {
            return selectControl(path, "default", "Default", String(config.default ?? ""), ["", "true", "false"]);
        }
        const inputType = ["number", "integer", "float"].includes(config.type) ? "number" : "text";
        return fieldControl(path, "default", "Default", config.default, inputType);
    }

    function renderFieldRow(key, config, path, movement) {
        const fullPath = [...path, key].join(".");
        const fieldName = config.label || config.title || key;
        const typeOptions = fieldTypes.map((type) => `<option value="${type}" ${config.type === type ? "selected" : ""}>${type}</option>`).join("");
        const extra = config.type === "enum"
            ? `
                ${fieldControl(fullPath, "choices", "Choices", choicesText(config))}
            `
            : config.type === "array"
                ? renderArrayItemControls(config, fullPath)
                : '<div></div>';
        const limits = ["number", "integer", "float"].includes(config.type)
            ? numericControls(config, fullPath)
            : config.type === "string"
                ? stringControls(config, fullPath)
                : "";
        const childContainer = config.type === "object"
            ? config.properties || {}
            : config.type === "array" && itemType(config) === "object"
                ? (config.items && config.items.properties) || {}
                : null;
        return `
            <div class="schema-field-row" data-row-path="${escapeHtml(fullPath)}">
                <div class="schema-field-actions">
                    <div class="schema-field-order-actions" role="group" aria-label="Reorder ${escapeHtml(fieldName)}">
                        <button class="btn btn-outline btn-xs" type="button" data-move-field="${escapeHtml(fullPath)}" data-move-direction="up" aria-label="Move ${escapeHtml(fieldName)} up" ${movement.canMoveUp ? "" : "disabled"}>Move up</button>
                        <button class="btn btn-outline btn-xs" type="button" data-move-field="${escapeHtml(fullPath)}" data-move-direction="down" aria-label="Move ${escapeHtml(fieldName)} down" ${movement.canMoveDown ? "" : "disabled"}>Move down</button>
                    </div>
                    <button class="btn btn-outline btn-error btn-xs schema-delete-field" type="button" data-delete-field="${escapeHtml(fullPath)}" aria-label="Delete field ${escapeHtml(fieldName)}">Delete field</button>
                </div>
                <label class="form-control">
                    <span class="label-text">Key</span>
                    <input class="input input-bordered input-xs" data-field-prop="key" data-field-path="${escapeHtml(fullPath)}" value="${escapeHtml(key)}"${invalidAttributes(fullPath, "key")}>
                    ${fieldErrorMarkup(fullPath, "key")}
                </label>
                <label class="form-control">
                    <span class="label-text">Label</span>
                    <input class="input input-bordered input-xs" data-field-prop="label" data-field-path="${escapeHtml(fullPath)}" value="${escapeHtml(config.label || config.title || "")}">
                </label>
                <label class="form-control">
                    <span class="label-text">Type</span>
                    <select class="select select-bordered select-xs" data-field-prop="type" data-field-path="${escapeHtml(fullPath)}">${typeOptions}</select>
                </label>
                <label class="label cursor-pointer justify-start gap-2">
                    <input class="checkbox checkbox-xs" type="checkbox" data-field-prop="required" data-field-path="${escapeHtml(fullPath)}" ${config.required ? "checked" : ""}>
                    <span class="label-text">Required</span>
                </label>
                ${checkboxControl(fullPath, "readonly", "Read only", Boolean(config.readonly))}
                ${extra}
                <label class="form-control">
                    <span class="label-text">Help</span>
                    <input class="input input-bordered input-xs" data-field-prop="help" data-field-path="${escapeHtml(fullPath)}" value="${escapeHtml(config.help || "")}">
                </label>
                ${defaultControl(config, fullPath)}
                ${limits}
                ${childContainer ? `
                    <div class="schema-field-children">
                        <div class="flex items-center gap-2 mb-2">
                            <button class="btn btn-outline btn-xs" type="button" data-add-child="${escapeHtml(fullPath)}" data-child-type="string">Add Field</button>
                            <button class="btn btn-outline btn-xs" type="button" data-add-child="${escapeHtml(fullPath)}" data-child-type="object">Add Object</button>
                            <button class="btn btn-outline btn-xs" type="button" data-add-child="${escapeHtml(fullPath)}" data-child-type="array">Add Array</button>
                        </div>
                        ${renderFieldRows(childContainer, [...path, key])}
                    </div>
                ` : ""}
            </div>
        `;
    }

    function itemType(config) {
        const items = config.items || {};
        return items.type || "string";
    }

    function renderYamlValue(value, indent) {
        const pad = " ".repeat(indent);
        if (Array.isArray(value)) {
            if (!value.length) {
                return "[]";
            }
            return "\n" + value.map((item) => `${pad}- ${renderYamlValue(item, indent + 2).trimStart()}`).join("\n");
        }
        if (value && typeof value === "object") {
            const entries = Object.entries(value);
            if (!entries.length) {
                return "{}";
            }
            return "\n" + entries.map(([key, child]) => {
                const rendered = renderYamlValue(child, indent + 2);
                return `${pad}${key}:${rendered.startsWith("\n") ? rendered : ` ${rendered}`}`;
            }).join("\n");
        }
        if (typeof value === "string") {
            return value === "" ? '""' : value;
        }
        return String(value);
    }

    function renderPreview() {
        yamlPreview.textContent = renderYamlValue(draft, 0).trimStart() + "\n";
    }

    function collectClientFindings() {
        const findings = [];
        const name = nameInput.value.trim();
        if (!name) {
            findings.push({ path: "name", message: "Schema file name is required." });
        } else if (!/^[^\\/]+\.(?:ya?ml|json)$/i.test(name)) {
            findings.push({ path: "name", message: "Use a file name ending in .yaml, .yml, or .json." });
        }
        if (!titleInput.value.trim()) {
            findings.push({ path: "title", message: "Schema title is required." });
        }

        function inspectFields(fields, parentPath = "") {
            fieldEntries(fields).forEach(([key, config]) => {
                const path = parentPath ? `${parentPath}.${key}` : key;
                const minLength = config.min_length;
                const maxLength = config.max_length;
                if (Number.isInteger(minLength) && Number.isInteger(maxLength) && minLength > maxLength) {
                    findings.push({ path: `${path}.min_length`, message: "Min length cannot be greater than max length." });
                }
                const minValue = config.min_value;
                const maxValue = config.max_value;
                if (Number.isFinite(minValue) && Number.isFinite(maxValue) && minValue > maxValue) {
                    findings.push({ path: `${path}.min_value`, message: "Min value cannot be greater than max value." });
                }
                if (config.type === "object") {
                    inspectFields(config.properties || {}, path);
                } else if (config.type === "array" && config.items && config.items.type === "object") {
                    inspectFields(config.items.properties || {}, path);
                } else if (config.type === "array" && config.items) {
                    const itemMinLength = config.items.min_length;
                    const itemMaxLength = config.items.max_length;
                    if (Number.isInteger(itemMinLength) && Number.isInteger(itemMaxLength) && itemMinLength > itemMaxLength) {
                        findings.push({ path: `${path}.items.min_length`, message: "Min length cannot be greater than max length." });
                    }
                    const itemMinValue = config.items.min_value;
                    const itemMaxValue = config.items.max_value;
                    if (Number.isFinite(itemMinValue) && Number.isFinite(itemMaxValue) && itemMinValue > itemMaxValue) {
                        findings.push({ path: `${path}.items.min_value`, message: "Min value cannot be greater than max value." });
                    }
                }
            });
        }

        inspectFields(draft.fields || {});
        return findings;
    }

    function renderFieldOutline() {
        const links = [];
        function visit(fields, parentPath = "", depth = 0) {
            fieldEntries(fields).forEach(([key, config]) => {
                const path = parentPath ? `${parentPath}.${key}` : key;
                const depthClass = `schema-outline-depth-${Math.min(depth, 4)}`;
                links.push(`
                    <button class="schema-outline-link ${depthClass}" type="button" data-outline-path="${escapeHtml(path)}">
                        <span class="font-medium">${escapeHtml(config.label || key)}</span>
                        <span class="font-mono text-base-content/50">${escapeHtml(key)}</span>
                    </button>
                `);
                if (config.type === "object") {
                    visit(config.properties || {}, path, depth + 1);
                } else if (config.type === "array" && config.items && config.items.type === "object") {
                    visit(config.items.properties || {}, path, depth + 1);
                }
            });
        }
        visit(draft.fields || {});
        fieldOutline.innerHTML = links.join("");
        fieldOutline.classList.toggle("hidden", links.length < 4);
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

    function displayFindingPath(path) {
        return String(path).replace(/\.items(?=\.|$)/g, "[]");
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
            const result = await window.DocFlow.apiPost("/api/schemas/pattern-test", { pattern, example });
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

    function renderValidationSummary() {
        const findings = combinedFindings();
        if (findings.length) {
            validationResults.innerHTML = `
                <div class="font-medium text-error mb-2">${findings.length} validation ${findings.length === 1 ? "issue" : "issues"}</div>
                <div class="schema-finding-list">
                    ${findings.map((finding) => `
                        <button class="schema-finding-link" type="button" data-finding-path="${escapeHtml(finding.path)}">
                            <span class="font-mono">${escapeHtml(displayFindingPath(finding.path))}</span>: ${escapeHtml(finding.message)}
                        </button>
                    `).join("")}
                </div>
            `;
        } else if (validationState === "valid") {
            validationResults.innerHTML = '<span class="text-success font-medium">Valid</span>';
        } else {
            validationResults.innerHTML = "";
        }
    }

    function renderActionState() {
        const findings = combinedFindings();
        const hasBlockingFinding = findings.length > 0;
        saveButton.disabled = hasBlockingFinding;
        validateButton.disabled = false;
        const invalidName = findings.some((finding) => finding.path === "name");
        const invalidTitle = findings.some((finding) => finding.path === "title");
        nameInput.setAttribute("aria-invalid", String(invalidName));
        titleInput.setAttribute("aria-invalid", String(invalidTitle));
        if (invalidName) {
            nameInput.setAttribute("aria-describedby", "schema-action-guidance");
        } else {
            nameInput.removeAttribute("aria-describedby");
        }
        if (invalidTitle) {
            titleInput.setAttribute("aria-describedby", "schema-action-guidance");
        } else {
            titleInput.removeAttribute("aria-describedby");
        }
        const metadataMessages = findings
            .filter((finding) => finding.path === "name" || finding.path === "title")
            .map((finding) => finding.message);
        actionGuidance.textContent = hasBlockingFinding
            ? metadataMessages.length
                ? `${metadataMessages.join(" ")} Resolve all validation issues before saving.`
                : "Resolve the validation issues before saving. Validate remains available to refresh the full error list."
            : dirty
                ? "Unsaved changes. Validate or save when ready."
                : "";
    }

    function render() {
        renderSchemaList();
        const displayName = nameInput.value || currentName || "New schema";
        detailTitle.textContent = `${dirty ? "* " : ""}${displayName}`;
        localFindings = collectClientFindings();
        fieldTree.innerHTML = renderFieldRows(draft.fields || {}, []);
        duplicateButton.disabled = !currentName;
        renderPreview();
        renderFieldOutline();
        renderActionState();
        renderValidationSummary();
    }

    function applySchemaPayload(schemaName, payload) {
        currentName = schemaName;
        rememberSchemaName(schemaName);
        draft = payload.raw_schema || emptySchema();
        nameInput.value = schemaName;
        titleInput.value = draft.title || "";
        descriptionInput.value = draft.description || "";
        detailHash.textContent = payload.schema && payload.schema.hash ? payload.schema.hash : "";
        const warning = payload.active_review_warning;
        setBox(warningBox, warning ? `${warning.message} (${warning.active_review_count})` : "");
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
        const requestedName = currentName;
        const listPromise = window.DocFlow.apiGet("/api/schemas");
        const detailPromise = requestedName && /\.(?:ya?ml|json)$/i.test(requestedName)
            ? window.DocFlow.apiGet(`/api/schemas/${encodeURIComponent(requestedName)}`)
            : null;
        if (detailPromise) {
            const [listResult, detailResult] = await Promise.allSettled([
                listPromise,
                detailPromise,
            ]);
            if (listResult.status === "rejected") {
                throw listResult.reason;
            }
            schemas = listResult.value.schemas || [];
            const resolvedName = resolveSchemaName(requestedName);
            if (
                detailResult.status === "fulfilled"
                && resolvedName === requestedName
            ) {
                applySchemaPayload(requestedName, detailResult.value);
                return;
            }
            currentName = resolvedName;
        } else {
            const listPayload = await listPromise;
            schemas = listPayload.schemas || [];
            currentName = resolveSchemaName(requestedName);
        }
        if (!currentName && schemas.length) {
            currentName = schemas[0].name;
        }
        if (currentName) {
            await loadSchema(currentName);
        } else {
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

    async function loadSchema(schemaName) {
        setBox(errorBox, "");
        const payload = await window.DocFlow.apiGet(`/api/schemas/${encodeURIComponent(schemaName)}`);
        applySchemaPayload(schemaName, payload);
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
        const name = nameInput.value.trim();
        const validation = await window.DocFlow.apiPost(`/api/schemas/${encodeURIComponent(name || currentName || "draft.yaml")}/validate`, { schema: draft });
        if (!validation.valid) {
            serverFindings = validation.findings || [];
            validationState = "invalid";
            setBox(errorBox, "Fix validation findings before saving this schema.");
            render();
            validationResults.focus();
            return;
        }
        const method = currentName ? window.DocFlow.apiPut : window.DocFlow.apiPost;
        const url = currentName ? `/api/schemas/${encodeURIComponent(currentName)}` : "/api/schemas";
        const payload = currentName ? { schema: draft } : { name, schema: draft };
        const result = await method(url, payload);
        const savedName = result.schema.name || name;
        currentName = savedName;
        dirty = false;
        await loadSchemas();
        await loadSchema(savedName);
        if (window.DocFlow) {
            window.DocFlow.showToast("Schema saved", "success");
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
        const name = nameInput.value.trim() || currentName || "draft.yaml";
        const result = await window.DocFlow.apiPost(`/api/schemas/${encodeURIComponent(name)}/validate`, { schema: draft });
        serverFindings = result.findings || [];
        validationState = result.valid ? "valid" : "invalid";
        render();
        validationResults.focus();
        const warning = result.active_review_warning;
        setBox(warningBox, warning ? `${warning.message} (${warning.active_review_count})` : "");
    }

    function syncMeta() {
        draft.title = titleInput.value.trim();
        draft.description = descriptionInput.value.trim();
        draft.fields = draft.fields || {};
    }

    function addField(path, type) {
        const container = getFieldContainer(path);
        if (!container) {
            return;
        }
        const key = uniqueFieldKey(container, "new_field");
        container[key] = defaultField(type);
        markDirty();
    }

    function findField(pathText) {
        const parts = pathText.split(".").filter(Boolean);
        const key = parts.pop();
        const container = getFieldContainer(parts);
        return { container, key, field: container && key ? container[key] : null };
    }

    function fieldPath(parentPath, key) {
        return parentPath ? `${parentPath}.${key}` : key;
    }

    function focusFieldAction(pathText, action) {
        const row = fieldTree.querySelector(`[data-row-path="${CSS.escape(pathText)}"]`);
        const preferred = row && row.querySelector(`[data-move-direction="${action}"]`);
        const control = preferred && !preferred.disabled
            ? preferred
            : row && (row.querySelector("[data-move-field]:not([disabled])") || row.querySelector("[data-delete-field]"));
        if (control) {
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
        const found = findField(pathText);
        if (!found.container || !found.key || !found.field || !["up", "down"].includes(direction)) {
            return false;
        }
        const entries = Object.entries(found.container);
        const currentIndex = entries.findIndex(([key]) => key === found.key);
        const nextIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
        if (currentIndex < 0 || nextIndex < 0 || nextIndex >= entries.length) {
            return false;
        }
        [entries[currentIndex], entries[nextIndex]] = [entries[nextIndex], entries[currentIndex]];
        Object.keys(found.container).forEach((key) => delete found.container[key]);
        entries.forEach(([key, config]) => {
            found.container[key] = config;
        });
        const fieldName = found.field.label || found.field.title || found.key;
        markDirty();
        focusFieldAction(pathText, direction);
        announceFieldChange(`Moved ${fieldName} ${direction}.`);
        return true;
    }

    function updateField(pathText, prop, value) {
        const found = findField(pathText);
        if (!found.container || !found.key || !found.field) {
            return false;
        }
        const findingPath = `${pathText}.${prop}`;
        pendingFindings = pendingFindings.filter((finding) => finding.path !== findingPath);
        const target = targetForProp(found.field, prop);
        const propName = prop.startsWith("items.") ? prop.slice("items.".length) : prop;
        if (prop === "key") {
            const nextKey = String(value || "").trim();
            if (!nextKey) {
                pendingFindings.push({ path: findingPath, message: "Field key cannot be empty." });
                return false;
            }
            if (nextKey === found.key) {
                return true;
            }
            if (found.container[nextKey]) {
                pendingFindings.push({ path: findingPath, message: `Field key "${nextKey}" already exists at this level.` });
                return false;
            }
            const entries = Object.entries(found.container);
            Object.keys(found.container).forEach((key) => delete found.container[key]);
            entries.forEach(([key, config]) => {
                found.container[key === found.key ? nextKey : key] = config;
            });
        } else if (prop === "type") {
            found.field.type = value;
            if (value === "object") {
                found.field.properties = found.field.properties || {};
                delete found.field.items;
                delete found.field.choices;
            } else if (value === "array") {
                found.field.items = found.field.items || { type: "string" };
                delete found.field.properties;
                delete found.field.choices;
            } else if (value === "enum") {
                found.field.choices = found.field.choices || ["new", "approved"];
                delete found.field.properties;
                delete found.field.items;
            } else {
                delete found.field.properties;
                delete found.field.items;
                delete found.field.choices;
            }
        } else if (prop === "required") {
            found.field.required = Boolean(value);
        } else if (prop === "readonly") {
            found.field.readonly = Boolean(value);
        } else if (prop === "choices") {
            found.field.choices = parseChoices(value);
        } else if (prop === "array_item_type") {
            found.field.items = value === "object" ? { type: "object", properties: {} } : { type: value };
        } else if (prop.startsWith("items.")) {
            updateScalarProperty(target, propName, value);
        } else if (["min_value", "max_value", "step", "min_length", "max_length", "decimal_places"].includes(prop)) {
            if (String(value).trim() === "") {
                delete found.field[prop];
            } else if (prop === "decimal_places" || prop === "min_length" || prop === "max_length") {
                found.field[prop] = Number.parseInt(value, 10);
            } else {
                found.field[prop] = Number(value);
            }
        } else if (prop === "default") {
            if (String(value).trim() === "") {
                delete found.field.default;
            } else {
                found.field.default = coerceDefaultValue(found.field.type, value);
            }
        } else if (prop === "multiline") {
            found.field.multiline = Boolean(value);
        } else if (prop === "format") {
            if (String(value).trim() === "") {
                delete found.field.format;
            } else {
                found.field.format = value;
            }
        } else {
            found.field[prop] = value;
        }
        if (prop.endsWith("pattern")) {
            patternResults.delete(findingPath);
        }
        setBox(errorBox, "");
        markDirty();
        return true;
    }

    function targetForProp(field, prop) {
        if (!prop.startsWith("items.")) {
            return field;
        }
        field.items = field.items || { type: "string" };
        return field.items;
    }

    function updateScalarProperty(target, prop, value) {
        if (prop === "choices") {
            target.choices = parseChoices(value);
            return;
        }
        if (prop === "default") {
            if (String(value).trim() === "") {
                delete target.default;
            } else {
                target.default = coerceDefaultValue(target.type, value);
            }
            return;
        }
        if (prop === "multiline") {
            target.multiline = Boolean(value);
            return;
        }
        if (prop === "format") {
            if (String(value).trim() === "") {
                delete target.format;
            } else {
                target.format = value;
            }
            return;
        }
        if (["min_value", "max_value", "step"].includes(prop)) {
            if (String(value).trim() === "") {
                delete target[prop];
            } else {
                target[prop] = Number(value);
            }
            return;
        }
        if (["min_length", "max_length", "decimal_places"].includes(prop)) {
            if (String(value).trim() === "") {
                delete target[prop];
            } else {
                target[prop] = Number.parseInt(value, 10);
            }
            return;
        }
        if (String(value).trim() === "") {
            delete target[prop];
        } else {
            target[prop] = value;
        }
    }

    function parseChoices(value) {
        return String(value)
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean)
            .map((item) => {
                if (!item.includes(":")) {
                    return item;
                }
                const [label, ...rest] = item.split(":");
                return { label: label.trim(), value: rest.join(":").trim() };
            });
    }

    function coerceDefaultValue(fieldType, value) {
        if (fieldType === "boolean") {
            return value === true || value === "true";
        }
        if (fieldType === "integer") {
            return Number.parseInt(value, 10);
        }
        if (fieldType === "number" || fieldType === "float") {
            return Number(value);
        }
        return value;
    }

    function deleteField(pathText) {
        const found = findField(pathText);
        if (!found.container || !found.key || !found.field) {
            return false;
        }
        const fieldName = found.field.label || found.field.title || found.key;
        const confirmed = window.confirm(
            `Delete field "${fieldName}" from this schema draft?\n\n` +
            "The field will be permanently removed when you save the schema."
        );
        if (!confirmed) {
            return false;
        }
        const parentPath = pathText.split(".").slice(0, -1).join(".");
        const entries = Object.entries(found.container);
        const deletedIndex = entries.findIndex(([key]) => key === found.key);
        delete found.container[found.key];
        const remaining = Object.keys(found.container);
        const focusKey = remaining[Math.min(deletedIndex, remaining.length - 1)];
        const focusPath = focusKey ? fieldPath(parentPath, focusKey) : "";
        markDirty();
        if (focusPath) {
            const nextInput = fieldTree.querySelector(`[data-row-path="${CSS.escape(focusPath)}"] [data-field-prop="key"]`);
            if (nextInput) {
                nextInput.focus();
            }
        } else {
            const addControl = parentPath
                ? fieldTree.querySelector(`[data-add-child="${CSS.escape(parentPath)}"]`)
                : document.querySelector("[data-add-field]");
            if (addControl) {
                addControl.focus();
            }
        }
        announceFieldChange(`Deleted ${fieldName} from the schema draft.`);
        return true;
    }

    function confirmDiscardChanges() {
        return !dirty || window.confirm("Discard unsaved schema changes?");
    }

    schemaList.addEventListener("click", (event) => {
        const button = event.target.closest("[data-schema-name]");
        if (button && button.dataset.schemaName !== currentName && confirmDiscardChanges()) {
            loadSchema(button.dataset.schemaName).catch((error) => setBox(errorBox, error.message));
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
        currentName = "";
        draft = emptySchema();
        nameInput.value = "new_schema.yaml";
        titleInput.value = "New Schema";
        descriptionInput.value = "";
        detailHash.textContent = "";
        validationResults.innerHTML = "";
        setBox(warningBox, "");
        setBox(errorBox, "");
        pendingFindings = [];
        serverFindings = [];
        validationState = "";
        patternExamples.clear();
        patternResults.clear();
        fieldStatus.textContent = "";
        dirty = true;
        render();
    });
    duplicateButton.addEventListener("click", async () => {
        if (!currentName || !confirmDiscardChanges()) {
            return;
        }
        const newName = window.prompt("Duplicate schema as", currentName.replace(/(\.ya?ml|\.json)$/i, "_copy$1"));
        if (!newName) {
            return;
        }
        try {
            const result = await window.DocFlow.apiPost(`/api/schemas/${encodeURIComponent(currentName)}/duplicate`, { new_name: newName });
            currentName = result.schema.name || newName;
            await loadSchemas();
            await loadSchema(currentName);
        } catch (error) {
            setBox(errorBox, error.message);
        }
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
            row.scrollIntoView({ behavior: "smooth", block: "start" });
            const input = row.querySelector("[data-field-prop='key']");
            if (input) {
                input.focus({ preventScroll: true });
            }
        }
    });

    validationResults.addEventListener("click", (event) => {
        const button = event.target.closest("[data-finding-path]");
        if (button) {
            focusFinding(button.dataset.findingPath);
        }
    });

    loadSchemas().catch((error) => setBox(errorBox, error.message));
})();
