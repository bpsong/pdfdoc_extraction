/** Watch-folder list and activity presentation. */
export function createView(deps) {
    const { $, escape, date, getRows, filterBindings } = deps;
    function render() {
        const visible = window.WatchFolderViewModels.filterBindings(getRows(), {search:$("watch-search").value, status:$("watch-status").value, health:$("watch-health").value, retired:$("watch-retired").checked, updates:$("watch-updates").checked});
        $("watch-rows").innerHTML = visible.map(row => `<tr>
            <td class="watch-path-cell">${escape(row.folder_path)}</td>
            <td><span class="badge ${row.enabled ? "badge-success" : "badge-ghost"} badge-sm">${escape(row.state)}</span></td>
            <td>${escape(row.pipeline?.name || "Unbound")}</td>
            <td>${row.pipeline ? `v${escape(row.pipeline.version_number)}` : "—"}${row.update_available ? `<span class="watch-version-note">Update available: v${escape(row.latest_version.version_number)}</span>` : row.pipeline ? '<small>Latest</small>' : ""}</td>
            <td>${escape(row.health_status)}${row.validation_findings.map(f => `<small class="text-error">${escape(f.message)}</small>`).join("")}${row.health?.issue ? `<small class="text-error">${escape(row.health.issue)}</small>` : ""}<small>Last scan: ${escape(date(row.health?.last_scan_at))}</small><small>Ignored files: ${row.health?.ignored_count || 0}</small></td>
            <td>${escape(date(row.health?.last_ingested_at))}</td>
            <td>${row.state !== "retired" ? `<button class="btn btn-outline btn-xs" data-edit="${escape(row.id)}">Edit</button><button class="btn btn-ghost btn-xs" data-action="${row.enabled ? "pause" : "resume"}" data-id="${escape(row.id)}" ${!row.pipeline_version_id ? "disabled" : ""}>${row.enabled ? "Pause" : "Resume"}</button><button class="btn btn-ghost btn-xs" data-check="${escape(row.id)}">Check now</button>` : ""}<button class="btn btn-ghost btn-xs" data-activity="${escape(row.id)}">Activity</button></td>
        </tr>`).join("") || '<tr><td colspan="7">No watch folders match these filters.</td></tr>';
        const live = getRows().filter(row => row.state !== "retired");
        $("watch-summary").textContent = `${visible.length} shown · ${live.length} current bindings · ${live.filter(row => row.enabled).length} enabled · ${live.filter(row => row.update_available).length} updates available`;
    }
    function renderActivity(payload, activityId, activityOffset) {
        $("watch-activity-body").innerHTML = `<p><a href="/app/reports?ingress_binding_id=${encodeURIComponent(activityId)}">View this folder in Reports →</a></p><h3>Recent batches</h3><ul>${payload.batches.map(batch => `<li><a href="/app/batches/${encodeURIComponent(batch.id)}">${escape(date(batch.created_at))} · ${escape(batch.status)}</a></li>`).join("") || "<li>No batches on this page.</li>"}</ul><h3>Configuration history</h3><ul>${payload.events.map(event => `<li>${escape(date(event.created_at))} · ${escape(event.event_type)} · ${escape(event.user || "system")}</li>`).join("") || "<li>No changes on this page.</li>"}</ul>`;
        $("watch-activity-prev").disabled = activityOffset === 0;
        $("watch-activity-next").disabled = payload.batches.length < 20 && payload.events.length < 20;
    }
    return { render, renderActivity };
}
