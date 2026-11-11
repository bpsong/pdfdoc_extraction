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
    BusinessRule, DateOrderRule, LineAmountRule, RequiredIfRule, SumEqualsRule,
    ValidationCheck, _evaluate_amount_rule, _evaluate_date_order, _evaluate_required_if,
)


@dataclass(frozen=True)
class ValidatorBinding:
    """Declare a configuration field containing document or relative row pointers."""

    name: str
    scope: Literal['document', 'row'] = 'document'
    types: frozenset[str] | None = None
    many: bool = False


@dataclass(frozen=True)
class BusinessValidatorPlugin:
    """One approved implementation, its exact configuration type, and bindings."""

    identifier: str
    configuration: type[BusinessRule]
    evaluate: Callable[[Mapping[str, Any], Any], list[ValidationCheck]]
    bindings: tuple[ValidatorBinding, ...]
    collection: str | None = None


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
            if (binding.name not in plugin.configuration.model_fields
                    or binding.scope not in {'document', 'row'}
                    or binding.scope == 'row' and not plugin.collection):
                raise ValueError('Invalid approved validator bindings.')
        if plugin.collection and plugin.collection not in plugin.configuration.model_fields:
            raise ValueError('Invalid approved validator collection.')
        result[plugin.identifier] = plugin
    return MappingProxyType(result)


NUMBERS = frozenset({'number', 'integer', 'float'})
SCALARS = frozenset({'string', 'number', 'integer', 'float', 'boolean', 'date', 'datetime', 'enum'})
APPROVED_VALIDATORS = build_validator_registry((
    BusinessValidatorPlugin('line_amount:v1', LineAmountRule, _evaluate_amount_rule, tuple(
        ValidatorBinding(name, 'row', NUMBERS) for name in ('quantity', 'unit_price', 'line_total')
    ), 'collection'),
    BusinessValidatorPlugin('sum_equals:v1', SumEqualsRule, _evaluate_amount_rule, (
        ValidatorBinding('item_value', 'row', NUMBERS), ValidatorBinding('target', types=NUMBERS),
    ), 'collection'),
    BusinessValidatorPlugin('date_order:v1', DateOrderRule, _evaluate_date_order, (
        ValidatorBinding('earlier', types=frozenset({'date'})), ValidatorBinding('later', types=frozenset({'date'})),
    )),
    BusinessValidatorPlugin('required_if:v1', RequiredIfRule, _evaluate_required_if, (
        ValidatorBinding('when', types=SCALARS), ValidatorBinding('required', many=True),
    )),
))


def get_validator(identifier: str) -> BusinessValidatorPlugin | None:
    """Resolve only exact identifiers from this release's approved code list."""
    return APPROVED_VALIDATORS.get(identifier)
