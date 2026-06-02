(function () {
    "use strict";

    const workspace = document.getElementById("review-gate-rules-workspace");
    if (!workspace) {
        return;
    }

    const state = {
        settings: {},
        taskKey: "",
        source: "",
        passThrough: {},
    };

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function percent(value) {
        const number = Number(value);
        if (Number.isNaN(number)) {
            return "-";
        }
        return `${Math.round(number * 100)}%`;
    }

    function titleCase(value) {
        return String(value || "")
            .replace(/_/g, " ")
            .replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function listText(values) {
        return Array.isArray(values) && values.length ? values.join(", ") : "";
    }

    function thresholdRows(map, type) {
        const entries = Object.entries(map || {});
        if (!entries.length) {
            return `<tr><td colspan="3" class="text-center text-base-content/50 py-8">No overrides</td></tr>`;
        }
        return entries.map(([key, value], index) => `
            <tr data-threshold-row="${escapeHtml(type)}" data-index="${index}">
                <td>
                    <input class="input input-bordered input-sm w-full" data-threshold-key="${escapeHtml(type)}"
                        value="${escapeHtml(key)}">
                </td>
                <td>
                    <input class="input input-bordered input-sm w-28" data-threshold-value="${escapeHtml(type)}"
                        min="0" max="1" step="0.01" type="number" value="${escapeHtml(value)}">
                </td>
                <td class="text-right">
                    <button class="btn btn-ghost btn-xs text-error" type="button" data-remove-threshold="${escapeHtml(type)}"
                        data-index="${index}">Remove</button>
                </td>
            </tr>
        `).join("");
    }

    function mapFromRows(type) {
        const rows = workspace.querySelectorAll(`[data-threshold-row="${type}"]`);
        const map = {};
        rows.forEach((row) => {
            const key = row.querySelector(`[data-threshold-key="${type}"]`);
            const value = row.querySelector(`[data-threshold-value="${type}"]`);
            const name = key ? key.value.trim() : "";
            if (name && value) {
                map[name] = Number(value.value || 0);
            }
        });
        return map;
    }

    function selectedSplitLevels() {
        return Array.from(workspace.querySelectorAll("[data-split-confidence]:checked"))
            .map((checkbox) => checkbox.dataset.splitConfidence)
            .filter(Boolean);
    }

    function splitFlags(value) {
        return String(value || "")
            .split(/[,\n]/)
            .map((item) => item.trim())
            .filter(Boolean);
    }

    function readSettings() {
        return {
            confidence_threshold: Number(document.getElementById("review-gate-confidence-input").value || 0),
            per_document_type_thresholds: mapFromRows("document"),
            field_threshold_overrides: mapFromRows("field"),
            review_scope: document.getElementById("review-gate-review-scope").value,
            queue_name: document.getElementById("review-gate-queue-name").value.trim(),
            always_review: document.getElementById("review-gate-always-review").checked,
            split_confidence_levels_requiring_review: selectedSplitLevels(),
            business_rule_flag_names: splitFlags(document.getElementById("review-gate-business-flags").value),
            require_review_when_missing_confidence: document.getElementById("review-gate-missing-confidence").checked,
            require_review_for_missing_required_fields: document.getElementById("review-gate-missing-required").checked,
            allow_operator_to_edit_high_confidence_fields: document.getElementById("review-gate-edit-high-confidence").checked,
            schema_file: document.getElementById("review-gate-schema-file").value.trim(),
            resume_policy: document.getElementById("review-gate-resume-policy").value,
            lock_timeout_minutes: Number(document.getElementById("review-gate-lock-timeout").value || 60),
        };
    }

    function renderSummary() {
        const settings = state.settings || {};
        document.getElementById("review-gate-task-key").textContent = state.taskKey || "No task";
        document.getElementById("review-gate-source").textContent = titleCase(state.source || "app_settings");
        document.getElementById("review-gate-threshold-summary").textContent = percent(settings.confidence_threshold);
        document.getElementById("review-gate-scope-summary").textContent = titleCase(settings.review_scope);
        document.getElementById("review-gate-queue-summary").textContent = settings.queue_name || "default_review";
        document.getElementById("review-gate-lock-summary").textContent = `${settings.lock_timeout_minutes || 60} min lock`;
        document.getElementById("review-gate-pass-summary").textContent = titleCase(state.passThrough.status || "passed");
        document.getElementById("review-gate-pass-status").textContent = state.passThrough.review_required === false
            ? "No review item"
            : "-";
    }

    function renderForm() {
        const settings = state.settings || {};
        const confidence = settings.confidence_threshold ?? 0.8;
        document.getElementById("review-gate-confidence-range").value = confidence;
        document.getElementById("review-gate-confidence-input").value = confidence;
        document.getElementById("review-gate-review-scope").value = settings.review_scope || "low_confidence_fields";
        document.getElementById("review-gate-queue-name").value = settings.queue_name || "default_review";
        document.getElementById("review-gate-lock-timeout").value = settings.lock_timeout_minutes || 60;
        document.getElementById("review-gate-schema-file").value = settings.schema_file || "";
        document.getElementById("review-gate-resume-policy").value = settings.resume_policy || "next_task";
        document.getElementById("review-gate-missing-confidence").checked = settings.require_review_when_missing_confidence !== false;
        document.getElementById("review-gate-missing-required").checked = settings.require_review_for_missing_required_fields !== false;
        document.getElementById("review-gate-always-review").checked = Boolean(settings.always_review);
        document.getElementById("review-gate-edit-high-confidence").checked = settings.allow_operator_to_edit_high_confidence_fields !== false;
        document.getElementById("review-gate-business-flags").value = listText(settings.business_rule_flag_names);

        const splitLevels = new Set(settings.split_confidence_levels_requiring_review || []);
        workspace.querySelectorAll("[data-split-confidence]").forEach((checkbox) => {
            checkbox.checked = splitLevels.has(checkbox.dataset.splitConfidence);
        });

        document.getElementById("review-gate-document-threshold-body").innerHTML = thresholdRows(
            settings.per_document_type_thresholds,
            "document"
        );
        document.getElementById("review-gate-field-threshold-body").innerHTML = thresholdRows(
            settings.field_threshold_overrides,
            "field"
        );
    }

    function render() {
        renderSummary();
        renderForm();
    }

    async function loadRules() {
        const payload = await window.DocFlow.apiGet("/api/admin/review-gate-rules");
        state.settings = payload.settings || {};
        state.taskKey = payload.task_key || "";
        state.source = payload.source || "";
        state.passThrough = payload.pass_through_behavior || {};
        render();
    }

    async function saveRules() {
        const payload = await window.DocFlow.apiPut("/api/admin/review-gate-rules", { settings: readSettings() });
        state.settings = payload.settings || {};
        state.taskKey = payload.task_key || "";
        state.source = payload.source || "";
        state.passThrough = payload.pass_through_behavior || {};
        render();
        window.DocFlow.showToast("Review gate rules saved", "success");
    }

    function addThreshold(type) {
        state.settings = readSettings();
        const mapName = type === "document" ? "per_document_type_thresholds" : "field_threshold_overrides";
        const prefix = type === "document" ? "document_type" : "field_key";
        let index = 1;
        let key = `${prefix}_${index}`;
        while (state.settings[mapName][key] !== undefined) {
            index += 1;
            key = `${prefix}_${index}`;
        }
        state.settings[mapName][key] = state.settings.confidence_threshold;
        render();
    }

    function removeThreshold(type, index) {
        state.settings = readSettings();
        const mapName = type === "document" ? "per_document_type_thresholds" : "field_threshold_overrides";
        const entries = Object.entries(state.settings[mapName] || {});
        entries.splice(index, 1);
        state.settings[mapName] = Object.fromEntries(entries);
        render();
    }

    document.getElementById("review-gate-confidence-range").addEventListener("input", (event) => {
        document.getElementById("review-gate-confidence-input").value = event.target.value;
        document.getElementById("review-gate-threshold-summary").textContent = percent(event.target.value);
    });
    document.getElementById("review-gate-confidence-input").addEventListener("input", (event) => {
        document.getElementById("review-gate-confidence-range").value = event.target.value;
        document.getElementById("review-gate-threshold-summary").textContent = percent(event.target.value);
    });
    document.getElementById("review-gate-refresh-button").addEventListener("click", () => {
        loadRules().catch((error) => window.DocFlow.showToast(error.message || "Unable to load rules", "error"));
    });
    document.getElementById("review-gate-save-button").addEventListener("click", () => {
        saveRules().catch((error) => window.DocFlow.showToast(error.message || "Unable to save rules", "error"));
    });
    document.getElementById("review-gate-add-document-threshold").addEventListener("click", () => addThreshold("document"));
    document.getElementById("review-gate-add-field-threshold").addEventListener("click", () => addThreshold("field"));
    workspace.addEventListener("click", (event) => {
        const button = event.target.closest("[data-remove-threshold]");
        if (button) {
            removeThreshold(button.dataset.removeThreshold, Number(button.dataset.index));
        }
    });

    loadRules().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load review gate rules", "error");
    });
})();
