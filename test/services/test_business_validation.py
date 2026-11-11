"""Synthetic contracts and arithmetic behavior for shared business validation."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
import json
from typing import Any

from pydantic import ValidationError
import pytest

from modules.services import business_validation as validation
from modules.services.business_validation import (
    BusinessValidationConfig, evaluate_business_rules,
)


def line_rule(**changes: Any) -> dict[str, Any]:
    return {
        "id": "line_amount", "validator": "line_amount:v1",
        "collection": "/items", "quantity": "/quantity",
        "unit_price": "/unit_price", "line_total": "/line_total", **changes,
    }


def sum_rule(**changes: Any) -> dict[str, Any]:
    return {
        "id": "subtotal", "validator": "sum_equals:v1",
        "collection": "/items", "item_value": "/line_total",
        "target": "/subtotal", **changes,
    }


def invoice(amount: str = "30.00", subtotal: str = "30.00") -> dict[str, Any]:
    return {
        "items": [{"quantity": 3, "unit_price": "10.00", "line_total": amount}],
        "subtotal": subtotal,
    }


def evaluate(
    values: dict[str, Any], *rules: dict[str, Any],
) -> validation.ValidationReport:
    return evaluate_business_rules(values, {"format_version": 1, "rules": list(rules)})


def test_multiple_rules_pass_and_return_json_serializable_evidence() -> None:
    values = invoice()
    values["items"].append({"quantity": 2, "unit_price": 5, "line_total": 10})
    values["subtotal"] = "40"
    report = evaluate(values, line_rule(), sum_rule(severity="blocking"))
    assert [check.status for check in report.checks] == ["passed"] * 3
    assert [check.row_index for check in report.checks] == [0, 1, None]
    assert report.checks[1].field_paths == (
        "/items/1/quantity", "/items/1/unit_price", "/items/1/line_total",
    )
    assert report.checks[-1].expected == "40.00"
    assert report.checks[-1].validator == "sum_equals:v1"
    assert not report.has_blocking_findings and not report.requires_review
    assert json.loads(json.dumps(report.to_dict()))["checks"][0]["expected"] == "30.00"


@pytest.mark.parametrize(
    ("amount", "subtotal", "statuses"),
    [
        ("300", "30", ["failed", "failed"]),
        ("300", "300", ["failed", "passed"]),
        ("30", "300", ["passed", "failed"]),
    ],
)
def test_rules_are_independent_and_never_correct_each_others_inputs(
    amount: str, subtotal: str, statuses: list[str],
) -> None:
    values = invoice(amount, subtotal)
    original = deepcopy(values)
    report = evaluate(values, line_rule(), sum_rule(severity="blocking"))
    assert [check.status for check in report.checks] == statuses
    assert report.has_blocking_findings == (statuses[1] == "failed")
    assert report.requires_review
    assert values == original


def test_reversing_rules_does_not_change_their_individual_results() -> None:
    first = evaluate(invoice("300", "30"), line_rule(), sum_rule())
    second = evaluate(invoice("300", "30"), sum_rule(), line_rule())
    assert first.checks == tuple(reversed(second.checks))


@pytest.mark.parametrize(
    ("actual", "status"), [("30.01", "passed"), ("29.99", "passed"), ("30.02", "failed")],
)
def test_tolerance_is_inclusive_in_both_directions(actual: str, status: str) -> None:
    check = evaluate(invoice(actual), line_rule()).checks[0]
    assert check.status == status
    assert check.actual == actual


@pytest.mark.parametrize(
    ("rounding", "expected"), [("ROUND_HALF_UP", "1.01"), ("ROUND_HALF_EVEN", "1.00")],
)
def test_rounding_is_explicit_and_independent_of_the_callers_decimal_context(
    rounding: str, expected: str,
) -> None:
    values = invoice(expected, expected)
    values["items"][0].update(quantity="1", unit_price="1.005")
    with localcontext() as context:
        context.prec = 2
        context.rounding = "ROUND_DOWN"
        check = evaluate(values, line_rule(rounding=rounding, tolerance="0")).checks[0]
        assert context.prec == 2
    assert check.status == "passed" and check.expected == expected


def test_sum_uses_entered_values_and_rounds_once_after_aggregation() -> None:
    values = {"items": [{"line_total": "0.005"}, {"line_total": "0.005"}], "subtotal": "0.01"}
    check = evaluate(values, sum_rule(tolerance="0")).checks[0]
    assert check.status == "passed" and check.expected == "0.01"


def test_negative_credit_values_zero_and_float_inputs_are_supported() -> None:
    values = {"items": [
        {"quantity": -3, "unit_price": 0.1, "line_total": -0.3},
        {"quantity": 0, "unit_price": "2.00", "line_total": 0},
    ], "subtotal": "-0.30"}
    assert all(check.status == "passed" for check in evaluate(values, line_rule(), sum_rule()).checks)


@pytest.mark.parametrize("bad", [None, "", "  ", True, False, "NaN", "Infinity", float("nan"),
                                  "1,000.00", "$10", {}, [], "1e100", "1e-100", "9" * 29,
                                  "1" * 129, "１２", "0_1"])
def test_missing_and_invalid_numbers_are_inconclusive_without_partial_sum(bad: Any) -> None:
    values = invoice()
    values["items"].append({"quantity": 1, "unit_price": 1, "line_total": bad})
    report = evaluate(values, line_rule(), sum_rule(severity="blocking"))
    assert [check.status for check in report.checks] == ["passed", "not_evaluated", "not_evaluated"]
    assert report.checks[-1].field_paths == ("/items/1/line_total",)
    assert report.checks[-1].expected is None
    assert report.has_blocking_findings and report.requires_review


def test_missing_quantity_does_not_prevent_independent_subtotal_check() -> None:
    values = invoice()
    del values["items"][0]["quantity"]
    report = evaluate(values, line_rule(), sum_rule())
    assert report.checks[0].code == "missing_input"
    assert report.checks[1].status == "passed"


@pytest.mark.parametrize("rows", [None, [], {}, "invalid", ["not a row"]])
def test_bad_or_empty_collections_never_pass(rows: Any) -> None:
    report = evaluate({"items": rows, "subtotal": 0}, line_rule(), sum_rule())
    assert all(check.status == "not_evaluated" for check in report.checks)
    assert report.requires_review and not report.has_blocking_findings


def test_missing_collection_and_target_have_actionable_paths() -> None:
    report = evaluate({}, line_rule(), sum_rule())
    assert all(check.field_paths == ("/items",) for check in report.checks)
    values = invoice()
    del values["subtotal"]
    check = evaluate(values, sum_rule()).checks[0]
    assert check.field_paths == ("/subtotal",) and check.code == "missing_input"


def test_escaped_and_nested_json_pointers() -> None:
    values = {"invoice": {"a/b": [{"~price": {"quantity": 3, "price": 10, "amount": 30}}], "sum": 30}}
    report = evaluate(values, line_rule(
        collection="/invoice/a~1b", quantity="/~0price/quantity",
        unit_price="/~0price/price", line_total="/~0price/amount",
    ), sum_rule(collection="/invoice/a~1b", item_value="/~0price/amount", target="/invoice/sum"))
    assert all(check.status == "passed" for check in report.checks)
    assert report.checks[0].field_paths[-1] == "/invoice/a~1b/0/~0price/amount"


def test_disabled_and_no_rules_are_explicit_nonblocking_results() -> None:
    report = evaluate({}, line_rule(enabled=False, severity="blocking"))
    assert report.checks[0].status == "skipped"
    assert not report.has_blocking_findings and not report.requires_review
    assert evaluate_business_rules({}).checks == ()
    assert evaluate_business_rules({}, {}).checks == ()


def test_blocking_rule_cannot_bypass_review_when_review_flag_is_disabled() -> None:
    report = evaluate(invoice("300"), line_rule(require_review=False))
    assert report.checks[0].status == "failed"
    assert not report.requires_review and not report.has_blocking_findings
    blocked = evaluate(invoice("300"), line_rule(severity="blocking", require_review=False))
    assert blocked.has_blocking_findings and blocked.requires_review


@pytest.mark.parametrize("changes", [
    {"validator": "line_amount:v2"}, {"validator": "custom_step.execute"},
    {"code": "raise Exception()"}, {"tolerance": "-0.01"}, {"tolerance": "NaN"},
    {"tolerance": True}, {"decimal_places": 9}, {"decimal_places": True},
    {"enabled": "false"}, {"require_review": 1}, {"id": ""},
    {"severity": "info"}, {"rounding": "unknown"}, {"quantity": "quantity"},
    {"quantity": ""}, {"quantity": "/a~2b"}, {"quantity": "/a~"},
    {"quantity": "/" + "x" * 256}, {"quantity": "/a" * 17},
])
def test_invalid_rule_configuration_fails_before_evaluating(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        evaluate(invoice(), line_rule(**changes))


@pytest.mark.parametrize("configuration", [
    {"format_version": 2}, {"format_version": True}, {"format_version": "1"},
    {"unexpected": []}, {"rules": [line_rule(), line_rule()]},
    {"rules": [line_rule(id=f"rule{i}") for i in range(validation.MAX_RULES + 1)]},
])
def test_invalid_config_version_duplicate_ids_and_rule_limits(
    configuration: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        evaluate_business_rules(invoice(), configuration)


def test_resource_limit_fails_closed_even_for_warning_with_review_disabled() -> None:
    values = {"items": [{}] * (validation.MAX_ROWS + 1)}
    report = evaluate(values, line_rule(require_review=False))
    assert report.checks[0].status == "error" and report.checks[0].code == "row_limit"
    assert report.requires_review and report.has_blocking_findings


def test_arithmetic_failure_is_visible_and_does_not_skip_other_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = validation._evaluate_rule

    def raise_for_line(
        values: dict[str, Any], rule: validation.LineAmountRule | validation.SumEqualsRule,
    ) -> list[validation.ValidationCheck]:
        if isinstance(rule, validation.LineAmountRule):
            raise InvalidOperation
        return original(values, rule)

    monkeypatch.setattr(validation, "_evaluate_rule", raise_for_line)
    report = evaluate(invoice(), line_rule(require_review=False), sum_rule())
    assert [check.status for check in report.checks] == ["error", "passed"]
    assert report.has_blocking_findings and report.requires_review


def test_configuration_round_trip_preserves_versions_and_deterministic_reports() -> None:
    config = BusinessValidationConfig.model_validate({"rules": [line_rule(), sum_rule()]})
    restored = BusinessValidationConfig.model_validate_json(config.model_dump_json())
    values = invoice("300")
    assert evaluate_business_rules(values, config) == evaluate_business_rules(values, restored)
    first = config.rules[0]
    assert isinstance(first, validation.LineAmountRule)
    assert first.tolerance == Decimal("0.01")
    with pytest.raises(ValidationError):
        config.rules[0].enabled = False


def test_message_is_literal_data_and_values_are_not_mutated() -> None:
    config = {"rules": [line_rule(message="{line_total} <script>literal</script>")]}
    values = invoice("300")
    originals = deepcopy((config, values))
    check = evaluate_business_rules(values, config).checks[0]
    assert check.message == config["rules"][0]["message"]
    assert (config, values) == originals


def test_non_mapping_payload_is_a_programming_error() -> None:
    with pytest.raises(TypeError, match="must be a mapping"):
        evaluate_business_rules(json.loads('[]'))


def test_nested_array_bindings_and_fractional_quantity() -> None:
    values = {"groups": [{"items": [
        {"numbers": ["1.5", "2.40", "3.60"]},
    ]}], "subtotal": "3.60"}
    report = evaluate(values, line_rule(
        collection="/groups/0/items", quantity="/numbers/0",
        unit_price="/numbers/1", line_total="/numbers/2",
    ), sum_rule(collection="/groups/0/items", item_value="/numbers/2"))
    assert all(check.status == "passed" for check in report.checks)


@pytest.mark.parametrize("amount", ["1e28", "1e-28", "9" * 28, "0e-100"])
def test_supported_numeric_boundaries_do_not_cause_arithmetic_errors(amount: str) -> None:
    values = invoice(amount, amount)
    values["items"][0].update(quantity=1, unit_price=amount)
    report = evaluate(values, line_rule(), sum_rule())
    assert all(check.status == "passed" for check in report.checks)


@pytest.mark.parametrize("places", [0, 8])
def test_decimal_place_limits_and_rounding_of_observed_amount(places: int) -> None:
    values = invoice("1.000000001", "1")
    values["items"][0].update(quantity=1, unit_price=1)
    check = evaluate(values, line_rule(decimal_places=places, tolerance="0")).checks[0]
    assert check.status == "passed"
    assert check.actual == ("1" if places == 0 else "1.00000000")


def test_row_limit_accepts_exact_boundary() -> None:
    row = invoice()["items"][0]
    report = evaluate({"items": [row] * validation.MAX_ROWS}, line_rule())
    assert len(report.checks) == validation.MAX_ROWS
    assert all(check.status == "passed" for check in report.checks)


def test_disabled_rule_still_requires_a_valid_configuration() -> None:
    with pytest.raises(ValidationError):
        evaluate({}, line_rule(enabled=False, validator="missing:v1"))


def test_invalid_target_is_not_replaced_by_zero() -> None:
    check = evaluate(invoice(subtotal="invalid"), sum_rule()).checks[0]
    assert check.status == "not_evaluated"
    assert check.field_paths == ("/subtotal",)
    assert check.actual is None and check.expected is None
