(function () {
    "use strict";

    const state = {
        tasks: [],
        selectedId: null,
        search: "",
        category: "all",
        status: "all",
    };

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function statusBadge(task) {
        if (task.import_status === "ok") {
            return '<span class="badge badge-success badge-sm">OK</span>';
        }
        return '<span class="badge badge-error badge-sm">Failed</span>';
    }

    function configuredBadge(task) {
        if (!task.is_configured) {
            return '<span class="badge badge-ghost badge-sm">Not in pipeline</span>';
        }
        return (task.configured_keys || [])
            .map((key) => `<span class="badge badge-primary badge-sm">${escapeHtml(key)}</span>`)
            .join(" ");
    }

    function matchesFilters(task) {
        if (state.category !== "all" && task.category !== state.category) {
            return false;
        }
        if (state.status === "configured" && !task.is_configured) {
            return false;
        }
        if (state.status !== "all" && state.status !== "configured" && task.import_status !== state.status) {
            return false;
        }
        if (!state.search) {
            return true;
        }
        const haystack = [
            task.label,
            task.category,
            task.module,
            task.class_name,
            task.docstring_summary,
            ...(task.configured_keys || []),
        ].join(" ").toLowerCase();
        return haystack.includes(state.search.toLowerCase());
    }

    function renderSummary(summary) {
        document.getElementById("task-catalog-total").textContent = String(summary.total || 0);
        document.getElementById("task-catalog-configured").textContent = String(summary.configured || 0);
        document.getElementById("task-catalog-available").textContent = String(summary.available || 0);
        document.getElementById("task-catalog-failed").textContent = String(summary.failed || 0);
    }

    function renderCategoryOptions() {
        const select = document.getElementById("task-catalog-category");
        const categories = [...new Set(state.tasks.map((task) => task.category).filter(Boolean))].sort();
        select.innerHTML = '<option value="all">All categories</option>' + categories
            .map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`)
            .join("");
        select.value = state.category;
    }

    function renderTable() {
        const body = document.getElementById("task-catalog-body");
        const tasks = state.tasks
            .filter(matchesFilters)
            .sort((a, b) => {
                if (a.import_status !== b.import_status) {
                    return a.import_status === "failed" ? -1 : 1;
                }
                return String(a.label || "").localeCompare(String(b.label || ""));
            });
        if (!tasks.length) {
            body.innerHTML = '<tr><td colspan="6" class="text-center text-base-content/50 py-10">No matching tasks</td></tr>';
            return;
        }
        body.innerHTML = tasks.map((task) => `
            <tr class="hover cursor-pointer ${task.id === state.selectedId ? "bg-primary/10" : ""}" data-task-id="${escapeHtml(task.id)}">
                <td class="px-4 py-3">
                    <div class="font-medium text-primary">${escapeHtml(task.label)}</div>
                    <div class="text-xs text-base-content/50">${escapeHtml(task.docstring_summary || "No summary available")}</div>
                </td>
                <td>${escapeHtml(task.category)}</td>
                <td class="font-mono text-xs">${escapeHtml(task.module)}</td>
                <td class="font-mono text-xs">${escapeHtml(task.class_name)}</td>
                <td>${statusBadge(task)}</td>
                <td>${configuredBadge(task)}</td>
            </tr>
        `).join("");

        body.querySelectorAll("[data-task-id]").forEach((row) => {
            row.addEventListener("click", () => {
                state.selectedId = row.dataset.taskId;
                renderTable();
                renderDetail();
            });
        });
    }

    function renderParameterList(parameters) {
        if (!parameters || !parameters.length) {
            return '<div class="text-sm text-base-content/50">No explicit constructor parameters discovered.</div>';
        }
        return `
            <div class="overflow-x-auto">
                <table class="table table-xs">
                    <thead><tr><th>Name</th><th>Required</th><th>Default</th></tr></thead>
                    <tbody>
                        ${parameters.map((parameter) => `
                            <tr>
                                <td class="font-mono">${escapeHtml(parameter.name)}</td>
                                <td>${parameter.required ? '<span class="badge badge-warning badge-xs">Required</span>' : '<span class="badge badge-ghost badge-xs">Optional</span>'}</td>
                                <td class="font-mono text-xs">${escapeHtml(formatValue(parameter.default))}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function renderConfiguredParams(task) {
        const params = task.configured_params || {};
        const keys = Object.keys(params);
        if (!keys.length) {
            return '<div class="text-sm text-base-content/50">This task is not configured in the active pipeline.</div>';
        }
        return keys.map((key) => `
            <div class="collapse collapse-arrow bg-base-200">
                <input type="checkbox" />
                <div class="collapse-title text-sm font-medium">${escapeHtml(key)}</div>
                <div class="collapse-content">
                    <pre class="task-catalog-json">${escapeHtml(JSON.stringify(params[key], null, 2))}</pre>
                </div>
            </div>
        `).join("");
    }

    function formatValue(value) {
        if (value === null || value === undefined) {
            return "";
        }
        if (typeof value === "object") {
            return JSON.stringify(value);
        }
        return String(value);
    }

    function renderDetail() {
        const task = state.tasks.find((candidate) => candidate.id === state.selectedId);
        const title = document.getElementById("task-detail-title");
        const subtitle = document.getElementById("task-detail-subtitle");
        const body = document.getElementById("task-detail-body");
        if (!task) {
            title.textContent = "Task Details";
            subtitle.textContent = "Select a task to inspect metadata.";
            body.innerHTML = '<div class="empty-panel">No task selected</div>';
            return;
        }

        title.textContent = task.label;
        subtitle.textContent = `${task.module}.${task.class_name}`;
        body.innerHTML = `
            <div class="flex flex-wrap gap-2">
                ${statusBadge(task)}
                ${task.is_configured ? '<span class="badge badge-primary badge-sm">Configured</span>' : '<span class="badge badge-outline badge-sm">Available</span>'}
                <span class="badge badge-ghost badge-sm">${escapeHtml(task.category)}</span>
                ${task.import_status === "ok" ? '<a class="btn btn-outline btn-xs ml-auto" href="/app/admin/pipeline">Add in Pipeline</a>' : ""}
            </div>
            ${task.import_error ? `<div class="alert alert-error text-sm"><span>${escapeHtml(task.import_error)}</span></div>` : ""}
            <div>
                <h3 class="font-semibold text-sm mb-1">Summary</h3>
                <p class="text-sm text-base-content/70">${escapeHtml(task.docstring_summary || "No summary available.")}</p>
            </div>
            <div>
                <h3 class="font-semibold text-sm mb-2">Expected Inputs</h3>
                <div class="flex flex-wrap gap-1">${(task.expected_inputs || []).length ? (task.expected_inputs || []).map((item) => `<span class="badge badge-outline badge-sm">${escapeHtml(item)}</span>`).join("") : '<span class="text-sm text-base-content/50">No declared inputs.</span>'}</div>
            </div>
            <div>
                <h3 class="font-semibold text-sm mb-2">Expected Outputs</h3>
                <div class="flex flex-wrap gap-1">${(task.expected_outputs || []).length ? (task.expected_outputs || []).map((item) => `<span class="badge badge-outline badge-sm">${escapeHtml(item)}</span>`).join("") : '<span class="text-sm text-base-content/50">No declared outputs.</span>'}</div>
            </div>
            <div>
                <h3 class="font-semibold text-sm mb-2">Constructor Parameters</h3>
                ${renderParameterList(task.parameters)}
            </div>
            <div>
                <h3 class="font-semibold text-sm mb-2">Configured Parameters</h3>
                <div class="flex flex-col gap-2">${renderConfiguredParams(task)}</div>
            </div>
        `;
    }

    function render(payload) {
        renderSummary(payload.summary || {});
        renderCategoryOptions();
        renderTable();
        renderDetail();
    }

    async function loadCatalog() {
        const body = document.getElementById("task-catalog-body");
        body.innerHTML = '<tr><td colspan="6" class="text-center text-base-content/50 py-10">Loading task catalog...</td></tr>';
        try {
            const payload = await window.DocFlow.apiGet("/api/admin/task-catalog");
            state.tasks = payload.tasks || [];
            render(payload);
        } catch (error) {
            body.innerHTML = '<tr><td colspan="6" class="text-center text-error py-10">Task catalog failed to load</td></tr>';
            window.DocFlow.showToast(error.message || "Task catalog failed to load", "error");
        }
    }

    function bindEvents() {
        document.getElementById("task-catalog-refresh").addEventListener("click", loadCatalog);
        document.getElementById("task-catalog-search").addEventListener("input", (event) => {
            state.search = event.target.value || "";
            renderTable();
        });
        document.getElementById("task-catalog-category").addEventListener("change", (event) => {
            state.category = event.target.value || "all";
            renderTable();
        });
        document.getElementById("task-catalog-status").addEventListener("change", (event) => {
            state.status = event.target.value || "all";
            renderTable();
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        if (!document.getElementById("task-catalog-workspace")) {
            return;
        }
        bindEvents();
        loadCatalog();
    });
})();
