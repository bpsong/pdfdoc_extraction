import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
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















    const api = createApi(window.DocFlow);
    const { statusBadge, confidenceText, confidenceBand, confidenceBadge, itemHasLowConfidence, documentLabel, documentType, renderCounts, renderFilters, activeOwner, actionButtons, renderRows, render } = createView({ state, docFlow: window.DocFlow, claimReviewItem });
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
            await api.claim(reviewItemId);
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
            const payload = await api.list(params);
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
