# Submit documents

| Item | Value |
| --- | --- |
| Audience | Operators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

Use the pipeline and version approved for your document type. One browser
submission uses one pipeline for the whole batch. Submit separate batches for
documents needing different processes; choosing a similar name just to proceed
can produce the wrong fields, review form and output.

Go to [browser upload](#upload-through-the-browser),
[interrupted uploads](#if-transfer-is-cancelled-or-acceptance-is-uncertain), or
[incoming folders](#use-an-incoming-folder).

## Prepare your PDFs

Check that each file is a real, complete PDF that opens normally and contains
all expected pages in order. Renaming another file type to `.pdf` does not
convert it. Use a readable scan; if pages are illegible, extraction and review
cannot reliably recover their contents. Ask for a better source where possible.

Confirm whether the chosen pipeline accepts bundles containing several documents
or expects one document per PDF. A multi-page invoice is still one document;
it should not be split into one invoice per page. Ask your administrator if
the correct intake is unclear. Avoid including unrelated documents in the same
bundle without an agreed processing method.

Keep the source available until you have confirmed acceptance and the required
outcome. The app manages its working filenames; you do not need to rename its
internal files or move processing folders yourself.

## Upload through the browser

1. Sign in and select **Upload & Process**.
2. Under **1. Select a pipeline**, select the correct name and published version.
   Expand **Pipeline details** for its description. Details do not select it;
   check its selection control before continuing.
3. If the required pipeline is absent, select **Refresh** once. If still missing,
   ask your administrator. Do not substitute an unapproved pipeline/version.
4. Select or drag PDFs into the upload area. Keyboard users can focus the area
   and press **Enter** or **Space** to choose files.
5. Check **Selected Files**, the file count and total size. Remove unintended
   or invalid entries. If **Start processing** is unavailable, check pipeline
   selection, the file list and displayed validation messages.
6. Select **Start processing** once. Keep the page open during transfer; the app
   opens the accepted batch's processing dashboard afterward.
7. Check the dashboard's assigned pipeline/version, filenames and statuses.
   Record the batch identifier for later lookup or support.

### File and batch limits

The usual defaults are **20 PDFs**, **50 MB per file**, and **200 MB per batch**.
Your deployment can set different limits: follow those displayed on the page.
A batch very close to the total limit can be rejected because the transfer also
contains file information. Leave some room below the limit.

If too many files or the combined size exceeds the limit, submit smaller groups.
If one PDF exceeds the per-file limit, ask your administrator for an approved
way to reduce or divide it while preserving required content. The manual split
review happens after acceptance; it cannot make an oversized upload acceptable.
If the app says upload capacity is full, wait briefly and retry as instructed.

## If transfer is cancelled or acceptance is uncertain

The upload percentage describes transfer from your browser, not extraction,
review or final output. **Cancel upload** stops that transfer attempt; the
application may already have accepted the work. A lost connection has the same
uncertainty. Do not assume that cancellation removed an accepted batch.

1. Read the status and error. The app attempts to check whether the submission
   was accepted and can open that batch automatically.
2. If a batch opens, follow it; do not start another upload just because the
   previous transfer looked interrupted. Check Reports if you need to confirm it.
3. If the page says acceptance is unconfirmed and directs a retry, keep the same
   browser tab and retry the same files with the same pipeline/version. Select
   **Start processing** when available. This lets the app recognise the same
   submission attempt; changing the files/version or starting in another tab
   can create a separate submission.
4. If the selected version is no longer eligible, read the refreshed selection
   message and confirm the correct replacement with your administrator. Do not
   choose another version only to clear the message.
5. If you still cannot establish acceptance, contact the administrator with the
   time, filenames, pipeline/version and message before starting new work.

After a page reload, the same tab can show **Checking previous upload acceptance**
or ask you to select the same files and pipeline again. Follow that guidance.
The app's retry protection is for recognising a submission attempt; it is not
a promise that every repeated upload of the same PDF will be rejected.

If the message says **Previous upload history was cleaned up**, ask whether
processing again is intended. The earlier records may have been removed while
files were kept. A deliberate new upload is different from recovering the
original attempt.

## Use an incoming folder

1. Confirm the exact folder, accepted document type and expected processing
   time with your administrator. Its pipeline/version is assigned by the Admin;
   you do not select one from the folder.
2. Follow the agreed copying procedure and place complete PDFs there. Allow
   copying to finish. Do not move or edit a file while the app is taking it in.
3. Open **Reports**, find the new batch and select **Open processing dashboard**.
4. Check each document and complete any requested split or extraction review.
5. Confirm final results and required files, just as for browser uploads.

A file leaving the incoming folder means it was taken in, not that processing
finished. A file remaining there with no batch may indicate paused intake or
an access problem. Check the agreed path and Reports, then ask the administrator;
avoid repeatedly copying it or submitting it through the browser at the same time.

## Choose the right settings

The chosen version determines extraction fields, review requirements and outputs.
Publishing new settings does not change documents already accepted or make an
old retry use the latest version. An administrator explicitly changes incoming
folder assignments for future files. If the wrong pipeline accepted a document,
report the batch before resubmitting so duplicate work can be accounted for.

Continue with [monitoring and results](monitoring-and-results.md).
