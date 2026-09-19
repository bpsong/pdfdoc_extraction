/** Document extraction request. */
export function createApi(docFlow) {
    return { getDocument: (id) => docFlow.apiGet(`/api/documents/${encodeURIComponent(id)}/extraction`) };
}
