"""Behavior and wiring checks for pipeline-editor native modules."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "web" / "static" / "js" / "pipeline-config"


def _run_module(module_name: str, expression: str) -> object:
    """Evaluate an exported pure module with the repository Node runtime."""
    module_path = (MODULE_ROOT / module_name).as_posix()
    script = f"""
        const fs = require('node:fs');
        const source = fs.readFileSync({json.dumps(module_path)}, 'utf8');
        const url = 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
        import(url).then(async (module) => {{
            const result = await (async () => {{ {expression} }})();
            process.stdout.write(JSON.stringify(result));
        }}).catch((error) => {{ console.error(error); process.exit(1); }});
    """
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_pipeline_model_round_trips_enabled_and_disabled_steps() -> None:
    result = _run_module(
        "model.js",
        """
        const model = {
            steps: [
                {key: 'extract', module: 'standard_step.extraction.x', class: 'ExtractPdfTask', enabled: true},
                {key: 'review', module: 'standard_step.review.x', class: 'ReviewGateTask', enabled: false},
                {key: 'archive', module: 'standard_step.archiver.x', class: 'ArchivePdfTask', enabled: true},
            ],
        };
        const definition = module.modelToDefinition(model);
        return {definition, restored: module.definitionToModel(definition)};
        """,
    )

    assert result["definition"]["pipeline"] == ["extract", "archive"]
    assert set(result["definition"]["tasks"]) == {"extract", "review", "archive"}
    assert [step["key"] for step in result["restored"]["steps"]] == ["extract", "review", "archive"]
    assert result["restored"]["steps"][1]["enabled"] is False


def test_pipeline_model_filters_housekeeping_and_classifies_steps() -> None:
    result = _run_module(
        "model.js",
        """
        const model = {steps: [
            {key: 'cleanup', module: 'standard_step.housekeeping.cleanup', class: 'CleanupTask'},
            {key: 'review', module: 'standard_step.review.review_gate', class: 'ReviewGateTask'},
            {key: 'custom', module: 'custom_step.example', class: 'ExampleTask'},
        ]};
        return {
            keys: module.withoutHousekeeping(model).steps.map((step) => step.key),
            kinds: model.steps.map(module.taskKind),
            types: model.steps.map(module.stepType),
            summary: module.summaryText({steps: [{enabled: true}, {enabled: false}]}),
        };
        """,
    )

    assert result == {
        "keys": ["review", "custom"],
        "kinds": ["housekeeping", "review", "task"],
        "types": ["optional", "review", "optional"],
        "summary": "1/2 enabled",
    }


def test_pipeline_parameter_helpers_create_arrays_and_delete_nested_values() -> None:
    result = _run_module(
        "parameters.js",
        """
        const params = {};
        module.setParam(params, ['rules', 0, 'column'], 'invoice_id');
        const value = module.getParam(params, ['rules', 0, 'column'], null);
        module.deleteParam(params, ['rules', 0, 'column']);
        return {params, value, fallback: module.getParam(params, ['missing'], 'fallback')};
        """,
    )

    assert result == {
        "params": {"rules": [{}]},
        "value": "invoice_id",
        "fallback": "fallback",
    }


def test_pipeline_template_loads_feature_entry_as_a_native_module() -> None:
    template = (ROOT / "web/templates/pipeline_config.html").read_text(encoding="utf-8")
    entry = (MODULE_ROOT / "index.js").read_text(encoding="utf-8")

    assert 'type="module"' in template
    assert "/static/js/pipeline-config/index.js?v=controller-modularization-4" in template
    assert 'import "../pipeline_config.js?v=controller-modularization-4";' in entry


def test_pipeline_api_owns_encoded_routes_and_request_methods() -> None:
    result = _run_module(
        "api.js",
        """
        const calls = [];
        const docFlow = {
            apiGet: async (url) => { calls.push(['GET', url]); return {ok: true}; },
            apiPost: async (url, body) => { calls.push(['POST', url, body]); return {ok: true}; },
            apiPut: async (url, body) => { calls.push(['PUT', url, body]); return {ok: true}; },
            csrfHeaders: (method) => ({'X-CSRF-Test': method}),
        };
        const fetchCalls = [];
        const fakeFetch = async (url, options) => {
            fetchCalls.push([url, options]);
            return {ok: true, status: 200, json: async () => ({ok: true})};
        };
        const api = module.createPipelineApi(docFlow, fakeFetch);
        await api.getTemplate('template/a');
        await api.saveDraft('template/a', {expected_revision: 4});
        await api.publishDraft('template/a', 4);
        await api.updateTemplate('template/a', {name: 'Updated'});
        await api.importDraft('template/a', 4, {name: 'draft.yaml', text: async () => 'pipeline: []'});
        return {calls, fetchCalls, exportUrl: api.exportDraftUrl('template/a')};
        """,
    )

    assert result["calls"] == [
        ["GET", "/api/admin/pipeline-templates/template%2Fa"],
        ["PUT", "/api/admin/pipeline-templates/template%2Fa/draft", {"expected_revision": 4}],
        ["POST", "/api/admin/pipeline-templates/template%2Fa/publish", {"expected_revision": 4}],
    ]
    assert result["fetchCalls"][0][0] == "/api/admin/pipeline-templates/template%2Fa"
    assert result["fetchCalls"][0][1]["method"] == "PATCH"
    assert result["fetchCalls"][1][0].endswith("/draft/import?expected_revision=4")
    assert result["fetchCalls"][1][1]["method"] == "POST"
    assert result["exportUrl"].endswith("template%2Fa/draft/export?format=yaml")


def test_pipeline_controller_has_no_direct_transport_calls() -> None:
    controller = (ROOT / "web/static/js/pipeline_config.js").read_text(encoding="utf-8")

    assert "fetch(" not in controller
    assert "window.DocFlow.apiGet" not in controller
    assert "window.DocFlow.apiPost" not in controller
    assert "window.DocFlow.apiPut" not in controller


def test_pipeline_controller_delegates_task_rendering_and_resource_browsing() -> None:
    controller = (ROOT / "web/static/js/pipeline_config.js").read_text(encoding="utf-8")
    task_editors = (ROOT / "web/static/js/pipeline-config/task-editors.js").read_text(encoding="utf-8")
    resource_browser = (ROOT / "web/static/js/pipeline-config/resource-browser.js").read_text(encoding="utf-8")

    for function_name in (
        "splitControls",
        "extractControls",
        "glmOcrExtractControls",
        "storageControls",
        "reviewControls",
        "rulesControls",
        "directoryControl",
        "fileControl",
        "loadDirectoryBrowser",
        "loadCsvMetadata",
    ):
        assert f"function {function_name}(" not in controller

    for module_source in (task_editors, resource_browser):
        assert "window." not in module_source
        assert "document." not in module_source
        assert "fetch(" not in module_source


def test_pipeline_preview_redacts_nested_secrets_without_mutating_the_draft() -> None:
    result = _run_module(
        "preview.js",
        """
        const draft = {steps: [{
            key: 'extract', module: 'standard_step.extraction.x', class: 'ExtractPdfTask',
            enabled: true, params: {api_key: {$secret: 'live-alias'}, nested: {password: 'never-show', visible: 'yes'}},
        }]};
        const preview = module.buildPipelineYamlPreview(draft);
        return {preview, originalAlias: draft.steps[0].params.api_key.$secret};
        """,
    )

    assert "[REDACTED]" in result["preview"]
    assert "live-alias" not in result["preview"]
    assert "never-show" not in result["preview"]
    assert '"visible": "yes"' in result["preview"]
    assert result["originalAlias"] == "live-alias"


def test_pipeline_workspace_view_renders_lists_catalog_and_validation() -> None:
    result = _run_module(
        "workspace-view.js",
        """
        const element = () => ({textContent: '', innerHTML: '', disabled: false});
        const elements = Object.fromEntries([
            'activeList', 'draftList', 'activeSummary', 'draftSummary', 'validationSummary',
            'validationResults', 'addTaskSelect', 'publishButton', 'saveDraftButton',
            'validateButton', 'publishHelp',
        ].map((key) => [key, element()]));
        const helpers = {
            escapeHtml: (value) => String(value),
            badgeForStep: () => '<span>badge</span>',
            stepsOf: (model) => model.steps || [],
            summaryText: (model) => `${(model.steps || []).length}/${(model.steps || []).length} enabled`,
        };
        const view = module.createPipelineWorkspaceView(elements, helpers);
        view.render({
            active: {steps: []},
            draft: {steps: [{key: 'archive', label: 'Archive', enabled: true}]},
            selectedIndex: 0, revision: 3, baseVersionId: null, versions: [], dirty: false,
            paramsInvalid: false,
            catalog: [{id: 'archive-id', label: 'Archive', category: 'storage', import_status: 'ok', class_name: 'ArchivePdfTask', module: 'standard_step.archiver.x'}],
            validation: {findings: [{severity: 'error', code: 'invalid', path: 'pipeline', message: 'Fix it'}]},
        });
        return Object.fromEntries(Object.entries(elements).map(([key, value]) => [key, value]));
        """,
    )

    assert "Archive" in result["draftList"]["innerHTML"]
    assert "Draft r3" in result["draftSummary"]["textContent"]
    assert "archive-id" in result["addTaskSelect"]["innerHTML"]
    assert result["validationSummary"]["textContent"] == "1 blocking, 0 warnings"
    assert result["publishButton"]["disabled"] is True
    assert "Fix it" in result["validationResults"]["innerHTML"]


def test_pipeline_task_editors_render_every_supported_task_family() -> None:
    result = _run_module(
        "task-editors.js",
        """
        const state = {draft: {steps: []}, validation: null, schemaVersions: [], csvMetadata: {}, providerModes: {}, providerModeDrafts: {}};
        const taskKind = (step) => step.kind;
        const getParam = (params, path, fallback) => {
            let current = params || {};
            for (const key of path) {
                if (!current || typeof current !== 'object' || !(key in current)) return fallback;
                current = current[key];
            }
            return current === undefined ? fallback : current;
        };
        const editor = module.createPipelineTaskEditors({
            state,
            escapeHtml: (value) => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;'),
            pathAttr: (path) => JSON.stringify(path).replaceAll('"', '&quot;'),
            taskKind,
            stepsOf: (model) => model.steps || [],
            getParam,
            selectedTaskFindings: () => [],
            versionLabel: (version, kind) => `${kind} v${version.version_number || version.version || "?"}`,
        });
        const tasks = [
            {key: 'split', kind: 'split', class: 'LlamaCloudSplitTask', params: {}},
            {key: 'extract', kind: 'extract', class: 'ExtractPdfTask', params: {fields: {}}},
            {key: 'glm', kind: 'extract', class: 'GlmOcrExtractTask', params: {fields: {}}},
            {key: 'review', kind: 'review', class: 'ReviewGateTask', params: {}},
            {key: 'csv', kind: 'storage', class: 'StoreMetadataAsCsv', params: {}},
            {key: 'rules', kind: 'rules', class: 'UpdateReferenceTask', params: {}},
            {key: 'archive', kind: 'archive', class: 'ArchivePdfTask', params: {}},
            {key: 'context', kind: 'context', class: 'AssignNanoidTask', params: {}},
        ];
        state.draft.steps = tasks;
        return tasks.map((task) => editor.taskSpecificControls(task));
        """,
    )

    expected_markers = [
        "Split output directory",
        "Extraction fields",
        "Ollama host",
        "Confidence threshold",
        "Data output directory",
        "Reference CSV",
        "Archive directory",
        "Nanoid length",
    ]
    assert all(marker in html for marker, html in zip(expected_markers, result, strict=True))
    assert 'data-param-action="open-directory-browser"' in result[0]
    assert 'data-param-action="open-file-browser"' in result[5]


def test_pipeline_resource_browser_owns_directory_file_and_csv_behavior() -> None:
    result = _run_module(
        "resource-browser.js",
        """
        const state = {directoryBrowser: {mode: 'file', path: ['reference_file'], extensions: '.csv'}, csvMetadata: {}};
        const params = {};
        let renders = 0;
        let dirty = 0;
        const api = {
            listFiles: async (path, extensions) => ({current: path, entries: [{path: 'reference_file/data.csv'}], extensions}),
            listDirectories: async (path) => ({current: path, entries: []}),
            getCsvMetadata: async (path) => ({path, columns: ['id', 'status']}),
            createDirectory: async (path) => ({path}),
        };
        const getParam = (object, path, fallback) => path.reduce((value, key) => value && value[key], object) ?? fallback;
        const setParam = (object, path, value) => { object[path[0]] = value; };
        const browser = module.createPipelineResourceBrowser({
            state, api, render: () => { renders += 1; }, markDirty: () => { dirty += 1; },
            paramsForSelected: () => params, setParamsError: () => {}, getParam, setParam,
            showError: () => {}, getNewDirectoryName: () => 'qa-folder',
        });
        const safeAbsolute = browser.browserStartPath('C:/secret');
        await browser.loadDirectoryBrowser('reference_file');
        const listing = state.directoryBrowser.listing;
        browser.selectFile('reference_file/data.csv');
        await browser.loadCsvMetadata('reference_file/data.csv');
        return {safeAbsolute, listing, params, metadata: state.csvMetadata['reference_file/data.csv'], renders, dirty};
        """,
    )

    assert result["safeAbsolute"] == "."
    assert result["listing"]["current"] == "reference_file"
    assert result["params"]["reference_file"] == "reference_file/data.csv"
    assert result["metadata"]["columns"] == ["id", "status"]
    assert result["dirty"] == 1
    assert result["renders"] >= 3
