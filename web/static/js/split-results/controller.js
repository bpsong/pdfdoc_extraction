import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
(function () {
    "use strict";

    const workspace = document.getElementById("split-results-workspace");
    if (!workspace) {
        return;
    }

    const batchId = workspace.dataset.batchId || "";
    const tableBody = document.getElementById("split-results-table-body");
    const totalFiles = document.getElementById("split-total-files");
    const documentsCreated = document.getElementById("split-documents-created");
    const successful = document.getElementById("split-successful");
    const failed = document.getElementById("split-failed");









    const api = createApi(window.DocFlow);
    const { escapeHtml, titleCase, statusBadge, pageLabel, renderSummary, childRows, renderSources } = createView({ tableBody, totalFiles, documentsCreated, successful, failed, docFlow: window.DocFlow });
    async function loadSplitResults() {
        if (!batchId) {
            tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-base-content/50 py-10">No batch selected</td></tr>';
            return;
        }

        try {
            const payload = await api.getBatch(batchId);
            renderSummary(payload.summary || {});
            renderSources(payload.sources || []);
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-error py-10">${escapeHtml(error.message || "Unable to load split results")}</td></tr>`;
            if (window.DocFlow) {
                window.DocFlow.showToast(error.message || "Unable to load split results", "error");
            }
        }
    }

    loadSplitResults();
})();
