/** Catalog-driven authoring; every business evaluation stays on the server. */

const numericTypes = ['number', 'integer', 'float'];
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g,
    (char) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
const copy = (value) => value === undefined ? undefined : structuredClone(value);
const parts = (path) => String(path).split('.');
const safeParts = (path) => parts(path).every((part) => /^[a-z][a-z0-9_]*$/.test(part)
    && !['__proto__', 'constructor', 'prototype'].includes(part));
const get = (object, path) => parts(path).reduce((value, key) => value && Object.hasOwn(value, key) ? value[key] : undefined, object);
function put(object, path, value) {
    if (!safeParts(path)) return;
    const keys = parts(path);
    let parent = object;
    keys.slice(0, -1).forEach((key) => {
        if (!parent[key] || typeof parent[key] !== 'object' || Array.isArray(parent[key])) parent[key] = {};
        parent = parent[key];
    });
    if (value === undefined) delete parent[keys.at(-1)];
    else parent[keys.at(-1)] = value;
}
const literalKind = (value) => value === null ? 'null' : ['number', 'boolean'].includes(typeof value) ? typeof value : 'string';
const encode = (key) => String(key).replace(/~/g, '~0').replace(/\//g, '~1');
const knownKinds = new Set(['field', 'collection', 'choice', 'boolean', 'text', 'decimal', 'integer', 'typed', 'operand']);

export function createBusinessRulesModel(getDraft, initialCatalog = null) {
    let catalog = null;
    function setCatalog(value) {
        if (!value || value.catalog_version !== 1 || !Array.isArray(value.validators)
                || !Array.isArray(value.common_controls) || value.validators.some((entry) =>
                    !Array.isArray(entry.controls) || entry.controls.some((control) => !knownKinds.has(control.kind)))) {
            throw new Error('Unsupported business-rule catalog. Retry or contact a maintainer.');
        }
        catalog = copy(value);
    }
    if (initialCatalog) setCatalog(initialCatalog);
    const definitions = () => catalog?.validators || [];
    const definition = (id) => definitions().find((entry) => entry.id === id);
    const commonControls = () => catalog?.common_controls || [];
    const rules = () => Array.isArray(getDraft().business_validation?.rules) ? getDraft().business_validation.rules : [];
    const root = () => ({type: 'object', properties: getDraft().fields || {}});
    function resolve(scope, pointer) {
        if (typeof pointer !== 'string' || !pointer.startsWith('/') || pointer.length > 256
                || pointer.split('/').length > 17 || /~([^01]|$)/.test(pointer)) return null;
        let current = scope;
        for (const encoded of pointer.slice(1).split('/')) {
            const key = encoded.replace(/~1/g, '/').replace(/~0/g, '~');
            current = current?.type === 'object' ? current.properties?.[key]
                : current?.type === 'array' && /^(0|[1-9][0-9]*)$/.test(key) ? current.items : null;
            if (!current || typeof current !== 'object') return null;
        }
        return current;
    }
    function options(scope, types = null, prefix = '', result = [], collection = false) {
        for (const [key, field] of Object.entries(scope?.properties || {})) {
            if (!field || typeof field !== 'object') continue;
            const path = `${prefix}/${encode(key)}`;
            if (collection ? field.type === 'array' && field.items?.type === 'object' : !types || types.includes(field.type)) {
                result.push({value: path, label: `${field.label || key} (${path})`});
            }
            if (field.type === 'object') options(field, types, path, result, collection);
        }
        return result;
    }
    const descriptorValue = (rule, control) => get(rule, control.name) === undefined ? copy(control.default) : get(rule, control.name);
    function visible(rule, control) {
        const controls = definition(rule.validator)?.controls || [];
        return (control.visible_when || []).every(({field, values}) => {
            const other = controls.find((entry) => entry.name === field);
            const value = get(rule, field) === undefined ? other?.default : get(rule, field);
            return values.some((choice) => typeof choice === typeof value && choice === value);
        });
    }
    function choices(rule, prop, descriptor = null) {
        const control = descriptor || definition(rule.validator)?.controls.find((entry) => entry.name === prop);
        if (!control) return [];
        if (control.kind === 'choice') return control.choices;
        if (control.kind === 'collection') return options(root(), null, '', [], true);
        const scope = control.scope === 'row' ? resolve(root(), get(rule, definition(rule.validator)?.collection))?.items : root();
        return options(scope, control.types);
    }
    function operandChoices(rule, operand, control) {
        const collection = definition(rule.validator)?.collection;
        return options(operand?.scope === 'row' ? resolve(root(), rule[collection])?.items : root(), control.types || numericTypes);
    }
    function unavailableReason(entry) {
        const collections = options(root(), null, '', [], true);
        if (entry.collection && !entry.collection_when && !collections.length) return 'Add a repeating group with object rows first.';
        for (const control of entry.controls) {
            if (control.kind === 'operand') {
                if (!options(root(), control.types).length && !collections.some((item) =>
                    options(resolve(root(), item.value)?.items, control.types).length)) return 'Add numeric fields first.';
            } else if (control.kind === 'field' && control.required) {
                const available = control.scope === 'row'
                    ? collections.some((item) => options(resolve(root(), item.value)?.items, control.types).length)
                    : options(root(), control.types).length;
                if (!available) return `Add compatible fields for ${control.label.toLowerCase()} first.`;
            }
        }
        return '';
    }
    function initialize(rule, entry) {
        for (const control of [...entry.controls, ...commonControls()]) {
            if (!visible(rule, control)) continue;
            const value = control.default !== null && control.default !== undefined ? copy(control.default)
                : control.kind === 'operand' ? {kind: 'field', scope: rule.scope === 'rows' ? 'row' : 'document', field: ''}
                : control.many ? [] : control.kind === 'boolean' ? false : '';
            put(rule, control.name, value);
        }
    }
    function supportedSection(section) {
        return section && typeof section === 'object' && !Array.isArray(section)
            && (section.format_version === undefined || section.format_version === 1)
            && (section.rules === undefined || Array.isArray(section.rules));
    }
    function add(identifier) {
        const entry = definition(identifier);
        if (!entry) return false;
        const draft = getDraft();
        if (Object.hasOwn(draft, 'business_validation') && !supportedSection(draft.business_validation)) {
            throw new Error('Repair or remove the unsupported rule configuration before adding rules.');
        }
        if (rules().length >= 50) throw new Error('A form supports at most 50 business rules.');
        draft.business_validation ??= {format_version: 1, rules: []};
        draft.business_validation.format_version ??= 1;
        draft.business_validation.rules ??= [];
        const base = identifier.split(':')[0].replace(/[^A-Za-z0-9_-]/g, '_');
        let number = 1;
        while (rules().some((rule) => rule?.id === `${base}_${number}`)) number += 1;
        const rule = {id: `${base}_${number}`, validator: identifier};
        initialize(rule, entry);
        rules().push(rule);
        return true;
    }
    function update(index, prop, value) {
        const rule = rules()[index];
        if (!rule || !catalog) return false;
        if (prop === 'validator') {
            const entry = definition(value);
            if (!entry) return false;
            for (const key of Object.keys(rule)) if (!['id', 'enabled', 'severity', 'require_review', 'message'].includes(key)) delete rule[key];
            rule.validator = value;
            const common = Object.fromEntries(commonControls().map((control) => [control.name, copy(rule[control.name])]));
            initialize(rule, entry);
            for (const [key, original] of Object.entries(common)) if (original !== undefined) rule[key] = original;
            return true;
        }
        const controls = [...(definition(rule.validator)?.controls || []), ...commonControls()];
        const typed = controls.find((control) => control.kind === 'typed' && `${control.name}_kind` === prop);
        if (typed) { put(rule, typed.name, {string: '', number: 0, boolean: false, null: null}[value]); return true; }
        const operand = controls.find((control) => control.kind === 'operand' && prop.startsWith(`${control.name}.`));
        if (operand && prop.endsWith('.kind')) {
            put(rule, operand.name, value === 'constant' && operand.allow_constant ? {kind: 'constant', value: ''}
                : {kind: 'field', scope: rule.scope === 'rows' ? 'row' : 'document', field: ''});
            return true;
        }
        if (operand && prop.endsWith('.scope')) { put(rule, operand.name, {kind: 'field', scope: value, field: ''}); return true; }
        if (operand && prop.endsWith('.field') && get(rule, operand.name)?.kind !== 'field') {
            put(rule, operand.name, {kind: 'field', scope: rule.scope === 'rows' ? 'row' : 'document', field: value});
            return true;
        }
        const control = controls.find((entry) => entry.name === prop);
        if (control?.kind === 'choice') {
            const selected = control.choices.find((choice) => String(choice.value) === String(value));
            if (selected) value = selected.value;
        }
        if (control?.kind === 'typed') value = literalKind(get(rule, prop)) === 'number' ? value === '' ? '' : Number(value)
            : literalKind(get(rule, prop)) === 'boolean' ? value === 'true' : value;
        if (control?.kind === 'integer') value = value === '' ? '' : Number(value);
        put(rule, prop, value);
        for (const entry of controls) {
            if (entry.kind === 'typed' && entry.condition_field === prop) {
                const type = resolve(root(), value)?.type;
                put(rule, entry.name, numericTypes.includes(type) ? 0 : type === 'boolean' ? false : '');
            }
            if (entry.kind === 'operand' && prop === 'scope' && get(rule, entry.name)?.kind === 'field') {
                put(rule, entry.name, {kind: 'field', scope: value === 'rows' ? 'row' : 'document', field: ''});
            }
            if (!visible(rule, entry)) put(rule, entry.name, undefined);
            else if (get(rule, entry.name) === undefined && entry.default !== null) put(rule, entry.name, copy(entry.default));
        }
        return true;
    }
    function move(index, delta) {
        if (index + delta < 0 || index + delta >= rules().length) return false;
        [rules()[index], rules()[index + delta]] = [rules()[index + delta], rules()[index]];
        return true;
    }
    function remove(index) { rules().splice(index, 1); if (!rules().length) delete getDraft().business_validation; }
    function finiteDecimal(value) {
        const text = String(value).trim();
        return ![null, true, false].includes(value) && ['string', 'number'].includes(typeof value) && text.length <= 128
            && /^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(text) && Number.isFinite(Number(text));
    }
    function findings() {
        const section = getDraft().business_validation;
        if (section === undefined) return [];
        const result = [];
        const addFinding = (path, message) => result.push({path: `business_validation.${path}`, message});
        if (!supportedSection(section)) { addFinding('', 'Use a supported business-validation section.'); return result; }
        if (rules().length > 50) addFinding('rules', 'A form supports at most 50 rules.');
        const ids = new Set();
        rules().forEach((rule, index) => {
            const path = `rules.${index}`;
            if (!rule || typeof rule !== 'object' || Array.isArray(rule)) { addFinding(path, 'Rule must be an object.'); return; }
            if (typeof rule.id !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(rule.id) || ids.has(rule.id)) addFinding(`${path}.id`, 'Use a unique rule ID starting with a letter (up to 64 characters).');
            ids.add(rule.id);
            if (!catalog) return;
            const entry = definition(rule.validator);
            if (!entry) { addFinding(`${path}.validator`, 'Select an available validator version.'); return; }
            function fieldFinding(control, value, key = control.name, scope = control.scope) {
                const parent = scope === 'row' ? resolve(root(), rule[entry.collection])?.items : root();
                const field = resolve(parent, value);
                if (!field || control.types && !control.types.includes(field.type)) addFinding(`${path}.${key}`, 'Select an existing compatible field.');
            }
            for (const control of [...entry.controls, ...commonControls()]) {
                const value = descriptorValue(rule, control);
                if (!visible(rule, control)) {
                    if (get(rule, control.name) !== undefined) addFinding(`${path}.${control.name}`, 'Remove this option for the selected operation.');
                    continue;
                }
                const key = `${path}.${control.name}`;
                if (control.kind === 'collection') {
                    if (!choices(rule, control.name).some((item) => item.value === value)) addFinding(key, 'Select an existing repeating group of objects.');
                } else if (control.kind === 'field') {
                    if (control.many) {
                        if (!Array.isArray(value) || !value.length || value.length > (control.maximum || 20) || new Set(value).size !== value.length) addFinding(key, 'Select different required fields (up to 20).');
                        else value.forEach((pointer, number) => fieldFinding(control, pointer, `${control.name}.${number}`));
                    } else fieldFinding(control, value);
                } else if (control.kind === 'operand') {
                    if (value?.kind === 'constant' && control.allow_constant) {
                        if (!finiteDecimal(value.value)) addFinding(`${key}.value`, 'Enter a finite numeric constant.');
                    } else if (value?.kind === 'field') {
                        const scope = value.scope === undefined ? 'document' : value.scope;
                        if (!['document', 'row'].includes(scope) || scope === 'row' && rule.scope !== 'rows') addFinding(`${key}.scope`, 'Select a scope available to this rule.');
                        fieldFinding(control, value.field, `${control.name}.field`, scope);
                    } else addFinding(key, 'Select a field or an allowed constant.');
                } else if (control.kind === 'choice') {
                    if (!control.choices.some((choice) => choice.value === value)) addFinding(key, 'Select an available option.');
                } else if (control.kind === 'boolean') {
                    if (typeof value !== 'boolean') addFinding(key, 'Choose true or false.');
                } else if (['decimal', 'integer'].includes(control.kind)) {
                    if (!finiteDecimal(value) || control.kind === 'integer' && !Number.isInteger(value)
                        || control.minimum !== null && Number(value) < control.minimum
                        || control.maximum !== null && Number(value) > control.maximum) addFinding(key, 'Enter a number within the supported bounds.');
                } else if (control.kind === 'typed') {
                    const condition = resolve(root(), get(rule, control.condition_field));
                    const type = condition?.type;
                    if (value !== null && !(numericTypes.includes(type) && typeof value === 'number' && Number.isFinite(value)
                        || type === 'boolean' && typeof value === 'boolean'
                        || ['string', 'date', 'datetime'].includes(type) && typeof value === 'string'
                        || type === 'enum' && ['string', 'number', 'boolean'].includes(typeof value))) addFinding(key, 'Condition value must match the selected field type.');
                    const choices = condition?.choices?.length ? condition.choices : condition?.enum;
                    if (type === 'enum' && value !== null && Array.isArray(choices) && !choices.some((choice) => {
                        const option = choice && typeof choice === 'object' ? Object.hasOwn(choice, 'value') ? choice.value : choice.label : choice;
                        return typeof option === typeof value && option === value;
                    })) addFinding(key, 'Select a condition value offered by the field.');
                    if (typeof value === 'string' && value.length > 500) addFinding(key, 'Condition text must contain at most 500 characters.');
                } else if (value !== undefined && value !== null && (typeof value !== 'string' || control.max_length && value.length > control.max_length)) addFinding(key, 'Enter text within the supported length.');
            }
        });
        return result;
    }
    return {rules, choices, operandChoices, add, update, move, remove, findings, definitions, definition,
        commonControls, setCatalog, catalogReady: () => Boolean(catalog), descriptorValue, visible, unavailableReason};
}

export function renderBusinessRulePicker(container, model, query = '') {
    const search = query.trim().toLowerCase();
    const entries = model.definitions().filter((entry) => `${entry.title} ${entry.description} ${entry.category}`.toLowerCase().includes(search));
    container.innerHTML = entries.map((entry) => {
        const reason = model.unavailableReason(entry);
        return `<button type="button" class="btn btn-outline business-pattern-choice" data-add-business-rule="${escapeHtml(entry.id)}" ${reason ? 'disabled' : ''}>
            <strong>${escapeHtml(entry.title)}</strong><span>${escapeHtml(reason || entry.description)}</span></button>`;
    }).join('') || '<p>No matching rule patterns.</p>';
}

export function renderBusinessRules(container, model, findings, editable) {
    findings = findings.map((finding) => {
        const position = finding.path.indexOf('business_validation');
        return position < 0 ? finding : {...finding, path: finding.path.slice(position)};
    });
    const active = document.activeElement;
    const focusPath = container.contains(active) ? active.dataset.rulePath : null;
    const selection = focusPath && active.type === 'text' ? [active.selectionStart, active.selectionEnd] : null;
    const openIds = new Set(Array.from(container.querySelectorAll?.('details[open]') || [], (item) => item.dataset.ruleAdvanced));
    function control(rule, index, spec, value = model.descriptorValue(rule, spec), choices = null) {
        const prop = spec.name;
        const path = `business_validation.rules.${index}.${prop}`;
        const error = findings.find((item) => item.path === path || spec.many && item.path.startsWith(`${path}.`));
        const errorId = `business-error-${index}-${prop.replaceAll('.', '-')}`;
        const attrs = `data-rule-index="${index}" data-rule-prop="${escapeHtml(prop)}" data-rule-path="${path}" aria-label="Rule ${index + 1}: ${escapeHtml(spec.label)}"`
            + (error ? ` aria-invalid="true" aria-describedby="${errorId}"` : '');
        let input;
        if (choices) {
            const available = [...choices];
            const selected = spec.many ? Array.isArray(value) ? value : [] : [value];
            for (const entry of selected) if (entry && !available.some((item) => item.value === entry)) available.unshift({value: entry, label: `Current binding: ${entry}`});
            input = `<select class="select select-bordered select-sm" ${attrs} ${spec.many ? 'multiple size="4"' : ''}>${spec.many ? '' : '<option value="">Choose…</option>'}
                ${available.map((item) => `<option value="${escapeHtml(item.value)}" ${selected.includes(item.value) ? 'selected' : ''}>${escapeHtml(item.label)}</option>`).join('')}</select>`;
        } else if (spec.kind === 'boolean') input = `<input type="checkbox" class="checkbox checkbox-sm" ${attrs} ${value ? 'checked' : ''}>`;
        else input = `<input type="${spec.kind === 'integer' ? 'number' : 'text'}" class="input input-bordered input-sm" ${attrs} value="${escapeHtml(value)}"
            ${spec.kind === 'decimal' ? 'inputmode="decimal"' : ''} ${spec.minimum !== null && spec.minimum !== undefined ? `min="${spec.minimum}"` : ''}
            ${spec.maximum !== null && spec.maximum !== undefined ? `max="${spec.maximum}"` : ''} ${spec.max_length ? `maxlength="${spec.max_length}"` : ''}>`;
        return `<label class="form-control"><span class="label-text">${escapeHtml(spec.label)}</span>${input}
            ${error ? `<span class="text-xs text-error" id="${errorId}">${escapeHtml(error.message)}</span>` : ''}</label>`;
    }
    function widget(rule, index, spec) {
        if (!model.visible(rule, spec)) return '';
        const value = model.descriptorValue(rule, spec);
        if (spec.kind === 'typed') {
            const kind = literalKind(value);
            return control(rule, index, {...spec, name: `${spec.name}_kind`, label: 'Condition value type'}, kind,
                ['string', 'number', 'boolean', 'null'].map((item) => ({value: item, label: {string: 'Text', number: 'Number', boolean: 'Boolean', null: 'Null (explicit value)'}[item]})))
                + (kind === 'null' ? '<p>Condition matches an explicit null value.</p>'
                    : control(rule, index, spec, kind === 'boolean' ? String(value) : value,
                        kind === 'boolean' ? [{value: 'true', label: 'True'}, {value: 'false', label: 'False'}] : null));
        }
        if (spec.kind === 'operand') {
            const operand = value || {kind: 'field', scope: 'document', field: ''};
            const kindControl = spec.allow_constant ? control(rule, index, {...spec, name: `${spec.name}.kind`, label: `${spec.label}: source`}, operand.kind,
                [{value: 'field', label: 'Field'}, {value: 'constant', label: 'Constant'}]) : '';
            if (operand.kind === 'constant') return kindControl + control(rule, index,
                {...spec, kind: 'decimal', name: `${spec.name}.value`, label: `${spec.label}: constant`}, operand.value);
            const scopes = [{value: 'document', label: 'Document'}];
            if (rule.scope === 'rows') scopes.push({value: 'row', label: 'Current row'});
            return kindControl + control(rule, index, {...spec, name: `${spec.name}.scope`, label: `${spec.label}: scope`}, operand.scope === undefined ? 'document' : operand.scope, scopes)
                + control(rule, index, {...spec, name: `${spec.name}.field`, label: `${spec.label}: field`}, operand.field, model.operandChoices(rule, operand, spec));
        }
        return control(rule, index, spec, value, ['field', 'collection', 'choice'].includes(spec.kind) ? model.choices(rule, spec.name, spec) : null);
    }
    function summary(rule, entry) {
        return entry.controls.filter((spec) => model.visible(rule, spec)).map((spec) => {
            const value = model.descriptorValue(rule, spec);
            if (spec.kind === 'operand') {
                const label = value?.kind === 'constant' ? value.value : model.operandChoices(rule, value, spec).find((item) => item.value === value?.field)?.label;
                return label ? `${spec.label}: ${label}` : '';
            }
            if (!['field', 'collection', 'choice'].includes(spec.kind)) return '';
            const selected = Array.isArray(value) ? value : [value];
            const labels = model.choices(rule, spec.name, spec).filter((item) => selected.includes(item.value)).map((item) => item.label);
            return labels.length ? `${spec.label}: ${labels.join(', ')}` : '';
        }).filter(Boolean).join(' · ');
    }
    container.innerHTML = model.rules().map((raw, index) => {
        const rule = raw && typeof raw === 'object' ? raw : {};
        const entry = model.definition(rule.validator);
        const ready = Boolean(entry && model.catalogReady());
        const idError = findings.some((item) => item.path === `business_validation.rules.${index}.id`);
        return `<fieldset class="business-rule-card" ${editable ? '' : 'disabled'}><legend>${index + 1}. ${escapeHtml(rule.id || 'Business rule')}</legend>
            <div class="business-rule-actions">
                <button type="button" class="btn btn-outline btn-xs" data-rule-action="up" data-rule-index="${index}" ${index ? '' : 'disabled'} aria-label="Move rule ${index + 1} up">Move up</button>
                <button type="button" class="btn btn-outline btn-xs" data-rule-action="down" data-rule-index="${index}" ${index === model.rules().length - 1 ? 'disabled' : ''} aria-label="Move rule ${index + 1} down">Move down</button>
                <button type="button" class="btn btn-outline btn-error btn-xs" data-rule-action="delete" data-rule-index="${index}" aria-label="Delete rule ${index + 1}">Delete</button>
            </div>${ready ? `<p>${escapeHtml(entry.description)}</p><div class="business-rule-grid">
                ${control(rule, index, {name: 'validator', label: 'Pattern'}, rule.validator, model.definitions().map((item) => ({value: item.id, label: item.title})))}
                ${entry.controls.map((spec) => widget(rule, index, spec)).join('')}
                ${model.commonControls().filter((spec) => spec.name !== 'message').map((spec) => widget(rule, index, spec)).join('')}
                </div><p class="business-rule-summary">${escapeHtml(summary(rule, entry))}</p>
                <details data-rule-advanced="${escapeHtml(rule.id)}" ${idError || openIds.has(rule.id) ? 'open' : ''}><summary>Advanced settings</summary><div class="business-rule-grid">
                ${control(rule, index, {name: 'id', label: 'Rule ID'}, rule.id)}
                ${model.commonControls().filter((spec) => spec.name === 'message').map((spec) => widget(rule, index, spec)).join('')}</div></details>`
                : `<p>Rule controls unavailable. Retry the catalog or repair the unavailable validator. Saved configuration is retained.</p><pre>${escapeHtml(JSON.stringify(rule, null, 2))}</pre>`}
            <p class="text-xs text-base-content/60">Blocking findings always require review. Revalidate current values after corrections.</p></fieldset>`;
    }).join('') || '<p class="text-sm text-base-content/60">No business rules configured.</p>';
    if (focusPath) {
        const replacement = Array.from(container.querySelectorAll('[data-rule-path]')).find((element) => element.dataset.rulePath === focusPath);
        if (replacement) {
            if (replacement.closest('details')) replacement.closest('details').open = true;
            replacement.focus({preventScroll: true});
            if (selection && replacement.type === 'text') replacement.setSelectionRange(...selection);
        }
    }
}
