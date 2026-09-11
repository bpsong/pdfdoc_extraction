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
    const reviewSummary = document.getElementById("extraction-review-summary");
    const previousButton = document.getElementById("previous-document-button");
    const nextButton = document.getElementById("next-document-button");
    let pdfViewer = null;

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
        return `<span class="badge ${window.DocFlow.statusBadgeClass(status, "unknown")} badge-sm">${escapeHtml(window.DocFlow.statusLabel(status, "unknown"))}</span>`;
    }

    function confidenceBadge(field, review) {
        if (field.confidence === null || field.confidence === undefined) {
            const label = review && review.status === "completed" ? "No model confidence" : "N/A confidence";
            return `<span class="badge badge-ghost badge-sm" title="Original extraction confidence">${label}</span>`;
        }
        const value = Number(field.confidence);
        const percent = Number.isFinite(value) ? `${Math.round(value * 100)}%` : "N/A";
        const classes = {
            high: "badge-success",
            medium: "badge-warning",
            low: "badge-error",
            missing: "badge-ghost",
        };
        const band = titleCase(field.confidence_band || "unknown");
        return `<span class="badge ${classes[field.confidence_band] || "badge-ghost"} badge-sm" title="Original extraction confidence">${escapeHtml(band)} confidence · ${escapeHtml(percent)}</span>`;
    }

    function nestedConfidenceSummary(field) {
        const nested = field.confidence_details && field.confidence_details.nested_confidences;
        if (!nested || typeof nested !== "object" || !Object.keys(nested).length) {
            return "";
        }
        const items = Object.entries(nested).slice(0, 4).map(([path, detail]) => {
            const confidence = Number(detail && detail.confidence);
            const percent = Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : "N/A";
            return `${path}: ${percent}`;
        });
        const suffix = Object.keys(nested).length > items.length ? " ..." : "";
        return `<div class="text-xs text-base-content/50 mt-1">${escapeHtml(items.join(", ") + suffix)}</div>`;
    }

    function renderPreview(payload) {
        const previewUrl = payload.document && payload.document.preview_url;
        if (pdfViewer) {
            pdfViewer.destroy();
            pdfViewer = null;
        }
        if (!previewUrl) {
            previewBody.innerHTML = '<div class="empty-panel">No preview available</div>';
            return;
        }
        pdfViewer = window.DocFlowPdfViewer.mount(
            previewBody,
            { url: previewUrl, title: `${payload.document.filename || "Document"} source PDF` },
        );
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

    function effectiveReviewStatus(field, review) {
        if (review && review.status === "completed" && field.review_status === "required") {
            return "reviewed";
        }
        return field.review_status;
    }

    function renderFields(fields, review) {
        if (!fields || !fields.length) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-base-content/50 py-10">No extraction fields</td></tr>';
            return;
        }
        tableBody.innerHTML = fields.map((field) => `
            <tr class="${field.requires_review && (!review || review.status !== "completed") ? "bg-warning/10" : ""} cursor-pointer" data-field-key="${escapeHtml(field.field_key)}" tabindex="0">
                <td>
                    <div class="font-medium">${escapeHtml(field.field_alias || field.field_key)}</div>
                    <div class="text-xs text-base-content/50">${escapeHtml(field.field_key)}</div>
                </td>
                <td class="max-w-sm">${formatValue(field.extracted_value)}${nestedConfidenceSummary(field)}</td>
                <td class="max-w-sm">${formatValue(field.final_value)}</td>
                <td>${confidenceBadge(field, review)}</td>
                <td>${statusBadge(effectiveReviewStatus(field, review))}</td>
            </tr>
        `).join("");
        tableBody.querySelectorAll("[data-field-key]").forEach((row) => {
            const field = fields.find((item) => String(item.field_key) === row.dataset.fieldKey);
            const selectField = () => {
                if (pdfViewer && field) {
                    pdfViewer.selectField(field.field_key, field, [field.field_key], field.field_alias || field.field_key);
                }
            };
            row.addEventListener("click", selectField);
            row.addEventListener("focus", selectField);
            row.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    selectField();
                }
            });
        });
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
        const completedReview = payload.review && payload.review.status === "completed";
        if (reviewSummary) {
            reviewSummary.classList.toggle("hidden", !completedReview);
            reviewSummary.innerHTML = completedReview
                ? '<strong>Human review complete.</strong> Fields that originally required attention are marked Reviewed. Confidence still describes the original extraction.'
                : "";
        }
        renderPreview(payload);
        renderFiles(payload.files || []);
        renderFields(payload.fields || [], payload.review || null);
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
