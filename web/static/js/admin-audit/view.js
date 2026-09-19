/** Rendering and presentation for admin-audit. */
export function createView(deps) {
    const { state, docFlow } = deps;
    const escapeHtml = docFlow.escapeHtml;

    function targetLabel(event) {
        if (event.document_id) {
            return `document ${event.document_id}`;
        }
        if (event.review_item_id) {
            return `review ${event.review_item_id}`;
        }
        if (event.batch_id) {
            return `batch ${event.batch_id}`;
        }
        return "admin";
    }

    function renderTable() {
        const body = document.getElementById("admin-audit-body");
        if (!state.events.length) {
            body.innerHTML = '<tr><td colspan="5" class="text-center text-base-content/50 py-4">No admin audit events match these filters.</td></tr>';
            renderDetail(null);
            return;
        }
        body.innerHTML = state.events.map((event) => `
            <tr class="${event.id === state.selectedId ? "active" : ""}">
                <td class="text-xs">${docFlow.escapeHtml(docFlow.formatDateTime(event.created_at))}</td>
                <td>${escapeHtml(event.user || "system")}</td>
                <td><span class="badge badge-sm badge-outline">${escapeHtml(event.event_type)}</span></td>
                <td class="font-mono text-xs">${escapeHtml(targetLabel(event))}</td>
                <td class="text-right">
                    <button class="btn btn-ghost btn-xs" data-audit-id="${escapeHtml(event.id)}" type="button">Details</button>
                </td>
            </tr>
        `).join("");
    }

    function renderPagination() {
        const start = state.total ? state.offset + 1 : 0;
        const end = Math.min(state.offset + state.events.length, state.total);
        document.getElementById("admin-audit-page-summary").textContent = `${start}-${end} of ${state.total}`;
        document.getElementById("admin-audit-prev").disabled = state.offset === 0;
        document.getElementById("admin-audit-next").disabled = state.offset + state.limit >= state.total;
        document.querySelectorAll("[data-audit-sort]").forEach((button) => {
            const active = button.dataset.auditSort === state.sortBy;
            button.setAttribute("aria-sort", active ? (state.sortDir === "asc" ? "ascending" : "descending") : "none");
            button.querySelector("span").textContent = active ? (state.sortDir === "asc" ? "↑" : "↓") : "";
        });
    }

    function renderDetail(event) {
        document.getElementById("admin-audit-detail-title").textContent = event ? event.event_type : "Event Details";
        document.getElementById("admin-audit-detail-subtitle").textContent = event
            ? `${event.user || "system"} - ${docFlow.formatDateTime(event.created_at)}`
            : "Select an event";
        document.getElementById("admin-audit-detail-json").textContent = event
            ? JSON.stringify(event, null, 2)
            : "Select an audit event to view details.";
    }

    function renderEventTypeOptions() {
        const datalist = document.getElementById("admin-audit-event-types");
        const types = [...new Set(state.events.map((event) => event.event_type).filter(Boolean))].sort();
        datalist.innerHTML = types.map((type) => `<option value="${escapeHtml(type)}"></option>`).join("");
    }

    return { targetLabel, renderTable, renderPagination, renderDetail, renderEventTypeOptions };
}
