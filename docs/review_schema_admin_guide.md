# Review Schema Admin Guide

This guide explains how administrators configure schema-driven human review fields for the review gate.

Review schemas control how extracted fields appear in the human review UI and how corrected values are validated before a review item is completed. They are separate from the extraction task, but the field keys should match the extraction output keys.

When a review schema is configured, the review gate uses `required: true` to decide which fields are mandatory for confidence gating. Optional fields still appear in the review UI, but a missing value or missing confidence score on an optional field does not force review by itself. Explicit review policies such as `field_threshold_overrides`, split-confidence rules, business-rule flags, schema validation errors, or `always_review` can still force review.

For object, scalar-array, and object-array fields, confidence gating uses the aggregate field confidence persisted by extraction. New LlamaCloud Extract v2 runs compute that aggregate as the minimum nested numeric confidence. For example, a required `line_items` array with one low-confidence `line_items.0.quantity` cell can route the top-level `line_items` field to review while the UI highlights the specific low-confidence cell.

## How Review Schemas Connect to the Pipeline

The review gate task references a schema through `tasks.<review_gate_task>.params.schema_file`.

Example:

```yaml
tasks:
  review_gate:
    module: standard_step.review.review_gate
    class: ReviewGateTask
    params:
      confidence_threshold: 0.90
      schema_file: "schemas/invoice.yaml"
      queue_name: "default_review"
      review_scope: "low_confidence_fields"
      require_review_when_missing_confidence: true
      require_review_for_missing_required_fields: true
      resume_policy: "next_task"
    on_error: stop

pipeline:
  - extract_document_data
  - review_gate
  - store_metadata_json
```

Use a schema file that resolves under a configured schema directory. The runtime schema loader supports `schema.directories`, `schema.dirs`, `schema.directory`, and `schemas.directory`; if none is configured, it defaults to `schemas` relative to the config file. Absolute schema paths and relative paths are accepted only when they resolve under one of those configured directories.

Example schema root configuration:

```yaml
schema:
  directories:
    - "schemas"
```

## Field Keys and Labels

Schema field keys must match the extracted field keys stored by the extraction step.

Example:

```yaml
fields:
  invoice_amount:
    type: float
    label: Invoice amount
```

In this example, `invoice_amount` is the stable key. `label` is only the human-friendly text shown in the UI.

When using a saved LlamaCloud Extract v2 configuration, make sure the returned field keys or aliases map cleanly to the workflow field keys configured in `config.yaml`.

### Mapping Structured Extraction Objects

Extraction task configuration and review schemas use different type syntax.
For a structured extraction object, keep the top-level and child keys aligned
between the two configurations.

Extraction task field:

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
    notes:
      alias: Notes
      type: "Optional[str]"
```

Matching review schema field:

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
      notes:
        type: string
        label: Notes
        required: false
```

The review UI renders each property with its typed control. Review schemas are
not generated automatically from extraction fields, so administrators must
maintain this key and type alignment when either configuration changes.

## Supported Field Types

The review schema supports these field types:

| Type | Review UI behavior | Validation behavior |
| --- | --- | --- |
| `string` | Text input | Value must be text when present |
| `float` | Number input | Value must be numeric |
| `number` | Number input | Value must be numeric |
| `integer` | Number input with integer step | Value must be an integer |
| `boolean` | True/false/missing selector | Value must be true or false when present |
| `date` | Date picker | Value must be a valid ISO date, `YYYY-MM-DD` |
| `datetime` | Date/time input | Value must be a valid ISO datetime |
| `enum` | Select list with scalar or label/value choices | Value must be one of the configured choices |
| `array` | List editor with typed item controls | Value must be an array |
| `object` | Nested editor or JSON editor | Value must be an object |

Additional schema options include:

| Option | Applies to | Purpose |
| --- | --- | --- |
| `label` | all fields | Human-readable field label |
| `required` | all fields | Requires a value before completion and makes the field subject to missing-confidence review gating |
| `description` | all fields | Help text in the review UI |
| `help` | all fields | Help text in the review UI; equivalent to `description` for display |
| `readonly` | all fields | Shows the value but disables editing in review |
| `default` | all fields | Default value used by schema-aware editors when creating values |
| `multiline: true` | `string` | Renders a textarea for long values |
| `placeholder` | `string` | Placeholder text for empty string inputs |
| `choices` or `enum` | `enum` | Allowed values for select fields |
| `items` | `array` | Defines array item type and item-level metadata |
| `properties` | `object` | Defines nested object fields and property-level metadata |
| `min_length`, `max_length`, `pattern` | `string` | Text validation rules |
| `min_value`, `max_value`, `step`, `decimal_places`, `format` | numeric fields | Numeric validation and display rules |

