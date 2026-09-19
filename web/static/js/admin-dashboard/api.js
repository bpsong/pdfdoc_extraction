/** Admin dashboard requests. */
export function createApi(docFlow) {
    return { getSummary: () => docFlow.apiGet('/api/admin/summary'), getSettings: () => docFlow.apiGet('/api/admin/settings'), saveSettings: (settings) => docFlow.apiPut('/api/admin/settings', {settings}) };
}
