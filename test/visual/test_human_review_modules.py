"""Behavior checks for human-review model and API boundaries."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "web/static/js/human-review"


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


def test_review_model_paths_edit_policy_and_corrections() -> None:
    result = _run_module(
        "model.js",
        """
        const state = {
            operator: 'admin', lock: {locked_by: 'admin'},
            reviewItem: {status: 'pending'},
            metadata: {editable_fields: ['invoice_amount', 'address']},
            schemaFields: [
                {key: 'invoice_amount', type: 'number'},
                {key: 'address', type: 'object', children: [
                    {key: 'city', type: 'string', readonly: true},
                    {key: 'zip', type: 'string'},
                ]},
            ],
            originalValues: {invoice_amount: 10, address: {city: 'Old', zip: '1'}},
            values: {invoice_amount: 12, address: {city: 'Old', zip: '2'}},
        };
        const model = module.createHumanReviewModel(state);
        const permissions = {
            amount: model.canEditPath(['invoice_amount']),
            city: model.canEditPath(['address', 'city']),
            zip: model.canEditPath(['address', 'zip']),
            other: model.canEditPath(['other']),
        };
        const corrections = model.collectCorrections();
        const root = {};
        model.setByPath(root, ['items', 0, 'quantity'], 3);
        state.lock = {locked_by: 'operator'};
        return {permissions, corrections, nested: model.getByPath(root, ['items', 0, 'quantity']),
            blockedCorrections: model.collectCorrections()};
        """,
    )
    assert result["permissions"] == {
        "amount": True, "city": False, "zip": True, "other": False,
    }
    assert result["corrections"] == {
        "invoice_amount": 12, "address": {"city": "Old", "zip": "2"},
    }
    assert result["nested"] == 3
    assert result["blockedCorrections"] == {}


def test_review_model_normalizes_values_and_source_visibility() -> None:
    result = _run_module(
        "model.js",
        """
        const state = {
            metadata: {draft: {corrections: {amount: 8}}, highlight_fields: []},
            sourceValueMode: 'review', sourceValueReveals: new Set(),
            schemaFields: [], fields: [], fieldsByKey: new Map(),
            originalValues: {}, values: {},
            reviewItem: {status: 'pending'},
        };
        const model = module.createHumanReviewModel(state);
        model.initializeValues({fields: [{field_key: 'amount', extracted_value_json: '5',
            final_value_json: '6', confidence: 0.95}], schema: {fields: []}});
        const initial = {original: state.originalValues.amount, draft: state.values.amount,
            visible: model.shouldShowSourceValue(['amount'], state.fields[0], 8, 5)};
        state.sourceValueMode = 'hidden';
        const hidden = model.shouldShowSourceValue(['amount'], state.fields[0], 8, 5);
        state.sourceValueMode = 'all';
        const all = model.shouldShowSourceValue(['amount'], state.fields[0], 8, 5);
        return {initial, hidden, all, normalizedMode: model.normalizeSourceValueMode('bad')};
        """,
    )
    assert result["initial"] == {"original": 6, "draft": 8, "visible": True}
    assert result["hidden"] is False
    assert result["all"] is True
    assert result["normalizedMode"] == "review"


def test_review_api_encodes_item_id_and_preserves_correction_payload() -> None:
    result = _run_module(
        "api.js",
        """
        const calls = [];
        const docFlow = {
            apiGet: async (url) => {calls.push({url, method: 'GET'}); return {};},
            apiPost: async (url, body) => {calls.push({url, method: 'POST', body}); return {};},
        };
        const api = module.createHumanReviewApi(docFlow, 'id/with space');
        await api.load();
        await api.claim();
        await api.saveDraft({amount: 12});
        await api.previewDiff({amount: 12});
        await api.release();
        await api.complete({amount: 12});
        return calls;
        """,
    )
    assert [call["method"] for call in result] == [
        "GET", "POST", "POST", "POST", "POST", "POST",
    ]
    assert all("id%2Fwith%20space" in call["url"] for call in result)
    assert result[2]["body"] == {"corrections": {"amount": 12}}
    assert result[3]["body"] == {"corrections": {"amount": 12}}
    assert result[5]["body"] == {"corrections": {"amount": 12}}


def test_review_entry_uses_matching_asset_version_and_no_controller_transport() -> None:
    template = (ROOT / "web/templates/human_review.html").read_text(encoding="utf-8")
    entry = (MODULE_ROOT / "index.js").read_text(encoding="utf-8")
    controller = (MODULE_ROOT / "controller.js").read_text(encoding="utf-8")
    model = (MODULE_ROOT / "model.js").read_text(encoding="utf-8")
    assert "human-review/index.js?v=controller-modularization-6a" in template
    assert 'import "./controller.js?v=controller-modularization-6a"' in entry
    assert controller.count("controller-modularization-6a") == 4
    assert "window.DocFlow.apiGet" not in controller
    assert "window.DocFlow.apiPost" not in controller
    assert "window." not in model
    assert "document." not in model
