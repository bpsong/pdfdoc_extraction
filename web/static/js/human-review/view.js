/** PDF, lock, diff, source-mode, and pane presentation for review. */

export function createHumanReviewView(state, elements, model, callbacks, docFlow, pdfViewerRuntime) {
    const { escapeHtml, titleCase, pathString, fieldForPath, fieldLabel,
        isComplete, hasOwnLock, formatValue, normalizeSourceValueMode } = model;
    const renderEditor = callbacks.renderEditor;

    function storageGet(key) {
        try {
            return window.localStorage.getItem(key);
        } catch (error) {
            return null;
        }
    }

    function storageSet(key, value) {
        try {
            window.localStorage.setItem(key, value);
        } catch (error) {
            // Preference persistence is optional; keep the current in-page state.
        }
    }

    function initializeSourceValueMode() {
        state.sourceValueMode = normalizeSourceValueMode(storageGet("docflow.review.sourceValueMode"));
        if (elements.sourceModeSelect) {
            elements.sourceModeSelect.value = state.sourceValueMode;
        }
        if (elements.workspace) {
            elements.workspace.dataset.sourceValueMode = state.sourceValueMode;
        }
    }

    function setSourceValueMode(mode) {
        state.sourceValueMode = normalizeSourceValueMode(mode);
        state.sourceValueReveals.clear();
        storageSet("docflow.review.sourceValueMode", state.sourceValueMode);
        if (elements.sourceModeSelect) {
            elements.sourceModeSelect.value = state.sourceValueMode;
        }
        if (elements.workspace) {
            elements.workspace.dataset.sourceValueMode = state.sourceValueMode;
        }
        renderEditor();
    }

    function renderPdfPreview() {
        const documentPayload = state.document || {};
        const filename = documentPayload.filename || documentPayload.original_filename || "Document";
        if (state.pdfViewer) {
            state.pdfViewer.destroy();
            state.pdfViewer = null;
        }
        if (documentPayload.preview_url) {
            elements.pdfOpenLink.href = documentPayload.preview_url;
            elements.pdfOpenLink.classList.remove("hidden");
            state.pdfViewer = pdfViewerRuntime.mount(
                elements.pdfBody,
                { url: documentPayload.preview_url, title: `${filename} source PDF` },
            );
        } else {
            elements.pdfOpenLink.classList.add("hidden");
            elements.pdfBody.innerHTML = '<div class="empty-panel">Source PDF unavailable</div>';
        }
    }

    function selectPdfField(pathParts, field) {
        if (!state.pdfViewer) {
            return;
        }
        state.pdfViewer.selectField(
            pathString(pathParts),
            fieldForPath(pathParts) || field,
            pathParts,
            fieldLabel(field),
        );
    }

    function statusBadge(status) {
        return `<span class="badge ${docFlow.statusBadgeClass(status, "pending")} badge-sm">${escapeHtml(docFlow.statusLabel(status, "pending"))}</span>`;
    }

    function renderHeader() {
        const documentPayload = state.document || {};
        const filename = documentPayload.filename || documentPayload.original_filename || "Document";
        elements.documentTitle.textContent = filename;
        elements.documentSubtitle.textContent = [
            titleCase(documentPayload.document_type || documentPayload.split_category || "Document"),
            documentPayload.status ? titleCase(documentPayload.status) : "",
        ].filter(Boolean).join(" - ");
        elements.itemBadge.textContent = state.reviewItemId;
        if (elements.providerBadge) {
            const provider = state.extraction && state.extraction.provider;
            elements.providerBadge.textContent = provider === "glm_ocr_ollama"
                ? "GLM-OCR"
                : provider === "llamacloud_extract_v2"
                    ? "LlamaCloud Extract"
                    : provider || "Provider unavailable";
            elements.providerBadge.classList.remove("hidden");
        }
        elements.statusBadge.innerHTML = isComplete()
            ? '<span class="badge badge-success badge-sm">Review complete</span>'
            : statusBadge(state.reviewItem && state.reviewItem.status);
        elements.statusBadge.classList.remove("hidden");

        const reasons = state.metadata.reasons || [];
        if (isComplete()) {
            elements.reasonSummary.textContent = "Original extraction confidence is retained for reference.";
        } else if (reasons.length) {
            elements.reasonSummary.textContent = reasons.map((reason) => titleCase(reason.reason)).join(", ");
        } else {
            elements.reasonSummary.textContent = titleCase(state.reviewItem && state.reviewItem.reason);
        }

        renderPdfPreview();
    }

    function renderLockState() {
        const lockedBy = state.lock && state.lock.locked_by;
        const ownsLock = hasOwnLock();
        const completed = isComplete();
        const showBlockingBanner = Boolean(state.lock && !ownsLock);
        elements.lockBanner.classList.toggle("hidden", !showBlockingBanner);
        if (showBlockingBanner) {
            elements.lockBanner.textContent = `Locked by ${lockedBy || "another operator"} until ${docFlow.formatDateTime(state.lock.expires_at)}.`;
        }

        if (elements.completionBanner) {
            elements.completionBanner.classList.toggle("hidden", !completed);
            elements.completionBanner.innerHTML = completed
                ? '<strong>Review complete.</strong> The values below were accepted by a reviewer. Original extraction confidence remains visible for reference; no further review action is required.'
                : "";
        }

        if (elements.lockSummary) {
            const showOwnLockSummary = Boolean(state.lock && ownsLock);
            elements.lockSummary.classList.toggle("hidden", !showOwnLockSummary);
            elements.lockSummary.textContent = showOwnLockSummary
                ? `Claimed until ${docFlow.formatDateTime(state.lock.expires_at)}`
                : "";
        }

        const claimDisabled = completed || Boolean(state.lock) || state.completionPending;
        elements.claimButton.disabled = claimDisabled;
        elements.claimButton.classList.toggle("hidden", claimDisabled);
        elements.releaseButton.disabled = completed || !ownsLock || state.completionPending;
        elements.saveButton.disabled = completed || !ownsLock || state.completionPending;
        elements.completeButton.disabled = completed || !ownsLock || state.completionPending;
        elements.diffButton.disabled = completed || !ownsLock || state.completionPending;
        if (!state.completionPending) {
            elements.completeButton.innerHTML = "Complete Review";
            elements.completeButton.removeAttribute("aria-busy");
        }
    }

    function setCompletionPending(pending) {
        state.completionPending = pending;
        elements.workspace.classList.toggle("is-completing", pending);
        if (elements.actionStatus) {
            elements.actionStatus.classList.toggle("hidden", !pending);
            elements.actionStatus.innerHTML = pending
                ? '<span class="review-action-spinner" aria-hidden="true"></span><span>Saving review and finishing workflow…</span>'
                : "";
        }
        if (pending) {
            elements.completeButton.disabled = true;
            elements.completeButton.setAttribute("aria-busy", "true");
            elements.completeButton.innerHTML = '<span class="review-action-spinner" aria-hidden="true"></span><span>Saving review…</span>';
            elements.claimButton.disabled = true;
            elements.releaseButton.disabled = true;
            elements.saveButton.disabled = true;
            elements.diffButton.disabled = true;
        }
    }

    function setPanePercent(percent, persist = true) {
        if (!elements.workspace || !elements.paneDivider) {
            return;
        }
        const width = elements.workspace.clientWidth || 1;
        const narrow = width < 780;
        elements.workspace.classList.toggle("is-narrow", narrow);
        const minimum = narrow ? 35 : Math.max(35, Math.ceil((368 / width) * 100));
        const maximum = narrow ? 70 : Math.min(70, Math.floor(((width - 396) / width) * 100));
        state.panePercent = Math.min(maximum, Math.max(minimum, Math.round(percent)));
        elements.workspace.style.setProperty("--review-pdf-pane-width", `${state.panePercent}%`);
        elements.paneDivider.setAttribute("aria-valuemin", String(minimum));
        elements.paneDivider.setAttribute("aria-valuemax", String(maximum));
        elements.paneDivider.setAttribute("aria-valuenow", String(state.panePercent));
        if (persist) {
            state.preferredPanePercent = state.panePercent;
            storageSet("docflow.review.pdfPanePercent", String(state.preferredPanePercent));
        }
    }

    function initializePaneDivider() {
        if (!elements.workspace || !elements.paneDivider) {
            return;
        }
        const saved = Number(storageGet("docflow.review.pdfPanePercent"));
        state.preferredPanePercent = Number.isFinite(saved) && saved ? saved : 52;
        setPanePercent(state.preferredPanePercent, false);

        elements.paneDivider.addEventListener("pointerdown", (event) => {
            if (window.matchMedia("(max-width: 900px)").matches) {
                return;
            }
            elements.paneDivider.setPointerCapture(event.pointerId);
            elements.workspace.classList.add("is-resizing");
        });
        elements.paneDivider.addEventListener("pointermove", (event) => {
            if (!elements.paneDivider.hasPointerCapture(event.pointerId)) {
                return;
            }
            const bounds = elements.workspace.getBoundingClientRect();
            setPanePercent(((event.clientX - bounds.left) / bounds.width) * 100);
        });
        const stopResize = (event) => {
            if (elements.paneDivider.hasPointerCapture(event.pointerId)) {
                elements.paneDivider.releasePointerCapture(event.pointerId);
            }
            elements.workspace.classList.remove("is-resizing");
        };
        elements.paneDivider.addEventListener("pointerup", stopResize);
        elements.paneDivider.addEventListener("pointercancel", stopResize);
        elements.paneDivider.addEventListener("dblclick", () => setPanePercent(52));
        elements.paneDivider.addEventListener("keydown", (event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
                event.preventDefault();
                setPanePercent(state.panePercent + (event.key === "ArrowRight" ? 3 : -3));
            } else if (event.key === "Home") {
                event.preventDefault();
                setPanePercent(35);
            } else if (event.key === "End") {
                event.preventDefault();
                setPanePercent(70);
            }
        });
        const refreshPaneSize = () => setPanePercent(state.preferredPanePercent, false);
        window.addEventListener("resize", refreshPaneSize);
        new ResizeObserver(refreshPaneSize).observe(elements.workspace);
    }

    function renderDiff(diff) {
        elements.diffPanel.classList.remove("hidden");
        const changes = diff.changes || [];
        if (!changes.length) {
            elements.diffBody.innerHTML = '<div class="text-base-content/60">No changes from current final values.</div>';
            return;
        }
        elements.diffBody.innerHTML = changes.map((change) => `
            <div class="review-diff-row">
                <div class="font-medium">${escapeHtml(titleCase(change.field))}</div>
                <div class="review-diff-value text-base-content/60">${escapeHtml(formatValue(change.old_value))}</div>
                <div class="review-diff-value font-medium">${escapeHtml(formatValue(change.new_value))}</div>
            </div>
        `).join("");
    }

    return { initializeSourceValueMode, setSourceValueMode, renderPdfPreview,
        selectPdfField, renderHeader, renderLockState, setCompletionPending,
        setPanePercent, initializePaneDivider, renderDiff };
}
