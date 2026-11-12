"""Document-neutral comparisons retain strict numbers, scope, and release policy."""

from copy import deepcopy
from typing import Any

from pydantic import ValidationError
import pytest

from modules.services.business_validation import BusinessValidationConfig, evaluate_business_rules
from modules.services.business_validation_schema import validate_business_validation_schema


def rule(**changes: Any) -> dict[str, Any]:
    return {'id': 'quantity_limit', 'validator': 'compare_number:v1', 'severity': 'blocking',
            'left': {'kind': 'field', 'scope': 'document', 'field': '/delivered'},
            'operator': 'lte', 'right': {'kind': 'field', 'scope': 'document', 'field': '/ordered'}, **changes}


@pytest.mark.parametrize('operator,left,right,passed', [
    ('eq', '0.1', '.10', True), ('eq', 3, 4, False), ('ne', 3, 4, True), ('ne', 3, 3, False),
    ('lt', 2, 3, True), ('lt', 3, 3, False), ('lte', 3, 3, True), ('lte', 4, 3, False),
    ('gt', 4, 3, True), ('gt', 3, 3, False), ('gte', 3, 3, True), ('gte', 2, 3, False),
    ('gt', '0.1000001', '0.1', True), ('lt', '-2', '-1', True),
])
def test_numeric_operators_are_exact(operator: str, left: Any, right: Any, passed: bool) -> None:
    values = {'delivered': left, 'ordered': right}
    before = deepcopy(values)
    report = evaluate_business_rules(values, {'rules': [rule(operator=operator)]})
    check = report.checks[0]
    assert check.status == ('passed' if passed else 'failed')
    assert report.has_blocking_findings is not passed
    assert check.field_paths == ('/delivered', '/ordered')
    assert values == before


@pytest.mark.parametrize('operator,expected', [('eq', 'passed'), ('ne', 'failed')])
def test_equality_tolerance_is_inclusive(operator: str, expected: str) -> None:
    report = evaluate_business_rules({'delivered': '1.01'}, {'rules': [rule(
        operator=operator, right={'kind': 'constant', 'value': '1'}, tolerance='0.01',
    )]})
    assert report.checks[0].status == expected
    assert report.checks[0].field_paths == ('/delivered',)


@pytest.mark.parametrize('bad', [None, True, False, '', 'NaN', 'Infinity', [], {}, '1e100', '1,000'])
def test_invalid_values_never_pass(bad: Any) -> None:
    report = evaluate_business_rules({'delivered': bad, 'ordered': 5}, {'rules': [rule()]})
    assert report.checks[0].status == 'not_evaluated'
    assert report.has_blocking_findings


@pytest.mark.parametrize('changes', [
    {'tolerance': '0'}, {'tolerance': None}, {'scope': 'rows'}, {'collection': '/lines'}, {'collection': None},
    {'left': {'kind': 'field', 'scope': 'row', 'field': '/delivered'}},
    {'right': {'kind': 'constant', 'value': True}},
    {'right': {'kind': 'constant', 'value': 'NaN'}},
    {'right': {'kind': 'constant', 'value': '1', 'field': '/ordered'}},
    {'operator': 'eq', 'tolerance': '-0.1'}, {'operator': 'eq', 'tolerance': None},
])
def test_invalid_configuration_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        BusinessValidationConfig.model_validate({'rules': [rule(**changes)]})


def test_rows_are_independent_and_can_compare_document_fields() -> None:
    configuration = {'rules': [rule(scope='rows', collection='/packages',
        left={'kind': 'field', 'scope': 'row', 'field': '/weight'},
        right={'kind': 'field', 'scope': 'document', 'field': '/limit'})]}
    report = evaluate_business_rules({'packages': [{'weight': 2}, {}, {'weight': 5}], 'limit': 3}, configuration)
    assert [check.status for check in report.checks] == ['passed', 'not_evaluated', 'failed']
    assert [check.row_index for check in report.checks] == [0, 1, 2]
    assert report.checks[2].field_paths == ('/packages/2/weight', '/limit')
    assert report.checks[1].field_paths == ('/packages/1/weight',)


@pytest.mark.parametrize('rows,code', [([], 'empty_collection'), ({}, 'invalid_collection'), ([{}] * 1001, 'row_limit')])
def test_row_limits_and_absence_remain_fail_closed(rows: Any, code: str) -> None:
    report = evaluate_business_rules({'packages': rows, 'ordered': 3}, {'rules': [rule(
        scope='rows', collection='/packages', left={'kind': 'field', 'scope': 'row', 'field': '/weight'},
    )]})
    assert report.checks[0].code == code
    assert report.has_blocking_findings


def test_binding_validation_checks_nested_operands_in_each_scope() -> None:
    schema = {'fields': {'packages': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'weight': {'type': 'number'}, 'description': {'type': 'string'},
    }}}, 'limit': {'type': 'number'}}, 'business_validation': {'rules': [rule(
        scope='rows', collection='/packages', left={'kind': 'field', 'scope': 'row', 'field': '/weight'},
        right={'kind': 'field', 'scope': 'document', 'field': '/limit'},
    )]}}
    original = deepcopy(schema)
    assert not validate_business_validation_schema(schema)
    assert schema == original
    schema['business_validation']['rules'][0]['left']['field'] = '/description'
    assert validate_business_validation_schema(schema)[0]['path'] == 'business_validation.rules.0.left.field'
    schema['business_validation']['rules'][0]['left']['field'] = '/weight'
    schema['business_validation']['rules'][0]['right'] = {'kind': 'constant', 'value': '4.25'}
    assert not validate_business_validation_schema(schema)


def test_parsed_rule_models_keep_absent_ordering_tolerance() -> None:
    config = BusinessValidationConfig.model_validate({'rules': [rule()]})
    rebuilt = BusinessValidationConfig.model_validate({'rules': config.rules})
    assert evaluate_business_rules({'delivered': 2, 'ordered': 3}, rebuilt).checks[0].status == 'passed'


@pytest.mark.parametrize('operand,path', [
    ({'kind': 'constant', 'value': 'NaN'}, 'right.value'),
    ({'kind': 'field', 'field': 'bad-pointer'}, 'right.field'),
    ({'kind': 'field', 'field': '/ordered', 'scope': 'invalid'}, 'right.scope'),
])
def test_nested_operand_errors_address_real_controls(operand: dict[str, Any], path: str) -> None:
    schema = {'fields': {}, 'business_validation': {'rules': [rule(right=operand)]}}
    before = deepcopy(schema)
    findings = validate_business_validation_schema(schema)
    assert findings[0]['path'] == f'business_validation.rules.0.{path}'
    assert schema == before
