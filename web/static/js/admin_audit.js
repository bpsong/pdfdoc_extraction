(function () {
    "use strict";

    const workspace = document.getElementById("admin-audit-workspace");
    if (!workspace) {
        return;
    }

    const state = {
        events: [],
        selectedId: null,
        total: 0,
        limit: 25,
        offset: 0,
        sortBy: "created_at",
        sortDir: "desc",
    };
    const escapeHtml = window.DocFlow.escapeHtml;

    function queryString() {
        const params = new URLSearchParams();
        const values = {
            event_type: document.getElementById("admin-audit-event-type").value.trim(),
            user: document.getElementById("admin-audit-user").value.trim(),
            created_from: document.getElementById("admin-audit-created-from").value,
            created_to: document.getElementById("admin-audit-created-to").value,
            limit: String(state.limit),
            offset: String(state.offset),
            sort_by: state.sortBy,
            sort_dir: state.sortDir,
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
                <td class="text-xs">${window.DocFlow.escapeHtml(window.DocFlow.formatDateTime(event.created_at))}</td>
                <td>${escapeHtml(event.user || "system")}</td>
                <td><span class="badge badge-sm badge-outline">${escapeHtml(event.event_type)}</span></td>
                <td class="font-mono text-xs">${escapeHtml(targetLabel(event))}</td>
                <td class="text-right">
                    <button class="btn btn-ghost btn-xs" data-audit-id="${escapeHtml(event.id)}" type="button">Details</button>
                </td>
            </tr>
        `).join("");
    }

    function renderPagination() {
        const start = state.total ? state.offset + 1 : 0;
        const end = Math.min(state.offset + state.events.length, state.total);
        document.getElementById("admin-audit-page-summary").textContent = `${start}-${end} of ${state.total}`;
        document.getElementById("admin-audit-prev").disabled = state.offset === 0;
        document.getElementById("admin-audit-next").disabled = state.offset + state.limit >= state.total;
        document.querySelectorAll("[data-audit-sort]").forEach((button) => {
            const active = button.dataset.auditSort === state.sortBy;
            button.setAttribute("aria-sort", active ? (state.sortDir === "asc" ? "ascending" : "descending") : "none");
            button.querySelector("span").textContent = active ? (state.sortDir === "asc" ? "↑" : "↓") : "";
        });
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
        state.total = Number(payload.total || 0);
        state.limit = Number(payload.limit || state.limit);
        state.offset = Number(payload.offset || 0);
        state.selectedId = state.events[0] ? state.events[0].id : null;
        renderEventTypeOptions();
        renderTable();
        renderDetail(state.events[0] || null);
        renderPagination();
    }

    function clearFilters() {
        ["admin-audit-event-type", "admin-audit-user", "admin-audit-created-from", "admin-audit-created-to"].forEach((id) => {
            document.getElementById(id).value = "";
        });
        state.offset = 0;
        loadAudit().catch((error) => window.DocFlow.showToast(error.message || "Unable to load audit events", "error"));
    }

    document.getElementById("admin-audit-refresh-button").addEventListener("click", () => {
        loadAudit().catch((error) => window.DocFlow.showToast(error.message || "Unable to load audit events", "error"));
    });
    document.getElementById("admin-audit-apply-button").addEventListener("click", () => {
        state.offset = 0;
        loadAudit().catch((error) => window.DocFlow.showToast(error.message || "Unable to load audit events", "error"));
    });
    document.getElementById("admin-audit-clear-button").addEventListener("click", clearFilters);
    workspace.addEventListener("click", (event) => {
        const sortButton = event.target.closest("[data-audit-sort]");
        if (sortButton) {
            const sortBy = sortButton.dataset.auditSort;
            state.sortDir = state.sortBy === sortBy && state.sortDir === "asc" ? "desc" : "asc";
            state.sortBy = sortBy;
            state.offset = 0;
            loadAudit().catch((error) => window.DocFlow.showToast(error.message || "Unable to sort audit events", "error"));
            return;
        }
        const button = event.target.closest("[data-audit-id]");
        if (!button) {
            return;
        }
        state.selectedId = button.dataset.auditId;
        const selected = state.events.find((item) => item.id === state.selectedId) || null;
        renderTable();
        renderDetail(selected);
    });
    document.getElementById("admin-audit-prev").addEventListener("click", () => {
        state.offset = Math.max(0, state.offset - state.limit);
        loadAudit().catch((error) => window.DocFlow.showToast(error.message || "Unable to load audit events", "error"));
    });
    document.getElementById("admin-audit-next").addEventListener("click", () => {
        state.offset += state.limit;
        loadAudit().catch((error) => window.DocFlow.showToast(error.message || "Unable to load audit events", "error"));
    });

    loadAudit().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load audit events", "error");
    });
})();
