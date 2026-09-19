import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
(function () {
    "use strict";

    const state = {
        tasks: [],
        selectedId: null,
        search: "",
        category: "all",
        status: "all",
    };














    const api = createApi(window.DocFlow);
    const { escapeHtml, statusBadge, configuredBadge, matchesFilters, renderSummary, renderCategoryOptions, renderTable, renderParameterList, renderConfiguredParams, formatValue, renderDetail, render } = createView({ state, docFlow: window.DocFlow });
    async function loadCatalog() {
        const body = document.getElementById("task-catalog-body");
        body.innerHTML = '<tr><td colspan="6" class="text-center text-base-content/50 py-10">Loading task catalog...</td></tr>';
        try {
            const payload = await api.load();
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
