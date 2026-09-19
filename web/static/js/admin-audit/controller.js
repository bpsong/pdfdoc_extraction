import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
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







    const api = createApi(window.DocFlow);
    const { targetLabel, renderTable, renderPagination, renderDetail, renderEventTypeOptions } = createView({ state, docFlow: window.DocFlow });
    async function loadAudit() {
        const payload = await api.list(queryString());
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
