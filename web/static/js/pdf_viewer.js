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

    function fitHashValue(fitMode) {
        if (fitMode === "page") {
            return "page-fit";
        }
        if (fitMode === "width") {
            return "page-width";
        }
        return "";
    }

    function withFitMode(pdfUrl, fitMode) {
        const zoom = fitHashValue(fitMode);
        if (!pdfUrl || !zoom) {
            return pdfUrl;
        }
        const text = String(pdfUrl);
        const hashIndex = text.indexOf("#");
        const base = hashIndex >= 0 ? text.slice(0, hashIndex) : text;
        const hash = hashIndex >= 0 ? text.slice(hashIndex + 1) : "";
        const params = new URLSearchParams(hash);
        params.set("zoom", zoom);
        return `${base}#${params.toString()}`;
    }

    function renderIframeFallback(container, pdfUrl, title, options) {
        if (!container) {
            return;
        }
        if (!pdfUrl) {
            container.innerHTML = '<div class="empty-panel">Source PDF unavailable</div>';
            return;
        }
        const safeUrl = escapeHtml(withFitMode(pdfUrl, options && options.fitMode));
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
        withFitMode,
    };
})();
