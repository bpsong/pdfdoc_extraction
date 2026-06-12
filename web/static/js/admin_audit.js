(function () {
    "use strict";

    const workspace = document.getElementById("admin-audit-workspace");
    if (!workspace) {
        return;
    }

    const state = {
        events: [],
        selectedId: null,
    };

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function queryString() {
        const params = new URLSearchParams();
        const values = {
            event_type: document.getElementById("admin-audit-event-type").value.trim(),
            user: document.getElementById("admin-audit-user").value.trim(),
            created_from: document.getElementById("admin-audit-created-from").value,
            created_to: document.getElementById("admin-audit-created-to").value,
            limit: "100",
        };
        Object.entries(values).forEach(([key, value]) => {
            if (value) {
                params.set(key, value);
            }
        });
        const text = params.toString();
        return text ? `?${text}` : "";
    }

    function targetLabel(event) {
        if (event.document_id) {
            return `document ${event.document_id}`;
        }
        if (event.review_item_id) {
            return `review ${event.review_item_id}`;
        }
        if (event.batch_id) {
            return `batch ${event.batch_id}`;
        }
        return "admin";
    }

    function renderTable() {
        const body = document.getElementById("admin-audit-body");
        if (!state.events.length) {
            body.innerHTML = '<tr><td colspan="5" class="text-center text-base-content/50 py-4">No admin audit events match these filters.</td></tr>';
            renderDetail(null);
            return;
        }
        body.innerHTML = state.events.map((event) => `
            <tr class="${event.id === state.selectedId ? "active" : ""}">
                <td class="text-xs">${escapeHtml(window.DocFlow.formatDateTime(event.created_at))}</td>
                <td>${escapeHtml(event.user || "system")}</td>
                <td><span class="badge badge-sm badge-outline">${escapeHtml(event.event_type)}</span></td>
                <td class="font-mono text-xs">${escapeHtml(targetLabel(event))}</td>
                <td class="text-right">
                    <button class="btn btn-ghost btn-xs" data-audit-id="${escapeHtml(event.id)}" type="button">Details</button>
                </td>
            </tr>
        `).join("");
    }

    function renderDetail(event) {
        document.getElementById("admin-audit-detail-title").textContent = event ? event.event_type : "Event Details";
        document.getElementById("admin-audit-detail-subtitle").textContent = event
            ? `${event.user || "system"} - ${window.DocFlow.formatDateTime(event.created_at)}`
            : "Select an event";
        document.getElementById("admin-audit-detail-json").textContent = event
            ? JSON.stringify(event, null, 2)
            : "Select an audit event to view details.";
    }

    function renderEventTypeOptions() {
        const datalist = document.getElementById("admin-audit-event-types");
        const types = [...new Set(state.events.map((event) => event.event_type).filter(Boolean))].sort();
        datalist.innerHTML = types.map((type) => `<option value="${escapeHtml(type)}"></option>`).join("");
    }

    async function loadAudit() {
        const payload = await window.DocFlow.apiGet(`/api/admin/audit${queryString()}`);
        state.events = payload.events || [];
        state.selectedId = state.events[0] ? state.events[0].id : null;
        renderEventTypeOptions();
        renderTable();
        renderDetail(state.events[0] || null);
    }

    function clearFilters() {
        ["admin-audit-event-type", "admin-audit-user", "admin-audit-created-from", "admin-audit-created-to"].forEach((id) => {
            document.getElementById(id).value = "";
        });
        loadAudit().catch((error) => window.DocFlow.showToast(error.message || "Unable to load audit events", "error"));
    }

    document.getElementById("admin-audit-refresh-button").addEventListener("click", () => {
        loadAudit().catch((error) => window.DocFlow.showToast(error.message || "Unable to load audit events", "error"));
    });
    document.getElementById("admin-audit-apply-button").addEventListener("click", () => {
        loadAudit().catch((error) => window.DocFlow.showToast(error.message || "Unable to load audit events", "error"));
    });
    document.getElementById("admin-audit-clear-button").addEventListener("click", clearFilters);
    workspace.addEventListener("click", (event) => {
        const button = event.target.closest("[data-audit-id]");
        if (!button) {
            return;
        }
        state.selectedId = button.dataset.auditId;
        const selected = state.events.find((item) => item.id === state.selectedId) || null;
        renderTable();
        renderDetail(selected);
    });

    loadAudit().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load audit events", "error");
    });
})();
