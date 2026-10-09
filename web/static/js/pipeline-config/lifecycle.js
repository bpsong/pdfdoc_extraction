/** Explicit archive and retention actions, with native modal focus handling. */
export function createPipelineLifecycle({ api, getTemplate, hasUnsavedChanges, onArchived, escapeHtml }) {
    const byId = (id) => document.getElementById(`pipeline-lifecycle-${id}`);
    const dialog = byId("dialog"), title = byId("title"), body = byId("body");
    const error = byId("error"), next = byId("next"), close = byId("close");
    let template, mode, preview, busy = false;
    const labels = {
        batches: "Batches", documents: "Documents", processing_jobs: "Processing jobs",
        task_runs: "Task runs", extraction_results: "Extraction results", extracted_fields: "Extracted fields",
        review_items: "Completed review items", review_locks: "Expired review locks",
        manual_split_decisions: "Split decisions", document_files: "File registrations",
        upload_submissions: "Upload receipts to trim",
    };
    function counts(values) {
        return `<dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">${Object.entries(labels).filter(([key]) => key in values).map(([key, label]) =>
            `<dt>${escapeHtml(label)}</dt><dd class="text-right font-semibold">${Number(values[key])}</dd>`).join("")}</dl>`;
    }
    const retained = `<p class="mt-4 text-sm">Pipeline definitions, published versions, audit events, and files on disk are retained. Deleted history disappears from reports and document/review pages; file preview links for deleted records stop working.</p>
        <p class="mt-2 text-sm text-base-content/60">SQLite can reuse the freed space. The database file may keep its current size; disk compaction is a separate maintenance operation.</p>`;
    function setAction(text, disabled = false, destructive = false) {
        next.textContent = text;
        next.disabled = disabled;
        next.classList.remove("hidden");
        next.classList.toggle("btn-error", destructive);
        next.classList.toggle("btn-primary", !destructive);
    }
    function settings() {
        mode = "settings"; preview = null;
        title.textContent = `Clean up processing data · ${template.name}`;
        body.innerHTML = `<p class="text-sm">Delete finished processing history for this pipeline, including all documents in each eligible batch. Queued, running, resumable, and pending-review work is protected.</p>
            <label class="form-control mt-4"><span class="label-text">Finished before (UTC, exclusive)</span>
            <input id="pipeline-cleanup-cutoff" type="date" class="input input-bordered" required max="${new Date().toISOString().slice(0, 10)}"></label>
            <p class="mt-2 text-xs text-base-content/60">Every record in the batch must have its latest activity before midnight UTC on this date.</p>${retained}`;
        setAction("Preview cleanup");
    }
    function confirmation() {
        mode = "confirm";
        title.textContent = `Confirm cleanup · ${preview.template_name}`;
        const reasons = { pending_review: "Pending review or review lock", active_work: "Active or resumable work", recent_activity: "On or after cutoff", inconsistent_history: "Incomplete or linked history" };
        body.innerHTML = `<p class="mb-3 text-sm">Eligible history before <strong>${escapeHtml(preview.cutoff_date)} 00:00 UTC</strong></p>${counts(preview.counts)}
            <h3 class="mt-4 font-semibold">Excluded whole batches</h3><ul class="mt-2 text-sm">${Object.entries(preview.excluded).map(([key, value]) => `<li>${reasons[key]}: ${value.batches} batches / ${value.documents} documents</li>`).join("")}</ul>
            ${retained}<p class="mt-4 font-semibold">Deletion cannot be undone in the app.</p>
            <label class="form-control mt-3"><span class="label-text">Type the pipeline name: ${escapeHtml(preview.template_name)}</span><input id="pipeline-cleanup-name" class="input input-bordered" autocomplete="off"></label>
            <p class="mt-2 text-xs text-base-content/60">Preview expires in 15 minutes. Any change to eligible records requires a new preview.</p>`;
        setAction("Delete processing data", true, true);
        close.textContent = "Back";
        const input = document.getElementById("pipeline-cleanup-name");
        input.addEventListener("input", () => { next.disabled = busy || !preview.counts.batches || input.value !== preview.template_name; });
        title.focus();
        dialog.querySelector(".modal-box").scrollTop = 0;
    }
    async function open(action) {
        const selected = getTemplate();
        if (!selected) {
            window.DocFlow.showToast("Wait for the selected pipeline to finish loading.", "warning");
            return;
        }
        if (action === "archive" && hasUnsavedChanges()) {
            window.DocFlow.showToast("Save or discard draft changes before archiving this pipeline.", "warning");
            return;
        }
        template = { ...selected }; mode = action; preview = null;
        error.textContent = ""; close.textContent = "Cancel";
        title.textContent = action === "archive" ? `Archive pipeline · ${template.name}` : "Clean up processing data";
        body.textContent = "Loading…";
        setAction("Loading…", true);
        dialog.showModal(); title.focus();
        if (action !== "archive") { settings(); return; }
        busy = true; close.disabled = true;
        try {
            preview = await api.archivePreview(template.id);
            template = preview.template;
            body.innerHTML = `<p class="text-sm">Archiving is permanent: this pipeline cannot be reactivated. It is hidden from the default admin list and unavailable for new uploads.</p>
                <p class="mt-3 text-sm">History, versions, audit events, and files remain available. Existing jobs and reviews continue; no processing data is deleted.</p>
                <p class="mt-3 text-sm">Retained: ${preview.counts.pipeline_versions} published versions, ${preview.counts.batches} batches, ${preview.counts.documents} documents. Existing work: ${preview.counts.active_jobs} queued/running jobs, ${preview.counts.pending_reviews} open reviews.</p>
                <h3 class="mt-4 font-semibold">Watch folders</h3><ul class="mt-2 break-words text-sm">${preview.bindings.map(binding => `<li>${escapeHtml(binding.folder_path)} · ${binding.retired_at ? "Retired" : binding.enabled ? "Enabled" : "Paused"}</li>`).join("") || "<li>No linked watch folders</li>"}</ul>
                <p class="mt-3 text-sm">Paused bindings keep their configuration and reserved paths. <a class="link" href="/app/admin/watch-folders">Manage watch folders</a></p>
                ${preview.blockers.map(message => `<p class="mt-3 text-sm text-error">${escapeHtml(message)}</p>`).join("")}`;
            setAction("Archive pipeline", !preview.can_archive);
        } catch (failure) { error.textContent = failure.message; }
        finally { busy = false; close.disabled = false; }
    }
    next.addEventListener("click", async () => {
        if (busy || next.disabled) return;
        busy = true; next.disabled = true; close.disabled = true; error.textContent = "";
        try {
            if (mode === "archive") {
                const result = await api.archive(template.id, template.name);
                await onArchived(result.template); dialog.close();
                window.DocFlow.showToast("Pipeline archived. Show archived is enabled so you can clean up its history.", "success");
            } else if (mode === "settings") {
                const cutoff = document.getElementById("pipeline-cleanup-cutoff");
                if (!cutoff.reportValidity()) { setAction("Preview cleanup"); return; }
                preview = await api.cleanupPreview(template.id, cutoff.value);
                confirmation();
            } else if (mode === "confirm") {
                const result = await api.cleanup(template.id, preview.preview_id, document.getElementById("pipeline-cleanup-name").value);
                mode = "done"; title.textContent = "Processing data cleaned up";
                body.innerHTML = counts(result.deleted) + `<p class="mt-4 text-sm">Trimmed ${result.receipts_tombstoned} upload receipts. Files deleted: 0.</p>${retained}`;
                next.classList.add("hidden"); close.textContent = "Done";
                title.focus();
            }
        } catch (failure) {
            // A failed confirmation must obtain a fresh, reviewable preview.
            if (mode === "confirm") { settings(); close.textContent = "Cancel"; }
            error.textContent = failure.message;
            next.disabled = mode === "archive";
        } finally { busy = false; close.disabled = false; }
    });
    close.addEventListener("click", () => {
        if (busy) return;
        error.textContent = "";
        if (mode === "confirm") { settings(); close.textContent = "Cancel"; }
        else dialog.close();
    });
    dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
    document.getElementById("pipeline-archive-button").addEventListener("click", () => open("archive"));
    document.getElementById("pipeline-cleanup-button").addEventListener("click", () => open("settings"));
}
