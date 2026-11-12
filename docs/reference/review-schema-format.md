# Review schema format and validation

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-11-11 — repository/source review; no live deployment check; comparison operands/scopes, publication/bindings, and synthetic regressions |
| Applies to | Production application; SQLite schema 9 |

Routine form authoring belongs in the [Admin guide](../admin/managing-review-forms.md).
This reference covers portable YAML/JSON and advanced field mapping. Runtime
review uses the exact published SQLite definition selected by the pipeline.
Editing a filesystem schema does not change already-published behaviour.

## Import, Export, and Legacy Migration

YAML and JSON files are portable interchange and legacy migration formats; they
are not the authoritative runtime store. Import a file into a schema draft,
validate it, and explicitly publish it. The application then stores the
canonical definition and immutable versions in SQLite.

### Legacy `schema_file` migration

Older deployment YAML identifies a filesystem schema with `schema_file`:

```yaml
tasks:
  review_gate:
    module: standard_step.review.review_gate
    class: ReviewGateTask
    params:
      schema_file: "schemas/invoice.yaml"
```

This is legacy migration input only. Current pipeline validation rejects
`schema_file`; do not configure it for a new pipeline. Import the file into a
review-form draft, publish it, select its exact `schema_version_id` in the
pipeline editor, then validate and publish a new pipeline version.

Folders used to locate legacy filesystem schemas can be configured explicitly:

```yaml
schema:
  directories:
    - "schemas"
```

Relative folder names are resolved from the folder containing `config.yaml`.
They do not control where Review Form Editor drafts are saved; those drafts and
their published versions are stored in SQLite. Ask the application owner before
changing the legacy schema search roots.

### Safe import procedure

1. Confirm the legacy file or portable export to import.
2. Preserve an unchanged backup outside runtime and source-control secrets.
3. Open the file in a plain-text editor if changes are required.
4. Make the required changes. Use spaces, not tabs, for indentation.
5. Save the file as UTF-8 text and keep its existing `.yaml`, `.yml`, or
   `.json` extension.
6. Open the configured application address and go to `/app/schemas`; choose
   **Import** and target an editable draft. Import files must be no larger than
   1 MiB. If `format_version` is present, it must be `1` or `2`. Published forms
   containing business rules use outer format `2`; the rules' own format remains `1`.
7. Validate and correct every blocking finding.
8. Publish the schema version, select it in the pipeline draft, and publish the
   pipeline version.
9. Test a representative document in the Review Queue.

If import fails, restore the backup and validate the portable file with the CLI
described under Advanced Validation.

### YAML formatting rules

- Use spaces for indentation. Two spaces per level is recommended.
- Keep every field under `fields:`.
- Indent a field's settings below its key.
- Indent object children below `properties:`.
- Indent the definition of array members below `items:`.
- Use `true` and `false` without quotation marks for yes/no settings.
- Put quotation marks around ambiguous text, especially values containing `:`,
  `#`, or leading zeros.
- Do not repeat a key at the same level.

This is a minimal valid YAML schema:

```yaml
title: Invoice Review
description: Check the extracted invoice details.
version: "1.0"
fields:
  invoice_number:
    type: string
    label: Invoice number
    required: true
    help: Enter the invoice number exactly as printed.

  invoice_date:
    type: date
    label: Invoice date
    required: true

  invoice_amount:
    type: number
    label: Invoice amount
    required: true
    format: money
    decimal_places: 2
    min_value: 0
```

## Schema File Reference

### Top-level settings

| Setting | Required | Purpose |
| --- | --- | --- |
| `title` | Recommended by the editor | Friendly name of the schema; browser checks require it, but the server validator does not enforce it |
| `description` | Recommended | Short explanation of when the form is used |
| `version` | Optional in portable files | Descriptive source label; SQLite assigns the authoritative immutable version number |
| `fields` | Yes | Collection of fields displayed on the review form |
| `business_validation` | Optional | Versioned deterministic rules enforced at the gate and review completion |

