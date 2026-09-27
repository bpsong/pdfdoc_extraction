# Review Schema Administrator Guide

This guide explains how an application administrator creates and maintains the
form that operators use to check extracted document data in the **Review
Queue**. SQLite stores the editable draft and immutable published versions.
Use the **Review Form Editor** at `/app/schemas` for routine authoring. YAML or
JSON is for import, export, and legacy migration.

Use the Review Form Editor for routine changes. It shows the available settings,
checks the schema before saving, and reduces the risk of formatting errors.
Direct file editing does not change runtime behavior. Import creates or updates
a draft; an administrator must validate and publish it, then select that exact
published schema version in a pipeline draft and publish a new pipeline
version.

> **Critical:** A published review form has no effect until a pipeline draft
> selects its exact `schema_version_id` and that pipeline is published. Existing
> pipeline versions keep their existing review-form version.

## Contents

**Terminology:** This guide primarily uses **review form** for the
administrator-managed template and its published versions. “Review schema”
names the portable data format or an API/configuration term.

- [What a Review Schema Controls](#what-a-review-schema-controls)
- [Before You Begin](#before-you-begin)
- [Authoring: Use the Review Form Editor](#authoring-use-the-review-form-editor)
- [Import, Export, and Legacy Migration](#import-export-and-legacy-migration)
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

## Authoring: Use the Review Form Editor

### Open the editor

1. Start the application and sign in as an administrator.
2. Open `/app/schemas`, or select **Review Forms** from the
   administrator navigation.
3. Select an existing schema template from the list, or select **New Review
   Form**.

The page contains three areas:

- **Review Forms** lists forms and lifecycle/version information.
- The center panel contains draft metadata and fields.
- **Version history & dependencies** shows validation findings, published
  versions, and pipeline dependencies. Expand **Canonical draft preview** to
  inspect a YAML-like rendering. It is generated for display and may not quote
  every special character as valid YAML; export the draft when you need a
  portable file.

### Create a schema

1. Select **New Review Form**.
2. In the creation dialog, enter a unique stable key and a review form name.
   Keys use lowercase hyphen-separated words, start with a letter, and may
   contain numbers (for example, `invoice-review`). The dialog starts with
   `new-review-form`; change it when that key is already in use.
3. Enter a clear **Title**, such as `Invoice Review`.
4. Enter a short **Description** explaining when the form is used.
5. Add and configure the fields as described below.
6. Select **Validate**.
7. Correct every reported error. Selecting an error moves to the affected
   control.
8. Select **Save draft**. Saving does not make the schema available to a
   pipeline.
9. Select **Publish** after validation. Publication creates immutable version
   1; later publications increment that template's version number.

The application will not overwrite another template with the same key. The
editor also offers **Find a field** and a clickable field outline to navigate
large forms. The form URL can be bookmarked as `/app/schemas/{schema_name}`.

### Edit an existing schema

1. Select the schema from the left panel. Use **Search schemas** if the list is
   long. The form identity includes its stable key, **Review form name**, title,
   and the **Lifecycle** control. The editor also shows **Draft revision** and
   **Latest version** so you can confirm which revision you are changing.
2. Confirm the stable key, display name, and title before changing anything.
3. Change the metadata or fields. An asterisk beside the schema title indicates
   that the draft has unsaved changes.
4. Select **Validate** and resolve all findings.
5. Select **Save draft**, validate, and publish a new immutable version.
6. Select that exact schema version in the relevant pipeline draft, validate
   and publish a new pipeline version.
7. Test the resulting form with a representative document.

Published content is immutable. Editing always changes the draft, not an
existing version. To create a separate template, select **New Review Form** and
import an exported definition into its new draft; no Duplicate action is
available.

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

Use field keys that match the extraction result exactly. Lowercase letters,
numbers, and underscores are a convention, not a server-enforced format. The
server does not validate field-key syntax or duplicate nested keys; duplicate
YAML keys can silently overwrite earlier values when parsed. Check spelling,
case, and nesting carefully. The template stable key has a stricter enforced
lowercase-hyphen format, which is separate from field keys.

Review schemas can contain multiple arrays of objects. This differs from an
extraction task's field configuration, which supports at most one
`List[Any]` table field. The extraction pipeline editor explains and enforces
that task-specific limit; it does not limit arrays in the Review Form Editor.

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

### Validate, save, publish, import, export, and change lifecycle

- **Validate** saves unsaved draft changes first, then validates that saved
  revision.
- **Save draft** persists editable content in SQLite.
- **Publish** repeats validation and creates the next immutable version.
- **Import** accepts a portable YAML/JSON definition into a draft; it never
  publishes automatically.
- **Export** downloads the current draft as a portable, redacted definition.
  It includes a draft `revision`, not a published version number or database UUID.
- **Lifecycle** offers **Inactive**, **Active**, and **Archived**. A form needs
  a published version before activation. Only an inactive form can be archived;
  archived is terminal and cannot be restored or published. Draft saves may
  still be accepted, but do not make an archived form usable.

The editor disables Save for its client-side blocking findings: a missing
stable key or title, empty or duplicate field keys detected in the editor, or
minimum values greater than maximum values. These client checks are not all
server validation rules. A malformed pattern does not itself disable Save; use
**Test pattern** or run server-side **Validate** to surface pattern problems.

The server does not require a schema `title`, and field keys are not covered by
a strict allowlist. Unknown field settings may pass through without a useful
validation error, so review spelling carefully. Field `title` can act as a
label alias; prefer `label` for clarity.

The editor warns before discarding unsaved changes when you select another
schema, create a schema, follow another link, refresh, or close the page.

Before deactivating or archiving a template, inspect its dependencies. Published
pipeline versions and in-progress reviews retain access to the exact immutable
schema version they already reference.

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

## Connect the Schema to the Review Gate

Creating or publishing a schema does not automatically assign it to a workflow. This is the required activation step for a review form. In the pipeline draft, select the exact published schema version for the review
gate. The persisted dependency and runtime parameter use `schema_version_id`.

```yaml
tasks:
  review_gate:
    module: standard_step.review.review_gate
    class: ReviewGateTask
    params:
      confidence_threshold: 0.90
      schema_version_id: "selected-by-the-admin-editor"
      queue_name: "default_review"
      review_scope: "low_confidence_fields"
      require_review_when_missing_confidence: true
      require_review_for_missing_required_fields: true
      resume_policy: "next_task"
    on_error: stop
```

Select only a published version belonging to an active schema template, then
validate and publish the pipeline draft. Existing pipeline versions and review
resumes keep their prior schema version when a newer schema is published.

Other supported review-gate parameters include `per_document_type_thresholds`,
`field_threshold_overrides`, `split_confidence_levels_requiring_review`,
`always_review`, `allow_operator_to_edit_high_confidence_fields`, and
`require_review_when_missing_confidence`. `resume_policy` currently accepts only
`next_task`; it is not exposed as an editor choice. `schema_file` is legacy
migration input and is rejected for a current pipeline definition. See the
[user guide, section 4.8](user_guide.md#48-task-system-standard-steps-and-parameters)
for the full parameter descriptions.

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
real review than in the Review Form Editor. The application documents no fixed
field-count, nesting-depth, or label-length cap; the 1 MiB import limit is the
practical boundary for portable files. When validation findings contain a field
key including `api_key`, `password`, `secret`, `token`, or `credential`, that
key may be replaced with `[REDACTED]` in the response.

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
key and type changes with the extraction configuration owner. They also do not
update existing pipeline versions: publish the schema, select it in a pipeline
draft, and publish a new pipeline version.

## Troubleshooting

| Symptom | Check and action |
| --- | --- |
| A field does not appear | Confirm that the field is under `fields:` or the correct nested `properties:`, then validate and save. |
| A field appears but its extracted value is blank | Confirm that its key, letter case, nesting, and type match the extraction result. |
| A date appears blank | Confirm that the extracted value uses `YYYY-MM-DD`. |
| **Save** is unavailable | Read the validation findings and correct every blocking error. |
| An operator cannot edit a field | Clear **Read only** unless editing is intentionally prohibited. |
| A document enters review unexpectedly | Check required fields and the review gate's confidence and business rules. Optional fields can still appear without being required. |
| A new schema is not used | Confirm that it was published, that the exact version is selected in the pipeline draft, and that a new pipeline version was published. |
| An imported schema is missing | Confirm the import succeeded into the intended draft and that the template is not archived. |
| Import is rejected | Keep the file at or below 1 MiB and use `format_version: 1` when specifying a format version. |
| Validation reports a path such as `line_items[].unit_price` | Open that nested field. `[]` means the problem applies to an item in a repeating array. |
| Direct editing caused the schema to stop loading | Restore the backup, then check YAML indentation, tabs, repeated keys, and unquoted special characters. |
| Another administrator saved while I was editing | Drafts use revision checks. A stale save or publish is rejected; reload the current draft before continuing, and coordinate edits to avoid losing unsaved browser work. |
| My export contains `revision`, not a version number | Export downloads the current draft. Publish it to create an immutable version, then use version history to confirm its number. |
| I cannot publish an archived form | Archived forms are terminal and cannot be restored. Create a new form and import the archived form’s exported definition. |

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

For common config-check findings, see [Config Check Troubleshooting](config_check_troubleshooting.md). The complete review-gate parameter list is in [the user guide, section 4.8](user_guide.md#48-task-system-standard-steps-and-parameters).

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
`config.yaml`; see [Config Check Troubleshooting](config_check_troubleshooting.md).

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\services\test_schema_service.py test\standard_step\review\test_review_gate.py
```

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\visual\test_schema_review_visual.py
```
