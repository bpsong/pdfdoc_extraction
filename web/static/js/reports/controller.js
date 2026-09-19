import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
(function () {
    "use strict";

    const workspace = document.getElementById("reports-workspace");
    if (!workspace) {
        return;
    }

    const batchModal = document.getElementById("batch-detail-modal");
    const batchDetailTitle = document.getElementById("batch-detail-title");
    const batchDetailSubtitle = document.getElementById("batch-detail-subtitle");
    const batchDetailBody = document.getElementById("batch-detail-body");
    const batchDetailProcessingLink = document.getElementById("batch-detail-processing-link");

















    const api = createApi(window.DocFlow);
    const { escapeHtml, titleCase, statusBadge, workflowState, formatDuration, formatDateTime, safeJsonBlock, renderMetric, renderSimpleRows, renderSourceRows, renderRecentBatches, renderBatchSummary, renderTaskRows, renderDocumentDetails, renderBatchDetails, render } = createView({ batchDetailTitle, batchDetailSubtitle, batchDetailBody, batchDetailProcessingLink, docFlow: window.DocFlow });
    async function openBatchDetails(batchId) {
        if (!batchModal || !batchId) {
            return;
        }
        batchDetailTitle.textContent = "Loading batch details";
        batchDetailSubtitle.textContent = batchId;
        batchDetailProcessingLink.classList.add("hidden");
        batchDetailBody.innerHTML = '<div class="empty-panel"><span class="loading loading-spinner loading-sm"></span> Loading workflow details</div>';
        batchModal.showModal();
        try {
            const state = await api.getBatch(batchId);
            renderBatchDetails(state || {});
        } catch (error) {
            batchDetailBody.innerHTML = `<div class="empty-panel text-error">${escapeHtml(error.message || "Unable to load batch details")}</div>`;
            if (window.DocFlow) {
                window.DocFlow.showToast(error.message || "Unable to load batch details", "error");
            }
        }
    }


    async function loadReports() {
        const bindingId = new URLSearchParams(window.location.search).get("ingress_binding_id");
        if (bindingId) {
            document.getElementById("reports-workspace").hidden = true;
            const section = document.getElementById("reports-binding");
            section.classList.remove("hidden");
            const offset = Number(section.dataset.offset || 0);
            const result = await api.getBindingActivity(bindingId, offset);
            document.getElementById("reports-binding-path").textContent = `Binding ${bindingId} · page ${offset / 20 + 1}`;
            document.getElementById("reports-binding-rows").innerHTML = result.batches.map(batch => `<p class="py-3 border-b"><a href="/app/batches/${encodeURIComponent(batch.id)}">${escapeHtml(batch.created_at)} · ${escapeHtml(batch.status)}</a></p>`).join("") || '<p class="py-4">No batches on this page.</p>';
            document.getElementById("reports-binding-prev").disabled = offset === 0;
            document.getElementById("reports-binding-next").disabled = result.batches.length < 20;
            return;
        }
        const payload = await api.getSummary();
        render(payload || {});
    }

    document.getElementById("reports-refresh-button").addEventListener("click", () => {
        loadReports().catch((error) => window.DocFlow.showToast(error.message || "Unable to load reports", "error"));
    });

    ["prev", "next"].forEach(direction => document.getElementById(`reports-binding-${direction}`).addEventListener("click", () => {
        const section = document.getElementById("reports-binding");
        section.dataset.offset = Math.max(0, Number(section.dataset.offset || 0) + (direction === "next" ? 20 : -20));
        loadReports().catch(error => window.DocFlow.showToast(error.message, "error"));
    }));

    document.getElementById("reports-recent-body").addEventListener("click", (event) => {
        const row = event.target.closest(".reports-batch-row");
        if (row) {
            openBatchDetails(row.dataset.batchId);
        }
    });

    document.getElementById("reports-recent-body").addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") {
            return;
        }
        const row = event.target.closest(".reports-batch-row");
        if (row) {
            event.preventDefault();
            openBatchDetails(row.dataset.batchId);
        }
    });

    loadReports().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load reports", "error");
    });
})();
