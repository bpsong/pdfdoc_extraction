# Review Schema Admin Guide

This guide explains how administrators configure schema-driven human review fields for the review gate.

Review schemas control how extracted fields appear in the human review UI and how corrected values are validated before a review item is completed. They are separate from the extraction task, but the field keys should match the extraction output keys.

When a review schema is configured, the review gate uses `required: true` to decide which fields are mandatory for confidence gating. Optional fields still appear in the review UI, but a missing value or missing confidence score on an optional field does not force review by itself. Explicit review policies such as `field_threshold_overrides`, split-confidence rules, business-rule flags, schema validation errors, or `always_review` can still force review.

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

Use a path that exists from the project root when running config validation. The runtime schema loader also supports schema files stored under the configured schema directory, which defaults to `schemas`.

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

## Supported Field Types

The review schema supports these field types:

| Type | Review UI behavior | Validation behavior |
| --- | --- | --- |
| `string` | Text input | Value must be text when present |
| `float` | Number input | Value must be numeric |
| `number` | Number input | Value must be numeric |
| `integer` | Number input with integer step | Value must be an integer |
| `boolean` | Checkbox | Value must be true or false |
| `date` | Date picker | Browser expects `YYYY-MM-DD` |
| `datetime` | Date/time input | Browser expects date-time compatible input |
| `enum` | Select list | Value must be one of the configured choices |
| `array` | List editor | Value must be an array |
| `object` | Nested editor or JSON editor | Value must be an object |

Additional schema options include:

| Option | Applies to | Purpose |
| --- | --- | --- |
| `label` | all fields | Human-readable field label |
| `required` | all fields | Requires a value before completion and makes the field subject to missing-confidence review gating |
| `description` | all fields | Help text in the review UI |
| `multiline: true` | `string` | Renders a textarea for long values |
| `choices` or `enum` | `enum` | Allowed values for select fields |
| `items` | `array` | Defines array item type |
| `properties` | `object` | Defines nested object fields |
| `min_length`, `max_length`, `pattern` | `string` | Text validation rules |
| `min_value`, `max_value` | numeric fields | Numeric validation rules |

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

## Validation

After changing `config.yaml` or schema files, run:

```powershell
C:\Python313\python.exe -m tools.config_check --verbose validate --config config.yaml
```

To validate schema behavior through tests:

```powershell
C:\Python313\python.exe -m pytest -v test\services\test_schema_service.py test\standard_step\review\test_review_gate.py
```