The Review Form Editor displays authoritative version history. An exported draft includes its revision, not a published version number. A version label inside imported content does not select or overwrite an SQLite version. Field keys and settings are not comprehensively allowlisted by server validation; unknown or misspelled settings may be carried through without being applied.

### Business validation configuration

The published review-schema record uses outer format version 2 when it contains
business rules. The nested `business_validation.format_version` remains 1 and
versions the rule configuration independently. These values describe different
contracts. Business reports expose the enclosing version as
`schema_format_version`; their own `format_version` versions the report contract.

Published rules run against persisted extracted fields at the review gate and
against the actual submitted values before review completion. Existing confidence,
legacy review flags, and field/schema checks still apply. The detail API evaluates
the displayed values including saved drafts; the revalidation API evaluates unsaved
corrections without saving or resuming. The review screen displays independent
rule outcomes, inline field/row findings, decimal evidence, and a Revalidate
action. Editing values or rows invalidates the current annotations; responses
are applied only when the local edits, request tag, source revision, and pinned
form/hash still match. Completed reviews show their stored accepted report.

```yaml
business_validation:
  format_version: 1
  rules:
    - id: item_amount
      validator: line_amount:v1
      collection: /items
      quantity: /quantity
      unit_price: /unit_price
      line_total: /line_total
      severity: warning
      tolerance: "0.01"
    - id: invoice_subtotal
      validator: sum_equals:v1
      collection: /items
      item_value: /line_total
      target: /subtotal_before_discount
      severity: blocking
      tolerance: "0.01"
```

`collection` must resolve to an existing array of objects. Row bindings are
JSON Pointers relative to an item; `target` is relative to the document. Bind
numeric `number`, `float`, or `integer` fields. Nested objects and explicitly
indexed array members are supported; `~0` escapes a tilde and `~1` a slash.
Wildcards, expression strings, and import/module paths are not supported.

Each rule needs a unique ID and an available, explicit `validator` version.
Common settings default to `enabled: true`, `require_review: true`, and
`severity: warning`. The two arithmetic templates also default to
`tolerance: "0.01"`, `decimal_places: 2`, and `rounding: ROUND_HALF_UP`.
`ROUND_HALF_EVEN` is also supported. Decimal places
must be an integer from 0 to 8; tolerance must be a bounded finite nonnegative
decimal. `message` is optional plain text, at most 500 characters. The evaluator
rounds expected and observed amounts before comparing against inclusive tolerance;
the subtotal sums entered amounts and rounds once. Missing inputs are inconclusive.

Two additional templates use document-relative pointers:

```yaml
business_validation:
  format_version: 1
  rules:
    - id: invoice_dates
      validator: date_order:v1
      earlier: /invoice_date
      later: /due_date
      allow_equal: true
      severity: blocking
    - id: purchase_order
      validator: required_if:v1
      when: /has_purchase_order
      equals: true
      required: [/purchase_order_number, /supplier/name]
      severity: warning
```

`date_order:v1` binds two `date` fields. Values must be real calendar dates in
`YYYY-MM-DD` format; date-times, localized strings, and surrounding whitespace
are invalid. It checks `earlier <= later`, or strict `<` with `allow_equal: false`.
Missing/invalid dates cannot be evaluated. It does not guess time zones or formats.

`required_if:v1` compares a scalar `when` field with a typed JSON `equals`
constant. Boolean `true`, number `1`, and text `"1"` are different; numeric
`1` and `1.0` match. The constant must fit the selected field's type and enum
choices, if defined. Select 1–20 unique existing document fields in `required`.
When the condition matches, null, blank text, empty arrays, and empty objects
are missing; `false` and `0` are present. A nonmatching condition is **Not
applicable**, distinct from a disabled rule. A missing condition key cannot be
evaluated. An explicitly present null can match `equals: null`; null does not
match an absent key. Neither template accepts arithmetic settings.

