/** Pure YAML-preview generation with recursive secret redaction. */

function scalarYaml(value) {
    if (value === null || value === undefined) return "null";
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    return JSON.stringify(String(value));
}

export function renderYamlValue(value, depth = 0) {
    const indent = "  ".repeat(depth);
    if (Array.isArray(value)) {
        if (!value.length) return "[]";
        return value.map((item) => {
            if (item && typeof item === "object") {
                if (!Object.keys(item).length) return `${indent}- ${renderYamlValue(item, depth + 1)}`;
                return `${indent}- ${renderYamlValue(item, depth + 1).trimStart()}`;
            }
            return `${indent}- ${scalarYaml(item)}`;
        }).join("\n");
    }
    if (value && typeof value === "object") {
        const entries = Object.entries(value);
        if (!entries.length) return "{}";
        return entries.map(([key, item]) => {
            const renderedKey = scalarYaml(String(key));
            if (item && typeof item === "object") {
                if (!Object.keys(item).length) {
                    return `${indent}${renderedKey}: ${renderYamlValue(item, depth + 1)}`;
                }
                return `${indent}${renderedKey}:\n${renderYamlValue(item, depth + 1)}`;
            }
            return `${indent}${renderedKey}: ${scalarYaml(item)}`;
        }).join("\n");
    }
    return scalarYaml(value);
}

function isSecretKey(key) {
    return /(api[_-]?key|password|secret|token|credential)/i.test(String(key || ""));
}

export function redactSecrets(value) {
    if (Array.isArray(value)) return value.map((item) => redactSecrets(item));
    if (value && typeof value === "object") {
        return Object.fromEntries(Object.entries(value).map(([key, item]) => [
            key,
            isSecretKey(key) ? "[REDACTED]" : redactSecrets(item),
        ]));
    }
    return value;
}

export function previewDefinition(draft) {
    const tasks = {};
    const pipeline = [];
    const steps = Array.isArray(draft && draft.steps) ? draft.steps : [];
    steps.forEach((step) => {
        tasks[step.key] = {
            module: step.module,
            class: step.class,
            params: step.params || {},
        };
        if (step.on_error) tasks[step.key].on_error = step.on_error;
        if (step.enabled !== false) pipeline.push(step.key);
    });
    return { tasks, pipeline };
}

export function buildPipelineYamlPreview(draft) {
    return `${renderYamlValue(redactSecrets(previewDefinition(draft)), 0)}\n`;
}
