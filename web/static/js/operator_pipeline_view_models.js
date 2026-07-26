(function () {
    "use strict";

    function canStart(files, selectedVersionId, uploading) {
        const entries = files || [];
        return !uploading
            && Boolean(selectedVersionId)
            && entries.length > 0
            && entries.every((entry) => !entry.error);
    }

    function refreshSelection(currentId, pipelines) {
        return (pipelines || []).some((item) => item.pipeline_version_id === currentId)
            ? currentId
            : "";
    }

    function pipelineLabel(item) {
        return `${item.name || item.template_key} · v${item.version_number}`;
    }

    window.DocFlowOperatorPipeline = {
        canStart,
        refreshSelection,
        pipelineLabel,
    };
})();
