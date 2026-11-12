"""Approved catalog metadata is complete, consistent, and safe to serialize."""

from dataclasses import replace
import json

import pytest

from modules.services.business_validation_catalog_service import business_validator_catalog, business_validator_labels
from modules.services.business_validation_metadata import ValidatorControl, ValidatorEditor
from modules.services.business_validation_registry import APPROVED_VALIDATORS, build_validator_registry


def test_catalog_is_neutral_serializable_and_detached_from_configuration() -> None:
    first = business_validator_catalog()
    assert first['catalog_version'] == 1
    assert len(first['validators']) == 5
    text = json.dumps(first)
    assert 'Invoice subtotal' not in text and 'standard_step' not in text
    assert set(business_validator_labels()) == set(APPROVED_VALIDATORS)
    first['validators'][0]['controls'][0]['label'] = 'changed'
    assert business_validator_catalog()['validators'][0]['controls'][0]['label'] == 'Repeating group'


@pytest.mark.parametrize('control', [
    ValidatorControl('nonexistent', 'Bad', 'text'),
    ValidatorControl('quantity', 'Bad', 'field', types=frozenset({'string'})),
    ValidatorControl('rounding', 'Bad', 'choice', default='wrong', choices=(('ROUND_HALF_UP', 'Half up'),)),
    ValidatorControl('quantity', 'Bad', 'text', visible_when=(('missing', ('x',)),)),
    ValidatorControl('rounding', 'Bad', 'choice', choices=((True, 'True'), ('true', 'Text'))),
    ValidatorControl('decimal_places', 'Bad', 'integer', minimum=8, maximum=0),
    ValidatorControl('message', 'Bad', 'text', max_length=-1),
])
def test_invalid_editor_descriptors_are_rejected(control: ValidatorControl) -> None:
    plugin = APPROVED_VALIDATORS['line_amount:v1']
    bad = replace(plugin, editor=ValidatorEditor('Example', 'Description', 'Checks', (control,)))
    with pytest.raises(ValueError):
        build_validator_registry((bad,))


def test_operand_metadata_must_match_approved_binding_types() -> None:
    plugin = APPROVED_VALIDATORS['compare_number:v1']
    bad = replace(plugin, editor=ValidatorEditor('Example', 'Description', 'Checks', (
        ValidatorControl('left', 'Value', 'operand', types=frozenset({'string'})),
    )))
    with pytest.raises(ValueError, match='operand'):
        build_validator_registry((bad,))
