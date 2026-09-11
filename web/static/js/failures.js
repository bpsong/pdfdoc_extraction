(function () {
    "use strict";

    const workspace = document.getElementById("failures-workspace");
    if (!workspace) {
        return;
    }

    const tableBody = document.getElementById("failures-table-body");
    const countBadge = document.getElementById("failures-count");
    const detailTitle = document.getElementById("failure-detail-title");
    const detailSubtitle = document.getElementById("failure-detail-subtitle");
    const detailBody = document.getElementById("failure-detail-body");
    const sourceLink = document.getElementById("failure-source-link");
    let failures = [];
    let pdfViewer = null;
    const pageState = { total: 0, limit: 25, offset: 0, sortBy: "failure_at", sortDir: "desc" };
    const escapeHtml = window.DocFlow.escapeHtml;
    const titleCase = window.DocFlow.titleCase;

    function formatDateTime(value) {
        return window.DocFlow.formatDateTime(value) || "n/a";
    }

    function shortText(value, maxLength) {
        const text = String(value || "");
        if (text.length <= maxLength) {
            return text;
        }
        return `${text.slice(0, maxLength - 1)}...`;
    }

    function jsonBlock(value) {
        return `<pre class="text-xs whitespace-pre-wrap bg-base-200 rounded p-3 overflow-auto max-h-80">${window.DocFlow.escapeHtml(JSON.stringify(value || {}, null, 2))}</pre>`;
    }

    function renderRows() {
        countBadge.textContent = String(pageState.total);
        if (!failures.length) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-base-content/50 py-10">No failed documents</td></tr>';
            return;
        }
        tableBody.innerHTML = failures.map((item) => {
            const document = item.document || {};
            const sourceDocument = item.source_document || document;
            const failedTask = item.failed_task || {};
            const failure = item.failure || {};
            const group = item.group || {};
            const groupCount = Number(group.count || 1);
            return `
                <tr>
                    <td>
                        <div class="font-medium">${escapeHtml(sourceDocument.filename || document.filename || document.id)}</div>
                        <div class="text-xs text-base-content/50 font-mono">${escapeHtml(sourceDocument.id || document.id || "")}</div>
                        ${groupCount > 1 ? `<div class="badge badge-error badge-xs mt-1">${groupCount} split documents affected</div>` : ""}
                    </td>
                    <td>
                        <div class="text-sm">${escapeHtml(failedTask.task_key || "")}</div>
                        <div class="text-xs text-base-content/50">${escapeHtml(failedTask.class_name || "")}</div>
                    </td>
                    <td class="max-w-sm text-error text-xs">${escapeHtml(shortText(failure.message || failedTask.error, 180))}</td>
                    <td class="text-xs">${escapeHtml(formatDateTime(item.failure_at || failedTask.ended_at))}</td>
                    <td><button class="btn btn-error btn-xs" type="button" data-failure-document="${escapeHtml(document.id)}">Open Failure</button></td>
                </tr>
            `;
        }).join("");
    }

    function renderPagination() {
        const start = pageState.total ? pageState.offset + 1 : 0;
        const end = Math.min(pageState.offset + failures.length, pageState.total);
        document.getElementById("failures-page-summary").textContent = `${start}-${end} of ${pageState.total}`;
        document.getElementById("failures-prev").disabled = pageState.offset === 0;
        document.getElementById("failures-next").disabled = pageState.offset + pageState.limit >= pageState.total;
        document.querySelectorAll("[data-failure-sort]").forEach((button) => {
            const active = button.dataset.failureSort === pageState.sortBy;
            button.setAttribute("aria-sort", active ? (pageState.sortDir === "asc" ? "ascending" : "descending") : "none");
            button.querySelector("span").textContent = active ? (pageState.sortDir === "asc" ? "↑" : "↓") : "";
        });
    }

    function renderDetail(payload) {
        const documentPayload = payload.document || {};
        const sourceDocument = payload.source_document || documentPayload;
        const splitSegment = payload.split_segment || {};
        const failure = payload.failure || {};
        const failedTask = payload.latest_failed_task || {};
        const relatedFailures = Array.isArray(payload.related_failures) ? payload.related_failures : [];
        detailTitle.textContent = sourceDocument.filename || documentPayload.filename || documentPayload.id || "Failure Detail";
        detailSubtitle.textContent = `${failedTask.task_key || "failed task"} | ${titleCase(failure.failure_type || "task_failed")}`;
        sourceLink.href = payload.source_preview_url || payload.preview_url || "#";
        sourceLink.classList.toggle("hidden", !(payload.source_preview_url || payload.preview_url));
        if (pdfViewer) {
            pdfViewer.destroy();
            pdfViewer = null;
        }
        detailBody.innerHTML = `
            <div>
                <div class="alert alert-error mb-4">
                    <div>
                        <div class="font-semibold">Manual source PDF examination required</div>
                        <div class="text-sm">${escapeHtml(failure.operator_action || "Inspect/correct the source PDF or configuration outside this failed workflow, then re-ingest as a new document if appropriate.")}</div>
                    </div>
                </div>
                <div class="grid gap-3 text-sm">
                    <div>
                        <div class="text-xs text-base-content/50">Error</div>
                        <div class="text-error whitespace-pre-wrap">${escapeHtml(failure.message || failedTask.error || "Task failed")}</div>
                    </div>
                    <div>
                        <div class="text-xs text-base-content/50">Original Source PDF</div>
                        <div>${escapeHtml(sourceDocument.filename || sourceDocument.id || "")}</div>
                        <div class="text-xs font-mono text-base-content/50">${escapeHtml(sourceDocument.id || "")}</div>
                    </div>
                    ${splitSegment && splitSegment.document_id ? `
                        <div>
                            <div class="text-xs text-base-content/50">Failed Split Segment</div>
                            <div>${escapeHtml(splitSegment.filename || documentPayload.filename || "")}</div>
                            <div class="text-xs text-base-content/60">
                                Pages ${escapeHtml((splitSegment.pages || []).join(", ") || `${splitSegment.page_start || "?"}-${splitSegment.page_end || "?"}`)}
                                | ${escapeHtml(splitSegment.category || "unknown")}
                                | ${escapeHtml(splitSegment.confidence || "unknown")} confidence
                            </div>
                        </div>
                    ` : ""}
                    ${relatedFailures.length > 1 ? `
                        <div>
                            <div class="text-xs text-base-content/50">Related Split Failures</div>
                            <div class="text-sm">${relatedFailures.length} split documents failed with the same task error.</div>
                        </div>
                    ` : ""}
                    <div>
                        <div class="text-xs text-base-content/50">Source Path</div>
                        <div class="text-xs font-mono break-all">${escapeHtml(sourceDocument.file_path || documentPayload.file_path || "")}</div>
                    </div>
                    <div>
                        <div class="text-xs text-base-content/50">Provider Job</div>
                        <div class="text-xs font-mono">${escapeHtml(failure.provider_job_id || "n/a")}</div>
                    </div>
                </div>
                <div class="mt-4">
                    <div class="text-xs font-medium mb-1">Failure Metadata</div>
                    ${jsonBlock({ policy: failure.policy, segments: failure.segments })}
                </div>
            </div>
            <div>
                ${payload.source_preview_url || payload.preview_url
                    ? '<div id="failure-pdf-viewer" class="failure-pdf-viewer"></div>'
                    : '<div class="empty-panel">Source PDF preview unavailable</div>'}
                <div class="mt-4">
                    <div class="text-xs font-medium mb-1">Failed Task Output</div>
                    ${jsonBlock(failedTask.output || {})}
                </div>
            </div>
        `;
        const previewUrl = payload.source_preview_url || payload.preview_url;
        const viewerContainer = document.getElementById("failure-pdf-viewer");
        if (previewUrl && viewerContainer) {
            pdfViewer = window.DocFlowPdfViewer.mount(
                viewerContainer,
                { url: previewUrl, title: `${sourceDocument.filename || "Document"} source PDF` },
            );
        }
    }

    async function openFailure(documentId) {
        if (!documentId) {
            return;
        }
        detailTitle.textContent = "Loading failure";
        detailSubtitle.textContent = documentId;
        sourceLink.classList.add("hidden");
        detailBody.innerHTML = '<div class="empty-panel lg:col-span-2"><span class="loading loading-spinner loading-sm"></span> Loading failure detail</div>';
        try {
            const payload = await window.DocFlow.apiGet(`/api/failures/${encodeURIComponent(documentId)}`);
            renderDetail(payload || {});
        } catch (error) {
            detailBody.innerHTML = `<div class="empty-panel text-error lg:col-span-2">${escapeHtml(error.message || "Unable to load failure")}</div>`;
            window.DocFlow.showToast(error.message || "Unable to load failure", "error");
        }
    }

    async function loadFailures() {
        try {
            const params = new URLSearchParams({
                limit: String(pageState.limit),
                offset: String(pageState.offset),
                sort_by: pageState.sortBy,
                sort_dir: pageState.sortDir,
            });
            const payload = await window.DocFlow.apiGet(`/api/failures?${params}`);
            failures = Array.isArray(payload.failures) ? payload.failures : [];
            pageState.total = Number(payload.total || 0);
            pageState.limit = Number(payload.limit || pageState.limit);
            pageState.offset = Number(payload.offset || 0);
            renderRows();
            renderPagination();
            const locationParams = new URLSearchParams(window.location.search);
            const requestedDocument = locationParams.get("document_id");
            const first = requestedDocument || (failures[0] && failures[0].document && failures[0].document.id);
            if (first) {
                await openFailure(first);
            }
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="5" class="text-center text-error py-10">${escapeHtml(error.message || "Unable to load failures")}</td></tr>`;
            window.DocFlow.showToast(error.message || "Unable to load failures", "error");
        }
    }

    tableBody.addEventListener("click", (event) => {
        const button = event.target.closest("[data-failure-document]");
        if (!button) {
            return;
        }
        openFailure(button.dataset.failureDocument);
    });

    workspace.addEventListener("click", (event) => {
        const sortButton = event.target.closest("[data-failure-sort]");
        if (!sortButton) {
            return;
        }
        const sortBy = sortButton.dataset.failureSort;
        pageState.sortDir = pageState.sortBy === sortBy && pageState.sortDir === "asc" ? "desc" : "asc";
        pageState.sortBy = sortBy;
        pageState.offset = 0;
        loadFailures();
    });
    document.getElementById("failures-prev").addEventListener("click", () => {
        pageState.offset = Math.max(0, pageState.offset - pageState.limit);
        loadFailures();
    });
    document.getElementById("failures-next").addEventListener("click", () => {
        pageState.offset += pageState.limit;
        loadFailures();
    });

    loadFailures();
})();
