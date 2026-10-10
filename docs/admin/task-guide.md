# Choose and configure pipeline tasks

| Item | Value |
| --- | --- |
| Audience | Application administrators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

A task is one processing operation. This guide covers every currently approved
built-in task, what you need to configure, and where it belongs. Use **Task
Catalog** to check availability on your deployment, then **Pipeline** to add
and configure tasks in a draft. A task can be approved but unavailable because
a required software package is missing; **Importable** checks whether the app
can load it, not whether its provider connection works.

The names below are the catalog's generated labels. An existing pipeline may
give the same task a friendlier **Label**, such as `Extract document data`.
The short identifiers in the second column help distinguish tasks and report
issues to support; you do not need to enter program names or edit code.

Go directly to [all built-in tasks](#available-built-in-tasks),
[task ordering](#order-tasks-around-the-business-outcome),
[splitting](#configure-splitting), [outputs and archiving](#configure-output-files),
[reference updates](#configure-a-reference-csv-update), or
[failure and cleanup settings](#failure-settings-and-working-file-housekeeping).

## Available built-in tasks

| Catalog label | Built-in identifier | Purpose / normal position |
| --- | --- | --- |
| **Llama Cloud Split** | `llamacloud_split` | Classifies and splits a bundle through LlamaCloud. Before extraction. Requires an approved cloud connection. |
| **Manual Split** | `manual_split` | An operator chooses page boundaries in Review Queue. Before extraction. Local; no cloud splitter required. |
| **Extract Pdf** | `extract_pdf` | LlamaCloud extracts configured values. Choose one extraction method. |
| **Lite Parse Extract** | `liteparse_extract` | Local text/OCR parsing and one model request for selected evidence. Choose when the complete input/output fits. |
| **Glm Ocr Extract** | `glm_ocr_extract` | Local visual extraction per page, with optional complete-document reconciliation. Consider for larger inputs. |
| **Review Gate** | `review_gate` | Pauses for checking and correction. After extraction, before outputs requiring approved values. |
| **Assign Nanoid** | `assign_nanoid` | Generates a short identifier for filenames. Before tasks using its filename token. |
| **Store Metadata As Csv** | `store_metadata_as_csv` | Exports values as spreadsheet-style rows, with one row per table item. After review if approval is required. |
| **Store Metadata As Json** | `store_metadata_as_json` | Exports structured values while retaining groups and repeated items. After review if approval is required. |
| **Store File To Localdrive** | `store_file_to_localdrive` | Copies the processed PDF to an output folder with the chosen filename. |
| **Archive Pdf** | `archive_pdf` | Copies the PDF being processed at that step to an archive destination with a safe unique name. |
| **Update Reference** | `update_reference` | Marks matching rows in a reference CSV. After review when matching needs approved values. |
| **Cleanup** | `cleanup_task` | Internal working-file housekeeping, normally invoked automatically. Do not add it to an ordinary pipeline. |

Only one split task, one extraction task and one Review Gate are allowed per
pipeline definition. Choose either cloud or manual splitting and one of the
three extraction methods. Disabled duplicates are not a useful way to keep
alternative designs: remove the unused task or clone a separate pipeline.
Other repeated task types can produce a warning; confirm they are intentional,
for example separate JSON and CSV outputs or copies to different destinations.

If you need a task absent from this list, ask the maintainer whether a custom
task is available and approved for the deployment. Typing a new name does not
create a supported operation. An unapproved task blocks use; a task's approval
does not itself establish business suitability.

## Order tasks around the business outcome

A normal human-checked document pipeline is:

1. Optional split, when a PDF contains several separate documents.
2. One extraction task for the intended document type.
3. Review Gate with the matching published form.
4. Optional Assign Nanoid for a short filename identifier.
5. Required JSON/CSV exports and PDF copy.
6. Optional reference CSV update and source archive according to your process.

The editor rejects a split after extraction and a gate before extraction.
A split cannot be the final step: its child documents need following processing.
Extraction must precede tasks that use extracted values, and review must precede
actions that must use approved values. The validator does not prove every
business dependency is satisfied; inspect the order yourself.

Manual split review and extracted-data review are different pauses. A combined
bundle may first need page boundaries, then each resulting document needs its
own extracted values checked. Adding Review Gate does not provide page splitting.

For cloud-free processing, use Manual Split (if needed), a local extractor,
Review Gate and local output tasks. Adding Llama Cloud Split still sends the
PDF to a cloud service even when extraction is local.

## Configure splitting

### Manual Split

Add **Manual Split** before extraction. Set **Split output directory** to the
working folder approved by IT, keep **Enable manual splitting** selected, and
use the agreed **Review queue**, normally `default_review`.

For a multi-page PDF the operator chooses **No split** or groups covering all
pages, then submits the decision. No split continues the same document. A
confirmed split sends each child PDF through the following tasks; the parent
records the split outcome. One-page PDFs continue automatically. Test both
no-split and split cases, including which child PDFs and exports appear.

The split folder stores working child PDFs. If they must remain available as
business records, configure appropriate PDF output/archive steps and confirm
the resulting files with IT. Do not equate a working directory with a backup.

### Llama Cloud Split

1. Add **Llama Cloud Split** before extraction. Use the **API key secret alias**
   supplied by IT and set **Split output directory**.
2. Choose **Define categories here**, then define category names and descriptions
   that distinguish real document types, for example `invoice` and `credit-note`.
   Describe what makes each category recognisable; avoid near-identical rules.
3. Alternatively choose **Use saved LlamaCloud configuration** and enter the
   provider configuration ID prepared for this process.
4. Decide **When pages cannot be categorized**. **Keep uncategorized pages**
   retains them, **Stop the split** prevents continuing that split, and **Skip
   uncategorized pages** leaves them out of generated PDFs. Use Skip only when
   your business policy permits excluding those pages and you have tested it.
5. Review the split confidence-failure choices and unknown-category checks.
   A selected failure level stops the split; a later Review Gate cannot review
   a split that has already failed. If review should handle a successful but
   uncertain split, align these choices with the gate's split confidence levels.
6. Test actual page grouping, uncategorized pages and ambiguous categories before
   enabling folder intake. Advanced polling/timeouts belong with IT if provider
   response times require adjustment.

Splitting into different categories does not automatically select a different
extraction task for each category. This pipeline still has one extraction
configuration. If the resulting document types need different fields, agree
separate pipelines/intake with the process owner rather than expecting category
names to switch extraction schemas.

## Configure extraction and review

Use [Configure extraction](configuring-extraction.md) for method selection,
field definitions, grouped values, table columns, local runtime settings and
LlamaCloud setup. Do not put both local extractors into one pipeline to compare
them; clone pipelines and use the same test set.

Use [Manage review forms](managing-review-forms.md) for a complete form example
and gate controls. Select an exact published form version. Local extraction's
missing confidence sends all fields to a following gate; use document-wide
editing when every value and row needs confirmation. Without a gate, outputs
can be written without operator approval.

## Configure output files

Confirm approved destinations, write access and receiving-system requirements
with IT and the business owner. A folder must be accessible to the application
account on the server; a folder on your own laptop may not be suitable.

### CSV or JSON values

1. Add **Store Metadata As Csv**, **Store Metadata As Json**, or both after review.
2. Set **Data output directory** to the approved destination; use the folder
   browser where available.
3. Set **Filename template**. Start with `{id}` to name each document uniquely.
   The task adds `.csv` or `.json`, so omit the extension from the template.
4. Use **Insert a token** to add a field, for example
   `{id}_{invoice_number}`. A token means “insert this document's value here.”
   Prefer required scalar values; an optional missing value can make naming fail.
5. Keep compatibility overrides off for a normal new pipeline. Published
   storage tasks do not automatically inherit extraction aliases from another
   task. Normally outputs use the produced field keys. If recipients require
   specific column/key labels, ask support to prepare task-specific field
   definitions and test them. The CSV editor's hint about reusing extraction
   fields does not guarantee inherited aliases.
6. Run the complete pipeline and inspect the actual saved file with its receiver.

CSV expands a table into one row per item, repeating document-level values.
Item columns normally start with `item_`. When no table rows are present the
task can write a document-level row instead; decide whether that is acceptable
for your documents. JSON retains grouped values and repeated objects and is
often a better fit for a system expecting that structure. Neither task validates
the receiver's business rules or calculates missing amounts.

**Use nested storage overrides** and **CSV extraction-field override** support
advanced/older definitions. They are not prerequisites for basic export. Do
not turn them on just to fix a wrong key in extraction or review.

### Copy a PDF with a meaningful filename

Add **Store File To Localdrive**, set **PDF output directory** and a **Filename
template**, for example `{id}_{invoice_number}`. The task adds `.pdf`. Put it
after review when the name uses corrected values. It copies the current
processed PDF (a child PDF after a split); it does not draw corrected text onto
its pages. Open the copied PDF during acceptance testing.

Keep an identifier in filenames when different documents can share a reference.
These output tasks protect against overwrites using unique filenames, but a
clear naming policy is easier for staff to trace. The editor's **Preview**
shows the template, not a sample with real extracted values; a real test is needed.

### Assign a short identifier

Add **Assign Nanoid** before filename tasks if you need `{nanoid}`. Set **Nanoid
length** from 5 to 21; a new task starts at 10. Longer values offer more possible
identifiers. A normal `{id}` filename does not require this task. Check that the
same generated value appears in the PDF and data filenames if they should pair.

### Archive the source PDF

Add **Archive Pdf** and set **Archive directory** to an existing approved
folder. It copies the PDF being processed at that step with a safe, unique name
and leaves the source file in place. After a split, that is the child PDF; it
does not automatically go back and archive the original bundle. Put Archive Pdf
before splitting if you need a copy of the whole incoming bundle, and verify
that copy in your split acceptance test. Use the PDF output task for child copies
with names based on approved values. An Archive Pdf task is different from
archiving a pipeline definition or deleting processing history. It does not
implement a full backup or automatically expire old files.

## Configure a reference CSV update

Use **Update Reference** only when your process must mark an existing external
list, such as a register of purchase orders. Arrange an approved writable CSV
and a test copy first; this task modifies the file.

1. Place it after review when matches must use approved extracted values.
2. Choose **Reference CSV**. Confirm its column headings load.
3. Select **Update field** and enter **Write value**, for example `MATCHED` and
   `yes`. This is the column/value written into matching rows.
4. Keep **Backup reference CSV before write** enabled unless IT has agreed an
   alternative. A task backup is not a deployment-wide backup.
5. Under **Match conditions**, set **CSV column** to the reference-file heading
   and **From context** to the corresponding document field. “Context” here
   means values already produced by earlier tasks, such as `purchase_order_number`.
6. Use **Add clause** for up to five conditions. Every condition must match
   the same CSV row. Choose **Text comparison** for references with leading zeros
   and **Numeric comparison** for amounts when appropriate; **Auto-detect**
   lets the task choose.
7. Test a matching row, a non-matching row, a missing document value and duplicate
   matching rows. Inspect what changed in the CSV and its backup.

For example, match `P/O NO.` against `purchase_order_number` as text and `AMOUNT`
against `invoice_amount` numerically, then write `yes` in `MATCHED`. This example
requires those extraction fields; it is separate from the basic invoice fields
used in the other guides. Use the keys your pipeline actually produces.

The task updates matching rows; it does not append a new row for an unseen
reference. A missing comparison value can result in no match without failing
the pipeline. Therefore “pipeline completed” does not prove that the reference
was updated. Verify the business outcome explicitly.

## Failure settings and working-file housekeeping

In each task's settings, **If this task fails** offers **Stop the pipeline**,
**Continue to the next task** and **Default runtime behavior**. Start with Stop
for extraction, review, required outputs and critical business updates. Continue
is appropriate only when later tasks remain meaningful after that failure and
you have a procedure to detect the missing outcome. Choosing Continue does not
turn a failed task into a successful one.

The app normally invokes **Cleanup** automatically when a workflow reaches its
cleanup phase. It removes eligible working PDFs and preserves registered output
files; it is not the Admin history-cleanup action. Review pauses and split
handoffs have special handling so work can continue. Do not add Cleanup early
to reclaim space: it can remove a working PDF that later tasks need. Ask IT
about storage pressure and retention instead.

For a complete setup and acceptance sequence, follow
[Manage pipelines](managing-pipelines.md). Exact implementation parameters are
in the [technical task reference](../reference/tasks/README.md).
