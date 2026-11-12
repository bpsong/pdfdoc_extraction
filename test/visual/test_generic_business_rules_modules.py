"""Reusable widgets support catalog plugins, comparisons, and unavailable catalogs."""

import json
from pathlib import Path
from typing import Any, Literal, Mapping

import pytest

from modules.services.business_validation import (
    BusinessRule, Pointer, ValidationCheck, evaluate_business_rules, make_validation_check,
)
from modules.services.business_validation_metadata import ValidatorControl, ValidatorEditor
from modules.services.business_validation_registry import (
    APPROVED_VALIDATORS, BusinessValidatorPlugin, ValidatorBinding, build_validator_registry,
)
from test.visual.test_schema_editor_modules import _run_module


def test_comparison_controls_keep_scope_and_constant_payloads_strict() -> None:
    result = _run_module('business-rules.js', '''
        const draft={fields:{limit:{type:'number'},lines:{type:'array',items:{type:'object',properties:{
            delivered:{type:'number'},ordered:{type:'number'},note:{type:'string'}}}}}};
        const model=module.createBusinessRulesModel(()=>draft,catalog);
        model.add('compare_number:v1');
        model.update(0,'scope','rows'); model.update(0,'collection','/lines');
        model.update(0,'left.field','/delivered'); model.update(0,'right.field','/ordered');
        const valid=model.findings(); const row=structuredClone(model.rules()[0]);
        model.update(0,'right.scope','document'); model.update(0,'right.field','/limit');
        const document=model.findings();
        model.update(0,'right.kind','constant'); model.update(0,'right.value','2.50');
        model.update(0,'operator','eq'); model.update(0,'tolerance','0.01');
        const equal=structuredClone(model.rules()[0]); const equalFindings=model.findings();
        model.update(0,'operator','lte');
        const ordered=structuredClone(model.rules()[0]);
        model.update(0,'scope','document'); model.update(0,'left.field','/limit');
        return {valid,row,document,equal,equalFindings,ordered,final:model.rules()[0],findings:model.findings()};
    ''')
    assert result['valid'] == result['document'] == result['equalFindings'] == result['findings'] == []
    assert result['row']['left']['scope'] == result['row']['right']['scope'] == 'row'
    assert result['equal']['right'] == {'kind': 'constant', 'value': '2.50'}
    assert result['equal']['tolerance'] == '0.01'
    assert 'tolerance' not in result['ordered'] and 'collection' not in result['final']


def test_loading_and_retrying_catalog_does_not_rewrite_draft_or_choose_a_group() -> None:
    result = _run_module('business-rules.js', '''
        const draft={fields:{a:{type:'array',items:{type:'object',properties:{n:{type:'number'}}}},
            b:{type:'array',items:{type:'object',properties:{n:{type:'number'}}}}},
            business_validation:{rules:[{id:'existing',validator:'line_amount:v1',collection:'/a',quantity:'/n',unit_price:'/n',line_total:'/n'}]}};
        const original=JSON.stringify(draft);
        const model=module.createBusinessRulesModel(()=>draft);
        const cannotAdd=model.add('line_amount:v1');
        model.update(0,'quantity','/changed'); model.findings();
        const offline=JSON.stringify(draft);
        model.setCatalog(catalog); model.findings();
        const restored=JSON.stringify(draft);
        model.setCatalog(catalog); model.add('line_amount:v1');
        return {original,offline,restored,cannotAdd,collection:model.rules()[1].collection};
    ''')
    assert result['original'] == result['offline'] == result['restored']
    assert result['cannotAdd'] is False and result['collection'] == ''


def test_imported_comparison_mismatches_are_located_without_discarding_values() -> None:
    result = _run_module('business-rules.js', '''
        const draft={fields:{n:{type:'number'}},business_validation:{rules:[{
            id:'cmp',validator:'compare_number:v1',scope:'document',operator:'lt',tolerance:'1',
            left:{kind:'field',scope:'row',field:'/missing'},right:{kind:'constant',value:'NaN'}}]}};
        const before=JSON.stringify(draft);
        const model=module.createBusinessRulesModel(()=>draft,catalog);
        return {before,after:JSON.stringify(draft),findings:model.findings()};
    ''')
    assert result['before'] == result['after']
    assert {item['path'] for item in result['findings']} >= {
        'business_validation.rules.0.left.scope', 'business_validation.rules.0.left.field',
        'business_validation.rules.0.right.value', 'business_validation.rules.0.tolerance',
    }


