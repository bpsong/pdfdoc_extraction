/** Review-form list, field controls, outline, preview, and validation views. */

export function createSchemaEditorView(elements, helpers) {
    const { escapeHtml, fieldEntries, fieldTypes, combinedFindings, getState, setBox } = helpers;
    const { schemaList, schemaCount, fieldOutline, fieldNavigation, fieldTree, yamlPreview,
        validationResults, saveButton, validateButton, nameInput, titleInput,
        actionGuidance, detailTitle, detailHash, identityWarningBox,
        duplicateButton, exportButton, statusSelect, revisionLabel,
        latestVersionLabel, versionHistory, dependencyUsage } = elements;

    function findingId(path) {
        return `schema-finding-${String(path).replace(/[^a-zA-Z0-9_-]+/g, "-")}`;
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
        const { patternExamples, patternResults } = getState();
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

    function renderSchemaList() {
        const { schemas, schemaSearch, currentId } = getState();
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
            <button class="schema-list-item ${schema.id === currentId ? "active" : ""}" type="button" data-schema-id="${escapeHtml(schema.id)}">
                <div class="flex items-center justify-between gap-2"><span class="font-medium text-sm truncate">${escapeHtml(schema.name)}</span><span class="badge badge-ghost badge-xs">${escapeHtml(schema.status)}</span></div>
                <div class="text-xs text-base-content/50 truncate">${escapeHtml(schema.schema_key)} · r${escapeHtml(schema.draft_revision || "—")} · v${escapeHtml(schema.latest_version || "—")}</div>
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
                <details class="schema-field-details">
                    <summary class="schema-field-summary">
                        <span class="font-medium">${escapeHtml(fieldName)}</span>
                        <span class="font-mono text-base-content/50">${escapeHtml(key)}</span>
                        <span class="badge badge-ghost badge-xs">${escapeHtml(config.type || "string")}</span>
                        ${config.required ? '<span class="badge badge-primary badge-xs">Required</span>' : ""}
                    </summary>
                    <div class="schema-field-editor-grid">
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
                </details>
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
        const { draft } = getState();
        yamlPreview.textContent = renderYamlValue(draft, 0).trimStart() + "\n";
    }

    function renderFieldOutline() {
        const { fieldSearch, draft } = getState();
        const links = [];
        const query = fieldSearch.trim().toLowerCase();
        function visit(fields, parentPath = "", depth = 0) {
            fieldEntries(fields).forEach(([key, config]) => {
                const path = parentPath ? `${parentPath}.${key}` : key;
                const depthClass = `schema-outline-depth-${Math.min(depth, 4)}`;
                const label = config.label || key;
                if (!query || `${label} ${key}`.toLowerCase().includes(query)) {
                    links.push(`
                        <button class="schema-outline-link ${depthClass}" type="button" data-outline-path="${escapeHtml(path)}">
                            <span class="font-medium">${escapeHtml(label)}</span>
                            <span class="font-mono text-base-content/50">${escapeHtml(key)}</span>
                        </button>
                    `);
                }
                if (config.type === "object") {
                    visit(config.properties || {}, path, depth + 1);
                } else if (config.type === "array" && config.items && config.items.type === "object") {
                    visit(config.items.properties || {}, path, depth + 1);
                }
            });
        }
        visit(draft.fields || {});
        fieldOutline.innerHTML = links.length ? links.join("") : '<p class="schema-outline-empty">No matching fields</p>';
        fieldNavigation.classList.toggle("hidden", links.length < 2 && !query);
    }

    function displayFindingPath(path) {
        return String(path).replace(/\.items(?=\.|$)/g, "[]");
    }

    function renderValidationSummary() {
        const { validationState } = getState();
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
        const { dirty } = getState();
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

    function captureFieldTreeFocus() {
        const active = document.activeElement;
        if (!active || !fieldTree.contains(active)) {
            return null;
        }

        let selector = "";
        if (active.dataset.fieldPath && active.dataset.fieldProp) {
            selector = `${active.tagName.toLowerCase()}[data-field-path="${CSS.escape(active.dataset.fieldPath)}"][data-field-prop="${CSS.escape(active.dataset.fieldProp)}"]`;
        } else if (active.dataset.moveField && active.dataset.moveDirection) {
            selector = `${active.tagName.toLowerCase()}[data-move-field="${CSS.escape(active.dataset.moveField)}"][data-move-direction="${CSS.escape(active.dataset.moveDirection)}"]`;
        } else if (active.dataset.deleteField) {
            selector = `${active.tagName.toLowerCase()}[data-delete-field="${CSS.escape(active.dataset.deleteField)}"]`;
        } else {
            return null;
        }
        const matches = Array.from(fieldTree.querySelectorAll(selector));
        const matchIndex = Math.max(0, matches.indexOf(active));
        const hasSelection = typeof active.selectionStart === "number";
        return {
            selector,
            matchIndex,
            selectionStart: hasSelection ? active.selectionStart : null,
            selectionEnd: hasSelection ? active.selectionEnd : null,
            selectionDirection: hasSelection ? active.selectionDirection : null,
            treeScrollLeft: fieldTree.scrollLeft,
            treeScrollTop: fieldTree.scrollTop,
            windowScrollX: window.scrollX,
            windowScrollY: window.scrollY,
        };
    }

    function renderFieldTreeWithFocusRestore() {
        const { draft } = getState();
        const focus = captureFieldTreeFocus();
        fieldTree.innerHTML = renderFieldRows(draft.fields || {}, []);
        if (!focus) {
            return;
        }

        const matches = fieldTree.querySelectorAll(focus.selector);
        const restored = matches[focus.matchIndex] || matches[0];
        if (!restored) {
            return;
        }
        let compactEditor = restored.closest("details.schema-field-details");
        while (compactEditor) {
            compactEditor.open = true;
            compactEditor = compactEditor.parentElement?.closest("details.schema-field-details");
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
        fieldTree.scrollLeft = focus.treeScrollLeft;
        fieldTree.scrollTop = focus.treeScrollTop;
        window.scrollTo(focus.windowScrollX, focus.windowScrollY);
    }

    function renderMetadata() {
        const { schemas, currentId, currentName, currentTemplate, currentRevision,
            currentVersions, currentUsage, dirty } = getState();
        const displayName = titleInput.value || nameInput.value || currentName || "New review form";
        detailTitle.textContent = `${dirty ? "* " : ""}${displayName}`;
        detailHash.textContent = currentName
            ? `Stable key: ${currentName}${detailHash.dataset.hash ? ` · ${detailHash.dataset.hash}` : ""}`
            : "";
        const listedName = schemas.find((schema) => schema.id === currentId)?.name
            || currentTemplate && currentTemplate.name
            || "";
        const draftTitle = titleInput.value.trim();
        const namesDiffer = listedName && draftTitle && listedName.trim().toLowerCase() !== draftTitle.toLowerCase();
        setBox(identityWarningBox, namesDiffer
            ? `The list name “${listedName}” and this draft title “${draftTitle}” differ. They remain unchanged; confirm the intended form before publishing.`
            : "");
        duplicateButton.disabled = !currentId || !currentRevision || currentTemplate && currentTemplate.status === "archived";
        exportButton.disabled = !currentId;
        statusSelect.disabled = !currentId;
        revisionLabel.textContent = currentRevision ? `Draft revision ${currentRevision}` : "Revision —";
        latestVersionLabel.textContent = currentVersions.length ? `Latest version ${currentVersions[0].version_number}` : "No published version";
        versionHistory.innerHTML = currentVersions.length
            ? currentVersions.map((version) => `<div class="rounded-lg border border-base-300 p-2"><strong>Version ${escapeHtml(version.version_number)}</strong><div class="text-xs text-base-content/60">${escapeHtml(version.published_at || "")} · ${escapeHtml(String(version.content_hash || "").slice(0, 12))}</div></div>`).join("")
            : '<div class="empty-panel py-3">No published versions</div>';
        dependencyUsage.innerHTML = currentUsage.dependency_count
            ? `<strong>Used by ${escapeHtml(currentUsage.dependency_count)} published pipeline task(s)</strong>${(currentUsage.dependencies || []).map((item) => `<div class="mt-1 text-xs">${escapeHtml(item.pipeline_name)} v${escapeHtml(item.pipeline_version_number)} · ${escapeHtml(item.task_key)}</div>`).join("")}`
            : '<span class="text-base-content/60">No published pipeline dependencies.</span>';
    }

    return { findingId, pathsMatch, renderSchemaList, renderFieldRows,
        renderPreview, renderFieldOutline, renderValidationSummary,
        renderActionState, renderFieldTreeWithFocusRestore, renderMetadata };
}
