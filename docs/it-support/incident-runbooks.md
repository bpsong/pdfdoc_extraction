# Investigate runtime incidents

| Item | Value |
| --- | --- |
| Audience | IT support and deployment owners |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Establish scope and preserve evidence

Confirm the active deployment YAML/database, run ID, failed component and first
observed time. Capture the batch, document, job or review identifier and pinned
pipeline version. Use Reports/Failures, admin runtime health and role logs;
developers can trace persistence using [execution walkthroughs](../developer/execution-walkthroughs.md).
Keep resolved secrets and raw document values out of shared evidence.

## App does not become ready

1. Inspect the supervisor log, then web/worker logs for the first failure.
2. Run [config-check](config-check-troubleshooting.md) against the intended YAML.
   Check required folders, deployment-account permissions, database access and
   the exact supported schema.
3. Use the matching artifact and normal parent migration path. Back up before
   upgrade repair. The validator does not migrate and an older artifact cannot
   safely open an unsupported newer schema.
4. Restart through the supervisor after addressing the cause. Verify every
   component before resuming intake.

## Upload accepted but no processing begins

1. Confirm the batch exists before asking the operator to submit again.
2. Inspect worker heartbeat/logs and queued job/lease state through supported
   diagnostics. The web process accepts uploads; the worker runs queued roots.
3. Check for supervisor shutdown, provider delays and exhausted attempts.
   Expired job leases can requeue after interruption, subject to attempt limits.
4. Restore worker availability and observe the existing job before choosing a
   new submission. External side effects may already have happened; lease
   recovery does not guarantee exactly-once provider/storage execution.

## Incoming-folder file never appears in Reports

Check the binding is enabled, assigned to the intended eligible published
version, and healthy in the current run. Test listing access under the app
account, then inspect the coordinator log/health observations. Check file type,
copy completion and conflicts with another bound path. **Check now** does not
ingest a PDF or prove move/delete permissions. Verify with one approved synthetic
file after fixing the cause; avoid duplicate customer submissions.

## Review or saved split decision does not continue

Confirm the review kind, claim, draft revision and saved decision/application
phase. An extraction review resumes at the next task; manual split re-enters
its own pinned task to apply the accepted decision. Do not confuse HTTP 202 or
**Decision saved** with completed downstream work.

Use the offered manual **Retry continuation** only for unapplied accepted work
with no active attempt or queued children with no task runs. Started, failed
downstream, completed or ambiguous attempts require maintainer investigation;
the retry does not replay them. An abrupt crash can leave orphan split files.
See the exact [recovery boundary](../reference/tasks/splitting.md).

## Extraction failed or saved output is missing

Inspect the failed task, provider availability, configured secret alias/model,
timeouts and write permissions. Check existing files and registered artifacts
before retrying. Successful extraction does not prove storage completed.
History cleanup removes app file links while retaining physical files; ask the
admin whether cleanup occurred before treating those links as an incident.

## Close the incident

Verify readiness, affected work, review continuation and readable outputs.
Coordinate resumed intake and record the cause, recovery action and any work
needing reconciliation. Escalate ambiguous state to maintainers with safe IDs
and logs. Do not repair SQLite rows or delete workflow files while the app is
running; use supported recovery or a planned stopped-state repair/restore.
