import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
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










    const api = createApi(window.DocFlow);
    const { escapeHtml, titleCase, percent, renderSummary, renderRecentAudit, renderSettings, settingInput, readSettings } = createView({ state, docFlow: window.DocFlow });
    async function loadSummary() {
        state.summary = await api.getSummary();
        renderSummary();
    }

    async function loadSettings() {
        state.settings = await api.getSettings();
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
        state.settings = await api.saveSettings(readSettings());
        renderSettings();
        state.summary = await api.getSummary();
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
