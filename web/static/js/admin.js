(function () {
    "use strict";

    const workspace = document.getElementById("admin-dashboard-workspace");
    if (!workspace) {
        return;
    }

    const state = {
        summary: null,
        settings: null,
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

    function percent(value) {
        const number = Number(value);
        return Number.isFinite(number) ? `${Math.round(number * 100)}%` : "-";
    }

    function renderSummary() {
        const summary = state.summary || {};
        const configHealth = summary.config_health || {};
        const schema = summary.schema_validation || {};
        const pipeline = summary.pipeline || {};
        const reviewGate = summary.review_gate || {};
        const split = summary.split || {};
        const audit = summary.audit || {};
        const versions = summary.config_versions || {};

        document.getElementById("admin-config-health").textContent = configHealth.valid ? "Ready" : "Blocked";
        document.getElementById("admin-config-health").classList.toggle("text-error", !configHealth.valid);
        document.getElementById("admin-config-health").classList.toggle("text-success", Boolean(configHealth.valid));
        document.getElementById("admin-config-summary").textContent = `${configHealth.summary?.errors || 0} errors, ${configHealth.summary?.warnings || 0} warnings`;
        document.getElementById("admin-config-source").textContent = configHealth.source || "Active config";

        document.getElementById("admin-schema-health").textContent = schema.valid ? "Ready" : "Review";
        document.getElementById("admin-schema-summary").textContent = `${schema.summary?.errors || 0} errors, ${schema.summary?.warnings || 0} warnings`;
        document.getElementById("admin-pipeline-health").textContent = String(pipeline.active?.enabled_steps || 0);
        document.getElementById("admin-pipeline-summary").textContent = pipeline.has_draft ? "Draft pending" : "Published pipeline";
        document.getElementById("admin-draft-status").textContent = pipeline.has_draft ? "Draft pending" : "No draft";

        document.getElementById("admin-audit-count").textContent = String(audit.total_admin_events || 0);
        document.getElementById("admin-published-count").textContent = String(versions.published || 0);
        document.getElementById("admin-draft-count").textContent = String(versions.drafts || 0);
        document.getElementById("admin-review-threshold").textContent = percent(reviewGate.confidence_threshold);
        document.getElementById("admin-split-status").textContent = titleCase(split.adapter_status?.status || "unknown");

        renderRecentAudit(audit.recent_events || []);
    }

    function renderRecentAudit(events) {
        const body = document.getElementById("admin-recent-audit-body");
        if (!events.length) {
            body.innerHTML = '<tr><td colspan="3" class="text-center text-base-content/50 py-10">No admin activity</td></tr>';
            return;
        }
        body.innerHTML = events.map((event) => `
            <tr>
                <td class="text-xs">${escapeHtml(window.DocFlow.formatDateTime(event.created_at))}</td>
                <td>${escapeHtml(event.user || "system")}</td>
                <td><span class="badge badge-sm badge-outline">${escapeHtml(event.event_type)}</span></td>
            </tr>
        `).join("");
    }

    function renderSettings() {
        const payload = state.settings || {};
        const groups = payload.groups || [];
        document.getElementById("admin-settings-count").textContent = `${Object.keys(payload.settings || {}).length} keys`;
        const container = document.getElementById("admin-settings-groups");
        if (!groups.length) {
            container.innerHTML = '<div class="empty-panel">No editable settings</div>';
            return;
        }
        container.innerHTML = groups.map((group) => `
            <section class="admin-settings-group">
                <div>
                    <h3 class="font-semibold text-sm">${escapeHtml(titleCase(group.name))}</h3>
                    <p class="text-xs text-base-content/50">Editable allow-listed values</p>
                </div>
                <div class="admin-settings-grid">
                    ${(group.settings || []).map((setting) => settingInput(setting)).join("")}
                </div>
            </section>
        `).join("");
    }

    function settingInput(setting) {
        const key = escapeHtml(setting.key);
        const label = escapeHtml(setting.label);
        const type = escapeHtml(setting.type);
        if (setting.type === "bool") {
            return `
                <label class="form-control admin-setting-control bg-base-200/60 rounded-lg p-3">
                    <span class="label-text mb-2">${label}</span>
                    <input class="toggle toggle-sm" data-admin-setting-key="${key}" data-admin-setting-type="${type}"
                        type="checkbox" ${setting.value ? "checked" : ""}>
                </label>
            `;
        }
        const inputType = setting.type === "positive_int" ? "number" : "text";
        return `
            <label class="form-control admin-setting-control bg-base-200/60 rounded-lg p-3">
                <span class="label-text mb-2">${label}</span>
                <input class="input input-bordered input-sm w-full" data-admin-setting-key="${key}" data-admin-setting-type="${type}"
                    type="${inputType}" value="${escapeHtml(setting.value || "")}">
            </label>
        `;
    }

    function readSettings() {
        const settings = {};
        workspace.querySelectorAll("[data-admin-setting-key]").forEach((input) => {
            const key = input.dataset.adminSettingKey;
            const type = input.dataset.adminSettingType;
            if (type === "bool") {
                settings[key] = input.checked;
            } else if (type === "positive_int") {
                settings[key] = Number(input.value || 0);
            } else {
                settings[key] = input.value;
            }
        });
        return settings;
    }

    async function loadSummary() {
        state.summary = await window.DocFlow.apiGet("/api/admin/summary");
        renderSummary();
    }

    async function loadSettings() {
        state.settings = await window.DocFlow.apiGet("/api/admin/settings");
        renderSettings();
    }

    async function loadDashboard() {
        const results = await Promise.allSettled([
            loadSummary(),
            loadSettings(),
        ]);
        const failure = results.find((result) => result.status === "rejected");
        if (failure) {
            throw failure.reason;
        }
    }

    async function saveSettings() {
        state.settings = await window.DocFlow.apiPut("/api/admin/settings", { settings: readSettings() });
        renderSettings();
        state.summary = await window.DocFlow.apiGet("/api/admin/summary");
        renderSummary();
        window.DocFlow.showToast("Settings saved", "success");
    }

    document.getElementById("admin-refresh-button").addEventListener("click", () => {
        loadDashboard().catch((error) => window.DocFlow.showToast(error.message || "Unable to load admin summary", "error"));
    });
    document.getElementById("admin-save-settings-button").addEventListener("click", () => {
        saveSettings().catch((error) => window.DocFlow.showToast(error.message || "Unable to save settings", "error"));
    });

    loadDashboard().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load admin dashboard", "error");
    });
})();
