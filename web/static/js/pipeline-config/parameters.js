/** Browser-independent helpers for nested pipeline task parameters. */

export function getParam(params, path, fallback) {
    let current = params || {};
    for (const segment of path) {
        if (!current || typeof current !== "object" || !(segment in current)) return fallback;
        current = current[segment];
    }
    return current === undefined ? fallback : current;
}

export function setParam(params, path, value) {
    if (!path.length) return;
    let current = params;
    path.slice(0, -1).forEach((segment, index) => {
        if (!current[segment] || typeof current[segment] !== "object") {
            current[segment] = typeof path[index + 1] === "number" ? [] : {};
        }
        current = current[segment];
    });
    current[path[path.length - 1]] = value;
}

export function deleteParam(params, path) {
    if (!path.length) return;
    let current = params;
    path.slice(0, -1).forEach((segment) => {
        current = current && current[segment];
    });
    if (current && typeof current === "object") delete current[path[path.length - 1]];
}
