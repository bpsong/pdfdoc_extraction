(() => {
    "use strict";
    const $ = id => document.getElementById(id);
    const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
    const date = value => value ? new Date(value).toLocaleString() : "No activity";
    let rows = [], templates = [], versions = [], current = null, busy = false, opener = null;
    let activityId = null, activityOffset = 0;
    const dialog = $("watch-dialog");
    async function request(url, method = "GET", body) {
        const response = await fetch(url, {method, credentials:"same-origin", headers:{"Content-Type":"application/json", ...window.DocFlow.csrfHeaders(method)}, ...(body ? {body:JSON.stringify(body)} : {})});
        const payload = await response.json();
        if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : payload.detail?.message || "Unable to complete request.");
        return payload;
    }
    function render() {
        const visible = window.WatchFolderViewModels.filterBindings(rows, {search:$("watch-search").value, status:$("watch-status").value, health:$("watch-health").value, retired:$("watch-retired").checked, updates:$("watch-updates").checked});
        $("watch-rows").innerHTML = visible.map(row => `<tr>
            <td class="watch-path-cell">${escape(row.folder_path)}</td>
            <td><span class="badge ${row.enabled ? "badge-success" : "badge-ghost"} badge-sm">${escape(row.state)}</span></td>
            <td>${escape(row.pipeline?.name || "Unbound")}</td>
            <td>${row.pipeline ? `v${escape(row.pipeline.version_number)}` : "—"}${row.update_available ? `<span class="watch-version-note">Update available: v${escape(row.latest_version.version_number)}</span>` : row.pipeline ? '<small>Latest</small>' : ""}</td>
            <td>${escape(row.health_status)}${row.validation_findings.map(f => `<small class="text-error">${escape(f.message)}</small>`).join("")}${row.health?.issue ? `<small class="text-error">${escape(row.health.issue)}</small>` : ""}<small>Last scan: ${escape(date(row.health?.last_scan_at))}</small><small>Ignored files: ${row.health?.ignored_count || 0}</small></td>
            <td>${escape(date(row.health?.last_ingested_at))}</td>
            <td>${row.state !== "retired" ? `<button class="btn btn-outline btn-xs" data-edit="${escape(row.id)}">Edit</button><button class="btn btn-ghost btn-xs" data-action="${row.enabled ? "pause" : "resume"}" data-id="${escape(row.id)}" ${!row.pipeline_version_id ? "disabled" : ""}>${row.enabled ? "Pause" : "Resume"}</button><button class="btn btn-ghost btn-xs" data-check="${escape(row.id)}">Check now</button>` : ""}<button class="btn btn-ghost btn-xs" data-activity="${escape(row.id)}">Activity</button></td>
        </tr>`).join("") || '<tr><td colspan="7">No watch folders match these filters.</td></tr>';
        const live = rows.filter(row => row.state !== "retired");
        $("watch-summary").textContent = `${visible.length} shown · ${live.length} current bindings · ${live.filter(row => row.enabled).length} enabled · ${live.filter(row => row.update_available).length} updates available`;
    }
    async function load() {
        rows = (await request("/api/admin/watch-folder-bindings")).bindings;
        render();
    }
    function showError(error) { $("watch-message").textContent = error.message; }
    async function loadVersions(selected = null) {
        const templateId = $("watch-pipeline").value;
        versions = templateId ? (await request(`/api/admin/pipeline-templates/${encodeURIComponent(templateId)}/versions`)).versions : [];
        versions.sort((a,b) => b.version_number - a.version_number);
        $("watch-version").innerHTML = '<option value="">Select version</option>' + versions.map((v,i) => `<option value="${escape(v.id)}">v${escape(v.version_number)}${i === 0 ? " — Latest" : ""} · ${escape(date(v.published_at))}</option>`).join("");
        $("watch-version").value = selected || versions[0]?.id || "";
        $("watch-upgrade").disabled = !versions.length;
        if (!templateId) $("watch-enabled").checked = false;
    }
    async function edit(id) {
        current = rows.find(row => row.id === id) || null;
        opener = document.activeElement;
        $("watch-title").textContent = current ? "Edit watch folder" : "Add watch folder";
        $("watch-path").value = current?.folder_path || "";
        $("watch-enabled").checked = current?.enabled || false;
        $("watch-error").textContent = "";
        $("watch-check-result").textContent = "";
        $("watch-existing-actions").hidden = !current;
        $("watch-delete").hidden = !current?.can_delete;
        templates = (await request("/api/admin/pipeline-templates")).templates;
        $("watch-pipeline").innerHTML = '<option value="">Unbound</option>' + templates.filter(t => t.status === "active" || t.id === current?.pipeline_template_id).map(t => `<option value="${escape(t.id)}">${escape(t.name)}${t.status !== "active" ? ` (${escape(t.status)})` : ""}</option>`).join("");
        $("watch-pipeline").value = current?.pipeline_template_id || "";
        await loadVersions(current?.pipeline_version_id);
        dialog.showModal();
        $("watch-path").focus();
    }
    function close() { if (!busy) { dialog.close(); opener?.focus(); } }
    function confirmChange(message) {
        return new Promise(resolve => {
            const confirm = $("watch-confirm");
            $("watch-confirm-text").textContent = message;
            confirm.returnValue = "cancel";
            confirm.addEventListener("close", () => resolve(confirm.returnValue === "confirm"), {once:true});
            confirm.showModal();
        });
    }
    async function mutate(row, action) {
        const messages = {pause:"Pause new ingestion? Existing documents continue processing.",resume:"Resume ingestion using the assigned version? Files already in the folder may be ingested.",unbind:"Unbind this pipeline and stop new ingestion? Existing documents retain their assignments.",retire:"Retire this binding? History is retained and the path becomes available for reuse. Files on disk are not deleted.",delete:"Permanently delete this unused setting? Files on disk are not deleted."};
        if (!row || !await confirmChange(messages[action])) return;
        await request(`/api/admin/watch-folder-bindings/${encodeURIComponent(row.id)}`, action === "delete" ? "DELETE" : "PATCH", action === "delete" ? undefined : {action, expected_revision:row.revision});
        close();
        await load();
        $("watch-message").textContent = "Binding updated.";
    }
    $("watch-form").addEventListener("submit", async event => {
        event.preventDefault();
        if (busy) return;
        const path = $("watch-path").value.trim(), pipeline = $("watch-pipeline").value, version = $("watch-version").value, enabled = $("watch-enabled").checked;
        const error = window.WatchFolderViewModels.validateForm(path, pipeline, version, enabled);
        if (error) { $("watch-error").textContent = error; return; }
        if (current && (current.pipeline_version_id !== (version || null) || current.enabled !== enabled || current.folder_path !== path)
            && !await confirmChange("Apply these changes to future ingestion? An already-started file claim may finish. Existing batches and documents retain their assigned version.")) return;
        busy = true;
        $("watch-save").disabled = true;
        try {
            const body = {enabled, ...(version ? {pipeline_version_id:version} : current ? {action:"unbind"} : {pipeline_version_id:""})};
            // Do not revalidate an unchanged inaccessible path during an emergency pause.
            if (!current || path !== current.folder_path) body.folder_path = path;
            if (current) body.expected_revision = current.revision;
            await request(`/api/admin/watch-folder-bindings${current ? `/${encodeURIComponent(current.id)}` : ""}`, current ? "PATCH" : "POST", body);
            busy = false;
            close();
            await load();
        } catch(error) { $("watch-error").textContent = error.message; }
        finally { busy = false; $("watch-save").disabled = false; }
    });
    async function check(path, target) {
        target.textContent = "Checking folder access…";
        const result = await request("/api/admin/watch-folder-check", "POST", {folder_path:path});
        target.textContent = `${result.ok ? "Access check passed" : "Access check failed"}: ${result.message}`;
    }
    async function activity() {
        const payload = await request(`/api/admin/watch-folder-bindings/${encodeURIComponent(activityId)}/activity?offset=${activityOffset}`);
        $("watch-activity-body").innerHTML = `<p><a href="/app/reports?ingress_binding_id=${encodeURIComponent(activityId)}">View this folder in Reports →</a></p><h3>Recent batches</h3><ul>${payload.batches.map(batch => `<li><a href="/app/batches/${encodeURIComponent(batch.id)}">${escape(date(batch.created_at))} · ${escape(batch.status)}</a></li>`).join("") || "<li>No batches on this page.</li>"}</ul><h3>Configuration history</h3><ul>${payload.events.map(event => `<li>${escape(date(event.created_at))} · ${escape(event.event_type)} · ${escape(event.user || "system")}</li>`).join("") || "<li>No changes on this page.</li>"}</ul>`;
        $("watch-activity-prev").disabled = activityOffset === 0;
        $("watch-activity-next").disabled = payload.batches.length < 20 && payload.events.length < 20;
    }
    $("watch-rows").addEventListener("click", async event => {
        const button = event.target.closest("button"); if (!button) return;
        try {
            if (button.dataset.edit) await edit(button.dataset.edit);
            if (button.dataset.action) await mutate(rows.find(row => row.id === button.dataset.id), button.dataset.action);
            if (button.dataset.check) { await check(rows.find(row => row.id === button.dataset.check).folder_path, $("watch-message")); await load(); }
            if (button.dataset.activity) { activityId = button.dataset.activity; activityOffset = 0; await activity(); $("watch-activity").showModal(); }
        } catch(error) { showError(error); }
    });
    $("watch-existing-actions").addEventListener("click", event => {
        const action = event.target.dataset.lifecycle;
        if (action) mutate(current, action).catch(error => $("watch-error").textContent = error.message);
    });
    $("watch-add").onclick = () => edit(null).catch(showError);
    $("watch-refresh").onclick = () => load().catch(showError);
    $("watch-test").onclick = () => check($("watch-path").value, $("watch-check-result")).catch(error => $("watch-check-result").textContent = error.message);
    $("watch-pipeline").onchange = () => loadVersions().catch(error => $("watch-error").textContent = error.message);
    $("watch-upgrade").onclick = () => { $("watch-version").value = versions[0]?.id || ""; };
    $("watch-close").onclick = close;
    $("watch-cancel").onclick = close;
    dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
    ["watch-search","watch-status","watch-health","watch-updates","watch-retired"].forEach(id => $(id).addEventListener("input", render));
    $("watch-activity-close").onclick = () => $("watch-activity").close();
    $("watch-activity-prev").onclick = () => {activityOffset = Math.max(0,activityOffset - 20); activity().catch(showError);};
    $("watch-activity-next").onclick = () => {activityOffset += 20; activity().catch(showError);};
    load().catch(showError);
})();
