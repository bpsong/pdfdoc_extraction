# Resolve common problems and request help

| Item | Value |
| --- | --- |
| Audience | Operators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

Start with the document's current status and exact message. A loading problem,
an outstanding review and a failed processing step need different actions.
Check existing work before submitting the same PDF again, especially after an
interrupted upload or a split.

## Everyday problems

| Problem | First action | Ask for help when |
| --- | --- | --- |
| Cannot sign in | Check the selected account and password; observe any displayed cooldown before trying again. | You forgot the password or access remains unavailable; the Admin changes the operator password. |
| Pipeline missing | Select Refresh once and check its name/version with the Admin. | It needs publication/activation or your approved version is unavailable. |
| Start processing unavailable | Select a pipeline, add valid PDFs and read file-count/size/type messages. | The list is valid but submission remains unavailable. |
| Upload too large | Reduce the batch size; follow the displayed per-file and total limits. | One required PDF exceeds the per-file limit; ask about an approved way to reduce/divide it. |
| Upload cancelled or connection lost | Follow the same-tab, same-files and same-version acceptance check/retry procedure. | You cannot confirm whether work was accepted; do not create a separate upload yet. |
| File stays in incoming folder | Check the agreed path and Reports. | No batch appears in the expected intake time; Admin checks the folder, IT checks the watcher/access. |
| Processing appears stuck | Check Current step, Review Queue, latest history and all children. | The same step remains unchanged beyond the expected time for that pipeline. |
| Review list empty | Check Needs review versus History, ownership/pipeline/search filters, pagination and Refresh. | You know an item should exist but still cannot find it. |
| Field not editable | Check the claim, review status, read-only marker and scope of permitted edits. | A wrong value cannot be corrected under the configured form. |
| Review cannot complete | Read missing/invalid required-value messages and check claim ownership. | A required fact is absent, a valid choice is missing or the form is unsuitable. |
| Source PDF/evidence unavailable | Check the source preview and page controls. Lack of a precise highlight alone is not failure. | The PDF itself cannot be read or opened; do not approve unseen values. |
| Files missing or inaccessible | Check final workflow status and registered filenames; confirm the approved output location. | Required outputs are absent or you cannot access the agreed destination. |
| Old batch disappeared | Ask whether processing history was cleaned up or the batch is outside Recent Batches. | You need retained files/history or are considering processing it again. |

Operators do not install software, edit processing settings or recover the Admin
account. Give the Admin the symptoms; they can correct business configuration
or involve IT. Do not put passwords or service keys into support descriptions.

## Investigate a failed document

1. On its processing dashboard, select **View failure details** or **Open Failure**.
   Alternatively open **Failures** from the menu.
2. Find the document/source name and failure time. Sort by **Document**,
   **Failed Task**, **Error** or **Failed At** using heading buttons, and use
   **Previous**/**Next** for more rows. The current Failures page does not have
   a search box; a direct failure link from the batch avoids locating it manually.
3. Select **Open Failure**. Read the full **Error**, the failed step and suggested
   operator action. The list can shorten messages; open the detail to read them.
4. Examine the preview or **Open Source PDF**. Check readability, page order
   and whether the PDF contains the document type the selected pipeline expects.
5. For a split failure, check **Original Source PDF**, **Failed Split Segment**,
   its page range/category and **Related Split Failures**. Similar child failures
   can be grouped under one source; this is not necessarily several failed uploads.
6. Compare the failure with current dashboard status and recent task history.
   An older failed attempt can remain visible after later progress.
7. Resolve an actual source issue through the agreed business process, or ask
   the Admin about form, task, connection or configuration failures. Re-submit
   only after the cause is addressed and a new submission is appropriate.

For example, a blurry scan needs a better source; a missing installed model
needs IT attention. Repeatedly uploading either document without addressing
the cause does not fix it. Detailed task output on the failure page is there
for investigation; you do not need to interpret all of it to request help.

## Understand which retry action is offered

| Action/context | What it does |
| --- | --- |
| **Refresh / Retry** beside a page-loading error | Loads screen information again. It does not necessarily restart any processing task. |
| Retrying an unconfirmed upload in the same tab with the same files/version | Attempts to resolve/reuse that submission. Check whether an existing accepted batch opens. |
| **Retry continuation** on a saved manual split decision | Continues eligible unstarted work for that decision when the app permits it. It does not edit boundaries or retry arbitrary downstream failures. |
| Uploading again as new work | Creates a new submission when appropriate; it can duplicate earlier work. Use after the cause is addressed and acceptance/history is understood. |

An existing processing retry keeps its original pipeline version. Publishing
a fix does not make old work silently adopt it. Let the Admin decide whether
an existing item can continue or a new submission is needed after a change.

For interrupted uploads use
[the acceptance recovery steps](submitting-documents.md#if-transfer-is-cancelled-or-acceptance-is-uncertain).
For saving/claim problems use
[review ownership guidance](reviewing-extracted-data.md#claims-expiry-and-another-session).

## Common questions

**Does Save Draft finish a review?** No. It saves progress. Use Complete Review
after checking extracted information, or Confirm split / Continue without
splitting for a manual split decision.

**Why is a completed review still low confidence?** The score describes original
extraction. Review complete, Reviewed and Corrected identify the human outcome;
a missing score does not reopen completed work.

**Can I edit values on Extraction?** It shows saved results and evidence. Use
an available claimed review for permitted corrections; ask the Admin about
changes needed after review is completed.

**Does local splitting mean the whole pipeline is local?** It describes that
step. Another configured task can use a cloud provider. Ask the Admin which
process is approved rather than inferring it from a single screen badge.

**Where are my files?** Extraction lists registered filenames/types. Use the
approved output folder/access method from your Admin; that list itself has no
download buttons. A file may be kept even after its processing history is removed.

## Give support enough information

Use your organisation's approved support channel and provide:

- Batch and document identifiers displayed by the app, plus the original filename.
- Pipeline name/version and approximate submission/failure time, including
  your local time zone if the support team works elsewhere.
- Whether this was a browser upload, incoming-folder intake, extracted-data
  review or manual split, and the step/action you were taking.
- Current status, failed step, exact message and whether another attempt progressed.
- For split work, original source and affected child identifiers/page ranges.
- Whether you saved a draft, completed a decision, cancelled a transfer or retried,
  and whether the expected final files exist.

Share document contents/screenshots only through a channel approved for that
information. Remove unrelated personal/customer information and credentials.
The Admin can pass technical faults to IT while keeping the document and
business context clear.
