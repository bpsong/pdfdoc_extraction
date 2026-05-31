(function () {
    "use strict";

    const workspace = document.getElementById("processing-workspace");
    if (!workspace) {
        return;
    }

    const batchId = workspace.dataset.batchId || "";
    const tableBody = document.getElementById("processing-table-body");
    const progressBar = document.getElementById("overall-progress-bar");
    const progressLabel = document.getElementById("overall-progress-label");
    const refreshNote = document.getElementById("processing-refresh-note");
    const splitResultsLink = document.getElementById("split-results-link");
    const terminalStatuses = new Set(["completed", "completed_with_errors", "failed", "cancelled"]);
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

    function stageIcon(state) {
        if (state === "completed") {
            return '<svg class="w-4 h-4 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>';
        }
        if (state === "running") {
            return '<span class="loading loading-spinner loading-xs text-primary"></span>';
        }
        if (state === "warning") {
            return '<span class="badge badge-warning badge-xs">Review</span>';
        }
        if (state === "failed") {
            return '<span class="badge badge-error badge-xs">Failed</span>';
        }
        if (state === "skipped") {
            return '<span class="text-base-content/30">Skipped</span>';
        }
        return '<span class="text-base-content/30">-</span>';
    }

    function documentStage(document, stage) {
        const status = String(document.status || "").toLowerCase();
        const taskKey = String(document.current_task_key || "").toLowerCase();
        if (status === "failed" || status === "cancelled") {
            return "failed";
        }
        if (stage === "splitting") {
            if (document.parent_document_id || status === "split_completed") {
                return "completed";
            }
            if (status === "split_pending" || taskKey.includes("split")) {
                return "running";
            }
            return "skipped";
        }
        if (stage === "extracting") {
            if (["extraction_completed", "review_required", "in_review", "review_completed", "completed"].includes(status)) {
                return "completed";
            }
            if (status === "extraction_pending" || taskKey.includes("extract")) {
                return "running";
            }
            return "pending";
        }
        if (stage === "review") {
            if (["review_required", "in_review"].includes(status)) {
                return "warning";
            }
            if (["review_completed", "completed"].includes(status)) {
                return "completed";
            }
            if (taskKey.includes("review")) {
                return "running";
            }
            return "pending";
        }
        if (stage === "output") {
            if (status === "completed") {
                return "completed";
            }
            if (taskKey.includes("store") || taskKey.includes("output") || taskKey.includes("archive")) {
                return "running";
            }
            return "pending";
        }
        return "pending";
    }

    function rowAction(batch, document) {
        const status = String(document.status || "").toLowerCase();
        if (["review_required", "in_review"].includes(status)) {
            return '<a href="/app/review" class="btn btn-warning btn-xs">Review</a>';
        }
        if (["extraction_completed", "review_completed", "completed"].includes(status)) {
            return `<a href="/app/documents/${encodeURIComponent(document.id)}/extraction" class="btn btn-ghost btn-xs">Extraction</a>`;
        }
        if (batch && batch.id) {
            return `<a href="/app/batches/${encodeURIComponent(batch.id)}/split-results" class="btn btn-ghost btn-xs">Split</a>`;
        }
        return '<span class="text-xs text-base-content/40">Pending</span>';
    }

    function renderRows(batches) {
        const rows = [];
        batches.forEach((entry) => {
            const batch = entry.batch;
            entry.documents.forEach((document) => {
                const filename = document.original_filename || document.file_path || document.id;
                const progress = Number(document.progress_percent || 0);
                rows.push(`
                    <tr>
                        <td>
                            <div class="text-sm font-medium truncate max-w-xs">${escapeHtml(filename)}</div>
                            <div class="text-xs text-base-content/40">${escapeHtml(batch.id || "")}</div>
                        </td>
                        <td>${statusBadge(document.status)}</td>
                        <td>${stageIcon(documentStage(document, "splitting"))}</td>
                        <td>${stageIcon(documentStage(document, "extracting"))}</td>
                        <td>${stageIcon(documentStage(document, "review"))}</td>
                        <td>${stageIcon(documentStage(document, "output"))}</td>
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
            tableBody.innerHTML = '<tr><td colspan="8" class="text-center text-base-content/50 py-10">No active documents</td></tr>';
            return;
        }
        tableBody.innerHTML = rows.join("");
    }

    function aggregateProgress(batches) {
        let total = 0;
        let count = 0;
        batches.forEach((entry) => {
            if (entry.documents.length) {
                entry.documents.forEach((document) => {
                    total += Number(document.progress_percent || 0);
                    count += 1;
                });
            } else if (entry.batch) {
                total += Number(entry.batch.progress_percent || 0);
                count += 1;
            }
        });
        return count ? Math.round(total / count) : 0;
    }

    function stepStateFromDocuments(documents, stage) {
        if (!documents.length) {
            return "pending";
        }
        const states = documents.map((document) => documentStage(document, stage));
        if (states.includes("failed")) {
            return "failed";
        }
        if (states.includes("warning")) {
            return "warning";
        }
        if (states.includes("running")) {
            return "running";
        }
        if (states.every((state) => state === "completed")) {
            return "completed";
        }
        if (stage === "splitting" && states.every((state) => state === "skipped")) {
            return "skipped";
        }
        return "pending";
    }

    function renderStep(element, label, state, detail) {
        const iconClass = state === "completed" ? "completed" : state === "running" ? "running" : state === "warning" ? "warning" : state === "failed" ? "failed" : "";
        const icon = state === "running"
            ? '<span class="loading loading-spinner loading-xs"></span>'
            : state === "completed"
                ? '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>'
                : state === "failed"
                    ? '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>'
                    : '<span class="w-2 h-2 rounded-full bg-current"></span>';
        element.innerHTML = `
            <div class="pipeline-step-icon ${iconClass}">${icon}</div>
            <p class="mt-2 text-xs font-medium ${state === "pending" || state === "skipped" ? "text-base-content/50" : ""}">${escapeHtml(label)}</p>
            <p class="text-xs text-base-content/50">${escapeHtml(detail)}</p>
        `;
    }

    function renderPipeline(batches) {
        const documents = batches.flatMap((entry) => entry.documents);
        const uploadedState = documents.length ? "completed" : "pending";
        const stepStates = [
            ["uploaded", "Uploaded", uploadedState, documents.length ? `${documents.length} files` : "Pending"],
            ["splitting", "Splitting", stepStateFromDocuments(documents, "splitting"), ""],
            ["extracting", "Extracting", stepStateFromDocuments(documents, "extracting"), ""],
            ["review", "Review", stepStateFromDocuments(documents, "review"), ""],
            ["output", "Output", stepStateFromDocuments(documents, "output"), ""],
        ];
        stepStates.forEach(([key, label, state, detail]) => {
            const element = document.querySelector(`[data-step="${key}"]`);
            const displayDetail = detail || (state === "running" ? "In progress" : state === "completed" ? "Done" : state === "skipped" ? "Skipped" : state === "warning" ? "Needs review" : state === "failed" ? "Failed" : "Pending");
            if (element) {
                renderStep(element, label, state, displayDetail);
            }
        });
        document.querySelectorAll(".pipeline-connector").forEach((connector, index) => {
            const beforeState = stepStates[index][2];
            connector.classList.toggle("active", ["completed", "running"].includes(beforeState));
        });
    }

    function updateSplitLink(batches) {
        const targetBatch = batchId ? batches[0]?.batch : batches.find((entry) => entry.documents.some((document) => document.parent_document_id || document.status === "split_completed"))?.batch;
        if (targetBatch && targetBatch.id) {
            splitResultsLink.href = `/app/batches/${encodeURIComponent(targetBatch.id)}/split-results`;
            splitResultsLink.classList.remove("hidden");
        } else {
            splitResultsLink.classList.add("hidden");
        }
    }

    async function loadBatchEntry(id) {
        const batch = await window.DocFlow.apiGet(`/api/batches/${encodeURIComponent(id)}`);
        const documents = await window.DocFlow.apiGet(`/api/batches/${encodeURIComponent(id)}/documents`);
        return { batch, documents };
    }

    async function loadVisibleBatches() {
        if (batchId) {
            return [await loadBatchEntry(batchId)];
        }
        const batches = await window.DocFlow.apiGet("/api/batches");
        const visible = batches.slice(0, 10);
        return Promise.all(visible.map((batch) => loadBatchEntry(batch.id)));
    }

    function hasActiveWork(batches) {
        return batches.some((entry) => {
            if (!isTerminal(entry.batch.status)) {
                return true;
            }
            return entry.documents.some((document) => !isTerminal(document.status));
        });
    }

    async function refreshProcessing() {
        try {
            const batches = await loadVisibleBatches();
            renderPipeline(batches);
            renderRows(batches);
            updateSplitLink(batches);
            const progress = aggregateProgress(batches);
            progressBar.value = progress;
            progressLabel.textContent = `${progress}%`;
            refreshNote.textContent = batches.length ? `Last updated ${new Date().toLocaleTimeString()}` : "No batches found";

            if (hasActiveWork(batches)) {
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

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            refreshProcessing();
        }
    });

    refreshProcessing();
})();
