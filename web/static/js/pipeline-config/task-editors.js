/** Task-specific controls and browser panels for the pipeline editor. */

export function createPipelineTaskEditors(context) {
    const {
        state,
        escapeHtml,
        pathAttr,
        taskKind,
        stepsOf,
        getParam,
        selectedTaskFindings,
        versionLabel,
    } = context;

    function controlValue(value) {
        return escapeHtml(value === null || value === undefined ? "" : value);
    }

    function numberValue(value) {
        if (typeof value === "number" && Number.isFinite(value)) {
            return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)));
        }
        if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) {
            const numeric = Number(value);
            return Number.isInteger(numeric) ? String(numeric) : String(Number(numeric.toFixed(6)));
        }
        return value === null || value === undefined ? "" : String(value);
    }

    function textControl(label, path, value, options) {
        const opts = options || {};
        const inputClass = opts.mono ? "input input-bordered input-sm font-mono" : "input input-bordered input-sm";
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <input class="${inputClass}" data-param-path="${pathAttr(path)}" ${opts.paramType ? `data-param-type="${escapeHtml(opts.paramType)}"` : ""} ${opts.ariaLabel ? `aria-label="${escapeHtml(opts.ariaLabel)}"` : ""} value="${controlValue(value)}" ${opts.readonly ? "readonly" : ""}>
                ${opts.hint ? `<span class="text-xs text-base-content/50 mt-1">${escapeHtml(opts.hint)}</span>` : ""}
                ${opts.findings || ""}
            </label>
        `;
    }

    function secretControl(label, path, value) {
        const alias = (
            value
            && typeof value === "object"
            && Object.keys(value).length === 1
            && typeof value.$secret === "string"
        ) ? value.$secret : (typeof value === "string" ? value : "");
        return `
            <label class="form-control min-w-0">
                <span class="label-text">${escapeHtml(label)} secret alias</span>
                <input class="input input-bordered input-sm w-full min-w-0 font-mono" autocomplete="off" data-param-type="secret-reference" data-param-path="${pathAttr(path)}" value="${controlValue(alias)}" placeholder="llamacloud-primary">
                <span class="text-xs text-base-content/50 mt-1">References a value from deployment configuration. The secret itself is never displayed or versioned.</span>
            </label>
        `;
    }

    function numberControl(label, path, value, attrs, findings) {
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <input class="input input-bordered input-sm" type="number" data-param-type="number" data-param-path="${pathAttr(path)}" value="${escapeHtml(numberValue(value))}" ${attrs || ""}>
                ${findings || ""}
            </label>
        `;
    }

    function checkboxControl(label, path, value, hint) {
        return `
            <label class="label cursor-pointer justify-start gap-3 rounded-lg border border-base-300 bg-base-100 px-3">
                <input class="toggle toggle-sm" type="checkbox" data-param-type="checkbox" data-param-path="${pathAttr(path)}" ${value ? "checked" : ""}>
                <span>
                    <span class="label-text block">${escapeHtml(label)}</span>
                    ${hint ? `<span class="text-xs text-base-content/50">${escapeHtml(hint)}</span>` : ""}
                </span>
            </label>
        `;
    }

    function selectControl(label, path, value, options, hint, findings, paramType) {
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <select class="select select-bordered select-sm" data-param-path="${pathAttr(path)}" ${paramType ? `data-param-type="${escapeHtml(paramType)}"` : ""}>
                    ${options.map((option) => `
                        <option value="${escapeHtml(option.value)}" ${String(value ?? "") === String(option.value) ? "selected" : ""} ${option.disabled ? "disabled" : ""}>${escapeHtml(option.label)}</option>
                    `).join("")}
                </select>
                ${hint ? `<span class="text-xs text-base-content/50 mt-1">${escapeHtml(hint)}</span>` : ""}
                ${findings || ""}
            </label>
        `;
    }

    function nullableBooleanControl(label, path, value) {
        return `
            <label class="form-control">
                <span class="label-text">${escapeHtml(label)}</span>
                <select class="select select-bordered select-sm" data-param-type="nullable-boolean" data-param-path="${pathAttr(path)}">
                    <option value="" ${value === null || value === undefined ? "selected" : ""}>Default</option>
                    <option value="true" ${value === true ? "selected" : ""}>Yes</option>
                    <option value="false" ${value === false ? "selected" : ""}>No</option>
                </select>
            </label>
        `;
    }

    function textareaControl(label, path, value, options) {
        const opts = options || {};
        return `
            <label class="form-control ${opts.full ? "md:col-span-2" : ""}">
                <span class="label-text">${escapeHtml(label)}</span>
                <textarea class="textarea textarea-bordered text-sm ${opts.mono ? "font-mono" : ""}" data-param-path="${pathAttr(path)}" ${opts.paramType ? `data-param-type="${escapeHtml(opts.paramType)}"` : ""} ${opts.ariaLabel ? `aria-label="${escapeHtml(opts.ariaLabel)}"` : ""}>${escapeHtml(value || "")}</textarea>
                ${opts.findings || ""}
            </label>
        `;
    }

    function directoryControl(label, path, value, options) {
        const opts = options || {};
        const current = value || "";
        return `
            <div class="directory-control">
                <label class="form-control min-w-0">
                    <span class="label-text">${escapeHtml(label)}</span>
                    <div class="join w-full">
                        <input class="input input-bordered input-sm join-item min-w-0 flex-1 font-mono" data-param-path="${pathAttr(path)}" value="${controlValue(current)}">
                        <button class="btn btn-outline btn-sm join-item" type="button" data-param-action="open-directory-browser" data-param-path="${pathAttr(path)}" data-current-path="${escapeHtml(current || ".")}">Browse</button>
                    </div>
                    ${opts.hint ? `<span class="text-xs text-base-content/50 mt-1">${escapeHtml(opts.hint)}</span>` : ""}
                    ${opts.findings || ""}
                </label>
            </div>
        `;
    }

    function fileControl(label, path, value, extensions, options) {
        const opts = options || {};
        const current = value || "";
        return `
            <div class="directory-control">
                <label class="form-control min-w-0">
                    <span class="label-text">${escapeHtml(label)}</span>
                    <div class="join w-full">
                        <input class="input input-bordered input-sm join-item min-w-0 flex-1 font-mono" data-param-path="${pathAttr(path)}" value="${controlValue(current)}">
                        <button class="btn btn-outline btn-sm join-item" type="button" data-param-action="open-file-browser" data-param-path="${pathAttr(path)}" data-current-path="${escapeHtml(current)}" data-start-path="${escapeHtml(opts.startPath || ".")}" data-extensions="${escapeHtml(extensions || "")}">Browse</button>
                    </div>
                    ${opts.hint ? `<span class="text-xs text-base-content/50 mt-1">${escapeHtml(opts.hint)}</span>` : ""}
                    ${opts.findings || ""}
                </label>
            </div>
        `;
    }

    function section(title, body) {
        return `
            <div class="rounded-lg border border-base-300 bg-base-100 p-3">
                <h3 class="text-sm font-semibold mb-3">${escapeHtml(title)}</h3>
                ${body}
            </div>
        `;
    }

    function detailsSection(title, body, open) {
        return `
            <details class="rounded-lg border border-base-300 bg-base-100" ${open ? "open" : ""}>
                <summary class="cursor-pointer px-3 py-3 text-sm font-semibold">${escapeHtml(title)}</summary>
                <div class="space-y-3 border-t border-base-300 p-3">
                    ${body}
                </div>
            </details>
        `;
    }

    function directoryBrowserPanel() {
        const browser = state.directoryBrowser;
        if (!browser || !browser.open) {
            return "";
        }
        const listing = browser.listing || {};
        const directories = Array.isArray(listing.directories) ? listing.directories : [];
        const files = Array.isArray(listing.files) ? listing.files : [];
        const fileMode = browser.mode === "file";
        return `
            <div class="directory-browser-backdrop" role="presentation">
                <aside class="directory-browser-drawer" role="dialog" aria-modal="true" aria-labelledby="directory-browser-title">
                    <header class="directory-browser-header">
                        <div class="min-w-0">
                            <h3 id="directory-browser-title" class="text-base font-semibold">${fileMode ? "Select file" : "Select output directory"}</h3>
                            <p class="mt-1 truncate font-mono text-xs text-base-content/55">${escapeHtml(listing.current || browser.current || ".")}</p>
                        </div>
                        <button class="btn btn-ghost btn-circle btn-sm" type="button" aria-label="Close directory browser" data-param-action="close-directory-browser">Close</button>
                    </header>
                    <div class="directory-browser-body">
                        ${browser.error ? `<div class="alert alert-error py-2 text-xs">${escapeHtml(browser.error)}</div>` : ""}
                        <div class="directory-browser-toolbar">
                            ${fileMode ? "" : `<button class="btn btn-outline btn-sm" type="button" data-param-action="select-current-directory" ${browser.loading ? "disabled" : ""}>Use current</button>`}
                            <button class="btn btn-ghost btn-sm" type="button" data-param-action="browse-directory-up" ${!listing.parent || browser.loading ? "disabled" : ""}>Up</button>
                        </div>
                        <div class="directory-browser-list">
                            ${browser.loading ? '<div class="empty-panel">Loading directories</div>' : ""}
                            ${!browser.loading && directories.map((entry) => `
                                <button class="directory-row" type="button" data-param-action="browse-directory" data-directory-path="${escapeHtml(entry.path)}">
                                    <span class="directory-row-icon">/</span>
                                    <span class="min-w-0 truncate">${escapeHtml(entry.name)}</span>
                                </button>
                            `).join("")}
                            ${!browser.loading && files.map((entry) => `
                                <button class="directory-row" type="button" data-param-action="select-file" data-file-path="${escapeHtml(entry.path)}">
                                    <span class="directory-row-icon">F</span>
                                    <span class="min-w-0 truncate">${escapeHtml(entry.name)}</span>
                                </button>
                            `).join("")}
                            ${!browser.loading && !directories.length && !files.length ? `<div class="empty-panel">${fileMode ? "No matching files" : "No child directories"}</div>` : ""}
                        </div>
                        ${fileMode ? "" : `<div class="directory-create-row">
                            <input class="input input-bordered input-sm min-w-0 flex-1" id="pipeline-new-directory-name" value="${controlValue(browser.newDirectory || "")}" placeholder="New folder name">
                            <button class="btn btn-outline btn-sm" type="button" data-param-action="create-directory">Create</button>
                        </div>`}
                    </div>
                    <footer class="directory-browser-footer">
                        <button class="btn btn-ghost btn-sm" type="button" data-param-action="close-directory-browser">Cancel</button>
                        ${fileMode ? "" : '<button class="btn btn-primary btn-sm" type="button" data-param-action="select-current-directory">Select</button>'}
                    </footer>
                </aside>
            </div>
        `;
    }

    function unwrapOptionalType(type) {
        const text = String(type || "str").trim();
        const match = text.match(/^Optional\[(.*)\]$/);
        return match ? match[1].trim() : text;
    }

    function isRequiredType(type) {
        const text = String(type || "str").trim();
        return !(text.startsWith("Optional[") && text.endsWith("]"));
    }

    function withRequiredState(type, required) {
        const base = unwrapOptionalType(type || "str");
        return required ? base : `Optional[${base}]`;
    }

    function extractionFieldControls(step, hint) {
        const polishedLayout = step.class === "GlmOcrExtractTask";
        const params = step.params || {};
        const fields = params.fields && typeof params.fields === "object" && !Array.isArray(params.fields) ? params.fields : {};
        const naturalFieldEntries = Object.entries(fields);
        const fieldEntries = polishedLayout
            ? naturalFieldEntries.map((entry, index) => ({ entry, index })).sort((first, second) => {
                const firstOrder = Number.isInteger(first.entry[1] && first.entry[1].schema_order) ? first.entry[1].schema_order : Number.MAX_SAFE_INTEGER;
                const secondOrder = Number.isInteger(second.entry[1] && second.entry[1].schema_order) ? second.entry[1].schema_order : Number.MAX_SAFE_INTEGER;
                return firstOrder - secondOrder || first.index - second.index;
            }).map(({ entry }) => entry)
            : naturalFieldEntries;
        const tableKeys = fieldEntries.filter(([, field]) => field && (field.is_table || unwrapOptionalType(field.type) === "List[Any]")).map(([key]) => key);
        const typeOptions = [
            { value: "str", label: "Text" },
            { value: "int", label: "Integer" },
            { value: "float", label: "Number" },
            { value: "bool", label: "Yes / No" },
            { value: "List[str]", label: "List of text" },
            { value: "List[int]", label: "List of integers" },
            { value: "List[float]", label: "List of numbers" },
            { value: "List[bool]", label: "List of yes / no" },
            { value: "Dict[str, Any]", label: "Object with defined fields" },
            { value: "List[Any]", label: "List of objects" },
        ];
        const controls = fieldEntries.map(([fieldKey, field], fieldIndex) => {
            const fieldValue = field && typeof field === "object" ? field : {};
            const fieldType = fieldValue.type || "str";
            const baseType = unwrapOptionalType(fieldType);
            const required = isRequiredType(fieldType);
            const isTable = baseType === "List[Any]" || Boolean(fieldValue.is_table);
            const isObject = baseType === "Dict[str, Any]";
            const tableBlocked = !isTable && tableKeys.length >= 1;
            const itemFields = fieldValue.item_fields && typeof fieldValue.item_fields === "object" ? fieldValue.item_fields : {};
            const objectFields = fieldValue.object_fields && typeof fieldValue.object_fields === "object" ? fieldValue.object_fields : {};
            const schemaFields = isTable ? itemFields : objectFields;
            const schemaControls = isTable || isObject ? `
                <div class="row-schema-summary md:col-span-2">
                    <div>
                        <div class="text-xs font-semibold">${isTable ? "Row schema" : "Object properties"}</div>
                        <div class="mt-0.5 text-xs text-base-content/55">${Object.keys(schemaFields).length} flat ${isTable ? "row fields" : "properties"} defined</div>
                    </div>
                    <button class="btn btn-outline btn-xs" type="button" data-param-action="edit-field-schema" data-field-key="${escapeHtml(fieldKey)}" data-schema-kind="${isTable ? "row" : "object"}">Edit ${isTable ? "row schema" : "object properties"}</button>
                </div>
            ` : "";
            const constraintControls = polishedLayout && baseType === "str" ? `
                <label class="form-control">
                    <span class="label-text">Allowed values</span>
                    <input class="input input-bordered input-sm" aria-label="Allowed values for ${escapeHtml(fieldKey)}" placeholder="Optional, comma-separated" data-param-action="field-choices" data-field-key="${escapeHtml(fieldKey)}" value="${controlValue(Array.isArray(fieldValue.choices) ? fieldValue.choices.join(", ") : "")}">
                    <span class="mt-1 text-xs text-base-content/50">Constrains Ollama to one configured text value.</span>
                </label>
                <label class="form-control">
                    <span class="label-text">Value normalization</span>
                    <select class="select select-bordered select-sm" aria-label="Value normalization for ${escapeHtml(fieldKey)}" data-param-action="field-normalizer" data-field-key="${escapeHtml(fieldKey)}">
                        <option value="" ${fieldValue.normalizer ? "" : "selected"}>None</option>
                        <option value="iso_date" ${fieldValue.normalizer === "iso_date" ? "selected" : ""}>Date to YYYY-MM-DD</option>
                    </select>
                    <span class="mt-1 text-xs text-base-content/50">Date cleanup runs locally after source transcription.</span>
                </label>
            ` : "";
            const renderedTypeOptions = typeOptions.some((option) => option.value === baseType)
                ? typeOptions
                : [{ value: baseType, label: `Legacy type (${baseType})`, disabled: true }, ...typeOptions];
            return `
                <div class="field-editor ${polishedLayout ? "extraction-field-editor-polished" : ""}">
                    <details class="extraction-field-details">
                        <summary class="extraction-field-summary">
                            <span class="font-medium">${escapeHtml(fieldValue.alias || fieldKey)}</span>
                            <span class="font-mono text-base-content/50">${escapeHtml(fieldKey)}</span>
                            <span class="badge badge-ghost badge-xs">${escapeHtml(baseType)}</span>
                            ${required ? '<span class="badge badge-primary badge-xs">Required</span>' : ""}
                        </summary>
                        <div class="extraction-field-editor-content">
                    <div class="property-field-grid ${polishedLayout ? "property-field-grid-polished" : ""}">
                        <label class="form-control">
                            <span class="label-text">Field key</span>
                            <input class="input input-bordered input-sm font-mono" aria-label="Field key for ${escapeHtml(fieldKey)}" data-param-action="rename-extract-field" data-field-key="${escapeHtml(fieldKey)}" value="${escapeHtml(fieldKey)}">
                        </label>
                        ${textControl("Alias", ["fields", fieldKey, "alias"], fieldValue.alias || "", { ariaLabel: `Alias for ${fieldKey}` })}
                        <label class="form-control">
                            <span class="label-text">Type</span>
                            <select class="select select-bordered select-sm" aria-label="Type for ${escapeHtml(fieldKey)}" data-param-action="field-type" data-field-key="${escapeHtml(fieldKey)}" data-required="${required ? "true" : "false"}">
                                ${renderedTypeOptions.map((option) => `<option value="${escapeHtml(option.value)}" ${baseType === option.value ? "selected" : ""} ${(option.value === "List[Any]" && tableBlocked) || option.disabled ? "disabled" : ""}>${escapeHtml(option.label)}</option>`).join("")}
                            </select>
                            ${tableBlocked && !polishedLayout ? '<span class="mt-1 text-xs text-warning">Only one List of objects field is supported.</span>' : ""}
                            <span class="mt-1 text-xs text-base-content/50">Python type: ${escapeHtml(withRequiredState(baseType, required))}${isTable ? " · flat row objects" : ""}</span>
                        </label>
                        <button class="btn ${polishedLayout ? "btn-outline extraction-field-remove" : "btn-ghost btn-square self-end"} btn-sm text-error" type="button" title="Remove field" aria-label="Remove field ${escapeHtml(fieldKey)}" data-param-action="remove-extract-field" data-field-key="${escapeHtml(fieldKey)}">Remove</button>
                    </div>
                    ${inlineFindings(step, `fields.${fieldKey}`, true)}
                    <div class="mt-3 grid gap-3 ${polishedLayout ? "extraction-field-details-polished" : "md:grid-cols-2"}">
                        <label class="label cursor-pointer justify-start gap-3 rounded-lg border border-base-300 px-3 ${polishedLayout ? "extraction-required-control" : ""}">
                            <input class="checkbox checkbox-sm" type="checkbox" aria-label="Required field ${escapeHtml(fieldKey)}" data-param-action="field-required" data-field-key="${escapeHtml(fieldKey)}" ${required ? "checked" : ""}>
                            <span>
                                <span class="label-text block">Required field</span>
                                <span class="text-xs text-base-content/50">${required ? "Must be returned" : "May be omitted"}</span>
                            </span>
                        </label>
                        ${textareaControl("Extraction guidance", ["fields", fieldKey, "description"], fieldValue.description || "", { full: !polishedLayout, ariaLabel: `Extraction guidance for ${fieldKey}` })}
                        ${polishedLayout ? numberControl("Schema position", ["fields", fieldKey, "schema_order"], fieldValue.schema_order ?? fieldIndex + 1, 'min="1" step="1"', inlineFindings(step, `fields.${fieldKey}.schema_order`)) : ""}
                        ${constraintControls}
                        ${schemaControls}
                    </div>
                        </div>
                    </details>
                </div>
            `;
        }).join("");
        return `${tableKeys.length > 1 ? '<div class="alert alert-error py-2 text-xs">Only one table field is supported. Change extra fields to a scalar type.</div>' : ""}${section("Extraction fields", `
            <div class="flex justify-between items-center gap-3 mb-3">
                <p class="text-xs text-base-content/60">${escapeHtml(hint || "Define scalar fields and one optional table-style field for extraction. Review schemas are configured separately and may contain multiple arrays of objects.")}</p>
                <button class="btn btn-outline btn-xs" type="button" data-param-action="add-extract-field">Add field</button>
            </div>
            ${polishedLayout ? "" : '<div class="alert alert-info py-2 text-xs">Each extraction task supports one List of objects field. The additional table option stays unavailable once one is configured.</div>'}
            <div class="space-y-3">${controls || '<div class="empty-panel">No extraction fields configured</div>'}</div>
        `)}`;
    }

    function structuredFieldSchemaDrawer(step) {
        const fieldKey = state.editingFieldSchema;
        const schemaKind = state.fieldSchemaKind;
        if (!fieldKey || !schemaKind || !step) {
            return "";
        }
        const fieldConfig = getParam(step.params || {}, ["fields", fieldKey], null);
        if (!fieldConfig || typeof fieldConfig !== "object") {
            state.editingFieldSchema = null;
            state.fieldSchemaKind = null;
            state.fieldSchemaDraft = null;
            return "";
        }
        const configKey = schemaKind === "object" ? "object_fields" : "item_fields";
        const glmConstraints = step.class === "GlmOcrExtractTask";
        const configuredFields = state.fieldSchemaDraft && typeof state.fieldSchemaDraft === "object"
            ? state.fieldSchemaDraft
            : (fieldConfig[configKey] && typeof fieldConfig[configKey] === "object" ? fieldConfig[configKey] : {});
        const fieldOptions = [
            { value: "str", label: "Text" },
            { value: "int", label: "Integer" },
            { value: "float", label: "Number" },
            { value: "bool", label: "Yes / No" },
        ];
        const naturalConfiguredEntries = Object.entries(configuredFields);
        const configuredEntries = glmConstraints
            ? naturalConfiguredEntries.map((entry, index) => ({ entry, index })).sort((first, second) => {
                const firstOrder = Number.isInteger(first.entry[1] && first.entry[1].schema_order) ? first.entry[1].schema_order : Number.MAX_SAFE_INTEGER;
                const secondOrder = Number.isInteger(second.entry[1] && second.entry[1].schema_order) ? second.entry[1].schema_order : Number.MAX_SAFE_INTEGER;
                return firstOrder - secondOrder || first.index - second.index;
            }).map(({ entry }) => entry)
            : naturalConfiguredEntries;
        const rows = configuredEntries.map(([itemKey, itemField], itemIndex) => {
            const itemConfig = itemField && typeof itemField === "object" ? itemField : {};
            const baseType = fieldOptions.some((option) => option.value === unwrapOptionalType(itemConfig.type)) ? unwrapOptionalType(itemConfig.type) : "str";
            const required = isRequiredType(itemConfig.type || "str");
            return `
                <div class="row-schema-field">
                    <input class="input input-bordered input-sm min-w-0 font-mono" aria-label="Field key for ${escapeHtml(itemKey)}" data-param-action="rename-schema-draft-field" data-item-key="${escapeHtml(itemKey)}" value="${escapeHtml(itemKey)}">
                    <select class="select select-bordered select-sm min-w-0" aria-label="Type for ${escapeHtml(itemKey)}" data-param-action="schema-draft-field-type" data-item-key="${escapeHtml(itemKey)}" data-required="${required ? "true" : "false"}">
                        ${fieldOptions.map((option) => `<option value="${escapeHtml(option.value)}" ${baseType === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
                    </select>
                    <label class="row-required-toggle">
                        <input class="checkbox checkbox-primary checkbox-sm" type="checkbox" aria-label="Required field ${escapeHtml(itemKey)}" data-param-action="schema-draft-field-required" data-item-key="${escapeHtml(itemKey)}" ${required ? "checked" : ""}>
                    </label>
                    <button class="btn btn-ghost btn-square btn-sm text-error" type="button" aria-label="Remove field ${escapeHtml(itemKey)}" data-param-action="remove-schema-draft-field" data-item-key="${escapeHtml(itemKey)}">Remove</button>
                    <input class="input input-bordered input-sm col-span-full min-w-0" aria-label="Alias for ${escapeHtml(itemKey)}" placeholder="Field alias" data-param-action="schema-draft-alias" data-item-key="${escapeHtml(itemKey)}" value="${controlValue(itemConfig.alias || "")}">
                    <input class="input input-bordered input-sm col-span-full min-w-0" aria-label="Extraction guidance for ${escapeHtml(itemKey)}" placeholder="Extraction guidance (optional)" data-param-action="schema-draft-guidance" data-item-key="${escapeHtml(itemKey)}" value="${controlValue(itemConfig.description || "")}">
                    ${glmConstraints ? `<input class="input input-bordered input-sm col-span-full min-w-0" type="number" min="1" step="1" aria-label="Schema position for ${escapeHtml(itemKey)}" data-param-action="schema-draft-order" data-item-key="${escapeHtml(itemKey)}" value="${escapeHtml(numberValue(itemConfig.schema_order ?? itemIndex + 1))}">` : ""}
                    ${glmConstraints && baseType === "str" ? `
                        <input class="input input-bordered input-sm col-span-full min-w-0" aria-label="Allowed values for ${escapeHtml(itemKey)}" placeholder="Allowed values (optional, comma-separated)" data-param-action="schema-draft-choices" data-item-key="${escapeHtml(itemKey)}" value="${controlValue(Array.isArray(itemConfig.choices) ? itemConfig.choices.join(", ") : "")}">
                        <select class="select select-bordered select-sm col-span-full min-w-0" aria-label="Value normalization for ${escapeHtml(itemKey)}" data-param-action="schema-draft-normalizer" data-item-key="${escapeHtml(itemKey)}">
                            <option value="" ${itemConfig.normalizer ? "" : "selected"}>No value normalization</option>
                            <option value="iso_date" ${itemConfig.normalizer === "iso_date" ? "selected" : ""}>Normalize date to YYYY-MM-DD</option>
                        </select>
                    ` : ""}
                </div>
            `;
        }).join("");
        const preview = Object.fromEntries(configuredEntries.map(([itemKey, itemField]) => [itemKey, sampleValueForType(itemField && itemField.type)]));
        const invalidKeys = Object.keys(configuredFields).some((key) => !String(key).trim()) || new Set(Object.keys(configuredFields)).size !== Object.keys(configuredFields).length;
        const isObject = schemaKind === "object";
        return `
            <div class="row-schema-backdrop" role="presentation">
                <aside class="row-schema-drawer" role="dialog" aria-modal="true" aria-labelledby="field-schema-title">
                    <header class="row-schema-header">
                        <div>
                            <h3 id="field-schema-title" class="text-base font-semibold">${isObject ? "Object properties" : "Row schema"} - <span class="font-mono">${escapeHtml(fieldKey)}</span></h3>
                            <p class="mt-1 text-xs text-base-content/55">Define the flat ${isObject ? "properties in this object" : "columns for each object in the list"}.</p>
                        </div>
                        <button class="btn btn-ghost btn-circle btn-sm" type="button" aria-label="Close field schema" data-param-action="close-field-schema">Close</button>
                    </header>
                    <div class="row-schema-body">
                        <div class="row-schema-notice"><span>${isObject ? "This is a flat object" : "Each row is a flat object"}. Nested objects or lists are not supported.</span></div>
                        <div class="row-schema-table">
                            <div class="row-schema-columns" aria-hidden="true"><span>Field key</span><span>Type</span><span>Required</span><span>Actions</span></div>
                            ${rows || '<div class="empty-panel m-3">No fields yet. Add the first field to define the object.</div>'}
                        </div>
                        ${invalidKeys ? '<div class="mt-2 text-xs text-error">Field keys must be unique and cannot be empty.</div>' : ""}
                        <button class="btn btn-outline btn-sm mt-3" type="button" data-param-action="add-schema-draft-field">Add field</button>
                        <div class="mt-8">
                            <div class="text-sm font-semibold">Object preview</div>
                            <div class="mt-1 text-xs text-base-content/55">Sample values using the configured types</div>
                            <pre class="row-schema-preview">${escapeHtml(JSON.stringify(preview, null, 2))}</pre>
                        </div>
                    </div>
                    <footer class="row-schema-footer">
                        <button class="btn btn-ghost btn-sm" type="button" data-param-action="cancel-field-schema">Cancel</button>
                        <button class="btn btn-primary btn-sm" type="button" data-param-action="save-field-schema" ${invalidKeys || !Object.keys(configuredFields).length ? "disabled" : ""}>Done</button>
                    </footer>
                </aside>
            </div>
        `;
    }

    function sampleValueForType(type) {
        const baseType = unwrapOptionalType(type);
        if (baseType === "int") {
            return 1;
        }
        if (baseType === "float") {
            return 1.25;
        }
        if (baseType === "bool") {
            return true;
        }
        return "text";
    }

    function inlineFindings(step, path, prefix) {
        const expected = `tasks.${step.key}.params.${path}`;
        const matches = selectedTaskFindings(step).filter((finding) => {
            const findingPath = String(finding.path || "");
            return prefix ? findingPath.startsWith(expected) : findingPath === expected;
        });
        return matches.map((finding) => `
            <div class="mt-1 text-xs ${finding.severity === "error" ? "text-error" : "text-warning"}">
                ${escapeHtml(finding.message || "Invalid value")}
            </div>
        `).join("");
    }

    function splitControls(step) {
        const params = step.params || {};
        const categories = Array.isArray(params.categories) ? params.categories : [];
        const failLevels = Array.isArray(params.fail_on_confidence_levels) ? params.fail_on_confidence_levels : [];
        const policy = params.allow_uncategorized || "include";
        const mode = state.providerModes[step.key] || (params.configuration_id ? "saved" : "inline");
        const policyHints = {
            include: "Keep pages that the splitter cannot classify.",
            forbid: "Treat any unclassified page as a split failure.",
            omit: "Leave unclassified pages out of generated PDFs.",
        };
        return `
            <div class="space-y-3">
                ${checkboxControl("Enable document splitting", ["enabled"], params.enabled !== false, "This runtime switch is separate from including the task in the pipeline.")}
                ${secretControl("API key", ["api_key"], params.api_key || "")}
                <label class="form-control">
                    <span class="label-text">Split configuration</span>
                    <select class="select select-bordered select-sm" data-param-action="provider-mode" data-provider-kind="split">
                        <option value="inline" ${mode === "inline" ? "selected" : ""}>Define categories here</option>
                        <option value="saved" ${mode === "saved" ? "selected" : ""}>Use saved LlamaCloud configuration</option>
                    </select>
                </label>
                ${mode === "saved" ? textControl("LlamaCloud configuration ID", ["configuration_id"], params.configuration_id || "", { mono: true, findings: inlineFindings(step, "configuration_id") }) : ""}
                ${mode === "inline" ? selectControl("When pages cannot be categorized", ["allow_uncategorized"], policy, [
                    { value: "include", label: "Keep uncategorized pages" },
                    { value: "forbid", label: "Stop the split" },
                    { value: "omit", label: "Skip uncategorized pages" },
                ], policyHints[policy]) : ""}
                ${directoryControl("Split output directory", ["split_dir"], params.split_dir || "", { hint: "Child PDFs created by this task are written here.", findings: inlineFindings(step, "split_dir") })}
                ${section("Stop on confidence levels", `
                    <p class="mb-3 text-xs text-base-content/55">The split fails when any result reports a selected confidence level.</p>
                    <div class="grid gap-2 sm:grid-cols-3">
                        ${["high", "medium", "low"].map((level) => `
                            <label class="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-2 text-sm ${failLevels.includes(level) ? "border-primary bg-primary/5" : "border-base-300"}">
                                <input class="checkbox checkbox-sm" type="checkbox" data-param-action="split-confidence-level" value="${level}" ${failLevels.includes(level) ? "checked" : ""}>
                                <span class="capitalize">${level}</span>
                            </label>
                        `).join("")}
                    </div>
                `)}
                ${checkboxControl("Stop on unknown categories", ["fail_on_unknown_category"], params.fail_on_unknown_category !== false, params.fail_on_unknown_category !== false ? "Only configured category names are accepted." : "Unknown category names are allowed.")}
                ${mode === "inline" ? section("Document categories", `
                    <div class="mb-3 flex items-start justify-between gap-3">
                        <p class="text-xs text-base-content/55">Define every document type the splitter should recognize.</p>
                        <button class="btn btn-outline btn-xs" type="button" data-param-action="add-split-category">Add category</button>
                    </div>
                    <div class="space-y-3">
                        ${categories.map((category, index) => `
                            <div class="rounded-md border border-base-300 p-3">
                                <div class="mb-2 flex items-center justify-between">
                                    <span class="text-xs font-semibold uppercase text-base-content/60">Category ${index + 1}</span>
                                    <button class="btn btn-ghost btn-xs text-error" type="button" data-param-action="remove-split-category" data-category-index="${index}">Remove</button>
                                </div>
                                <div class="space-y-3">
                                    ${textControl("Category name", ["categories", index, "name"], category && category.name || "")}
                                    ${textareaControl("What belongs in this category?", ["categories", index, "description"], category && category.description || "")}
                                </div>
                            </div>
                        `).join("") || '<div class="empty-panel">No inline categories. Provide a configuration ID or add a category.</div>'}
                    </div>
                `) : ""}
                ${textControl("Allowed category names (optional)", ["allowed_categories"], Array.isArray(params.allowed_categories) ? params.allowed_categories.join(", ") : "", { hint: mode === "saved" ? "Comma-separated local allow-list. Leave blank to accept provider category names except blank, other, or uncategorized." : "Comma-separated allow-list. Leave blank to use the category names above.", paramType: "csv-list" })}
                ${detailsSection("Advanced provider settings", `
                    <div class="grid gap-3 md:grid-cols-2">
                        ${textControl("Project ID (optional)", ["project_id"], params.project_id || "", { mono: true })}
                        ${textControl("Organization ID (optional)", ["organization_id"], params.organization_id || "", { mono: true })}
                        ${numberControl("Polling interval (seconds)", ["poll_interval_seconds"], params.poll_interval_seconds ?? 1, 'min="0.1" step="0.1"')}
                        ${numberControl("Timeout (seconds)", ["timeout_seconds"], params.timeout_seconds ?? 7200, 'min="1" step="1"')}
                    </div>
                `)}
            </div>
        `;
    }

    function extractControls(step) {
        const params = step.params || {};
        const mode = state.providerModes[step.key] || (params.configuration_id ? "saved" : "inline");
        const supportedTiers = ["agentic", "cost_effective"];
        const tier = params.tier || "agentic";
        const tierOptions = supportedTiers.includes(tier)
            ? [{ value: "agentic", label: "Agentic" }, { value: "cost_effective", label: "Cost effective" }]
            : [{ value: tier, label: `Unsupported legacy value: ${tier}` }, { value: "agentic", label: "Agentic" }, { value: "cost_effective", label: "Cost effective" }];
        return `
            <div class="space-y-3">
                ${secretControl("API key", ["api_key"], params.api_key || "")}
                <label class="form-control">
                    <span class="label-text">Extraction configuration</span>
                    <select class="select select-bordered select-sm" data-param-action="provider-mode" data-provider-kind="extract">
                        <option value="inline" ${mode === "inline" ? "selected" : ""}>Define extraction here</option>
                        <option value="saved" ${mode === "saved" ? "selected" : ""}>Use saved LlamaCloud configuration</option>
                    </select>
                </label>
                ${mode === "saved" ? textControl("LlamaCloud configuration ID", ["configuration_id"], params.configuration_id || "", { mono: true, findings: inlineFindings(step, "configuration_id") }) : ""}
                ${mode === "inline" ? `
                    <div class="grid gap-3 md:grid-cols-2">
                        ${selectControl("Tier", ["tier"], tier, tierOptions)}
                        ${selectControl("Target", ["extraction_target"], params.extraction_target || "per_doc", [
                            { value: "per_doc", label: "Per document" },
                            { value: "per_page", label: "Per page" },
                            { value: "per_table_row", label: "Per table row" },
                        ])}
                    </div>
                    ${checkboxControl("Request confidence scores", ["confidence_scores"], params.confidence_scores !== false)}
                    ${detailsSection("Advanced inline extraction settings", `
                        ${textControl("Parse tier (optional)", ["parse_tier"], params.parse_tier || "")}
                        ${selectControl("Source citations", ["cite_sources"], params.cite_sources === true ? "true" : params.cite_sources === false ? "false" : "", [
                            { value: "", label: "Use provider default" },
                            { value: "true", label: "Request citations" },
                            { value: "false", label: "Do not request citations" },
                        ], "Use provider default unless this pipeline needs an explicit setting.", "", "nullable-boolean")}
                    `)}
                ` : ""}
                ${detailsSection("Advanced provider settings", `
                    <div class="grid gap-3 md:grid-cols-2">
                        ${textControl("Project ID (optional)", ["project_id"], params.project_id || "", { mono: true })}
                        ${textControl("Organization ID (optional)", ["organization_id"], params.organization_id || "", { mono: true })}
                        ${numberControl("Polling interval (seconds)", ["poll_interval_seconds"], params.poll_interval_seconds ?? 2, 'min="0.1" step="0.1"')}
                        ${numberControl("Timeout (seconds)", ["timeout_seconds"], params.timeout_seconds ?? 1800, 'min="1" step="1"')}
                    </div>
                `)}
                ${extractionFieldControls(step, mode === "saved" ? "Define the local field mapping used to normalize saved-configuration results for review and storage." : "Define the inline provider schema and local field mapping.")}
                ${structuredFieldSchemaDrawer(step)}
            </div>
        `;
    }

    function glmOcrExtractControls(step) {
        const params = step.params || {};
        const fields = params.fields && typeof params.fields === "object" && !Array.isArray(params.fields) ? params.fields : {};
        const fieldEntries = Object.entries(fields);
        const tableCount = fieldEntries.filter(([, field]) => {
            const fieldValue = field && typeof field === "object" ? field : {};
            return Boolean(fieldValue.is_table) || unwrapOptionalType(fieldValue.type) === "List[Any]";
        }).length;
        const host = params.ollama_host || "http://127.0.0.1:11434";
        const model = params.model || "glm-ocr:latest";
        const resolutionMode = params.resolution_mode || "page_merge";
        const resolverModel = params.resolver_model || "qwen3.5:9b-q4_K_M";
        const tableStatus = tableCount === 0 ? "No table" : tableCount === 1 ? "One table" : `${tableCount} tables (fix required)`;
        return `
            <div class="space-y-3" data-glm-ocr-controls>
                <div class="rounded-lg border border-primary/20 bg-primary/5 p-3">
                    <div class="text-xs font-semibold uppercase text-primary">Local GLM-OCR extraction</div>
                    <div class="mt-2 grid gap-2 text-xs sm:grid-cols-2">
                        <div><span class="text-base-content/55">Model</span><div class="font-mono break-all">${escapeHtml(model)}</div></div>
                        <div><span class="text-base-content/55">Ollama host</span><div class="font-mono break-all">${escapeHtml(host)}</div></div>
                        <div><span class="text-base-content/55">Fields</span><div>${fieldEntries.length}</div></div>
                        <div><span class="text-base-content/55">Table status</span><div>${escapeHtml(tableStatus)}</div></div>
                        <div><span class="text-base-content/55">Resolution</span><div>${resolutionMode === "document" ? "Complete document" : "Page merge"}</div></div>
                        ${resolutionMode === "document" ? `<div><span class="text-base-content/55">Resolver</span><div class="font-mono break-all">${escapeHtml(resolverModel)}</div></div>` : ""}
                    </div>
                </div>
                <div class="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm">
                    GLM-OCR does not provide confidence scores. If a Review Gate follows this task, every extracted field is sent for operator review.
                </div>
                ${section("Local model", `
                    <div class="grid gap-3 md:grid-cols-2">
                        ${textControl("Ollama host", ["ollama_host"], host, { mono: true, hint: "Local Ollama HTTP endpoint. Embedded credentials are not allowed.", findings: inlineFindings(step, "ollama_host") })}
                        ${textControl("Model", ["model"], model, { mono: true, findings: inlineFindings(step, "model") })}
                    </div>
                    <div class="mt-3">
                        ${textareaControl("Document instructions", ["document_instructions"], params.document_instructions || "", { full: true, findings: inlineFindings(step, "document_instructions") })}
                    </div>
                    <div class="mt-3">
                        ${selectControl("Prompt construction", ["prompt_style"], params.prompt_style || "detailed", [
                            { value: "detailed", label: "Detailed (compatibility default)" },
                            { value: "compact", label: "Compact (schema sent once)" },
                            { value: "verbatim", label: "Verbatim instructions (advanced)" },
                        ], "Compact uses a short framework contract. Verbatim sends Document instructions exactly as written while still enforcing Ollama's native JSON Schema.", inlineFindings(step, "prompt_style"))}
                    </div>
                `)}
                ${section("Document resolution", `
                    ${selectControl("Resolution mode", ["resolution_mode"], resolutionMode, [
                        { value: "document", label: "Complete document (recommended)" },
                        { value: "page_merge", label: "Page merge (legacy)" },
                    ], "Complete document resolves scalar and object fields against bounded page images, then reconciles tables from structured GLM-OCR evidence. Page merge keeps the first supported page value.", inlineFindings(step, "resolution_mode"))}
                    ${resolutionMode === "document" ? `
                        <div class="mt-3">
                            ${textControl("Resolver model", ["resolver_model"], resolverModel, { mono: true, hint: "A local vision-capable instruction model installed in Ollama.", findings: inlineFindings(step, "resolver_model") })}
                        </div>
                        ${detailsSection("Resolver runtime settings", `
                            <div class="grid gap-3 md:grid-cols-2">
                                ${numberControl("Resolver image max dimension", ["resolver_max_dimension"], params.resolver_max_dimension ?? 1280, 'min="256" max="4096" step="1"', inlineFindings(step, "resolver_max_dimension"))}
                                ${numberControl("Resolver context length", ["resolver_num_ctx"], params.resolver_num_ctx ?? 18000, 'min="1" step="1"', inlineFindings(step, "resolver_num_ctx"))}
                                ${numberControl("Resolver prediction length", ["resolver_num_predict"], params.resolver_num_predict ?? 10000, 'min="1" step="1"', inlineFindings(step, "resolver_num_predict"))}
                                ${numberControl("Resolver attempts", ["resolver_max_attempts"], params.resolver_max_attempts ?? 2, 'min="1" max="5" step="1"', inlineFindings(step, "resolver_max_attempts"))}
                            </div>
                        `)}
                    ` : ""}
                `)}
                ${detailsSection("Local runtime settings", `
                    <div class="grid gap-3 md:grid-cols-2">
                        ${numberControl("PDF render DPI", ["dpi"], params.dpi ?? 216, 'min="72" step="1"', inlineFindings(step, "dpi"))}
                        ${numberControl("Context length", ["num_ctx"], params.num_ctx ?? 8192, 'min="1" step="1"', inlineFindings(step, "num_ctx"))}
                        ${numberControl("Prediction length", ["num_predict"], params.num_predict ?? 2048, 'min="1" step="1"', inlineFindings(step, "num_predict"))}
                        ${numberControl("Timeout (seconds)", ["timeout_seconds"], params.timeout_seconds ?? 300, 'min="1" step="1"', inlineFindings(step, "timeout_seconds"))}
                    </div>
                `)}
                ${extractionFieldControls(step, "Define scalar fields, flat objects, and at most one array-of-objects table for local GLM-OCR extraction.")}
                ${structuredFieldSchemaDrawer(step)}
            </div>
        `;
    }

    function extractionFieldNames() {
        const extract = stepsOf(state.draft).find((step) => taskKind(step) === "extract");
        const fields = extract && extract.params && extract.params.fields;
        return fields && typeof fields === "object" && !Array.isArray(fields) ? Object.keys(fields) : [];
    }

    function availableFilenameTokens() {
        return [...new Set(["id", "nanoid", "filename", "source", "original_filename", "file_path", ...extractionFieldNames()])];
    }

    function filenameBuilder(step, path, value) {
        return `
            <div class="rounded-lg border border-base-300 bg-base-100 p-3">
                ${textControl("Filename template", path, value || "", { mono: true })}
                <div class="mt-3 rounded-md bg-base-200 px-3 py-2">
                    <div class="text-xs font-semibold uppercase text-base-content/60">Preview</div>
                    <div class="mt-1 break-all font-mono text-xs">${escapeHtml(value || "No filename template yet")}</div>
                </div>
                <label class="form-control mt-3">
                    <span class="label-text text-xs font-semibold">Insert a token</span>
                    <input class="input input-bordered input-sm" data-token-search placeholder="Find a field or context token">
                </label>
                <div class="mt-2 flex flex-wrap gap-1" data-token-list>
                    ${availableFilenameTokens().map((token) => `<button class="btn btn-outline btn-xs h-auto min-h-7 font-mono" type="button" data-param-action="insert-filename-token" data-token="${escapeHtml(token)}" data-param-path="${pathAttr(path)}">{${escapeHtml(token)}}</button>`).join("")}
                </div>
                ${inlineFindings(step, path.join("."))}
            </div>
        `;
    }

    function objectJsonControl(label, path, value, hint) {
        return `
            <div>
                <label class="form-control">
                    <span class="label-text">${escapeHtml(label)}</span>
                    <textarea class="textarea textarea-bordered min-h-32 font-mono text-xs" data-object-json-editor data-object-json-path="${pathAttr(path)}">${escapeHtml(JSON.stringify(value || {}, null, 2))}</textarea>
                </label>
                ${hint ? `<div class="mt-1 text-xs text-base-content/55">${escapeHtml(hint)}</div>` : ""}
                ${state.objectJsonError ? `<div class="mt-1 text-xs text-error">${escapeHtml(state.objectJsonError)}</div>` : ""}
                <button class="btn btn-outline btn-xs mt-2" type="button" data-param-action="apply-object-json" data-param-path="${pathAttr(path)}">Apply field override</button>
            </div>
        `;
    }

    function storageControls(step) {
        const params = step.params || {};
        const isCsv = step.class === "StoreMetadataAsCsv";
        const isPdf = step.class === "StoreFileToLocaldrive";
        const dirParam = isPdf ? "files_dir" : "data_dir";
        const nested = isCsv && params.storage && typeof params.storage === "object" ? params.storage : null;
        const pathRoot = nested ? ["storage"] : [];
        const directory = nested ? nested.data_dir : params[dirParam];
        const filename = nested ? nested.filename : params.filename;
        const overrideFields = isCsv && params.extraction && params.extraction.fields && typeof params.extraction.fields === "object" ? params.extraction.fields : null;
        return `
            <div class="space-y-3">
                ${isCsv ? `<label class="flex items-start gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-3"><input class="toggle toggle-sm" type="checkbox" data-param-action="toggle-nested-storage" ${nested ? "checked" : ""}><span><span class="block text-sm font-medium">Use nested storage overrides</span><span class="mt-1 block text-xs text-base-content/55">Compatibility format: storage.data_dir and storage.filename.</span></span></label>` : ""}
                ${directoryControl(isPdf ? "PDF output directory" : "Data output directory", [...pathRoot, dirParam], directory || "", { findings: inlineFindings(step, `${pathRoot.length ? "storage." : ""}${dirParam}`) })}
                ${filenameBuilder(step, [...pathRoot, "filename"], filename || "")}
                ${isCsv ? detailsSection("CSV extraction-field override", `
                    <label class="flex items-start gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-3"><input class="toggle toggle-sm" type="checkbox" data-param-action="toggle-storage-extraction" ${overrideFields ? "checked" : ""}><span><span class="block text-sm font-medium">Use task-specific field definitions</span><span class="mt-1 block text-xs text-base-content/55">Normally the CSV task reuses fields from Extract document data.</span></span></label>
                    ${overrideFields ? objectJsonControl("Field definitions", ["extraction", "fields"], overrideFields, "Advanced compatibility setting for this storage task only.") : ""}
                `) : ""}
            </div>
        `;
    }

    function thresholdMapControl(label, hint, path, value, keyOptions) {
        const entries = Object.entries(value && typeof value === "object" ? value : {});
        return section(label, `
            <div class="mb-3 flex items-start justify-between gap-3">
                <p class="text-xs text-base-content/55">${escapeHtml(hint)}</p>
                <button class="btn btn-outline btn-xs" type="button" data-param-action="add-threshold" data-map-path="${pathAttr(path)}" data-key-options="${escapeHtml(JSON.stringify(keyOptions || []))}">Add</button>
            </div>
            <div class="space-y-2">
                ${entries.map(([key, threshold]) => `
                    <div class="threshold-row">
                        ${keyOptions && keyOptions.length ? `<label class="form-control"><span class="label-text">Field</span><select class="select select-bordered select-sm" data-param-action="rename-threshold-key" data-map-path="${pathAttr(path)}" data-old-key="${escapeHtml(key)}">${[...new Set([key, ...keyOptions])].map((option) => `<option value="${escapeHtml(option)}" ${option === key ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select></label>` : `<label class="form-control"><span class="label-text">Document type</span><input class="input input-bordered input-sm font-mono" data-param-action="rename-threshold-key" data-map-path="${pathAttr(path)}" data-old-key="${escapeHtml(key)}" value="${escapeHtml(key)}"></label>`}
                        ${numberControl("Threshold", [...path, key], threshold, 'min="0" max="1" step="0.01"')}
                        <button class="btn btn-ghost btn-sm self-end text-error" type="button" data-param-action="remove-threshold" data-map-path="${pathAttr(path)}" data-key="${escapeHtml(key)}">Remove</button>
                    </div>
                `).join("") || '<div class="empty-panel py-3">No overrides. The default threshold applies.</div>'}
            </div>
        `);
    }

    function reviewControls(step) {
        const params = step.params || {};
        const splitLevels = Array.isArray(params.split_confidence_levels_requiring_review) ? params.split_confidence_levels_requiring_review : [];
        const percent = Math.round(Number(params.confidence_threshold ?? 0.8) * 100);
        const reviewScope = params.review_scope || "low_confidence_fields";
        const reviewScopeOptions = [
            { value: "document", label: "Entire document" },
            { value: "low_confidence_fields", label: "Low-confidence fields" },
        ];
        if (!["document", "low_confidence_fields"].includes(reviewScope)) {
            reviewScopeOptions.unshift({ value: reviewScope, label: `Legacy scope: ${reviewScope}` });
        }
        return `
            <div class="space-y-3">
                <div class="rounded-lg border border-info/20 bg-info/10 p-3 text-sm">Threshold priority is field override, then document type, then the default threshold.</div>
                <fieldset class="rounded-lg border border-base-300 bg-base-100 p-3">
                    <div class="flex items-center justify-between gap-3"><legend class="text-xs">Confidence threshold</legend><label class="flex items-center gap-1 text-sm font-semibold"><input class="input input-bordered input-xs w-20 text-right" type="number" min="0" max="100" step="1" value="${percent}" data-param-action="confidence-percent"><span>%</span></label></div>
                    <input class="range range-primary range-sm mt-3" type="range" min="0" max="100" step="1" value="${percent}" data-param-action="confidence-percent" aria-label="Confidence threshold slider">
                    <p class="mt-2 text-xs text-base-content/55">Send results below ${percent}% confidence for review.</p>
                </fieldset>
                ${thresholdMapControl("Field threshold overrides", "Set a stricter or more permissive score for individual extraction fields.", ["field_threshold_overrides"], params.field_threshold_overrides, extractionFieldNames())}
                ${thresholdMapControl("Document-type thresholds", "Applied when a field has no field-specific override.", ["per_document_type_thresholds"], params.per_document_type_thresholds, [])}
                ${section("Review split confidence levels", `<p class="mb-3 text-xs text-base-content/55">Pause when the upstream split result reports a selected level.</p><div class="grid grid-cols-3 gap-2">${["high", "medium", "low"].map((level) => `<label class="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-2 text-sm ${splitLevels.includes(level) ? "border-primary bg-primary/5" : "border-base-300"}"><input class="checkbox checkbox-sm" type="checkbox" data-param-action="review-split-level" value="${level}" ${splitLevels.includes(level) ? "checked" : ""}><span class="capitalize">${level}</span></label>`).join("")}</div>`)}
                ${selectControl(
                    "Published review form version",
                    ["schema_version_id"],
                    params.schema_version_id || "",
                    [
                        { value: "", label: "Select an exact published version" },
                        ...state.schemaVersions.map((version) => ({
                            value: version.id,
                            label: versionLabel(version, "schema"),
                        })),
                    ],
                    "Publishing a newer review form does not change this exact selection.",
                    inlineFindings(step, "schema_version_id")
                )}
                ${textControl("Queue", ["queue_name"], params.queue_name || "default_review")}
                ${selectControl("Reviewer editing scope", ["review_scope"], reviewScope, reviewScopeOptions, "Review conditions below determine when review is required.")}
                ${checkboxControl("Review when confidence is missing", ["require_review_when_missing_confidence"], params.require_review_when_missing_confidence !== false)}
                ${checkboxControl("Review missing required fields", ["require_review_for_missing_required_fields"], params.require_review_for_missing_required_fields !== false, "Schema-required fields trigger review when absent.")}
                ${checkboxControl("Always require review", ["always_review"], Boolean(params.always_review), "Pause every document regardless of confidence and schema results.")}
                ${checkboxControl("Allow editing high-confidence fields", ["allow_operator_to_edit_high_confidence_fields"], params.allow_operator_to_edit_high_confidence_fields !== false, "Reviewers may correct fields that did not trigger the gate.")}
            </div>
        `;
    }

    function rulesControls(step) {
        const params = step.params || {};
        const info = state.csvMetadata[params.reference_file] || {};
        const columns = Array.isArray(info.columns) ? info.columns : [];
        const clauses = params.csv_match && Array.isArray(params.csv_match.clauses) ? params.csv_match.clauses : [];
        const contextFields = [...new Set([...extractionFieldNames(), "id", "nanoid", "filename", "source", "original_filename", "file_path"])];
        const optionHtml = (values, current) => [...new Set([current || "", ...values])].map((value) => `<option value="${escapeHtml(value)}" ${value === current ? "selected" : ""}>${escapeHtml(value || "Select...")}</option>`).join("");
        return `
            <div class="space-y-3">
                ${fileControl("Reference CSV", ["reference_file"], params.reference_file || "", ".csv", { startPath: "reference_file", findings: inlineFindings(step, "reference_file") })}
                ${columns.length ? `<div class="text-xs text-base-content/60">${columns.length} CSV columns loaded.</div>` : ""}
                <label class="form-control"><span class="label-text">Update field</span><select class="select select-bordered select-sm" data-param-path="${pathAttr(["update_field"])}">${optionHtml(columns, params.update_field || "")}</select>${inlineFindings(step, "update_field")}</label>
                ${textControl("Write value", ["write_value"], params.write_value || "")}
                <div class="rounded-lg border border-primary/20 bg-primary/5 p-3"><div class="text-xs font-semibold uppercase text-primary">Rule outcome</div><p class="mt-1 text-sm">If all ${clauses.length || "configured"} ${clauses.length === 1 ? "condition matches" : "conditions match"}, set <code class="font-semibold">${escapeHtml(params.update_field || "the selected field")}</code> to <code class="font-semibold">${escapeHtml(params.write_value || "the configured value")}</code>.</p></div>
                ${checkboxControl("Backup reference CSV before write", ["backup"], params.backup !== false)}
                ${section("Match conditions", `
                    <div class="mb-3 flex items-center justify-between gap-3"><p class="text-xs text-base-content/55">Every condition must match (AND).</p><button class="btn btn-outline btn-xs" type="button" data-param-action="add-rule-clause" ${clauses.length >= 5 ? "disabled" : ""}>Add clause</button></div>
                    <div class="space-y-2">${clauses.map((clause, index) => `
                        <div class="rounded-md border border-base-300 p-2">
                            <div class="mb-2 text-xs font-semibold text-base-content/60">Condition ${index + 1}</div>
                            <div class="rule-clause-grid">
                                <label class="form-control"><span class="label-text">CSV column</span><select class="select select-bordered select-sm" data-param-path="${pathAttr(["csv_match", "clauses", index, "column"])}">${optionHtml(columns, clause.column || "")}</select></label>
                                <label class="form-control"><span class="label-text">From context</span><select class="select select-bordered select-sm" data-param-path="${pathAttr(["csv_match", "clauses", index, "from_context"])}">${optionHtml(contextFields, clause.from_context || "")}</select></label>
                                <button class="btn btn-ghost btn-sm self-end text-error" type="button" data-param-action="remove-rule-clause" data-clause-index="${index}" ${clauses.length <= 1 ? "disabled" : ""}>Remove</button>
                            </div>
                            <div class="mt-2 max-w-xs"><label class="form-control"><span class="label-text">Comparison type</span><select class="select select-bordered select-sm" data-param-action="rule-comparison" data-clause-index="${index}"><option value="auto" ${clause.number === undefined || clause.number === null ? "selected" : ""}>Auto-detect</option><option value="text" ${clause.number === false ? "selected" : ""}>Text comparison</option><option value="number" ${clause.number === true ? "selected" : ""}>Numeric comparison</option></select></label></div>
                            ${inlineFindings(step, `csv_match.clauses[${index}]`, true)}
                        </div>
                    `).join("") || '<div class="empty-panel">Add a match condition.</div>'}</div>
                `)}
            </div>
        `;
    }

    function taskSpecificControls(step) {
        if (step.class === "GlmOcrExtractTask") {
            return glmOcrExtractControls(step);
        }
        const kind = taskKind(step);
        if (kind === "split") {
            return splitControls(step);
        }
        if (kind === "extract") {
            return extractControls(step);
        }
        if (kind === "review") {
            return reviewControls(step);
        }
        if (kind === "storage") {
            return storageControls(step);
        }
        if (kind === "rules") {
            return rulesControls(step);
        }
        if (kind === "archive") {
            return `<div class="space-y-3"><div class="rounded-lg border border-info/20 bg-info/10 p-3 text-sm">The original source PDF is copied here with a safe, unique filename. The source file remains in place.</div>${directoryControl("Archive directory", ["archive_dir"], (step.params || {}).archive_dir || "", { findings: inlineFindings(step, "archive_dir") })}</div>`;
        }
        if (kind === "context") {
            return numberControl("Nanoid length", ["length"], (step.params || {}).length ?? 12, 'min="5" max="21" step="1" required', inlineFindings(step, "length"));
        }
        return '<div class="empty-panel">No task-specific form exists for this task. Use advanced params JSON below.</div>';
    }

    return {
        detailsSection,
        directoryBrowserPanel,
        isRequiredType,
        taskSpecificControls,
        unwrapOptionalType,
        withRequiredState,
    };
}
