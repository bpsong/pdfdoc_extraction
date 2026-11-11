# Develop approved business validators

| Item | Value |
| --- | --- |
| Audience | Developers and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-31 — repository/source review; no live deployment check; Pyright and isolated synthetic regressions |
| Applies to | Production application; SQLite schema 9; format-2 rule forms |

Business validators check a snapshot and produce findings. Keep orchestration,
persistence, claims, and resume in their existing services. The registry is an
explicit source-controlled approval list, separate from the pipeline task import
registry. There is no code-upload, expression evaluator, module-path setting,
or runtime registration endpoint. This is reviewed Python code running in the
application process, not a sandbox for untrusted code.

## Define an exact implementation

In a reviewed module, subclass `BusinessRule` with a literal version and strict
parameters. Use the shared `Pointer` type for bindings. For example:

```python
from typing import Any, Literal, Mapping

from modules.services.business_validation import (
    BusinessRule, Pointer, ValidationCheck, make_validation_check,
    read_business_value,
)


class SupplierRule(BusinessRule):
    validator: Literal['supplier_code:v1']
    supplier: Pointer


def check_supplier(values: Mapping[str, Any], rule: SupplierRule) -> list[ValidationCheck]:
    value = read_business_value(values, rule.supplier)
    valid = isinstance(value, str) and value.startswith('SUP-')
    return [make_validation_check(
        rule, status='passed' if valid else 'failed',
        code='supplier_code_checked', message='Supplier code must start with SUP-.',
        field_paths=(rule.supplier,),
    )]
```

Add its `BusinessValidatorPlugin` descriptor to `APPROVED_VALIDATORS` in
[the registry](../../modules/services/business_validation_registry.py), with a
document binding such as `ValidatorBinding('supplier', types=frozenset({'string'}))`.
For an item validator, declare the collection property and row-relative bindings.
Use `many=True` for a configuration property containing multiple pointers. The
schema binder checks these pointers/types before publication and exact loading.
Add the corresponding reviewed authoring adapter and controls in
`web/static/js/schema-editor/business-rules.js`; an installed server descriptor
alone does not add a new editor template. Preserve unavailable bindings visibly.

Configuration inherits frozen/extra-forbidden behavior. The registry rejects
duplicate IDs or mismatched literal configuration types and exposes an immutable
mapping. Forms resolve exact identifiers only. Keep `supplier_code:v1` unchanged
when adding a new `supplier_code:v2`; published versions and reports retain their
old implementation identities. Startup refuses unavailable IDs. Do not alias an
old name to changed behavior or edit immutable form records.

## Preserve bounded, independent evaluation

Each evaluator receives its own copied snapshot and configuration. Never mutate
either; mutation becomes a blocking error. Do not perform network, filesystem,
database, subprocess, OCR, or other side effects. Read persisted/enriched inputs
through form fields; reference lookups belong in a separate task before the gate.
Rules must finish with bounded CPU/memory work. There is no process-level timeout
or isolation for approved Python code; review algorithms as part of approval.

Isolation currently copies the entire supplied values mapping for every enabled
rule and compares it with the original after evaluation. Evaluation cost therefore
depends on the full document size as well as rule and row counts. Measure with
synthetic representative payloads before changing this boundary. A hash can
detect mutation but cannot by itself prevent mutation of the original or keep
one rule's changes from reaching another. Performance investigation is tracked
in the [audit follow-up plan](../../tasks/tasks-r4-audit-follow-up.md).

The engine allows 50 rules, 1,000 rows per collection, and 1–1,000 checks per
evaluator. Numeric checks use an 80-digit Decimal context and bounded input size,
precision and exponent. Returned `ValidationCheck` objects must retain the rule's
ID, validator, severity and review policy. Messages are at most 1,000 characters,
codes match a bounded identifier, paths use valid JSON Pointers, row indexes are
0–999, and expected/actual/difference evidence strings are at most 256 characters.
Return structured evidence rather than raw tracebacks. The engine rejects invalid
contracts, converts plugin exceptions into generic blocking `validator_error`
findings, and continues other independent rules. Missing/invalid inputs cannot
count as passes. A `skipped` result means disabled or not applicable, never success.

The broad exception boundary is intentional. A generic infrastructure error may
have no field paths because the evaluator did not establish trustworthy field
evidence. It still identifies the rule and validator and blocks release. The
current boundary does not log the caught exception. Planned diagnostic logging
must use safe code metadata and exclude exception messages, values, configuration
dumps, and traceback locals; it must preserve the generic report and independent
rule execution.

The shared evaluator runs at the gate, on displayed/draft values, on unsaved
Revalidate requests, and independently at completion. Warnings follow configured
review policy; blocking failures/inconclusive outcomes and evaluator errors prevent
release. No validator calculates replacement field values. Acceptance commits
corrections, final report and workflow state atomically before resume. Reports
contain business evidence: audit only identities/counts and keep values/messages
out of logs.

## Verify and release

Test valid/invalid/missing data, type/binding rejection, limits, deterministic
results, no mutation or I/O, exceptions, invalid results, and independent rules.
Keep old/new implementations tested together. Include schema serialization,
publication/hash retention, exact-version gate and completion, browser authoring,
stale findings, and actual downstream exports. Use synthetic documents and
temporary databases; no provider credentials are needed.

Run the pinned [Pyright check](testing-and-verification.md#static-type-checking)
as well as runtime tests. Annotate evaluator input as `Mapping[str, Any]` and
results as `list[ValidationCheck]`. Bind enum values using the same aliases,
label fallback, and typed equality as schema/review controls; test both portable
aliases and numeric-versus-boolean cases. Retain existing valid version behavior.

See [schema format](../reference/review-schema-format.md#business-validation-configuration),
[task standards](../../tasks/standard_task_creation_guidelines.md#pinned-business-validation-at-the-review-gate),
and the [R4 verification record](../../tasks/tasks-r4-business-validation.md).
