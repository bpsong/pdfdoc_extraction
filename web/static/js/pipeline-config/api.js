/** HTTP boundary for the versioned pipeline editor. */

export function createPipelineApi(docFlow, fetchImpl = globalThis.fetch) {
    async function patch(url, payload) {
        const response = await fetchImpl(url, {
            method: "PATCH",
            credentials: "same-origin",
            headers: {
                "Accept": "application/json",
                "Content-Type": "application/json",
                ...docFlow.csrfHeaders("PATCH"),
            },
            body: JSON.stringify(payload || {}),
        });
        if (!response.ok) {
            const body = await response.json();
            const detail = body.detail || "Request failed";
            const error = new Error(detail.message || detail);
            error.detail = detail;
            error.status = response.status;
            throw error;
        }
        return response.json();
    }

    return {
        listTemplates: () => docFlow.apiGet("/api/admin/pipeline-templates?include_archived=true"),
        getTaskCatalog: () => docFlow.apiGet("/api/admin/task-catalog"),
        getTemplate: (templateId) => docFlow.apiGet(
            `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}`,
        ),
        getVersion: (templateId, versionId) => docFlow.apiGet(
            `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}/versions/${encodeURIComponent(versionId)}`,
        ),
        listWatchFolderBindings: () => docFlow.apiGet("/api/admin/watch-folder-bindings"),
        saveDraft: (templateId, payload) => docFlow.apiPut(
            `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}/draft`,
            payload,
        ),
        validateDraft: (templateId) => docFlow.apiPost(
            `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}/draft/validate`,
            {},
        ),
        getDiff: (templateId) => docFlow.apiGet(
            `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}/diff`,
        ),
        publishDraft: (templateId, expectedRevision) => docFlow.apiPost(
            `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}/publish`,
            { expected_revision: expectedRevision },
        ),
        listDirectories: (path) => docFlow.apiGet(
            `/api/admin/pipeline/directories?path=${encodeURIComponent(path || ".")}`,
        ),
        listFiles: (path, extensions) => docFlow.apiGet(
            `/api/admin/pipeline/files?path=${encodeURIComponent(path || ".")}&extensions=${encodeURIComponent(extensions || "")}`,
        ),
        getCsvMetadata: (path) => docFlow.apiGet(
            `/api/admin/pipeline/csv-metadata?path=${encodeURIComponent(path)}`,
        ),
        createDirectory: (path) => docFlow.apiPost("/api/admin/pipeline/directories", { path }),
        createTemplate: (templateKey, name) => docFlow.apiPost(
            "/api/admin/pipeline-templates",
            { template_key: templateKey, name },
        ),
        cloneTemplate: (templateId, templateKey, name) => docFlow.apiPost(
            `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}/clone`,
            { template_key: templateKey, name },
        ),
        updateTemplate: (templateId, payload) => patch(
            `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}`,
            payload,
        ),
        async importDraft(templateId, expectedRevision, file) {
            const response = await fetchImpl(
                `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}/draft/import?expected_revision=${encodeURIComponent(expectedRevision)}`,
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Accept": "application/json",
                        "Content-Type": file.name.endsWith(".json") ? "application/json" : "application/yaml",
                        ...docFlow.csrfHeaders("POST"),
                    },
                    body: await file.text(),
                },
            );
            if (!response.ok) {
                const payload = await response.json();
                throw new Error(payload.detail && payload.detail.message || payload.detail || "Import failed");
            }
            return response.json();
        },
        exportDraftUrl: (templateId) => (
            `/api/admin/pipeline-templates/${encodeURIComponent(templateId)}/draft/export?format=yaml`
        ),
    };
}
