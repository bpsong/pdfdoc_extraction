(function () {
    "use strict";

    function lifecycleActions(status, hasPublishedVersion) {
        return {
            canActivate: status === "inactive" && Boolean(hasPublishedVersion),
            canDeactivate: status === "active",
            canArchive: status === "inactive",
            canEdit: status !== "archived",
            canPublish: status !== "archived",
        };
    }

    function versionLabel(item, kind) {
        const prefix = kind === "schema" ? (item.schema_key || item.template_name) : (item.template_key || item.name);
        const hash = item.content_hash ? ` · ${String(item.content_hash).slice(0, 10)}` : "";
        return `${prefix || "Template"} · v${item.version_number || "—"}${hash}`;
    }

    function groupFindings(findings) {
        return (findings || []).reduce((groups, finding) => {
            const severity = finding.severity || "error";
            (groups[severity] = groups[severity] || []).push(finding);
            return groups;
        }, {});
    }

    function conflictMessage(error) {
        const detail = error && error.detail;
        if (detail && typeof detail === "object" && detail.current) {
            return {
                message: detail.message || "The draft changed on the server.",
                current: detail.current,
                reloadRequired: true,
            };
        }
        return { message: (detail && detail.message) || detail || error.message || "Request failed.", reloadRequired: false };
    }

    window.DocFlowVersionedAdmin = {
        lifecycleActions,
        versionLabel,
        groupFindings,
        conflictMessage,
    };
})();
