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
        return `<pre class="text-xs whitespace-pre-wrap bg-base-200 rounded p-3 overflow-auto max-h-80">${escapeHtml(JSON.stringify(value || {}, null, 2))}</pre>`;
    }

    function renderRows() {
        countBadge.textContent = String(failures.length);
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
                    ? `<iframe class="extraction-pdf-frame" src="${escapeHtml(payload.source_preview_url || payload.preview_url)}" title="Source PDF preview"></iframe>`
                    : '<div class="empty-panel">Source PDF preview unavailable</div>'}
                <div class="mt-4">
                    <div class="text-xs font-medium mb-1">Failed Task Output</div>
                    ${jsonBlock(failedTask.output || {})}
                </div>
            </div>
        `;
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
            const payload = await window.DocFlow.apiGet("/api/failures");
            failures = Array.isArray(payload.failures) ? payload.failures : [];
            renderRows();
            const params = new URLSearchParams(window.location.search);
            const requestedDocument = params.get("document_id");
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

    loadFailures();
})();
