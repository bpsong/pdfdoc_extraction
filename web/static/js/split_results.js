(function () {
    "use strict";

    const workspace = document.getElementById("split-results-workspace");
    if (!workspace) {
        return;
    }

    const batchId = workspace.dataset.batchId || "";
    const tableBody = document.getElementById("split-results-table-body");
    const totalFiles = document.getElementById("split-total-files");
    const documentsCreated = document.getElementById("split-documents-created");
    const successful = document.getElementById("split-successful");
    const failed = document.getElementById("split-failed");

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

    function statusBadge(status) {
        const normalized = String(status || "pending").toLowerCase();
        const badgeClass = normalized === "failed"
            ? "badge-error"
            : normalized === "success" || normalized === "completed" || normalized === "split_completed"
                ? "badge-success"
                : normalized === "review_required" || normalized === "in_review"
                    ? "badge-warning"
                    : "badge-ghost";
        return `<span class="badge ${badgeClass} badge-sm">${escapeHtml(titleCase(normalized))}</span>`;
    }

    function pageLabel(child) {
        if (child.page_start && child.page_end) {
            return child.page_start === child.page_end ? `Page ${child.page_start}` : `Pages ${child.page_start}-${child.page_end}`;
        }
        if (Array.isArray(child.pages) && child.pages.length) {
            return `Pages ${child.pages.join(", ")}`;
        }
        return "-";
    }

    function renderSummary(summary) {
        totalFiles.textContent = summary.total_files || 0;
        documentsCreated.textContent = summary.documents_created || 0;
        successful.textContent = summary.successful || 0;
        failed.textContent = summary.failed || 0;
    }

    function childRows(source) {
        if (!source.children || !source.children.length) {
            return `
                <tr class="split-child-row">
                    <td colspan="4" class="text-sm text-base-content/50">No child documents were created for this source.</td>
                </tr>
            `;
        }

        return source.children
            .map((child) => `
                <tr class="split-child-row bg-base-200/40">
                    <td>
                        <div class="text-sm font-medium">${escapeHtml(child.filename || child.document_id)}</div>
                        <div class="text-xs text-base-content/50">${escapeHtml(pageLabel(child))} | ${escapeHtml(child.category || "uncategorized")} | ${escapeHtml(child.split_confidence || "unknown")} confidence</div>
                    </td>
                    <td class="text-sm">Child</td>
                    <td>${statusBadge(child.status)}</td>
                    <td>
                        <a href="/app/documents/${encodeURIComponent(child.document_id)}/extraction" class="btn btn-ghost btn-xs">Extraction</a>
                    </td>
                </tr>
            `)
            .join("");
    }

    function renderSources(sources) {
        if (!sources || !sources.length) {
            tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-base-content/50 py-10">No split results</td></tr>';
            return;
        }

        tableBody.innerHTML = sources
            .map((source) => {
                const firstChild = source.children && source.children[0];
                const action = firstChild
                    ? `<a href="/app/documents/${encodeURIComponent(firstChild.document_id)}/extraction" class="btn btn-primary btn-xs">View Extraction</a>`
                    : '<span class="text-xs text-base-content/40">No extraction</span>';
                return `
                    <tr>
                        <td class="text-sm font-medium">${escapeHtml(source.source_file || source.document_id)}</td>
                        <td class="text-sm">${Number(source.documents_created || 0)}</td>
                        <td>${statusBadge(source.status)}</td>
                        <td>${action}</td>
                    </tr>
                    ${childRows(source)}
                `;
            })
            .join("");
    }

    async function loadSplitResults() {
        if (!batchId) {
            tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-base-content/50 py-10">No batch selected</td></tr>';
            return;
        }

        try {
            const payload = await window.DocFlow.apiGet(`/api/batches/${encodeURIComponent(batchId)}/split-results`);
            renderSummary(payload.summary || {});
            renderSources(payload.sources || []);
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-error py-10">${escapeHtml(error.message || "Unable to load split results")}</td></tr>`;
            if (window.DocFlow) {
                window.DocFlow.showToast(error.message || "Unable to load split results", "error");
            }
        }
    }

    loadSplitResults();
})();
