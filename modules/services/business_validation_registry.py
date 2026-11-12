"""Explicit code-reviewed validator allowlist; never load modules from form data.

Keep old version entries when adding changed implementations. Extensions provide
a strict frozen configuration model, bounded pure evaluator, and schema bindings.
There is deliberately no runtime registration or administrator upload endpoint.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any, Literal, get_args

from modules.services.business_validation import (
    BusinessRule, CompareNumberRule, DateOrderRule, LineAmountRule, RequiredIfRule, SumEqualsRule,
    ValidationCheck, _evaluate_amount_rule, _evaluate_compare_number, _evaluate_date_order, _evaluate_required_if,
)
from modules.services.business_validation_metadata import (
    Condition, ValidatorControl, ValidatorEditor, model_has_path, validate_editor,
)


@dataclass(frozen=True)
class ValidatorBinding:
    """Declare a configuration field containing document or relative row pointers."""

    name: str
    scope: Literal['document', 'row'] = 'document'
    types: frozenset[str] | None = None
    many: bool = False
    when: Condition | None = None
    scope_field: str | None = None


@dataclass(frozen=True)
class BusinessValidatorPlugin:
    """One approved implementation, its exact configuration type, and bindings."""

    identifier: str
    configuration: type[BusinessRule]
    evaluate: Callable[[Mapping[str, Any], Any], list[ValidationCheck]]
    bindings: tuple[ValidatorBinding, ...]
    collection: str | None = None
    collection_when: Condition | None = None
    editor: ValidatorEditor | None = None


def build_validator_registry(plugins: Iterable[BusinessValidatorPlugin]) -> Mapping[str, BusinessValidatorPlugin]:
    """Reject ambiguous/unsafe descriptors before exposing an immutable registry."""
    result = {}
    for plugin in plugins:
        if (not re.fullmatch(r'[a-z][a-z0-9_.-]*:v[1-9][0-9]*', plugin.identifier)
                or len(plugin.identifier) > 128 or plugin.identifier in result
                or not issubclass(plugin.configuration, BusinessRule)
                or get_args(plugin.configuration.model_fields['validator'].annotation) != (plugin.identifier,)
                or plugin.configuration.model_config.get('extra') != 'forbid'
                or not plugin.configuration.model_config.get('frozen') or not callable(plugin.evaluate)):
            raise ValueError('Invalid or duplicate approved validator descriptor.')
        for binding in plugin.bindings:
            if (not model_has_path(plugin.configuration, binding.name)
                    or binding.scope not in {'document', 'row'}
                    or binding.scope == 'row' and not plugin.collection
                    or binding.scope_field is not None and not model_has_path(plugin.configuration, binding.scope_field)
                    or binding.when is not None and not model_has_path(plugin.configuration, binding.when[0])):
                raise ValueError('Invalid approved validator bindings.')
        if plugin.collection and plugin.collection not in plugin.configuration.model_fields:
            raise ValueError('Invalid approved validator collection.')
        if plugin.collection_when and (not plugin.collection
                or not model_has_path(plugin.configuration, plugin.collection_when[0])):
            raise ValueError('Invalid approved validator collection condition.')
        if plugin.editor is not None:
            validate_editor(plugin.configuration, plugin.editor)
            for control in plugin.editor.controls:
                if control.kind == 'collection' and control.name != plugin.collection:
                    raise ValueError('Invalid approved validator collection control.')
                if control.kind == 'field':
                    binding = next((item for item in plugin.bindings if item.name == control.name), None)
                    if (binding is None or control.scope != binding.scope
                            or control.types != binding.types or control.many != binding.many):
                        raise ValueError('Editor field conflicts with approved binding.')
                if control.kind == 'operand':
                    binding = next((item for item in plugin.bindings if item.name == f'{control.name}.field'), None)
                    if (binding is None or binding.scope_field != f'{control.name}.scope'
                            or binding.types != control.types or binding.many):
                        raise ValueError('Editor operand conflicts with approved binding.')
        result[plugin.identifier] = plugin
    return MappingProxyType(result)


NUMBERS = frozenset({'number', 'integer', 'float'})
SCALARS = frozenset({'string', 'number', 'integer', 'float', 'boolean', 'date', 'datetime', 'enum'})
AMOUNT_OPTIONS = (
    ValidatorControl('tolerance', 'Allowed difference', 'decimal', default='0.01', minimum=0),
    ValidatorControl('decimal_places', 'Decimal places', 'integer', default=2, minimum=0, maximum=8),
    ValidatorControl('rounding', 'Rounding', 'choice', default='ROUND_HALF_UP',
                     choices=(('ROUND_HALF_UP', 'Half up'), ('ROUND_HALF_EVEN', 'Half even'))),
)
APPROVED_VALIDATORS = build_validator_registry((
    BusinessValidatorPlugin('line_amount:v1', LineAmountRule, _evaluate_amount_rule, tuple(
        ValidatorBinding(name, 'row', NUMBERS) for name in ('quantity', 'unit_price', 'line_total')
    ), 'collection', editor=ValidatorEditor(
        'Multiply two row fields',
        'Check that two numeric values multiplied together match the recorded result. Choose compatible units.',
        'Calculations', (
            ValidatorControl('collection', 'Repeating group', 'collection'),
            ValidatorControl('quantity', 'First value field', 'field', scope='row', types=NUMBERS),
            ValidatorControl('unit_price', 'Second value field', 'field', scope='row', types=NUMBERS),
            ValidatorControl('line_total', 'Result field', 'field', scope='row', types=NUMBERS),
            *AMOUNT_OPTIONS,
        ),
    )),
    BusinessValidatorPlugin('sum_equals:v1', SumEqualsRule, _evaluate_amount_rule, (
        ValidatorBinding('item_value', 'row', NUMBERS), ValidatorBinding('target', types=NUMBERS),
    ), 'collection', editor=ValidatorEditor(
        'Sum rows against a field',
        'Compare the sum of entered row values with a document field. Choose values with consistent units.',
        'Calculations', (
            ValidatorControl('collection', 'Repeating group', 'collection'),
            ValidatorControl('item_value', 'Value to sum', 'field', scope='row', types=NUMBERS),
            ValidatorControl('target', 'Target field', 'field', types=NUMBERS),
            *AMOUNT_OPTIONS,
        ),
    )),
    BusinessValidatorPlugin('date_order:v1', DateOrderRule, _evaluate_date_order, (
        ValidatorBinding('earlier', types=frozenset({'date'})), ValidatorBinding('later', types=frozenset({'date'})),
    ), editor=ValidatorEditor('Date order', 'Check that an earlier calendar date is on or before a later date.',
                             'Dates', (
        ValidatorControl('earlier', 'Earlier date field', 'field', types=frozenset({'date'})),
        ValidatorControl('later', 'Later date field', 'field', types=frozenset({'date'})),
        ValidatorControl('allow_equal', 'Allow same day', 'boolean', default=True),
    ))),
    BusinessValidatorPlugin('required_if:v1', RequiredIfRule, _evaluate_required_if, (
        ValidatorBinding('when', types=SCALARS), ValidatorBinding('required', many=True),
    ), editor=ValidatorEditor('Require fields when a condition matches',
                             'Require selected fields when a typed condition matches. Missing conditions cannot be evaluated.',
                             'Requirements', (
        ValidatorControl('when', 'Condition field', 'field', types=SCALARS),
        ValidatorControl('equals', 'Equals value', 'typed', default='', condition_field='when'),
        ValidatorControl('required', 'Required fields', 'field', many=True),
    ))),
    BusinessValidatorPlugin('compare_number:v1', CompareNumberRule, _evaluate_compare_number, (
        ValidatorBinding('left.field', types=NUMBERS, scope_field='left.scope'),
        ValidatorBinding('right.field', types=NUMBERS, scope_field='right.scope', when=('right.kind', ('field',))),
    ), 'collection', collection_when=('scope', ('rows',)), editor=ValidatorEditor(
        'Compare numbers', 'Compare a numeric field with another field or a constant, without implicit rounding.',
        'Comparisons', (
            ValidatorControl('scope', 'Apply to', 'choice', default='document',
                             choices=(('document', 'Document'), ('rows', 'Each repeating row'))),
            ValidatorControl('collection', 'Repeating group', 'collection', visible_when=(('scope', ('rows',)),)),
            ValidatorControl('left', 'Left value', 'operand', types=NUMBERS),
            ValidatorControl('operator', 'Operator', 'choice', default='lte', choices=(
                ('eq', 'Equal to (=)'), ('ne', 'Not equal to (≠)'), ('lt', 'Less than (<)'),
                ('lte', 'Less than or equal to (≤)'), ('gt', 'Greater than (>)'), ('gte', 'Greater than or equal to (≥)'),
            )),
            ValidatorControl('right', 'Compare with', 'operand', types=NUMBERS, allow_constant=True),
            ValidatorControl('tolerance', 'Allowed difference', 'decimal', default='0', minimum=0,
                             visible_when=(('operator', ('eq', 'ne')),)),
        ),
    )),
))


def get_validator(identifier: str) -> BusinessValidatorPlugin | None:
    """Resolve only exact identifiers from this release's approved code list."""
    return APPROVED_VALIDATORS.get(identifier)
