(function () {
    "use strict";

    const state = {
        items: [],
        filter: "active",
        search: "",
        total: 0,
        counts: {},
        limit: 25,
        offset: 0,
        sortBy: "created_at",
        sortDir: "asc",
        queryKey: null,
        pipeline: "",
    };
    const escapeHtml = window.DocFlow.escapeHtml;
    const titleCase = window.DocFlow.titleCase;

    function statusBadge(status) {
        const badgeClass = window.DocFlow.statusBadgeClass(status, "pending");
        return `<span class="badge ${badgeClass} badge-sm">${window.DocFlow.escapeHtml(window.DocFlow.statusLabel(status, "pending"))}</span>`;
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
            const createdAt = window.DocFlow.formatDateTime(item.created_at);
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

    function announceReviewChanges(previousItems, nextItems) {
        if (!previousItems.length || !window.DocFlow || !window.DocFlow.announce) {
            return;
        }
        const previousById = new Map(previousItems.map((item) => [String(item.id), item]));
        const additions = nextItems.filter((item) => !previousById.has(String(item.id)));
        const completed = nextItems.filter((item) => {
            const previous = previousById.get(String(item.id));
            return previous && previous.status !== "completed" && item.status === "completed";
        });
        const messages = [];
        if (additions.length) {
            messages.push(`${additions.length} new review item${additions.length === 1 ? "" : "s"}`);
        }
        if (completed.length) {
            messages.push(`${completed.length} review item${completed.length === 1 ? "" : "s"} completed`);
        }
        if (messages.length) {
            window.DocFlow.announce(messages.join("; "));
        }
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

    let loadInFlight = false;
    let loadQueued = false;

    async function loadReviewItems() {
        if (loadInFlight) {
            loadQueued = true;
            return;
        }
        loadInFlight = true;
        const body = document.getElementById("review-queue-body");
        const region = document.getElementById("review-queue-region");
        [body, region].forEach((element) => {
            if (element) {
                element.setAttribute("aria-busy", "true");
            }
        });
        body.innerHTML = window.DocFlow.tableSkeletonRows(7, 4);
        try {
            const params = new URLSearchParams({
                paginated: "true",
                limit: String(state.limit),
                offset: String(state.offset),
                filter: state.filter,
                search: state.search,
                pipeline_id: state.pipeline,
                sort_by: state.sortBy,
                sort_dir: state.sortDir,
            });
            const payload = await window.DocFlow.apiGet(`/api/review/items?${params}`);
            if (loadQueued) return;
            const pipelineSelect = document.getElementById("review-pipeline");
            pipelineSelect.innerHTML = '<option value="">All pipelines</option>' + (payload.pipelines || []).map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join("");
            pipelineSelect.value = state.pipeline;
            const nextItems = Array.isArray(payload.items) ? payload.items : [];
            const queryKey = params.toString();
            if (state.queryKey === queryKey) {
                announceReviewChanges(state.items, nextItems);
            }
            state.items = nextItems;
            state.queryKey = queryKey;
            state.total = Number(payload.total || 0);
            state.counts = payload.counts || {};
            state.limit = Number(payload.limit || state.limit);
            state.offset = Number(payload.offset || 0);
            render();
        } catch (error) {
            body.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center py-10">
                        <p class="text-error">Review queue failed to load</p>
                        <button class="btn btn-outline btn-sm mt-3" type="button" data-review-retry>Retry</button>
                    </td>
                </tr>
            `;
            window.DocFlow.showToast(error.message || "Review queue failed to load", "error");
        } finally {
            loadInFlight = false;
            if (loadQueued) {
                loadQueued = false;
                loadReviewItems();
                return;
            }
            [body, region].forEach((element) => {
                if (element) {
                    element.setAttribute("aria-busy", "false");
                }
            });
        }
    }

    function bindEvents() {
        document.getElementById("review-pipeline").addEventListener("change", event => {
            state.pipeline = event.target.value;
            state.offset = 0;
            loadReviewItems();
        });
        document.getElementById("review-page-size").addEventListener("change", event => {
            state.limit = Number(event.target.value);
            state.offset = 0;
            loadReviewItems();
        });
        document.querySelectorAll(".review-filter").forEach((button) => {
            button.addEventListener("click", () => {
                state.filter = button.dataset.filter || "all";
                state.offset = 0;
                loadReviewItems();
            });
        });
        let searchTimer = null;
        document.getElementById("review-search-input").addEventListener("input", (event) => {
            state.search = event.target.value || "";
            state.offset = 0;
            window.clearTimeout(searchTimer);
            searchTimer = window.setTimeout(loadReviewItems, 250);
        });
        document.getElementById("review-refresh-button").addEventListener("click", loadReviewItems);
        document.getElementById("review-queue-body").addEventListener("click", (event) => {
            if (event.target.closest("[data-review-retry]")) {
                loadReviewItems();
            }
        });
        document.getElementById("review-prev").addEventListener("click", () => {
            state.offset = Math.max(0, state.offset - state.limit);
            loadReviewItems();
        });
        document.getElementById("review-next").addEventListener("click", () => {
            state.offset += state.limit;
            loadReviewItems();
        });
        document.getElementById("review-queue-region").addEventListener("click", (event) => {
            const button = event.target.closest("[data-review-sort]");
            if (!button) {
                return;
            }
            const sortBy = button.dataset.reviewSort;
            state.sortDir = state.sortBy === sortBy && state.sortDir === "asc" ? "desc" : "asc";
            state.sortBy = sortBy;
            state.offset = 0;
            loadReviewItems();
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        if (!document.getElementById("review-queue-workspace")) {
            return;
        }
        bindEvents();
        loadReviewItems();
    });
})();
