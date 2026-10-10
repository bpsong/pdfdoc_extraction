# Review schema format and validation

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
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
   1 MiB. If `format_version` is present, it must be `1`.
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

The Review Form Editor displays authoritative version history. An exported draft includes its revision, not a published version number. A version label inside imported content does not select or overwrite an SQLite version. Field keys and settings are not comprehensively allowlisted by server validation; unknown or misspelled settings may be carried through without being applied.

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
