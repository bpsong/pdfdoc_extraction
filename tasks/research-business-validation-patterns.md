# Research: useful additions to the business-rule catalog

| Item | Value |
| --- | --- |
| Researched | 2026-11-12 |
| Status | Recommendations for review; no application changes |
| Scope | Document-independent rule patterns and shared authoring capabilities |
| Basis | Current repository implementation and primary product/standards documentation |

## Recommendation

Expand the five-pattern catalog with five additional patterns: **Calculate and
compare**, **Match fields**, **Unique rows**, **Row count**, and **Required field
group**. Add a shared **When** condition and consistent document/current-row
scope as supporting capabilities, rather than creating separate patterns for
every conditional variation. This would produce ten selectable patterns while
making existing ones more useful across document types.

These priorities are engineering judgments about reusable coverage and the
current gaps. They are not frequency estimates from the user's document corpus
or a commitment to implement every feature at once.

## What the current application already covers

The approved registry exposes numeric comparison, multiplication of two row
fields, summation of row values against a document field, date order, and
conditional required fields. The editor selects compatible fields through
server-owned metadata. Existing exact validator versions must remain available.

The ordinary form-field configuration already supports requiredness, numeric
minimum/maximum, string lengths, regex patterns, enum choices, and value types.
Do not present these as entirely missing business capabilities. Their current
schema-validation behavior differs from configurable warning/blocking business
findings; reusing validation helpers is preferable to duplicating semantics.

