# R3 CSV reference lookup and enrichment, 2026-11-25

| Item | Value |
| --- | --- |
| Audience | Operators, administrators, IT support and maintainers |
| Owner | Application maintainers |
| Status | Historical record |
| Last verified | 2026-11-25 — isolated Windows SQLite deployment, offline extraction, real storage and Chromium |
| Applies to | R3 CSV lookup release and SQLite schema 11 |

## What changed

Administrators can publish a read-only CSV lookup that adds text to effective
document data. The task supports independent match policies and copies returned
identifiers such as `00042` into JSON, CSV and filenames. Reviewers resolve
ambiguity with recorded evidence or hold release for an unresolved required
lookup. SQLite schema 11 persists decision revisions for pinned documents and
their split children. Release uses the same effective values on a direct run
and after an accepted review.

## Who is affected and what to do

- Administrators can start with the [supplier lookup example](../../reference/tasks/rules-context-housekeeping.md#synthetic-supplier-example)
  and validate the pipeline before activation.
- Operators can [resolve a lookup](../../operator/reviewing-extracted-data.md#resolve-a-csv-reference-lookup)
  using the source PDF, candidate evidence and a recorded reason.
- IT support should verify [register access on Windows](../../it-support/configuration-and-access.md#prepare-a-csv-lookup-register),
  retain approved reference bytes under the backup policy, and follow the
  [recovery runbook](../../it-support/incident-runbooks.md#csv-lookup-is-blocking-release)
  if a paused review needs to rematch.

The [archived R3 implementation record](../../../tasks/archive/tasks-r3-csv-reference-lookup.md)
contains the exact test commands, the clean 2,154-pass full suite and five
skips, Chromium screenshots, and the final example verification. The
[roadmap](../../../tasks/roadmap.md#r3-csv-reference-lookup-and-enrichment)
records completion on SQLite.
