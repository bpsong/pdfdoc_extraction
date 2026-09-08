(function (root) {
    "use strict";
    function filterBindings(rows, filters) {
        const query = (filters.search || "").toLowerCase();
        return rows.filter(row => (filters.retired || row.state !== "retired")
            && (!filters.status || row.state === filters.status)
            && (!filters.health || row.health_status === filters.health)
            && (!filters.updates || row.update_available)
            && `${row.folder_path} ${row.pipeline?.name || ""}`.toLowerCase().includes(query));
    }
    function validateForm(path, pipeline, version, enabled) {
        if (!path.trim()) return "Folder path is required.";
        if (pipeline && !version) return "Choose a published version.";
        if (enabled && !version) return "Bind a published version before enabling.";
        return "";
    }
    const api = { filterBindings, validateForm };
    if (typeof module !== "undefined") module.exports = api;
    else root.WatchFolderViewModels = api;
})(typeof window === "undefined" ? globalThis : window);
