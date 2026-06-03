(function () {
    "use strict";

    const workspace = document.getElementById("reports-workspace");
    if (!workspace) {
        return;
    }

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
            <tr>
                <td class="text-xs">${escapeHtml(window.DocFlow.formatDateTime(batch.created_at))}</td>
                <td>${escapeHtml(titleCase(batch.source))}</td>
                <td class="font-mono text-xs">${escapeHtml(batch.id)}</td>
                <td>${statusBadge(batch.status)}</td>
                <td class="text-right">${escapeHtml(batch.progress_percent || 0)}%</td>
            </tr>
        `).join("");
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

    loadReports().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load reports", "error");
    });
})();
