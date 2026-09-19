import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
(function () {
    "use strict";

    const workspace = document.getElementById("settings-workspace");
    if (!workspace) {
        return;
    }












    const api = createApi(window.DocFlow);
    const { escapeHtml, titleCase, percent, displayValue, tableRows, renderSummary, renderPaths, renderReview, renderPipeline, render } = createView({ docFlow: window.DocFlow });
    async function loadSettings() {
        const payload = await api.load();
        render(payload || {});
    }

    document.getElementById("settings-refresh-button").addEventListener("click", () => {
        loadSettings().catch((error) => window.DocFlow.showToast(error.message || "Unable to load settings", "error"));
    });

    loadSettings().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load settings", "error");
    });
})();
