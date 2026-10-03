/** Rendering and presentation for split-results. */
export function createView(deps) {
    const { tableBody, totalFiles, documentsCreated, documentsContinuing, successful, failed, docFlow } = deps;

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
        return `<span class="badge ${docFlow.statusBadgeClass(status, "pending")} badge-sm">${escapeHtml(docFlow.statusLabel(status, "pending"))}</span>`;
    }

    function pageLabel(child) {
        if (child.page_start && child.page_end) {
            return child.page_start === child.page_end ? `Page ${child.page_start}` : `Pages ${child.page_start}-${child.page_end}`;
        }
        if (Array.isArray(child.pages) && child.pages.length) {
            if (child.pages.length === 1) {
                return `Page ${child.pages[0]}`;
            }
            return `Pages ${child.pages.join(", ")}`;
        }
        return "-";
    }

    function renderSummary(summary) {
        totalFiles.textContent = summary.total_files || 0;
        documentsCreated.textContent = summary.documents_created || 0;
        if (documentsContinuing) {
            const count = Number(summary.documents_continuing || 0);
            documentsContinuing.textContent = `${count} original${count === 1 ? "" : "s"} continued`;
        }
        successful.textContent = summary.successful || 0;
        failed.textContent = summary.failed || 0;
    }

    function childRows(source) {
        if (source.split_outcome === "single_document") {
            return `<tr class="split-child-row"><td colspan="4" class="text-sm">No split needed — processing the original document. ${escapeHtml(pageLabel(source))} | ${escapeHtml(source.category || "uncategorized")} | ${escapeHtml(source.split_confidence || "unknown")} confidence</td></tr>`;
        }
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
                    <td class="text-sm" data-label="Document">Child</td>
                    <td data-label="Status">${statusBadge(child.status)}</td>
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
                const extractionId = source.extraction_document_id || (firstChild && firstChild.document_id);
                const action = extractionId
                    ? `<a href="/app/documents/${encodeURIComponent(extractionId)}/extraction" class="btn btn-primary btn-xs">View Extraction</a>`
                    : '<span class="text-xs text-base-content/40">No extraction</span>';
                return `
                    <tr class="split-source-row">
                        <td class="text-sm font-medium">${escapeHtml(source.source_file || source.document_id)}</td>
                        <td class="text-sm" data-label="Documents Created">${Number(source.documents_created || 0)}</td>
                        <td data-label="Status">${statusBadge(source.status)}</td>
                        <td>${action}</td>
                    </tr>
                    ${childRows(source)}
                `;
            })
            .join("");
    }

    return { escapeHtml, titleCase, statusBadge, pageLabel, renderSummary, childRows, renderSources };
}
