# Review extracted information

| Item | Value |
| --- | --- |
| Audience | Operators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

Review compares the machine's extracted information with the source PDF and
records the checked values. A document can require review because of low or
missing confidence, absent required values or your organisation's policy.
An item in the queue does not necessarily mean extraction failed.

Go to [finding work](#open-and-claim-a-review),
[correcting the form](#check-and-correct-the-form),
[saving or completing](#save-progress-complete-or-hand-over), or
[claim problems](#claims-expiry-and-another-session).

## Open and claim a review

1. Select **Review Queue**. **Needs review** contains outstanding decisions;
   **History** contains completed ones.
2. Use **Pipeline** and **Search documents** to narrow the list. Check the
   filename and pipeline, especially when similar documents appear.
3. Use the ownership filters below to find available work or return to your item.
4. Select **Claim & review** beside an available extraction review, or
   **Continue review** for your existing claim. If you open **View**, select
   **Claim** before editing when it is offered. A claim temporarily reserves
   the item for the signed-in account.
5. Check the source PDF and the form's reason for review. For an item marked
   **Manual split**, use [the separate split procedure](manual-splitting.md).

| Queue control | How to use it |
| --- | --- |
| **All active** | See outstanding items regardless of ownership. |
| **Unclaimed** | Find work available to claim. Expired claims become available again. |
| **Assigned to me** | Return to an item claimed by your signed-in account. |
| **Claimed by others** | Inspect work reserved by another account; do not assume it is available to edit. |
| **History** | Inspect completed reviews and split plans; it is not the unfinished-work list. |
| Column heading buttons | Sort by Document, Pipeline, Fields to check, Review signal, Queued at or Status; select again to change direction. |
| **Rows per page**, **Previous**, **Next** | Browse 10, 25, 50 or 100 rows per page. Filters/page-size changes return to page one; sorting applies to all matching items, not just visible rows. |
| **Refresh**, or **Retry** beside a load error | Reload queue information. This does not restart document processing. |

**Fields to check** summarises why the item needs attention; open it for the
full form. **Review signal** shows extraction confidence or missing confidence.
For Manual split it says **Manual task** and shows a page count, because that
decision is about boundaries rather than extraction confidence.

Claims identify accounts, not individual people. If colleagues share the
operator login, **Assigned to me** can include their work too. Coordinate your
items and avoid editing the same document in several tabs or computers.

## Check and correct the form

1. Confirm the document name. Compare the source PDF with **Review Fields**.
   Scroll the PDF and form independently. Drag their divider to make room, or
   focus the divider and use Left/Right arrow keys. On smaller screens the panes
   appear one above the other.
2. Read field help and required/read-only markers. Correct permitted values
   against the actual document, including fields that look plausible at first.
3. Select or focus a field to locate supporting evidence in the PDF, when
   available. Use PDF previous/next page controls, page number and zoom to
   inspect surrounding content. **Open** opens the source PDF separately when
   available. See the source-display explanation below.
4. Check grouped fields and every repeating row, including tables continued
   onto another page. An apparently correct header does not confirm its lines.
5. Select **Preview Diff** to inspect proposed corrections against original
   extraction. Check that you did not accidentally change another value.
6. **Save Draft** for unfinished work, or **Complete Review** only when the
   required checks are complete. Follow any validation/error message.

### Enter the right kind of value

| Control | What to check |
| --- | --- |
| Text | Preserve reference spelling, leading zeros and meaningful punctuation. A multiline box is useful for long addresses/descriptions. |
| Number or amount | Enter the numeric value, including the correct sign and decimal places; keep currency words/symbols in their own field where provided. Do not calculate a replacement for a missing printed amount unless your agreed process requires it. |
| Whole number | Use a whole-number quantity. Ask the Admin if the form cannot accept a valid fractional quantity. |
| Date | Use the date picker for the correct printed date, distinguishing issue date from due date. If the extracted date is blank or ambiguous, check the PDF rather than guessing the day/month order. |
| Date and time | Use the date/time control and your agreed time convention; ask when the source is ambiguous. |
| Choice list | Select an available valid choice. Ask the Admin if a legitimate source value is absent instead of choosing the nearest option. |
| Yes/no | Distinguish false from missing/unknown. Do not assume a prefilled value is evidence from the document. |
| Required | A blank value can prevent completion. If the fact is absent from the PDF, request guidance; do not invent it. |
| Read only | You cannot correct the value through that control. Report an incorrect read-only value. |

### Check repeating lists and tables

Use **Add** for a repeated simple value, such as another serial number, and
**Remove** to remove a mistaken item when permitted. For a table, **Add Row**
creates another row and **Remove** removes the selected row. Verify which row
you are changing before removing it, then use Preview Diff to check the result.
These changes affect review values, not the PDF pages.

Check descriptions, quantities, unit prices and any printed distinguishing
references against the source. Preserve legitimate repeated items even when
their descriptions and prices match. Check for omitted continuation rows and
duplicate headings interpreted as items. If row controls are disabled, check
your claim and the configured editing permissions; ask the Admin if the form
does not permit a correction your process needs.

### Understand Source and confidence

The **Source** selector controls the original extracted values displayed beside
your current edits. It does not replace the PDF:

- **Review only** shows source values for fields needing attention or with changes.
- **All** shows source values throughout the scalar-field form.
- **Hidden** reduces those source-value displays; the PDF remains available.

**Show source value** reveals a field's original extracted value when hidden.
That value came from the machine; it is not automatically verified truth.
Selecting/focusing the field can also navigate to PDF evidence. Some methods
provide precise highlights, some provide only a page, and others show diagnostic
citations. A page link or diagnostic citation does not prove the value is right;
read the PDF, including adjacent labels and rows.

Confidence describes the original machine result. The display bands are High
(90% and above), Medium (70% to below 90%) and Low (below 70%); these bands are
not necessarily your Admin's review thresholds. For example, a field at 86%
needs review under a 90% rule. GLM-OCR and LiteParse supply no numeric score;
their values still need checking. Do not treat **Missing confidence** as zero
accuracy or as a reason to skip the item.

## Save progress, complete or hand over

| Action | Result |
| --- | --- |
| **Preview Diff** | Compares proposed values with original extraction. It does not save or complete review. |
| **Save Draft** | Saves permitted corrections and keeps processing waiting for review. Wait for Draft saved before leaving. |
| **Complete Review** | Submits checked values and allows processing to continue. |
| **Release** | Returns unfinished work to the queue. Save the draft first if the next reviewer should receive your corrections. |
| **Back to Queue** | Navigation only; do not rely on it to save edits or release the claim. |

After **Complete Review**, the button shows **Saving review…** and a message
shows **Saving review and finishing workflow…**. Keep the page open until the
queue appears. Controls are disabled to avoid submitting twice. If completion
fails, read the message; controls can become available again. If the connection
is lost, check History/current status before repeating the action.

The completed item leaves Needs review and is available in History. It shows
**Review complete** with no further review action required. **No model confidence**
or a low original score can remain visible after completion; those are historical
extraction evidence. On Extraction, unchanged checked fields can show **Reviewed**
and changed fields **Corrected**. Check the processing dashboard for later steps
and confirm final outputs; review completion does not itself prove all exports
finished successfully.

### Worked correction

The PDF shows an invoice total of `1,250.00`, but extraction shows `125.00`.
Claim the review, check that this is the final total rather than subtotal,
and enter `1250.00` in the amount control. Preview Diff should show only the
intended correction and any other deliberate edits. Save Draft if more work
remains, or complete after checking the remaining required fields and rows.
After processing finishes, verify the Final Value and the required export.
The source PDF remains unchanged.

## Claims, expiry and another session

Check **Claimed until** while working. Claims last for a limited period chosen
by the Admin. Save progress before a long break and Release if handing over.
Closing the browser is not a substitute for saving or releasing.

If saving reports that the claim expired or belongs to someone else, stop and
coordinate ownership. Note any unsaved intended corrections before reloading
or claiming again: the extraction-review page reloads saved data when a claim
is acquired. Return to the queue, refresh and claim when available, then compare
the saved draft with the PDF before reapplying any missing corrections. Do not
assume renewal preserves unsaved form entries. A saved draft is not a completed
review and remains work for the next reviewer.

If another session changed the item, reload its latest saved state after noting
your intended changes. If it is completed, inspect History; do not attempt to
overwrite it. Persistent claim or save errors need administrator investigation.

## When the form cannot be completed

Ask the Admin when a required fact is absent, the form has the wrong fields,
a valid choice/number cannot be entered, or a read-only value needs correction.
Give the batch/document identifiers, field label and exact message. Do not
invent a value to satisfy the form. Publishing a corrected form does not
automatically change a document already in review; let the Admin determine
how that existing item should be handled.

See [getting help](troubleshooting.md) for a handoff checklist.
