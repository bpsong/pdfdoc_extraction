"""Date/conditional semantics and strict, isolated approved-plugin contracts."""

from copy import deepcopy
from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import Any, Literal, cast

import pytest
from pydantic import ValidationError

from modules.services.business_validation import (
    BusinessRule, BusinessValidationConfig, Pointer, RequiredIfRule, ValidationCheck, evaluate_business_rules,
    make_validation_check, read_business_value,
)
from modules.services.business_validation_registry import (
    APPROVED_VALIDATORS, BusinessValidatorPlugin, ValidatorBinding, build_validator_registry,
)
from modules.services.business_validation_schema import validate_business_validation_schema


DATE = {'id': 'dates', 'validator': 'date_order:v1', 'earlier': '/issued', 'later': '/due', 'severity': 'blocking'}
CONDITIONAL = {'id': 'purchase_order', 'validator': 'required_if:v1', 'when': '/has_po', 'equals': True,
               'required': ['/po_number'], 'severity': 'blocking'}


def evaluate(values: dict[str, Any], *rules: dict[str, Any]) -> Any:
    return evaluate_business_rules(values, {'rules': rules})


@pytest.mark.parametrize('issued,due,equal,status', [
    ('2026-10-01', '2026-10-30', True, 'passed'), ('2026-10-30', '2026-10-01', True, 'failed'),
    ('2026-10-30', '2026-10-30', True, 'passed'), ('2026-10-30', '2026-10-30', False, 'failed'),
    ('2024-02-29', '2024-03-01', False, 'passed'), ('2025-02-29', '2025-03-01', True, 'not_evaluated'),
    ('20261001', '2026-10-30', True, 'not_evaluated'), ('2026-10-01T00:00:00Z', '2026-10-30', True, 'not_evaluated'),
    ('2026-10-01 ', '2026-10-30', True, 'not_evaluated'), (None, '2026-10-30', True, 'not_evaluated'),
    ('2026-10-01', 20261030, True, 'not_evaluated'), ('2026-10-01', True, True, 'not_evaluated'),
])
def test_date_order_uses_explicit_calendar_dates(issued: Any, due: Any, equal: bool, status: str) -> None:
    report = evaluate({'issued': issued, 'due': due}, {**DATE, 'allow_equal': equal})
    assert report.checks[0].status == status
    assert report.has_blocking_findings is (status != 'passed')
    assert report.checks[0].difference is None


@pytest.mark.parametrize('values,equals,status', [
    ({'has_po': True, 'po_number': 'PO-1'}, True, 'passed'),
    ({'has_po': True, 'po_number': ''}, True, 'failed'),
    ({'has_po': True, 'po_number': None}, True, 'failed'),
    ({'has_po': True, 'po_number': []}, True, 'failed'),
    ({'has_po': True, 'po_number': {}}, True, 'failed'),
    ({'has_po': True, 'po_number': False}, True, 'passed'),
    ({'has_po': True, 'po_number': 0}, True, 'passed'),
    ({'has_po': False}, True, 'skipped'), ({'has_po': 1}, True, 'skipped'),
    ({'has_po': False}, 0, 'skipped'), ({'has_po': 1.0}, 1, 'failed'),
    ({'has_po': '1'}, 1, 'skipped'), ({'has_po': None}, None, 'failed'),
    ({'has_po': ''}, '', 'failed'), ({}, None, 'not_evaluated'),
    ({'has_po': {}}, True, 'not_evaluated'), ({'has_po': float('nan')}, 1, 'not_evaluated'),
])
def test_conditional_presence_is_typed_and_missing_is_explicit(values: dict[str, Any], equals: Any, status: str) -> None:
    report = evaluate(values, {**CONDITIONAL, 'equals': equals})
    assert report.checks[0].status == status
    assert report.has_blocking_findings is (status not in {'passed', 'skipped'})
    if status == 'skipped':
        assert report.checks[0].code == 'condition_not_met'


