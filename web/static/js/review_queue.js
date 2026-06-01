(function () {
    "use strict";

    const state = {
        items: [],
        filter: "all",
        search: "",
    };

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function titleCase(value) {
        return String(value || "")
            .replace(/[_-]+/g, " ")
            .replace(/\s+/g, " ")
            .trim()
            .replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Unknown";
    }

    function statusBadge(status) {
        const normalized = String(status || "pending").toLowerCase();
        const badgeClass = normalized === "completed"
            ? "badge-success"
            : normalized === "in_review"
                ? "badge-info"
                : normalized === "pending"
                    ? "badge-warning"
                    : "badge-ghost";
        return `<span class="badge ${badgeClass} badge-sm">${escapeHtml(titleCase(normalized))}</span>`;
    }

    function confidenceText(value) {
        if (value === null || value === undefined || value === "") {
            return "Missing";
        }
        const numeric = Number(value);
        if (Number.isNaN(numeric)) {
            return escapeHtml(value);
        }
        return `${Math.round(numeric * 100)}%`;
    }

    function confidenceBadge(value) {
        if (value === null || value === undefined || value === "") {
            return '<span class="badge badge-ghost badge-sm">Missing</span>';
        }
        const numeric = Number(value);
        const badgeClass = Number.isNaN(numeric)
            ? "badge-ghost"
            : numeric < 0.7
                ? "badge-error"
                : numeric < 0.9
                    ? "badge-warning"
                    : "badge-success";
        return `<span class="badge ${badgeClass} badge-sm">${confidenceText(value)}</span>`;
    }

    function itemHasLowConfidence(item) {
        const reason = String(item.reason || "").toLowerCase();
        const metadata = item.metadata || {};
        return reason.includes("confidence")
            || (metadata.low_confidence_fields || []).length > 0
            || (item.review_field_labels || []).length > 0;
    }

    function documentLabel(item) {
        const document = item.document || {};
        return document.filename || document.original_filename || item.document_id || "Document";
    }

    function documentType(item) {
        const document = item.document || {};
        return document.document_type || document.split_category || "Document";
    }

    function matchesSearch(item) {
        if (!state.search) {
            return true;
        }
        const haystack = [
            documentLabel(item),
            documentType(item),
            item.reason,
            item.queue_name,
            ...(item.review_field_labels || []),
        ].join(" ").toLowerCase();
        return haystack.includes(state.search.toLowerCase());
    }

    function matchesFilter(item) {
        if (state.filter === "all") {
            return true;
        }
        if (state.filter === "low_confidence") {
            return itemHasLowConfidence(item) && item.status !== "completed";
        }
        return item.status === state.filter;
    }

    function renderCounts() {
        const all = state.items.length;
        const low = state.items.filter((item) => itemHasLowConfidence(item) && item.status !== "completed").length;
        const inReview = state.items.filter((item) => item.status === "in_review").length;
        const completed = state.items.filter((item) => item.status === "completed").length;
        document.getElementById("review-count-all").textContent = String(all);
        document.getElementById("review-count-low").textContent = String(low);
        document.getElementById("review-count-in-review").textContent = String(inReview);
        document.getElementById("review-count-completed").textContent = String(completed);
    }

    function renderFilters() {
        document.querySelectorAll(".review-filter").forEach((button) => {
            const active = button.dataset.filter === state.filter;
            button.classList.toggle("btn-primary", active);
            button.classList.toggle("btn-outline", !active);
        });
    }

    function actionButtons(item) {
        const id = encodeURIComponent(item.id);
        if (item.status === "completed") {
            return `<a class="btn btn-outline btn-xs" href="/app/review/${id}">Open</a>`;
        }
        const claimLabel = item.status === "in_review" ? "Open" : "Claim";
        const claimClass = item.status === "in_review" ? "btn-outline" : "btn-primary";
        return `
            <div class="flex justify-end gap-2">
                <button class="btn ${claimClass} btn-xs review-claim-action" type="button" data-review-id="${escapeHtml(item.id)}">${claimLabel}</button>
                <a class="btn btn-ghost btn-xs" href="/app/review/${id}">View</a>
            </div>
        `;
    }

    function renderRows() {
        const body = document.getElementById("review-queue-body");
        const items = state.items.filter((item) => matchesFilter(item) && matchesSearch(item));
        if (!items.length) {
            body.innerHTML = '<tr><td colspan="7" class="text-center text-base-content/50 py-10">No review items</td></tr>';
            return;
        }

        body.innerHTML = items.map((item) => {
            const labels = item.review_field_labels || [];
            const labelText = labels.length ? labels.slice(0, 3).join(", ") : titleCase(item.reason);
            const extra = labels.length > 3 ? ` +${labels.length - 3}` : "";
            const document = item.document || {};
            const createdAt = window.DocFlow.formatDateTime(item.created_at);
            return `
                <tr class="hover">
                    <td class="px-4 py-3">
                        <a class="font-medium text-primary" href="/app/review/${encodeURIComponent(item.id)}">${escapeHtml(documentLabel(item))}</a>
                        <div class="text-xs text-base-content/50">${escapeHtml(createdAt)}</div>
                    </td>
                    <td>${escapeHtml(titleCase(documentType(item)))}</td>
                    <td class="max-w-sm">
                        <span class="text-sm">${escapeHtml(labelText)}${escapeHtml(extra)}</span>
                    </td>
                    <td>${confidenceBadge(item.lowest_confidence)}</td>
                    <td>${escapeHtml(item.queue_name || "default_review")}</td>
                    <td>${statusBadge(item.status)}</td>
                    <td class="text-right">${actionButtons(item)}</td>
                </tr>
            `;
        }).join("");

        body.querySelectorAll(".review-claim-action").forEach((button) => {
            button.addEventListener("click", () => claimReviewItem(button.dataset.reviewId, button));
        });
    }

    function render() {
        renderCounts();
        renderFilters();
        renderRows();
    }

    async function claimReviewItem(reviewItemId, button) {
        if (!reviewItemId) {
            return;
        }
        button.disabled = true;
        try {
            await window.DocFlow.apiPost(`/api/review/items/${encodeURIComponent(reviewItemId)}/claim`, {});
            window.location.href = `/app/review/${encodeURIComponent(reviewItemId)}`;
        } catch (error) {
            button.disabled = false;
            window.DocFlow.showToast(error.message || "Unable to claim review item", "error");
            await loadReviewItems();
        }
    }

    async function loadReviewItems() {
        const body = document.getElementById("review-queue-body");
        body.innerHTML = '<tr><td colspan="7" class="text-center text-base-content/50 py-10">Loading review items...</td></tr>';
        try {
            const payload = await window.DocFlow.apiGet("/api/review/items");
            state.items = Array.isArray(payload) ? payload : [];
            render();
        } catch (error) {
            body.innerHTML = '<tr><td colspan="7" class="text-center text-error py-10">Review queue failed to load</td></tr>';
            window.DocFlow.showToast(error.message || "Review queue failed to load", "error");
        }
    }

    function bindEvents() {
        document.querySelectorAll(".review-filter").forEach((button) => {
            button.addEventListener("click", () => {
                state.filter = button.dataset.filter || "all";
                render();
            });
        });
        document.getElementById("review-search-input").addEventListener("input", (event) => {
            state.search = event.target.value || "";
            renderRows();
        });
        document.getElementById("review-refresh-button").addEventListener("click", loadReviewItems);
    }

    document.addEventListener("DOMContentLoaded", () => {
        if (!document.getElementById("review-queue-workspace")) {
            return;
        }
        bindEvents();
        loadReviewItems();
    });
})();
