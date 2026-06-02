(function () {
    "use strict";

    const workspace = document.getElementById("split-settings-workspace");
    if (!workspace) {
        return;
    }

    const state = {
        settings: {},
        taskKey: "",
        source: "",
        adapterStatus: {},
    };

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function titleCase(value) {
        return String(value || "")
            .replace(/_/g, " ")
            .replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function categoryRows(categories) {
        if (!Array.isArray(categories) || !categories.length) {
            return `<tr><td colspan="3" class="text-center text-base-content/50 py-8">No categories</td></tr>`;
        }
        return categories.map((category, index) => `
            <tr data-category-row data-index="${index}">
                <td>
                    <input class="input input-bordered input-sm w-full" data-category-name
                        value="${escapeHtml(category.name || "")}">
                </td>
                <td>
                    <input class="input input-bordered input-sm w-full" data-category-description
                        value="${escapeHtml(category.description || "")}">
                </td>
                <td class="text-right">
                    <button class="btn btn-ghost btn-xs text-error" data-remove-category="${index}" type="button">Remove</button>
                </td>
            </tr>
        `).join("");
    }

    function readCategories() {
        return Array.from(workspace.querySelectorAll("[data-category-row]"))
            .map((row) => {
                const name = row.querySelector("[data-category-name]");
                const description = row.querySelector("[data-category-description]");
                return {
                    name: name ? name.value.trim() : "",
                    description: description ? description.value.trim() : "",
                };
            })
            .filter((category) => category.name);
    }

    function readSettings() {
        return {
            enabled: document.getElementById("split-settings-enabled").checked,
            categories: readCategories(),
            allow_uncategorized: document.getElementById("split-settings-allow-uncategorized").value,
            split_dir: document.getElementById("split-settings-split-dir").value.trim(),
            configuration_id: document.getElementById("split-settings-configuration-id").value.trim(),
            project_id: document.getElementById("split-settings-project-id").value.trim(),
            organization_id: document.getElementById("split-settings-organization-id").value.trim(),
            poll_interval_seconds: Number(document.getElementById("split-settings-poll-interval").value || 1),
            timeout_seconds: Number(document.getElementById("split-settings-timeout").value || 7200),
        };
    }

    function statusBadge(status) {
        const normalized = String(status || "unknown");
        const badgeClass = normalized === "ready"
            ? "badge-success"
            : normalized === "disabled"
                ? "badge-ghost"
                : "badge-warning";
        return `<span class="badge ${badgeClass} badge-sm">${escapeHtml(titleCase(normalized))}</span>`;
    }

    function renderSummary() {
        const settings = state.settings || {};
        const status = state.adapterStatus || {};
        document.getElementById("split-settings-task-key").textContent = state.taskKey || "No task";
        document.getElementById("split-settings-source").textContent = titleCase(state.source || "app_settings");
        document.getElementById("split-settings-enabled-summary").textContent = settings.enabled ? "Enabled" : "Disabled";
        document.getElementById("split-settings-category-summary").textContent = `${(settings.categories || []).length} categories`;
        document.getElementById("split-settings-adapter-summary").innerHTML = statusBadge(status.status);
        document.getElementById("split-settings-secret-summary").textContent = settings.api_key_configured ? "API key configured" : "No API key";
        document.getElementById("split-settings-connection-summary").innerHTML = statusBadge(status.status);
        document.getElementById("split-settings-connection-message").textContent = status.message || "-";
    }

    function renderStatus() {
        const settings = state.settings || {};
        const status = state.adapterStatus || {};
        const alert = document.getElementById("split-settings-status-alert");
        alert.className = `alert text-sm ${status.ok ? "alert-success" : status.status === "disabled" ? "" : "alert-warning"}`;
        alert.textContent = status.message || "No adapter status";
        document.getElementById("split-settings-api-key-state").textContent = settings.api_key_configured ? "Configured" : "Missing";
        document.getElementById("split-settings-network-state").textContent = status.network_checked ? "Checked" : "Not checked";
    }

    function renderForm() {
        const settings = state.settings || {};
        document.getElementById("split-settings-enabled").checked = Boolean(settings.enabled);
        document.getElementById("split-settings-allow-uncategorized").value = settings.allow_uncategorized || "include";
        document.getElementById("split-settings-split-dir").value = settings.split_dir || "data/app/split";
        document.getElementById("split-settings-configuration-id").value = settings.configuration_id || "";
        document.getElementById("split-settings-project-id").value = settings.project_id || "";
        document.getElementById("split-settings-organization-id").value = settings.organization_id || "";
        document.getElementById("split-settings-poll-interval").value = settings.poll_interval_seconds || 1;
        document.getElementById("split-settings-timeout").value = settings.timeout_seconds || 7200;
        document.getElementById("split-settings-category-body").innerHTML = categoryRows(settings.categories || []);
    }

    function render() {
        renderSummary();
        renderStatus();
        renderForm();
    }

    async function loadSettings() {
        const payload = await window.DocFlow.apiGet("/api/admin/split-settings");
        state.settings = payload.settings || {};
        state.taskKey = payload.task_key || "";
        state.source = payload.source || "";
        state.adapterStatus = payload.adapter_status || {};
        render();
    }

    async function saveSettings() {
        const payload = await window.DocFlow.apiPut("/api/admin/split-settings", { settings: readSettings() });
        state.settings = payload.settings || {};
        state.taskKey = payload.task_key || "";
        state.source = payload.source || "";
        state.adapterStatus = payload.adapter_status || {};
        render();
        window.DocFlow.showToast("Split settings saved", "success");
    }

    async function testConnection() {
        const status = await window.DocFlow.apiPost("/api/admin/split-settings/test-connection", {});
        state.adapterStatus = status || {};
        renderSummary();
        renderStatus();
        window.DocFlow.showToast("Split connection check completed", status.ok ? "success" : "warning");
    }

    function addCategory() {
        state.settings = readSettings();
        state.settings.categories.push({ name: "invoice", description: "" });
        render();
    }

    function removeCategory(index) {
        state.settings = readSettings();
        state.settings.categories.splice(index, 1);
        render();
    }

    document.getElementById("split-settings-refresh-button").addEventListener("click", () => {
        loadSettings().catch((error) => window.DocFlow.showToast(error.message || "Unable to load split settings", "error"));
    });
    document.getElementById("split-settings-save-button").addEventListener("click", () => {
        saveSettings().catch((error) => window.DocFlow.showToast(error.message || "Unable to save split settings", "error"));
    });
    document.getElementById("split-settings-test-button").addEventListener("click", () => {
        testConnection().catch((error) => window.DocFlow.showToast(error.message || "Unable to test split settings", "error"));
    });
    document.getElementById("split-settings-add-category").addEventListener("click", addCategory);
    workspace.addEventListener("click", (event) => {
        const button = event.target.closest("[data-remove-category]");
        if (button) {
            removeCategory(Number(button.dataset.removeCategory));
        }
    });

    loadSettings().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load split settings", "error");
    });
})();
