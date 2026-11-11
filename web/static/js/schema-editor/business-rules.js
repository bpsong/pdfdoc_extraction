/** Versioned rule authoring; all business evaluation stays on the server. */

const numericTypes = new Set(["number", "integer", "float"]);
const bindings = {
    "line_amount:v1": ["quantity", "unit_price", "line_total"],
    "sum_equals:v1": ["item_value", "target"],
    "date_order:v1": ["earlier", "later"],
    "required_if:v1": ["when", "required"],
};
const titles = {
    "line_amount:v1": "Line amount: quantity × unit price",
    "sum_equals:v1": "Subtotal: sum of line amounts",
    "date_order:v1": "Date order: earlier and later dates",
    "required_if:v1": "Conditional required fields",
};
const labels = {
    collection: "Item collection", quantity: "Quantity field", unit_price: "Unit price field",
    line_total: "Line total field", item_value: "Line amount to sum", target: "Invoice subtotal field",
    earlier: "Earlier date field", later: "Later date field", when: "Condition field", required: "Required fields",
};
const usesCollection = (validator) => ['line_amount:v1', 'sum_equals:v1'].includes(validator);
const scalarTypes = new Set(['string', 'number', 'integer', 'float', 'boolean', 'date', 'datetime', 'enum']);
const literalKind = (value) => value === null ? 'null' : ['number', 'boolean'].includes(typeof value) ? typeof value : 'string';
const ruleBindings = (validator) => Object.hasOwn(bindings, validator) ? bindings[validator] : [];
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g,
    (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]));
