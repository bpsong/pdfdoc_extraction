"""Behavior checks for the production review-form editor modules."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "web/static/js/schema-editor"


def _run_module(module_name: str, expression: str) -> object:
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
        ["node", "-e", script], cwd=ROOT, check=True,
        capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def test_schema_model_handles_nested_fields_rename_reorder_and_remove() -> None:
    result = _run_module(
        "model.js",
        """
        const draft = module.emptySchema();
        const model = module.createSchemaModel(() => draft);
        const outer = model.addField([], 'object');
        const first = model.addField([outer], 'string');
        const second = model.addField([outer], 'integer');
        const path = outer + '.' + first;
        const duplicate = model.updateField(path, 'key', second);
        const renamed = model.updateField(path, 'key', 'invoice_number');
        const moved = model.moveField(outer + '.' + second, 'up');
        const removed = model.removeField(outer + '.invoice_number');
        return {
            duplicate, renamed, moved, removed,
            keys: Object.keys(draft.fields[outer].properties),
            findings: model.collectClientFindings('qa-form', 'QA Form'),
        };
        """,
    )
    assert result["duplicate"]["ok"] is False
    assert result["renamed"]["renamedPath"].endswith(".invoice_number")
    assert result["moved"]["ok"] is True
    assert result["removed"]["ok"] is True
    assert result["keys"] == ["new_field_2"]
    assert result["findings"] == []


def test_schema_model_coerces_scalar_properties_and_finds_nested_conflicts() -> None:
    result = _run_module(
        "model.js",
        """
        const draft = module.emptySchema();
        const model = module.createSchemaModel(() => draft);
        const arrayKey = model.addField([], 'array');
        model.updateField(arrayKey, 'array_item_type', 'object');
        const childKey = model.addField([arrayKey], 'number');
        const childPath = arrayKey + '.' + childKey;
        model.updateField(childPath, 'min_value', '10');
        model.updateField(childPath, 'max_value', '2');
        model.updateField(childPath, 'default', '4.5');
        model.updateField(childPath, 'required', true);
        const invalid = model.collectClientFindings('qa-form', 'QA Form');
        model.updateField(childPath, 'max_value', '12');
        const valid = model.collectClientFindings('qa-form', 'QA Form');
        return {child: draft.fields[arrayKey].items.properties[childKey], invalid, valid};
        """,
    )
    assert result["child"]["default"] == 4.5
    assert result["child"]["required"] is True
    assert result["invalid"] == [{
        "path": "new_field.new_field.min_value",
        "message": "Min value cannot be greater than max value.",
    }]
    assert result["valid"] == []


def test_schema_api_preserves_revision_csrf_and_same_origin() -> None:
    result = _run_module(
        "api.js",
        """
        const requests = [];
        const docFlow = {
            csrfHeaders: (method) => ({'X-CSRF-Token': method}),
            apiGet: async (path) => ({path}),
            apiPost: async (path, body) => ({path, body}),
            apiPut: async (path, body) => ({path, body}),
        };
        const fetchImpl = async (url, options) => {
            requests.push({url, method: options.method, credentials: options.credentials,
                csrf: options.headers['X-CSRF-Token'], body: options.body});
            return {ok: true, json: async () => ({ok: true})};
        };
        const api = module.createSchemaEditorApi(docFlow, fetchImpl);
        const draft = await api.saveDraft('a/b', 3, {title: 'QA'});
        await api.updateTemplate('a/b', {status: 'inactive'});
        await api.importDraft('a/b', 4, {name: 'qa.yaml', text: async () => 'title: QA'});
        return {draft, requests, exportUrl: api.exportDraftUrl('a/b')};
        """,
    )
    assert result["draft"]["body"]["expected_revision"] == 3
    assert result["draft"]["path"].endswith("a%2Fb/draft")
    assert [request["method"] for request in result["requests"]] == ["PATCH", "POST"]
    assert all(request["credentials"] == "same-origin" for request in result["requests"])
    assert result["requests"][1]["csrf"] == "POST"
    assert "expected_revision=4" in result["requests"][1]["url"]
    assert result["exportUrl"].endswith("a%2Fb/draft/export?format=yaml")


def test_schema_entry_loads_all_modules_with_matching_asset_version() -> None:
    template = (ROOT / "web/templates/schema_editor.html").read_text(encoding="utf-8")
    entry = (MODULE_ROOT / "index.js").read_text(encoding="utf-8")
    controller = (ROOT / "web/static/js/schema-editor/controller.js").read_text(encoding="utf-8")
    assert "/static/js/schema-editor/index.js?v=controller-modularization-5d" in template
    assert 'import "./controller.js?v=controller-modularization-5d"' in entry
    assert controller.count("controller-modularization-5d") == 3
    assert "fetch(" not in controller
    assert "window.DocFlow.apiGet(" not in controller
    assert "window.DocFlow.apiPost(" not in controller
    assert "window.DocFlow.apiPut(" not in controller
