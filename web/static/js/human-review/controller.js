import { createHumanReviewModel } from "./model.js?v=controller-modularization-6a";
import { createHumanReviewApi } from "./api.js?v=controller-modularization-6a";
import { createHumanReviewFieldView } from "./field-view.js?v=controller-modularization-6a";
import { createHumanReviewView } from "./view.js?v=controller-modularization-6a";

(function () {
    "use strict";

    const state = {
        reviewItemId: "",
        operator: "",
        reviewItem: null,
        metadata: {},
        document: null,
        extraction: null,
        fields: [],
        fieldsByKey: new Map(),
        schemaFields: [],
        originalValues: {},
        values: {},
        lock: null,
        sourceValueMode: "review",
        sourceValueReveals: new Set(),
        pdfViewer: null,
        panePercent: 52,
        preferredPanePercent: 52,
        completionPending: false,
    };

    const elements = {};

    function bindElements() {
        elements.workspace = document.getElementById("human-review-workspace");
        elements.documentTitle = document.getElementById("review-document-title");
        elements.documentSubtitle = document.getElementById("review-document-subtitle");
        elements.pdfBody = document.getElementById("review-pdf-body");
        elements.pdfOpenLink = document.getElementById("review-pdf-open-link");
        elements.itemBadge = document.getElementById("review-item-badge");
        elements.providerBadge = document.getElementById("review-provider-badge");
        elements.statusBadge = document.getElementById("review-status-badge");
        elements.reasonSummary = document.getElementById("review-reason-summary");
        elements.fieldsContainer = document.getElementById("review-fields-container");
        elements.lockBanner = document.getElementById("review-lock-banner");
        elements.completionBanner = document.getElementById("review-completion-banner");
        elements.lockSummary = document.getElementById("review-lock-summary");
        elements.claimButton = document.getElementById("review-claim-button");
        elements.releaseButton = document.getElementById("review-release-button");
        elements.saveButton = document.getElementById("review-save-button");
        elements.actionStatus = document.getElementById("review-action-status");
        elements.completeButton = document.getElementById("review-complete-button");
        elements.diffButton = document.getElementById("review-diff-button");
        elements.sourceModeSelect = document.getElementById("review-source-mode-select");
        elements.diffPanel = document.getElementById("review-diff-panel");
        elements.diffBody = document.getElementById("review-diff-body");
        elements.diffCloseButton = document.getElementById("review-diff-close-button");
        elements.paneDivider = document.getElementById("review-pane-divider");
    }

    const model = createHumanReviewModel(state);
    let fieldView;
    const { initializeValues, collectCorrections } = model;
    let initializeSourceValueMode;
    let setSourceValueMode;
    let renderHeader;
    let renderLockState;
    let setCompletionPending;
    let initializePaneDivider;
    let renderDiff;
    let renderEditor;
    let api;

    function applyPayload(payload) {
        state.reviewItem = payload.review_item || {};
        state.metadata = payload.metadata || state.reviewItem.metadata || {};
        state.document = payload.document || null;
        state.extraction = payload.extraction || null;
        state.lock = payload.lock || null;
        initializeValues(payload);
        renderHeader();
        renderLockState();
        renderEditor();
    }

    async function loadReviewItem() {
        elements.fieldsContainer.innerHTML = '<div class="empty-panel">Loading review details...</div>';
        try {
            const payload = await api.load();
            applyPayload(payload);
        } catch (error) {
            elements.fieldsContainer.innerHTML = '<div class="empty-panel text-error">Review item failed to load</div>';
            window.DocFlow.showToast(error.message || "Review item failed to load", "error");
        }
    }

    async function claimReview() {
        elements.claimButton.disabled = true;
        try {
            await api.claim();
            window.DocFlow.showToast("Review item claimed", "success");
            await loadReviewItem();
        } catch (error) {
            elements.claimButton.disabled = false;
            window.DocFlow.showToast(error.message || "Unable to claim review item", "error");
        }
    }

    async function releaseReview() {
        elements.releaseButton.disabled = true;
        try {
            await api.release();
            window.DocFlow.showToast("Review item released", "success");
            await loadReviewItem();
        } catch (error) {
            elements.releaseButton.disabled = false;
            window.DocFlow.showToast(error.message || "Unable to release review item", "error");
        }
    }

    async function saveDraft() {
        elements.saveButton.disabled = true;
        try {
            const payload = await api.saveDraft(collectCorrections());
            applyPayload(payload);
            window.DocFlow.showToast("Draft saved", "success");
        } catch (error) {
            elements.saveButton.disabled = false;
            window.DocFlow.showToast(error.message || "Unable to save draft", "error");
        }
    }

    async function previewDiff() {
        elements.diffButton.disabled = true;
        try {
            const payload = await api.previewDiff(collectCorrections());
            renderDiff(payload);
        } catch (error) {
            window.DocFlow.showToast(error.message || "Unable to preview diff", "error");
        } finally {
            elements.diffButton.disabled = false;
        }
    }

    async function completeReview() {
        if (state.completionPending) {
            return;
        }
        setCompletionPending(true);
        try {
            await api.complete(collectCorrections());
            window.DocFlow.showToast("Review completed", "success");
            window.location.href = "/app/review";
        } catch (error) {
            setCompletionPending(false);
            renderLockState();
            elements.completeButton.disabled = false;
            window.DocFlow.showToast(error.message || "Unable to complete review", "error");
        }
    }

    function bindEvents() {
        elements.claimButton.addEventListener("click", claimReview);
        elements.releaseButton.addEventListener("click", releaseReview);
        elements.saveButton.addEventListener("click", saveDraft);
        elements.diffButton.addEventListener("click", previewDiff);
        elements.completeButton.addEventListener("click", completeReview);
        elements.diffCloseButton.addEventListener("click", () => elements.diffPanel.classList.add("hidden"));
        if (elements.sourceModeSelect) {
            elements.sourceModeSelect.addEventListener("change", () => setSourceValueMode(elements.sourceModeSelect.value));
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        bindElements();
        if (!elements.workspace) {
            return;
        }
        state.reviewItemId = elements.workspace.dataset.reviewItemId || "";
        state.operator = elements.workspace.dataset.reviewOperator || "";
        if (!state.reviewItemId) {
            elements.fieldsContainer.innerHTML = '<div class="empty-panel text-error">Missing review item id</div>';
            return;
        }
        const view = createHumanReviewView(state, elements, model,
            { renderEditor: () => fieldView.renderEditor() },
            window.DocFlow, window.DocFlowPdfViewer);
        fieldView = createHumanReviewFieldView(state, elements, model, view);
        ({ initializeSourceValueMode, setSourceValueMode, renderHeader,
            renderLockState, setCompletionPending, initializePaneDivider, renderDiff } = view);
        ({ renderEditor } = fieldView);
        initializeSourceValueMode();
        api = createHumanReviewApi(window.DocFlow, state.reviewItemId);
        bindEvents();
        initializePaneDivider();
        loadReviewItem();
    });
})();
