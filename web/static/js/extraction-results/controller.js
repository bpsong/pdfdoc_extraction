import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
(function () {
    "use strict";

    const workspace = document.getElementById("extraction-results-workspace");
    if (!workspace) {
        return;
    }

    const documentId = workspace.dataset.documentId || "";
    const title = document.getElementById("extraction-document-title");
    const statusLabel = document.getElementById("extraction-document-status");
    const previewBody = document.getElementById("extraction-preview-body");
    const fileList = document.getElementById("extraction-file-list");
    const tableBody = document.getElementById("extraction-fields-table-body");
    const jobLabel = document.getElementById("extraction-job-label");
    const providerLabel = document.getElementById("extraction-provider-label");
    const rawPayload = document.getElementById("extraction-raw-payload");
    const reviewLink = document.getElementById("extraction-review-link");
    const reviewSummary = document.getElementById("extraction-review-summary");
    const previousButton = document.getElementById("previous-document-button");
    const nextButton = document.getElementById("next-document-button");















    const api = createApi(window.DocFlow);
    const { escapeHtml, titleCase, formatValue, statusBadge, confidenceBadge, nestedConfidenceSummary, renderPreview, renderFiles, effectiveReviewStatus, renderFields, wireSiblingButtons, renderPayload } = createView({ documentId, title, statusLabel, previewBody, fileList, tableBody, jobLabel, providerLabel, rawPayload, reviewLink, reviewSummary, previousButton, nextButton, docFlow: window.DocFlow, pdfRuntime: window.DocFlowPdfViewer });
    async function loadExtraction() {
        if (!documentId) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-error py-10">No document selected</td></tr>';
            return;
        }
        try {
            const payload = await api.getDocument(documentId);
            renderPayload(payload);
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="5" class="text-center text-error py-10">${escapeHtml(error.message || "Unable to load extraction")}</td></tr>`;
            previewBody.innerHTML = '<div class="empty-panel">Preview unavailable</div>';
            if (window.DocFlow) {
                window.DocFlow.showToast(error.message || "Unable to load extraction", "error");
            }
        }
    }

    loadExtraction();
})();
