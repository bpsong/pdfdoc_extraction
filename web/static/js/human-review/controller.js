import { createHumanReviewModel } from "./model.js?v=generic-rules-1";
import { createHumanReviewApi } from "./api.js?v=generic-rules-1";
import { createHumanReviewFieldView } from "./field-view.js?v=generic-rules-1";
import { createHumanReviewView } from "./view.js?v=generic-rules-1";
import { createReviewValidation } from './validation.js?v=generic-rules-1';
import { createReviewValidationView } from './validation-view.js?v=generic-rules-1';

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
        savingDraft: false,
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
        elements.revalidateButton = document.getElementById('review-revalidate-button');
        elements.validationPanel = document.getElementById('review-validation-panel');
        elements.validationStatus = document.getElementById('review-validation-status');
        elements.validationSummary = document.getElementById('review-validation-summary');
        elements.validationDetails = document.getElementById('review-validation-details');
        elements.validationList = document.getElementById('review-validation-list');
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
    let validationView;
    const validation = createReviewValidation(state, model, renderValidation);

    function renderValidation() {
        validationView?.render();
        if (validation.current().enabled && validation.current().conflict) {
            elements.saveButton.disabled = true;
            elements.completeButton.disabled = true;
        }
    }

    function applyPayload(payload, preservedValues = null) {
        state.reviewRevision = payload.review_revision || null;
        state.reviewItem = payload.review_item || {};
        state.metadata = payload.metadata || state.reviewItem.metadata || {};
        state.document = payload.document || null;
        state.extraction = payload.extraction || null;
        state.lock = payload.lock || null;
        initializeValues(payload);
        if (preservedValues) state.values = preservedValues;
        renderHeader();
        renderLockState();
        renderEditor();
        validation.load(payload);
        if (preservedValues) validation.changed();
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
        if (state.savingDraft || state.completionPending) return;
        state.savingDraft = true;
        renderLockState();
        const savedValues = model.cloneValue(state.values);
        const ticket = validation.capture();
        try {
            const payload = await api.saveDraft(collectCorrections());
            const preservedValues = JSON.stringify(savedValues) === JSON.stringify(state.values)
                ? null : model.cloneValue(state.values);
            applyPayload(payload, preservedValues);
            window.DocFlow.showToast("Draft saved", "success");
        } catch (error) {
            validation.fail(ticket, error);
            window.DocFlow.showToast(error.message || "Unable to save draft", "error");
        } finally {
            state.savingDraft = false;
            renderLockState();
            renderValidation();
        }
    }

    async function revalidate() {
        if (!validation.canCheck()) return;
        const ticket = validation.capture(true);
        try {
            const payload = await api.revalidate(collectCorrections(), ticket.id);
            validation.accept(ticket, payload);
        } catch (error) {
            validation.fail(ticket, error);
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
        if (state.completionPending || state.savingDraft) {
            return;
        }
        setCompletionPending(true);
        const ticket = validation.capture();
        try {
            await api.complete(collectCorrections());
            window.DocFlow.showToast("Review completed", "success");
            window.location.href = "/app/review";
        } catch (error) {
            setCompletionPending(false);
            renderLockState();
            validation.completionFailure(ticket, error);
            renderValidation();
            if (validation.current().enabled) {
                validationView.scrollToSummary();
                elements.validationStatus.tabIndex = -1;
                elements.validationStatus.focus({preventScroll: true});
            }
            window.DocFlow.showToast(error.message || "Unable to complete review", "error");
        }
    }

    function bindEvents() {
        elements.claimButton.addEventListener("click", claimReview);
        elements.releaseButton.addEventListener("click", releaseReview);
        elements.saveButton.addEventListener("click", saveDraft);
        elements.diffButton.addEventListener("click", previewDiff);
        elements.completeButton.addEventListener("click", completeReview);
        elements.revalidateButton.addEventListener('click', revalidate);
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
        validationView = createReviewValidationView(elements, model, validation);
        fieldView = createHumanReviewFieldView(state, elements, model, view, {
            changed: () => validation.changed(), rendered: renderValidation,
        });
        ({ initializeSourceValueMode, setSourceValueMode, renderHeader,
            renderLockState, setCompletionPending, initializePaneDivider, renderDiff } = view);
        ({ renderEditor } = fieldView);
        initializeSourceValueMode();
        api = createHumanReviewApi(window.DocFlow, state.reviewItemId, () => state.reviewRevision);
        bindEvents();
        initializePaneDivider();
        loadReviewItem();
    });
})();
