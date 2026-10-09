# Watch-folder administration reference

This reference contains the administrative and schema details for watch-folder
bindings. The main [architecture document](design_architecture.md#watch-folder-administration)
covers the claim/worker boundary and the invariant to preserve when changing it.

## Binding lifecycle

`/app/admin/watch-folders` manages binding configuration. A binding is enabled,
paused (assignment retained), unbound (assignment cleared), or retired (disabled
and immutable). Paused and unbound paths remain reserved. Retired paths are
reusable through a new binding identity; historical batch references remain
intact. Only unreferenced settings may be permanently deleted. Lifecycle
actions do not delete source directories or PDFs.

## Pipeline archiving and history cleanup

Before archiving a pipeline, set it inactive and resolve every enabled binding
pointing to it: pause, reassign, unbind, or retire the binding. The archive dialog
lists linked folders and blocks confirmation while an enabled binding remains.
Paused bindings retain their exact assignment and reserved path. Archiving does
not stop already pinned jobs or reviews, and does not remove watch-folder
configuration, directories, or PDFs. Archived pipelines cannot be restored.

**Clean up processing data** is a separate action on the Pipeline page. It can
remove eligible whole batches from binding activity history and Reports while
retaining binding settings, health observations, and original audit events.
Removing all batch references may make a binding eligible for the
existing separate settings-delete action; cleanup never invokes that action.
See the [pipeline retention guide](pipeline_retention_admin_guide.md) for cutoff,
review protection, storage, and confirmation rules.

## Persistence and revisions

Schema version 7 rebuilds binding constraints to allow nullable assignments and
adds retirement timestamps and optimistic revisions. The migration preserves
binding IDs and checks foreign keys before committing. Configuration changes
advance revisions; monitoring observations do not. Pause, unbind, and retire do
not require a healthy filesystem or executable assignment.

Before each file claim, the coordinator re-reads the binding under SQLite's
write lock, verifies the source directory and exact-version eligibility, and
serializes the claim against administrative mutations. A started claim may
finish before an update; subsequent claims use the current configuration. New
batch metadata retains the source folder and binding revision. Earlier records
are not backfilled with guessed source snapshots.

## Health and access checks

`watch_folder_health` stores scan, success, and ingestion timestamps, scan
issues, and ignored-file counts. The UI distinguishes configuration state from
scan health; missing or old observations are stale after the larger of 30
seconds or three poll intervals. Test access/Check run non-ingesting directory
existence/listing checks in the web process. They do not test destructive
filesystem permissions, enqueue work, start a watcher, or replace coordinator
scan timestamps.

The page presents exact-version upgrades, lifecycle confirmations, filters,
bounded activity history, and binding-scoped Reports links. Audit Log includes
the existing `admin_` event family and `watch_binding.*` configuration events.
