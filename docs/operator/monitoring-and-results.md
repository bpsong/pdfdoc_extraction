# Monitor processing and find results

| Item | Value |
| --- | --- |
| Audience | Operators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

Check both the processing outcome and the information your work needs.
Uploading confirms acceptance; completing review confirms a human decision;
later output tasks still need to finish. A PDF split into several documents
can have a different outcome for each child.

Go to [find a batch](#find-your-batch), [understand statuses](#decide-what-needs-attention),
[split results](#check-documents-created-by-splitting), or
[values and files](#check-values-and-files).

## Find your batch

After a browser upload, the app opens the batch's processing dashboard.
Check its pipeline name/version and original filenames to confirm the work.
Record or bookmark the batch address if you need to return later.

To find recent work:

1. Open **Reports** and find **Recent Batches**.
2. Match the submission time, source and batch identifier. **Source** distinguishes
   browser intake from other intake such as an incoming folder.
3. Select the batch row; keyboard users can focus it and press Enter or Space.
4. In its details, inspect documents and task history, then select
   **Open processing dashboard**.

Reports also summarises document statuses, submission sources, review activity,
completed/failed totals and average processing time. These are activity summaries,
not proof that a particular document's required output is correct. Select
**Refresh** to update Reports. Recent Batches is not an exhaustive searchable
archive; ask the Admin if older work is absent and you have its identifier.

On the dashboard, **Current step** identifies what a document is doing or
waiting for, and **Last completed** identifies the latest finished step.
Pipeline steps can summarise several documents, so inspect individual rows
when some have finished and others need attention. The dashboard refreshes
periodically. A Retry control beside a loading error reloads the view; it does
not restart processing.

## Decide what needs attention

| Status or step state | Meaning and next action |
| --- | --- |
| **Queued / Pending** | Accepted or waiting for a step. Monitor; repeated uploads do not make it start sooner. |
| **Processing / Running** | A step is working. Allow time appropriate to the document and pipeline. |
| **Review Required / In Review** | A person needs to decide or has claimed the item. Open Review Queue and check ownership. |
| **Split Completed** | Splitting finished. Inspect the child documents and their remaining steps; the whole business process may still be unfinished. |
| **Extraction Completed** | Values were extracted. Review and output can still follow. |
| **Review Completed** | Review finished; check the remaining workflow and output. |
| **Completed** | Configured processing finished. Confirm the required results/files. |
| **Completed With Errors** | Work ended with recorded problems. Read Failures and check which required outcomes are missing. |
| **Failed** | A step could not finish. Open Failure details and read the suggested action. |
| **Paused** | Work is paused; inspect the current step and Review Queue, or ask the Admin about an unexpected pause. |
| **Skipped** on a step | That operation was not performed for this document. Check the reason, for example no split needed; it does not by itself mean failure. |
| **Cancelled** | Work was cancelled. Ask the Admin what should happen next; do not assume results exist. |

Progress percentages describe recorded processing steps, not extraction accuracy
or a reliable time remaining. Long scans, larger documents, local model loading
and tables can take longer. Ask the Admin for the normal range for this pipeline;
report an unchanged step beyond that range with its time and document identifier.

**View failure details** or **Open Failure** can remain available because an
earlier failed attempt is recorded. Compare that evidence with the document's
current status and latest task history before deciding to resubmit.

## Check documents created by splitting

From the batch dashboard select **View Split Results** when offered (or its
**Split** action). Find the source PDF and inspect each child row's page range,
category and status. Select **Extraction** for the individual child. A source
row's **View Extraction** can open a child rather than the whole original;
check the filename and pages after opening it.

Each child continues separately and may need its own review. One can finish
while another is waiting or failed. The original's status reflects that wider
outcome; finishing the split decision does not finish all children.

| Split Results display | How to read it |
| --- | --- |
| **Documents Created**, **Successful Children**, **Failed Children** | Counts of generated child documents/outcomes, not a count of PDFs you originally submitted. |
| **originals continued** | Original PDFs that continued as one document rather than producing children. |
| **No split needed — processing the original document** | The splitter identified a single document; follow the original's remaining extraction/review. |
| **Single-page PDF / Operator chose not to split** | The manual step continued the original without creating children. |
| **Waiting for manual split review** | Go to Review Queue and make the page-boundary decision. |
| **No child documents were created** | Check the actual split outcome/status. Zero children alone does not prove a successful no-split result. |

A category describes the split classification. It does not prove extracted
fields are accurate or that the child finished. If grouping/page coverage looks
wrong, record the source and child identifiers and ask the Admin before
resubmitting the bundle.

## Check values and files

Open a document's **Extraction** action. It displays the source/stored PDF and
saved values; it is not an editing screen. Use **Review** to open an available
review item and claim it before making permitted corrections.

| Column or label | Meaning |
| --- | --- |
| **Extracted Value** | What the extraction method originally read. It remains evidence even after correction. |
| **Final Value** | The currently saved result, including accepted review corrections when present. Before review, it may still equal the original. |
| **Confidence** | The original extraction score, when supplied. It does not become a new score after a human correction. |
| **Review Status — Required** | The value needed attention; check whether its review is still outstanding. |
| **Reviewed** | Review finished for a value that required attention and was accepted. |
| **Corrected** | A value was changed during review. |
| **Human review complete / Review complete** | No further action is required on that review. Check the document's later processing outcome separately. |

For a corrected invoice total, the two value columns can differ intentionally.
Use the approved Final Value for the agreed downstream work. **Raw Payload**
is detailed original extraction information for investigation; it may not
include human corrections and should not be used in place of Final Value.

Select or focus a field row to locate its evidence. Precise highlights are
available only when the method supplied suitable evidence. With page-only or
diagnostic evidence, read the PDF yourself. High/medium/low confidence describes
the machine result, not approval. **No model confidence**, **N/A confidence**
or **No confidence** means a score was not supplied; completed reviews can still
show that label without requiring another review.

**Previous** and **Next** beside Extracted Fields move between documents in the
same batch. The PDF viewer's page arrows/page number move within the current PDF.
Check the filename to avoid comparing one document's values against another's pages.

### Find the actual output

The pipeline determines which PDF copies, CSVs (spreadsheet-style rows) and
JSON files (structured results for other systems) are saved. The file list
under the Extraction PDF identifies registered filenames and types. The current
list does not itself provide download buttons: use the approved output folder
or access method supplied by your administrator. **No registered files** is not
proof that every pipeline was intended to save exports; confirm expected outputs.

Check that required files exist, belong to the correct document and contain
the final reviewed values. A PDF copy retains the source page content; correcting
data does not rewrite printed text on its pages. If file access is unavailable,
give the Admin the document/batch identifiers and displayed filenames rather
than trying to browse the application's working directories.

Old batches can disappear after an administrator removes finished processing
history. Files may remain separately while app pages/preview links stop working.
Ask before submitting an old document again.

See [reviewing information](reviewing-extracted-data.md),
[manual splitting](manual-splitting.md), and [troubleshooting](troubleshooting.md).
