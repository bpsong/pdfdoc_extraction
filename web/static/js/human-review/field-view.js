/** DOM rendering for scalar, object, and array review fields. */

export function createHumanReviewFieldView(state, elements, model, view) {
    const { escapeHtml, titleCase, defaultValueForField, getByPath, setByPath, pathString, formatValue, optionItems, encodedOptionValue, decodedOptionValue, numberStep, formatInputValue, scalarTextValue, fieldLabel, fieldHelpText, isComplete, canEditPath, isHighlighted, shouldShowSourceValue, fieldForPath, confidenceInfoForPath, parseInputValue, defaultObjectArrayRow } = model;
    const { selectPdfField } = view;

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
        const invalid = !input.disabled && Boolean(input.value) && input.validity && !input.validity.valid;
        input.classList.toggle("input-error", invalid);
        input.classList.toggle("textarea-error", invalid);
        wrapper.classList.toggle("review-input-invalid", invalid);
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

    function confidenceBadge(field) {
        const confidence = field && field.confidence;
        if (confidence === null || confidence === undefined || confidence === "") {
            const label = isComplete() ? "No model confidence" : "Missing confidence";
            return `<span class="badge badge-ghost badge-sm" title="Original extraction confidence">${label}</span>`;
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
        const band = Number.isNaN(numeric) ? "Unknown" : numeric < 0.7 ? "Low" : numeric < 0.9 ? "Medium" : "High";
        return `<span class="badge ${badgeClass} badge-sm" title="Original extraction confidence">${band} confidence · ${escapeHtml(text)}</span>`;
    }

    function updateSourceVisibility(row, pathParts, fieldInfo, extractedValue) {
        const currentValue = getByPath(state.values, pathParts);
        const visible = shouldShowSourceValue(pathParts, fieldInfo, currentValue, extractedValue);
        row.classList.toggle("source-hidden", !visible);
        row.classList.toggle("source-visible", visible);
    }

    function appendConfidenceBadge(container, fieldInfo, className) {
        const wrapper = createElement("span", className || "review-inline-confidence");
        wrapper.innerHTML = confidenceBadge(fieldInfo);
        container.appendChild(wrapper);
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
            input.value = scalarTextValue(value);
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

    function renderScalarField(field, pathParts, container) {
        const fieldInfo = fieldForPath(pathParts);
        const confidenceInfo = confidenceInfoForPath(pathParts);
        const value = getByPath(state.values, pathParts);
        const extracted = getByPath({ [pathParts[0]]: fieldInfo ? fieldInfo.extracted_value : undefined }, pathParts);
        const editable = canEditPath(pathParts);
        const row = createElement("div", "review-field-row");
        row.dataset.fieldPath = pathString(pathParts);
        row.classList.toggle("highlight", !isComplete() && isHighlighted(pathParts));
        row.classList.toggle("locked", !editable);
        row.addEventListener("click", () => selectPdfField(pathParts, field));

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
        row.querySelector("input, textarea, select")?.addEventListener("focus", () => selectPdfField(pathParts, field));
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
        header.addEventListener("click", () => selectPdfField(pathParts, field));
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
            textarea.addEventListener("focus", () => selectPdfField(pathParts, field));
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
            row.classList.toggle("highlight", !isComplete() && isHighlighted([...pathParts, index]));
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
                    cell.classList.toggle("highlight", !isComplete() && isHighlighted(itemPath));
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
        const preferredField = state.schemaFields.find((field) => isHighlighted([field.key])) || state.schemaFields[0];
        if (preferredField) {
            selectPdfField([preferredField.key], preferredField);
        }
    }

    return { renderEditor };
}
