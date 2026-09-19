import { createModel } from './model.js?v=controller-modularization-7a';
import { createView } from './view.js?v=controller-modularization-7a';
import { createApi } from './api.js?v=controller-modularization-7a';
(function () {
    "use strict";

    const workspace = document.getElementById("upload-workspace");
    if (!workspace) {
        return;
    }

    const maxUploadMb = Number(workspace.dataset.maxUploadMb || "50");
    const maxUploadBytes = maxUploadMb * 1024 * 1024;
    const maxUploadFiles = Number(workspace.dataset.maxUploadFiles || "20");
    const maxUploadRequestMb = Number(workspace.dataset.maxUploadRequestMb || "200");
    const maxUploadRequestBytes = maxUploadRequestMb * 1024 * 1024;
    const dropZone = document.getElementById("upload-drop-zone");
    const fileInput = document.getElementById("pdf-file-input");
    const fileList = document.getElementById("selected-file-list");
    const fileCount = document.getElementById("selected-file-count");
    const fileSummary = document.getElementById("selected-file-summary");
    const startButton = document.getElementById("start-processing-button");
    const uploadAlert = document.getElementById("upload-alert");
    const uploadStatus = document.getElementById("upload-status");
    const uploadProgressRegion = document.getElementById("upload-progress-region");
    const uploadProgressBar = document.getElementById("upload-progress-bar");
    const uploadProgressLabel = document.getElementById("upload-progress-label");
    const cancelUploadButton = document.getElementById("cancel-upload-button");
    const pipelineList = document.getElementById("pipeline-version-list");
    const pipelineAlert = document.getElementById("pipeline-selection-alert");
    const pipelineRefresh = document.getElementById("pipeline-selection-refresh");
    let selectedFiles = [];
    let availablePipelines = [];
    let selectedPipelineVersionId = "";
    let uploading = false;
    
    let submissionId = null;
    let submissionSignature = null;
    const receiptStorageKey = "docflow-upload-receipt";
    const identitiesStorageKey = "docflow-upload-identities";
    let submissionIdentities = {};
    try { submissionIdentities = JSON.parse(sessionStorage.getItem(identitiesStorageKey) || "{}"); } catch (_) {}
    const savedReceipt = sessionStorage.getItem(receiptStorageKey);
    if (savedReceipt) {
        try {
            const saved = JSON.parse(savedReceipt);
            submissionId = saved.id;
            submissionSignature = saved.signature;
        } catch (_) { sessionStorage.removeItem(receiptStorageKey); }
    }


    const model = createModel({ maxUploadMb, maxUploadBytes, maxUploadFiles, maxUploadRequestMb, maxUploadRequestBytes });
    const { escapeHtml, formatBytes, validateFile, fileKey, validateBatch } = model;
    const { setAlert, updateUploadProgress, setPipelineAlert, renderPipelines, renderSelectedFiles, resetUploadMilestones } = createView({ fileList, fileCount, fileSummary, startButton, uploadAlert, uploadStatus, uploadProgressBar, uploadProgressLabel, pipelineList, pipelineAlert, docFlow: window.DocFlow, operatorPipeline: window.DocFlowOperatorPipeline, getState: () => ({ selectedFiles, availablePipelines, selectedPipelineVersionId, uploading }), model });
    const api = createApi(window.DocFlow, updateUploadProgress, () => submissionId);
    const { uploadBatchRequest, cancelUpload } = api;
    async function resolveAcceptance() {
        if (!submissionId) return false;
        const receipt = await api.getReceipt(submissionId);
        if (receipt.status === "accepted") {
            delete submissionIdentities[submissionSignature];
            sessionStorage.setItem(identitiesStorageKey, JSON.stringify(submissionIdentities));
            sessionStorage.removeItem(receiptStorageKey);
            window.location.href = `/app/batches/${encodeURIComponent(receipt.batch_id)}`;
            return true;
        }
        return false;
    }












    async function loadPipelines() {
        const payload = await api.listPipelines();
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


    async function uploadBatch() {
        const validFiles = selectedFiles.filter((entry) => !entry.error);
        if (validateBatch(selectedFiles) || !window.DocFlowOperatorPipeline.canStart(
            selectedFiles,
            selectedPipelineVersionId,
            uploading
        )) {
            return;
        }

        const formData = new FormData();
        const signature = JSON.stringify([selectedPipelineVersionId, validFiles.map(entry => entry.key)]);
        if (submissionSignature !== signature || !submissionId) {
            submissionId = submissionIdentities[signature] || crypto.randomUUID();
            submissionSignature = signature;
        }
        submissionIdentities[signature] = submissionId;
        sessionStorage.setItem(identitiesStorageKey, JSON.stringify(submissionIdentities));
        sessionStorage.setItem(receiptStorageKey, JSON.stringify({id: submissionId, signature}));
        formData.append("pipeline_version_id", selectedPipelineVersionId);
        validFiles.forEach((entry) => formData.append("files", entry.file, entry.file.name));

        uploading = true;
        startButton.disabled = true;
        startButton.classList.add("loading");
        cancelUploadButton.classList.remove("hidden");
        cancelUploadButton.disabled = false;
        resetUploadMilestones();
        uploadProgressRegion.classList.remove("hidden");
        uploadProgressRegion.setAttribute("aria-busy", "true");
        updateUploadProgress(0, 1);
        setAlert("");

        try {
            const payload = await uploadBatchRequest(formData);
            if (!payload) {
                return;
            }
            updateUploadProgress(1, 1);
            delete submissionIdentities[submissionSignature];
            sessionStorage.setItem(identitiesStorageKey, JSON.stringify(submissionIdentities));
            sessionStorage.removeItem(receiptStorageKey);
            uploadStatus.textContent = "Upload complete. Starting processing...";
            window.location.href = `/app/batches/${encodeURIComponent(payload.batch_id)}`;
        } catch (error) {
            let accepted = false;
            try { accepted = await resolveAcceptance(); } catch (_) { /* Keep identity for retry. */ }
            if (accepted) return;
            uploading = false;
            startButton.classList.remove("loading");
            startButton.disabled = false;
            cancelUploadButton.classList.add("hidden");
            cancelUploadButton.disabled = true;
            uploadProgressRegion.setAttribute("aria-busy", "false");
            const cancelled = error.name === "AbortError";
            const busy = error.status === 429;
            uploadStatus.textContent = cancelled
                ? "Transfer stopped. Acceptance is unconfirmed; retry the same files and pipeline safely."
                : busy
                    ? "Upload capacity is temporarily full."
                    : "Upload not confirmed. Retry the same files and pipeline safely.";
            setAlert(cancelled ? "" : error.message || "Upload failed");
            if ([403, 409].includes(error.status)) {
                selectedPipelineVersionId = "";
                await loadPipelines();
                setPipelineAlert("The selected version is no longer eligible. Choose again from the refreshed list.");
            }
            if (window.DocFlow && !cancelled) {
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

    dropZone.addEventListener("keydown", (event) => {
        if (uploading || !["Enter", " "].includes(event.key)) {
            return;
        }
        event.preventDefault();
        fileInput.click();
    });

    startButton.addEventListener("click", uploadBatch);
    cancelUploadButton.addEventListener("click", cancelUpload);

    window.UploadProcess = {
        handleFileSelection,
        renderSelectedFiles,
        uploadBatch,
        cancelUpload,
        loadPipelines,
        validateBatch,
    };
    loadPipelines().catch((error) => {
        setPipelineAlert(error.message || "Unable to load available pipelines.");
        renderSelectedFiles();
    });
    if (submissionId) {
        uploadStatus.textContent = "Checking previous upload acceptance...";
        resolveAcceptance().then(accepted => {
            if (!accepted) uploadStatus.textContent = "Previous upload unconfirmed. Select the same files and pipeline to retry safely.";
        }).catch(() => {
            uploadStatus.textContent = "Unable to check previous upload. Select the same files and pipeline to retry safely.";
        });
    }
})();
