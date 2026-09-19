/** Configuration-validation requests. */
export function createApi(docFlow) {
    return { getActive: () => docFlow.apiGet('/api/config/validation'), validateSchemas: () => docFlow.apiPost('/api/admin/schemas/validate-all', {}), getPipeline: () => docFlow.apiGet('/api/admin/pipeline'), validatePipeline: (model) => docFlow.apiPost('/api/admin/pipeline/validate', {model}), validateDraft: (payload) => docFlow.apiPost('/api/config/validation', payload) };
}
