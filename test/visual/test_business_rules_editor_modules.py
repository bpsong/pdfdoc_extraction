"""Behavior and escaping checks for the business-rule authoring controls."""

import json

import pytest

from test.helpers_business_validation import invoice_review_schema
from test.visual.test_schema_editor_modules import _run_module


@pytest.mark.parametrize('alias', ['choices', 'enum'])
def test_conditional_enum_literals_match_supported_field_choices(alias: str) -> None:
    result = _run_module('business-rules.js', f'''
        const draft = {{fields:{{status:{{type:'enum', {alias}:[{{label:'Approved', value:'approved'}}]}},
            po_number:{{type:'string'}}}}}};
        const model = module.createBusinessRulesModel(()=>draft, catalog);
        model.add('required_if:v1'); model.update(0,'when','/status');
        model.update(0,'required',['/po_number']); model.update(0,'equals','rejected');
        const rejected = model.findings();
        model.update(0,'equals','approved');
        const valid = model.findings();
        draft.fields.status.{alias} = [{{label:'Approved'}}];
        model.update(0,'equals','Approved');
        const labelOnly = model.findings();
        draft.fields.status.{alias} = [1];
        model.update(0,'equals_kind','number'); model.update(0,'equals','1.0');
        const numeric = model.findings();
        model.update(0,'equals_kind','boolean'); model.update(0,'equals','true');
        return {{rejected, valid, labelOnly, numeric, wrongType:model.findings()}};
    ''')
    assert any(finding['path'].endswith('.equals') for finding in result['rejected'])
    assert result['valid'] == result['labelOnly'] == result['numeric'] == []
    assert any(finding['path'].endswith('.equals') for finding in result['wrongType'])


def test_rule_authoring_preserves_fields_and_unrelated_metadata() -> None:
    schema = invoice_review_schema()
    del schema["business_validation"]
    result = _run_module("business-rules.js", f"""
        const draft = {json.dumps(schema)};
        const original = JSON.stringify(draft.fields);
        draft.custom_note = 'keep this';
        const model = module.createBusinessRulesModel(() => draft, catalog);
        model.add('line_amount:v1'); model.update(0, 'collection', '/items');
        for (const [prop, value] of Object.entries({{quantity:'/quantity',unit_price:'/unit_price',line_total:'/line_total'}})) model.update(0, prop, value);
        model.add('sum_equals:v1'); model.update(1, 'collection', '/items');
        model.update(1, 'item_value', '/line_total');
        model.update(1, 'target', '/subtotal');
        model.update(1, 'severity', 'blocking');
        model.update(0, 'enabled', false);
        const findings = model.findings();
        model.move(1, -1);
        const fieldsWereUnchanged = original === JSON.stringify(draft.fields);
        draft.fields.items.items.properties.quantity.label = 'Changed quantity';
        const saved = JSON.parse(JSON.stringify(draft));
        const restored = module.createBusinessRulesModel(() => saved, catalog);
        return {{draft, findings, restored:restored.rules(), ids:model.rules().map(rule=>rule.id),
            fieldsWereUnchanged}};
    """)
    assert result["findings"] == []
    assert result["fieldsWereUnchanged"]
    assert result["ids"] == ["sum_equals_1", "line_amount_1"]
    assert result["draft"]["custom_note"] == "keep this"
    assert result["restored"][1]["enabled"] is False
    assert result["draft"]["fields"]["items"]["items"]["properties"]["quantity"]["label"] == "Changed quantity"


def test_broken_renamed_or_deleted_bindings_are_retained_and_flagged() -> None:
    result = _run_module("business-rules.js", f"""
        const draft = {json.dumps(invoice_review_schema())};
        const model = module.createBusinessRulesModel(() => draft, catalog);
        delete draft.fields.items.items.properties.quantity;
        draft.fields.subtotal.type = 'string';
        return {{findings:model.findings(), rules:model.rules()}};
    """)
    assert {finding["path"] for finding in result["findings"]} == {
        "business_validation.rules.0.quantity", "business_validation.rules.1.target",
    }
    assert result["rules"][0]["quantity"] == "/quantity"
    assert result["rules"][1]["target"] == "/subtotal"


def test_rule_deletion_type_switch_and_duplicate_ids() -> None:
    result = _run_module("business-rules.js", f"""
        const draft = {json.dumps(invoice_review_schema())};
        const model = module.createBusinessRulesModel(() => draft, catalog);
        model.update(0, 'id', 'subtotal');
        const duplicates = model.findings();
        model.update(0, 'validator', 'sum_equals:v1');
        const switched = structuredClone(model.rules()[0]);
        model.remove(1); model.remove(0);
        return {{duplicates, switched, sectionRemaining:Object.hasOwn(draft,'business_validation')}};
    """)
    assert any(finding["path"].endswith(".id") for finding in result["duplicates"])
    assert "quantity" not in result["switched"]
    assert result["switched"]["target"] == ""
    assert result["sectionRemaining"] is False


