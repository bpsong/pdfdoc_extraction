/** Filtered audit request. */
export function createApi(docFlow) {
    return { list: (query) => docFlow.apiGet(`/api/admin/audit${query}`) };
}
