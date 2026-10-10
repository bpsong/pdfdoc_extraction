# Split a PDF during review

| Item | Value |
| --- | --- |
| Audience | Operators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

Use this review when the pipeline asks you to decide which pages belong to
separate documents. It does not correct extracted values. One invoice may
span several pages, so split at document boundaries rather than after every page.
If a page's ownership is unclear, ask the process owner before confirming.

Go to [the split procedure](#choose-and-confirm-boundaries),
[a worked plan](#example-three-documents-in-one-pdf), or
[claim/recovery guidance](#claims-and-recovery).

## Open the manual task

1. Open **Review Queue** and use **Needs review**, pipeline/search and ownership
   filters to find the source PDF.
2. Look for **Manual split**, its page count and **Manual task** review signal.
3. Select **Claim & split** for available work. Your existing claim can show
   **Open split**. **View split** opens an inspection view; use **Claim** when
   available before editing.
4. Confirm the source filename and page count, and wait for the PDF to load.
   The pages appear in vertical source order; scroll through all of them.

Manual splitting happens locally on the application server. Its page badge
describes this step; later extraction can use another configured method. Ask
the Admin about the whole pipeline if processing location matters to your work.

## Choose and confirm boundaries

1. Read enough of each page to recognise the end of one document and start of
   the next. Keep continuation pages with their own document.
2. Select the checkbox **between** two pages to split after the first page.
   Clear it to undo that boundary before confirmation.
3. Check **Split plan**. It lists Document 1, Document 2 and so on with their
   page ranges, plus the document/boundary counts. Every source page remains
   included in order. This screen does not delete or rearrange pages.
4. Numbered markers match selected boundaries with **Split after page …** in
   the plan. Select a plan boundary to jump to its checkbox. Use **+**, **−**
   or **Fit width** to read small print; zoom does not change boundaries.
5. Select **Save draft** if unfinished. Wait for **Draft saved. Processing remains
   paused.** Reopening restores the saved boundaries; unsaved choices are not
   a saved plan.
6. When correct, select **Confirm split** once. If the PDF is one whole document,
   clear every boundary and select **Continue without splitting** instead.
7. Wait for **Decision saved**. The saved decision is final. Select
   **View processing** to follow the batch; you can leave the form once the
   decision has been saved while downstream processing runs.

The source PDF remains unchanged. A split creates child documents, each of
which continues through later steps and can require extracted-data review.
No split continues the original through those steps. One-page PDFs normally
pass the manual step automatically without a queue decision.

## Example: three documents in one PDF

A seven-page bundle contains one invoice on pages 1–2, another on pages 3–5,
and a final invoice on pages 6–7. Select boundaries **after page 2** and
**after page 5**. The plan should show:

| Resulting document | Pages |
| --- | --- |
| Document 1 | 1–2 |
| Document 2 | 3–5 |
| Document 3 | 6–7 |

Do not select after page 1 just because the first invoice continues onto page 2.
Check the beginning and ending page of every planned document, then confirm.
For a single seven-page invoice, select no boundaries and continue without
splitting. If the plan is wrong after confirmation, contact the Admin with the
source and decision details; it cannot be edited into a different decision.

## Claims and recovery

| Situation | What to do |
| --- | --- |
| Buttons/checkboxes unavailable | Wait for the PDF, check whether you own the claim and whether the decision is already saved. Claim when available. |
| You need more time | Use **Renew claim** when offered. Save the draft before taking a long break. |
| Handing work over | Save the intended plan first, then **Release** and tell the next reviewer which document needs attention. |
| Unsaved selections | Save before Back to Queue, reloading or closing. A leave-page warning is not a save. |
| Newer draft in another session | Note your intended boundaries, then reload and inspect the latest saved plan before saving/completing. Renewal can keep your unsaved selections visible but requires reload when the saved revision changed. |
| Claim expired | Renew/claim when permitted, compare the restored/current plan, then save or confirm. Coordinate with any other reviewer. |
| PDF cannot render | Reload when advised; do not confirm boundaries on an unreadable preview. Ask the Admin if it repeats. |

Unlike extraction review, the split page explicitly preserves visible unsaved
boundaries during a renewal unless you reload. That does not allow overwriting
a newer saved plan; read the stale-draft message and reconcile it first.

## Follow a saved decision

Completed plans appear in Review Queue **History** under **View split**. Use
**View processing** to inspect the original and any children, then
[monitor all their outcomes](monitoring-and-results.md#check-documents-created-by-splitting).
The plan page is not proof that extraction and exports finished.

If the message says the decision was saved but processing could not continue,
use **Retry continuation** only when it is offered for that decision. It handles
eligible work that has not started; it does not redo a split plan or rerun every
child's later failure. If an attempt already started, the app can require Admin
repair. Give the Admin the exact message instead of repeatedly clicking or
re-uploading the original bundle.

If the status refresh fails after confirmation, the decision may already be
saved. Open History or the processing dashboard to check; avoid making a second
submission merely because the latest status could not load.

See [getting help](troubleshooting.md) for the handoff information.
