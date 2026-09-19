/** Browser-independent human-review values, permissions, and corrections. */

export function createHumanReviewModel(state) {
    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function titleCase(value) {
        return String(value || "")
            .replace(/[_-]+/g, " ")
            .replace(/\s+/g, " ")
            .trim()
            .replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Unknown";
    }

    function cloneValue(value) {
        if (value === undefined) {
            return undefined;
        }
        return JSON.parse(JSON.stringify(value));
    }

    function parseJsonMaybe(value, fallback) {
        if (value === null || value === undefined || value === "") {
            return fallback;
        }
        if (typeof value !== "string") {
            return value;
        }
        try {
            return JSON.parse(value);
        } catch (error) {
            return fallback;
        }
    }

    function normalizeSourceValueMode(mode) {
        return ["review", "all", "hidden"].includes(mode) ? mode : "review";
    }

    function valueFromField(field, preferredKey) {
        if (Object.prototype.hasOwnProperty.call(field, preferredKey)) {
            return field[preferredKey];
        }
        return parseJsonMaybe(field[`${preferredKey}_json`], null);
    }

    function fieldFinalValue(field) {
        const corrected = valueFromField(field, "corrected_value");
        if (corrected !== null && corrected !== undefined) {
            return corrected;
        }
        const finalValue = valueFromField(field, "final_value");
        if (finalValue !== null && finalValue !== undefined) {
            return finalValue;
        }
        return valueFromField(field, "extracted_value");
    }

    function fieldExtractedValue(field) {
        const extracted = valueFromField(field, "extracted_value");
        return extracted === undefined ? null : extracted;
    }

    function normalizeFields(fields) {
        return (fields || []).map((field) => ({
            ...field,
            field_key: String(field.field_key || ""),
            field_alias: field.field_alias || field.field_key,
            extracted_value: fieldExtractedValue(field),
            final_value: fieldFinalValue(field),
            corrected_value: valueFromField(field, "corrected_value"),
            requires_review: Boolean(field.requires_review),
        }));
    }

    function defaultValueForField(field) {
        if (field.default !== undefined && field.default !== null) {
            return cloneValue(field.default);
        }
        if (field.type === "object") {
            return {};
        }
        if (field.type === "array") {
            return [];
        }
        if (field.type === "boolean") {
            return field.required ? null : false;
        }
        if (field.type === "number" || field.type === "float" || field.type === "integer") {
            return field.required ? null : "";
        }
        return "";
    }

    function getByPath(root, pathParts) {
        return pathParts.reduce((current, part) => {
            if (current === null || current === undefined) {
                return undefined;
            }
            return current[part];
        }, root);
    }

    function setByPath(root, pathParts, value) {
        let current = root;
        pathParts.forEach((part, index) => {
            if (index === pathParts.length - 1) {
                current[part] = value;
                return;
            }
            if (current[part] === null || typeof current[part] !== "object") {
                current[part] = typeof pathParts[index + 1] === "number" ? [] : {};
            }
            current = current[part];
        });
    }

    function pathString(pathParts) {
        return pathParts.join(".");
    }

    function formatValue(value) {
        if (value === null || value === undefined || value === "") {
            return "Missing";
        }
        if (Array.isArray(value)) {
            return `${value.length} item${value.length === 1 ? "" : "s"}`;
        }
        if (typeof value === "object") {
            return JSON.stringify(value);
        }
        return String(value);
    }

    function optionItems(field) {
        if (Array.isArray(field.option_items) && field.option_items.length) {
            return field.option_items;
        }
        return (field.options || []).map((option) => ({ label: String(option), value: option }));
    }

    function encodedOptionValue(value) {
        return JSON.stringify(value);
    }

    function decodedOptionValue(value) {
        if (value === "") {
            return null;
        }
        try {
            return JSON.parse(value);
        } catch (error) {
            return value;
        }
    }

    function decimalPlaces(field) {
        if (field.decimal_places !== null && field.decimal_places !== undefined && field.decimal_places !== "") {
            const numeric = Number(field.decimal_places);
            return Number.isInteger(numeric) && numeric >= 0 ? numeric : null;
        }
        if (field.format === "money") {
            return 2;
        }
        return null;
    }

    function numberStep(field) {
        if (field.type === "integer") {
            return "1";
        }
        if (field.step !== null && field.step !== undefined && field.step !== "") {
            return String(field.step);
        }
        const places = decimalPlaces(field);
        if (places !== null) {
            return String(10 ** -places);
        }
        return "any";
    }

    function formatInputValue(field, value) {
        if (value === null || value === undefined || typeof value === "object") {
            return "";
        }
        if (field.type === "number" || field.type === "float") {
            const places = decimalPlaces(field);
            const numeric = Number(value);
            if (places !== null && Number.isFinite(numeric)) {
                return numeric.toFixed(places);
            }
        }
        if (field.type === "date") {
            return normalizeDateValue(value);
        }
        if (field.type === "datetime") {
            return normalizeDateTimeValue(value);
        }
        return String(value);
    }

    function scalarTextValue(value) {
        if (value === null || value === undefined || typeof value === "object") {
            return "";
        }
        return String(value);
    }

    function normalizeDateValue(value) {
        if (!value) {
            return "";
        }
        const text = String(value);
        const match = text.match(/^(\d{4}-\d{2}-\d{2})/);
        return match ? match[1] : text;
    }

    function normalizeDateTimeValue(value) {
        if (!value) {
            return "";
        }
        const text = String(value);
        const match = text.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
        return match ? `${match[1]}T${match[2]}` : text;
    }

    function deepEqual(left, right) {
        return JSON.stringify(left) === JSON.stringify(right);
    }

    function fieldLabel(field) {
        return field.label || titleCase(field.key);
    }

    function fieldHelpText(field) {
        return field.help || field.description || "";
    }

    function hasOwnLock() {
        return Boolean(state.lock && state.lock.locked_by === state.operator);
    }

    function isComplete() {
        return state.reviewItem && state.reviewItem.status === "completed";
    }

    function canEditPath(pathParts) {
        if (!hasOwnLock() || isComplete()) {
            return false;
        }
        const schemaField = fieldForSchemaPath(pathParts);
        if (schemaField && schemaField.readonly) {
            return false;
        }
        const editableFields = state.metadata.editable_fields || [];
        if (!editableFields.length) {
            return true;
        }
        const fullPath = pathString(pathParts);
        const rootKey = String(pathParts[0]);
        return editableFields.includes(fullPath) || editableFields.includes(rootKey);
    }

    function isHighlighted(pathParts) {
        const highlighted = state.metadata.highlight_fields || state.metadata.low_confidence_fields || [];
        const highlightedPaths = state.metadata.low_confidence_paths || [];
        if (!highlighted.length) {
            return highlightedPaths.includes(pathString(pathParts));
        }
        const fullPath = pathString(pathParts);
        const rootKey = String(pathParts[0]);
        return highlighted.includes(fullPath) || highlighted.includes(rootKey) || highlightedPaths.includes(fullPath);
    }

    function shouldShowSourceValue(pathParts, fieldInfo, currentValue, extractedValue) {
        const sourcePath = pathString(pathParts);
        const confidence = Number(fieldInfo && fieldInfo.confidence);
        const lowConfidence = fieldInfo
            && (fieldInfo.confidence_band === "low" || fieldInfo.confidence_band === "medium" || (Number.isFinite(confidence) && confidence < 0.9));
        if (state.sourceValueReveals.has(sourcePath)) {
            return true;
        }
        if (state.sourceValueMode === "all") {
            return true;
        }
        if (state.sourceValueMode === "hidden") {
            return false;
        }
        return isHighlighted(pathParts)
            || Boolean(fieldInfo && fieldInfo.requires_review)
            || Boolean(lowConfidence)
            || Boolean(fieldInfo && fieldInfo.corrected_value !== null && fieldInfo.corrected_value !== undefined)
            || !deepEqual(currentValue, extractedValue);
    }

    function fieldForPath(pathParts) {
        return state.fieldsByKey.get(String(pathParts[0])) || null;
    }

    function confidenceInfoForPath(pathParts) {
        const fieldInfo = fieldForPath(pathParts);
        if (!fieldInfo) {
            return null;
        }
        if (pathParts.length === 1) {
            if ((fieldInfo.confidence === null || fieldInfo.confidence === undefined || fieldInfo.confidence === "")
                && fieldInfo.confidence_details
                && fieldInfo.confidence_details.confidence !== undefined) {
                return {
                    ...fieldInfo,
                    confidence: fieldInfo.confidence_details.confidence,
                    confidence_band: fieldInfo.confidence_details.confidence_band || fieldInfo.confidence_band,
                };
            }
            return fieldInfo;
        }
        const nestedPath = pathParts.slice(1).join(".");
        const nested = fieldInfo.confidence_details
            && fieldInfo.confidence_details.nested_confidences
            && fieldInfo.confidence_details.nested_confidences[nestedPath];
        return nested || fieldInfo;
    }

    function fieldForSchemaPath(pathParts) {
        let current = (state.schemaFields || []).find((field) => field.key === pathParts[0]);
        for (let index = 1; index < pathParts.length && current; index += 1) {
            const part = pathParts[index];
            if (typeof part === "number") {
                continue;
            }
            const children = current.children || (current.item_schema && current.item_schema.fields) || [];
            current = children.find((child) => child.key === part);
        }
        return current || null;
    }

    function inferredFieldFromValue(key, value) {
        if (Array.isArray(value)) {
            const first = value[0];
            if (first && typeof first === "object" && !Array.isArray(first)) {
                return {
                    key,
                    path: key,
                    label: titleCase(key),
                    type: "array",
                    editor: "object_array",
                    item_schema: {
                        type: "object",
                        fields: Object.keys(first).map((childKey) => inferredFieldFromValue(childKey, first[childKey])),
                    },
                    children: [],
                };
            }
            return {
                key,
                path: key,
                label: titleCase(key),
                type: "array",
                editor: "scalar_array",
                item_schema: { type: "string" },
                children: [],
            };
        }
        if (value && typeof value === "object") {
            return {
                key,
                path: key,
                label: titleCase(key),
                type: "object",
                editor: "object",
                children: Object.keys(value).map((childKey) => inferredFieldFromValue(childKey, value[childKey])),
            };
        }
        const type = typeof value === "number" ? "number" : typeof value === "boolean" ? "boolean" : "string";
        return { key, path: key, label: titleCase(key), type, editor: type === "boolean" ? "checkbox" : type, children: [] };
    }

    function mergedSchemaFields(schemaFields, fields) {
        const merged = [...(schemaFields || [])];
        const seen = new Set(merged.map((field) => field.key));
        fields.forEach((field) => {
            if (!field.field_key || seen.has(field.field_key)) {
                return;
            }
            const inferred = inferredFieldFromValue(field.field_key, field.final_value);
            inferred.label = field.field_alias || inferred.label;
            merged.push(inferred);
            seen.add(field.field_key);
        });
        return merged;
    }

    function initializeValues(payload) {
        state.fields = normalizeFields(payload.fields || []);
        state.fieldsByKey = new Map(state.fields.map((field) => [field.field_key, field]));
        state.originalValues = {};
        state.fields.forEach((field) => {
            state.originalValues[field.field_key] = cloneValue(field.final_value);
        });
        const schemaFields = payload.schema && Array.isArray(payload.schema.fields) ? payload.schema.fields : [];
        schemaFields.forEach((field) => {
            if (!Object.prototype.hasOwnProperty.call(state.originalValues, field.key)) {
                state.originalValues[field.key] = defaultValueForField(field);
            }
        });
        state.values = cloneValue(state.originalValues) || {};
        const draftCorrections = state.metadata.draft && state.metadata.draft.corrections;
        if (draftCorrections && typeof draftCorrections === "object") {
            Object.entries(draftCorrections).forEach(([key, value]) => {
                state.values[key] = cloneValue(value);
            });
        }
        state.schemaFields = mergedSchemaFields(schemaFields, state.fields);
    }

    function parseInputValue(input, field) {
        if (field.type === "boolean" || field.editor === "checkbox") {
            if (input.value === "") {
                return null;
            }
            return input.value === "true";
        }
        if ((field.options || field.option_items) && input.tagName === "SELECT") {
            return decodedOptionValue(input.value);
        }
        if (field.type === "number" || field.type === "float" || field.type === "integer") {
            if (input.value === "") {
                return null;
            }
            const value = field.type === "integer" ? Number.parseInt(input.value, 10) : Number.parseFloat(input.value);
            return Number.isNaN(value) ? null : value;
        }
        if (field.type === "date") {
            return input.value || null;
        }
        if (field.type === "datetime") {
            return input.value || null;
        }
        return input.value;
    }

    function defaultObjectArrayRow(fields) {
        const row = {};
        (fields || []).forEach((field) => {
            row[field.key] = defaultValueForField(field);
        });
        return row;
    }

    function collectCorrections() {
        const corrections = {};
        state.schemaFields.forEach((field) => {
            const key = field.key;
            if (!canEditPath([key])) {
                return;
            }
            if (!deepEqual(state.values[key], state.originalValues[key])) {
                corrections[key] = cloneValue(state.values[key]);
            }
        });
        return corrections;
    }

    return {
        escapeHtml, titleCase, cloneValue, parseJsonMaybe, normalizeSourceValueMode, normalizeFields, defaultValueForField, getByPath, setByPath, pathString, formatValue, optionItems, encodedOptionValue, decodedOptionValue, decimalPlaces, numberStep, formatInputValue, scalarTextValue, fieldLabel, fieldHelpText, hasOwnLock, isComplete, canEditPath, isHighlighted, shouldShowSourceValue, fieldForPath, confidenceInfoForPath, fieldForSchemaPath, initializeValues, parseInputValue, defaultObjectArrayRow, collectCorrections,
    };
}
