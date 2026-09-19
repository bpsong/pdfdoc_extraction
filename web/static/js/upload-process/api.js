/** CSRF-aware upload requests and cancellable transfer. */
export function createApi(docFlow, updateUploadProgress, getSubmissionId) {
    const state = { activeUploadXhr: null };
    function uploadBatchRequest(formData) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            state.activeUploadXhr = xhr;
            const clearActiveRequest = () => {
                if (state.activeUploadXhr === xhr) {
                    state.activeUploadXhr = null;
                }
            };
            xhr.open("POST", "/api/batches/upload");
            xhr.withCredentials = true;
            xhr.setRequestHeader("Accept", "application/json");
            xhr.setRequestHeader("Idempotency-Key", getSubmissionId());
            const csrfHeaders = docFlow ? docFlow.csrfHeaders("POST") : {};
            Object.entries(csrfHeaders).forEach(([name, value]) => xhr.setRequestHeader(name, value));
            xhr.upload.addEventListener("progress", (event) => {
                if (event.lengthComputable) {
                    updateUploadProgress(event.loaded, event.total);
                }
            });
            xhr.addEventListener("load", () => {
                clearActiveRequest();
                let payload = null;
                try {
                    payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
                } catch (error) {
                    payload = null;
                }
                if (xhr.status === 401) {
                    window.location.href = "/login";
                    resolve(null);
                    return;
                }
                if (xhr.status < 200 || xhr.status >= 300) {
                    const detail = payload && payload.detail ? payload.detail : xhr.statusText;
                    const message = typeof detail === "string" ? detail : detail && detail.message || "Upload failed";
                    const requestError = new Error(message);
                    requestError.status = xhr.status;
                    requestError.retryAfter = xhr.getResponseHeader("Retry-After");
                    reject(requestError);
                    return;
                }
                resolve(payload);
            });
            xhr.addEventListener("error", () => {
                clearActiveRequest();
                reject(new Error("Upload failed: network error"));
            });
            xhr.addEventListener("abort", () => {
                clearActiveRequest();
                const error = new Error("Upload was cancelled");
                error.name = "AbortError";
                reject(error);
            });
            xhr.send(formData);
        });
    }

    function cancelUpload() {
        if (state.activeUploadXhr) {
            state.activeUploadXhr.abort();
        }
    }
    return { uploadBatchRequest, cancelUpload, getReceipt: (id) => docFlow.apiGet(`/api/upload-submissions/${encodeURIComponent(id)}`), listPipelines: () => docFlow.apiGet('/api/pipelines/available?source=upload') };
}
