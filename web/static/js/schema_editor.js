(function () {
    "use strict";

    const workspace = document.getElementById("schema-editor-workspace");
    if (!workspace) {
        return;
    }

    const schemaList = document.getElementById("schema-list");
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
    const fieldTypes = ["string", "number", "integer", "float", "boolean", "date", "datetime", "enum", "object", "array"];
    let schemas = [];
    let currentName = workspace.dataset.schemaName || "";
    let draft = emptySchema();
    let dirty = false;

    function emptySchema() {
        return { title: "", description: "", fields: {} };
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
        schemaList.innerHTML = schemas.map((schema) => `
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

    function renderFieldRow(key, config, path) {
        const fullPath = [...path, key].join(".");
        const typeOptions = fieldTypes.map((type) => `<option value="${type}" ${config.type === type ? "selected" : ""}>${type}</option>`).join("");
        const extra = config.type === "enum"
            ? `<label class="form-control"><span class="label-text">Choices</span><input class="input input-bordered input-xs" data-field-prop="choices" data-field-path="${escapeHtml(fullPath)}" value="${escapeHtml((config.choices || config.enum || []).join(", "))}"></label>`
            : config.type === "array"
                ? `<label class="form-control"><span class="label-text">Items</span><select class="select select-bordered select-xs" data-field-prop="array_item_type" data-field-path="${escapeHtml(fullPath)}"><option value="string" ${itemType(config) === "string" ? "selected" : ""}>string</option><option value="number" ${itemType(config) === "number" ? "selected" : ""}>number</option><option value="object" ${itemType(config) === "object" ? "selected" : ""}>object</option></select></label>`
                : '<div></div>';
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
                <button class="btn btn-ghost btn-xs" type="button" data-delete-field="${escapeHtml(fullPath)}">Delete</button>
                ${extra}
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

    async function loadSchemas() {
        const payload = await window.DocFlow.apiGet("/api/schemas");
        schemas = payload.schemas || [];
        if (!currentName && schemas.length) {
            currentName = schemas[0].name;
        }
        if (currentName) {
            await loadSchema(currentName);
        } else {
            render();
        }
    }

    async function loadSchema(schemaName) {
        setBox(errorBox, "");
        const payload = await window.DocFlow.apiGet(`/api/schemas/${encodeURIComponent(schemaName)}`);
        currentName = schemaName;
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

    async function saveSchema() {
        syncMeta();
        const name = nameInput.value.trim();
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
        if (prop === "key") {
            const nextKey = String(value || "").trim();
            if (!nextKey || nextKey === found.key || found.container[nextKey]) {
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
        } else if (prop === "choices") {
            found.field.choices = String(value).split(",").map((item) => item.trim()).filter(Boolean);
        } else if (prop === "array_item_type") {
            found.field.items = value === "object" ? { type: "object", properties: {} } : { type: value };
        } else {
            found.field[prop] = value;
        }
        markDirty();
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

    loadSchemas().catch((error) => setBox(errorBox, error.message));
})();
