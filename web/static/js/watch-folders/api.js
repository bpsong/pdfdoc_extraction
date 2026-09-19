/** Same-origin watch-folder requests with CSRF. */
export function createApi(docFlow, fetchImpl = globalThis.fetch) {
    async function request(url, method = "GET", body) {
        const response = await fetchImpl(url, {method, credentials:"same-origin", headers:{"Content-Type":"application/json", ...docFlow.csrfHeaders(method)}, ...(body ? {body:JSON.stringify(body)} : {})});
        const payload = await response.json();
        if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : payload.detail?.message || "Unable to complete request.");
        return payload;
    }
    return { request };
}
