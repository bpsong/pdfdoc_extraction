(function () {
    "use strict";

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function renderIframeFallback(container, pdfUrl, title) {
        if (!container) {
            return;
        }
        if (!pdfUrl) {
            container.innerHTML = '<div class="empty-panel">Source PDF unavailable</div>';
            return;
        }
        const safeUrl = escapeHtml(pdfUrl);
        const safeTitle = escapeHtml(title || "Source PDF preview");
        container.innerHTML = `
            <iframe class="review-pdf-frame" src="${safeUrl}" title="${safeTitle}"></iframe>
            <div class="sr-only">
                PDF preview fallback. <a href="${safeUrl}" target="_blank" rel="noreferrer">Open PDF</a>
            </div>
        `;
    }

    window.DocFlowPdfViewer = {
        renderIframeFallback,
    };
})();
