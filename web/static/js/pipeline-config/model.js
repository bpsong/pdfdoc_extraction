/** Pure transformations for versioned pipeline definitions. */

export function clone(value) {
    return JSON.parse(JSON.stringify(value || {}));
}

export function stepsOf(model) {
    return Array.isArray(model && model.steps) ? model.steps : [];
}

export function taskKind(step) {
    const moduleName = String(step && step.module || "");
    const className = String(step && step.class || "");
    if (className === "LlamaCloudSplitTask" || moduleName.includes(".split.")) return "split";
    if (className === "ExtractPdfTask" || moduleName.includes(".extraction.")) return "extract";
    if (className === "ReviewGateTask" || moduleName.includes(".review.")) return "review";
    if (moduleName.includes(".storage.")) return "storage";
    if (moduleName.includes(".rules.")) return "rules";
    if (moduleName.includes(".archiver.")) return "archive";
    if (moduleName.includes(".context.")) return "context";
    if (moduleName.includes(".housekeeping.") || className === "CleanupTask") return "housekeeping";
    return "task";
}

export function withoutHousekeeping(model) {
    const copy = clone(model || { steps: [] });
    copy.steps = stepsOf(copy).filter((step) => taskKind(step) !== "housekeeping");
    return copy;
}

export function stepType(step) {
    const moduleName = String(step && step.module || "");
    const className = String(step && step.class || "");
    if (moduleName.includes(".extraction.") || className === "ExtractPdfTask") return "extract";
    if (moduleName.includes(".split.") || className === "LlamaCloudSplitTask") return "split";
    if (moduleName === "standard_step.review.review_gate" || className === "ReviewGateTask") return "review";
    return "optional";
}

export function summaryText(model) {
    const steps = stepsOf(model);
    const enabled = steps.filter((step) => step.enabled !== false).length;
    return `${enabled}/${steps.length} enabled`;
}

export function definitionToModel(definition) {
    const pipeline = Array.isArray(definition && definition.pipeline) ? definition.pipeline : [];
    const tasks = definition && typeof definition.tasks === "object" ? definition.tasks : {};
    const enabledKeys = new Set(pipeline);
    const fallbackKeys = [...pipeline, ...Object.keys(tasks).filter((key) => !enabledKeys.has(key))];
    const editorOrder = definition && definition.editor_order;
    // Presentation metadata must never override the executable pipeline order.
    const validOrder = Array.isArray(editorOrder)
        && editorOrder.length === fallbackKeys.length
        && new Set(editorOrder).size === editorOrder.length
        && editorOrder.every((key) => fallbackKeys.includes(key))
        && JSON.stringify(editorOrder.filter((key) => enabledKeys.has(key))) === JSON.stringify(pipeline);
    const orderedKeys = validOrder ? editorOrder : fallbackKeys;
    return {
        steps: orderedKeys.map((key) => ({
            key,
            enabled: enabledKeys.has(key),
            ...clone(tasks[key] || {}),
        })),
    };
}

export function modelToDefinition(model) {
    const tasks = {};
    const pipeline = [];
    stepsOf(model).forEach((step) => {
        const copy = clone(step);
        const key = copy.key;
        delete copy.key;
        const enabled = copy.enabled !== false;
        delete copy.enabled;
        tasks[key] = copy;
        if (enabled) pipeline.push(key);
    });
    return { schema_version: 1, pipeline, tasks, editor_order: stepsOf(model).map((step) => step.key) };
}