Enum bindings honor both `choices` and the compatible `enum` field setting.
For choice objects, compare with `value`, falling back to `label` only when
`value` is absent. Numeric `1` and `1.0` are equivalent here too; booleans remain
distinct from numbers. A non-null constant outside the offered values is an
error in the editor, publication, portable validation, and exact-version checks.

The general numeric comparison pattern supports document or independent row
checks without invoice-specific keys:

```yaml
business_validation:
  format_version: 1
  rules:
    - id: delivered_within_order
      validator: compare_number:v1
      scope: rows
      collection: /packages
      left: {kind: field, scope: row, field: /delivered}
      operator: lte
      right: {kind: field, scope: row, field: /ordered}
      severity: blocking
    - id: coverage_limit
      validator: compare_number:v1
      scope: document
      left: {kind: field, scope: document, field: /covered}
      operator: lte
      right: {kind: constant, value: "100000.00"}
      severity: blocking
```

`compare_number:v1` requires `left`, `operator`, and `right`. Its `scope` is
`document` (default) or `rows`. `left` must be a field operand. `right` is either a field operand
or a finite decimal constant. A field operand contains exactly `kind: field`,
`scope: document|row` (default document), and `field`. A constant contains
`kind: constant` and `value`; it accepts a bounded numeric value or decimal string,
never a boolean. Operand field bindings must be numeric. A document check forbids
`collection` (including null) and row operands. A rows check requires an
array-of-objects `collection`; either operand may reference document scope or
the current row. There are no joins or cross-row references. Evidence uses
absolute paths, including the row index.

Operators are `eq`, `ne`, `lt`, `lte`, `gt`, and `gte`. Ordering compares exact
Decimal values without quantization or rounding. Only `eq`/`ne` accept
`tolerance`, a bounded nonnegative decimal defaulting to zero. Equality passes
when the absolute difference is at most tolerance; inequality passes when it is
greater. Ordering rejects an explicitly supplied tolerance, including null.
There are no rounding/decimal-place options for comparisons. Missing, null,
blank, malformed, or nonfinite inputs are inconclusive; an empty/invalid
collection is inconclusive and an oversized collection produces a blocking
error. Row checks remain independent when another row has invalid inputs.

The editor obtains display metadata from the approved catalog; titles and widget
defaults are not inserted into existing stored configurations merely by opening
the editor. Existing identifiers `line_amount:v1`, `sum_equals:v1`,
`date_order:v1`, and `required_if:v1` retain their keys and evaluation semantics.
Their display titles describe reusable operations; this does not migrate hashes,
rewrite old forms, or change accepted reports.

Specialized validators use the reviewed, source-controlled
[plugin contract](../developer/business-validation-plugins.md). Forms cannot
upload code or select Python modules. Exact identifiers such as `name:v1`
remain supported while a changed implementation is added as `name:v2`.

Each collection check supports at most 1,000 rows. Numeric inputs have at most
128 characters, 28 significant digits, and adjusted exponent from -28 to 28.
Checks reject nonfinite/localized values and booleans as amounts. Validator
failures become blocking error findings; another independent rule still runs.

At most 50 rules are allowed. Unknown properties/versions, duplicate IDs,
malformed pointers, and missing/incompatible field bindings prevent publication,
including for disabled rules. Rule definitions are preserved without injecting
defaults into stored content. A rule change changes the form's content hash.
Forms without the section remain unchanged; an explicitly malformed/null section
is an error. Portable/stored config checks and pipeline dependency validation
use the same binding validator. Startup and exact-version loading reject
unsupported published rules; retain old implementations needed by published forms.

Business-rule forms require outer publication format `2`. Older loaders reject
that format instead of silently ignoring required rules. Previously authored
format-1 rule forms remain inspectable but cannot execute: republish the draft
as format 2, select the new form version in a pipeline draft, and publish the
pipeline. Existing assignments remain immutable. Forms without rules continue
to publish as format 1. No database migration changes existing form records.

