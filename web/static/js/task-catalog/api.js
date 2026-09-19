/** Task-catalog request. */
export function createApi(docFlow) {
    return { load: () => docFlow.apiGet('/api/admin/task-catalog') };
}
