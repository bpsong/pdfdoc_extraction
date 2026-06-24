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
    const yamlPreview = document.getElementById("schema-yaml-preview");
    const validationResults = document.getElementById("schema-validation-results");
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
        return entries.map(([key, config]) => renderFieldRow(key, config, path)).join("");
    }

    function fieldControl(path, prop, label, value, type = "text") {
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <input class="input input-bordered input-xs" type="${escapeHtml(type)}" data-field-prop="${escapeHtml(prop)}" data-field-path="${escapeHtml(path)}" value="${escapeHtml(value ?? "")}">
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
        return `
            ${fieldControl(path, `${prefix}min_length`, "Min length", target.min_length, "number")}
            ${fieldControl(path, `${prefix}max_length`, "Max length", target.max_length, "number")}
            ${fieldControl(path, `${prefix}pattern`, "Pattern", target.pattern)}
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

    function renderFieldRow(key, config, path) {
        const fullPath = [...path, key].join(".");
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
                <label class="form-control">
                    <span class="label-text">Key</span>
                    <input class="input input-bordered input-xs" data-field-prop="key" data-field-path="${escapeHtml(fullPath)}" value="${escapeHtml(key)}">
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
                <button class="btn btn-ghost btn-xs" type="button" data-delete-field="${escapeHtml(fullPath)}">Delete</button>
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

    function render() {
        renderSchemaList();
        const displayName = nameInput.value || currentName || "New schema";
        detailTitle.textContent = `${dirty ? "* " : ""}${displayName}`;
        fieldTree.innerHTML = renderFieldRows(draft.fields || {}, []);
        saveButton.disabled = !nameInput.value.trim();
        validateButton.disabled = !nameInput.value.trim();
        duplicateButton.disabled = !currentName;
        renderPreview();
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
        validationResults.innerHTML = "";
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
        const name = nameInput.value.trim();
        const validation = await window.DocFlow.apiPost(`/api/schemas/${encodeURIComponent(name || currentName || "draft.yaml")}/validate`, { schema: draft });
        if (!validation.valid) {
            validationResults.innerHTML = (validation.findings || []).map((finding) => `
                <div class="text-error">${escapeHtml(finding.path)}: ${escapeHtml(finding.message)}</div>
            `).join("") || '<span class="text-error font-medium">Schema validation failed</span>';
            setBox(errorBox, "Fix validation findings before saving this schema.");
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
        const name = nameInput.value.trim() || currentName || "draft.yaml";
        const result = await window.DocFlow.apiPost(`/api/schemas/${encodeURIComponent(name)}/validate`, { schema: draft });
        if (result.valid) {
            validationResults.innerHTML = '<span class="text-success font-medium">Valid</span>';
        } else {
            validationResults.innerHTML = (result.findings || []).map((finding) => `
                <div class="text-error">${escapeHtml(finding.path)}: ${escapeHtml(finding.message)}</div>
            `).join("");
        }
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

    function updateField(pathText, prop, value) {
        const found = findField(pathText);
        if (!found.container || !found.key || !found.field) {
            return;
        }
        const target = targetForProp(found.field, prop);
        const propName = prop.startsWith("items.") ? prop.slice("items.".length) : prop;
        if (prop === "key") {
            const nextKey = String(value || "").trim();
            if (!nextKey || nextKey === found.key) {
                return;
            }
            if (found.container[nextKey]) {
                setBox(errorBox, `Field key "${nextKey}" already exists at this level.`);
                return;
            }
            found.container[nextKey] = found.field;
            delete found.container[found.key];
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
        setBox(errorBox, "");
        markDirty();
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
        if (found.container && found.key) {
            delete found.container[found.key];
            markDirty();
        }
    }

    schemaList.addEventListener("click", (event) => {
        const button = event.target.closest("[data-schema-name]");
        if (button) {
            loadSchema(button.dataset.schemaName).catch((error) => setBox(errorBox, error.message));
        }
    });

    document.querySelectorAll("[data-add-field]").forEach((button) => {
        button.addEventListener("click", () => addField([], button.dataset.addField));
    });

    fieldTree.addEventListener("click", (event) => {
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

    fieldTree.addEventListener("change", (event) => {
        const input = event.target.closest("[data-field-prop]");
        if (!input) {
            return;
        }
        const value = input.type === "checkbox" ? input.checked : input.value;
        updateField(input.dataset.fieldPath, input.dataset.fieldProp, value);
    });

    [titleInput, descriptionInput].forEach((input) => {
        input.addEventListener("input", () => {
            syncMeta();
            markDirty();
        });
    });

    nameInput.addEventListener("input", render);
    schemaSearchInput.addEventListener("input", (event) => {
        schemaSearch = event.target.value || "";
        renderSchemaList();
    });
    saveButton.addEventListener("click", () => saveSchema().catch((error) => setBox(errorBox, error.message)));
    validateButton.addEventListener("click", () => validateSchema().catch((error) => setBox(errorBox, error.message)));
    createButton.addEventListener("click", () => {
        currentName = "";
        draft = emptySchema();
        nameInput.value = "new_schema.yaml";
        titleInput.value = "New Schema";
        descriptionInput.value = "";
        detailHash.textContent = "";
        validationResults.innerHTML = "";
        setBox(warningBox, "");
        setBox(errorBox, "");
        dirty = true;
        render();
    });
    duplicateButton.addEventListener("click", async () => {
        if (!currentName) {
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

    loadSchemas().catch((error) => setBox(errorBox, error.message));
})();