For money-like values, use either `format: money` or `decimal_places: 2`. The review UI will display two decimals and use a `0.01` increment unless a different `step` is configured.

Array `items` may use scalar types (`string`, `number`, `integer`, `float`, `boolean`, `date`, `datetime`, `enum`) or `object`. Scalar items can define the same type-specific options as top-level fields. Object-array item `properties` can define their own numeric, enum, boolean, date, text, required, readonly, default, and help metadata.

When extraction metadata includes nested confidence, the review UI displays an aggregate badge on array/object group headers and per-cell badges for object arrays. Nested details are stored in `source_json.confidence_details`; no review schema changes or database migration are required.

## Date Fields and LlamaCloud Output

For `type: date`, the review UI uses a browser date input. Browser date inputs require ISO date strings:

```text
YYYY-MM-DD
```

For example, April 5, 2026 must be returned as:

```text
2026-04-05
```

If LlamaCloud returns `04-05-2026`, `05/Apr/2026`, or another non-ISO format, the browser date input may display an empty value even though the extracted value exists. Configure LlamaCloud Extract v2 date fields to return `YYYY-MM-DD` when the review schema uses `type: date`.

If the provider cannot guarantee ISO dates, keep the schema field as `type: string` or add a normalization step before human review.

## Example Invoice Review Schema

```yaml
title: Invoice Review
description: Review schema for extracted invoice fields.
version: "1.0"
fields:
  supplier_name:
    type: string
    label: Supplier name
    required: false

  client_name:
    type: string
    label: Client name
    required: false

  client_address:
    type: string
    label: Client
    required: false
    multiline: true

  invoice_amount:
    type: float
    label: Invoice amount
    required: true
    format: money
    decimal_places: 2

  insurance_start_date:
    type: date
    label: Insurance Start date
    required: false

  insurance_end_date:
    type: date
    label: Insurance End date
    required: false

  policy_number:
    type: string
    label: Policy Number
    required: false

  serial_numbers:
    type: array
    label: Serial Numbers
    required: false
    items:
      type: string

  invoice_type:
    type: string
    label: Invoice type
    required: false
```

## Common Mistakes

- `schema_file` points to a missing file.
- Schema field keys do not match extraction field keys.
- A numeric field is configured as `string`, allowing free-text edits.
- A long text field is missing `multiline: true`.
- A date field is configured as `date`, but LlamaCloud returns `MM-DD-YYYY`, `DD/MMM/YYYY`, or another non-ISO format.
- `required: true` is used on optional business data, causing missing values or missing confidence to route documents to review.
- A saved LlamaCloud configuration returns aliases that do not map to the workflow field keys.
- Older extraction records created before nested confidence persistence may still show missing array/object confidence because historical data is not backfilled automatically.

## Validation

The Schema Editor validates draft structure before saving. Invalid regular
expressions, contradictory minimum/maximum constraints, duplicate or empty
field keys, and missing schema metadata are shown as linked findings. Selecting
a finding moves focus to the affected control. Save remains disabled until the
draft is valid, while Validate stays available to refresh the full result.

The editor warns before discarding unsaved changes when switching schemas,
starting a new schema, duplicating, navigating away, or closing the page. Long
schemas include a field outline for direct navigation. At narrower widths the
schema list, editor, and YAML preview reflow instead of requiring page-level
horizontal scrolling.

Validation findings appear above the YAML preview with an error count and the
affected field path. Select a finding to move focus to its field. Object-array
paths use the compact form `line_items[].unit_price` so nested fields remain
easy to identify.

### Testing a string pattern

Every string Pattern control includes an Example value and **Test pattern**
button. Enter a representative extracted value and run the test before saving:

- **Example matches this pattern** confirms that the expression compiles and
  accepts the example.
- **Example does not match this pattern** means the expression is valid but the
  example would fail review validation.
- A red syntax message means the regular expression does not compile; Save is
  disabled until the pattern is corrected.

Pattern tests run on the server with the same Python regular-expression
semantics used during review validation. Example values and test results are
editor aids only and are not written into the schema file.

After changing `config.yaml` or schema files, run:

```powershell
.\.venv\Scripts\python.exe -m tools.config_check validate --config config.yaml --import-checks
```

To validate schema behavior through tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\services\test_schema_service.py test\standard_step\review\test_review_gate.py
```

To run the schema-driven review and schema-editor visual checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\visual\test_schema_review_visual.py
```
