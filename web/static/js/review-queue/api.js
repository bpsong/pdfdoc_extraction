/** Review queue list and claim requests. */
export function createApi(docFlow) {
    return { list: (params) => docFlow.apiGet(`/api/review/items?${params}`), claim: (id) => docFlow.apiPost(`/api/review/items/${encodeURIComponent(id)}/claim`, {}) };
}
