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
            .replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function statusBadge(status) {
        const normalized = String(status || "unknown").toLowerCase();
        const badgeClass = normalized.includes("fail")
            ? "badge-error"
            : normalized.includes("complete") || normalized === "review_completed"
                ? "badge-success"
                : normalized.includes("review")
                    ? "badge-warning"
            : "badge-ghost";
        return `<span class="badge badge-sm ${badgeClass}">${escapeHtml(titleCase(status))}</span>`;
    }

    function formatDuration(startedAt, endedAt) {
        if (!startedAt || !endedAt) {
            return "n/a";
        }
        const started = new Date(startedAt);
        const ended = new Date(endedAt);
        if (Number.isNaN(started.getTime()) || Number.isNaN(ended.getTime())) {
            return "n/a";
        }
        const seconds = Math.max(0, (ended.getTime() - started.getTime()) / 1000);
        if (seconds < 60) {
            return `${Math.round(seconds * 10) / 10}s`;
        }
        const minutes = seconds / 60;
        if (minutes < 60) {
            return `${Math.round(minutes * 10) / 10}m`;
        }
        return `${Math.round((minutes / 60) * 10) / 10}h`;
    }

    function formatDateTime(value) {
        if (!value) {
            return "n/a";
        }
        return window.DocFlow.formatDateTime(value) || "n/a";
    }

    function safeJsonBlock(value) {
        if (value === null || value === undefined || value === "") {
            return "{}";
        }
        if (typeof value === "string") {
            try {
                return JSON.stringify(JSON.parse(value), null, 2);
            } catch (error) {
                return value;
            }
        }
        return JSON.stringify(value, null, 2);
    }

    function renderMetric(id, value) {
        document.getElementById(id).textContent = String(value ?? 0);
    }

    function renderSimpleRows(bodyId, rows, labelKey, countKey, emptyText) {
        const body = document.getElementById(bodyId);
        if (!Array.isArray(rows) || !rows.length) {
            body.innerHTML = `<tr><td colspan="2" class="text-center text-base-content/50 py-10">${escapeHtml(emptyText)}</td></tr>`;
            return;
        }
        body.innerHTML = rows.map((row) => `
            <tr>
                <td>${statusBadge(row[labelKey])}</td>
                <td class="text-right font-semibold">${escapeHtml(row[countKey] || 0)}</td>
            </tr>
        `).join("");
    }

    function renderSourceRows(rows) {
        const body = document.getElementById("reports-source-body");
        if (!Array.isArray(rows) || !rows.length) {
            body.innerHTML = '<tr><td colspan="2" class="text-center text-base-content/50 py-10">No source data</td></tr>';
            return;
        }
        body.innerHTML = rows.map((row) => `
            <tr>
                <td>${escapeHtml(titleCase(row.source))}</td>
                <td class="text-right font-semibold">${escapeHtml(row.count || 0)}</td>
            </tr>
        `).join("");
    }

    function renderRecentBatches(batches) {
        const body = document.getElementById("reports-recent-body");
        if (!Array.isArray(batches) || !batches.length) {
            body.innerHTML = '<tr><td colspan="5" class="text-center text-base-content/50 py-10">No recent batches</td></tr>';
            return;
        }
        body.innerHTML = batches.map((batch) => `
            <tr class="reports-batch-row" role="button" tabindex="0" data-batch-id="${escapeHtml(batch.id)}" aria-label="View batch ${escapeHtml(batch.id)} workflow details">
                <td class="text-xs">${escapeHtml(window.DocFlow.formatDateTime(batch.created_at))}</td>
                <td>${escapeHtml(titleCase(batch.source))}</td>
                <td class="font-mono text-xs">${escapeHtml(batch.id)}</td>
                <td>${statusBadge(batch.status)}</td>
                <td class="text-right">${escapeHtml(batch.progress_percent || 0)}%</td>
            </tr>
        `).join("");
    }

    function renderBatchSummary(state) {
        const batch = state.batch || {};
        return `
            <div class="reports-batch-summary">
                <div>
                    <div class="text-xs text-base-content/50">Source</div>
                    <div class="font-medium">${escapeHtml(titleCase(batch.source))}</div>
                </div>
                <div>
                    <div class="text-xs text-base-content/50">Status</div>
                    <div>${statusBadge(batch.status)}</div>
                </div>
                <div>
                    <div class="text-xs text-base-content/50">Created</div>
                    <div class="text-sm">${escapeHtml(formatDateTime(batch.created_at))}</div>
                </div>
                <div>
                    <div class="text-xs text-base-content/50">Updated</div>
                    <div class="text-sm">${escapeHtml(formatDateTime(batch.updated_at))}</div>
                </div>
                <div>
                    <div class="text-xs text-base-content/50">Progress</div>
                    <div class="font-medium">${escapeHtml(state.progress_percent ?? batch.progress_percent ?? 0)}%</div>
                </div>
            </div>
        `;
    }

    function renderTaskRows(taskRuns) {
        if (!Array.isArray(taskRuns) || !taskRuns.length) {
            return '<tr><td colspan="7" class="text-center text-base-content/50 py-6">No task runs recorded</td></tr>';
        }
        return taskRuns.map((run) => {
            const rawId = `task-run-${String(run.id || "").replace(/[^a-zA-Z0-9_-]/g, "")}`;
            return `
                <tr>
                    <td>
                        <div class="font-medium">${escapeHtml(run.task_key)}</div>
                        <div class="text-xs text-base-content/50">${escapeHtml(run.class_name || run.module_name)}</div>
                    </td>
                    <td>${statusBadge(run.status)}</td>
                    <td class="text-xs">${escapeHtml(formatDateTime(run.started_at))}</td>
                    <td class="text-xs">${escapeHtml(formatDateTime(run.ended_at))}</td>
                    <td class="text-xs">${escapeHtml(formatDuration(run.started_at, run.ended_at))}</td>
                    <td class="max-w-xs">${run.error ? `<span class="text-error text-xs">${escapeHtml(run.error)}</span>` : '<span class="text-xs text-base-content/40">None</span>'}</td>
                    <td>
                        <details class="reports-task-json">
                            <summary class="btn btn-ghost btn-xs">JSON</summary>
                            <div class="reports-task-json-grid">
                                <div>
                                    <div class="text-xs font-medium mb-1">Input</div>
                                    <pre id="${escapeHtml(rawId)}-input">${escapeHtml(safeJsonBlock(run.input_json))}</pre>
                                </div>
                                <div>
                                    <div class="text-xs font-medium mb-1">Output</div>
                                    <pre id="${escapeHtml(rawId)}-output">${escapeHtml(safeJsonBlock(run.output_json))}</pre>
                                </div>
                            </div>
                        </details>
                    </td>
                </tr>
            `;
        }).join("");
    }

    function renderDocumentDetails(documentPayload) {
        const filename = documentPayload.original_filename || documentPayload.file_path || documentPayload.id;
        const currentStep = documentPayload.current_step || {};
        const lastStep = documentPayload.last_completed_step || {};
        return `
            <section class="reports-document-detail">
                <div class="reports-document-header">
                    <div class="min-w-0">
                        <h3 class="font-medium truncate">${escapeHtml(filename)}</h3>
                        <p class="text-xs text-base-content/50 font-mono truncate">${escapeHtml(documentPayload.id)}</p>
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                        ${statusBadge(documentPayload.status)}
                        <span class="text-xs text-base-content/50">${escapeHtml(documentPayload.progress_percent || 0)}%</span>
                    </div>
                </div>
                <div class="reports-step-strip">
                    <div>
                        <span>Current</span>
                        <strong>${escapeHtml(currentStep.label || currentStep.key || "Pending")}</strong>
                    </div>
                    <div>
                        <span>Last Completed</span>
                        <strong>${escapeHtml(lastStep.label || lastStep.key || "None")}</strong>
                    </div>
                </div>
                <div class="overflow-x-auto">
                    <table class="table table-sm reports-task-table">
                        <thead>
                            <tr>
                                <th>Task</th>
                                <th>Status</th>
                                <th>Started</th>
                                <th>Ended</th>
                                <th>Duration</th>
                                <th>Error</th>
                                <th>Raw</th>
                            </tr>
                        </thead>
                        <tbody>${renderTaskRows(documentPayload.task_runs || [])}</tbody>
                    </table>
                </div>
            </section>
        `;
    }

    function renderBatchDetails(state) {
        const batch = state.batch || {};
        batchDetailTitle.textContent = batch.original_filename || batch.id || "Batch details";
        batchDetailSubtitle.textContent = batch.id || "";
        batchDetailProcessingLink.href = `/app/batches/${encodeURIComponent(batch.id || "")}`;
        batchDetailProcessingLink.classList.toggle("hidden", !batch.id);
        const documents = Array.isArray(state.documents) ? state.documents : [];
        batchDetailBody.innerHTML = `
            ${renderBatchSummary(state)}
            <div class="reports-document-list">
                ${documents.length ? documents.map(renderDocumentDetails).join("") : '<div class="empty-panel">No documents recorded for this batch</div>'}
            </div>
        `;
    }

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
            const state = await window.DocFlow.apiGet(`/api/batches/${encodeURIComponent(batchId)}/processing-state`);
            renderBatchDetails(state || {});
        } catch (error) {
            batchDetailBody.innerHTML = `<div class="empty-panel text-error">${escapeHtml(error.message || "Unable to load batch details")}</div>`;
            if (window.DocFlow) {
                window.DocFlow.showToast(error.message || "Unable to load batch details", "error");
            }
        }
    }

    function render(payload) {
        const summary = payload.summary || {};
        renderMetric("reports-total-batches", summary.total_batches);
        renderMetric("reports-total-documents", summary.total_documents);
        renderMetric("reports-completed-documents", summary.documents_completed);
        renderMetric("reports-failed-documents", summary.documents_failed);
        renderMetric("reports-reviewed-documents", summary.documents_reviewed);
        document.getElementById("reports-average-processing").textContent = summary.average_processing_display || "n/a";
        document.getElementById("reports-review-total").textContent = `${payload.review?.total || 0} review items`;
        renderSimpleRows(
            "reports-status-body",
            payload.document_statuses || [],
            "status",
            "count",
            "No document status data",
        );
        renderSourceRows(payload.batch_sources || []);
        renderSimpleRows(
            "reports-review-body",
            payload.review?.by_status || [],
            "status",
            "count",
            "No review data",
        );
        renderRecentBatches(payload.recent_batches || []);
    }

    async function loadReports() {
        const payload = await window.DocFlow.apiGet("/api/reports/summary");
        render(payload || {});
    }

    document.getElementById("reports-refresh-button").addEventListener("click", () => {
        loadReports().catch((error) => window.DocFlow.showToast(error.message || "Unable to load reports", "error"));
    });

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
