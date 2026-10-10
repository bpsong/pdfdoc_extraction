# Architectural decisions and constraints

| Item | Value |
| --- | --- |
| Audience | Software architects and technical leads |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Key architectural decisions

1. **SQLite owns operational state.** New workflow-state features use
   repositories and services rather than status files.
2. **The filesystem owns large artifacts.** SQLite records artifact role,
   path, and metadata rather than file contents.
3. **Pipeline composition is stored and versioned.** An editable SQLite draft
   defines task order, implementation, parameters, and error behavior.
   Publication creates an immutable executable version; YAML/JSON remain
   portable import/export formats.
4. **Workflow control is application-managed.** SQLite and workflow context
   drive progress, pause, resume, failure, and split behavior.
5. **Backend responsibilities are layered.** Routes handle HTTP concerns,
   services handle use cases, and repositories handle table-specific storage.
6. **Production and prototype UI are separate.** Production behavior belongs
   under `web/`; `pipeline_visual_editor_prototype/` is not loaded at runtime.

### Invariants to preserve

- Every accepted document is pinned to one immutable pipeline version.
- A review item is pinned to the exact review-schema version used by its
  pipeline version.
- The worker is the only normal executor of queued root workflows.
- The parent is the only normal migration owner.
- SQLite owns workflow state; the filesystem owns artifact contents.
- Published pipeline and review-schema versions are immutable.
- Review completion can acquire downstream resume only once.
- Upload idempotency applies only to the same key, user, pipeline, and content.
- Legacy YAML pipeline/task definitions are import sources, not runtime state.


## Rationale and consequences

| Decision | Rationale | Consequence to account for |
| --- | --- | --- |
| SQLite owns state | Durable local transactions join jobs, reviews, versions and audits | Schema upgrades and local write contention are application concerns |
| Filesystem owns large artifacts | PDFs and exports remain ordinary files with registered metadata | Database and artifact backups must represent the same recovery point |
| Exact immutable versions | Accepted work remains reproducible across configuration changes | New publication needs an explicit intake assignment change |
| One supervised worker | Durable acceptance is separate from execution in a simple local topology | This is not a distributed worker pool or a multi-host queue |
| Application-managed review resume | Human decisions survive process restarts in the state store | Continuation is reconstructed; some interrupted side effects are ambiguous |
| Layered services and repositories | Cross-table invariants have one business owner | Route and repository changes must preserve that ownership |

These rationales explain the current implementation. They do not establish a
new target architecture or promise unimplemented recovery behaviour.

## Known architectural debt

| Area | Current constraint |
| --- | --- |
| Workflow contract | Weakly typed mutable context dictionary |
| API composition | Large `api_router.py` integration surface |
| Configuration | YAML, SQLite settings, and versions have different semantics |
| Execution | One SQLite-backed worker and lease recovery; no distributed worker pool or multi-host coordination |
| Throughput | Sequential watch-folder and split-child processing |
| Persistence | SQLite write-concurrency ceiling and coarse migrations |
| I/O | Blocking file and provider operations in local processes |
| Capacity | No measured or supported documents-per-day capacity target |
| Review | New-flow resume rather than durable engine suspension |
| Compatibility | Legacy SQLite response shapes remain; filesystem status is removed |
| Frontend | Large controllers and implicit DOM/API contracts |
| Secrets | Provider credentials may reside in local runtime YAML |
| Storage | Artifact availability assumes shared local filesystem access |

These are current constraints, not an approved target-state plan.

Task cleanup handles workflow-owned temporary files, and upload reconciliation
removes upload-owned orphans after interrupted submissions. This document does
not define an automatic retention period, orphan scan for all artifact roles, or
log rotation policy. Explicit admin processing-history cleanup is separate from
task housekeeping and retains physical files; neither performs compaction.


## Record future decisions

When a change alters process, persistence, workflow or trust ownership, record
the date, problem, considered options, chosen decision, consequences and links
to implementation and verification. Mark an earlier decision superseded and
link its successor; retain the old rationale. Keep proposed designs clearly
labelled and separate from implemented contracts.