def test_no_rules_do_not_change_existing_forms_and_bad_sections_are_not_erased() -> None:
    result = _run_module("business-rules.js", """
        const legacy = {fields:{}};
        const model = module.createBusinessRulesModel(() => legacy, catalog);
        model.rules(); model.findings();
        const invalid = {fields:{},business_validation:{format_version:99,rules:[]}};
        const bad = module.createBusinessRulesModel(() => invalid, catalog);
        let rejected=false; try {bad.add('line_amount:v1');} catch(error) {rejected=true;}
        return {legacy,invalid,rejected,findings:bad.findings(),unknown:model.add('toString')};
    """)
    assert result["legacy"] == {"fields": {}}
    assert result["invalid"]["business_validation"]["format_version"] == 99
    assert result["rejected"] and result["findings"] and not result["unknown"]


def test_omitted_optional_defaults_match_backend_without_rewriting_on_load() -> None:
    result = _run_module("business-rules.js", """
        const draft={fields:{},business_validation:{}};
        const model=module.createBusinessRulesModel(()=>draft, catalog);
        const findings=model.findings();
        const before=JSON.stringify(draft);
        model.add('line_amount:v1');
        return {findings,before,after:draft.business_validation};
    """)
    assert result["findings"] == []
    assert json.loads(result["before"])["business_validation"] == {}
    assert result["after"]["format_version"] == 1
    assert len(result["after"]["rules"]) == 1


def test_date_and_conditional_rules_author_typed_values_and_survive_type_switches() -> None:
    result = _run_module('business-rules.js', '''
        const draft = {fields:{issued:{type:'date'},due:{type:'date'},has_po:{type:'boolean'},po_number:{type:'string'}}};
        const model = module.createBusinessRulesModel(()=>draft, catalog);
        model.add('date_order:v1');
        model.update(0,'earlier','/issued'); model.update(0,'later','/due');
        model.update(0,'allow_equal',false);
        model.add('required_if:v1'); model.update(1,'when','/has_po');
        model.update(1,'equals','true'); model.update(1,'required',['/po_number']);
        const findings = model.findings();
        const rules = structuredClone(model.rules());
        model.update(0,'validator','required_if:v1');
        const switched = structuredClone(model.rules()[0]);
        delete draft.fields.po_number;
        return {findings,rules,switched,broken:model.findings()};
    ''')
    assert result['findings'] == []
    assert result['rules'][0]['allow_equal'] is False
    assert result['rules'][1]['equals'] is True
    assert result['rules'][1]['required'] == ['/po_number']
    assert 'tolerance' not in result['rules'][0] and 'collection' not in result['rules'][1]
    assert 'earlier' not in result['switched'] and 'allow_equal' not in result['switched']
    assert any(finding['path'].endswith('.required.0') for finding in result['broken'])


def test_rule_controls_escape_imported_values_and_expose_actionable_errors() -> None:
    schema = invoice_review_schema()
    schema["business_validation"]["rules"][0]["id"] = '<img src=x onerror="bad()">'
    schema["business_validation"]["rules"][0]["quantity"] = "/missing"
    schema["business_validation"]["rules"][1]["validator"] = "toString"
    result = _run_module("business-rules.js", f"""
        global.document = {{activeElement:null}};
        const draft = {json.dumps(schema)};
        const model = module.createBusinessRulesModel(() => draft, catalog);
        const element={{contains:()=>false,innerHTML:''}};
        module.renderBusinessRules(element, model, model.findings(), false);
        return element.innerHTML;
    """)
    assert "<img" not in result
    assert "&lt;img" in result
    assert 'aria-invalid="true"' in result
    assert 'aria-describedby="business-error-0-quantity"' in result
    assert "Current binding: /missing" in result
    assert 'class="business-rule-card" disabled' in result


def test_nested_and_escaped_dropdown_paths_use_semantic_numeric_fields() -> None:
    result = _run_module("business-rules.js", """
        const draft={fields:{'a/b~':{type:'object',properties:{
            rows:{type:'array',items:{type:'object',properties:{
                'unit/price':{type:'number'},description:{type:'string'}}}},
            sum:{type:'number'}}}}};
        const model=module.createBusinessRulesModel(()=>draft, catalog);
        const rule={validator:'line_amount:v1',collection:'/a~1b~0/rows'};
        return {collections:model.choices(rule,'collection'), numbers:model.choices(rule,'unit_price'), target:model.choices({...rule,validator:'sum_equals:v1'},'target')};
    """)
    assert result["collections"][0]["value"] == "/a~1b~0/rows"
    assert result["numbers"] == [{"value": "/unit~1price", "label": "unit/price (/unit~1price)"}]
    assert result["target"][0]["value"] == "/a~1b~0/sum"