Blocking failed/inconclusive findings and evaluator errors prevent completion.
Nonblocking warnings may be accepted. Accepted corrections, report, review/task
state, and audit summary commit together before workflow resume. Reports carry
exact form/hash/validator, document/extraction/source, and value revision identities.
Read/revalidation reports are ephemeral; gate and final accepted reports are
durable. Audits contain identities/counts rather than raw rule evidence or amounts.

See the [phased R4 plan](../../tasks/tasks-r4-business-validation.md) for integration
status, numeric bounds, and verification evidence.

### Field settings

| Setting | Applies to | Purpose |
| --- | --- | --- |
| `type` | all fields | Selects the kind of value and form control |
| `label` | all fields | Friendly field name shown to the operator |
| `required` | all fields | Requires a value before completion; default is `false` |
| `help` or `description` | all fields | Instruction displayed with the field |
| `readonly` | all fields | Displays the value but prevents editing |
| `default` | all fields | Starting value used when a value is created |
| `multiline` | `string` | Uses a larger text box when `true` |
| `placeholder` | `string` | Shows an entry hint; it is not saved as a value |
| `min_length`, `max_length` | `string` | Limits the number of characters |
| `pattern` | `string` | Requires text to follow a specified pattern |
| `min_value`, `max_value` | numeric fields | Limits the accepted numeric range |
| `step` | numeric fields | Sets the normal increment, such as `0.01` |
| `decimal_places` | numeric fields | Sets the expected number of decimal places for display |
| `format: money` | numeric fields | Displays the value as money |
| `choices` or `enum` | `enum` | Lists the accepted choices |
| `items` | `array` | Defines each repeated item |
| `properties` | `object` | Defines the child fields |

Do not add a restrictive pattern, length, or numeric range unless values that
fall outside it should genuinely prevent an operator from completing review.

### Date values

Field `title` is also accepted as an alias for the displayed label in compatible schema data, but use `label` in new definitions. The server does not reject every unknown setting, so unsupported or misspelled keys may be ignored by the form.

A `date` field requires a value in this order:

```text
YYYY-MM-DD
```

For example, April 5, 2026 is:

```text
2026-04-05
```

Values such as `04-05-2026` or `05/Apr/2026` can appear blank in the browser's
date control even when extraction returned a value. Configure extraction to
return `YYYY-MM-DD`. If that is not possible, use `type: string` or arrange for
the value to be converted before review.

### Text patterns

A pattern is an advanced rule for text such as a policy number. In the Schema
Editor, every string **Pattern** control has an **Example value** and **Test
pattern** button. Test both a value that should pass and one that should fail.

- **Example matches this pattern** means the example will be accepted.
- **Example does not match this pattern** means the pattern is valid but the
  example will be rejected.
- A red syntax message means the pattern itself is invalid.

Pattern examples and test results are not saved in the schema. If your
organization does not already use documented patterns, obtain assistance
before adding one; an incorrect pattern can prevent valid reviews from being
completed.

## Complete Example: Invoice Review Form

This example demonstrates text, dates, choices, yes/no values, numbers, a
simple list, a grouped object, and a repeating table.

```yaml
title: Invoice Review
description: Check invoice details before they are stored.
version: "1.0"
fields:
  invoice_number:
    type: string
    label: Invoice number
    required: true
    placeholder: INV-12345
    help: Enter the number exactly as printed on the invoice.

  invoice_date:
    type: date
    label: Invoice date
    required: true

  document_type:
    type: enum
    label: Document type
    required: true
    choices:
      - label: Invoice
        value: invoice
      - label: Credit note
        value: credit_note
      - label: Receipt
        value: receipt

  purchase_order_present:
    type: boolean
    label: Purchase order shown
    required: false
    help: Select true only when a purchase order number appears on the document.

  invoice_amount:
    type: number
    label: Invoice amount
    required: true
    format: money
    decimal_places: 2
    min_value: 0

  extraction_reference:
    type: string
    label: Processing reference
    readonly: true

  notes:
    type: string
    label: Review notes
    required: false
    multiline: true

  serial_numbers:
    type: array
    label: Serial numbers
    required: false
    items:
      type: string

  supplier:
    type: object
    label: Supplier
    required: false
    properties:
      name:
        type: string
        label: Supplier name
        required: true
      tax_number:
        type: string
        label: Tax number
        required: false

  line_items:
    type: array
    label: Invoice lines
    required: false
    items:
      type: object
      properties:
        description:
          type: string
          label: Description
          required: true
        quantity:
          type: number
          label: Quantity
          required: true
          min_value: 0
        unit_price:
          type: number
          label: Unit price
          required: true
          format: money
          decimal_places: 2
```

