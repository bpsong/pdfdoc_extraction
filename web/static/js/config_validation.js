(function () {
    "use strict";

    const workspace = document.getElementById("config-validation-workspace");
    if (!workspace) {
        return;
    }

    const SECRET_KEYS = [
        "api_key",
        "apikey",
        "password",
        "password_hash",
        "secret",
        "secret_key",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
    ];

    const state = {
        result: null,
        rawVisible: true,
    };

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
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

    function normalizeFinding(finding) {
        const level = finding.severity || finding.level || "info";
        const location = finding.location || {};
        const locationText = location.line
            ? `${location.line}${location.column ? `:${location.column}` : ""}`
            : "";
        return {
            level,
            code: finding.code || "",
            path: finding.path || "",
            message: finding.message || "",
            suggestion: finding.suggestion || "",
            location: locationText,
        };
    }

    function summaryFromResult(result) {
        const findings = Array.isArray(result && result.findings) ? result.findings.map(normalizeFinding) : [];
        const summary = result && result.summary ? result.summary : {};
        return {
            errors: Number(summary.errors ?? findings.filter((finding) => finding.level === "error").length),
            warnings: Number(summary.warnings ?? findings.filter((finding) => finding.level === "warning").length),
            info: Number(summary.info ?? findings.filter((finding) => finding.level === "info").length),
        };
    }

    function badgeClass(level) {
        if (level === "error") {
            return "badge-error";
        }
        if (level === "warning") {
            return "badge-warning";
        }
        return "badge-ghost";
    }

    function renderValidationSummary(summary) {
        document.getElementById("validation-errors-count").textContent = String(summary.errors);
        document.getElementById("validation-warnings-count").textContent = String(summary.warnings);
        document.getElementById("validation-info-count").textContent = String(summary.info);
        const readiness = document.getElementById("validation-readiness");
        readiness.textContent = summary.errors > 0 ? "Blocked" : state.result ? "Ready" : "Not run";
        readiness.classList.toggle("text-error", summary.errors > 0);
        readiness.classList.toggle("text-success", state.result && summary.errors === 0);
    }

    function renderFindings(findings) {
        const body = document.getElementById("validation-findings-body");
        document.getElementById("validation-findings-summary").textContent = findings.length
            ? `${findings.length} findings`
            : state.result
                ? "Validation passed"
                : "No validation run";

        if (!findings.length) {
            body.innerHTML = state.result
                ? '<tr><td colspan="6" class="text-center text-success py-10">Validation passed</td></tr>'
                : '<tr><td colspan="6" class="text-center text-base-content/50 py-10">No validation findings</td></tr>';
            return;
        }

        body.innerHTML = findings.map((finding) => `
            <tr>
                <td><span class="badge badge-sm ${badgeClass(finding.level)}">${escapeHtml(finding.level)}</span></td>
                <td class="font-mono text-xs">${escapeHtml(finding.code)}</td>
                <td class="font-mono text-xs">${escapeHtml(finding.path)}</td>
                <td>${escapeHtml(finding.message)}</td>
                <td>${escapeHtml(finding.suggestion)}</td>
                <td class="font-mono text-xs">${escapeHtml(finding.location)}</td>
            </tr>
        `).join("");
    }

    function renderRawJson() {
        const rawPanel = document.getElementById("validation-raw-json");
        rawPanel.classList.toggle("hidden", !state.rawVisible);
        document.getElementById("validation-raw-toggle").textContent = state.rawVisible ? "Hide" : "Show";
        rawPanel.textContent = JSON.stringify(redactSecrets(state.result || {}), null, 2);
    }

    function render() {
        const summary = summaryFromResult(state.result || {});
        const findings = Array.isArray(state.result && state.result.findings)
            ? state.result.findings.map(normalizeFinding)
            : [];
        renderValidationSummary(summary);
        renderFindings(findings);
        renderRawJson();
        document.getElementById("validation-source-label").textContent = state.result && state.result.source
            ? `Source: ${state.result.source}`
            : "Active configuration";
    }

    async function loadActiveValidation() {
        state.result = await window.DocFlow.apiGet("/api/config/validation");
        render();
    }

    async function validateAllSchemas() {
        state.result = await window.DocFlow.apiPost("/api/admin/schemas/validate-all", {});
        render();
    }

    async function runDraftValidation() {
        const yamlText = document.getElementById("validation-draft-yaml").value;
        if (!yamlText.trim()) {
            window.DocFlow.showToast("Paste draft YAML before validating.", "warning");
            return;
        }
        state.result = await window.DocFlow.apiPost("/api/config/validation", {
            yaml_text: yamlText,
            strict: document.getElementById("validation-strict-toggle").checked,
            import_checks: document.getElementById("validation-import-toggle").checked,
        });
        render();
    }

    function toggleRawJson() {
        state.rawVisible = !state.rawVisible;
        renderRawJson();
    }

    document.getElementById("validation-active-button").addEventListener("click", () => {
        loadActiveValidation().catch((error) => window.DocFlow.showToast(error.message || "Unable to validate config", "error"));
    });
    document.getElementById("validation-draft-button").addEventListener("click", () => {
        runDraftValidation().catch((error) => window.DocFlow.showToast(error.message || "Unable to validate draft", "error"));
    });
    document.getElementById("validation-schemas-button").addEventListener("click", () => {
        validateAllSchemas().catch((error) => window.DocFlow.showToast(error.message || "Unable to validate schemas", "error"));
    });
    document.getElementById("validation-raw-toggle").addEventListener("click", toggleRawJson);

    loadActiveValidation().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load validation", "error");
        render();
    });
})();
