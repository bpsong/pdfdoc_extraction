(function () {
    "use strict";

    const workspace = document.getElementById("processing-workspace");
    if (!workspace) {
        return;
    }

    const batchId = workspace.dataset.batchId || "";
    const tableBody = document.getElementById("processing-table-body");
    const pipelineStepList = document.getElementById("pipeline-step-list");
    const progressBar = document.getElementById("overall-progress-bar");
    const progressLabel = document.getElementById("overall-progress-label");
    const refreshNote = document.getElementById("processing-refresh-note");
    const splitResultsLink = document.getElementById("split-results-link");
    const clearFailureNotificationsButton = document.getElementById("clear-failure-notifications-button");
    const terminalStatuses = new Set(["completed", "completed_with_errors", "failed", "cancelled", "review_completed"]);
    let pollTimer = null;

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function titleCase(value) {
        return String(value || "unknown")
            .replace(/_/g, " ")
            .replace(/\b\w/g, (letter) => letter.toUpperCase());
    }

    function isTerminal(status) {
        return terminalStatuses.has(String(status || "").toLowerCase());
    }

    function statusBadge(status) {
        const normalized = String(status || "queued").toLowerCase();
        const classByStatus = {
            received: "badge-ghost",
            queued: "badge-ghost",
            processing: "badge-primary",
            split_pending: "badge-warning",
            split_completed: "badge-success",
            extraction_pending: "badge-warning",
            extraction_completed: "badge-success",
            review_required: "badge-warning",
            in_review: "badge-warning",
            review_completed: "badge-success",
            completed: "badge-success",
            completed_with_errors: "badge-warning",
            failed: "badge-error",
            cancelled: "badge-ghost",
        };
        return `<span class="badge ${classByStatus[normalized] || "badge-ghost"} badge-sm">${escapeHtml(titleCase(normalized))}</span>`;
    }

    function categoryBadge(category) {
        const normalized = String(category || "custom").toLowerCase();
        const classByCategory = {
            context: "badge-ghost",
            split: "badge-info",
            extract: "badge-primary",
            review: "badge-warning",
            storage: "badge-success",
            rules: "badge-secondary",
            archive: "badge-accent",
            housekeeping: "badge-ghost",
            ingestion: "badge-ghost",
            custom: "badge-ghost",
        };
        return `<span class="badge ${classByCategory[normalized] || "badge-ghost"} badge-xs">${escapeHtml(titleCase(normalized))}</span>`;
    }

    function stateIcon(state) {
        if (state === "running") {
            return '<span class="loading loading-spinner loading-xs"></span>';
        }
        if (state === "completed") {
            return '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>';
        }
        if (state === "failed") {
            return '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>';
        }
        if (state === "paused") {
            return '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6" /></svg>';
        }
        if (state === "skipped") {
            return '<span class="text-xs font-semibold">Skip</span>';
        }
        return '<span class="w-2 h-2 rounded-full bg-current"></span>';
    }

    function stateClass(state) {
        if (state === "completed") {
            return "completed";
        }
        if (state === "running") {
            return "running";
        }
        if (state === "paused") {
            return "warning";
        }
        if (state === "failed") {
            return "failed";
        }
        if (state === "skipped") {
            return "skipped";
        }
        return "";
    }

    function stepDetail(step) {
        const counts = step.counts || {};
        const parts = [];
        if (counts.completed) {
            parts.push(`${counts.completed} done`);
        }
        if (counts.running) {
            parts.push(`${counts.running} running`);
        }
        if (counts.paused) {
            parts.push(`${counts.paused} paused`);
        }
        if (counts.failed) {
            parts.push(`${counts.failed} failed`);
        }
        if (counts.pending && !parts.length) {
            parts.push(`${counts.pending} pending`);
        }
        if (counts.skipped && !parts.length) {
            parts.push(`${counts.skipped} skipped`);
        }
        return parts.join(", ") || titleCase(step.state || "pending");
    }

    function ingestionStep(state) {
        const documentCount = (state.documents || []).length;
        const sourceDocuments = (state.documents || []).filter((document) => !document.parent_document_id);
        const splitDocuments = (state.documents || []).filter((document) => document.parent_document_id);
        const failed = (state.documents || []).filter((document) => String(document.status || "").toLowerCase() === "failed").length;
        const failedSources = sourceDocuments.filter((document) => String(document.status || "").toLowerCase() === "failed").length;
        const failedSplits = splitDocuments.filter((document) => String(document.status || "").toLowerCase() === "failed").length;
        const running = (state.documents || []).filter((document) => !isTerminal(document.status)).length;
        const sourceLabel = `${sourceDocuments.length} source${sourceDocuments.length === 1 ? "" : "s"}`;
        const splitLabel = `${splitDocuments.length} split document${splitDocuments.length === 1 ? "" : "s"}`;
        let detail = documentCount ? `${documentCount} files${failed ? `, ${failed} failed` : ""}` : "Pending";
        if (splitDocuments.length) {
            const failureParts = [];
            if (failedSources) {
                failureParts.push(`${failedSources} source${failedSources === 1 ? "" : "s"} failed`);
            }
            if (failedSplits) {
                failureParts.push(`${failedSplits} split document${failedSplits === 1 ? "" : "s"} failed`);
            }
            detail = `${sourceLabel}, ${splitLabel}${failureParts.length ? `, ${failureParts.join(", ")}` : ""}`;
        }
        return {
            key: "ingestion",
            label: "Uploaded",
            category: "ingestion",
            state: documentCount ? "completed" : "pending",
            counts: {
                completed: documentCount,
                running,
                failed,
                paused: 0,
                pending: documentCount ? 0 : 1,
                skipped: 0,
            },
            detail,
        };
    }

    function renderPipelineStep(step) {
        const state = String(step.state || "pending");
        const muted = state === "pending" || state === "skipped" ? "text-base-content/50" : "";
        return `
            <div class="pipeline-step" data-step="${escapeHtml(step.key)}">
                <div class="pipeline-step-icon ${stateClass(state)}">${stateIcon(state)}</div>
                <div class="pipeline-step-text">
                    <div class="pipeline-step-label ${muted}">${escapeHtml(step.label || step.key)}</div>
                    <div class="pipeline-step-key">${escapeHtml(step.key || "")}</div>
                    <div class="pipeline-step-meta">
                        ${categoryBadge(step.category)}
                        <span>${escapeHtml(step.detail || stepDetail(step))}</span>
                    </div>
                </div>
            </div>
        `;
    }

    function renderPipelineGroup(state, showTitle) {
        const batch = state.batch || {};
        const steps = [ingestionStep(state)].concat(state.aggregate_step_states || []);
        const compactClass = steps.length > 8 ? " compact" : "";
        const items = [];
        steps.forEach((step, index) => {
            if (index > 0) {
                const previousState = String(steps[index - 1].state || "");
                items.push(`<div class="pipeline-connector ${["completed", "running"].includes(previousState) ? "active" : ""}"></div>`);
            }
            items.push(renderPipelineStep(step));
        });

        return `
            <div class="pipeline-group">
                ${showTitle ? `
                    <div class="pipeline-group-header">
                        <span class="font-medium truncate">${escapeHtml(batch.original_filename || batch.id || "Batch")}</span>
                        <span class="badge badge-outline badge-xs">${escapeHtml(batch.id || "")}</span>
                    </div>
                ` : ""}
                <div class="pipeline-steps${compactClass}">
                    ${items.join("")}
                </div>
            </div>
        `;
    }

    function renderPipeline(states) {
        if (!states.length) {
            pipelineStepList.innerHTML = '<div class="empty-panel">No active pipeline data</div>';
            return;
        }
        pipelineStepList.innerHTML = states.map((state) => renderPipelineGroup(state, states.length > 1)).join("");
    }

    function stepName(step) {
        if (!step) {
            return '<span class="text-xs text-base-content/40">Pending</span>';
        }
        const state = String(step.state || "pending");
        return `
            <div class="min-w-36">
                <div class="text-sm font-medium">${escapeHtml(step.label || step.key)}</div>
                <div class="flex items-center gap-2 text-xs text-base-content/50">
                    ${categoryBadge(step.category)}
                    <span>${escapeHtml(titleCase(state))}</span>
                </div>
            </div>
        `;
    }

    function rowAction(batch, document) {
        const status = String(document.status || "").toLowerCase();
        if (hasFailureEvidence(document)) {
            return `<a href="/app/failures?document_id=${encodeURIComponent(document.id)}" class="btn btn-error btn-xs">Open Failure</a>`;
        }
        if (["review_required", "in_review"].includes(status)) {
            return '<a href="/app/review" class="btn btn-warning btn-xs">Review</a>';
        }
        if (["extraction_completed", "review_completed", "completed"].includes(status)) {
            return `<a href="/app/documents/${encodeURIComponent(document.id)}/extraction" class="btn btn-ghost btn-xs">Extraction</a>`;
        }
        if (batch && batch.id && hasSplitEvidence(document)) {
            return `<a href="/app/batches/${encodeURIComponent(batch.id)}/split-results" class="btn btn-ghost btn-xs">Split</a>`;
        }
        return '<span class="text-xs text-base-content/40">Pending</span>';
    }

    function hasFailureEvidence(document) {
        return Boolean(
            String(document.status || "").toLowerCase() === "failed"
            || (document.task_states || []).some((step) => step.state === "failed")
            || (document.task_runs || []).some((run) => String(run.status || "").toLowerCase() === "failed")
        );
    }

    function hasSplitEvidence(document) {
        return Boolean(
            document.parent_document_id
            || String(document.status || "").toLowerCase() === "split_completed"
            || (document.task_states || []).some((step) => step.category === "split" && ["completed", "running"].includes(step.state))
        );
    }

    function renderRows(states) {
        const rows = [];
        states.forEach((state) => {
            const batch = state.batch || {};
            (state.documents || []).forEach((document) => {
                const filename = document.original_filename || document.file_path || document.id;
                const progress = Number(document.progress_percent || 0);
                rows.push(`
                    <tr>
                        <td>
                            <div class="text-sm font-medium truncate max-w-xs">${escapeHtml(filename)}</div>
                            <div class="text-xs text-base-content/40">${escapeHtml(batch.id || document.batch_id || "")}</div>
                        </td>
                        <td>${statusBadge(document.status)}</td>
                        <td>${stepName(document.current_step)}</td>
                        <td>${stepName(document.last_completed_step)}</td>
                        <td>
                            <div class="flex items-center gap-2 min-w-28">
                                <progress class="progress progress-primary w-20" value="${progress}" max="100"></progress>
                                <span class="text-xs">${progress}%</span>
                            </div>
                        </td>
                        <td>${rowAction(batch, document)}</td>
                    </tr>
                `);
            });
        });

        if (!rows.length) {
            tableBody.innerHTML = '<tr><td colspan="6" class="text-center text-base-content/50 py-10">No active documents</td></tr>';
            return;
        }
        tableBody.innerHTML = rows.join("");
    }

    function aggregateProgress(states) {
        let total = 0;
        let count = 0;
        states.forEach((state) => {
            total += Number(state.progress_percent || 0);
            count += 1;
        });
        return count ? Math.round(total / count) : 0;
    }

    function updateSplitLink(states) {
        const target = states.find((state) => (state.documents || []).some(hasSplitEvidence));
        if (target && target.batch && target.batch.id) {
            splitResultsLink.href = `/app/batches/${encodeURIComponent(target.batch.id)}/split-results`;
            splitResultsLink.classList.remove("hidden");
        } else {
            splitResultsLink.classList.add("hidden");
        }
    }

    async function loadVisibleStates() {
        if (batchId) {
            return [await window.DocFlow.apiGet(`/api/batches/${encodeURIComponent(batchId)}/processing-state`)];
        }
        const payload = await window.DocFlow.apiGet("/api/processing-state");
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

    async function refreshProcessing() {
        try {
            const states = await loadVisibleStates();
            renderPipeline(states);
            renderRows(states);
            updateSplitLink(states);
            await updateFailureNotificationControl();
            const progress = aggregateProgress(states);
            progressBar.value = progress;
            progressLabel.textContent = `${progress}%`;
            refreshNote.textContent = states.length ? `Last updated ${new Date().toLocaleTimeString()}` : "No batches found";

            if (hasActiveWork(states)) {
                if (!pollTimer) {
                    pollTimer = window.setInterval(refreshProcessing, 3000);
                }
            } else if (pollTimer) {
                window.clearInterval(pollTimer);
                pollTimer = null;
            }
        } catch (error) {
            refreshNote.textContent = error.message || "Unable to load processing state";
            if (window.DocFlow) {
                window.DocFlow.showToast(error.message || "Unable to load processing state", "error");
            }
        }
    }

    async function updateFailureNotificationControl() {
        if (!clearFailureNotificationsButton || !window.DocFlow || !window.DocFlow.refreshFailureNotifications) {
            return;
        }
        const payload = await window.DocFlow.refreshFailureNotifications();
        const count = Number(payload && payload.count ? payload.count : 0);
        clearFailureNotificationsButton.classList.toggle("hidden", count <= 0);
    }

    if (clearFailureNotificationsButton) {
        clearFailureNotificationsButton.addEventListener("click", async () => {
            try {
                await window.DocFlow.apiPost("/api/failures/notifications/clear", {});
                window.DocFlow.showToast("Error notification cleared", "success");
                await updateFailureNotificationControl();
            } catch (error) {
                window.DocFlow.showToast(error.message || "Unable to clear error notification", "error");
            }
        });
    }

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            refreshProcessing();
        }
    });

    refreshProcessing();
})();
