(function () {
    "use strict";

    const workspace = document.getElementById("upload-workspace");
    if (!workspace) {
        return;
    }

    const maxUploadMb = Number(workspace.dataset.maxUploadMb || "50");
    const maxUploadBytes = maxUploadMb * 1024 * 1024;
    const dropZone = document.getElementById("upload-drop-zone");
    const fileInput = document.getElementById("pdf-file-input");
    const fileList = document.getElementById("selected-file-list");
    const fileCount = document.getElementById("selected-file-count");
    const fileSummary = document.getElementById("selected-file-summary");
    const startButton = document.getElementById("start-processing-button");
    const uploadAlert = document.getElementById("upload-alert");
    const uploadStatus = document.getElementById("upload-status");
    const pipelineList = document.getElementById("pipeline-version-list");
    const pipelineAlert = document.getElementById("pipeline-selection-alert");
    const pipelineRefresh = document.getElementById("pipeline-selection-refresh");
    let selectedFiles = [];
    let availablePipelines = [];
    let selectedPipelineVersionId = "";
    let uploading = false;

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatBytes(bytes) {
        if (!bytes) {
            return "0 B";
        }
        const units = ["B", "KB", "MB", "GB"];
        const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
        const value = bytes / Math.pow(1024, index);
        return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
    }

    function validateFile(file) {
        const name = file.name || "";
        if (!name.toLowerCase().endsWith(".pdf")) {
            return "Only PDF files are accepted";
        }
        if (file.type && file.type !== "application/pdf" && file.type !== "application/x-pdf") {
            return "Browser reported a non-PDF file type";
        }
        if (file.size > maxUploadBytes) {
            return `File exceeds ${maxUploadMb} MB`;
        }
        return "";
    }

    function fileKey(file) {
        return `${file.name}:${file.size}:${file.lastModified}`;
    }

    function setAlert(message) {
        if (!uploadAlert) {
            return;
        }
        uploadAlert.textContent = message || "";
        uploadAlert.classList.toggle("hidden", !message);
    }

    function setPipelineAlert(message) {
        pipelineAlert.textContent = message || "";
        pipelineAlert.classList.toggle("hidden", !message);
    }

    function renderPipelines() {
        if (!availablePipelines.length) {
            pipelineList.innerHTML = '<div class="empty-panel md:col-span-2 xl:col-span-3">No active pipeline versions are available. Ask an administrator to publish and activate one.</div>';
            setPipelineAlert("Processing is unavailable until an eligible pipeline version exists.");
            return;
        }
        setPipelineAlert("");
        pipelineList.innerHTML = availablePipelines.map((pipeline) => {
            const selected = pipeline.pipeline_version_id === selectedPipelineVersionId;
            return `
                <label class="cursor-pointer rounded-lg border p-4 transition ${selected ? "border-primary bg-primary/5 ring-1 ring-primary" : "border-base-300 hover:border-primary/50"}">
                    <span class="flex items-start gap-3">
                        <input class="radio radio-primary radio-sm mt-0.5" type="radio" name="pipeline-version" value="${escapeHtml(pipeline.pipeline_version_id)}" ${selected ? "checked" : ""}>
                        <span class="min-w-0">
                            <span class="block font-semibold">${escapeHtml(pipeline.name || pipeline.template_key)}</span>
                            <span class="mt-0.5 block text-xs text-base-content/50">${escapeHtml(pipeline.template_key)} · Version ${escapeHtml(pipeline.version_number)} · ${escapeHtml(pipeline.step_count)} safe display step(s)</span>
                            <span class="mt-0.5 block text-xs text-base-content/50">Published ${escapeHtml(window.DocFlow.formatDateTime(pipeline.published_at) || "—")}</span>
                            ${pipeline.document_type ? `<span class="mt-2 inline-block badge badge-outline badge-sm">${escapeHtml(pipeline.document_type)}</span>` : ""}
                            ${pipeline.description ? `<span class="mt-2 block text-sm text-base-content/70">${escapeHtml(pipeline.description)}</span>` : ""}
                            ${pipeline.operator_instructions ? `<span class="mt-2 block rounded bg-base-200 p-2 text-xs">${escapeHtml(pipeline.operator_instructions)}</span>` : ""}
                        </span>
                    </span>
                </label>
            `;
        }).join("");
    }

    async function loadPipelines() {
        const payload = await window.DocFlow.apiGet("/api/pipelines/available?source=upload");
        availablePipelines = payload.pipelines || [];
        selectedPipelineVersionId = window.DocFlowOperatorPipeline.refreshSelection(
            selectedPipelineVersionId,
            availablePipelines
        );
        renderPipelines();
        renderSelectedFiles();
    }

    function handleFileSelection(files) {
        const existing = new Set(selectedFiles.map((entry) => entry.key));
        Array.from(files || []).forEach((file) => {
            const key = fileKey(file);
            if (existing.has(key)) {
                return;
            }
            existing.add(key);
            selectedFiles.push({
                key,
                file,
                error: validateFile(file),
            });
        });
        renderSelectedFiles();
    }

    function removeFile(key) {
        selectedFiles = selectedFiles.filter((entry) => entry.key !== key);
        renderSelectedFiles();
    }

    function renderSelectedFiles() {
        const validFiles = selectedFiles.filter((entry) => !entry.error);
        const totalSize = selectedFiles.reduce((total, entry) => total + entry.file.size, 0);
        fileCount.textContent = `${selectedFiles.length} ${selectedFiles.length === 1 ? "file" : "files"}`;
        fileSummary.textContent = `Total files: ${selectedFiles.length} | Total size: ${formatBytes(totalSize)}`;
        startButton.disabled = !window.DocFlowOperatorPipeline.canStart(
            selectedFiles,
            selectedPipelineVersionId,
            uploading
        );

        if (!selectedFiles.length) {
            fileList.innerHTML = '<div class="empty-panel">No files selected</div>';
            setAlert("");
            return;
        }

        fileList.innerHTML = selectedFiles
            .map((entry) => {
                const statusIcon = entry.error
                    ? '<span class="badge badge-error badge-sm">Invalid</span>'
                    : '<svg class="w-5 h-5 text-success shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>';
                return `
                    <div class="upload-file-row">
                        <div class="w-8 h-8 bg-error/10 rounded flex items-center justify-center shrink-0">
                            <svg class="w-4 h-4 text-error" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" /></svg>
                        </div>
                        <div class="flex-1 min-w-0">
                            <p class="text-sm font-medium truncate">${escapeHtml(entry.file.name)}</p>
                            <p class="text-xs text-base-content/50">${formatBytes(entry.file.size)}${entry.error ? ` | ${escapeHtml(entry.error)}` : ""}</p>
                        </div>
                        ${statusIcon}
                        <button class="btn btn-ghost btn-xs" type="button" data-remove-file="${escapeHtml(entry.key)}" aria-label="Remove ${escapeHtml(entry.file.name)}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                    </div>
                `;
            })
            .join("");

        const invalid = selectedFiles.find((entry) => entry.error);
        setAlert(invalid ? `${invalid.file.name}: ${invalid.error}` : "");
    }

    async function uploadBatch() {
        const validFiles = selectedFiles.filter((entry) => !entry.error);
        if (!window.DocFlowOperatorPipeline.canStart(
            selectedFiles,
            selectedPipelineVersionId,
            uploading
        )) {
            return;
        }

        const formData = new FormData();
        formData.append("pipeline_version_id", selectedPipelineVersionId);
        validFiles.forEach((entry) => formData.append("files", entry.file, entry.file.name));

        uploading = true;
        startButton.disabled = true;
        startButton.classList.add("loading");
        uploadStatus.textContent = "Uploading batch...";
        setAlert("");

        try {
            const response = await fetch("/api/batches/upload", {
                method: "POST",
                credentials: "same-origin",
                headers: window.DocFlow ? window.DocFlow.csrfHeaders("POST") : {},
                body: formData,
            });
            if (response.status === 401) {
                window.location.href = "/login";
                return;
            }
            if (!response.ok) {
                let detail = response.statusText;
                try {
                    const payload = await response.json();
                    detail = payload.detail || detail;
                } catch (error) {
                    detail = response.statusText;
                }
                const requestError = new Error(typeof detail === "string" ? detail : detail.message || "Upload failed");
                requestError.status = response.status;
                throw requestError;
            }
            const payload = await response.json();
            window.location.href = `/app/batches/${encodeURIComponent(payload.batch_id)}`;
        } catch (error) {
            uploading = false;
            startButton.classList.remove("loading");
            startButton.disabled = false;
            uploadStatus.textContent = "";
            setAlert(error.message || "Upload failed");
            if ([400, 403, 409].includes(error.status)) {
                selectedPipelineVersionId = "";
                await loadPipelines();
                setPipelineAlert("The selected version is no longer eligible. Choose again from the refreshed list.");
            }
            if (window.DocFlow) {
                window.DocFlow.showToast(error.message || "Upload failed", "error");
            }
        }
    }

    fileInput.addEventListener("change", (event) => {
        handleFileSelection(event.target.files);
        event.target.value = "";
    });

    fileList.addEventListener("click", (event) => {
        const button = event.target.closest("[data-remove-file]");
        if (button) {
            removeFile(button.dataset.removeFile);
        }
    });

    pipelineList.addEventListener("change", (event) => {
        const input = event.target.closest("input[name='pipeline-version']");
        if (!input) return;
        selectedPipelineVersionId = input.value;
        renderPipelines();
        renderSelectedFiles();
    });
    pipelineRefresh.addEventListener("click", () => {
        loadPipelines().catch((error) => setPipelineAlert(error.message));
    });

    ["dragenter", "dragover"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.add("drag-active");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.remove("drag-active");
        });
    });

    dropZone.addEventListener("drop", (event) => {
        handleFileSelection(event.dataTransfer.files);
    });

    startButton.addEventListener("click", uploadBatch);

    window.UploadProcess = {
        handleFileSelection,
        renderSelectedFiles,
        uploadBatch,
        loadPipelines,
    };
    loadPipelines().catch((error) => {
        setPipelineAlert(error.message || "Unable to load available pipelines.");
        renderSelectedFiles();
    });
})();
