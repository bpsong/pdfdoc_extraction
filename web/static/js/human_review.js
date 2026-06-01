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
        elements.claimButton = document.getElementById("review-claim-button");
        elements.releaseButton = document.getElementById("review-release-button");
        elements.saveButton = document.getElementById("review-save-button");
        elements.completeButton = document.getElementById("review-complete-button");
        elements.diffButton = document.getElementById("review-diff-button");
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
            return false;
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
            return "";
        }
        if (Array.isArray(value)) {
            return `${value.length} item${value.length === 1 ? "" : "s"}`;
        }
        if (typeof value === "object") {
            return JSON.stringify(value);
        }
        return String(value);
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
        if (!highlighted.length) {
            return false;
        }
        const fullPath = pathString(pathParts);
        const rootKey = String(pathParts[0]);
        return highlighted.includes(fullPath) || highlighted.includes(rootKey);
    }

    function fieldForPath(pathParts) {
        return state.fieldsByKey.get(String(pathParts[0])) || null;
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

        if (documentPayload.preview_url) {
            elements.pdfOpenLink.href = documentPayload.preview_url;
            elements.pdfOpenLink.classList.remove("hidden");
            window.DocFlowPdfViewer.renderIframeFallback(elements.pdfBody, documentPayload.preview_url, filename);
        } else {
            elements.pdfOpenLink.classList.add("hidden");
            window.DocFlowPdfViewer.renderIframeFallback(elements.pdfBody, null, filename);
        }
    }

    function renderLockState() {
        const lockedBy = state.lock && state.lock.locked_by;
        const ownsLock = hasOwnLock();
        elements.lockBanner.classList.toggle("hidden", !state.lock);
        if (state.lock) {
            elements.lockBanner.textContent = ownsLock
                ? `Claimed by you until ${window.DocFlow.formatDateTime(state.lock.expires_at)}.`
                : `Locked by ${lockedBy || "another operator"} until ${window.DocFlow.formatDateTime(state.lock.expires_at)}.`;
        }

        const completed = isComplete();
        elements.claimButton.disabled = completed || ownsLock;
        elements.releaseButton.disabled = completed || !ownsLock;
        elements.saveButton.disabled = completed || !ownsLock;
        elements.completeButton.disabled = completed || !ownsLock;
        elements.diffButton.disabled = completed || !ownsLock;
    }

    function renderScalarInput(field, pathParts, value, editable) {
        const wrapper = createElement("div", "");
        const options = field.options || [];
        let input;
        if (options.length) {
            input = createElement("select", "select select-bordered select-sm w-full");
            input.appendChild(new Option("", ""));
            options.forEach((option) => input.appendChild(new Option(String(option), String(option))));
            input.value = value ?? "";
        } else if (field.type === "boolean" || field.editor === "checkbox") {
            const label = createElement("label", "label cursor-pointer justify-start gap-2");
            input = createElement("input", "checkbox checkbox-sm");
            input.type = "checkbox";
            input.checked = Boolean(value);
            label.appendChild(input);
            label.appendChild(createElement("span", "label-text", "True"));
            wrapper.appendChild(label);
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
            if (input.type === "number") {
                input.step = field.type === "integer" ? "1" : "any";
            }
            input.value = value ?? "";
        }

        input.disabled = !editable;
        const eventName = input.type === "checkbox" ? "change" : "input";
        input.addEventListener(eventName, () => {
            setByPath(state.values, pathParts, parseInputValue(input, field));
        });
        if (!wrapper.children.length) {
            wrapper.appendChild(input);
        }
        return wrapper;
    }

    function parseInputValue(input, field) {
        if (input.type === "checkbox") {
            return input.checked;
        }
        if (field.type === "number" || field.type === "float" || field.type === "integer") {
            if (input.value === "") {
                return null;
            }
            const value = field.type === "integer" ? Number.parseInt(input.value, 10) : Number.parseFloat(input.value);
            return Number.isNaN(value) ? null : value;
        }
        return input.value;
    }

    function renderScalarField(field, pathParts, container) {
        const fieldInfo = fieldForPath(pathParts);
        const value = getByPath(state.values, pathParts);
        const extracted = getByPath({ [pathParts[0]]: fieldInfo ? fieldInfo.extracted_value : undefined }, pathParts);
        const editable = canEditPath(pathParts);
        const row = createElement("div", "review-field-row");
        row.classList.toggle("highlight", isHighlighted(pathParts));
        row.classList.toggle("locked", !editable);

        const labelCell = createElement("div", "review-field-label");
        labelCell.appendChild(createElement("div", "font-medium text-sm", field.label || titleCase(field.key)));
        if (field.description) {
            labelCell.appendChild(createElement("div", "text-xs text-base-content/50", field.description));
        }
        row.appendChild(labelCell);

        row.appendChild(createElement("div", "review-extracted-value", formatValue(extracted)));

        const confidence = createElement("div", "");
        confidence.innerHTML = confidenceBadge(fieldInfo);
        row.appendChild(confidence);

        row.appendChild(renderScalarInput(field, pathParts, value, editable));
        container.appendChild(row);
    }

    function renderObjectField(field, pathParts, container) {
        const value = getByPath(state.values, pathParts);
        if (!value || typeof value !== "object" || Array.isArray(value)) {
            setByPath(state.values, pathParts, {});
        }
        const group = createElement("div", "review-nested-group");
        const header = createElement("div", "review-nested-header");
        header.appendChild(createElement("div", "font-medium text-sm", field.label || titleCase(field.key)));
        if (field.description) {
            header.appendChild(createElement("div", "text-xs text-base-content/50", field.description));
        }
        group.appendChild(header);

        const body = createElement("div", "review-nested-body");
        const children = field.children || [];
        if (!children.length) {
            const textarea = createElement("textarea", "textarea textarea-bordered textarea-sm w-full");
            textarea.rows = 4;
            textarea.value = JSON.stringify(getByPath(state.values, pathParts) || {}, null, 2);
            textarea.disabled = !canEditPath(pathParts);
            textarea.addEventListener("input", () => {
                try {
                    setByPath(state.values, pathParts, JSON.parse(textarea.value || "{}"));
                } catch (error) {
                    setByPath(state.values, pathParts, textarea.value);
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
        header.appendChild(createElement("div", "font-medium text-sm", field.label || titleCase(field.key)));
        const addButton = createElement("button", "btn btn-outline btn-xs", "Add");
        addButton.type = "button";
        addButton.disabled = !canEditPath(pathParts);
        addButton.addEventListener("click", () => {
            value.push("");
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
        header.appendChild(createElement("div", "font-medium text-sm", field.label || titleCase(field.key)));
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
            const table = createElement("table", "table table-xs");
            const thead = createElement("thead");
            thead.innerHTML = `<tr>${itemFields.map((itemField) => `<th>${escapeHtml(itemField.label || titleCase(itemField.key))}</th>`).join("")}<th></th></tr>`;
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
                    cell.appendChild(renderScalarInput(itemField, itemPath, item ? item[itemField.key] : "", canEditPath(pathParts)));
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
    }

    document.addEventListener("DOMContentLoaded", () => {
        bindElements();
        if (!elements.workspace) {
            return;
        }
        state.reviewItemId = elements.workspace.dataset.reviewItemId || "";
        state.operator = elements.workspace.dataset.reviewOperator || "";
        if (!state.reviewItemId) {
            elements.fieldsContainer.innerHTML = '<div class="empty-panel text-error">Missing review item id</div>';
            return;
        }
        bindEvents();
        loadReviewItem();
    });
})();
