"""Pure, versioned business checks shared by review and gate integration.

This module does not load configuration, save values, or execute user code.
All validators inspect the same payload without applying calculated corrections.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Context, Decimal, DecimalException, localcontext
import re
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BeforeValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    SerializeAsAny,
    StringConstraints,
    field_validator,
    model_validator,
)


MAX_RULES = 50
MAX_ROWS = 1000
Status = Literal["passed", "failed", "not_evaluated", "skipped", "error"]
Severity = Literal["warning", "blocking"]


def _pointer(value: str) -> str:
    if (
        not value.startswith("/")
        or len(value) > 256
        or value.count("/") > 16
        or re.search(r"~(?:[^01]|$)", value)
    ):
        raise ValueError("Use a non-root JSON Pointer with at most 16 segments.")
    return value


Pointer = Annotated[
    str, StringConstraints(strict=True, min_length=1), AfterValidator(_pointer)
]


def _decimal(value: Any) -> Decimal:
    """Read a bounded JSON-compatible number without locale guessing."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("A finite decimal number is required.")
    text = str(value).strip()
    if len(text) > 128:
        raise ValueError("Numeric input exceeds the supported size.")
    try:
        number = Decimal(text)
    except DecimalException as exc:
        raise ValueError("A finite decimal number is required.") from exc
    if (
        not number.is_finite()
        or len(number.as_tuple().digits) > 28
        or (number != 0 and not -28 <= number.adjusted() <= 28)
        or not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text)
    ):
        raise ValueError("Number is outside the supported decimal format/range.")
    return number


class BusinessRule(BaseModel):
    """Common immutable contract for a reviewed server-side validator."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    validator: Annotated[str, StringConstraints(strict=True, max_length=128)]

    id: Annotated[str, StringConstraints(
        strict=True, pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
    )]
    enabled: StrictBool = True
    severity: Severity = "warning"
    require_review: StrictBool = True
    message: Annotated[str, StringConstraints(strict=True, max_length=500)] | None = None


class _AmountRule(BusinessRule):
    tolerance: Decimal = Decimal("0.01")
    decimal_places: Annotated[StrictInt, Field(ge=0, le=8)] = 2
    rounding: Literal["ROUND_HALF_UP", "ROUND_HALF_EVEN"] = "ROUND_HALF_UP"
    collection: Pointer

    @field_validator("tolerance", mode="before")
    @classmethod
    def validate_tolerance(cls, value: Any) -> Decimal:
        number = _decimal(value)
        if number < 0:
            raise ValueError("Tolerance cannot be negative.")
        return number


class LineAmountRule(_AmountRule):
    """Compare quantity times unit price with the entered amount in each row."""

    validator: Literal["line_amount:v1"]
    quantity: Pointer
    unit_price: Pointer
    line_total: Pointer


class SumEqualsRule(_AmountRule):
    """Compare the sum of entered row amounts with a document-level amount."""

    validator: Literal["sum_equals:v1"]
    item_value: Pointer
    target: Pointer


class DateOrderRule(BusinessRule):
    """Require one explicit calendar date to precede another."""

    validator: Literal["date_order:v1"]
    earlier: Pointer
    later: Pointer
    allow_equal: StrictBool = True


def _literal(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 500:
        raise ValueError("Condition text must contain at most 500 characters.")
    if type(value) in {int, float}:
        _decimal(value)
    return value


JsonScalar = Annotated[StrictStr | StrictBool | StrictInt | StrictFloat | None, AfterValidator(_literal)]


class RequiredIfRule(BusinessRule):
    """Require nonempty values when an explicitly typed scalar condition matches."""

    validator: Literal["required_if:v1"]
    when: Pointer
    equals: JsonScalar
    required: Annotated[tuple[Pointer, ...], Field(min_length=1, max_length=20)]

    @field_validator("required")
    @classmethod
    def unique_required(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Required field bindings must be unique.")
        return value


def _parse_rule(value: Any) -> BusinessRule:
    from modules.services.business_validation_registry import get_validator

    raw = value.model_dump() if isinstance(value, BusinessRule) else value
    identifier = raw.get("validator") if isinstance(raw, Mapping) else None
    plugin = get_validator(identifier) if isinstance(identifier, str) else None
    if plugin is None:
        raise ValueError("Select an available validator version.")
    return plugin.configuration.model_validate(raw)


Rule = Annotated[SerializeAsAny[BusinessRule], BeforeValidator(_parse_rule)]


class BusinessValidationConfig(BaseModel):
    """Strict allowlist of versioned validators; no expression/import surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[1] = 1
    rules: Annotated[tuple[Rule, ...], Field(max_length=MAX_RULES)] = ()

    @field_validator("format_version", mode="before")
    @classmethod
    def validate_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Format version must be the integer 1.")
        return value

    @model_validator(mode="after")
    def unique_ids(self) -> BusinessValidationConfig:
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Business-rule IDs must be unique.")
        return self


