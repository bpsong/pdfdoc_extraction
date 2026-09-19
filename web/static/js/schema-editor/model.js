/** Browser-independent review-form field and validation operations. */

export function emptySchema() {
    return { title: "", description: "", fields: {} };
}

export function createSchemaModel(getDraft) {
    function fieldEntries(container) {
        return Object.entries(container || {}).filter(([, config]) => config && typeof config === "object");
    }

    function getFieldContainer(path) {
        let container = getDraft().fields;
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

    function findField(pathText) {
        const parts = pathText.split(".").filter(Boolean);
        const key = parts.pop();
        const container = getFieldContainer(parts);
        return { container, key, field: container && key ? container[key] : null };
    }

    function fieldPath(parentPath, key) {
        return parentPath ? `${parentPath}.${key}` : key;
    }

    function addField(path, type) {
        const container = getFieldContainer(path);
        if (!container) {
            return;
        }
        const key = uniqueFieldKey(container, "new_field");
        container[key] = defaultField(type);
        return key;
    }

    function moveField(pathText, direction) {
        const found = findField(pathText);
        if (!found.container || !found.key || !found.field || !["up", "down"].includes(direction)) {
            return { ok: false };
        }
        const entries = Object.entries(found.container);
        const currentIndex = entries.findIndex(([key]) => key === found.key);
        const nextIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
        if (currentIndex < 0 || nextIndex < 0 || nextIndex >= entries.length) {
            return { ok: false };
        }
        [entries[currentIndex], entries[nextIndex]] = [entries[nextIndex], entries[currentIndex]];
        Object.keys(found.container).forEach((key) => delete found.container[key]);
        entries.forEach(([key, config]) => {
            found.container[key] = config;
        });
        const fieldName = found.field.label || found.field.title || found.key;
        return { ok: true, fieldName };
    }

    function updateFieldModel(pathText, prop, value) {
        const found = findField(pathText);
        if (!found.container || !found.key || !found.field) {
            return { ok: false };
        }
        const findingPath = `${pathText}.${prop}`;
        const target = targetForProp(found.field, prop);
        const propName = prop.startsWith("items.") ? prop.slice("items.".length) : prop;
        let renamedPath = "";
        if (prop === "key") {
            const nextKey = String(value || "").trim();
            if (!nextKey) {
                return { ok: false, finding: { path: findingPath, message: "Field key cannot be empty." } };
            }
            if (nextKey === found.key) {
                return { ok: true };
            }
            if (found.container[nextKey]) {
                return { ok: false, finding: { path: findingPath, message: `Field key "${nextKey}" already exists at this level.` } };
            }
            const entries = Object.entries(found.container);
            Object.keys(found.container).forEach((key) => delete found.container[key]);
            entries.forEach(([key, config]) => {
                found.container[key === found.key ? nextKey : key] = config;
            });
            renamedPath = fieldPath(pathText.split(".").slice(0, -1).join("."), nextKey);
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
        return { ok: true, renamedPath };
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

    function collectClientFindings(name, title) {
        const findings = [];
        const schemaKey = String(name || "").trim();
        if (!schemaKey) {
            findings.push({ path: "name", message: "Stable schema key is required." });
        } else if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(schemaKey)) {
            findings.push({ path: "name", message: "Use lowercase words separated by hyphens." });
        }
        if (!String(title || "").trim()) {
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

        inspectFields(getDraft().fields || {});
        return findings;
    }

    function removeField(pathText) {
        const found = findField(pathText);
        if (!found.container || !found.key || !found.field) return { ok: false };
        const fieldName = found.field.label || found.field.title || found.key;
        const parentPath = pathText.split(".").slice(0, -1).join(".");
        const deletedIndex = Object.keys(found.container).indexOf(found.key);
        delete found.container[found.key];
        const remaining = Object.keys(found.container);
        const focusKey = remaining[Math.min(deletedIndex, remaining.length - 1)];
        return { ok: true, fieldName, parentPath,
            focusPath: focusKey ? fieldPath(parentPath, focusKey) : "" };
    }

    return { fieldEntries, getFieldContainer, defaultField, uniqueFieldKey,
        findField, fieldPath, addField, moveField, updateField: updateFieldModel,
        removeField, collectClientFindings };
}
