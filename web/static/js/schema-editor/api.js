/** Versioned review-form requests used by the admin editor. */

export function createSchemaEditorApi(docFlow, fetchImpl = globalThis.fetch) {
    const base = "/api/admin/review-schemas";
    const templateUrl = (id) => `${base}/${encodeURIComponent(id)}`;

    async function request(url, method, body, contentType = "application/json") {
        const response = await fetchImpl(url, {
            method,
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
                "Content-Type": contentType,
                ...docFlow.csrfHeaders(method),
            },
            body: typeof body === "string" ? body : JSON.stringify(body),
        });
        if (!response.ok) {
            const payload = await response.json();
            const detail = payload.detail || "Request failed";
            throw new Error(detail.message || detail);
        }
        return response.json();
    }

    return {
        listTemplates: () => docFlow.apiGet(`${base}?include_archived=true`),
        getTemplate: (id) => docFlow.apiGet(templateUrl(id)),
        createTemplate: (key, name, schema) => docFlow.apiPost(base, {
            schema_key: key, name, schema,
        }),
        updateTemplate: (id, metadata) => request(templateUrl(id), "PATCH", metadata),
        saveDraft: (id, revision, schema) => docFlow.apiPut(`${templateUrl(id)}/draft`, {
            expected_revision: revision, schema,
        }),
        validateDraft: (id) => docFlow.apiPost(`${templateUrl(id)}/draft/validate`, {}),
        publishDraft: (id, revision) => docFlow.apiPost(`${templateUrl(id)}/publish`, {
            expected_revision: revision,
        }),
        testPattern: (pattern, example) => docFlow.apiPost("/api/schemas/pattern-test", {
            pattern, example,
        }),
        async importDraft(id, revision, file) {
            return request(
                `${templateUrl(id)}/draft/import?expected_revision=${encodeURIComponent(revision)}`,
                "POST",
                await file.text(),
                file.name.endsWith(".json") ? "application/json" : "application/yaml",
            );
        },
        exportDraftUrl: (id) => `${templateUrl(id)}/draft/export?format=yaml`,
    };
}