Check the example against extraction output: `supplier.name`,
`line_items[].quantity`, and `line_items[].unit_price` must match exactly in
key and nesting. For each line item, verify that `quantity` is the numeric
quantity value and that `unit_price` is the matching per-item amount.

## Advanced Behavior

### Required fields and review routing

When a schema is configured, `required: true` means an operator must supply a
value before completing review. It also identifies fields that are subject to
missing-value and missing-confidence review routing when those review gate
policies are enabled.

Optional fields still appear on the form. A missing optional value or missing
confidence score does not force review by itself. Other workflow rules can
still force review, including field-specific thresholds, split-confidence
rules, business-rule flags, schema validation errors, and an always-review
policy.

For object and array fields, extraction can supply both an overall confidence
and confidence for nested values. A low-confidence cell such as
`line_items[0].quantity` can route the `line_items` group to review while the
form highlights the specific cell. Older extraction records may not contain
this nested confidence information; changing the schema does not add it to
historical records.

### Mapping a structured extraction object

Extraction and review schemas use different type names. Administrators who
maintain both configurations must align the top-level key, child keys, and
value types.

An extraction configuration might define:

```yaml
summary:
  alias: Summary
  type: "Dict[str, Any]"
  object_fields:
    customer_name:
      alias: Customer name
      type: str
    invoice_count:
      alias: Invoice count
      type: int
    total_amount:
      alias: Total amount
      type: float
    approved:
      alias: Approved
      type: bool
```

The matching review schema is:

```yaml
fields:
  summary:
    type: object
    label: Summary
    properties:
      customer_name:
        type: string
        label: Customer name
      invoice_count:
        type: integer
        label: Invoice count
      total_amount:
        type: number
        label: Total amount
      approved:
        type: boolean
        label: Approved
```

Review schemas are not generated automatically from extraction fields. Update
both configurations when their shared structure changes.

## Advanced Validation

For common config-check findings, see [Config Check Troubleshooting](../it-support/config-check-troubleshooting.md). The complete review-gate parameter list is in [review gate reference](tasks/review-gate.md#reviewreview_gate).

The Review Form Editor is the primary validation method for administrators. A
terminal user can validate a stored draft/version without changing SQLite:

```powershell
.\.venv\Scripts\python.exe -m tools.config_check validate --config config.yaml --review-schema invoice --draft
.\.venv\Scripts\python.exe -m tools.config_check validate --config config.yaml --review-schema invoice --version 2
.\.venv\Scripts\python.exe -m tools.config_check validate-file --file .\schemas\invoice.yaml --kind review-schema
```

Exit codes are `0` for a clean result, `1` for errors, `2` for warning-only
results, and `64` for command usage or configuration requirements. Stored
`--review-schema` checks require `database.path` in the selected config. A
`validate-file --kind review-schema` run reports schema findings as errors, so
exit code `2` does not describe those findings.

### Maintainer-only test commands

The following automated tests are for application maintainers, not routine
schema administration. Stored selectors require `database.path` in
`config.yaml`; see [Config Check Troubleshooting](../it-support/config-check-troubleshooting.md).

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\services\test_schema_service.py test\standard_step\review\test_review_gate.py
```

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\visual\test_schema_review_visual.py
```
