(function () {
    "use strict";

    const workspace = document.getElementById("settings-workspace");
    if (!workspace) {
        return;
    }

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

    function percent(value) {
        const number = Number(value);
        return Number.isFinite(number) ? `${Math.round(number * 100)}%` : "-";
    }

    function displayValue(value) {
        if (value === null || value === undefined || value === "") {
            return "-";
        }
        if (typeof value === "boolean") {
            return value ? "Yes" : "No";
        }
        if (Array.isArray(value)) {
            return value.length ? value.join(", ") : "-";
        }
        if (typeof value === "object") {
            return JSON.stringify(value);
        }
        return String(value);
    }

    function tableRows(rows) {
        if (!rows.length) {
            return '<tr><td colspan="2" class="text-center text-base-content/50 py-10">No settings available</td></tr>';
        }
        return rows.map((row) => `
            <tr>
                <th class="w-48">${escapeHtml(row.label)}</th>
                <td class="font-mono text-xs break-all">${escapeHtml(displayValue(row.value))}</td>
            </tr>
        `).join("");
    }

    function renderSummary(payload) {
        const application = payload.application || {};
        const review = payload.review || {};
        const reviewGate = review.review_gate || {};
        const split = payload.split || {};
        const pipeline = payload.pipeline || [];
        document.getElementById("settings-app-name").textContent = application.app_name || "DocFlow AI";
        document.getElementById("settings-page-size").textContent = `${application.page_size || 25} rows per page`;
        document.getElementById("settings-pipeline-count").textContent = String(pipeline.length);
        document.getElementById("settings-review-lock").textContent = `${review.lock_timeout_minutes || 60}m`;
        document.getElementById("settings-review-queue").textContent = review.default_queue_name || "default_review";
        document.getElementById("settings-split-state").textContent = split.enabled ? "Enabled" : "Disabled";
        document.getElementById("settings-split-state").classList.toggle("text-success", Boolean(split.enabled));
        document.getElementById("settings-split-detail").textContent = split.configured
            ? `${split.categories_count || 0} categories`
            : "No split task";
        if (reviewGate.configured) {
            document.getElementById("settings-review-lock").title = `Review gate threshold ${percent(reviewGate.confidence_threshold)}`;
        }
    }

    function renderPaths(paths, split) {
        const rows = [
            { label: "Watch folder", value: paths.watch_folder_dir },
            { label: "Processing folder", value: paths.processing_dir },
            { label: "Upload folder", value: paths.upload_dir },
            { label: "SQLite database", value: paths.database_path },
            { label: "Split output", value: split && split.configured ? split.split_dir : null },
        ];
        document.getElementById("settings-paths-body").innerHTML = tableRows(rows);
    }

    function renderReview(review) {
        const gate = review.review_gate || {};
        const rows = [
            { label: "Default queue", value: review.default_queue_name },
            { label: "Lock timeout", value: `${review.lock_timeout_minutes || 60} minutes` },
            { label: "Review gate task", value: gate.configured ? gate.task_key : "Not configured" },
            { label: "Confidence threshold", value: percent(gate.confidence_threshold) },
            { label: "Review scope", value: titleCase(gate.review_scope) },
            { label: "Always review", value: gate.always_review },
            { label: "Schema file", value: gate.schema_file },
            { label: "Field overrides", value: gate.field_threshold_overrides || {} },
            { label: "Document type thresholds", value: gate.per_document_type_thresholds || {} },
        ];
        document.getElementById("settings-review-body").innerHTML = tableRows(rows);
    }

    function renderPipeline(steps) {
        const body = document.getElementById("settings-pipeline-body");
        if (!Array.isArray(steps) || !steps.length) {
            body.innerHTML = '<tr><td colspan="5" class="text-center text-base-content/50 py-10">No configured pipeline steps</td></tr>';
            return;
        }
        body.innerHTML = steps.map((step) => `
            <tr>
                <td>${escapeHtml(Number(step.index || 0) + 1)}</td>
                <td>
                    <div class="font-semibold">${escapeHtml(step.label || step.key)}</div>
                    <div class="text-xs text-base-content/50 font-mono">${escapeHtml(step.key)}</div>
                </td>
                <td>${escapeHtml(step.class || "-")}</td>
                <td class="font-mono text-xs break-all">${escapeHtml(step.module || "-")}</td>
                <td>${escapeHtml(step.on_error || "-")}</td>
            </tr>
        `).join("");
    }

    function render(payload) {
        renderSummary(payload);
        renderPaths(payload.paths || {}, payload.split || {});
        renderReview(payload.review || {});
        renderPipeline(payload.pipeline || []);
    }

    async function loadSettings() {
        const payload = await window.DocFlow.apiGet("/api/settings");
        render(payload || {});
    }

    document.getElementById("settings-refresh-button").addEventListener("click", () => {
        loadSettings().catch((error) => window.DocFlow.showToast(error.message || "Unable to load settings", "error"));
    });

    loadSettings().catch((error) => {
        window.DocFlow.showToast(error.message || "Unable to load settings", "error");
    });
})();