def test_multiple_rules_stay_independent_and_config_round_trips() -> None:
    config = BusinessValidationConfig.model_validate({'rules': [DATE, CONDITIONAL]})
    restored = BusinessValidationConfig.model_validate_json(config.model_dump_json())
    values = {'issued': '2026-10-30', 'due': '2026-10-01', 'has_po': True}
    original = deepcopy(values)
    report = evaluate_business_rules(values, restored)
    assert [check.status for check in report.checks] == ['failed', 'failed']
    assert values == original
    assert isinstance(restored.rules[1], RequiredIfRule)
    assert restored.rules[1].equals is True


@pytest.mark.parametrize('rule', [
    {**DATE, 'allow_equal': 'false'}, {**DATE, 'tolerance': '.01'},
    {**CONDITIONAL, 'required': []}, {**CONDITIONAL, 'required': ['/x'] * 2},
    {**CONDITIONAL, 'required': [f'/x{i}' for i in range(21)]},
    {**CONDITIONAL, 'equals': []}, {**CONDITIONAL, 'equals': float('inf')},
    {**CONDITIONAL, 'equals': 'x' * 501}, {**CONDITIONAL, 'module': 'os'},
])
def test_extension_configuration_is_strict_and_bounded(rule: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        BusinessValidationConfig.model_validate({'rules': [rule]})


def extension_schema() -> dict[str, Any]:
    return {'fields': {'issued': {'type': 'date'}, 'due': {'type': 'date'}, 'has_po': {'type': 'boolean'},
                       'po_number': {'type': 'string'}}, 'business_validation': {'rules': [DATE, CONDITIONAL]}}


@pytest.mark.parametrize('change,path', [('date', 'earlier'), ('condition', 'when'), ('constant', 'equals'), ('required', 'required.0')])
def test_binding_validation_uses_plugin_metadata(change: str, path: str) -> None:
    schema = extension_schema()
    assert not validate_business_validation_schema(schema)
    if change == 'date': schema['fields']['issued']['type'] = 'string'
    elif change == 'condition': schema['fields']['has_po']['type'] = 'object'
    elif change == 'constant': schema['business_validation']['rules'][1] = {**CONDITIONAL, 'equals': 'true'}
    else: schema['business_validation']['rules'][1] = {**CONDITIONAL, 'required': ['/missing']}
    findings = validate_business_validation_schema(schema)
    assert any(finding['path'].endswith('.' + path) for finding in findings)


@pytest.mark.parametrize('alias', ['choices', 'enum'])
@pytest.mark.parametrize('options,constant,valid', [
    (['approved'], 'approved', True), (['approved'], 'rejected', False),
    ([{'label': 'Approved'}], 'Approved', True),
    ([{'label': 'Approved', 'value': 'approved'}], 'approved', True),
    ([{'label': 'Approved', 'value': 'approved'}], 'Approved', False),
    ([1], 1.0, True), ([1], True, False), ([True], 1, False),
    (['1'], 1, False), ([{'label': 'No', 'value': False}], False, True),
])
def test_conditional_enum_literals_follow_field_aliases_and_typed_values(
    alias: str, options: list[Any], constant: Any, valid: bool,
) -> None:
    schema = extension_schema()
    schema['fields']['has_po'] = {'type': 'enum', alias: options}
    schema['business_validation']['rules'][1]['equals'] = constant
    findings = validate_business_validation_schema(schema)
    assert (not findings) is valid
    if not valid:
        assert findings[0]['path'] == 'business_validation.rules.1.equals'


class SupplierRule(BusinessRule):
    validator: Literal['test.supplier:v1']
    field: Pointer


def supplier_check(values: Mapping[str, Any], rule: SupplierRule) -> list[ValidationCheck]:
    value = read_business_value(values, rule.field)
    return [make_validation_check(rule, 'passed' if value == 'ACME' else 'failed', 'supplier_match',
                                  'Check the supplier.', (rule.field,))]


PLUGIN = BusinessValidatorPlugin('test.supplier:v1', SupplierRule, supplier_check,
                                 (ValidatorBinding('field', types=frozenset({'string'})),))


def test_only_reviewed_registry_entries_can_execute_and_validate_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    rule = {'id': 'supplier', 'validator': PLUGIN.identifier, 'field': '/supplier', 'severity': 'blocking'}
    with pytest.raises(ValidationError):
        evaluate({'supplier': 'ACME'}, rule)
    approved = build_validator_registry((*APPROVED_VALIDATORS.values(), PLUGIN))
    with pytest.raises(TypeError):
        # Deliberately exercise an invalid write beyond the read-only contract.
        cast(Any, approved)['new'] = PLUGIN
    monkeypatch.setattr('modules.services.business_validation_registry.APPROVED_VALIDATORS', approved)
    assert evaluate({'supplier': 'ACME'}, rule).checks[0].status == 'passed'
    assert evaluate({'supplier': 'OTHER'}, rule).has_blocking_findings
    schema = {'fields': {'supplier': {'type': 'string'}}, 'business_validation': {'rules': [rule]}}
    assert not validate_business_validation_schema(schema)
    schema['fields']['supplier']['type'] = 'number'
    assert validate_business_validation_schema(schema)[0]['path'].endswith('.field')
    with pytest.raises(ValueError, match='duplicate'):
        build_validator_registry((PLUGIN, PLUGIN))


def test_new_validator_version_retains_the_old_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    class SupplierRuleV2(SupplierRule):
        validator: Literal['test.supplier:v2']

    def different(values: Mapping[str, Any], rule: SupplierRuleV2) -> list[ValidationCheck]:
        return [make_validation_check(rule, 'failed', 'supplier_match', 'Different approved policy.', (rule.field,))]

    newer = BusinessValidatorPlugin('test.supplier:v2', SupplierRuleV2, different, PLUGIN.bindings)
    registry = build_validator_registry((*APPROVED_VALIDATORS.values(), PLUGIN, newer))
    monkeypatch.setattr('modules.services.business_validation_registry.APPROVED_VALIDATORS', registry)
    report = evaluate({'supplier': 'ACME'}, {'id': 'old', 'validator': PLUGIN.identifier, 'field': '/supplier'},
                       {'id': 'new', 'validator': newer.identifier, 'field': '/supplier'})
    assert [check.status for check in report.checks] == ['passed', 'failed']
    assert [check.validator for check in report.checks] == ['test.supplier:v1', 'test.supplier:v2']


@pytest.mark.parametrize('behavior', ['exception', 'mutation', 'empty', 'wrong_identity', 'wrong_path', 'wrong_evidence', 'many'])
def test_plugin_failures_and_malformed_results_fail_closed_without_mutation(monkeypatch: pytest.MonkeyPatch, behavior: str) -> None:
    def broken(values: dict[str, Any], rule: SupplierRule) -> list[Any]:
        if behavior == 'exception': raise RuntimeError('DO_NOT_EXPOSE_CUSTOMER_VALUE')
        if behavior == 'mutation': values['supplier'] = 'ALTERED'
        result = supplier_check(values, rule)
        if behavior == 'empty': return []
        if behavior == 'wrong_identity': return [replace(result[0], rule_id='different')]
        if behavior == 'wrong_path': return [replace(result[0], field_paths=('not-a-pointer',))]
        if behavior == 'wrong_evidence': return [replace(result[0], actual={'bad': 'value'})]
        if behavior == 'many': return result * 1001
        return result
    plugins = dict(APPROVED_VALIDATORS)
    plugins[PLUGIN.identifier] = replace(PLUGIN, evaluate=broken)
    monkeypatch.setattr('modules.services.business_validation_registry.APPROVED_VALIDATORS', MappingProxyType(plugins))
    values = {'supplier': 'ACME', 'issued': '2026-10-01', 'due': '2026-10-02'}
    before = deepcopy(values)
    report = evaluate(values, {'id': 'supplier', 'validator': PLUGIN.identifier, 'field': '/supplier'}, DATE)
    assert [check.status for check in report.checks] == ['error', 'passed']
    assert report.has_blocking_findings
    assert 'DO_NOT_EXPOSE' not in str(report)
    assert values == before
