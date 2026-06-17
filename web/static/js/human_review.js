(function () {
    "use strict";

    const state = {
        reviewItemId: "",
        operator: "",
        reviewItem: null,
        metadata: {},
        document: null,
        fields: [],
        fieldsByKey: new Map(),
        schemaFields: [],
        originalValues: {},
        values: {},
        lock: null,
        sourceValueMode: "review",
        sourceValueReveals: new Set(),
    };

    const elements = {};

    function bindElements() {
        elements.workspace = document.getElementById("human-review-workspace");
        elements.documentTitle = document.getElementById("review-document-title");
        elements.documentSubtitle = document.getElementById("review-document-subtitle");
        elements.pdfBody = document.getElementById("review-pdf-body");
        elements.pdfOpenLink = document.getElementById("review-pdf-open-link");
        elements.itemBadge = document.getElementById("review-item-badge");
        elements.statusBadge = document.getElementById("review-status-badge");
        elements.reasonSummary = document.getElementById("review-reason-summary");
        elements.fieldsContainer = document.getElementById("review-fields-container");
        elements.lockBanner = document.getElementById("review-lock-banner");
        elements.lockSummary = document.getElementById("review-lock-summary");
        elements.claimButton = document.getElementById("review-claim-button");
        elements.releaseButton = document.getElementById("review-release-button");
        elements.saveButton = document.getElementById("review-save-button");
        elements.completeButton = document.getElementById("review-complete-button");
        elements.diffButton = document.getElementById("review-diff-button");
        elements.sourceModeSelect = document.getElementById("review-source-mode-select");
        elements.diffPanel = document.getElementById("review-diff-panel");
        elements.diffBody = document.getElementById("review-diff-body");
        elements.diffCloseButton = document.getElementById("review-diff-close-button");
    }

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

    function storageGet(key) {
        try {
            return window.localStorage.getItem(key);
        } catch (error) {
            return null;
        }
    }

    function storageSet(key, value) {
        try {
            window.localStorage.setItem(key, value);
        } catch (error) {
            // Preference persistence is optional; keep the current in-page state.
        }
    }

    function normalizeSourceValueMode(mode) {
        return ["review", "all", "hidden"].includes(mode) ? mode : "review";
    }

    function initializeSourceValueMode() {
        state.sourceValueMode = normalizeSourceValueMode(storageGet("docflow.review.sourceValueMode"));
        if (elements.sourceModeSelect) {
            elements.sourceModeSelect.value = state.sourceValueMode;
        }
        if (elements.workspace) {
            elements.workspace.dataset.sourceValueMode = state.sourceValueMode;
        }
    }

    function setSourceValueMode(mode) {
        state.sourceValueMode = normalizeSourceValueMode(mode);
        state.sourceValueReveals.clear();
        storageSet("docflow.review.sourceValueMode", state.sourceValueMode);
        if (elements.sourceModeSelect) {
            elements.sourceModeSelect.value = state.sourceValueMode;
        }
        if (elements.workspace) {
            elements.workspace.dataset.sourceValueMode = state.sourceValueMode;
        }
        renderEditor();
    }

    function renderPdfPreview() {
        const documentPayload = state.document || {};
        const filename = documentPayload.filename || documentPayload.original_filename || "Document";
        if (documentPayload.preview_url) {
            elements.pdfOpenLink.href = documentPayload.preview_url;
            elements.pdfOpenLink.classList.remove("hidden");
            window.DocFlowPdfViewer.renderIframeFallback(
                elements.pdfBody,
                documentPayload.preview_url,
                filename,
            );
        } else {
            elements.pdfOpenLink.classList.add("hidden");
            window.DocFlowPdfViewer.renderIframeFallback(elements.pdfBody, null, filename);
        }
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
        if (value === null || value === undefined) {
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

    function applyInputConstraints(input, field) {
        if (field.required) {
            input.required = true;
        }
        if (field.placeholder) {
            input.placeholder = field.placeholder;
        }
        if (field.min_length !== null && field.min_length !== undefined && input.type !== "number") {
            input.minLength = Number(field.min_length);
        }
        if (field.max_length !== null && field.max_length !== undefined && input.type !== "number") {
            input.maxLength = Number(field.max_length);
        }
        if (field.pattern && input.tagName !== "TEXTAREA") {
            input.pattern = field.pattern;
        }
        if (input.type === "number") {
            if (field.min_value !== null && field.min_value !== undefined && field.min_value !== "") {
                input.min = String(field.min_value);
            }
            if (field.max_value !== null && field.max_value !== undefined && field.max_value !== "") {
                input.max = String(field.max_value);
            }
            input.step = numberStep(field);
        }
    }

    function setConstraintState(input, wrapper) {
        const invalid = Boolean(input.value) && input.validity && !input.validity.valid;
        input.classList.toggle("input-error", invalid);
        input.classList.toggle("textarea-error", invalid);
        wrapper.classList.toggle("review-input-invalid", invalid);
    }

    function deepEqual(left, right) {
        return JSON.stringify(left) === JSON.stringify(right);
    }

    function createElement(tagName, className, text) {
        const element = document.createElement(tagName);
        if (className) {
            element.className = className;
        }
        if (text !== undefined) {
            element.textContent = text;
        }
        return element;
    }

    function iconSvg(paths) {
        return `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                ${paths}
            </svg>
        `;
    }

    function createTooltipIcon(className, tooltip, ariaLabel, iconPaths) {
        const icon = createElement("span", `${className} tooltip tooltip-right`);
        icon.tabIndex = 0;
        icon.title = tooltip;
        icon.setAttribute("data-tip", tooltip);
        icon.setAttribute("aria-label", ariaLabel);
        icon.innerHTML = iconSvg(iconPaths);
        return icon;
    }

    function createIconButton(className, tooltip, ariaLabel, iconPaths) {
        const button = createElement("button", `${className} tooltip tooltip-left`);
        button.type = "button";
        button.title = tooltip;
        button.setAttribute("data-tip", tooltip);
        button.setAttribute("aria-label", ariaLabel);
        button.innerHTML = iconSvg(iconPaths);
        return button;
    }

    function fieldLabel(field) {
        return field.label || titleCase(field.key);
    }

    function fieldHelpText(field) {
        return field.help || field.description || "";
    }

    function appendFieldLabelContent(labelLine, field, options) {
        const settings = options || {};
        const label = fieldLabel(field);
        labelLine.appendChild(createElement("span", settings.labelClass || "font-medium text-sm", label));
        const helpText = fieldHelpText(field);
        if (helpText) {
            labelLine.appendChild(createTooltipIcon(
                "review-field-info",
                helpText,
                `${label}: ${helpText}`,
                '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 17v-6m0-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />',
            ));
        }
        if (field.required) {
            labelLine.appendChild(createElement("span", "badge badge-warning badge-xs", settings.shortBadges ? "Req" : "Required"));
        }
        if (field.readonly) {
            labelLine.appendChild(createElement("span", "badge badge-ghost badge-xs", settings.shortBadges ? "RO" : "Read only"));
        }
    }

    function statusBadge(status) {
        const normalized = String(status || "pending").toLowerCase();
        const badgeClass = normalized === "completed"
            ? "badge-success"
            : normalized === "in_review"
                ? "badge-info"
                : normalized === "pending"
                    ? "badge-warning"
                    : "badge-ghost";
        return `<span class="badge ${badgeClass} badge-sm">${escapeHtml(titleCase(normalized))}</span>`;
    }

    function confidenceBadge(field) {
        const confidence = field && field.confidence;
        if (confidence === null || confidence === undefined || confidence === "") {
            return '<span class="badge badge-ghost badge-sm">Missing</span>';
        }
        const numeric = Number(confidence);
        const badgeClass = Number.isNaN(numeric)
            ? "badge-ghost"
            : numeric < 0.7
                ? "badge-error"
                : numeric < 0.9
                    ? "badge-warning"
                    : "badge-success";
        const text = Number.isNaN(numeric) ? String(confidence) : `${Math.round(numeric * 100)}%`;
        return `<span class="badge ${badgeClass} badge-sm">${escapeHtml(text)}</span>`;
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

    function updateSourceVisibility(row, pathParts, fieldInfo, extractedValue) {
        const currentValue = getByPath(state.values, pathParts);
        const visible = shouldShowSourceValue(pathParts, fieldInfo, currentValue, extractedValue);
        row.classList.toggle("source-hidden", !visible);
        row.classList.toggle("source-visible", visible);
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

    function appendConfidenceBadge(container, fieldInfo, className) {
        const wrapper = createElement("span", className || "review-inline-confidence");
        wrapper.innerHTML = confidenceBadge(fieldInfo);
        container.appendChild(wrapper);
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

    function renderHeader() {
        const documentPayload = state.document || {};
        const filename = documentPayload.filename || documentPayload.original_filename || "Document";
        elements.documentTitle.textContent = filename;
        elements.documentSubtitle.textContent = [
            titleCase(documentPayload.document_type || documentPayload.split_category || "Document"),
            documentPayload.status ? titleCase(documentPayload.status) : "",
        ].filter(Boolean).join(" - ");
        elements.itemBadge.textContent = state.reviewItemId;
        elements.statusBadge.innerHTML = statusBadge(state.reviewItem && state.reviewItem.status);
        elements.statusBadge.classList.remove("hidden");

        const reasons = state.metadata.reasons || [];
        if (reasons.length) {
            elements.reasonSummary.textContent = reasons.map((reason) => titleCase(reason.reason)).join(", ");
        } else {
            elements.reasonSummary.textContent = titleCase(state.reviewItem && state.reviewItem.reason);
        }

        renderPdfPreview();
    }

    function renderLockState() {
        const lockedBy = state.lock && state.lock.locked_by;
        const ownsLock = hasOwnLock();
        const completed = isComplete();
        const showBlockingBanner = Boolean(state.lock && !ownsLock);
        elements.lockBanner.classList.toggle("hidden", !showBlockingBanner);
        if (showBlockingBanner) {
            elements.lockBanner.textContent = `Locked by ${lockedBy || "another operator"} until ${window.DocFlow.formatDateTime(state.lock.expires_at)}.`;
        }

        if (elements.lockSummary) {
            const showOwnLockSummary = Boolean(state.lock && ownsLock);
            elements.lockSummary.classList.toggle("hidden", !showOwnLockSummary);
            elements.lockSummary.textContent = showOwnLockSummary
                ? `Claimed until ${window.DocFlow.formatDateTime(state.lock.expires_at)}`
                : "";
        }

        const claimDisabled = completed || Boolean(state.lock);
        elements.claimButton.disabled = claimDisabled;
        elements.claimButton.classList.toggle("hidden", claimDisabled);
        elements.releaseButton.disabled = completed || !ownsLock;
        elements.saveButton.disabled = completed || !ownsLock;
        elements.completeButton.disabled = completed || !ownsLock;
        elements.diffButton.disabled = completed || !ownsLock;
    }

    function renderScalarInput(field, pathParts, value, editable) {
        const wrapper = createElement("div", "review-input-wrap");
        const options = optionItems(field);
        let input;
        if (options.length) {
            input = createElement("select", "select select-bordered select-sm w-full");
            input.appendChild(new Option("", ""));
            options.forEach((option) => input.appendChild(new Option(option.label, encodedOptionValue(option.value))));
            input.value = value === null || value === undefined ? "" : encodedOptionValue(value);
        } else if (field.type === "boolean" || field.editor === "checkbox") {
            input = createElement("select", "select select-bordered select-sm w-full");
            input.appendChild(new Option(field.required ? "Missing - choose true or false" : "Missing", ""));
            input.appendChild(new Option("True", "true"));
            input.appendChild(new Option("False", "false"));
            input.value = value === true ? "true" : value === false ? "false" : "";
            input.classList.toggle("select-warning", field.required && value === null);
        } else if (field.editor === "textarea") {
            input = createElement("textarea", "textarea textarea-bordered textarea-sm w-full");
            input.rows = 2;
            input.value = value ?? "";
        } else {
            input = createElement("input", "input input-bordered input-sm w-full");
            input.type = field.type === "number" || field.type === "integer" || field.type === "float"
                ? "number"
                : field.type === "date"
                    ? "date"
                    : field.type === "datetime"
                        ? "datetime-local"
                        : "text";
            input.value = formatInputValue(field, value);
        }

        input.dataset.fieldPath = pathString(pathParts);
        applyInputConstraints(input, field);
        input.disabled = !editable;
        const eventName = input.tagName === "SELECT" ? "change" : "input";
        input.addEventListener(eventName, () => {
            setByPath(state.values, pathParts, parseInputValue(input, field));
            setConstraintState(input, wrapper);
        });
        if (!wrapper.children.length) {
            wrapper.appendChild(input);
        }
        setConstraintState(input, wrapper);
        return wrapper;
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

    function renderScalarField(field, pathParts, container) {
        const fieldInfo = fieldForPath(pathParts);
        const confidenceInfo = confidenceInfoForPath(pathParts);
        const value = getByPath(state.values, pathParts);
        const extracted = getByPath({ [pathParts[0]]: fieldInfo ? fieldInfo.extracted_value : undefined }, pathParts);
        const editable = canEditPath(pathParts);
        const row = createElement("div", "review-field-row");
        row.dataset.fieldPath = pathString(pathParts);
        row.classList.toggle("highlight", isHighlighted(pathParts));
        row.classList.toggle("locked", !editable);

        const labelCell = createElement("div", "review-field-label");
        const labelLine = createElement("div", "review-label-line");
        appendFieldLabelContent(labelLine, field);
        labelCell.appendChild(labelLine);
        row.appendChild(labelCell);

        const sourceCell = createElement("div", "review-source-cell");
        sourceCell.appendChild(createElement("div", "review-extracted-value", `Source: ${formatValue(extracted)}`));
        const revealButton = createIconButton(
            "btn btn-ghost btn-xs btn-square review-source-reveal",
            "Show source value",
            `Show source value for ${fieldLabel(field)}`,
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5s8.268 2.943 9.542 7c-1.274 4.057-5.065 7-9.542 7S3.732 16.057 2.458 12z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />',
        );
        revealButton.addEventListener("click", () => {
            state.sourceValueReveals.add(pathString(pathParts));
            updateSourceVisibility(row, pathParts, fieldInfo, extracted);
        });
        sourceCell.appendChild(revealButton);
        row.appendChild(sourceCell);

        const confidence = createElement("div", "review-confidence-cell");
        confidence.innerHTML = confidenceBadge(confidenceInfo);
        row.appendChild(confidence);

        row.appendChild(renderScalarInput(field, pathParts, value, editable));
        row.addEventListener("input", () => updateSourceVisibility(row, pathParts, fieldInfo, extracted));
        row.addEventListener("change", () => updateSourceVisibility(row, pathParts, fieldInfo, extracted));
        updateSourceVisibility(row, pathParts, fieldInfo, extracted);
        container.appendChild(row);
    }

    function renderObjectField(field, pathParts, container) {
        const value = getByPath(state.values, pathParts);
        if (!value || typeof value !== "object" || Array.isArray(value)) {
            setByPath(state.values, pathParts, {});
        }
        const group = createElement("div", "review-nested-group");
        const header = createElement("div", "review-nested-header");
        const title = createElement("div", "review-label-line");
        appendFieldLabelContent(title, field);
        appendConfidenceBadge(title, confidenceInfoForPath(pathParts));
        header.appendChild(title);
        group.appendChild(header);

        const body = createElement("div", "review-nested-body");
        const children = field.children || [];
        if (!children.length) {
            const textarea = createElement("textarea", "textarea textarea-bordered textarea-sm w-full");
            textarea.rows = 4;
            textarea.value = JSON.stringify(getByPath(state.values, pathParts) || {}, null, 2);
            textarea.disabled = !canEditPath(pathParts);
            textarea.classList.add("review-json-editor");
            textarea.addEventListener("input", () => {
                try {
                    setByPath(state.values, pathParts, JSON.parse(textarea.value || "{}"));
                    textarea.classList.remove("textarea-error");
                } catch (error) {
                    setByPath(state.values, pathParts, textarea.value);
                    textarea.classList.add("textarea-error");
                }
            });
            body.appendChild(textarea);
        } else {
            children.forEach((child) => renderField(child, [...pathParts, child.key], body));
        }
        group.appendChild(body);
        container.appendChild(group);
    }

    function renderScalarArrayField(field, pathParts, container) {
        let value = getByPath(state.values, pathParts);
        if (!Array.isArray(value)) {
            value = [];
            setByPath(state.values, pathParts, value);
        }
        const group = createElement("div", "review-nested-group");
        const header = createElement("div", "review-nested-header flex items-center justify-between gap-2");
        const titleWrap = createElement("div", "");
        const title = createElement("div", "review-label-line");
        appendFieldLabelContent(title, field);
        appendConfidenceBadge(title, confidenceInfoForPath(pathParts));
        titleWrap.appendChild(title);
        header.appendChild(titleWrap);
        const addButton = createElement("button", "btn btn-outline btn-xs", "Add");
        addButton.type = "button";
        addButton.disabled = !canEditPath(pathParts);
        addButton.addEventListener("click", () => {
            value.push(defaultValueForField(field.item_schema || { type: "string" }));
            renderEditor();
        });
        header.appendChild(addButton);
        group.appendChild(header);

        const body = createElement("div", "review-nested-body review-array-list");
        if (!value.length) {
            body.appendChild(createElement("div", "text-sm text-base-content/50", "No values"));
        }
        value.forEach((item, index) => {
            const row = createElement("div", "review-array-row");
            const itemField = { ...(field.item_schema || { type: "string" }), key: String(index), label: `${field.label || field.key} ${index + 1}` };
            row.classList.toggle("highlight", isHighlighted([...pathParts, index]));
            appendConfidenceBadge(row, confidenceInfoForPath([...pathParts, index]));
            row.appendChild(renderScalarInput(itemField, [...pathParts, index], item, canEditPath(pathParts)));
            const removeButton = createElement("button", "btn btn-ghost btn-xs", "Remove");
            removeButton.type = "button";
            removeButton.disabled = !canEditPath(pathParts);
            removeButton.addEventListener("click", () => {
                value.splice(index, 1);
                renderEditor();
            });
            row.appendChild(removeButton);
            body.appendChild(row);
        });
        group.appendChild(body);
        container.appendChild(group);
    }

    function defaultObjectArrayRow(fields) {
        const row = {};
        (fields || []).forEach((field) => {
            row[field.key] = defaultValueForField(field);
        });
        return row;
    }

    function renderObjectArrayField(field, pathParts, container) {
        let value = getByPath(state.values, pathParts);
        if (!Array.isArray(value)) {
            value = [];
            setByPath(state.values, pathParts, value);
        }
        const itemFields = field.item_schema && Array.isArray(field.item_schema.fields) ? field.item_schema.fields : [];
        const group = createElement("div", "review-nested-group");
        const header = createElement("div", "review-nested-header flex items-center justify-between gap-2");
        const titleWrap = createElement("div", "");
        const title = createElement("div", "review-label-line");
        appendFieldLabelContent(title, field);
        appendConfidenceBadge(title, confidenceInfoForPath(pathParts));
        titleWrap.appendChild(title);
        header.appendChild(titleWrap);
        const addButton = createElement("button", "btn btn-outline btn-xs", "Add Row");
        addButton.type = "button";
        addButton.disabled = !canEditPath(pathParts);
        addButton.addEventListener("click", () => {
            value.push(defaultObjectArrayRow(itemFields));
            renderEditor();
        });
        header.appendChild(addButton);
        group.appendChild(header);

        const body = createElement("div", "review-nested-body review-object-array");
        if (!itemFields.length) {
            body.appendChild(createElement("div", "text-sm text-base-content/50", "No item schema available"));
        } else {
            const table = createElement("table", "table table-xs review-object-array-table");
            const thead = createElement("thead");
            const headerRow = createElement("tr");
            itemFields.forEach((itemField) => {
                const headingCell = createElement("th");
                const heading = createElement("div", "review-table-heading");
                appendFieldLabelContent(heading, itemField, { labelClass: "", shortBadges: true });
                headingCell.appendChild(heading);
                headerRow.appendChild(headingCell);
            });
            headerRow.appendChild(createElement("th"));
            thead.appendChild(headerRow);
            table.appendChild(thead);
            const tbody = createElement("tbody");
            if (!value.length) {
                const emptyRow = createElement("tr");
                emptyRow.innerHTML = `<td colspan="${itemFields.length + 1}" class="text-center text-base-content/50 py-4">No rows</td>`;
                tbody.appendChild(emptyRow);
            }
            value.forEach((item, index) => {
                const row = createElement("tr");
                itemFields.forEach((itemField) => {
                    const cell = createElement("td");
                    const itemPath = [...pathParts, index, itemField.key];
                    cell.classList.toggle("highlight", isHighlighted(itemPath));
                    appendConfidenceBadge(cell, confidenceInfoForPath(itemPath), "review-cell-confidence");
                    cell.appendChild(renderScalarInput(itemField, itemPath, item ? item[itemField.key] : "", canEditPath(pathParts) && !itemField.readonly));
                    row.appendChild(cell);
                });
                const actionCell = createElement("td", "text-right");
                const removeButton = createElement("button", "btn btn-ghost btn-xs", "Remove");
                removeButton.type = "button";
                removeButton.disabled = !canEditPath(pathParts);
                removeButton.addEventListener("click", () => {
                    value.splice(index, 1);
                    renderEditor();
                });
                actionCell.appendChild(removeButton);
                row.appendChild(actionCell);
                tbody.appendChild(row);
            });
            table.appendChild(tbody);
            body.appendChild(table);
        }
        group.appendChild(body);
        container.appendChild(group);
    }

    function renderField(field, pathParts, container) {
        if (field.type === "object" || field.editor === "object") {
            renderObjectField(field, pathParts, container);
        } else if (field.type === "array" && (field.editor === "object_array" || (field.item_schema && field.item_schema.type === "object"))) {
            renderObjectArrayField(field, pathParts, container);
        } else if (field.type === "array") {
            renderScalarArrayField(field, pathParts, container);
        } else {
            renderScalarField(field, pathParts, container);
        }
    }

    function renderEditor() {
        elements.fieldsContainer.innerHTML = "";
        if (!state.schemaFields.length) {
            elements.fieldsContainer.innerHTML = '<div class="empty-panel">No fields loaded</div>';
            return;
        }
        state.schemaFields.forEach((field) => {
            if (!Object.prototype.hasOwnProperty.call(state.values, field.key)) {
                state.values[field.key] = defaultValueForField(field);
            }
            renderField(field, [field.key], elements.fieldsContainer);
        });
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

    function renderDiff(diff) {
        elements.diffPanel.classList.remove("hidden");
        const changes = diff.changes || [];
        if (!changes.length) {
            elements.diffBody.innerHTML = '<div class="text-base-content/60">No changes from current final values.</div>';
            return;
        }
        elements.diffBody.innerHTML = changes.map((change) => `
            <div class="review-diff-row">
                <div class="font-medium">${escapeHtml(titleCase(change.field))}</div>
                <div class="review-diff-value text-base-content/60">${escapeHtml(formatValue(change.old_value))}</div>
                <div class="review-diff-value font-medium">${escapeHtml(formatValue(change.new_value))}</div>
            </div>
        `).join("");
    }

    function applyPayload(payload) {
        state.reviewItem = payload.review_item || {};
        state.metadata = payload.metadata || state.reviewItem.metadata || {};
        state.document = payload.document || null;
        state.lock = payload.lock || null;
        initializeValues(payload);
        renderHeader();
        renderLockState();
        renderEditor();
    }

    async function loadReviewItem() {
        elements.fieldsContainer.innerHTML = '<div class="empty-panel">Loading review details...</div>';
        try {
            const payload = await window.DocFlow.apiGet(`/api/review/items/${encodeURIComponent(state.reviewItemId)}`);
            applyPayload(payload);
        } catch (error) {
            elements.fieldsContainer.innerHTML = '<div class="empty-panel text-error">Review item failed to load</div>';
            window.DocFlow.showToast(error.message || "Review item failed to load", "error");
        }
    }

    async function claimReview() {
        elements.claimButton.disabled = true;
        try {
            await window.DocFlow.apiPost(`/api/review/items/${encodeURIComponent(state.reviewItemId)}/claim`, {});
            window.DocFlow.showToast("Review item claimed", "success");
            await loadReviewItem();
        } catch (error) {
            elements.claimButton.disabled = false;
            window.DocFlow.showToast(error.message || "Unable to claim review item", "error");
        }
    }

    async function releaseReview() {
        elements.releaseButton.disabled = true;
        try {
            await window.DocFlow.apiPost(`/api/review/items/${encodeURIComponent(state.reviewItemId)}/release`, {});
            window.DocFlow.showToast("Review item released", "success");
            await loadReviewItem();
        } catch (error) {
            elements.releaseButton.disabled = false;
            window.DocFlow.showToast(error.message || "Unable to release review item", "error");
        }
    }

    async function saveDraft() {
        elements.saveButton.disabled = true;
        try {
            const payload = await window.DocFlow.apiPost(
                `/api/review/items/${encodeURIComponent(state.reviewItemId)}/draft`,
                { corrections: collectCorrections() },
            );
            applyPayload(payload);
            window.DocFlow.showToast("Draft saved", "success");
        } catch (error) {
            elements.saveButton.disabled = false;
            window.DocFlow.showToast(error.message || "Unable to save draft", "error");
        }
    }

    async function previewDiff() {
        elements.diffButton.disabled = true;
        try {
            const payload = await window.DocFlow.apiPost(
                `/api/review/items/${encodeURIComponent(state.reviewItemId)}/diff`,
                { corrections: collectCorrections() },
            );
            renderDiff(payload);
        } catch (error) {
            window.DocFlow.showToast(error.message || "Unable to preview diff", "error");
        } finally {
            elements.diffButton.disabled = false;
        }
    }

    async function completeReview() {
        elements.completeButton.disabled = true;
        try {
            await window.DocFlow.apiPost(
                `/api/review/items/${encodeURIComponent(state.reviewItemId)}/complete`,
                { corrections: collectCorrections() },
            );
            window.DocFlow.showToast("Review completed", "success");
            window.location.href = "/app/review";
        } catch (error) {
            elements.completeButton.disabled = false;
            window.DocFlow.showToast(error.message || "Unable to complete review", "error");
        }
    }

    function bindEvents() {
        elements.claimButton.addEventListener("click", claimReview);
        elements.releaseButton.addEventListener("click", releaseReview);
        elements.saveButton.addEventListener("click", saveDraft);
        elements.diffButton.addEventListener("click", previewDiff);
        elements.completeButton.addEventListener("click", completeReview);
        elements.diffCloseButton.addEventListener("click", () => elements.diffPanel.classList.add("hidden"));
        if (elements.sourceModeSelect) {
            elements.sourceModeSelect.addEventListener("change", () => setSourceValueMode(elements.sourceModeSelect.value));
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        bindElements();
        if (!elements.workspace) {
            return;
        }
        state.reviewItemId = elements.workspace.dataset.reviewItemId || "";
        state.operator = elements.workspace.dataset.reviewOperator || "";
        initializeSourceValueMode();
        if (!state.reviewItemId) {
            elements.fieldsContainer.innerHTML = '<div class="empty-panel text-error">Missing review item id</div>';
            return;
        }
        bindEvents();
        loadReviewItem();
    });
})();