def test_omitted_operand_scope_uses_document_default_without_rewriting() -> None:
    result = _run_module('business-rules.js', '''
        const draft={fields:{n:{type:'number'}},business_validation:{rules:[{
            id:'cmp',validator:'compare_number:v1',operator:'lte',
            left:{kind:'field',field:'/n'},right:{kind:'field',field:'/n'}}]}};
        const before=JSON.stringify(draft);
        const model=module.createBusinessRulesModel(()=>draft,catalog);
        global.document={activeElement:null};const container={contains:()=>false,innerHTML:''};
        module.renderBusinessRules(container,model,model.findings(),true);
        return {before,after:JSON.stringify(draft),findings:model.findings(),html:container.innerHTML};
    ''')
    assert result['before'] == result['after'] and result['findings'] == []
    assert 'value="document" selected' in result['html']
    report = evaluate_business_rules({'n': 3}, {'rules': [{
        'id': 'cmp', 'validator': 'compare_number:v1', 'operator': 'lte',
        'left': {'kind': 'field', 'field': '/n'}, 'right': {'kind': 'field', 'field': '/n'},
    }]})
    assert report.checks[0].status == 'passed'


@pytest.mark.parametrize('malformed', ['broken', None, 2, []])
def test_explicit_field_selection_can_repair_malformed_imported_operand(malformed: Any) -> None:
    result = _run_module('business-rules.js', f'''
        const draft={{fields:{{n:{{type:'number'}}}},business_validation:{{rules:[{{
            id:'cmp',validator:'compare_number:v1',operator:'lte',left:{json.dumps(malformed)},
            right:{{kind:'constant',value:'3'}}}}]}}}};
        const before=JSON.stringify(draft);
        const model=module.createBusinessRulesModel(()=>draft,catalog);
        const findings=model.findings(); const after=JSON.stringify(draft);
        model.update(0,'left.field','/n');
        return {{before,after,findings,repaired:model.rules()[0].left,remaining:model.findings()}};
    ''')
    assert result['before'] == result['after'] and result['findings']
    assert result['repaired'] == {'kind': 'field', 'scope': 'document', 'field': '/n'}
    assert result['remaining'] == []


def test_new_reviewed_plugin_appears_without_frontend_validator_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    class PrefixRule(BusinessRule):
        validator: Literal['test.prefix:v1']
        field: Pointer
        prefix: str = 'AC'
        mode: Literal[1, False] = 1

    def evaluate(values: Mapping[str, Any], rule: PrefixRule) -> list[ValidationCheck]:
        return [make_validation_check(rule, 'passed' if values['supplier'].startswith(rule.prefix) else 'failed',
                                      'prefix_checked', 'Check the prefix.', (rule.field,))]

    types = frozenset({'string'})
    plugin = BusinessValidatorPlugin('test.prefix:v1', PrefixRule, evaluate,
        (ValidatorBinding('field', types=types),), editor=ValidatorEditor(
            'Supplier prefix', '<img src=x onerror=bad()>', 'Requirements', (
                ValidatorControl('field', 'Supplier field', 'field', types=types),
                ValidatorControl('prefix', 'Starts with', 'text', default='AC', max_length=20),
                ValidatorControl('mode', 'Mode', 'choice', default=1, choices=((1, 'One'), (False, 'False'))),
            )))
    registry = build_validator_registry((*APPROVED_VALIDATORS.values(), plugin))
    monkeypatch.setattr('modules.services.business_validation_registry.APPROVED_VALIDATORS', registry)
    result = _run_module('business-rules.js', '''
        global.document={activeElement:null};
        const draft={fields:{supplier:{type:'string'}}};
        const model=module.createBusinessRulesModel(()=>draft,catalog);
        model.add('test.prefix:v1'); model.update(0,'field','/supplier');
        model.update(0,'mode','false');
        const element={contains:()=>false,innerHTML:''};
        module.renderBusinessRules(element,model,model.findings(),true);
        const picker={innerHTML:''};module.renderBusinessRulePicker(picker,model,'prefix');
        return {draft,findings:model.findings(),html:element.innerHTML,picker:picker.innerHTML};
    ''')
    assert result['findings'] == [] and result['draft']['business_validation']['rules'][0]['prefix'] == 'AC'
    assert result['draft']['business_validation']['rules'][0]['mode'] is False
    assert 'Supplier field' in result['html'] and 'Starts with' in result['html']
    assert '<img' not in result['html'] + result['picker'] and '&lt;img' in result['picker']
    assert evaluate_business_rules({'supplier': 'ACME'}, result['draft']['business_validation']).checks[0].status == 'passed'
    source = (Path(__file__).resolve().parents[2] / 'web/static/js/schema-editor/business-rules.js').read_text(encoding='utf-8')
    assert all(identifier not in source for identifier in APPROVED_VALIDATORS)
