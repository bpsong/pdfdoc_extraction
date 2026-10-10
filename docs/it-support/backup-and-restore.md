# Back up, restore and maintain deployment storage

| Item | Value |
| --- | --- |
| Audience | IT support and deployment owners |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Backup and Recovery

For a complete operational backup, include:

- the SQLite database file configured at `database.path` (including templates,
  drafts, immutable versions, dependencies, and ingress bindings)
- task-owned output folders such as `files/`, `data/`, `archive_folder/`, and any split task `split_dir` used by configured tasks
- reference CSVs, deployment configuration, and any portable configuration
  exports retained by your organization

Stop the application before copying the SQLite database, or use SQLite's
online backup mechanism. Do not assume that copying only the main database
file while the service is running captures the complete state; account for
SQLite WAL/SHM files or use a consistent SQLite backup operation. Capture the
database and durable artifacts from the same backup point.

Restore the database and durable artifacts from the same backup point. If the
database is restored without the files, the UI may show registered artifacts
whose paths no longer exist. If files are restored without the database,
batch/task/review history and the exact executable versions needed for resume
will be incomplete. Do not reconstruct an interrupted run from the newest
draft or version. A legacy deployment YAML can be imported as a draft during
migration, but import never publishes and never replaces an already pinned
definition.


## Backup procedure

1. Record the deployed code revision, schema version, active YAML path, database
   location and all task-owned durable artifact/reference paths.
2. Pause intake and arrange a maintenance window. For a filesystem-copy backup,
   stop the supervised app and verify its child processes and other writers
   have stopped. An online database backup alone does not coordinate file changes.
3. Capture the consistent database, durable PDFs/exports/reference files and
   deployment configuration at the same recovery point. Protect secret-bearing
   configuration and backups using the approved access/encryption policy.
4. Check the captured files and record the backup time, revision and storage
   locations. Rehearse restore in an isolated environment before relying on it.
5. Restart and verify readiness and affected work before resuming intake.

## Restore procedure

1. Agree the recovery point and how to handle work accepted after it. Preserve
   the current deployment and evidence before replacing anything.
2. Stop the app and other writers. Restore a matching database, durable files,
   references, configuration and compatible application artifact. Keep paths
   consistent or reconcile them with the registered artifact paths.
3. Validate configuration and start through `main.py`. Check exact schema
   acceptance and every supervised component. Schema 9 has no supported downgrade.
4. Verify both logins, representative batches, pending reviews, pinned versions,
   folder assignments and readable source/output artifacts. Inspect interrupted
   work using [incident runbooks](incident-runbooks.md).
5. Test in isolation with synthetic input where possible, record the result and
   obtain the operational owner's agreement before resuming intake.

Exporting a pipeline/form captures its definition, not a full operational backup.
Processing-history cleanup retains physical files but removes their app links;
restoration requires a compatible database backup, not merely those PDFs.

## SQLite storage and compaction

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
