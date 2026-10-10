# Manage incoming watch folders

| Item | Value |
| --- | --- |
| Audience | Application administrators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

A watch-folder **binding** is the saved assignment of an incoming folder to
one published pipeline version. IT/support supplies the approved path and
prepares access for the computer and account running the application.

## Prepare intake

Choose a folder for one agreed document process. Confirm with IT that incoming
PDFs are complete before they are placed there, that the application account
can access it, and that the watcher is running. Publish and test the pipeline
and its matching review form using a controlled upload first. A watch folder
selects one exact published pipeline version; it does not choose document types
or switch extraction fields automatically from a PDF's content.

If a folder contains bundles, its assigned pipeline must have the appropriate
split step. If it contains unrelated document types needing different fields,
arrange separate intake paths or another supported routing process.

## Add a folder

1. Sign in as **admin**, open **Watch folders**, and select **Add watch folder**.
2. Enter **Folder path** and select **Test access**. If it fails, give IT the
   path and displayed message. A folder you can open may still be inaccessible
   to the application.
3. Select the **Pipeline** and **Published version** for this document type.
4. Set **Watch folder enabled** as needed and select **Save changes**.
5. Check status and health. Submit one approved test PDF and find its batch in
   **Reports** to verify that both intake and processing work.

For initial rollout, save the setting with **Watch folder enabled** clear until
you are ready for the controlled folder test. Enable/resume it in the agreed
window and check the resulting confirmation. Follow the sample through review
and actual output files before announcing routine availability.

## Change the assigned version

Select **Edit**. Choose the intended pipeline/version, or **Use latest version**
to select the newer published version. Select **Save changes** and **Confirm**
when asked. Test the change. Future intake uses the new assignment; documents
already accepted keep their original one.

For a planned change, record the old assignment, pause the folder, and coordinate
with the people supplying PDFs. Publish and test the new pipeline before choosing
its version here. **Use latest version** selects the latest published version
available when you apply the change; it is not a subscription to future versions.
Check the saved version number, resume, then process one controlled sample and
check its document details. Other folders keep their own assignments.

If that sample fails, pause intake again. Choose the recorded known-good
published version if available, save/confirm and test before resuming. Accepted
documents remain on their original versions; changing a folder does not repair
or rerun them. If an incoming PDF never appears in Reports, involve IT instead
of repeatedly changing field definitions.

## Pause, disconnect or retire a folder

| Action | Result |
| --- | --- |
| **Pause** | Stops new intake and keeps the assignment and reserved path |
| **Resume** | Restarts intake when the assignment and access are suitable |
| **Unbind pipeline** in Edit | Removes the assignment and keeps the path reserved |
| **Retire binding** in Edit | Ends use of this setting and releases its path for a new setting |
| **Delete unused binding** | Removes a setting only when no historical batches refer to it |

Confirm lifecycle changes and check the resulting status. These actions leave
the folder and PDFs in place. Pausing does not cancel accepted processing.
Use **Show retired** to inspect retired settings.

## Check health and history

Search by folder or pipeline; use status, health and **Updates available** filters.
**Check now** checks folder access but does not submit a PDF or prove processing
is running. **Activity** shows recent intake and links to Reports. Health that
stays stale, inaccessible folders or PDFs that never appear in Reports need
IT/support investigation.

| Observation | What to do |
| --- | --- |
| Pipeline/version cannot be selected | Check it has a published version and is active; archived definitions are unavailable for new intake. |
| Path is already reserved | Look for an existing paused, unbound or enabled setting. Edit/reuse it, or retire it when appropriate; Pause does not release the path. |
| Test access passes but no batch arrives | Check the setting is enabled, then ask IT to check the running watcher. Access testing alone does not prove intake is active. |
| Updates available | Review the new pipeline version and test it before deliberately changing the assignment. |
| Health is stale | Ask IT whether the application/watcher is running; stale health is different from a fresh successful check. |
| PDF enters review | Follow its required split/data review. Pending review is not a folder-access fault. |

Give support the folder setting/path, pipeline and selected version, time of
submission, displayed health/error and batch identifier if one exists. Share
document content only through an approved channel.

Before archiving a pipeline, pause or reassign all enabled folders pointing to
it. [History cleanup](archiving-and-retention.md) can remove old batch activity
while retaining the folder settings and health information.
