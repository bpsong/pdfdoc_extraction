/** Processing-state and notification requests. */
export function createApi(docFlow) {
    return { getBatch: (id) => docFlow.apiGet(`/api/batches/${encodeURIComponent(id)}/processing-state`), getAll: () => docFlow.apiGet('/api/processing-state'), clearFailureNotifications: () => docFlow.apiPost('/api/failures/notifications/clear', {}) };
}