const encode = (key) => String(key).replace(/~/g, "~0").replace(/\//g, "~1");

export function createBusinessRulesModel(getDraft) {
    function supportedSection(section) {
        return section && typeof section === "object" && !Array.isArray(section)
            && (section.format_version === undefined || section.format_version === 1)
            && (section.rules === undefined || Array.isArray(section.rules));
    }
    function rules() {
        const section = getDraft().business_validation;
        return Array.isArray(section?.rules) ? section.rules : [];
    }

    function resolve(root, pointer) {
        if (typeof pointer !== "string" || !pointer.startsWith("/")
            || pointer.length > 256 || pointer.split("/").length > 17 || /~([^01]|$)/.test(pointer)) return null;
        let current = root;
        for (const encoded of pointer.slice(1).split("/")) {
            const key = encoded.replace(/~1/g, "/").replace(/~0/g, "~");
            current = current?.type === "object" ? current.properties?.[key]
                : current?.type === "array" && /^(0|[1-9][0-9]*)$/.test(key) ? current.items : null;
            if (!current || typeof current !== "object") return null;
        }
        return current;
    }

    function root() { return {type: "object", properties: getDraft().fields || {}}; }

    function options(scope, type, prefix = "", result = []) {
        for (const [key, field] of Object.entries(scope?.properties || {})) {
            if (!field || typeof field !== "object") continue;
            const path = `${prefix}/${encode(key)}`;
            if ((type === "numeric" && numericTypes.has(field.type))
                || type === 'date' && field.type === 'date' || type === 'scalar' && scalarTypes.has(field.type) || type === 'any'
                || (type === "collection" && field.type === "array" && field.items?.type === "object")) {
                result.push({value: path, label: `${field.label || key} (${path})`});
            }
            if (field.type === "object") options(field, type, path, result);
        }
        return result;
    }

    function choices(rule, prop) {
        if (rule.validator === 'date_order:v1') return options(root(), 'date');
        if (rule.validator === 'required_if:v1') return options(root(), prop === 'when' ? 'scalar' : 'any');
        if (prop === "collection") return options(root(), "collection");
        if (prop === "target") return options(root(), "numeric");
        return options(resolve(root(), rule.collection)?.items, "numeric");
    }

    function add(validator) {
        if (!Object.hasOwn(bindings, validator)) return false;
        const draft = getDraft();
        if (Object.hasOwn(draft, "business_validation")
            && !supportedSection(draft.business_validation)) {
            throw new Error("Repair or remove the unsupported rule configuration before adding rules.");
        }
        if (rules().length >= 50) throw new Error("A form supports at most 50 business rules.");
        draft.business_validation ??= {format_version: 1, rules: []};
        draft.business_validation.format_version ??= 1;
        draft.business_validation.rules ??= [];
        const base = validator.split(":")[0];
        let number = 1;
        while (rules().some((rule) => rule?.id === `${base}_${number}`)) number += 1;
        const rule = {id: `${base}_${number}`, validator, enabled: true, severity: "warning", require_review: true};
        initialize(rule, validator);
        rules().push(rule);
        return true;
    }

    function initialize(rule, validator) {
        if (usesCollection(validator)) Object.assign(rule, {tolerance: '0.01', decimal_places: 2,
            rounding: 'ROUND_HALF_UP', collection: options(root(), 'collection')[0]?.value || ''});
        if (validator === 'date_order:v1') rule.allow_equal = true;
        if (validator === 'required_if:v1') rule.equals = '';
        ruleBindings(validator).forEach((prop) => { rule[prop] = prop === 'required' ? [] : ''; });
    }

    function update(index, prop, value) {
        const rule = rules()[index];
        if (!rule || typeof rule !== "object") return false;
        if (prop === "validator" && Object.hasOwn(bindings, value)) {
            [...Object.values(bindings).flat(), 'collection', 'tolerance', 'decimal_places', 'rounding', 'allow_equal', 'equals']
                .forEach((key) => { delete rule[key]; });
            initialize(rule, value);
        }
        if (prop === 'equals_kind') {
            rule.equals = {string: '', number: 0, boolean: false, null: null}[value];
            return true;
        }
        if (prop === 'equals') value = literalKind(rule.equals) === 'number' ? (value === '' ? '' : Number(value))
            : literalKind(rule.equals) === 'boolean' ? value === 'true' : value;
        if (prop === 'when' && value !== rule.when) {
            const type = resolve(root(), value)?.type;
            rule.equals = numericTypes.has(type) ? 0 : type === 'boolean' ? false : '';
        }
        rule[prop] = prop === "decimal_places" ? (String(value) === "" ? "" : Number(value)) : value;
        return true;
    }

    function move(index, direction) {
        const next = index + direction;
        if (next < 0 || next >= rules().length) return false;
        [rules()[index], rules()[next]] = [rules()[next], rules()[index]];
        return true;
    }

    function remove(index) {
        rules().splice(index, 1);
        if (!rules().length) delete getDraft().business_validation;
    }

    function findings() {
        const section = getDraft().business_validation;
        if (!Object.hasOwn(getDraft(), "business_validation")) return [];
        const result = [];
        const addFinding = (path, message) => result.push({path: `business_validation.${path}`, message});
        if (!supportedSection(section)) {
            addFinding("format_version", "Use business-validation format 1 with a rules list.");
            return result;
        }
        if (rules().length > 50) addFinding("rules", "A form supports at most 50 business rules.");
        const ids = new Set();
        rules().forEach((rule, index) => {
            const path = `rules.${index}`;
            if (!rule || typeof rule !== "object" || Array.isArray(rule)) {
                addFinding(path, "Rule must be an object."); return;
            }
            if (typeof rule.id !== "string" || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(rule.id) || ids.has(rule.id)) {
                addFinding(`${path}.id`, "Use a unique rule ID starting with a letter (up to 64 characters).");
            }
            ids.add(rule.id);
            if (!Object.hasOwn(bindings, rule.validator)) {
                addFinding(`${path}.validator`, "Select an available validator version."); return;
            }
            const collection = resolve(root(), rule.collection);
            if (usesCollection(rule.validator) && (collection?.type !== "array" || collection.items?.type !== "object")) {
                addFinding(`${path}.collection`, "Select an existing array of objects.");
            }
            if (usesCollection(rule.validator)) for (const prop of bindings[rule.validator]) {
                const field = resolve(prop === "target" ? root() : collection?.items, rule[prop]);
                if (!numericTypes.has(field?.type)) addFinding(`${path}.${prop}`, "Select an existing numeric field.");
            }
            if (rule.validator === 'date_order:v1') {
                for (const prop of bindings[rule.validator]) if (resolve(root(), rule[prop])?.type !== 'date') {
                    addFinding(`${path}.${prop}`, 'Select an existing date field.');
                }
                if (rule.allow_equal !== undefined && typeof rule.allow_equal !== 'boolean') addFinding(`${path}.allow_equal`, 'Choose whether equal dates are allowed.');
            }
            if (rule.validator === 'required_if:v1') {
                const condition = resolve(root(), rule.when);
                if (!scalarTypes.has(condition?.type)) addFinding(`${path}.when`, 'Select an existing scalar condition field.');
                if (!Array.isArray(rule.required) || !rule.required.length || rule.required.length > 20 || new Set(rule.required).size !== rule.required.length) {
                    addFinding(`${path}.required`, 'Select 1 to 20 different required fields.');
                } else for (const [index, pointer] of rule.required.entries()) if (!resolve(root(), pointer)) {
                    addFinding(`${path}.required.${index}`, 'Select an existing required field.');
                }
                const type = condition?.type;
                if (rule.equals !== null && !(numericTypes.has(type) && typeof rule.equals === 'number' && Number.isFinite(rule.equals)
                        || type === 'boolean' && typeof rule.equals === 'boolean'
                        || ['string', 'date', 'datetime'].includes(type) && typeof rule.equals === 'string'
                        || type === 'enum' && ['string', 'number', 'boolean'].includes(typeof rule.equals))) {
                    addFinding(`${path}.equals`, 'Condition value must match the selected field type.');
                }
                if (typeof rule.equals === 'string' && rule.equals.length > 500) addFinding(`${path}.equals`, 'Condition text must contain at most 500 characters.');
                if (type === 'enum' && rule.equals !== null) {
                    const choices = condition.choices?.length ? condition.choices : condition.enum;
                    if (Array.isArray(choices) && !choices.some((choice) => {
                        const option = choice && typeof choice === 'object' && !Array.isArray(choice)
                            ? Object.hasOwn(choice, 'value') ? choice.value : choice.label : choice;
                        return typeof option === typeof rule.equals && option === rule.equals;
                    })) addFinding(`${path}.equals`, 'Select a condition value offered by the field.');
                }
            }
            if (rule.tolerance !== undefined && (String(rule.tolerance).trim() === ""
                || typeof rule.tolerance === "boolean" || !Number.isFinite(Number(rule.tolerance)) || Number(rule.tolerance) < 0)) {
                addFinding(`${path}.tolerance`, "Tolerance must be a finite non-negative decimal.");
            }
            if (rule.decimal_places !== undefined && (!Number.isInteger(rule.decimal_places)
                || rule.decimal_places < 0 || rule.decimal_places > 8)) addFinding(`${path}.decimal_places`, "Use 0 to 8 decimal places.");
            if (rule.severity !== undefined && !["warning", "blocking"].includes(rule.severity)) addFinding(`${path}.severity`, "Select warning or blocking.");
            if (rule.rounding !== undefined && !["ROUND_HALF_UP", "ROUND_HALF_EVEN"].includes(rule.rounding)) addFinding(`${path}.rounding`, "Select a supported rounding mode.");
        });
        return result;
    }
    return {rules, choices, add, update, move, remove, findings};
}

export function renderBusinessRules(container, model, findings, editable) {
    const active = document.activeElement;
    const focusPath = container.contains(active) ? active.dataset.rulePath : null;
    const selection = focusPath && active.type === "text" ? [active.selectionStart, active.selectionEnd] : null;
    const rules = model.rules();
    const find = (path) => findings.find((finding) => {
        const position = finding.path.indexOf("business_validation");
        return finding.path.slice(position) === path;
    });
    function control(rule, index, prop, label, choices = null, kind = "text") {
        const path = `business_validation.rules.${index}.${prop}`;
        const value = prop === 'equals_kind' ? literalKind(rule.equals) : rule[prop] ?? ({enabled: true, require_review: true, allow_equal: true, severity: "warning",
            tolerance: "0.01", decimal_places: 2, rounding: "ROUND_HALF_UP"}[prop] ?? "");
        const error = find(path) || (prop === 'required' ? findings.find((item) => item.path.includes(`${path}.`)) : null);
        const attrs = `data-rule-index="${index}" data-rule-prop="${prop}" data-rule-path="${path}"`
            + ` aria-label="Rule ${index + 1}: ${escapeHtml(label)}"`
            + (error ? ` aria-invalid="true" aria-describedby="business-error-${index}-${prop}"` : "");
        let input;
        if (choices) {
            const available = [...choices];
            const selected = kind === 'multiple' ? (Array.isArray(value) ? value : []) : [value];
            for (const entry of selected) if (entry && !available.some((option) => option.value === entry)) available.unshift({value: entry, label: `Current binding: ${entry}`});
            const title = available.find((option) => option.value === value)?.label || "Choose a field";
            input = `<select class="select select-bordered select-sm" title="${escapeHtml(title)}" ${attrs} ${kind === 'multiple' ? 'multiple size="4"' : ''}>
                ${kind === 'multiple' ? '' : '<option value="">Choose…</option>'}${available.map((option) => `<option value="${escapeHtml(option.value)}" ${selected.includes(option.value) ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}</select>`;
        } else if (kind === "checkbox") {
            input = `<input type="checkbox" class="checkbox checkbox-sm" ${attrs} ${value ? "checked" : ""}>`;
        } else {
            input = `<input type="${kind}" class="input input-bordered input-sm" ${attrs} value="${escapeHtml(value)}" ${kind === "number" ? prop === 'decimal_places' ? 'min="0" max="8" step="1"' : 'step="any"' : ""}>`;
        }
        return `<label class="form-control"><span class="label-text">${escapeHtml(label)}</span>${input}
            ${error ? `<span class="text-xs text-error" id="business-error-${index}-${prop}">${escapeHtml(error.message)}</span>` : ""}</label>`;
    }
    container.innerHTML = rules.length ? rules.map((raw, index) => {
        const rule = raw && typeof raw === "object" ? raw : {};
        return `<fieldset class="business-rule-card" ${editable ? "" : "disabled"}>
            <legend>${index + 1}. ${escapeHtml(rule.id || "Business rule")}</legend>
            <div class="business-rule-actions">
                <button type="button" class="btn btn-outline btn-xs" data-rule-action="up" data-rule-index="${index}" ${index === 0 ? "disabled" : ""} aria-label="Move rule ${index + 1} up">Move up</button>
                <button type="button" class="btn btn-outline btn-xs" data-rule-action="down" data-rule-index="${index}" ${index === rules.length - 1 ? "disabled" : ""} aria-label="Move rule ${index + 1} down">Move down</button>
                <button type="button" class="btn btn-outline btn-error btn-xs" data-rule-action="delete" data-rule-index="${index}" aria-label="Delete rule ${index + 1}">Delete</button>
            </div>
            <div class="business-rule-grid">
                ${control(rule, index, "id", "Rule ID")}
                ${control(rule, index, "validator", "Check", Object.entries(titles).map(([value, label]) => ({value, label})))}
                ${control(rule, index, "enabled", "Enabled", null, "checkbox")}
                ${control(rule, index, "require_review", "Require review on warning", null, "checkbox")}
                ${usesCollection(rule.validator) ? control(rule, index, "collection", labels.collection, model.choices(rule, "collection")) : ''}
                ${ruleBindings(rule.validator).map((prop) => control(rule, index, prop, labels[prop], model.choices(rule, prop), prop === 'required' ? 'multiple' : 'text')).join("")}
                ${rule.validator === 'date_order:v1' ? control(rule, index, 'allow_equal', 'Allow same day', null, 'checkbox') : ''}
                ${rule.validator === 'required_if:v1' ? control(rule, index, 'equals_kind', 'Condition value type', ['string', 'number', 'boolean', 'null'].map(value => ({value, label: {string: 'Text', number: 'Number', boolean: 'Boolean', null: 'Null (missing value)'}[value]})))
                    + (rule.equals === null ? '<p class="text-sm">Condition matches an explicit null value.</p>' : control(rule, index, 'equals', 'Equals value', typeof rule.equals === 'boolean' ? [{value: true, label: 'True'}, {value: false, label: 'False'}] : null, typeof rule.equals === 'number' ? 'number' : 'text')) : ''}
                ${control(rule, index, "severity", "Severity", [{value: "warning", label: "Warning"}, {value: "blocking", label: "Blocking"}])}
                ${usesCollection(rule.validator) ? control(rule, index, "tolerance", "Allowed difference")
                    + control(rule, index, "decimal_places", "Decimal places", null, "number")
                    + control(rule, index, "rounding", "Rounding", [{value: "ROUND_HALF_UP", label: "Half up"}, {value: "ROUND_HALF_EVEN", label: "Half even"}]) : ''}
                ${control(rule, index, "message", "Mismatch message (optional)")}
            </div>
            <p class="text-xs text-base-content/60">Blocking findings always require review.${usesCollection(rule.validator) ? ' Bind the subtotal before discount and tax.' : rule.validator === 'date_order:v1' ? ' Compare calendar dates in YYYY-MM-DD format.' : ' A missing condition cannot be evaluated; false and zero remain valid values.'}</p>
        </fieldset>`;
    }).join("") : '<p class="text-sm text-base-content/60">No business rules configured.</p>';
    if (focusPath) {
        const replacement = Array.from(container.querySelectorAll("[data-rule-path]")).find((element) => element.dataset.rulePath === focusPath);
        if (replacement) {
            replacement.focus({preventScroll: true});
            if (selection) replacement.setSelectionRange(...selection);
        }
    }
}
