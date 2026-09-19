/** Upload selection, pipeline, and progress presentation. */
export function createView(deps) {
    const { fileList, fileCount, fileSummary, startButton, uploadAlert, uploadStatus, uploadProgressBar, uploadProgressLabel, pipelineList, pipelineAlert, docFlow, operatorPipeline, getState, model } = deps;
    const { escapeHtml, formatBytes, validateBatch } = model;
    let lastAnnouncedUploadMilestone = -1;
    function setAlert(message) {
        if (!uploadAlert) {
            return;
        }
        uploadAlert.textContent = message || "";
        uploadAlert.classList.toggle("hidden", !message);
    }

    function updateUploadProgress(loaded, total) {
        const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0;
        uploadProgressBar.value = percent;
        uploadProgressLabel.textContent = `${percent}%`;
        const milestone = Math.floor(percent / 25) * 25;
        if (milestone > lastAnnouncedUploadMilestone && uploadStatus) {
            uploadStatus.textContent = `Uploading batch... ${percent}%`;
            lastAnnouncedUploadMilestone = milestone;
        }
    }

    function setPipelineAlert(message) {
        pipelineAlert.textContent = message || "";
        pipelineAlert.classList.toggle("hidden", !message);
    }

    function renderPipelines() {
        if (!getState().availablePipelines.length) {
            pipelineList.innerHTML = '<div class="empty-panel md:col-span-2 xl:col-span-3">No active pipeline versions are available. Ask an administrator to publish and activate one.</div>';
            setPipelineAlert("Processing is unavailable until an eligible pipeline version exists.");
            return;
        }
        setPipelineAlert("");
        pipelineList.innerHTML = getState().availablePipelines.map((pipeline) => {
            const selected = pipeline.pipeline_version_id === getState().selectedPipelineVersionId;
            return `
                <div class="upload-pipeline-card rounded-lg border ${selected ? "border-primary bg-primary/5 ring-1 ring-primary" : "border-base-300"}">
                    <label class="upload-pipeline-choice cursor-pointer">
                        <input class="radio radio-primary radio-sm" type="radio" name="pipeline-version" value="${escapeHtml(pipeline.pipeline_version_id)}" ${selected ? "checked" : ""}>
                        <span class="min-w-0">
                            <span class="block font-semibold">${escapeHtml(pipeline.name || pipeline.template_key)}</span>
                            <span class="block text-xs text-base-content/60">Version ${escapeHtml(pipeline.version_number)}</span>
                        </span>
                    </label>
                    <details class="upload-pipeline-details">
                        <summary>Pipeline details</summary>
                        <div>
                            <p>${escapeHtml(pipeline.template_key)} &middot; ${escapeHtml(pipeline.step_count)} steps</p>
                            <p>Published ${escapeHtml(docFlow.formatDateTime(pipeline.published_at) || "—")}</p>
                            ${pipeline.document_type ? `<p>${escapeHtml(pipeline.document_type)}</p>` : ""}
                            ${pipeline.description ? `<p>${escapeHtml(pipeline.description)}</p>` : ""}
                            ${pipeline.operator_instructions ? `<p>${escapeHtml(pipeline.operator_instructions)}</p>` : ""}
                        </div>
                    </details>
                </div>
            `;
        }).join("");
    }

    function renderSelectedFiles() {
        const validFiles = getState().selectedFiles.filter((entry) => !entry.error);
        const totalSize = getState().selectedFiles.reduce((total, entry) => total + entry.file.size, 0);
        const batchError = validateBatch(getState().selectedFiles);
        fileCount.textContent = `${getState().selectedFiles.length} ${getState().selectedFiles.length === 1 ? "file" : "files"}`;
        fileSummary.textContent = `Total files: ${getState().selectedFiles.length} | Total size: ${formatBytes(totalSize)}`;
        startButton.disabled = Boolean(batchError) || !operatorPipeline.canStart(
            getState().selectedFiles,
            getState().selectedPipelineVersionId,
            getState().uploading
        );

        if (!getState().selectedFiles.length) {
            fileList.innerHTML = '<div class="empty-panel">No files selected</div>';
            setAlert("");
            return;
        }

        fileList.innerHTML = getState().selectedFiles
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

        const invalid = getState().selectedFiles.find((entry) => entry.error);
        setAlert(invalid ? `${invalid.file.name}: ${invalid.error}` : batchError);
    }
    function resetUploadMilestones() { lastAnnouncedUploadMilestone = -1; }
    return { setAlert, updateUploadProgress, setPipelineAlert, renderPipelines, renderSelectedFiles, resetUploadMilestones };
}
