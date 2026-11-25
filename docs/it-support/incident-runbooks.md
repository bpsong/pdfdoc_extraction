# Investigate runtime incidents

| Item | Value |
| --- | --- |
| Audience | IT support and deployment owners |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-11-25 — repository/source review; no live deployment check. CSV lookup recovery scenarios verified in synthetic workflows |
| Applies to | Production application; SQLite schema 11 |

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

## CSV lookup is blocking release

1. Find the document and lookup task in its pinned pipeline version. Check the
   configured register under the worker and web accounts. A required missing
   result, ambiguity, and an unreadable or invalid CSV have different remedies.
2. For a pending valid lookup, compare the PDF, review inputs and candidate
   evidence. Correct inaccurate input and use **Revalidate**. If the match list
   is truncated, narrow the input or work with the register owner to repair the
   duplicates. A valid optional miss can use the configured continuation policy
   or the review action **Skip lookup** when offered.
3. If the original file is unavailable for rematching, locate its approved
   backup and compare the SHA-256 to `recorded_source_sha256` in the
   [authenticated review detail](../reference/api-contracts.md#csv-lookup-on-extraction-reviews).
   On Windows, `Get-FileHash -LiteralPath <approved-csv-path> -Algorithm SHA256`
   verifies the recovered file. Coordinate any restore to the pinned path with
   the register owner because it can change results for new documents. When the
   replacement is approved instead, the reviewer uses **Use current reference
   file** with a reason and checks the new result before **Complete Review**.
4. If the file changes again during review, revalidate and check the new
   evidence before completion. Recorded choices for unchanged inputs and
   completed lookup decisions can use their persisted evidence. If a completed
   review did not continue, confirm document state and registered outputs,
   then use the [document resume contract](../reference/api-contracts.md#csv-lookup-on-extraction-reviews).
   A pipeline change applies to new assignments. Escalate disputed or failed
   work using safe identifiers and preserve the existing files and decision history.

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