@dataclass(frozen=True)
class ValidationCheck:
    """One row/document outcome with absolute JSON Pointer evidence paths."""

    rule_id: str
    validator: str
    severity: Severity
    require_review: bool
    status: Status
    code: str
    message: str
    field_paths: tuple[str, ...]
    row_index: int | None = None
    expected: str | None = None
    actual: str | None = None
    difference: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    """Deterministic results; completion policy remains with the review service."""

    checks: tuple[ValidationCheck, ...]

    @property
    def has_blocking_findings(self) -> bool:
        """Include inconclusive blocking rules and all infrastructure errors."""
        return any(
            check.status == "error" or (
                check.severity == "blocking"
                and check.status not in {"passed", "skipped"}
            )
            for check in self.checks
        )

    @property
    def requires_review(self) -> bool:
        """Blocking outcomes cannot opt out of review through rule policy."""
        if self.has_blocking_findings:
            return True
        return any(
            check.status == "error" or (
                check.require_review and check.status not in {"passed", "skipped"}
            )
            for check in self.checks
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible review data; never log this business payload."""
        return {
            "format_version": 1,
            "checks": [
                {**asdict(check), "field_paths": list(check.field_paths)}
                for check in self.checks
            ],
            "has_blocking_findings": self.has_blocking_findings,
            "requires_review": self.requires_review,
        }


class _InputProblem(ValueError):
    def __init__(self, code: str, path: str) -> None:
        self.code = code
        self.path = path


def _lookup(values: Any, path: str) -> Any:
    current = values
    for encoded in path[1:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if key not in current:
                raise _InputProblem("missing_input", path)
            current = current[key]
        elif isinstance(current, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            index = int(key)
            if index >= len(current):
                raise _InputProblem("missing_input", path)
            current = current[index]
        else:
            raise _InputProblem("invalid_input", path)
    return current


def _read(values: Any, path: str) -> Any:
    current = _lookup(values, path)
    if current is None or (isinstance(current, str) and not current.strip()):
        raise _InputProblem("missing_input", path)
    return current


def _number(values: Mapping[str, Any], path: str) -> Decimal:
    value = _read(values, path)
    try:
        return _decimal(value)
    except ValueError as exc:
        raise _InputProblem("invalid_input", path) from exc


def read_business_value(values: Mapping[str, Any], pointer: str, *, allow_empty: bool = False) -> Any:
    """Read an approved binding, preserving structured missing-input failures."""
    _pointer(pointer)
    return _lookup(values, pointer) if allow_empty else _read(values, pointer)


def _check(
    rule: BusinessRule,
    status: Status,
    code: str,
    message: str,
    paths: tuple[str, ...],
    row_index: int | None = None,
    **amounts: str,
) -> ValidationCheck:
    return ValidationCheck(
        rule_id=rule.id, validator=rule.validator, severity=rule.severity,
        require_review=rule.require_review, status=status, code=code,
        message=rule.message if rule.message and status == "failed" else message,
        field_paths=paths, row_index=row_index, **amounts,
    )


def _compare(
    rule: LineAmountRule | SumEqualsRule,
    expected: Decimal,
    actual: Decimal,
    paths: tuple[str, ...],
    row_index: int | None = None,
) -> ValidationCheck:
    quantum = Decimal(1).scaleb(-rule.decimal_places)
    expected = expected.quantize(quantum, rounding=rule.rounding)
    actual = actual.quantize(quantum, rounding=rule.rounding)
    difference = actual - expected
    passed = abs(difference) <= rule.tolerance
    return _check(
        rule, "passed" if passed else "failed",
        "matched" if passed else "amount_mismatch",
        "Amounts agree within tolerance." if passed else "Amounts differ beyond tolerance.",
        paths, row_index, expected=format(expected, "f"),
        actual=format(actual, "f"), difference=format(difference, "f"),
    )


def make_validation_check(
    rule: BusinessRule, status: Status, code: str, message: str, field_paths: tuple[str, ...],
    *, row_index: int | None = None, **evidence: str,
) -> ValidationCheck:
    """Build a plugin outcome with the pinned rule identity and severity policy."""
    return _check(rule, status, code, message, field_paths, row_index, **evidence)


def _evaluate_amount_rule(
    values: Mapping[str, Any], rule: LineAmountRule | SumEqualsRule,
) -> list[ValidationCheck]:
    rows = _read(values, rule.collection)
    if not isinstance(rows, list):
        raise _InputProblem("invalid_collection", rule.collection)
    if len(rows) > MAX_ROWS:
        return [_check(
            rule, "error", "row_limit",
            "Item count exceeds the evaluation limit.", (rule.collection,),
        )]
    if not rows:
        raise _InputProblem("empty_collection", rule.collection)

    if isinstance(rule, LineAmountRule):
        checks = []
        for index in range(len(rows)):
            prefix = f"{rule.collection}/{index}"
            paths = tuple(
                prefix + path
                for path in (rule.quantity, rule.unit_price, rule.line_total)
            )
            try:
                quantity, price, amount = (_number(values, path) for path in paths)
                checks.append(_compare(rule, quantity * price, amount, paths, index))
            except _InputProblem as exc:
                checks.append(_check(
                    rule, "not_evaluated", exc.code,
                    "Check the missing or invalid input.", (exc.path,), index,
                ))
        return checks

    paths = tuple(
        f"{rule.collection}/{index}{rule.item_value}"
        for index in range(len(rows))
    )
    total = sum((_number(values, path) for path in paths), Decimal(0))
    return [_compare(rule, total, _number(values, rule.target), (*paths, rule.target))]


def _calendar_date(values: Mapping[str, Any], pointer: str) -> date:
    raw = _read(values, pointer)
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
        raise _InputProblem("invalid_date", pointer)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise _InputProblem("invalid_date", pointer) from exc


def _evaluate_date_order(values: Mapping[str, Any], rule: DateOrderRule) -> list[ValidationCheck]:
    earlier = _calendar_date(values, rule.earlier)
    later = _calendar_date(values, rule.later)
    passed = earlier <= later if rule.allow_equal else earlier < later
    return [_check(
        rule, "passed" if passed else "failed", "dates_ordered" if passed else "date_order_mismatch",
        "Dates are in the configured order." if passed else "Check the order of the two dates.",
        (rule.earlier, rule.later), expected=f"{'On or after' if rule.allow_equal else 'After'} {earlier.isoformat()}",
        actual=later.isoformat(),
    )]


def _scalar_equal(left: Any, right: Any) -> bool:
    if type(left) in {int, float} and type(right) in {int, float}:
        return _decimal(left) == _decimal(right)
    if type(left) not in {str, bool, int, float, type(None)}:
        raise ValueError("Condition values must be JSON scalars.")
    return type(left) is type(right) and left == right


def _evaluate_required_if(values: Mapping[str, Any], rule: RequiredIfRule) -> list[ValidationCheck]:
    condition = _lookup(values, rule.when)
    try:
        matches = _scalar_equal(condition, rule.equals)
    except ValueError as exc:
        raise _InputProblem("invalid_condition", rule.when) from exc
    if not matches:
        return [_check(rule, "skipped", "condition_not_met", "The condition does not apply.", (rule.when,))]
    missing = []
    for pointer in rule.required:
        try:
            value = _read(values, pointer)
            if value == [] or value == {}:
                missing.append(pointer)
        except _InputProblem:
            missing.append(pointer)
    return [_check(
        rule, "failed" if missing else "passed", "conditional_required_missing" if missing else "required_values_present",
        "Fill the required values for this condition." if missing else "Required values are present.",
        (rule.when, *(missing or rule.required)),
    )]


def _evaluate_rule(values: Mapping[str, Any], rule: BusinessRule) -> list[ValidationCheck]:
    from modules.services.business_validation_registry import get_validator

    plugin = get_validator(rule.validator)
    if plugin is None:
        raise ValueError("Validator is unavailable.")
    if plugin.collection:
        pointer = getattr(rule, plugin.collection)
        rows = _read(values, pointer)
        if not isinstance(rows, list):
            raise _InputProblem("invalid_collection", pointer)
        if len(rows) > MAX_ROWS:
            return [_check(rule, "error", "row_limit", "Item count exceeds the evaluation limit.", (pointer,))]
        if not rows:
            raise _InputProblem("empty_collection", pointer)
    return plugin.evaluate(values, rule)


def evaluate_business_rules(
    values: Mapping[str, Any],
    configuration: Mapping[str, Any] | BusinessValidationConfig | None = None,
) -> ValidationReport:
    """Evaluate every independent rule without saving or changing input values.

    Malformed configuration raises Pydantic ValidationError before evaluation.
    Missing data is a structured inconclusive result; arithmetic/limit errors
    fail closed. Callers supply the pinned configuration and current snapshot.
    """
    if not isinstance(values, Mapping):
        raise TypeError("Business values must be a mapping.")
    config = (
        configuration if isinstance(configuration, BusinessValidationConfig)
        else BusinessValidationConfig.model_validate(
            {} if configuration is None else configuration
        )
    )
    checks: list[ValidationCheck] = []
    for rule in config.rules:
        if not rule.enabled:
            checks.append(_check(rule, "skipped", "disabled", "Rule is disabled.", ()))
            continue
        try:
            with localcontext(Context(prec=80, rounding=getattr(rule, "rounding", "ROUND_HALF_UP"))):
                isolated_values = deepcopy(values)
                isolated_rule = rule.model_copy(deep=True)
                produced = _evaluate_rule(isolated_values, isolated_rule)
                if (isolated_values != values or isolated_rule != rule
                        or not isinstance(produced, (list, tuple)) or len(produced) > MAX_ROWS):
                    raise ValueError("Invalid validator result.")
                for check in produced:
                    if (not isinstance(check, ValidationCheck) or check.rule_id != rule.id
                            or check.validator != rule.validator or check.severity != rule.severity
                            or type(check.require_review) is not bool or check.require_review != rule.require_review or check.status not in {
                                "passed", "failed", "not_evaluated", "skipped", "error",
                            } or not isinstance(check.message, str) or len(check.message) > 1000
                            or not isinstance(check.code, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', check.code)
                            or not isinstance(check.field_paths, tuple) or len(check.field_paths) > MAX_ROWS + 1
                            or any(not isinstance(path, str) or not path.startswith('/') or len(path) > 1024
                                   or path.count('/') > 64 or re.search(r'~(?:[^01]|$)', path)
                                   for path in check.field_paths)
                            or check.row_index is not None and (type(check.row_index) is not int or not 0 <= check.row_index < MAX_ROWS)
                            or any(value is not None and (not isinstance(value, str) or len(value) > 256)
                                   for value in (check.expected, check.actual, check.difference))):
                        raise ValueError("Invalid validator result.")
                if not produced:
                    raise ValueError("Validator returned no result.")
                checks.extend(produced)
        except _InputProblem as exc:
            checks.append(_check(
                rule, "not_evaluated", exc.code,
                "Check the missing or invalid input.", (exc.path,),
            ))
        except DecimalException:
            checks.append(_check(
                rule, "error", "arithmetic_error",
                "The calculation could not be completed.", (getattr(rule, "collection", ""),),
            ))
        except Exception:
            # An approved extension is still a failure boundary. Never expose its
            # exception text or allow a partial/mutated result to pass release.
            checks.append(_check(rule, "error", "validator_error", "The validator could not complete its check.", ()))
    return ValidationReport(tuple(checks))
