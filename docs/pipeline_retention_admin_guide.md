# Pipeline archiving and processing-data cleanup

This guide explains what to click in DocFlow. Sign in with the **admin** account,
then select **Pipeline** in the left navigation menu. If the menu shows only
icons, point to an icon to see its name. Operator accounts cannot use these
administration controls.

You can archive a pipeline and clean up its old processing data separately.
Choose the action that matches what you want to do:

| Action | Purpose | Processing history | Files on disk |
| --- | --- | --- | --- |
| **Archive pipeline** | Retire an inactive pipeline and hide it from the default list | Retained; assigned jobs and reviews can continue | Retained |
| **Clean up processing data** | Delete eligible finished batches before a chosen UTC date | Deleted for the selected whole batches | Retained |

You can clean up history for an active, inactive, or archived pipeline. You do
not need to archive it first. Archiving alone does not delete history or save
database space. Neither action permanently removes the pipeline from the app.

You can follow all the steps below through the app. You do not need to run
commands, edit configuration files, or open the database. The optional technical
reference at the end is for your IT/support team.

## Find a pipeline or change its name

1. Select **Pipeline** in the left menu.
2. At the top of the page, open the **Pipeline template** dropdown and select
   the pipeline. Wait for its name and task list to finish loading.
3. If the pipeline is missing, tick **Show archived** beneath the pipeline
   details, then look in **Pipeline template** again.
4. To rename an active or inactive pipeline, edit **Name**, then press **Tab**
   or click outside the field. Wait for **Pipeline details saved**. There is no
   separate Save button for the name.
5. Check that the new name appears in the **Pipeline template** dropdown.

Changing the name does not save task edits. Use **Save Draft** in the
**Editing draft** panel to save those separately. An archived pipeline's name
and task settings cannot be edited.

## Archive a pipeline

Archiving stops new use of the pipeline and hides it from the usual list.
**An archived pipeline cannot be reactivated.** Its existing jobs and reviews
can still finish, and its history remains available unless you clean it up
separately.

1. Open **Pipeline** and select the pipeline in **Pipeline template**.
2. If you have unsaved task changes, click **Save Draft** in **Editing draft**.
   To discard only your unsaved changes instead, click **Refresh** at the top
   and accept the discard confirmation. **Reset draft to published version**
   also replaces the draft with the published settings, so use Refresh when you
   only want to abandon unsaved edits.
3. In **Availability status**, choose **Inactive**. Wait for the save message
   and check that the dropdown shows **Inactive**. This stops new intake;
   existing work continues. You do not need to click Publish.
4. Click **Archive pipeline** beneath the pipeline details. A confirmation
   window opens with the pipeline name, retained history, and linked watch folders.
