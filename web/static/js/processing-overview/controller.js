import { createView } from './view.js?v=frontend-hardening-8';
import { createApi } from './api.js?v=frontend-hardening-8';
import { createPollingController } from '../polling.js?v=frontend-hardening-8';
(function () {
    "use strict";

    const workspace = document.getElementById("processing-workspace");
    if (!workspace) {
        return;
    }

    const batchId = workspace.dataset.batchId || "";
    const tableBody = document.getElementById("processing-table-body");
    const tableRegion = document.getElementById("processing-table-region");
    const pipelineStepList = document.getElementById("pipeline-step-list");
    const progressBar = document.getElementById("overall-progress-bar");
    const progressLabel = document.getElementById("overall-progress-label");
    const progressRegion = document.getElementById("processing-progress-region");
    const refreshNote = document.getElementById("processing-refresh-note");
    const splitResultsLink = document.getElementById("split-results-link");
    const clearFailureNotificationsButton = document.getElementById("clear-failure-notifications-button");
    const assignmentSummary = document.getElementById("pipeline-assignment-summary");
    const failureNotice = document.getElementById("processing-failure-notice");
    const terminalStatuses = new Set(["completed", "completed_with_errors", "failed", "cancelled", "review_completed"]);
    let refreshInFlight = false;
    let polling = null;
    let previousProcessingSnapshot = null;
    let previousFailureContent = null;























    const api = createApi(window.DocFlow);
    const { escapeHtml, titleCase, isTerminal, statusBadge, categoryBadge, stateIcon, stateClass, stepDetail, ingestionStep, renderPipelineStep, renderPipelineGroup, renderPipeline, renderAssignment, stepName, rowAction, hasFailureEvidence, renderFailureNotice, hasSplitEvidence, renderRows, aggregateProgress, updateSplitLink } = createView({ pipelineStepList, assignmentSummary, tableBody, failureNotice, splitResultsLink, docFlow: window.DocFlow });
    async function loadVisibleStates() {
        if (batchId) {
            return [await api.getBatch(batchId)];
        }
        const payload = await api.getAll();
        return Array.isArray(payload.batches) ? payload.batches : [];
    }

    function hasActiveWork(states) {
        return states.some((state) => {
            const batch = state.batch || {};
            if (!isTerminal(batch.status)) {
                return true;
            }
            return (state.documents || []).some((document) => !isTerminal(document.status));
        });
    }

    function processingSnapshot(states) {
        const snapshot = new Map();
        states.forEach((state) => {
            const batch = state.batch || {};
            const batchIdValue = String(batch.id || "");
            if (batchIdValue) {
                snapshot.set(`batch:${batchIdValue}`, {
                    label: batch.original_filename || batchIdValue,
                    status: String(batch.status || "queued").toLowerCase(),
                });
            }
            (state.documents || []).forEach((document) => {
                const documentId = String(document.id || "");
                if (documentId) {
                    snapshot.set(`document:${documentId}`, {
                        label: document.filename || document.original_filename || documentId,
                        status: String(document.status || "queued").toLowerCase(),
                    });
                }
            });
        });
        return snapshot;
    }

    function announceProcessingChanges(states) {
        const snapshot = processingSnapshot(states);
        if (!previousProcessingSnapshot) {
            previousProcessingSnapshot = snapshot;
            return;
        }

        const changes = [];
        snapshot.forEach((current, key) => {
            const previous = previousProcessingSnapshot.get(key);
            if (!previous || previous.status === current.status || !isTerminal(current.status)) {
                return;
            }
            changes.push(`${current.label}: ${titleCase(current.status)}`);
        });
        previousProcessingSnapshot = snapshot;

        if (changes.length && window.DocFlow && window.DocFlow.announce) {
            const visibleChanges = changes.slice(0, 3);
            const suffix = changes.length > visibleChanges.length
                ? `, plus ${changes.length - visibleChanges.length} more`
                : "";
            window.DocFlow.announce(`${visibleChanges.join("; ")}${suffix}`);
        }
    }

    async function refreshProcessing() {
        if (refreshInFlight) {
            return;
        }
        refreshInFlight = true;
        if (tableBody && tableBody.dataset.loadError === "true") {
            tableBody.innerHTML = window.DocFlow.tableSkeletonRows(6, 4);
            tableBody.dataset.loadError = "false";
        }
        [tableRegion, tableBody, progressRegion].forEach((element) => {
            if (element) {
                element.setAttribute("aria-busy", "true");
            }
        });
        try {
            const states = await loadVisibleStates();
            renderPipeline(states);
            renderAssignment(states);
            renderRows(states);
            renderFailureNotice(states);
            updateSplitLink(states);
            await updateFailureNotificationControl();
            const progress = aggregateProgress(states);
            progressBar.value = progress;
            progressLabel.textContent = `${progress}%`;
            announceProcessingChanges(states);
            refreshNote.textContent = states.length ? `Last updated ${new Date().toLocaleTimeString()}` : "No batches found";

            polling.setActive(hasActiveWork(states));
        } catch (error) {
            failureNotice.classList.add("hidden");
            const message = error.message || "Unable to load processing state";
            refreshNote.innerHTML = `
                <span class="text-error">${escapeHtml(message)}</span>
                <button id="processing-retry-button" class="btn btn-outline btn-xs ml-2" type="button">Retry</button>
            `;
            tableBody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-10">
                        <p class="text-error">Processing data failed to load</p>
                        <button class="btn btn-outline btn-sm mt-3" type="button" data-processing-retry>Retry</button>
                    </td>
                </tr>
            `;
            tableBody.dataset.loadError = "true";
            if (window.DocFlow) {
                window.DocFlow.showToast(message, "error");
            }
        } finally {
            refreshInFlight = false;
            [tableRegion, tableBody, progressRegion].forEach((element) => {
                if (element) {
                    element.setAttribute("aria-busy", "false");
                }
            });
        }
    }

    async function updateFailureNotificationControl() {
        if (!clearFailureNotificationsButton || !window.DocFlow || !window.DocFlow.refreshFailureNotifications) {
            return;
        }
        const payload = await window.DocFlow.refreshFailureNotifications({ force: true });
        const count = Number(payload && payload.count ? payload.count : 0);
        clearFailureNotificationsButton.classList.toggle("hidden", count <= 0);
    }

    if (clearFailureNotificationsButton) {
        clearFailureNotificationsButton.addEventListener("click", async () => {
            try {
                await api.clearFailureNotifications();
                window.DocFlow.showToast("Error notification cleared", "success");
                await updateFailureNotificationControl();
            } catch (error) {
                window.DocFlow.showToast(error.message || "Unable to clear error notification", "error");
            }
        });
    }

    refreshNote.addEventListener("click", (event) => {
        if (event.target.closest("#processing-retry-button")) {
            void polling.runNow();
        }
    });
    tableBody.addEventListener("click", (event) => {
        if (event.target.closest("[data-processing-retry]")) {
            void polling.runNow();
        }
    });

    polling = createPollingController({ task: refreshProcessing, intervalMs: 3000 });
    window.addEventListener("pagehide", polling.stop, { once: true });
    void polling.runNow();
})();
