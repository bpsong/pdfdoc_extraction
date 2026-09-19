/** Authenticated reports and batch-detail requests. */
export function createApi(docFlow) {
    return { getSummary: () => docFlow.apiGet('/api/reports/summary'), getBatch: (id) => docFlow.apiGet(`/api/batches/${encodeURIComponent(id)}/processing-state`), getBindingActivity: (id, offset) => docFlow.apiGet(`/api/admin/watch-folder-bindings/${encodeURIComponent(id)}/activity?offset=${offset}`) };
}
