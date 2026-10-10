# Manage review forms

| Item | Value |
| --- | --- |
| Audience | Application administrators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

A review form controls what operators see, correct and confirm after extraction.
It defines labels, controls, required values and checks. It does not tell the
extraction task what to read. Configure extraction separately, using the same
field keys and grouping. A **key** connects a value between steps; a **label**
is the friendly wording an operator sees.

This guide builds an invoice form as a worked example. Use your document's
actual fields; do not add invoice fields to unrelated document types.

Go directly to [create a form](#create-and-publish-a-form),
[field types and limits](#choose-the-control-and-its-limits),
[grouped and repeating examples](#field-controls-and-repeating-groups),
[review routing](#connect-the-form-and-configure-review-routing), or
[troubleshooting](#import-export-and-troubleshooting).

## Plan the form before opening the editor

List the values your process needs, their matching extraction keys, which can
legitimately be absent, and what an operator should check. Decide whether a
value is text, a number, a date, a fixed choice, a group or repeating rows.
Agree the output requirements with the people receiving the results.

Use text for reference numbers, postal codes and account numbers, even if they
contain only digits: a numeric control can lose leading zeros. Require a value
only when an operator can and must supply it for every applicable document.
Avoid a required, read-only field that extraction might leave blank; operators
cannot correct that situation to complete review.

Keep template keys and field keys distinct. `invoice-review` identifies the
whole form; `invoice_number` identifies a value. The form's stable key cannot
be used to connect individual fields.

## Create and publish a form

1. Sign in as **admin**, select **Review Forms**, then **New Review Form**.
2. Enter the **Stable key** `invoice-review` and **Review form name**
   `Invoice review`. If the key exists, choose a different key. Stable keys start
   with a letter and use lowercase letters, numbers and hyphens.
3. Set **Title** to `Check invoice details`. Add a **Description** such as
   `Check the supplier, invoice reference, date, total and every line against the PDF.`
4. Add and configure fields using the procedures below. Replace every temporary
   field key. **Find a field** and the field outline help navigate large forms.
5. Select **Save draft**, then **Validate**. Selecting **Validate** with unsaved
   edits saves them first. Read every finding and select a finding to reach its
   control. Correct errors, save and validate again.
6. Select **Publish**. Confirm the new numbered version under **Version history
   & dependencies**. The first publication creates version 1. Set **Lifecycle**
   to **Active** when ready; a form must be published before activation.
7. Open the intended pipeline draft, select **Review Gate**, then select this
   exact **Published review form version**. Save, validate and publish the
   pipeline. [Configure the gate](#connect-the-form-and-configure-review-routing)
   before routine use.
8. Submit approved test PDFs through that pipeline and inspect the complete
   operator form, including row controls and validation messages.

Publishing the form alone does not connect it to a pipeline. Editing its draft
does not change a published version or a document already accepted.

## Add and configure one field

Select **String**, **Number**, **Boolean**, **Enum**, **Object** or **Array** to
add a top-level field. Expand the new field's card. For a type absent from the
toolbar, add a field and change its **Type** list.

| Setting | How to choose it |
| --- | --- |
| **Key** | Copy the extraction key exactly, including letter case, underscores and its parent group. `invoice_number` and `Invoice_Number` are different keys. |
| **Label** | Use recognisable wording such as `Invoice number`. Labels can change without renaming the key. |
| **Type** | Match the kind of extracted value using the table below. |
| **Required** | Select only when a blank must prevent completion. It also affects missing-field review routing. |
| **Read only** | Select only when operators must not correct this value. Leave clear for ordinary extracted values. |
| **Help** | Explain the check, for example `Use the invoice reference, not the purchase order number.` |
| **Default** | A starting value when the form creates a value. Leave blank for facts that must come from the PDF; an invented default can disguise missing information. |
| **Move up / Move down** | Put related checks together. Moves apply among fields at the same level. |
| **Delete field** | Confirm removal from the draft. This does not remove the field from extraction or old published versions. |

### Choose the control and its limits

| Type shown in the Type list | Suitable use and additional controls |
| --- | --- |
| `string` | References, names, addresses. **Multiline** gives a larger box. **Placeholder** is a hint, not a saved value. **Min length** and **Max length** limit characters. |
| `number` or `float` | Decimal amounts and measurements. **Min value**, **Max value**, **Step**, **Decimal places** and **Format** configure the control. |
| `integer` | Whole-number quantities and counts. Avoid this for identifiers. |
| `boolean` | Yes/no information. The operator can distinguish true, false and missing; do not default to false when absence means unknown. |
| `date` | A calendar date. The saved value must be `YYYY-MM-DD`, for example `2026-10-10`. |
| `datetime` | A date and time. Test with the actual extracted representation and your intended time convention. |
| `enum` | A fixed choice. Enter comma-separated **Choices**, such as `SGD, USD, EUR`. |
| `object` | Related child values, such as a customer name and address. |
| `array` | Repeated text or rows. Choose each item's type in **Items**. |

For money, choose `number`, **Format** `money`, **Step** `0.01` and
**Decimal places** `2`. Confirm the final exports meet the receiver's precision
needs; display settings do not calculate totals or convert currencies. Do not
set a minimum of zero if credit notes or negative adjustments are valid.

For choices with different display wording and saved values, enter
`Approved:approved, Needs follow-up:follow_up, Rejected:rejected`. The word after
the colon is saved. Align choices with extraction's allowed values and the
receiving system; changing a displayed label is different from changing a saved
value. Avoid separators inside individual choices.

**Pattern** is an advanced text-format rule, not a plain-language instruction.
If your organisation needs one, obtain a tested rule from support, enter an
**Example value** and select **Test pattern**. Test both acceptable and rejected
examples, then **Validate**. Avoid enforcing a pattern learned from one PDF
when other suppliers use different reference formats.

## Field controls and repeating groups

### Worked invoice field list

Create these top-level fields. The extraction example in
[Configure extraction](configuring-extraction.md#worked-example-invoice-fields)
uses the same keys.

| Add button / Type | Key | Label | Required and advice |
| --- | --- | --- | --- |
| **String** / `string` | `invoice_number` | Invoice number | Required; help: `Check the invoice reference, including leading zeros.` |
| **String**, then `date` | `invoice_date` | Invoice date | Required; arrange date normalization in extraction or test that its result already uses `YYYY-MM-DD`. |
| **Enum** / `enum` | `currency` | Currency | Required; choices `SGD, USD, EUR` only if these are the complete currencies accepted by your process. |
| **Number** / `number` | `invoice_total` | Invoice total | Required; money display, step `0.01`, two decimal places. |
| **Object** / `object` | `customer` | Billed customer | Add children `name` and `address` as described below. |
| **Array** / `array` | `line_items` | Invoice lines | Set **Items** to `object` and add the columns below. |

Adjust required settings to your process. For example, an invoice without a
printed date must have an agreed handling procedure; making the date required
does not create evidence that is absent from the PDF.

### Group related values

1. Add **Object**, set **Key** to `customer` and **Label** to `Billed customer`.
2. Inside the object select **Add Field**. Set the child's **Key** to `name`,
   **Label** to `Customer name` and **Type** to `string`.
3. Select **Add Field** inside the same object again. Set **Key** to `address`,
   **Label** to `Customer address`, **Type** to `string`, and select **Multiline**.
4. Add help describing which party to check; a billed customer and a delivery
   recipient may differ. Make each child required only if appropriate.

The matching extraction must place `name` and `address` inside `customer`.
A top-level field named `customer_name` is a different arrangement. Write
`name` in the child **Key**, not `customer.name`; the parent supplies the grouping.
Multiline changes the review control's size. It does not instruct extraction
to read additional address lines.

### Add repeating invoice lines

1. Add **Array**, set **Key** to `line_items` and **Label** to `Invoice lines`.
2. Set **Items** to `object`. Child-field buttons appear inside the array.
3. Use **Add Field** inside the array for each column:

| Child key | Type | Label and recommended check |
| --- | --- | --- |
| `line_number` | `string` | Line number; retain printed distinguishing references if present. Leave optional when the document has none. |
| `description` | `string` | Description; enable Multiline for wrapped item text. |
| `quantity` | `number` | Quantity; use integer only if fractional quantities are never valid. |
| `unit_price` | `number` | Unit price; choose money display and the precision your process needs. |

4. Set child **Required** values according to the rules for each row. Do not
   require a printed line number if some suppliers omit it.
5. Test a PDF with several rows and confirm operators can inspect and correct
   each row. Check a table continuing onto another page and legitimate repeated
   rows, not just a single-line invoice.

For a list of serial numbers instead, add an array `serial_numbers` and set
**Items** to `string`. Configure **Item choices** or **Item default** only when
the selected item type needs them. Review forms allow multiple repeating groups;
the extraction step supports only one table of repeated objects. Adding a second
form table does not make extraction populate a second table.

## Connect the form and configure review routing

The **Review Gate** task decides when processing pauses for an operator.
The review form decides what the operator can enter. Put the gate after
extraction and before exports or reference-file updates that need approved values.

1. In **Pipeline**, select the intended draft and its **Review Gate** task.
2. Choose the exact **Published review form version**. Check the form name and
   version number; publishing another form version does not update this choice.
3. Set the controls below. Start local extraction with **Entire document** and
   editable fields. Use **Always require review** during initial acceptance
   testing so that you can inspect the whole form on every test PDF.
4. Select **Save Draft**, **Validate**, then **Publish**. Test using the newly
   published pipeline. Watch folders need their version assignment updated too.

| Gate control | What it means and how to choose it |
| --- | --- |
| **Confidence threshold** | Results below this score need review. The main control is a percentage: start at 80% if suitable, then evaluate actual correction rates. A score is not a guarantee of accuracy. |
| **Field threshold overrides** | Use **Add**, select a field and enter its threshold. These override the document-type and default thresholds. Override inputs use `0`–`1`: `0.95` means 95%. |
| **Document-type thresholds** | Enter the exact document type and a `0`–`1` threshold. Used only when the field has no field override. |
| **Review split confidence levels** | Pause when the preceding cloud split reports a selected high/medium/low level. A split that already failed cannot reach this gate. |
| **Reviewer editing scope** | **Entire document** permits document-wide checking; **Low-confidence fields** focuses review on flagged fields. Select the scope deliberately, independently of routing rules. |
| **Review when confidence is missing** | Keep enabled when an unscored value should be checked. |
| **Review missing required fields** | Keep enabled when absent form-required values should send the document to review. Required values still block completion when blank. |
| **Always require review** | Pauses every document, even when scores and required fields otherwise pass. Useful for acceptance testing or a mandatory human check. |
| **Allow editing high-confidence fields** | Leave enabled when operators must be able to correct values that did not trigger review. |
| **Queue** | Keep `default_review` unless your deployment has an agreed alternative. A queue name does not create a new user role or access policy. |

LiteParse and GLM-OCR supply no numeric field confidence. A following gate sends
every configured field for review using their unscored-result flag. Reducing
the confidence threshold does not make that local output bypass review.
Use **Entire document** when all values and line-item cells need confirmation.
Without a gate, the pipeline can export local output without a human check.

## Change and test a form

Select the form in the left panel and check its identity, **Draft revision** and
**Latest version**. An asterisk indicates unsaved changes. Consult **Version
history & dependencies** before changing keys, types, choices or lifecycle.

| Change | What else to check |
| --- | --- |
| Label, help, order or Multiline | Readability and operator workflow; extraction instructions are separate. |
| Key or parent group | Matching extraction and every dependent export/rule. A renamed key can appear blank. |
| Type or choices | Existing sample values must still display and pass completion checks. |
| Required or Read only | Operators can finish valid documents and correct legitimate errors. |
| New or removed field | Extraction, output and business process agree on whether it exists. |

Save, validate and publish the form, select its new exact version in each
affected pipeline, then publish those pipelines and update watch folders as
needed. Existing documents retain their original pipeline/form versions.

For acceptance, test a normal document, a missing optional value, a missing
required value, an invalid date/choice, long text, several rows and a deliberately
incorrect extracted value. Check required-field messages, corrections, row
count, review completion, and the final CSV/JSON output. Confirm corrected
values reach the output, not merely the on-screen draft. Use approved samples
and keep a short record of the versions and results.

## Import, export and troubleshooting

**Export** downloads the current draft, not necessarily the last published
version. Record what you exported. **Import** replaces draft content and needs
validation, publication and pipeline selection afterward; it does not activate
anything. To create a separate form, use **New Review Form** and import there.
There is no Duplicate button. The **Canonical draft preview** is a display aid;
use Export for a portable file. Imports must be at most 1 MiB.

| Symptom | Admin action |
| --- | --- |
| Field blank or absent | Check the document's pinned pipeline version, the gate's chosen form, exact keys and parent grouping. Adding a form field does not add extraction. |
| Date blank | Check the extracted representation is `YYYY-MM-DD`; configure supported extraction normalization or ask support. |
| Operator cannot correct a field | Check **Read only**, **Reviewer editing scope** and **Allow editing high-confidence fields**. |
| Cannot complete a valid document | Check missing required values, number/text limits, choices and dates. Remove only constraints that your business process does not require. |
| Save draft unavailable | Check missing title, empty/duplicate keys or contradictory minimum and maximum values. Read the editor's findings. |
| New form version not appearing | Publish the form, select that exact version in the pipeline, publish the pipeline and use it for new intake. |
| Stale revision / another admin saved | Record your intended edits, reload the current draft and coordinate changes before reapplying them. |
| A finding names `line_items[].unit_price` | Open `line_items`, then the `unit_price` child. The brackets mean a value in a repeating row. |

## Validation, lifecycle and unsaved work

Validation checks the draft's structure and configured rules; it does not prove
that extraction is accurate or that the operator workflow is usable. Validate
again after edits, then test actual review and final outputs.

The editor warns before discarding unsaved work. **Inactive** and **Active**
are lifecycle settings separate from draft publication. To archive, first make
the form inactive and review its dependencies. **Archived is permanent**:
the form cannot be restored or published again. Already published pipelines
and accepted reviews retain their selected version. Create a new form and
import an exported definition if you need a replacement.

For file-level rules used by support, see the
[schema-format reference](../reference/review-schema-format.md).