5. Read any red messages. If enabled watch folders are listed, click **Cancel**,
   follow [Pause linked watch folders](#pause-linked-watch-folders), then return
   to **Pipeline**, select the same pipeline, and click **Archive pipeline** again.
6. Check the pipeline name and the consequences in the window. Click
   **Archive pipeline** inside the window to confirm, or **Cancel** to leave
   the pipeline unchanged. You do not need to type its name for archiving.
7. Wait for **Pipeline archived**. Check that **Availability status** now shows
   **Archived** and **Show archived** is ticked. The selected pipeline stays
   visible, but its editing controls are disabled.

To find it on a later visit, open **Pipeline**, tick **Show archived**, and select
it from **Pipeline template**. Untick **Show archived** to hide archived entries
again. If a message says the list could not refresh after a successful archive,
click **Refresh**; the pipeline has already been archived.

You can still inspect an archived pipeline or click **Clean up processing data**.
If it has a published version, **Clone** creates a separate inactive pipeline
from its latest published settings. Cloning does not restore the archived
pipeline or copy its history and watch-folder assignments.

## Pause linked watch folders

Pausing is the simplest option when you want a folder to stop sending new files
to the pipeline. Files already accepted for processing continue. Files waiting
in the folder stay there.

1. Select **Watch folders** in the left menu.
2. In **Search folders or pipelines**, enter the pipeline name or a folder path
   shown in the archive window. Leave the status filter on **All statuses** so
   you can see both enabled and paused folders.
3. Check each matching row's **Pipeline** and **Folder** columns.
4. For a matching row with status **enabled**, click **Pause** in **Actions**.
5. In **Confirm change**, read the message and click **Confirm**.
6. Check that the row's status changes to **paused** and its action becomes
   **Resume**. Repeat for every enabled folder using this pipeline.
7. Return to **Pipeline**, select the pipeline, and retry **Archive pipeline**.

A paused folder keeps its pipeline settings, and its path remains reserved in
DocFlow. If you want a different outcome, use these alternatives:

| What you want | Steps on Watch folders |
| --- | --- |
| Keep receiving files through a different pipeline | Click **Edit**, choose another active **Pipeline** and its **Published version**, set **Watch folder enabled** as needed, click **Save changes**, then **Confirm** |
| Keep the folder setting but remove its pipeline assignment | Click **Edit**, then **Unbind pipeline**, then **Confirm** |
| Retire the folder setting and allow its path to be used by a new setting | Click **Edit**, then **Retire binding**, then **Confirm**; tick **Show retired** to see it afterwards |

These actions do not delete the folder or its PDFs.

## Clean up processing data

Use this action to remove old, finished processing history from the app.
**Deletion cannot be undone in the app.** Save any information you still need
before continuing, and arrange a backup with your IT/support team if needed.

1. Select **Pipeline** in the left menu.
2. Choose the pipeline in **Pipeline template**. For an archived pipeline, tick
   **Show archived** first. Check the **Name** field to confirm your selection.
3. Click **Clean up processing data** beneath the pipeline details.
4. In **Finished before (UTC, exclusive)**, choose a date using the date field.
   Choose today or an earlier date; future dates are not accepted.
   Only batches whose processing activity finished before that date can qualify.
   For example, choosing **1 January 2026** keeps activity on or after
   **1 January 2026, 00:00 UTC** (**08:00 in Singapore**). The original upload date
   alone does not decide whether a batch is old enough.
5. Click **Preview cleanup**. No processing history has been deleted at this point.
6. In **Confirm cleanup**, review the eligible **Batches**, **Documents**, and
   other record counts. Read **Excluded whole batches** to see what will stay.
   The app keeps a whole batch if any of its documents still needs work.
7. Scroll down to the confirmation field. Type the pipeline name exactly as
   shown, including spaces and capital letters. **Delete processing data**
   becomes available only when the name matches and at least one batch qualifies.
8. To change the date, click **Back**, choose another date, and preview again.
   To cancel from the preview, click **Back**, then **Cancel**, or press **Esc**.
9. To proceed, click **Delete processing data** once and wait for the result.
10. Check for **Processing data cleaned up** and review the deleted counts.
    **Files deleted: 0** confirms that files on disk were left in place. Click
    **Done** to close the window.
11. Open **Reports** from the left menu to check the remaining history. Deleted
    batches no longer appear. Open **Audit Log** to inspect the recorded admin
    cleanup event if needed.

### Understand the excluded batches

The app checks every document in a batch, including documents created by
splitting a PDF. These messages explain why an entire batch stays:

| Preview category | Why the entire batch stays |
| --- | --- |
| Pending review or review lock | A review is not completed, or a review lock remains live |
| Active or resumable work | Processing or a split decision still needs work, or a reviewed document is waiting for processing to continue |
| On or after cutoff | Recorded processing activity is on or after the exclusive cutoff |
| Incomplete or linked history | The app cannot safely separate the batch from other history; ask your support team to investigate if it needs removing |

Failed processing is not automatically eligible for deletion. Any pending review
or work waiting to continue still protects the batch. Each excluded batch is
counted once, under its first applicable reason.

### If you cannot continue

| What you see | What to do in the app |
| --- | --- |
| Archive asks you to save or discard changes | Close the message, click **Save Draft**, or use **Refresh** and accept the discard confirmation, then retry |
| Archive confirmation is unavailable | Read the red messages; set **Availability status** to **Inactive** and pause or move every enabled linked watch folder |
| Cleanup shows zero eligible batches | Review **Excluded whole batches**; use **Back** to choose a later allowed date, or finish outstanding processing/reviews and preview again |
| **Delete processing data** stays disabled | Check that eligible **Batches** is greater than zero and type the displayed name exactly |
| Preview expired or processing data changed | The window returns to date selection; choose the date again, click **Preview cleanup**, review the new counts, and re-enter the name |
| Retained records reference this history | No history was deleted by that attempt. Cancel and contact your support team with the message |
| A pipeline is missing from the list | Tick **Show archived**, then check **Pipeline template** again |

Previews expire after 15 minutes. If someone changes the pipeline or processing
history while you are reviewing it, the app asks for a new preview before
deleting anything. A rejected cleanup attempt does not partially delete history.

## What cleanup removes and retains

Cleanup removes the selected batches' processing records: document history,
processing steps, extraction results, completed reviews and split decisions,
and the app's links to their files.

Deleted history disappears from **Reports**, batch/document pages, review pages,
and processing timelines. Application PDF/artifact links for removed records
stop resolving. Cleanup cannot be undone in the app; recovery requires an
appropriate database backup and a planned restore that accounts for newer work.

Cleanup retains:

- Pipeline settings, saved drafts, published versions, and review forms.
- Watch-folder settings and health information. Cleanup does not pause,
  disconnect, retire, or delete a watch-folder setting.
- Original audit records, even when the processing history they describe has
  been removed. A new event in **Audit Log** records the cleanup cutoff and
  record counts.
- Physical source/split PDFs, archives, CSV/JSON exports, and other files.
  The result shows **Files deleted: 0**.
- A small record of previous uploads to prevent accidental duplicates. If an
  old upload's history was cleaned up, the upload page explains this and waits
  for you to deliberately start a new upload.

Deleting history makes database space available for future work. The database
file may stay the same size, and PDFs and exports remain on disk. There is no
**Compact database** button in this workflow. If you need to reduce the database
file's size, ask your IT/support team to arrange separate maintenance.

## Optional technical reference for IT/support

The sections below describe database maintenance, APIs, and deployment. They are
not required for the app-based steps above. Cleanup is separate from the
configured **Archive PDF** task and automatic working-file housekeeping.

### SQLite storage and compaction

Deleting rows frees pages for reuse; the database file usually keeps its size.
`VACUUM` rebuilds it to reclaim space, can need up to twice its size in free disk
space, and can change implicit rowids. `VACUUM INTO` creates a compact separate
copy without replacing the original. See [SQLite VACUUM](https://www.sqlite.org/lang_vacuum.html).

SQLite also offers `auto_vacuum` modes, including incremental reclamation; they
require database preparation and do not provide full page compaction. See
[SQLite auto_vacuum](https://www.sqlite.org/pragma.html#pragma_auto_vacuum).
This feature does not configure them or run compaction.

For manual compaction, use a planned maintenance window, a verified consistent
backup, and sufficient free disk space. Stop DocFlow processes and other writers
before maintenance, then verify integrity and application startup. Treat audit
event IDs as stable identities rather than implicit rowids.

### API contract

All routes below require the fixed `admin` role. Cookie-authenticated POSTs
require the existing CSRF cookie and matching `X-CSRF-Token` header. The prefix is
`/api/admin/pipeline-templates/{template_id}`.

| Method and suffix | JSON request | Successful response |
| --- | --- | --- |
| `GET /archive-preview` | None | `template`, `counts`, `bindings`, `blockers`, `can_archive` |
| `POST /archive` | `{"confirmation_name":"Exact pipeline name"}` | `template` with archived status |
| `POST /cleanup-preview` | `{"cutoff_date":"2026-01-01"}` | `preview_id`, `expires_at`, `template_name`, `cutoff_date`, `counts`, `excluded` |
| `POST /cleanup` | `{"preview_id":"UUID from preview","confirmation_name":"Exact pipeline name"}` | `deleted`, `excluded`, `audit_event_id`, `receipts_tombstoned`, `files_deleted: 0`, `compacted: false` |

Archive `counts` includes `pipeline_versions`, `batches`, `documents`,
`active_jobs`, and `pending_reviews`; its binding entries include ID, folder path,
enabled state, and retirement timestamp.

Cleanup `counts` uses table names: `batches`, `documents`, `processing_jobs`, `task_runs`,
`extraction_results`, `extracted_fields`, `review_items`, `review_locks`,
`manual_split_decisions`, `document_files`, and `upload_submissions`. Receipts
are trimmed, not deleted; the result reports them separately from `deleted`.
`excluded` has `pending_review`, `active_work`, `recent_activity`, and
`inconsistent_history`, each with `batches` and `documents` counts.

Errors return `400` for invalid cutoff/name/input, `401` for missing/invalid
authentication, `403` for role/CSRF denial, `404` for an unknown pipeline, and
`409` for archive blockers, stale/expired/unavailable previews, no eligible
history, or retained record references. No delete endpoint exists for pipelines.

`GET /api/admin/pipeline-templates` excludes archived templates unless
`include_archived=true`. `GET /api/upload-submissions/{submission_id}` returns
`{"status":"purged"}` for a cleaned receipt. Reusing that identity does not
create another batch; start a new upload with a new idempotency key.

### Upgrade and verification

This release requires schema **9**. Normal `main.py` startup owns migration;
web/worker children verify it. The upgrade preserves audit events and their
rowids while removing processing-record foreign keys from `audit_events`, and
adds expiring cleanup previews. It does not delete processing history or files.

Deploy server code, templates, and static assets together. Do not start an older
schema-8 artifact against a schema-9 database. See
[deployment and rollback](frontend_deployment.md) and the
[implementation and verification record](../tasks/tasks-pipeline-archive-cleanup.md).
