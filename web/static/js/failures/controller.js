import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
(function () {
    "use strict";

    const workspace = document.getElementById("failures-workspace");
    if (!workspace) {
        return;
    }

    const tableBody = document.getElementById("failures-table-body");
    const countBadge = document.getElementById("failures-count");
    const detailTitle = document.getElementById("failure-detail-title");
    const detailSubtitle = document.getElementById("failure-detail-subtitle");
    const detailBody = document.getElementById("failure-detail-body");
    const sourceLink = document.getElementById("failure-source-link");
    const state = { failures: [], pdfViewer: null, pageState: { total: 0, limit: 25, offset: 0, sortBy: "failure_at", sortDir: "desc" } };
    const pageState = state.pageState;
    const escapeHtml = window.DocFlow.escapeHtml;
    const titleCase = window.DocFlow.titleCase;








    const api = createApi(window.DocFlow);
    const { formatDateTime, shortText, jsonBlock, renderRows, renderPagination, renderDetail } = createView({ tableBody, countBadge, detailTitle, detailSubtitle, detailBody, sourceLink, state, docFlow: window.DocFlow, pdfRuntime: window.DocFlowPdfViewer });
    async function openFailure(documentId) {
        if (!documentId) {
            return;
        }
        detailTitle.textContent = "Loading failure";
        detailSubtitle.textContent = documentId;
        sourceLink.classList.add("hidden");
        detailBody.innerHTML = '<div class="empty-panel lg:col-span-2"><span class="loading loading-spinner loading-sm"></span> Loading failure detail</div>';
        try {
            const payload = await api.getDetail(documentId);
            renderDetail(payload || {});
        } catch (error) {
            detailBody.innerHTML = `<div class="empty-panel text-error lg:col-span-2">${escapeHtml(error.message || "Unable to load failure")}</div>`;
            window.DocFlow.showToast(error.message || "Unable to load failure", "error");
        }
    }

    async function loadFailures() {
        try {
            const params = new URLSearchParams({
                limit: String(pageState.limit),
                offset: String(pageState.offset),
                sort_by: pageState.sortBy,
                sort_dir: pageState.sortDir,
            });
            const payload = await api.list(params);
            state.failures = Array.isArray(payload.failures) ? payload.failures : [];
            pageState.total = Number(payload.total || 0);
            pageState.limit = Number(payload.limit || pageState.limit);
            pageState.offset = Number(payload.offset || 0);
            renderRows();
            renderPagination();
            const locationParams = new URLSearchParams(window.location.search);
            const requestedDocument = locationParams.get("document_id");
            const first = requestedDocument || (state.failures[0] && state.failures[0].document && state.failures[0].document.id);
            if (first) {
                await openFailure(first);
            }
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="5" class="text-center text-error py-10">${escapeHtml(error.message || "Unable to load failures")}</td></tr>`;
            window.DocFlow.showToast(error.message || "Unable to load failures", "error");
        }
    }

    tableBody.addEventListener("click", (event) => {
        const button = event.target.closest("[data-failure-document]");
        if (!button) {
            return;
        }
        openFailure(button.dataset.failureDocument);
    });

    workspace.addEventListener("click", (event) => {
        const sortButton = event.target.closest("[data-failure-sort]");
        if (!sortButton) {
            return;
        }
        const sortBy = sortButton.dataset.failureSort;
        pageState.sortDir = pageState.sortBy === sortBy && pageState.sortDir === "asc" ? "desc" : "asc";
        pageState.sortBy = sortBy;
        pageState.offset = 0;
        loadFailures();
    });
    document.getElementById("failures-prev").addEventListener("click", () => {
        pageState.offset = Math.max(0, pageState.offset - pageState.limit);
        loadFailures();
    });
    document.getElementById("failures-next").addEventListener("click", () => {
        pageState.offset += pageState.limit;
        loadFailures();
    });

    loadFailures();
})();
