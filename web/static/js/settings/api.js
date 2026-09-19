/** Operator settings request. */
export function createApi(docFlow) {
    return { load: () => docFlow.apiGet('/api/settings') };
}
