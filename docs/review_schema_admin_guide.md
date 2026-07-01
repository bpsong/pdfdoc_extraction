# Review Schema Administrator Guide

This guide explains how an application administrator creates and maintains the
form that operators use to check extracted document data in the **Review
Queue**. You can use either:

- the **Schema Editor** at `http://localhost:8000/app/schemas`; or
- a plain-text editor to create or change a schema file directly.

Use the Schema Editor for routine changes. It shows the available settings,
checks the schema before saving, and reduces the risk of formatting errors.
Direct file editing is useful for copying a known schema, making several
changes at once, or maintaining configuration through an established
administrative process.

## Contents

- [What a Review Schema Controls](#what-a-review-schema-controls)
- [Before You Begin](#before-you-begin)
- [Method 1: Use the Schema Editor](#method-1-use-the-schema-editor)
- [Method 2: Create or Edit a Schema File Directly](#method-2-create-or-edit-a-schema-file-directly)
- [Schema File Reference](#schema-file-reference)
- [Complete Example: Invoice Review Form](#complete-example-invoice-review-form)
- [Connect the Schema to the Review Gate](#connect-the-schema-to-the-review-gate)
- [Test the Operator's Form](#test-the-operators-form)
- [Safely Change an Existing Schema](#safely-change-an-existing-schema)
- [Troubleshooting](#troubleshooting)
- [Advanced Behavior](#advanced-behavior)
- [Advanced Validation](#advanced-validation)

## What a Review Schema Controls

A review schema controls:

- which extracted fields appear on the operator's review form;
- the label and help text shown for each field;
- whether a value is required or read only;
- which control is used, such as text, number, date, choice, or list; and
- which values the application accepts when the operator completes review.

A review schema does **not** tell the extraction service what to extract. The
extraction configuration and review schema are separate. Their field keys must
match so that the form can display the extracted values.

For example, the extraction result may contain an internal key named
`invoice_amount`. The review form can display the friendlier label **Invoice
amount**, but its key must remain `invoice_amount`.

```yaml
fields:
  invoice_amount:
    type: number
    label: Invoice amount
```

> **Important:** Changing a label is normally safe. Changing a key can break
> the connection to extracted data and make a value appear blank.

## Before You Begin

Before creating or changing a schema:

1. Sign in with an administrator account.
2. Identify the review gate and schema used by the document workflow.
3. Obtain the field keys produced by the extraction step. If you do not manage
   extraction configuration, ask the person who does for this list.
4. Decide which fields operators need to see and which are genuinely required.
5. Use a representative non-production PDF for the final test.

Avoid changing a production schema while operators are actively reviewing
documents that use it. Complete the change, validate it, and test the form
before asking operators to continue.

## Method 1: Use the Schema Editor

### Open the editor

1. Start the application and sign in as an administrator.
2. Open `http://localhost:8000/app/schemas`, or select **Schemas** from the
   administrator navigation.
3. Select an existing schema from the left panel, or select **New Schema**.

The page contains three areas:

- **Schemas** lists the available schema files and provides a search box.
- The center panel contains the schema name, description, and fields.
- **YAML Preview** shows the current draft in YAML form. The preview is read
  only; use the center-panel controls to make changes. When the selected file
  ends in `.json`, the application saves the equivalent JSON content.

### Create a schema

1. Select **New Schema**.
2. In **Name**, enter a unique file name ending in `.yaml`, `.yml`, or `.json`,
   such as `invoice.yaml`. YAML is recommended for files maintained by people.
3. Enter a clear **Title**, such as `Invoice Review`.
4. Enter a short **Description** explaining when the form is used.
5. Add and configure the fields as described below.
6. Select **Validate**.
7. Correct every reported error. Selecting an error moves to the affected
   control.
8. Select **Save**. A confirmation message appears when the schema is saved.

The application will not overwrite another schema when creating a new one. If
the name is already in use, choose a different name or edit the existing
schema.

### Edit an existing schema

1. Select the schema from the left panel. Use **Search schemas** if the list is
   long.
2. Confirm the file name and title before changing anything.
3. Change the metadata or fields. An asterisk beside the schema title indicates
   that the draft has unsaved changes.
4. Select **Validate** and resolve all findings.
5. Select **Save**.
6. Test the resulting form with a representative document.

The **Name** control identifies a new schema while it is being created. Saving
changes to an existing schema updates the selected file; it does not rename
that file. To create a similar schema with another name, use **Duplicate**.

### Add and configure a field

Use one of the field buttons, such as **String**, **Number**, **Boolean**,
**Enum**, **Object**, or **Array**, to add a top-level field. The new field has
a temporary key; replace it with the exact extraction key.

Each field has these main settings:

| Editor setting | Meaning for the administrator and operator |
| --- | --- |
| **Key** | Internal name that connects the form to extracted data. It must exactly match the extraction key, including underscores and letter case. |
| **Label** | Friendly name displayed to the operator. Changing it does not change the extraction key. |
| **Type** | Determines the form control and the values that are accepted. |
| **Required** | Prevents review completion when the value is blank. It can also cause missing data or confidence to be sent for review. |
| **Read only** | Displays the value but prevents the operator from correcting it. Use this only when correction is intentionally prohibited. |
| **Help** | Short instruction displayed with the field. Explain what the operator should check or enter. |
| **Default** | Starting value used when the form needs to create a value. It does not repair missing extraction configuration. |
| **Move up / Move down** | Changes the field's position among fields at the same level. Nested fields remain inside their current object or array. |
| **Delete field** | Opens a confirmation before removing the field from the draft form. The change is not permanent until the schema is saved. |

The add-field toolbar contains the most common types. To use `integer`,
`float`, `date`, or `datetime`, add a field first and then select the required
value from its **Type** list.

Use simple keys made from lowercase letters, numbers, and underscores, for
example `policy_number` or `invoice_date`. Do not use the label as the key
unless it is also the exact key returned by extraction.

Review schemas can contain multiple arrays of objects. This differs from an
extraction task's field configuration, which supports at most one
`List[Any]` table field. The extraction pipeline editor explains and enforces
that task-specific limit; it does not limit arrays in this Schema Editor.

### Choose the right field type

| Type | Use it for | What the operator sees |
| --- | --- | --- |
| `string` | Names, references, addresses, and other text | A text box, or a larger box when **Multiline** is selected |
| `number` or `float` | Amounts, rates, measurements, or decimal values | A number box |
| `integer` | Whole numbers such as quantity or page count | A whole-number box |
| `boolean` | A yes/no or true/false value | A true, false, or missing selector |
| `date` | A calendar date without a time | A date picker; the stored value must use `YYYY-MM-DD` |
| `datetime` | A date and time | A date-and-time control |
| `enum` | One value chosen from a fixed list | A selection list |
| `array` | A repeatable list, such as serial numbers or invoice lines | A list editor |
| `object` | A group of related fields, such as customer details | A nested group of controls |

For money, use `number` or `float`, select the `money` format, and normally set
**Decimal places** to `2`. Use **Min value** and **Max value** only when values
outside that range are always invalid.

For an `enum`, enter choices separated by commas. For example:

```text
Invoice, Credit note, Receipt
```

When the stored value and displayed wording should differ, use
`Label:value`. For example:

```text
Approved:approved, Needs follow-up:follow_up, Rejected:rejected
```

### Add grouped or repeating fields

Use an `object` when several child fields belong together:

1. Add an **Object** field.
2. Set its key and label.
3. Use **Add Field**, **Add Object**, or **Add Array** inside that object.
4. Configure each child key so it matches the corresponding child key in the
   extracted data.

Use an `array` for a repeatable list:

1. Add an **Array** field.
2. Set its key and label.
3. In **Items**, select the type of each list item.
4. If **Items** is `object`, add the columns as child fields inside the array.

For example, a `serial_numbers` array contains repeated text values, while a
`line_items` array normally contains objects with child fields such as
`description`, `quantity`, and `unit_price`.

### Validate, save, and duplicate

- **Validate** checks the current draft without saving it.
- **Save** validates again and then writes the schema file.
- **Duplicate** copies the selected saved schema under a new file name. Use it
  when a new document type is similar to an existing one.

Save remains unavailable while the editor detects a blocking error. Common
errors include a missing title, an empty or duplicate key, an invalid file
extension, an invalid text pattern, or minimum and maximum values that
contradict each other.

The editor warns before discarding unsaved changes when you select another
schema, create or duplicate a schema, follow another link, refresh, or close
the page.

The editor can delete fields but does not provide a button to delete an entire
schema file. Remove a schema file only through your approved file-management
process, and first confirm that no review gate refers to it.

## Method 2: Create or Edit a Schema File Directly

Review schemas are stored as YAML or JSON files. Unless the application is
configured differently, they are in the `schemas` folder beside `config.yaml`.
YAML examples in this guide use spaces to show which settings belong together.

### Find the schema file in use

The review gate identifies its schema with `schema_file` in `config.yaml`:

```yaml
tasks:
  review_gate:
    module: standard_step.review.review_gate
    class: ReviewGateTask
    params:
      schema_file: "schemas/invoice.yaml"
```

In this example, edit `schemas\invoice.yaml`. Do not assume that every schema
shown in the Schema Editor is currently used by a workflow.

The schema folders can be configured explicitly:

```yaml
schema:
  directories:
    - "schemas"
```

Relative folder names are resolved from the folder containing `config.yaml`.
If several schema folders are configured, the Schema Editor saves new schemas
in the first folder. Ask the application owner before changing these folders.

### Safe direct-editing procedure

1. Confirm the exact schema file referenced by the review gate.
2. Copy the file to a backup name outside the active schema folders. A backup
   ending in `.yaml`, `.yml`, or `.json` inside an active schema folder will
   also appear as a selectable schema.
3. Open the active file in a plain-text editor.
4. Make the required changes. Use spaces, not tabs, for indentation.
5. Save the file as UTF-8 text and keep its existing `.yaml`, `.yml`, or
   `.json` extension.
6. Open or refresh `/app/schemas`, select the file, and choose **Validate**.
7. Correct all findings and save the file again if necessary.
8. Test a representative document in the Review Queue.

If the file does not appear in the Schema Editor, check its folder and file
extension. If the editor cannot load it after a change, restore the backup and
validate the restored file.

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
| `title` | Yes | Friendly name of the schema |
| `description` | Recommended | Short explanation of when the form is used |
| `version` | Recommended | Administrator-controlled version label, such as `"1.1"` |
| `fields` | Yes | Collection of fields displayed on the review form |

The Schema Editor preserves a version already present in a file, but it does
not provide a separate Version control. Change `version` through direct file
editing when your administrative process requires it.

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

The extraction result must use the same structure: for example,
`supplier.name`, `line_items[].quantity`, and `line_items[].unit_price` must
correspond to the schema's child keys.

## Connect the Schema to the Review Gate

Creating a schema does not automatically assign it to a workflow. The review
gate must reference the file through `schema_file`.

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
```

If you use the application's pipeline administration page, select the schema
file in the review gate settings and validate the pipeline. If you edit
`config.yaml` directly, preserve its indentation and run the configuration
check described under Advanced Validation.

## Test the Operator's Form

Validation proves that the schema is structurally acceptable; it does not
prove that the form matches real documents. After every material change:

1. Process a representative non-production PDF through the workflow.
2. Open the item in **Review Queue**.
3. Confirm that every expected field appears in the intended order.
4. Confirm that labels and help text are understandable to an operator.
5. Check that extracted values appear under the correct fields.
6. Try correcting text, numeric, date, choice, list, and nested values as
   applicable.
7. Confirm that genuinely required fields prevent completion when blank.
8. Confirm that optional fields can remain blank.
9. Complete the review and verify the corrected result reaches the expected
   downstream output.

If possible, ask an operator who did not design the schema to perform this
test. Confusing wording and missing instructions are easier to detect during a
real review than in the Schema Editor.

## Safely Change an Existing Schema

Consider the effect on extraction and active reviews before changing a schema:

| Change | Likely effect |
| --- | --- |
| Change a label or help text | Changes operator wording without changing the extracted key |
| Rename a key | Existing extracted data under the old key may appear missing |
| Change a type | Existing values may no longer display correctly or pass validation |
| Select **Required** | Blank values prevent completion and may route more documents to review |
| Select **Read only** | Operators can no longer correct the value |
| Remove a field | It disappears from the form; extraction configuration is not changed |
| Add a field | It appears on the form, but remains blank unless extraction supplies the matching key or a value is otherwise created |
| Change choices or limits | Previously accepted values may fail validation |

Schema changes do not automatically update the extraction provider, convert
historical values, or recalculate historical confidence information. Coordinate
key and type changes with the extraction configuration owner.

## Troubleshooting

| Symptom | Check and action |
| --- | --- |
| A field does not appear | Confirm that the field is under `fields:` or the correct nested `properties:`, then validate and save. |
| A field appears but its extracted value is blank | Confirm that its key, letter case, nesting, and type match the extraction result. |
| A date appears blank | Confirm that the extracted value uses `YYYY-MM-DD`. |
| **Save** is unavailable | Read the validation findings and correct every blocking error. |
| An operator cannot edit a field | Clear **Read only** unless editing is intentionally prohibited. |
| A document enters review unexpectedly | Check required fields and the review gate's confidence and business rules. Optional fields can still appear without being required. |
| A new schema is not used | Confirm that the review gate's `schema_file` points to the new file and that the pipeline change was saved. |
| A schema is missing from the list | Confirm that it is in a configured schema folder and ends in `.yaml`, `.yml`, or `.json`; then refresh the page. |
| Validation reports a path such as `line_items[].unit_price` | Open that nested field. `[]` means the problem applies to an item in a repeating array. |
| Direct editing caused the schema to stop loading | Restore the backup, then check YAML indentation, tabs, repeated keys, and unquoted special characters. |

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

The Schema Editor is the primary validation method for administrators. After
changing `config.yaml` or schema files directly, an administrator who has
terminal access can also run the application configuration check from the
repository root:

```powershell
.\.venv\Scripts\python.exe -m tools.config_check validate --config config.yaml --import-checks
```

Exit code `2` means that validation completed with warnings only. Review the
warnings and decide whether they apply before using the workflow.

The following automated tests are intended for application maintainers, not
for routine schema administration:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\services\test_schema_service.py test\standard_step\review\test_review_gate.py
```

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\visual\test_schema_review_visual.py
```