Local sources: [registry](../modules/services/business_validation_registry.py),
[models/evaluator](../modules/services/business_validation.py),
[field validation](../modules/services/schema_service.py), and
[existing admin controls](../docs/admin/managing-review-forms.md#choose-the-control-and-its-limits).

## Highest-value additions

| Proposed picker pattern | Examples across document types | Gap and proposed boundary | Relative scope |
| --- | --- | --- | --- |
| **Calculate and compare** | Shipment gross = net + packaging; claim payable = allowed - deductible; document total = subtotal + charges - discount | Extend beyond the current two fixed arithmetic shapes. Use selected fields/constants and approved operators in a bounded calculation tree, initially addition/subtraction/multiplication, with explicit rounding and tolerance. Division can follow after zero-denominator and precision semantics are designed. No uploaded code or arbitrary expression execution. | Larger |
| **Match fields** | Header currency = row currency; policy reference = endorsement reference; sender identifier = declared sender identifier | Typed equality/inequality between fields, including text, date, and boolean values. Exact comparison by default; explicit trim/case options for text. No fuzzy matching or silent correction. Numeric comparison remains available under its existing version. | Medium |
| **Unique rows** | Package serials are unique; benefit identifiers are unique; line sequence numbers are unique | Select one or more key fields within one repeating group. Report all conflicting row indexes. Define null/blank, case, whitespace, and type semantics. Do not assume a product code must be unique: legitimate repeated items are common. | Medium |
| **Row count** | At least one package; number of insured people = declared count; number of extracted lines = printed line count | Compare collection length with a constant, numeric document field, or inclusive range. Define whether all rows or only explicitly qualifying rows count; do not silently ignore blank rows. Start with unfiltered count. | Smaller |
| **Required field group** | At least one of email/phone; exactly one of two alternative references; bank account and account-holder name supplied together | Support at-least-one, exactly-one, and all-or-none presence modes for selected fields. Missing, null, and blank/empty values need explicit semantics; false and zero remain supplied values. This adds relationships that ordinary Required flags cannot express. | Medium |

The arithmetic and field-matching directions are supported by documented
multi-field integrity checks in [Great Expectations](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/integrity/)
and mathematical expressions in [UiPath Taxonomy Manager](https://docs.uipath.com/document-understanding/automation-cloud/latest/classic-user-guide/taxonomy-manager).
These are capability precedents, not evidence that their exact configuration
contracts should be copied.

Single/composite uniqueness is explicitly documented by
[Great Expectations](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/uniqueness/).
Its [volume checks](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/volume/)
also cover row-count bounds and equality. Adapting those concepts to document
repeating groups is the recommendation here; document-relative count comparisons
are our proposed extension.

[JSON Schema conditional dependencies](https://json-schema.org/understanding-json-schema/reference/conditionals)
and [Boolean schema combinations](https://json-schema.org/understanding-json-schema/reference/combining)
provide a basis for grouped presence requirements. Property existence in JSON
Schema is not identical to a business value being nonblank; the UI/evaluator
must define the latter explicitly.

## Shared capabilities needed alongside the patterns

### When conditions

Allow an optional structured condition on an eligible rule: comparisons,
membership, and presence tests combined with bounded ALL/ANY groups. For example,
if a line is taxable, check its recorded tax against the configured calculation;
if a shipment is hazardous, require its relevant references. A known-false
condition is not applicable; missing/invalid condition inputs must not silently
disable a blocking check.

This is broader than today's conditional-required pattern. The current pattern
only tests one typed equality and then requires fields; it cannot condition a
numeric comparison or calculation. Keep that existing validator version intact.
[GX row conditions](https://docs.greatexpectations.io/docs/core/customize_expectations/row_conditions/)
document conditional application of checks, including comparison, membership,
nullity, and AND/OR relationships. The recommended UI would be a bounded form
builder rather than the Python expressions used in that product.

### Consistent scope and review explanations

Extend eligible date and requirement checks to current-row scope using explicit
document/current-row field selectors. Keep each rule independent; scope support
does not imply joins or rule chaining. A cross-field failure should identify all
relevant fields, while duplicate and count findings should explain affected rows
and observed/expected counts. Preserve the existing claim, revision, Revalidate,
draft, and independent completion enforcement contracts.

## Useful next-stage patterns

| Candidate | Value | Why later / what is actually new |
| --- | --- | --- |
| **Date distance / age** | Delivery within N days of dispatch; document age within a configured limit | Basic start <= event <= end can already use two Date order rules. Offsets/durations are the gap. Calendar-day versus business-day rules and timezone must be explicit. A rule using a reference date should consume a persisted reference, so repeated evaluation and accepted reports remain reproducible. |
| **Filtered aggregate** | Sum taxable lines; count covered people satisfying a condition; compare totals per category | Builds on When predicates and collection checks. Define empty-match behavior, unknown predicate inputs, group limits, and missing contributors before adding sum/count/min/max variants. |
| **Match reference / related document** | Supplier exists in approved master data; shipment items match an order; policy matches a prior record | Valuable but requires a separate enrichment/integration design. Fetch/version the evidence upstream and validate a persisted snapshot; do not add network/database lookups inside the pure evaluator. Matching keys, ambiguous matches, stale data, and access controls must be specified. |

[ABBYY FlexiCapture's documented invoice checks](https://help.abbyy.com/en-us/flexicapture/12/standalone_administrator/ir_verstatus/)
include arithmetic reconciliation, relative-date checks, and purchase-order
matching. These demonstrate real document-processing use cases; their
country-specific rules and automatic value filling are not recommendations for
this generic evaluator.

Cross-document duplicate prevention should also remain a separate design: a
read-only duplicate check alone cannot prevent concurrent acceptance of two
documents. Authoritative identity and transactional enforcement are required.

## Candidates not prioritized as new patterns

- Fixed numeric ranges, required fields, text length, regex, and fixed choices:
  already available in field configuration. Friendly presets could improve UX.
- Numeric equality: already covered by Compare numbers.
- Simple date ordering or a date between two fields: already expressible with
  Date order rules; offsets and conditional/row applicability are the gaps.
- Percentage calculation: include it through Calculate and compare using an
  explicit configured rate, rather than adding invoice/tax-specific patterns.
- AI plausibility, fuzzy party matching, and identifier checksums: useful for
  some workflows but need separate confidence, domain, and versioning contracts.

## Suggested delivery order

1. Agree on supported use cases and shared condition/scope semantics, using
   synthetic examples from shipping, insurance, and invoices.
2. Add Match fields and Row count, then Unique rows and Required field group.
   Build Calculate and compare as its own reviewed change because its numeric
   and UI contracts are broader.
3. Introduce shared When conditions incrementally for eligible patterns; retain
   unknown/missing outcomes and existing version compatibility.
4. Add date distance and filtered aggregates once their required context and
   predicate semantics are proven.
5. Design external/reference matching separately with persisted evidence and
   appropriate integration boundaries.

Each implementation should include configuration validation, immutable version
loading, gate/revalidation/completion enforcement, independent rules, and clear
operator evidence. Verify normal forms with no business rules as well.

## Research limits and verification

The sources establish available validation concepts, not their usage frequency,
ROI, or guaranteed suitability for every document. Recommendations above are
local design inferences. All sources were accessed on 2026-11-12; product pages
refer to the versions/editions they document and are not a universal comparison
of every current offering.

No application behavior, dependencies, runtime configuration, database, or rule
catalog was changed for this research. Runtime, type, and browser checks were
not rerun because this delivery adds a research document only.

Documentation structure verification passed **18 tests** in 0.89 seconds, using
`.\.venv\Scripts\python.exe -m pytest -q test/tools/test_documentation_structure.py --tb=short`.
`git diff --check` passed. No files were staged or committed.
