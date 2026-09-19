/** Authenticated failure requests. */
export function createApi(docFlow) {
    return { list: (params) => docFlow.apiGet(`/api/failures?${params}`), getDetail: (id) => docFlow.apiGet(`/api/failures/${encodeURIComponent(id)}`) };
}
