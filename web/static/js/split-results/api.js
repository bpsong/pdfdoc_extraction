/** Batch split-results request. */
export function createApi(docFlow) {
    return { getBatch: (id) => docFlow.apiGet(`/api/batches/${encodeURIComponent(id)}/split-results`) };
}
