import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
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
        rawVisible: false,
        target: "config.yaml",
    };












    const api = createApi(window.DocFlow);
    const { escapeHtml, secretKey, redactSecrets, normalizeFinding, summaryFromResult, badgeClass, renderValidationSummary, renderFindings, renderRawJson, render } = createView({ state, docFlow: window.DocFlow });
    async function loadActiveValidation() {
        state.result = await api.getActive();
        state.target = "config.yaml";
        render();
    }

    async function validateAllSchemas() {
        state.result = await api.validateSchemas();
        state.target = "review forms";
        render();
    }

    async function validatePipeline() {
        const payload = await api.getPipeline();
        const model = payload.draft && payload.draft.model
            ? payload.draft.model
            : payload.active && payload.active.model;
        state.result = await api.validatePipeline(model);
        state.result.source = "pipeline";
        state.target = "pipeline draft";
        render();
    }

    async function runDraftValidation() {
        const yamlText = document.getElementById("validation-draft-yaml").value;
        if (!yamlText.trim()) {
            window.DocFlow.showToast("Paste draft YAML before validating.", "warning");
            return;
        }
        state.result = await api.validateDraft({
            yaml_text: yamlText,
            strict: document.getElementById("validation-strict-toggle").checked,
            import_checks: document.getElementById("validation-import-toggle").checked,
        });
        state.target = "pasted YAML";
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
    document.getElementById("validation-pipeline-button").addEventListener("click", () => {
        validatePipeline().catch((error) => window.DocFlow.showToast(error.message || "Unable to validate pipeline", "error"));
    });
    document.getElementById("validation-raw-toggle").addEventListener("click", toggleRawJson);

    loadActiveValidation().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load validation", "error");
        render();
    });
})();
