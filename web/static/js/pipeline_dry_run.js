(function () {
    "use strict";

    const workspace = document.getElementById("pipeline-dry-run-workspace");
    if (!workspace) {
        return;
    }

    const SECRET_KEYS = ["api_key", "apikey", "password", "secret", "secret_key", "token"];
    const state = {
        result: null,
    };

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function titleCase(value) {
        return String(value || "")
            .replace(/_/g, " ")
            .replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function secretKey(key) {
        const normalized = String(key || "").toLowerCase();
        return SECRET_KEYS.some((secret) => normalized === secret || normalized.endsWith(`_${secret}`));
    }

    function redactSecrets(value) {
        if (Array.isArray(value)) {
            return value.map((item) => redactSecrets(item));
        }
        if (value && typeof value === "object") {
            const redacted = {};
            Object.entries(value).forEach(([key, item]) => {
                redacted[key] = secretKey(key) ? "[REDACTED]" : redactSecrets(item);
            });
            return redacted;
        }
        return value;
    }

    function parseMockResults() {
        const raw = document.getElementById("dry-run-mock-json").value.trim();
        if (!raw) {
            return {};
        }
        try {
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
                throw new Error("Mock results must be a JSON object.");
            }
            return parsed;
        } catch (error) {
            throw new Error(error.message || "Mock results JSON is invalid.");
        }
    }

    function requestPayload() {
        const fileInput = document.getElementById("dry-run-file-input");
        const file = fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
        const documentId = document.getElementById("dry-run-document-id").value.trim();
        const sample = file
            ? { filename: file.name, size_bytes: file.size, content_type: file.type || "application/pdf" }
            : {};
        const payload = {
            mock_results: parseMockResults(),
            sample,
        };
        if (file) {
            payload.sample_filename = file.name;
        }
        if (documentId) {
            payload.document_id = documentId;
        }
        return payload;
    }

    function renderStat(id, value) {
        document.getElementById(id).textContent = titleCase(value || "-");
    }

    function renderDecisionTable(result) {
        const body = document.getElementById("dry-run-decision-body");
        if (!result) {
            body.innerHTML = '<tr><td colspan="3" class="text-center text-base-content/50 py-10">No dry-run result</td></tr>';
            return;
        }
        const rows = [
            ["Split", result.split?.status, `${(result.split?.decisions || []).length} decisions`],
            ["Extraction", result.extraction?.status, `${result.extraction?.mock_field_count || 0} mock fields`],
            [
                "Review Gate",
                result.review_gate?.review_required ? "review required" : "pass",
                (result.review_gate?.reasons || []).join(", ") || "No review triggers",
            ],
            ["Validation", result.validation?.valid ? "valid" : "blocked", `${result.validation?.findings?.length || 0} findings`],
            ["Exports", "skipped", `${result.exports?.steps?.length || 0} export steps`],
        ];
        body.innerHTML = rows.map((row) => `
            <tr>
                <td class="font-semibold">${escapeHtml(row[0])}</td>
                <td><span class="badge badge-sm badge-outline">${escapeHtml(titleCase(row[1]))}</span></td>
                <td>${escapeHtml(row[2])}</td>
            </tr>
        `).join("");
    }

    function render() {
        const result = state.result;
        renderStat("dry-run-split-status", result?.split?.status);
        renderStat("dry-run-extraction-status", result?.extraction?.status);
        renderStat("dry-run-review-status", result?.review_gate?.review_required ? "review required" : result?.review_gate?.status);
        renderStat("dry-run-export-status", result?.exports?.final_exports_written ? "written" : "skipped");
        document.getElementById("dry-run-result-summary").textContent = result
            ? `${result.pipeline?.summary?.enabled_steps || 0} enabled steps`
            : "No dry run yet";
        document.getElementById("dry-run-audit-id").textContent = result?.audit_event_id || "No audit event";
        document.getElementById("dry-run-json").textContent = JSON.stringify(redactSecrets(result || {}), null, 2);
        renderDecisionTable(result);
    }

    async function runDryRun() {
        const payload = requestPayload();
        state.result = await window.DocFlow.apiPost("/api/admin/dry-run", payload);
        render();
        window.DocFlow.showToast("Dry run completed", "success");
    }

    document.getElementById("dry-run-run-button").addEventListener("click", () => {
        runDryRun().catch((error) => window.DocFlow.showToast(error.message || "Unable to run dry run", "error"));
    });

    render();
})();
