# Manage pipelines

| Item | Value |
| --- | --- |
| Audience | Application administrators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

A **pipeline** is an ordered set of processing tasks for a document type. A
**draft** is the editable working copy. Publishing creates a numbered version
that cannot be edited. Each document keeps the version selected when accepted,
even if you publish another version while it is running or awaiting review.

This guide takes you from a new definition to a tested processing service.
Use [Choose and configure tasks](task-guide.md) for every supported task and
[Configure extraction](configuring-extraction.md) for method-specific decisions.

Go directly to [creation and publication](#create-and-publish-a-pipeline),
[the worked pipeline](#worked-example-local-invoice-review-and-export),
[acceptance checks](#verify-before-routine-use),
[changing a pipeline](#change-an-existing-pipeline), or
[troubleshooting](#resolve-common-setup-problems).

## Prepare the processing design

Before creating a pipeline, establish:

- Which document type it accepts and whether a PDF can contain several separate
  documents that must be split first.
- Which fields and repeating table you need, which may be missing, and what the
  receiving person/system expects in the output.
- Which extraction method meets the document's size, layout, speed and approved
  processing location. Local and cloud tasks can be mixed, so inspect each step.
- Whether every document needs review or only those meeting specified conditions.
- Required CSV/JSON/PDF/archive destinations, prepared by IT for the application
  account, plus any approved connection secret aliases and installed models.
- Approved test documents, a person to check results, and acceptance criteria.

Create and publish the [review form](managing-review-forms.md) first if the
pipeline needs a gate. Make the form Active before validating/publishing a new
pipeline that references it. A form draft is not a selectable published version.

## Create and publish a pipeline

1. Sign in as **admin**, select **Pipeline**, then **New**.
2. Enter a unique **Stable pipeline key**, for example `invoice-local-review`,
   and friendly **Pipeline name**, for example `Invoices — local with review`.
   The key starts with a letter and uses lowercase words/numbers separated by
   hyphens. It cannot be renamed; the display name can.
3. Select **Create pipeline**. Confirm the new pipeline in **Pipeline template**.
   It starts inactive with an editable draft.
4. Set **Name**, **Document type** and **Description**. Leave each field by
   pressing Tab or clicking outside, then wait for its save message. Describe
   accepted documents and intended outputs so another Admin can select it safely.
5. In **Editing draft**, open **Add task**, choose an available task and select
   **Add**. Repeat for the required steps. See the worked example below.
6. Select each draft task to open **Step Parameters**. Complete its ordinary
   task controls. Give it a clear **Label** and keep a distinct **Key**.
   Leave implementation identifiers and advanced file-level settings to support.
7. Use **Up** and **Down** to arrange the list. Keep **Enabled in pipeline**
   selected for required tasks. Removing a task removes its settings from the
   draft after confirmation; published versions stay unchanged.
8. For each task, choose **If this task fails** deliberately. Start with
   **Stop the pipeline** for extraction, review and required outputs. Continue
   is suitable only when later steps still make sense after that failure.
9. Select **Save Draft**. Confirm the saved revision. Select **Validate** and
   inspect the findings, including warnings. Fix every blocking finding, save
   and validate again. Any subsequent draft edit needs another save/check.
10. Select **Diff** to inspect changes against the published base where available.
    Select **Publish**, review the task/dependency confirmation, then
    **Publish version**. Check the new version number and **Live pipeline**.
11. Select **Activate for uploads** when ready for a controlled upload test, or
    set **Availability status** to **Active** and check its save confirmation.
    Publication and availability are separate. Activation can make it visible
    to operators, so agree a test window; leave routine watch folders paused.
12. On **Upload & Process**, choose this pipeline and the intended published
    version, submit an approved sample, and follow it through Reports, review
    and final files. Complete acceptance checks before routine intake.

Task edits need **Save Draft** and publication. Name, description, document type
and availability save separately; changing them does not publish task edits.
**YAML Preview** shows the definition in a technical format; you do not need to
edit it to configure supported task forms.

## Worked example: local invoice review and export

This example accepts one invoice per PDF and creates approved JSON plus a PDF
copy. It is a starter design to adapt, not a preinstalled invoice template.
For multi-invoice bundles, add Manual Split before extraction and test the
extra operator step. Choose GLM-OCR instead of LiteParse when your sample set
needs its page-based processing; do not add both extractors.

First create `invoice-review` using the
[review-form example](managing-review-forms.md#worked-invoice-field-list),
publish it and make it Active. Ask IT to prepare local extraction and approve
the output destinations. The editor's relative folder defaults are suggestions;
confirm they refer to the intended server folders.

| Order | Task to add | Settings to complete |
| --- | --- | --- |
| 1 | **Lite Parse Extract** | Confirm Ollama host/model with IT; leave Selected pages empty for the whole PDF. Configure `invoice_number`, `invoice_date`, `currency`, `invoice_total`, `customer` and `line_items` using the extraction example. |
| 2 | **Review Gate** | Choose the exact `invoice-review` published version. Set Reviewer editing scope to Entire document; enable missing-confidence and missing-required-field review, editing high-confidence fields, and Always require review during acceptance. |
| 3 | **Store Metadata As Json** | Approved Data output directory; Filename template `{id}_{invoice_number}`. Use `{id}` alone if invoices without a reference must be accepted. |
| 4 | **Store File To Localdrive** | Approved PDF output directory; matching Filename template. |
| 5, optional | **Store Metadata As Csv** | Approved Data output directory and matching filename, when the receiver also needs one row per item. |
| 6, optional | **Archive Pdf** | Approved Archive directory if a separate source copy is required by policy. |

Set failure handling to Stop for the required tasks. Save, validate, publish
and activate in the sequence above. Submit a test invoice, claim its review,
change a deliberately incorrect value, complete review and inspect the files.
The exported corrected value must match the completed review. The PDF copy
still contains the source page content; review does not rewrite it.

The main invoice fields must use the same keys and nesting at extraction and
review. The `customer` group has `name` and `address`; the `line_items` table
has `line_number`, `description`, `quantity` and `unit_price`. A top-level
`customer_name` or a table column `price` would be a different key arrangement.

For GLM-OCR, replace task 1 with **Glm Ocr Extract** in a separate design,
configure **Complete document** and the installed resolver model, and keep the
same field/review arrangement. Compare speed and original extraction quality
using identical samples and output checks. Local output still needs review.

For LlamaCloud, use **Extract Pdf** instead and its approved secret alias.
After acceptance you may choose confidence-based review if business policy
allows it. Removing Always require review does not bypass local extractors'
unscored-result review requirement at a following gate.

## Verify before routine use

| Check | Evidence to inspect |
| --- | --- |
| Correct assignment | Reports/document details identify the intended pipeline and version. |
| Normal processing | A typical PDF reaches the expected finished state. |
| Split behaviour, if configured | No-split and split choices work; every required page appears in the right child and each child reaches output. |
| Extraction quality | Original extracted values, addresses and item counts match the PDF before corrections. Include the largest expected PDF and scans. |
| Review usability | All required controls appear, optional blanks are allowed, valid corrections can be made, and invalid required values prevent completion. |
| Approved output | Complete review, then open exported files: corrections, row count, keys/columns, filename and destination meet requirements. |
| Reference update, if configured | Intended reference rows change and unrelated rows stay unchanged. |
| Failure handling | Check known invalid/missing-input examples and ensure a required failure does not produce a misleading later business action. |
| Intake rollout | Controlled upload and folder sample both use the approved version; folder health alone is insufficient. |

Record sample identifiers, pipeline/form version numbers, settings changed,
outcomes and remaining limits. A single successful small PDF is insufficient
for a workflow expected to handle long documents or complex tables.

If acceptance fails, keep routine folder intake paused. Use an already tested
pipeline/version where available, correct the draft, publish a new version and
test a new submission. Do not expect an old document's retry or review resume
to adopt your new configuration.

## Change an existing pipeline

1. Select it in **Pipeline template** and record the current published version
   and watch-folder assignments. Coordinate editing with other Admins.
2. Edit the draft. A published version remains immutable. If the change affects
   review keys/types, publish and activate the matching form first, then select
   its exact version in the gate.
3. Save, validate, inspect Diff, publish and test new submissions. Keep the
   previous known-good version details for the rollout decision.
4. For uploads, tell operators which pipeline/version to select. Publishing
   does not rewrite already accepted documents.
5. For each incoming folder, explicitly
   [change its Published version](managing-watch-folders.md#change-the-assigned-version).
   A new publication does not update those assignments automatically.

**Refresh** reloads and can discard unsaved task edits after confirmation.
**Reset draft to published version** replaces the working draft with published
settings; save/validate the replacement if keeping it. It does not roll back
accepted documents or folder assignments. **Clone** creates a separate inactive
pipeline from the latest published settings, not from your unsaved draft, and
does not copy processing history or watch-folder assignments.

For a controlled return to earlier behaviour, folders can select an available
known-good published version. For new upload work, select the known-good version
where offered, or publish a new version containing the reviewed earlier settings.
Do not archive a pipeline as a temporary rollback; archiving is permanent.

## Transfer a definition

**Export** transfers the saved draft settings, not documents, history, installed
models or provider credentials. Save intended draft changes before exporting.
Record the source pipeline and revision/version context with the file.

**Import** updates the selected pipeline's draft. Select the destination
carefully; for an independent copy create a new pipeline first. Check every
task, exact review-form dependency, secret alias and destination after import.
Another installation may need its own matching form published and selected,
plus its own provider setup. Import does not publish or activate the pipeline.
Save/validate, publish and test before intake. Ask support about unfamiliar file
content or advanced settings; ordinary setup uses the screen controls.

## Resolve common setup problems

| What happens | What to check |
| --- | --- |
| Review form absent or dependency inactive | Publish the correct form, make it Active, refresh/select its exact published version and validate again. |
| Cannot add a second extractor/split/gate | One of each is supported per pipeline. Remove the alternative or create another pipeline. |
| Publish unavailable | Save the current draft and resolve blocking validation findings. Read the guidance if there are no changes from the published base. |
| Model/connection fails after validation passed | Validation does not perform live inference. Check task settings and give IT the safe connection/model error. |
| New version does not affect old work | Accepted documents retain their original versions. Test a new submission. |
| Folder still uses the old version | Edit that folder's assignment explicitly. |
| Output blank, wrong columns or wrong rows | Compare original extraction, form keys and nesting, completed review, then storage settings. Changing a label alone does not fix a key mismatch. |
| Stale revision / another Admin saved | Record intended changes, refresh and reconcile the current draft before saving again. |

For permanent retirement or removal of finished history, follow
[Archiving and retention](archiving-and-retention.md).
