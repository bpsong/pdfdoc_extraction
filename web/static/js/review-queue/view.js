/** Rendering and presentation for review-queue. */
export function createView(deps) {
    const { state, docFlow, claimReviewItem } = deps;
    const escapeHtml = docFlow.escapeHtml;
    const titleCase = docFlow.titleCase;

    function statusBadge(status) {
        const badgeClass = docFlow.statusBadgeClass(status, "pending");
        return `<span class="badge ${badgeClass} badge-sm">${docFlow.escapeHtml(docFlow.statusLabel(status, "pending"))}</span>`;
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

    function confidenceBand(value) {
        if (value === null || value === undefined || value === "") {
            return "Missing";
        }
        const numeric = Number(value);
        if (Number.isNaN(numeric)) {
            return "Unknown";
        }
        return numeric < 0.7 ? "Low" : numeric < 0.9 ? "Medium" : "High";
    }

    function confidenceBadge(value) {
        if (value === null || value === undefined || value === "") {
            return '<span class="badge badge-ghost badge-sm">Missing confidence</span>';
        }
        const numeric = Number(value);
        const badgeClass = Number.isNaN(numeric)
            ? "badge-ghost"
            : numeric < 0.7
                ? "badge-error"
                : numeric < 0.9
                    ? "badge-warning"
                    : "badge-success";
        return `<span class="badge ${badgeClass} badge-sm">${escapeHtml(confidenceBand(value))} confidence · ${confidenceText(value)}</span>`;
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

    function renderCounts() {
        for (const key of ["active", "unclaimed", "mine", "others", "completed"]) {
            document.getElementById(`review-count-${key}`).textContent = String(state.counts[key] || 0);
        }
        document.getElementById("review-ownership").classList.toggle("hidden", state.filter === "completed");
    }

    function renderFilters() {
        document.querySelectorAll(".review-filter").forEach((button) => {
            const active = button.dataset.filter === state.filter;
            button.classList.toggle("btn-primary", active);
            button.classList.toggle("btn-outline", !active);
            button.setAttribute("aria-pressed", String(active));
        });
    }

    function activeOwner(item) {
        return item.lock && Date.parse(item.lock.expires_at) > Date.now() ? item.lock.locked_by : null;
    }

    function actionButtons(item) {
        const id = encodeURIComponent(item.id);
        const owner = activeOwner(item);
        const operator = document.getElementById("review-queue-workspace").dataset.operator;
        if (item.status === "completed" || owner) {
            const label = item.status === "completed" ? "View" : owner === operator ? "Continue review" : "View";
            return `<a class="btn btn-outline btn-xs" href="/app/review/${id}">${label}</a>`;
        }
        return `<button class="btn btn-primary btn-xs review-claim-action" type="button" data-review-id="${escapeHtml(item.id)}">Claim &amp; review</button>`;
    }

    function renderRows() {
        const body = document.getElementById("review-queue-body");
        const items = state.items;
        if (!items.length) {
            body.innerHTML = '<tr><td colspan="7" class="text-center text-base-content/50 py-10">No review items</td></tr>';
            return;
        }

        body.innerHTML = items.map((item) => {
            const labels = item.review_field_labels || [];
            const labelText = labels.length ? labels.slice(0, 3).join(", ") : titleCase(item.reason);
            const extra = labels.length > 3 ? ` +${labels.length - 3}` : "";
            const document = item.document || {};
            const createdAt = docFlow.formatDateTime(item.created_at);
            return `
                <tr class="hover">
                    <td class="px-4 py-3">
                        <a class="font-medium text-primary" href="/app/review/${encodeURIComponent(item.id)}">${escapeHtml(documentLabel(item))}</a>
                        <div class="text-xs text-base-content/50">${escapeHtml(createdAt)}</div>
                    </td>
                    <td>${escapeHtml(item.pipeline_name || "Unassigned")}</td>
                    <td class="max-w-sm">
                        <span class="text-sm">${escapeHtml(labelText)}${escapeHtml(extra)}</span>
                    </td>
                    <td>${confidenceBadge(item.lowest_confidence)}</td>
                    <td>${escapeHtml(createdAt)}</td>
                    <td>${statusBadge(item.status === "completed" ? "completed" : activeOwner(item) ? "in_review" : "pending")}<div class="text-xs">${escapeHtml(item.status === "completed" ? "" : activeOwner(item) ? `Claimed by ${activeOwner(item)}` : "Unclaimed")}</div></td>
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
        const start = state.total ? state.offset + 1 : 0;
        const end = Math.min(state.offset + state.items.length, state.total);
        document.getElementById("review-page-summary").textContent = `${start}-${end} of ${state.total}`;
        document.getElementById("review-prev").disabled = state.offset === 0;
        document.getElementById("review-next").disabled = state.offset + state.limit >= state.total;
        document.querySelectorAll("[data-review-sort]").forEach((button) => {
            const active = button.dataset.reviewSort === state.sortBy;
            button.closest("th").setAttribute("aria-sort", active ? (state.sortDir === "asc" ? "ascending" : "descending") : "none");
            button.querySelector("span").textContent = active ? (state.sortDir === "asc" ? "↑" : "↓") : "";
        });
    }

    return { statusBadge, confidenceText, confidenceBand, confidenceBadge, itemHasLowConfidence, documentLabel, documentType, renderCounts, renderFilters, activeOwner, actionButtons, renderRows, render };
}
