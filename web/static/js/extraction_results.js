(function () {
    "use strict";

    const workspace = document.getElementById("extraction-results-workspace");
    if (!workspace) {
        return;
    }

    const documentId = workspace.dataset.documentId || "";
    const title = document.getElementById("extraction-document-title");
    const statusLabel = document.getElementById("extraction-document-status");
    const previewBody = document.getElementById("extraction-preview-body");
    const fileList = document.getElementById("extraction-file-list");
    const tableBody = document.getElementById("extraction-fields-table-body");
    const jobLabel = document.getElementById("extraction-job-label");
    const providerLabel = document.getElementById("extraction-provider-label");
    const rawPayload = document.getElementById("extraction-raw-payload");
    const reviewLink = document.getElementById("extraction-review-link");
    const previousButton = document.getElementById("previous-document-button");
    const nextButton = document.getElementById("next-document-button");

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

    function formatValue(value) {
        if (value === null || value === undefined) {
            return '<span class="text-base-content/40">N/A</span>';
        }
        if (typeof value === "object") {
            return `<code class="text-xs whitespace-pre-wrap">${escapeHtml(JSON.stringify(value, null, 2))}</code>`;
        }
        return escapeHtml(value);
    }

    function statusBadge(status) {
        const normalized = String(status || "unknown").toLowerCase();
        const badgeClass = normalized === "review_required" || normalized === "in_review" || normalized === "required"
            ? "badge-warning"
            : normalized === "corrected" || normalized === "review_completed" || normalized === "not_required"
                ? "badge-success"
                : normalized === "failed"
                    ? "badge-error"
                    : "badge-ghost";
        return `<span class="badge ${badgeClass} badge-sm">${escapeHtml(titleCase(normalized))}</span>`;
    }

    function confidenceBadge(field) {
        if (field.confidence === null || field.confidence === undefined) {
            return '<span class="badge badge-ghost badge-sm">N/A</span>';
        }
        const value = Number(field.confidence);
        const percent = Number.isFinite(value) ? `${Math.round(value * 100)}%` : "N/A";
        const classes = {
            high: "badge-success",
            medium: "badge-warning",
            low: "badge-error",
            missing: "badge-ghost",
        };
        return `<span class="badge ${classes[field.confidence_band] || "badge-ghost"} badge-sm">${escapeHtml(percent)}</span>`;
    }

    function renderPreview(payload) {
        const previewUrl = payload.document && payload.document.preview_url;
        if (!previewUrl) {
            previewBody.innerHTML = '<div class="empty-panel">No preview available</div>';
            return;
        }
        previewBody.innerHTML = `<iframe class="extraction-pdf-frame" src="${escapeHtml(previewUrl)}" title="Source PDF preview"></iframe>`;
    }

    function renderFiles(files) {
        if (!files || !files.length) {
            fileList.innerHTML = '<div class="text-xs text-base-content/50 px-4 py-3">No registered files</div>';
            return;
        }
        fileList.innerHTML = files.map((file) => `
            <div class="extraction-file-row">
                <div class="min-w-0">
                    <div class="text-sm font-medium truncate">${escapeHtml(file.filename || file.file_type || "file")}</div>
                    <div class="text-xs text-base-content/50 truncate">${escapeHtml(file.file_type || "")}</div>
                </div>
            </div>
        `).join("");
    }

    function renderFields(fields) {
        if (!fields || !fields.length) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-base-content/50 py-10">No extraction fields</td></tr>';
            return;
        }
        tableBody.innerHTML = fields.map((field) => `
            <tr class="${field.requires_review ? "bg-warning/10" : ""}">
                <td>
                    <div class="font-medium">${escapeHtml(field.field_alias || field.field_key)}</div>
                    <div class="text-xs text-base-content/50">${escapeHtml(field.field_key)}</div>
                </td>
                <td class="max-w-sm">${formatValue(field.extracted_value)}</td>
                <td class="max-w-sm">${formatValue(field.final_value)}</td>
                <td>${confidenceBadge(field)}</td>
                <td>${statusBadge(field.review_status)}</td>
            </tr>
        `).join("");
    }

    function wireSiblingButtons(payload) {
        const siblings = payload.siblings || [];
        const index = siblings.findIndex((item) => item.id === documentId);
        const previous = index > 0 ? siblings[index - 1] : null;
        const next = index >= 0 && index < siblings.length - 1 ? siblings[index + 1] : null;
        previousButton.disabled = !previous;
        nextButton.disabled = !next;
        previousButton.onclick = previous ? () => { window.location.href = `/app/documents/${encodeURIComponent(previous.id)}/extraction`; } : null;
        nextButton.onclick = next ? () => { window.location.href = `/app/documents/${encodeURIComponent(next.id)}/extraction`; } : null;
    }

    function renderPayload(payload) {
        const documentPayload = payload.document || {};
        const latest = payload.latest_extraction;
        title.textContent = documentPayload.filename || documentPayload.id || "Document";
        statusLabel.innerHTML = `${statusBadge(documentPayload.status)} ${documentPayload.document_type ? escapeHtml(documentPayload.document_type) : ""}`;
        jobLabel.textContent = latest ? `Job ${latest.provider_job_id || latest.id || ""}` : "No extraction result";
        providerLabel.textContent = latest ? latest.provider || "provider" : "No provider";
        rawPayload.textContent = JSON.stringify(latest ? latest.data : {}, null, 2);
        if (payload.review_item_id) {
            reviewLink.href = `/app/review/${encodeURIComponent(payload.review_item_id)}`;
            reviewLink.classList.remove("hidden");
        } else {
            reviewLink.classList.add("hidden");
        }
        renderPreview(payload);
        renderFiles(payload.files || []);
        renderFields(payload.fields || []);
        wireSiblingButtons(payload);
    }

    async function loadExtraction() {
        if (!documentId) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-error py-10">No document selected</td></tr>';
            return;
        }
        try {
            const payload = await window.DocFlow.apiGet(`/api/documents/${encodeURIComponent(documentId)}/extraction`);
            renderPayload(payload);
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="5" class="text-center text-error py-10">${escapeHtml(error.message || "Unable to load extraction")}</td></tr>`;
            previewBody.innerHTML = '<div class="empty-panel">Preview unavailable</div>';
            if (window.DocFlow) {
                window.DocFlow.showToast(error.message || "Unable to load extraction", "error");
            }
        }
    }

    loadExtraction();
})();
