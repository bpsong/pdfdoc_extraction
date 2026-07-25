# Implementation Plan: Multiple Versioned Pipeline Templates and Review Schemas

## Document status

| Item | Value |
| --- | --- |
| Purpose | Executable, checkbox-based implementation plan |
| Design authority | [Design: Multiple Versioned Pipeline Templates](design-multiple-pipeline-templates.md) |
| Audience | Coding agents, reviewers, test owners, and maintainers |
| Scope | Versioned pipelines, versioned review schemas, ingestion selection, execution pinning, migration, UI, CLI, testing, and focused documentation |
| Deferred | Mixed-document cross-pipeline routing and `workflow_runs` |
| Completion rule | Complete only after Phases 1-15 and the final requirement audit are checked |

## How to execute this plan

- Work phases in order unless a task explicitly says it may run in parallel.
- Before starting, identify the next unchecked task and verify every listed
  prerequisite is checked.
- Mark a subtask `[x]` immediately after its implementation and required
  verification pass.
- Mark a phase parent `[x]` only after every required child task, focused test
  command, and exit criterion in that phase is complete.
- Every implementation phase (Phases 1-12) has a mandatory focused unit-test
  gate. A phase cannot be completed using integration or visual tests as a
  substitute for its unit tests.
- Add newly discovered required work to the appropriate phase rather than
  leaving it only in chat, code comments, or review notes.
- Keep the **Relevant Files** section current with every file created or
  materially changed.
- Preserve user changes in a dirty worktree. Do not stage, commit, discard, or
  reformat unrelated files unless explicitly requested.
- Use `.\.venv\Scripts\python.exe` for every Python command and run tests from
  the repository root.
- Do not run live LlamaCloud checks unless separately authorized with explicit
  credentials.
- Visual testing begins only after all coding and non-visual automated testing
  are complete.
- Documentation updates begin only after visual testing passes. Keep them
  narrow, additive, and aligned with the implemented behavior; do not remove
  still-relevant operational or historical content.

## Outcomes

- Pipelines and review schemas have independent SQLite-backed templates,
  optimistic-concurrency drafts, and immutable published versions.
- Pipeline versions reference exact review-schema versions through normalized
  dependency rows.
- Upload and watch-folder ingestion pin one authorized published pipeline
  version before work is accepted.
- Root documents, split children, task runs, review items, retries, resume, and
  supported recovery paths use immutable pinned definitions.
- Runtime execution does not load global YAML `pipeline`/`tasks`, mutable
  filesystem review schemas, or an implicit latest version.
- `config-check` validates deployment YAML, stored SQLite objects, and portable
  import/export files through shared validators.
- Existing databases, configuration, review schemas, and non-terminal work are
  migrated only when the compatibility gates can prove a safe mapping.
- Existing task approval, security, artifact, review locking, split fan-out,
  leaf fan-in, audit, and local-filesystem business-artifact contracts remain
  intact.

## Non-goals

- Automatic classification or pipeline selection.
- Per-file pipeline selection within one upload batch.
- Cross-pipeline routing for split children.
- Arbitrary workflow graphs, conditional edges, joins, or user-authored code.
- `workflow_runs` or multi-pipeline execution by one document.
- Distributed workers, multi-host execution, or general interrupted-flow
  recovery.
- Deleting immutable versions or rewriting historical business results.
- Replacing SQLite or moving PDFs and other large artifacts into SQLite.

## Phase dependency map

```text
1 -> 2 -> 3 -> 4 -> 5
5 -> 6
5 -> 7
1-5 -> 8
3-4 -> 9
9 -> 10
6 + 9 + 10 -> 11
1-4 + 8 -> 12
1-12 -> 13 integration/security/full regression
13 -> 14 visual and accessibility testing
14 -> 15 focused documentation and final audit
```

Phases 6, 7, 9, and 12 may be developed in parallel only after their displayed
prerequisites are complete. Their final integration remains gated by Phase 13.

## Relevant files

Keep this list updated throughout implementation.

### Design and planning

- `tasks/design-multiple-pipeline-templates.md` — authoritative behavior and
  target architecture.
- `tasks/tasks-multiple-versioned-pipeline-templates.md` — this checklist.
- `tasks/future-multi-document-routing.md` — original multiple-template
  direction.
- `tasks/future-mixed-document-routing.md` — explicitly deferred routing
  extension.

### Persistence and services

- `modules/db/schema.sql` — new versioned-configuration tables, assignment
  columns, indexes, foreign keys, and triggers.
- `modules/db/migrations.py` — ordered schema version 3 upgrade and legacy
  import/cutover.
- `modules/db/repositories.py` — table-specific persistence.
- `modules/db/connection.py` — nested transaction support for atomic
  cross-repository ingestion and split operations.
- `modules/services/schema_service.py` — transition from filesystem runtime
  schemas to stored draft/version access and import/export support.
- `modules/services/pipeline_config_service.py` — current single-pipeline
  service to replace with template-scoped behavior.
- `modules/services/pipeline_validation_service.py` — shared explicit-source
  validation.
- `modules/services/workflow_state_service.py` — pinned task-run attribution.
- `modules/services/processing_state_service.py` — pinned version snapshots
  and display grouping.
- `modules/services/review_service.py` — review-item schema version identity.
- `modules/config_manager.py` and `modules/config_protocol.py` — deployment
  configuration and secret-alias access after global pipeline/schema cutover.
- New versioned configuration, review-schema, pipeline-template,
  pipeline-definition, ingestion-assignment, binding, validation-facade, and
  portable-bundle service modules introduced by this plan.
- `modules/services/pipeline_definition_service.py` — exact-version runtime
  loading, dependency verification, approval checks, and transient secret
  resolution.
- `modules/services/ingestion_assignment_service.py` — authorized, atomic
  upload/watch assignment.
- `modules/services/ingress_binding_service.py` — watch-folder path and
  lifecycle policy.
- `modules/services/watch_folder_coordinator.py` — serialized binding
  reconciliation, claiming, and processing.
- `modules/services/legacy_versioned_config_migration.py` — guarded v2
  schema/YAML import, compatibility checks, backfill, and compensation.
- `modules/services/batch_service.py` — assignment propagation during batch
  and root-document creation.

### Runtime and ingestion

- `modules/workflow_loader.py` — explicit executable definition loading.
- `modules/workflow_manager.py` — pinned root/child workflow orchestration.
- `modules/resume_manager.py` — pinned review resume.
- `modules/file_processor.py` — assignment-aware ingestion handoff.
- `modules/watch_folder_monitor.py` — current single-folder implementation to
  adapt or replace.
- `main.py` — migration ordering, coordinator startup, and runtime composition.
- `standard_step/split/llamacloud_split.py` — atomic inherited assignment for
  split children and artifacts.
- `standard_step/review/review_gate.py` — exact stored schema-version use.

### API, UI, and CLI

- `modules/api_router.py` — versioned APIs and compatibility-surface cutover.
- `web/server.py` — authenticated page routes.
- `web/templates/schema_editor.html` and `web/static/js/schema_editor.js` —
  versioned Review Forms workspace.
- `web/templates/pipeline_config.html` and
  `web/static/js/pipeline_config.js` — template-scoped pipeline workspace.
- `web/templates/upload_process.html` and `web/static/js/upload_process.js` —
  required version selection.
- `web/templates/processing_overview.html` and
  `web/static/js/processing_overview.js` — pinned version presentation.
- `web/static/css/app.css` — production styling where existing utilities are
  insufficient.
- `tools/config_check/` — explicit-source validation CLI, portable contracts,
  reporters, and validators.

### Maintained documentation

- `docs/design_architecture.md` — implemented architectural boundaries.
- `docs/user_guide.md` — administrator/operator lifecycle and ingestion use.
- `docs/review_schema_admin_guide.md` — versioned Review Forms workflow.
- `docs/config_check_troubleshooting.md` — stored-source and portable-file
  findings.
- `tools/config_check/README.md` — future CLI commands and compatibility.
- `tasks/standard_task_creation_guidelines.md` — shared task contract changes
  only where the implementation requires them.

### Test locations

- `test/db/` — schema, repository, immutability, and migration tests.
- `test/services/` — domain, canonicalization, validation, assignment, and
  coordinator unit tests.
- `test/workflow/` and `test/standard_step/review/` — pinned execution and
  review schema behavior.
- `test/integration/` — APIs, ingestion, migration, pause/resume, processing,
  and security boundaries.
- `test/integration/test_pipeline_selection_upload_api.py` — exact upload
  selection and redacted availability API.
- `test/integration/test_watch_folder_binding_api.py` — binding API role,
  CSRF, lifecycle, and conflict behavior.
- `test/db/test_versioned_config_migration.py` and
  `test/integration/test_migration_startup_gate.py` — migration matrix,
  compatibility/compensation, and startup ordering.
- `test/workflow/test_versioned_workflow_execution.py` — pinned runtime,
  secret/schema dependency, loader isolation, and task-run attribution.
- `test/tools/config_check/` — stored-source and portable-file CLI tests.
- `test/security/` — role, CSRF, secret, path, and protected-file regression.
- `test/visual/` — final browser, responsive, accessibility, and redaction
  verification.

---

## Phase 1 — Shared contracts, canonicalization, and validation facade

**Prerequisites:** Design document accepted; current baseline tests recorded.

**Exit criterion:** All versioned configuration types have one canonical
representation, validators no longer require root-level YAML, and Phase 1 unit
tests pass.

- [x] **1.0 Record the baseline before changing configuration behavior**
  - [x] 1.1 Run focused existing tests for schema service, pipeline service,
    pipeline validation, and config-check.
  - [x] 1.2 Record any pre-existing failures in this plan under
    **Implementation Notes**; do not silently treat them as regressions.
  - [x] 1.3 Confirm `git status --short` and preserve unrelated changes.

- [x] **1.4 Add typed internal contracts**
  - [x] 1.5 Define typed structures for pipeline definitions, task
    definitions, review schemas, template/version summaries, schema
    dependencies, validation sources, secret references, and portable
    coordinates.
  - [x] 1.6 Keep transport DTOs separate from repository rows and runtime
    secret-resolved objects.
  - [x] 1.7 Define supported format/schema version constants and reject
    unsupported versions explicitly.
  - [x] 1.8 Ensure runtime objects cannot accidentally serialize resolved
    secrets.

- [x] **1.9 Implement canonical JSON and hashing**
  - [x] 1.10 Recursively sort object keys, preserve list order, emit UTF-8
    canonical JSON, and reject non-JSON values.
  - [x] 1.11 Hash unresolved definitions and normalized schema content with
    SHA-256.
  - [x] 1.12 Normalize pipeline keys, schema keys, task keys, lifecycle values,
    and portable coordinates without changing meaningful task order.
  - [x] 1.13 Provide deterministic redacted display snapshots derived from
    canonical definitions.

- [x] **1.14 Implement secret-reference and redaction primitives**
  - [x] 1.15 Accept only exact one-property `{"$secret": "alias"}` objects and
    the documented alias syntax.
  - [x] 1.16 Reject literal values under secret-like keys in versioned drafts
    and portable pipeline imports.
  - [x] 1.17 Resolve aliases only into non-serializable runtime copies.
  - [x] 1.18 Apply one shared recursive redactor to API, audit, CLI, diff,
    validation, and logging payloads.
  - [x] 1.19 Ensure redacted placeholders cannot overwrite an existing secret
    alias accidentally.

- [x] **1.20 Add a shared validation facade**
  - [x] 1.21 Refactor pipeline rules to accept an explicit parsed definition,
    dependency resolver, task-approval policy, and base path.
  - [x] 1.22 Refactor review-schema rules to accept explicit normalized schema
    content.
  - [x] 1.23 Preserve current task ordering, extraction, split, review,
    storage, rules, token, path, import, performance, and security checks.
  - [x] 1.24 Standardize source-qualified finding paths and stable finding
    codes.
  - [x] 1.25 Keep the existing YAML config validator operational until Phase
    12 completes the CLI cutover.

- [x] **1.26 Implement portable bundle conversion**
  - [x] 1.27 Define pipeline-bundle and review-schema import/export contracts.
  - [x] 1.28 Convert portable schema key/version/hash coordinates to local
    version IDs only through an explicit resolver.
  - [x] 1.29 Convert local version IDs back to portable coordinates on export.
  - [x] 1.30 Reject `latest`, missing hashes, duplicate dependencies, UUID/hash
    disagreements, and unresolved offline dependencies.

- [x] **1.31 Complete Phase 1 unit tests**
  - [x] 1.32 Add canonicalization tests for nested objects, list ordering,
    Unicode, numeric/boolean/null values, and invalid Python-only values.
  - [x] 1.33 Add hash stability and meaningful-change tests.
  - [x] 1.34 Add secret alias, resolution, rotation, redaction, and
    serialization-leak tests.
  - [x] 1.35 Add validation-facade source/path and existing-rule parity tests.
  - [x] 1.36 Add portable bundle round-trip, offline dependency, mismatch, and
    malformed-input tests.
  - [x] 1.37 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\services\test_versioned_config_contracts.py `
      test\services\test_pipeline_validation_service.py `
      test\services\test_schema_service.py
    ```

---

## Phase 2 — SQLite schema, constraints, and repositories

**Prerequisites:** Phase 1 complete.

**Exit criterion:** Fresh databases expose the complete target schema,
repository operations enforce table-level invariants, and Phase 2 unit tests
pass.

- [x] **2.0 Add target tables**
  - [x] 2.1 Add `review_schema_templates`, `review_schema_drafts`,
    `review_schema_versions`, and
    `pipeline_version_schema_dependencies`.
  - [x] 2.2 Add `pipeline_templates`, `pipeline_drafts`,
    `pipeline_versions`, and `watch_folder_bindings`.
  - [x] 2.3 Add documented lifecycle checks, timestamps, authorship fields,
    revision fields, canonical content, hashes, validation summaries, and
    unique constraints.
  - [x] 2.4 Add composite uniqueness needed to prove template/version
    ownership.

- [x] **2.5 Add assignment and review identity columns**
  - [x] 2.6 Add pipeline template/version, assignment source, and binding
    columns to batches.
  - [x] 2.7 Add pipeline template/version columns to documents.
  - [x] 2.8 Add pipeline version to task runs.
  - [x] 2.9 Add nullable `review_schema_version_id` to review items for
    schema-driven review scopes.
  - [x] 2.10 Add foreign keys and indexes for ingestion, execution, review,
    version history, binding lookup, and processing-state queries.

- [x] **2.11 Add immutability and assignment triggers**
  - [x] 2.12 Reject updates and deletes of published pipeline/schema content,
    hashes, numbers, ownership, and publication attribution.
  - [x] 2.13 Reject changing a non-null batch or document assignment.
  - [x] 2.14 Reject template/schema keys changing after first publication.
  - [x] 2.15 Preserve mutable template metadata and lifecycle fields.
  - [x] 2.16 Verify archived/inactive definitions remain readable through
    foreign keys.

- [x] **2.17 Add repository methods**
  - [x] 2.18 Add table-specific create/get/list/update methods for schema
    templates/drafts/versions.
  - [x] 2.19 Add table-specific methods for pipeline
    templates/drafts/versions/dependencies.
  - [x] 2.20 Add binding persistence and referenced-binding checks.
  - [x] 2.21 Extend batch/document/task-run/review repositories with explicit
    assignment-aware operations.
  - [x] 2.22 Do not expose generic update/delete methods for immutable rows.
  - [x] 2.23 Keep cross-table publication, assignment, and lifecycle policy out
    of repositories.

- [x] **2.24 Prepare the ordered migration framework**
  - [x] 2.25 Replace the coarse schema-only bump with an explicit idempotent
    version 2-to-3 upgrade entry point.
  - [x] 2.26 Add safe table/column/index/trigger existence checks.
  - [x] 2.27 Keep upgrade transactions bounded and foreign-key checks enabled.
  - [x] 2.28 Defer legacy content transformation to Phase 8 while providing
    fresh-schema initialization for service development.

- [x] **2.29 Complete Phase 2 unit tests**
  - [x] 2.30 Test fresh schema creation and every expected table, column,
    index, foreign key, and trigger.
  - [x] 2.31 Test repository happy paths, missing rows, pagination, revision
    fields, and JSON parsing.
  - [x] 2.32 Test composite ownership failures and invalid lifecycle values.
  - [x] 2.33 Test immutable update/delete rejection and mutable metadata
    updates.
  - [x] 2.34 Test assignment-change rejection and schema-review foreign keys.
  - [x] 2.35 Test transaction rollback leaves no partial version/dependency
    rows.
  - [x] 2.36 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\db\test_migrations.py `
      test\db\test_repositories.py `
      test\db\test_versioned_configuration_schema.py
    ```

---

## Phase 3 — Versioned review-schema domain

**Prerequisites:** Phases 1-2 complete.

**Exit criterion:** Review schemas can be created, edited, validated, published,
imported, exported, and resolved entirely through SQLite, with complete Phase
3 unit coverage.

- [x] **3.0 Implement schema-template lifecycle**
  - [x] 3.1 Create inactive schema templates with validated stable keys and
    revision 1 drafts.
  - [x] 3.2 Allow metadata updates and valid active/inactive/archive
    transitions.
  - [x] 3.3 Require a published version before activation.
  - [x] 3.4 Keep archived/inactive published versions loadable for pinned
    pipeline dependencies.
  - [x] 3.5 Prevent archived versions from being selected in a new pipeline
    draft.

- [x] **3.6 Implement optimistic schema drafts**
  - [x] 3.7 Require `expected_revision` for every save/import.
  - [x] 3.8 Increment revision atomically and return a conflict payload for
    stale writers.
  - [x] 3.9 Normalize current schema fields, types, required markers, enums,
    numeric constraints, objects, arrays, titles, and descriptions.
  - [x] 3.10 Keep draft content canonical and independent from browser state.

- [x] **3.11 Implement immutable schema publication**
  - [x] 3.12 Run full deterministic validation before publication.
  - [x] 3.13 Use `BEGIN IMMEDIATE`, recheck revision/hash, allocate the next
    per-template version, insert the immutable row, advance the draft base,
    increment revision, and audit in one transaction.
  - [x] 3.14 Reject unchanged publication and concurrent duplicate numbering.
  - [x] 3.15 Return version ID, number, hash, publication attribution, and
    non-secret validation summary.

- [x] **3.16 Replace runtime filesystem schema access**
  - [x] 3.17 Add SQLite-backed schema resolution by exact version ID.
  - [x] 3.18 Verify format version and content hash on load.
  - [x] 3.19 Keep explicit legacy-file reading only in migration/import
    adapters.
  - [x] 3.20 Preserve current schema payload validation behavior and safe
    error paths.

- [x] **3.21 Implement schema import/export**
  - [x] 3.22 Parse `.yaml`, `.yml`, and `.json` into canonical draft content.
  - [x] 3.23 Make import save a draft only; never publish implicitly.
  - [x] 3.24 Export drafts/versions with stable key, version/hash metadata and
    no local-only data that prevents portability.
  - [x] 3.25 Reject malformed, oversized, unsupported, or ambiguous imports
    without changing the current draft.

- [x] **3.26 Add schema audit events**
  - [x] 3.27 Record template lifecycle, draft save/import/validation,
    publication, and policy-required export events.
  - [x] 3.28 Store IDs, safe names/keys, versions, hashes, actor, and outcomes;
    never store full schema content in audit events.

- [x] **3.29 Complete Phase 3 unit tests**
  - [x] 3.30 Test every lifecycle transition and invalid transition.
  - [x] 3.31 Test stale drafts, concurrent publication, numbering, no-change
    rejection, rollback, and immutability.
  - [x] 3.32 Test all supported schema field types and invalid combinations.
  - [x] 3.33 Test YAML/JSON canonical equivalence, import rollback, and export
    round trips.
  - [x] 3.34 Test exact-version loading after newer publish, deactivate, and
    archive.
  - [x] 3.35 Test audit payload safety and content/hash verification.
  - [x] 3.36 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\services\test_review_schema_version_service.py `
      test\services\test_schema_service.py `
      test\services\test_schema_service_edge_cases.py
    ```

---

## Phase 4 — Versioned pipeline-template domain

**Prerequisites:** Phases 1-3 complete.

**Exit criterion:** Independent pipeline templates support safe drafts,
validation, exact schema dependencies, publication, clone, lifecycle, and
runtime retrieval, with Phase 4 unit tests passing.

- [x] **4.0 Implement template lifecycle**
  - [x] 4.1 Create inactive templates with validated key/name and revision 1
    empty drafts.
  - [x] 4.2 Lock the template key after first publication while keeping
    documented metadata mutable.
  - [x] 4.3 Require a published version before activation.
  - [x] 4.4 Enforce active/inactive/archive transitions and binding
    prerequisites.
  - [x] 4.5 Implement `operator_selectable` independently from admin access.

- [x] **4.6 Implement template-scoped drafts**
  - [x] 4.7 Replace the single `config_versions` draft lookup with
    template-scoped revision-controlled drafts.
  - [x] 4.8 Preserve ordered tasks, parameters, labels, and `on_error`.
  - [x] 4.9 Preserve masked secret references without accepting literal
    secret values.
  - [x] 4.10 Reject stale revisions with a complete current-revision response
    and no merge.

- [x] **4.11 Implement exact schema dependencies**
  - [x] 4.12 Replace `ReviewGateTask.params.schema_file` with
    `schema_version_id` in stored drafts.
  - [x] 4.13 Validate existence, publication, active selector eligibility,
    content hash, and review/extraction compatibility.
  - [x] 4.14 Insert one immutable normalized dependency row per review task
    during publication.
  - [x] 4.15 Verify JSON IDs and dependency rows agree on every load.

- [x] **4.16 Implement pipeline publication**
  - [x] 4.17 Normalize, validate, secret-check, and hash outside the write
    transaction.
  - [x] 4.18 Use `BEGIN IMMEDIATE`, recheck revision/hash and DB-dependent
    findings, allocate the next version, insert definition/snapshot/
    dependencies, advance the draft, and audit atomically.
  - [x] 4.19 Reject unchanged publication, invalid task approval, unresolved
    secrets, invalid schema dependencies, and concurrent stale publication.
  - [x] 4.20 Keep all prior versions eligible for explicit ingestion while the
    template is active.

- [x] **4.21 Implement clone and diff**
  - [x] 4.22 Clone the source latest published definition into a new inactive
    template draft without copying versions or bindings.
  - [x] 4.23 Preserve secret aliases as references only.
  - [x] 4.24 Produce canonical redacted draft/version diffs that never expose
    resolved secrets or full schema content.

- [x] **4.25 Add pipeline audit events**
  - [x] 4.26 Record metadata/lifecycle, draft save/import/validation,
    publication, clone, and policy-required diff/export events.
  - [x] 4.27 Include stable IDs, key/name snapshot, version/hash, actor,
    outcomes, and safe summary only.

- [x] **4.28 Complete Phase 4 unit tests**
  - [x] 4.29 Test two templates draft/publish independently without
    cross-template mutation.
  - [x] 4.30 Test key locking, lifecycle prerequisites, operator eligibility,
    clone behavior, and archived pinned-version access.
  - [x] 4.31 Test stale saves, concurrent publication, monotonic numbering,
    rollback, unchanged definitions, and immutable rows.
  - [x] 4.32 Test valid/missing/inactive/archived/mismatched schema
    dependencies and normalized rows.
  - [x] 4.33 Test secret references, redacted diff/export, task approval, and
    validation parity.
  - [x] 4.34 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\services\test_pipeline_template_service.py `
      test\services\test_pipeline_config_service.py `
      test\services\test_catalog_pipeline_edge_cases.py
    ```

---

## Phase 5 — Pinned runtime execution, split, review, and resume

**Prerequisites:** Phases 1-4 complete.

**Exit criterion:** Every workflow construction and continuation path uses the
document's immutable version and schema dependencies without global/latest
fallback, and Phase 5 unit/workflow tests pass.

- [x] **5.0 Implement the pipeline definition service**
  - [x] 5.1 Load exact pipeline/template/version rows and verify schema version
    and content hash.
  - [x] 5.2 Load normalized review-schema dependencies and verify their hashes.
  - [x] 5.3 Verify task JSON dependency IDs match normalized dependency rows.
  - [x] 5.4 Resolve secrets into a non-serializable runtime definition.
  - [x] 5.5 Recheck approved module/class pairs before workflow construction.
  - [x] 5.6 Fail closed with redacted setup errors; never fall back to active
    YAML or newest versions.

- [x] **5.7 Refactor workflow construction**
  - [x] 5.8 Remove or replace `WorkflowLoader` singleton behavior so
    definitions cannot leak between runs.
  - [x] 5.9 Construct the ordered flow from an explicit executable definition.
  - [x] 5.10 Calculate configured and internal cleanup indexes from that
    definition.
  - [x] 5.11 Add template/version IDs to internal context only as cached
    attribution; SQLite remains authoritative.
  - [x] 5.12 Ensure task input/output persistence excludes resolved task
    secrets.

- [x] **5.13 Pin workflow-state writes**
  - [x] 5.14 Record `task_runs.pipeline_version_id` at start.
  - [x] 5.15 Verify every task run matches the document assignment.
  - [x] 5.16 Scope completed-downstream checks to the pinned version.
  - [x] 5.17 Keep existing stop/continue, retry, fatal-failure, cleanup, and
    finalization semantics.

- [x] **5.18 Pin split fan-out/fan-in**
  - [x] 5.19 Copy parent template/version into every child row in the child
    creation transaction.
  - [x] 5.20 Start children after the split index using the child's pinned
    definition.
  - [x] 5.21 Run extraction preflight with resolved parameters from that
    definition.
  - [x] 5.22 Preserve child idempotency, compensation, artifact registration,
    and terminal-leaf fan-in.

- [x] **5.23 Pin schema-driven review**
  - [x] 5.24 Inject exact schema-version content into `ReviewGateTask`; remove
    filesystem lookup from published execution.
  - [x] 5.25 Persist `review_items.review_schema_version_id` and schema hash.
  - [x] 5.26 Verify task, dependency row, and review item identity agree.
  - [x] 5.27 Preserve confidence, required-field, split-confidence, correction,
    locking, and audit behavior.

- [x] **5.28 Pin review resume**
  - [x] 5.29 Load and verify the document's pipeline/schema dependencies before
    claiming `review_completed -> resuming`.
  - [x] 5.30 Compute the next task from the pinned version and reconstruct
    context from SQLite.
  - [x] 5.31 Leave the document resumable when a definition/secret fails before
    the claim.
  - [x] 5.32 Preserve exactly-once resume and downstream duplicate prevention.

- [x] **5.33 Complete Phase 5 unit and workflow tests**
  - [x] 5.34 Test version load/hash/secret/schema failures and redaction.
  - [x] 5.35 Test two concurrent documents using different definitions without
    loader cross-contamination.
  - [x] 5.36 Test task run attribution, cleanup index, continued failure, and
    no global/latest fallback.
  - [x] 5.37 Test split inheritance, retry idempotency, compensation, preflight,
    artifact registration, and fan-in.
  - [x] 5.38 Test review schema pinning, newer schema publication, inactive/
    archived schema access, item identity, locking, and exactly-once resume.
  - [x] 5.39 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\workflow\test_versioned_workflow_execution.py `
      test\workflow\test_workflow_loader.py `
      test\workflow\test_workflow_manager.py `
      test\services\test_resume_manager.py `
      test\standard_step\review\test_review_gate.py
    ```

---

## Phase 6 — Assignment-aware upload ingestion

**Prerequisites:** Phases 1-5 complete.

**Exit criterion:** Upload batches require and persist one authorized exact
version before background work begins, and Phase 6 unit/API tests pass.

- [x] **6.0 Implement ingestion assignment service**
  - [x] 6.1 Resolve the selected version, verify hash/dependencies/secrets,
    require published active template, and enforce current-role eligibility.
  - [x] 6.2 Atomically create batch, root documents, source artifacts,
    assignment source, and audit event.
  - [x] 6.3 Require all root documents in one batch to match the batch
    assignment.
  - [x] 6.4 Return a safe assignment summary for APIs and logs.

- [x] **6.5 Add available-pipelines API**
  - [x] 6.6 Add `GET /api/pipelines/available?source=upload`.
  - [x] 6.7 Return one redacted item per eligible published version, newest
    first, with operator guidance and step count.
  - [x] 6.8 Filter operators by `operator_selectable`; allow admins every
    active template.
  - [x] 6.9 Exclude inactive/archived templates and all task parameters.

- [x] **6.10 Update multipart upload**
  - [x] 6.11 Require exactly one scalar `pipeline_version_id` before writing
    accepted files.
  - [x] 6.12 Reject missing, repeated, malformed, unknown, unpublished,
    inactive, archived, corrupt, or unauthorized selections without fallback.
  - [x] 6.13 Preserve existing PDF validation, collision-safe paths, file
    compensation, grouped batch behavior, and CSRF/auth checks.
  - [x] 6.14 Pass authoritative IDs to background processing and reject caller/
    document mismatches.
  - [x] 6.15 Include a redacted pipeline summary in the response.

- [x] **6.16 Add upload assignment audit**
  - [x] 6.17 Record user, batch/documents, template/version IDs, version
    number, safe key/name snapshot, and outcome.
  - [x] 6.18 Ensure rejected submissions contain no file contents, secret
    values, or raw definitions.

- [x] **6.19 Complete Phase 6 unit and API tests**
  - [x] 6.20 Test assignment service authorization, transaction rollback,
    root-document equality, and audit payloads.
  - [x] 6.21 Test available-version role filtering and ordering.
  - [x] 6.22 Test all invalid selection classes and confirm no rows/orphan
    files/background tasks.
  - [x] 6.23 Test multi-file one-version behavior and later publication does
    not change the batch.
  - [x] 6.24 Test CSRF, authentication, content limits, PDF header, and cleanup
    regressions.
  - [x] 6.25 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\services\test_ingestion_assignment_service.py `
      test\integration\test_pipeline_selection_upload_api.py `
      test\integration\test_batch_upload_api.py
    ```

---

## Phase 7 — SQLite watch-folder bindings and coordinator

**Prerequisites:** Phases 1-5 complete.

**Exit criterion:** Multiple non-overlapping folders ingest through exact
version bindings with deterministic reconciliation, and Phase 7 unit/
integration tests pass.

- [x] **7.0 Implement binding domain rules**
  - [x] 7.1 Normalize Windows paths relative to active config exactly as
    designed.
  - [x] 7.2 Reject duplicate, case-equivalent, nested, nonexistent,
    inaccessible, and non-directory paths.
  - [x] 7.3 Require exact published version and active template when enabling.
  - [x] 7.4 Permit historical disabled rows and prevent deletion after batch
    reference.
  - [x] 7.5 Audit create/update/enable/disable/delete outcomes without customer
    filenames.

- [x] **7.6 Implement binding APIs**
  - [x] 7.7 Add admin list/create/update/delete endpoints with role and CSRF
    enforcement.
  - [x] 7.8 Return normalized safe status, version summary, folder
    accessibility, and validation findings.
  - [x] 7.9 Return `409` for path conflicts, invalid lifecycle transitions, or
    referenced deletes.

- [x] **7.10 Implement multi-folder coordinator**
  - [x] 7.11 Scan all enabled bindings sequentially per poll to preserve the
    local throughput model.
  - [x] 7.12 Reconcile DB changes at least once per current polling interval.
  - [x] 7.13 Serialize reconciliation and file claims under one coordinator
    lock.
  - [x] 7.14 Define the move into processing storage as the claim boundary and
    retain its captured binding/version.
  - [x] 7.15 Create assignment-source `watch_folder` batches with binding ID
    and exact version.
  - [x] 7.16 Preserve PDF validation, retry, rename, invalid-file, shutdown,
    and unrelated-binding isolation.
  - [x] 7.17 Replace single-monitor composition in `main.py` without starting
    one unbounded worker thread per folder.

- [x] **7.18 Complete Phase 7 unit and integration tests**
  - [x] 7.19 Test path normalization across relative/absolute paths, case,
    separators, trailing separators, drive roots, duplicates, and nesting.
  - [x] 7.20 Test lifecycle/version eligibility and referenced deletion.
  - [x] 7.21 Test reconciliation add/change/disable, claim-boundary behavior,
    inaccessible-folder isolation, and graceful shutdown.
  - [x] 7.22 Test two folders ingest to different versions and binding changes
    affect only later claims.
  - [x] 7.23 Test existing invalid header, retry, and processing-directory
    behavior.
  - [x] 7.24 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\services\test_ingress_binding_service.py `
      test\services\test_watch_folder_coordinator.py `
      test\integration\test_input_processing.py `
      test\integration\test_sqlite_ingestion.py
    ```

---

## Phase 8 — Legacy schema/pipeline migration and startup cutover

**Prerequisites:** Phases 1-5 complete; Phase 2 migration framework present.

**Exit criterion:** Version 2 databases and current YAML/schema files migrate
idempotently or stop safely before accepting work, and Phase 8 migration tests
pass.

- [x] **8.0 Implement legacy review-schema discovery/import**
  - [x] 8.1 Resolve every configured legacy schema directory relative to the
    active config.
  - [x] 8.2 Canonicalize paths and deduplicate repeated references to the same
    file.
  - [x] 8.3 Import valid YAML/JSON as schema template/version 1/matching draft.
  - [x] 8.4 Activate schemas referenced by the active pipeline; leave other
    valid imports inactive.
  - [x] 8.5 Block migration for missing/invalid referenced schemas and report/
    skip unreferenced invalid files.
  - [x] 8.6 Generate deterministic keys and collision suffixes without
    overwriting.

- [x] **8.7 Transform the active pipeline**
  - [x] 8.8 Normalize active YAML `pipeline`/`tasks`.
  - [x] 8.9 Replace each `schema_file` with the imported exact
    `schema_version_id`.
  - [x] 8.10 Generate normalized schema dependency rows.
  - [x] 8.11 Extract secret-like literals into deterministic
    `pipeline_secrets` aliases without logging values.
  - [x] 8.12 Create active `default-processing` template/version 1/matching
    draft and verify partial-attempt hash identity.

- [x] **8.13 Implement compatibility gates**
  - [x] 8.14 Classify only completed/completed-with-errors/failed/cancelled as
    terminal for migration.
  - [x] 8.15 Require every non-terminal batch display snapshot to match the
    migrated version 1 snapshot.
  - [x] 8.16 Require every available legacy review schema hash to match the
    imported exact version.
  - [x] 8.17 Backfill review-item schema IDs only when unambiguous.
  - [x] 8.18 Block missing/mismatched/ambiguous non-terminal state with
    actionable finish/restore/re-ingest remediation.
  - [x] 8.19 Mark terminal provenance as migration-derived without claiming
    historical parameter/schema reproducibility.

- [x] **8.20 Backfill assignments and preserve history**
  - [x] 8.21 Backfill batches, documents, task runs, review items, and audit
    events.
  - [x] 8.22 Verify root/batch/child/task/schema dependency invariants before
    commit.
  - [x] 8.23 Leave all `config_versions` rows unchanged as legacy history.
  - [x] 8.24 Keep original schema files as non-authoritative import sources;
    never delete them automatically.

- [x] **8.25 Make YAML update atomic and compensating**
  - [x] 8.26 Write same-directory temporary YAML, preserve supported file
    permissions, atomically replace, and avoid secret values in logs.
  - [x] 8.27 Restore original YAML when DB/config coordination fails.
  - [x] 8.28 Ensure backup handling does not broaden permissions or expose a
    customer/config path in operator-facing output.

- [x] **8.29 Enforce startup ordering**
  - [x] 8.30 Run migration before web server, watch coordinator, or ingestion
    acceptance.
  - [x] 8.31 Stop startup on migration failure with safe diagnostics.
  - [x] 8.32 Record schema version 3 only after all invariants and compensation
    points succeed.
  - [x] 8.33 Make reruns idempotent and conflict-detecting, not duplicative.

- [x] **8.34 Complete Phase 8 unit and migration tests**
  - [x] 8.35 Test fresh, v2, partial-attempt, repeated, and rollback migrations.
  - [x] 8.36 Test referenced/unreferenced valid/invalid/duplicate schema files,
    key collisions, and active/inactive import status.
  - [x] 8.37 Test secret extraction without captured-log or error leakage.
  - [x] 8.38 Test matching/missing/mismatched pipeline snapshots and review
    hashes for every non-terminal status.
  - [x] 8.39 Test assignment/review backfill, provenance labels, unchanged
    `config_versions`, and schema file retention.
  - [x] 8.40 Test YAML/DB compensation and startup refuses new work on failure.
  - [x] 8.41 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\db\test_versioned_config_migration.py `
      test\db\test_migrations.py `
      test\integration\test_migration_startup_gate.py
    ```

---

## Phase 9 — Versioned administration and processing APIs

**Prerequisites:** Phases 1-4 complete; Phase 2 schema available.

**Exit criterion:** All designed admin/processing APIs use services, enforce
authorization/CSRF/concurrency, redact output, and pass Phase 9 unit/API tests.

- [ ] **9.0 Add review-schema APIs**
  - [ ] 9.1 Add schema template list/create/get/update lifecycle endpoints.
  - [ ] 9.2 Add draft get/save/import/export/validate endpoints.
  - [ ] 9.3 Add publish, version list/get/export, and usage/dependency
    endpoints.
  - [ ] 9.4 Return revision/hash conflicts and structured findings without
    schema content in error logs.

- [ ] **9.5 Add pipeline-template APIs**
  - [ ] 9.6 Add template list/create/get/update lifecycle and clone endpoints.
  - [ ] 9.7 Add draft get/save/import/export/validate/publish endpoints.
  - [ ] 9.8 Add version list/get/export and redacted version-to-version diff.
  - [ ] 9.9 Include exact schema version summaries and dependency findings.

- [ ] **9.10 Update processing APIs**
  - [ ] 9.11 Return pinned template/version identity and immutable display
    snapshot for batches/documents.
  - [ ] 9.12 Group state by `pipeline_version_id`, not mutable config or only
    content hash.
  - [ ] 9.13 Use legacy batch metadata snapshots only for migration diagnostics
    and explicitly labelled historical fallback.
  - [ ] 9.14 Preserve operator access without exposing admin definitions.

- [ ] **9.15 Cut over old internal admin endpoints**
  - [ ] 9.16 Replace single `/api/admin/pipeline` mutations atomically with
    template-scoped endpoints.
  - [ ] 9.17 Replace file-backed schema mutations with draft import/export.
  - [ ] 9.18 Do not allow old endpoints to write active YAML or schema files.
  - [ ] 9.19 Preserve only explicitly documented compatibility surfaces and
    return safe actionable responses for removed internal endpoints.

- [ ] **9.20 Enforce security and audit**
  - [ ] 9.21 Require admin role for all configuration/template/binding APIs.
  - [ ] 9.22 Preserve router-wide CSRF behavior for cookie-authenticated
    mutations and bearer-token rules.
  - [ ] 9.23 Enforce request size, content type, filename/path containment, and
    import parsing limits.
  - [ ] 9.24 Use shared redaction for definitions, diffs, findings, errors, and
    audits.
  - [ ] 9.25 Keep cross-table logic in services rather than route handlers.

- [ ] **9.26 Complete Phase 9 unit and API tests**
  - [ ] 9.27 Test response serializers/view models for redaction, schema
    dependency summaries, revisions, and pinned processing payloads.
  - [ ] 9.28 Test every endpoint happy path, 400/401/403/404/409/422 behavior,
    CSRF, stale revision, and invalid lifecycle.
  - [ ] 9.29 Test import/export content types, size/path protections, and no
    implicit publish.
  - [ ] 9.30 Test operator cannot access admin endpoints or secret-bearing
    fields.
  - [ ] 9.31 Test old mutations no longer alter YAML/files.
  - [ ] 9.32 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\services\test_versioned_admin_serializers.py `
      test\integration\test_versioned_schema_api.py `
      test\integration\test_versioned_pipeline_api.py `
      test\integration\test_dynamic_processing_pipeline_api.py
    ```

---

## Phase 10 — Review Forms and Pipeline administration UI

**Prerequisites:** Phases 3-4 and 9 complete.

**Exit criterion:** Admins can manage schema and pipeline lifecycles without
mutable runtime files/global pipeline state, frontend-independent Phase 10 unit
tests pass, and browser interaction is ready for final visual verification.

- [ ] **10.0 Refactor Review Forms workspace**
  - [ ] 10.1 List schema templates with status, draft revision, latest version,
    hash, and usage.
  - [ ] 10.2 Edit one server-backed draft through the existing typed field
    editor.
  - [ ] 10.3 Add create, activate/deactivate/archive, validate, publish,
    history, import, and export actions.
  - [ ] 10.4 Display immutable versions and pipeline dependencies.
  - [ ] 10.5 Handle stale revision conflicts without overwriting either
    writer.
  - [ ] 10.6 Make clear that schema publication does not update pipelines
    automatically.

- [ ] **10.7 Refactor Pipeline administration workspace**
  - [ ] 10.8 Add template selector/list, metadata, status, operator
    selectability, create, clone, activate/deactivate/archive, and version
    history.
  - [ ] 10.9 Scope the ordered task editor to one template draft and show its
    revision/base version.
  - [ ] 10.10 Replace review `schema_file` input with an exact active published
    schema-version selector showing version/hash/compatibility.
  - [ ] 10.11 Add validate, publish, canonical redacted preview, redacted diff,
    import, and export actions.
  - [ ] 10.12 Add binding management with normalized-path/version findings.
  - [ ] 10.13 Warn before navigation with unsaved draft changes; browser
    storage must not become authoritative.

- [ ] **10.14 Preserve production frontend/security conventions**
  - [ ] 10.15 Keep authenticated `/app/*` routes, shared `DocFlow` request/
    CSRF helpers, role-based navigation, server-side authorization, and
    same-origin rules.
  - [ ] 10.16 Preserve keyboard access, labels, focus order, error summaries,
    loading states, empty states, and responsive behavior.
  - [ ] 10.17 Never render resolved secrets, raw unredacted definitions, or
    full schema content in audit/usage summaries.
  - [ ] 10.18 Rebuild CSS if templates/JavaScript introduce new Tailwind
    utility classes.

- [ ] **10.19 Complete Phase 10 unit and route tests**
  - [ ] 10.20 Extract/test deterministic frontend-independent state/view-model
    helpers for revision conflicts, lifecycle action availability, schema
    selectors, version labels, and validation grouping.
  - [ ] 10.21 Test authenticated/admin page routes and operator redirects.
  - [ ] 10.22 Test template/controller DOM ID contracts and required scripts.
  - [ ] 10.23 Test API error mapping does not silently select a different
    template/schema version.
  - [ ] 10.24 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\services\test_versioned_admin_view_models.py `
      test\integration\test_new_ui_routes.py `
      test\integration\test_versioned_admin_pages.py
    ```

---

## Phase 11 — Upload and processing operator UI

**Prerequisites:** Phases 6 and 9 complete; Phase 10 shared UI conventions
available.

**Exit criterion:** Operators explicitly select a version and can see immutable
assignment identity throughout processing; Phase 11 unit/route tests pass.

- [ ] **11.0 Add required upload selection**
  - [ ] 11.1 Fetch available versions before enabling processing.
  - [ ] 11.2 Show name, description, document type, instructions, version
    number, publication time, and safe step count.
  - [ ] 11.3 Start with no implicit selection even when one version exists.
  - [ ] 11.4 Require valid files and one current selection before enabling the
    button.
  - [ ] 11.5 Submit exactly one `pipeline_version_id` for the whole batch.
  - [ ] 11.6 On stale/ineligible rejection, refresh the list without choosing a
    replacement silently.

- [ ] **11.7 Update processing presentation**
  - [ ] 11.8 Display template key/name and exact version on batch and document
    views.
  - [ ] 11.9 Render immutable display-snapshot steps and task states.
  - [ ] 11.10 Keep split/review/extraction actions based on document state.
  - [ ] 11.11 Label migration-derived historical provenance honestly.
  - [ ] 11.12 Preserve polling, terminal stop behavior, mobile layout, and long
    pipeline handling.

- [ ] **11.13 Preserve operator security**
  - [ ] 11.14 Do not expose task parameters, schema content, secret aliases not
    needed for display, or admin-only metadata.
  - [ ] 11.15 Preserve authentication redirect, CSRF, output escaping,
    same-origin PDF preview, and role checks.

- [ ] **11.16 Complete Phase 11 unit and route tests**
  - [ ] 11.17 Test selection state, button eligibility, stale-list reset,
    multipart field construction, and error mapping through deterministic
    helpers/view models.
  - [ ] 11.18 Test pinned pipeline labels/snapshots for current and
    migration-derived batches.
  - [ ] 11.19 Test operator page routes, empty available list, unauthenticated
    redirect, and no secret-bearing DOM data.
  - [ ] 11.20 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v `
      test\services\test_operator_pipeline_view_models.py `
      test\integration\test_upload_pipeline_selection_ui.py `
      test\integration\test_dynamic_processing_pipeline_api.py
    ```

---

## Phase 12 — `config-check` stored-source and portable-file CLI

**Prerequisites:** Phase 1 complete for facade/contracts; Phases 2-4 complete
for stored-source resolution; Phase 8 migration semantics defined.

**Exit criterion:** The CLI validates deployment YAML, SQLite drafts/versions,
bindings, and portable files read-only with compatible reporting, and Phase 12
unit/CLI tests pass.

- [ ] **12.0 Add explicit validation sources**
  - [ ] 12.1 Make default `validate --config` validate deployment YAML,
    database availability/version, secret aliases, active eligible pipeline
    versions, exact schema dependencies, and enabled bindings.
  - [ ] 12.2 Add `--pipeline <key>` with exactly one of `--draft` or
    `--version <n>`.
  - [ ] 12.3 Add `--review-schema <key>` with exactly one of `--draft` or
    `--version <n>`.
  - [ ] 12.4 Add `--all-stored` and enforce selector mutual exclusion.
  - [ ] 12.5 Resolve stable keys/version numbers, not caller-supplied UUIDs.

- [ ] **12.6 Add read-only database adapter**
  - [ ] 12.7 Open SQLite read-only and never initialize/migrate/write from
    validation.
  - [ ] 12.8 Return a blocking finding for missing/outdated DB schema.
  - [ ] 12.9 Load exact stored content/dependencies and qualify every finding
    path by source.
  - [ ] 12.10 Reuse the shared validation facade rather than duplicating UI/API
    rules.

- [ ] **12.11 Add `validate-file`**
  - [ ] 12.12 Support `--kind runtime|pipeline|review-schema`.
  - [ ] 12.13 Validate deployment YAML without opening SQLite for runtime kind.
  - [ ] 12.14 Resolve portable pipeline schema coordinates against the target
    DB when `--config` is provided.
  - [ ] 12.15 Require embedded dependency content for fully offline pipeline
    validation.
  - [ ] 12.16 Never import, save, publish, migrate, or rewrite during
    validation.

- [ ] **12.17 Extend portable contract schema output**
  - [ ] 12.18 Add `config-check schema --kind
    runtime|pipeline|review-schema|pipeline-bundle`.
  - [ ] 12.19 Keep machine-readable schemas deterministic for automation.

- [ ] **12.20 Preserve compatible CLI behavior**
  - [ ] 12.21 Preserve text/JSON formats, strict/base-dir/import/file/
    performance/security options where applicable.
  - [ ] 12.22 Return usage code `64` for incompatible flags rather than
    ignoring them.
  - [ ] 12.23 Preserve exit codes `0`, `1`, `2`, and `64`.
  - [ ] 12.24 Report legacy root `pipeline`, `tasks`, and filesystem review
    schemas as migration/deprecation findings, not active runtime definitions.
  - [ ] 12.25 Redact secrets consistently from arguments summary, findings,
    suggestions, exceptions, JSON, and logs.

- [ ] **12.26 Complete Phase 12 unit and CLI tests**
  - [ ] 12.27 Test parser selector combinations, defaults, errors, and schema
    kinds.
  - [ ] 12.28 Test read-only DB behavior and outdated/missing database
    findings.
  - [ ] 12.29 Test targeted drafts/versions, all-stored, active dependencies,
    and binding checks.
  - [ ] 12.30 Test portable online/offline resolution, hash mismatch, missing
    dependency, and no writes.
  - [ ] 12.31 Re-run all existing CLI validator/reporter/exit-code tests.
  - [ ] 12.32 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v test\tools\config_check
    ```

---

## Phase 13 — Cross-cutting integration, migration, security, and full regression

**Prerequisites:** Every task in Phases 1-12 checked.

**Exit criterion:** End-to-end behavior and broad regressions pass without live
provider calls. No implementation coding phase remains incomplete.

- [ ] **13.0 Run end-to-end multi-template scenarios**
  - [ ] 13.1 Create/publish two schema versions and two independent pipeline
    templates.
  - [ ] 13.2 Upload separate batches to different versions and prove pinned
    execution/task-run attribution.
  - [ ] 13.3 Publish newer pipeline/schema versions during active work and
    prove existing work is unchanged.
  - [ ] 13.4 Deactivate/archive templates and schemas and prove new work is
    rejected while pinned work resumes.

- [ ] **13.5 Run split/review/fan-in scenarios**
  - [ ] 13.6 Prove split children inherit assignments and do not duplicate on
    retry.
  - [ ] 13.7 Prove review item schema identity, correction, locking, completion,
    and exactly-once resume.
  - [ ] 13.8 Prove completed/failed/review-required child combinations retain
    current fan-in results.
  - [ ] 13.9 Prove artifact registration and cleanup remain correct.

- [ ] **13.10 Run ingestion/coordinator scenarios**
  - [ ] 13.11 Prove one upload batch cannot mix versions.
  - [ ] 13.12 Prove two folders use different versions and binding
    reconciliation changes only later claims.
  - [ ] 13.13 Prove invalid selections/bindings create no partial records or
    orphan files.

- [ ] **13.14 Run migration matrix**
  - [ ] 13.15 Cover fresh, v2 terminal, v2 review-paused, v2 processing,
    mismatch, missing schema, secret migration, partial failure, and idempotent
    rerun.
  - [ ] 13.16 Verify startup cannot accept HTTP/watch work before migration
    success.
  - [ ] 13.17 Verify legacy history and original schema files remain intact.

- [ ] **13.18 Run security regression**
  - [ ] 13.19 Test admin/operator separation and server-side authorization.
  - [ ] 13.20 Test CSRF, cookie/bearer behavior, trusted paths, import
    containment, protected PDFs, and output escaping.
  - [ ] 13.21 Scan API, audit, task-run, log, diff, CLI, error, fixture, and
    rendered payloads for synthetic secret sentinels.
  - [ ] 13.22 Verify arbitrary module/class, path, expression, draft, and
    unpublished version inputs cannot execute.

- [ ] **13.23 Run focused automated suites**

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -v test\db
  .\.venv\Scripts\python.exe -m pytest -v test\services
  .\.venv\Scripts\python.exe -m pytest -v test\workflow
  .\.venv\Scripts\python.exe -m pytest -v test\standard_step\review
  .\.venv\Scripts\python.exe -m pytest -v test\integration
  .\.venv\Scripts\python.exe -m pytest -v test\security
  .\.venv\Scripts\python.exe -m pytest -v test\tools\config_check
  ```

- [ ] **13.24 Run the full non-live pytest suite**

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -v
  ```

- [ ] **13.25 Review automated-test evidence**
  - [ ] 13.26 Record exact commands, counts, pass/fail outcomes, skips, and
    duration under **Implementation Notes**.
  - [ ] 13.27 Investigate every unexpected skip, warning, flaky retry, or
    intermittent failure.
  - [ ] 13.28 Do not proceed to visual testing until every required automated
    test is green or an explicitly documented external-only check is outside
    scope.

---

## Phase 14 — Final visual, interaction, responsive, and accessibility testing

**Prerequisites:** Phase 13 complete; all implementation coding and non-visual
automated testing complete.

**Exit criterion:** Production UI flows are visually and interactively verified
at required viewports with no secret/customer data in evidence.

- [ ] **14.0 Prepare safe visual fixtures**
  - [ ] 14.1 Use temporary database/configuration, synthetic pipeline/schema
    names, fake secret aliases, and synthetic PDFs.
  - [ ] 14.2 Seed empty, one-version, multi-version, inactive, archived,
    validation-error, stale-draft, long-pipeline, split, review, failed, and
    migration-derived states.
  - [ ] 14.3 Confirm screenshots cannot include real credentials, customer
    files, local sensitive paths, or raw extraction output.

- [ ] **14.4 Verify Review Forms visually**
  - [ ] 14.5 Capture/list-check empty, populated, draft-edit, validation,
    publish, version-history, import/export, dependency-usage, conflict, and
    archived states.
  - [ ] 14.6 Verify long labels, nested fields, enums, arrays, objects, error
    summaries, focus, keyboard flow, and responsive layouts.

- [ ] **14.7 Verify Pipeline administration visually**
  - [ ] 14.8 Capture/list-check template selection, metadata, task ordering,
    exact schema version selector, validation, redacted preview/diff,
    publication, history, clone, lifecycle, and bindings.
  - [ ] 14.9 Verify stale conflicts, unavailable schema versions, long
    pipelines, path findings, empty states, loading, and server errors.

- [ ] **14.10 Verify upload and processing visually**
  - [ ] 14.11 Verify no implicit pipeline choice, guidance/version display,
    file validation, button eligibility, stale selection recovery, and upload
    success.
  - [ ] 14.12 Verify processing identity, dynamic steps, split parent/children,
    paused review, failed/completed states, and migration provenance.
  - [ ] 14.13 Verify desktop, narrow desktop/tablet, and mobile layouts; include
    long pipeline labels and horizontal/vertical overflow.

- [ ] **14.14 Verify accessibility and security presentation**
  - [ ] 14.15 Check keyboard-only completion of primary actions, visible focus,
    labels, headings, landmarks, modal focus/escape, and live error messaging.
  - [ ] 14.16 Check text contrast, non-color status cues, zoom/reflow, and
    reduced-motion behavior where used.
  - [ ] 14.17 Inspect DOM/network/screenshot evidence for secret values,
    unescaped content, admin data on operator pages, and unsafe PDF framing.

- [ ] **14.18 Run browser visual tests**
  - [ ] 14.19 Install Playwright Chromium only if the environment reports it
    missing:

    ```powershell
    .\.venv\Scripts\python.exe -m playwright install chromium
    ```

  - [ ] 14.20 Run:

    ```powershell
    .\.venv\Scripts\python.exe -m pytest -v test\visual
    ```

  - [ ] 14.21 Review every captured screenshot at full resolution; passing
    pixel/DOM assertions alone is not sufficient.
  - [ ] 14.22 Fix visual defects, rerun affected unit/integration tests, rebuild
    CSS if needed, then rerun the complete visual suite.
  - [ ] 14.23 Record viewports, scenarios, screenshots, and results under
    **Implementation Notes**.

---

## Phase 15 — Focused documentation, cleanup, and completion audit

**Prerequisites:** Phase 14 complete. All automated and visual tests pass.

**Exit criterion:** Maintained documentation matches actual behavior, obsolete
runtime instructions are carefully corrected without removing still-relevant
content, the diff is clean, and every requirement is evidenced.

- [ ] **15.0 Update architecture documentation narrowly**
  - [ ] 15.1 Update `docs/design_architecture.md` sections for SQLite
    configuration authority, versioned schema/pipeline entities, ingestion,
    execution pinning, resume, watch coordinator, and CLI validation.
  - [ ] 15.2 Preserve unrelated architecture, artifact, security, review,
    split, and compatibility content.
  - [ ] 15.3 Update document verification date/revision only according to the
    repository's established convention.

- [ ] **15.4 Update administrator/operator documentation**
  - [ ] 15.5 Update `docs/user_guide.md` for schema publish-before-use,
    template lifecycle, upload selection, bindings, version display,
    migration, and recovery limitations.
  - [ ] 15.6 Update `docs/review_schema_admin_guide.md` for SQLite drafts/
    versions, import/export, dependencies, and exact-version pipeline
    selection.
  - [ ] 15.7 Retain still-valid field type, validation, review correction,
    security, and troubleshooting guidance.
  - [ ] 15.8 Clearly label any remaining legacy YAML/file instructions as
    migration/import-only rather than deleting useful examples.

- [ ] **15.9 Update CLI and operator documentation**
  - [ ] 15.10 Update `tools/config_check/README.md` with stored-source
    selectors, default DB-backed behavior, `validate-file`, portable bundles,
    flags, exit codes, examples, and read-only guarantees.
  - [ ] 15.11 Update `docs/config_check_troubleshooting.md` only for new
    source, migration, dependency, database-version, and redaction findings.
  - [ ] 15.12 Update packaged/help examples and error-code references that are
    now inaccurate.

- [ ] **15.13 Update task standards only where behavior changed**
  - [ ] 15.14 Review `tasks/standard_task_creation_guidelines.md`.
  - [ ] 15.15 Add narrowly scoped guidance for immutable definition injection,
    `pipeline_version_id`, exact review-schema dependencies, and prohibition
    on task-local global config/schema reload only if implementation changed
    those shared contracts.
  - [ ] 15.16 Do not rewrite unrelated task creation guidance.

- [ ] **15.17 Reconcile design and future documents**
  - [ ] 15.18 Update the design document's status and any implementation
    details that legitimately changed, without weakening acceptance criteria.
  - [ ] 15.19 Add cross-links between design, this completed plan, maintained
    docs, and the deferred mixed-document routing design.
  - [ ] 15.20 Keep mixed-document routing, `workflow_runs`, classification,
    and graph execution explicitly deferred.
  - [ ] 15.21 Move/archive this task plan only under the repository's normal
    completed-plan convention and only after every checkbox is complete.

- [ ] **15.22 Perform final diff and content review**
  - [ ] 15.23 Update **Relevant Files** with every created/materially changed
    file and a concise purpose.
  - [ ] 15.24 Review `git diff --check`, `git status --short`, and the full diff
    for accidental edits, generated runtime data, databases, PDFs, logs,
    credentials, customer content, and unrelated formatting.
  - [ ] 15.25 Search changed source, tests, docs, API fixtures, and screenshots
    for secret sentinels and legacy runtime `schema_file`/global pipeline
    fallbacks.
  - [ ] 15.26 Verify no implementation-only behavior exists in
    `pipeline_visual_editor_prototype/`.

- [ ] **15.27 Perform requirement-by-requirement completion audit**
  - [ ] 15.28 Map every design heading and acceptance criterion to checked
    tasks and authoritative evidence.
  - [ ] 15.29 Confirm every implementation phase unit-test command passed.
  - [ ] 15.30 Confirm Phase 13 focused/full suites and Phase 14 visual suite
    passed after the final code/CSS change.
  - [ ] 15.31 Confirm migration rollback/idempotency, authorization/CSRF,
    secret redaction, assignment immutability, exact schema dependency, split,
    review resume, fan-in, CLI read-only behavior, and documentation evidence.
  - [ ] 15.32 Treat missing, indirect, stale, or partial evidence as incomplete
    and add/reopen tasks until proven.
  - [ ] 15.33 Mark this plan complete only when no required task or unresolved
    finding remains.

## Design-to-phase coverage matrix

| Design area | Implementation phases | Final evidence |
| --- | --- | --- |
| Canonical definitions, hashes, secrets, redaction | 1 | Unit tests; security scan |
| Review schema tables/drafts/versions | 2-3 | DB/service tests; admin/UI tests |
| Pipeline tables/drafts/versions/dependencies | 2, 4 | DB/service tests; publication concurrency |
| Assignment columns and immutability | 2, 5-8 | Repository, workflow, ingestion, migration tests |
| Secret references and deployment YAML | 1, 4-5, 8, 12 | Redaction tests; migration and CLI evidence |
| Schema lifecycle/import/export | 3, 9-10, 12 | Service/API/UI/CLI tests |
| Pipeline lifecycle/clone/diff | 4, 9-10 | Service/API/UI tests |
| Upload selection and authorization | 6, 11 | API/UI/integration/visual tests |
| Watch-folder bindings/coordinator | 7 | Service/integration/visual admin tests |
| Pinned workflow loading/task runs/cleanup | 5 | Workflow tests |
| Split inheritance/preflight/fan-in | 5, 13 | Workflow and end-to-end tests |
| Review item schema identity/resume | 3, 5, 13 | Review/workflow/integration tests |
| Processing snapshots and grouping | 5, 9, 11 | Service/API/UI/visual tests |
| Admin APIs and security | 9 | API/security tests |
| Production admin/operator UI | 10-11 | Route/unit, integration, and Phase 14 visual tests |
| YAML/JSON portable files | 1, 3-4, 9, 12 | Round-trip/API/CLI tests |
| `config-check` future behavior | 1, 12 | Full CLI suite |
| Legacy v2/YAML/schema migration | 2, 8 | Migration matrix and startup gate |
| Audit and authorization | 3-9, 13 | Audit payload and security tests |
| Full regression | 13 | Focused suites and full pytest |
| Visual/accessibility verification | 14 | Reviewed screenshots and visual suite |
| Focused maintained documentation | 15 | Diff review and link/content audit |
| Deferred mixed-document routing boundary | 15 | Design/docs audit |

## Risk controls

- Keep new ingestion disabled until schema/pipeline persistence and pinned
  runtime execution are both ready.
- Never use latest-version or global-config fallback to make a test pass.
- Separate immutable content from mutable lifecycle metadata.
- Treat schema and pipeline publication as independent explicit actions.
- Resolve secret values only in memory and fail closed when unavailable.
- Keep migration before process startup and compensation-capable.
- Use composite foreign keys, normalized dependency rows, and triggers in
  addition to service checks.
- Preserve SQLite/file transaction compensation for uploaded/split artifacts.
- Keep CLI database access read-only and import/publish as separate actions.
- Retain legacy files/history until migration and final audit prove they are no
  longer runtime authorities.
- Run focused tests after each phase to localize regressions; do not postpone
  unit coverage to the final full suite.
- Do not use visual success to waive backend, migration, security, or CLI
  failures.

## Implementation notes

Add dated notes here during execution for:

- baseline and newly discovered pre-existing failures;
- intentionally added tasks and their rationale;
- exact test commands/outcomes/skips;
- migration fixtures and compatibility decisions;
- visual viewports/screenshots/results;
- checks not run and the concrete reason;
- final relevant-file reconciliation.

### 2026-07-25 — Phases 1-4

- Baseline before implementation: `270 passed, 3 skipped`; the three skips are
  existing Windows permission-behavior skips. The worktree contained only the
  two untracked multiple-pipeline design/task documents, which were preserved.
- The Phase 1 command in this plan named
  `test/services/test_pipeline_validation_service.py`, but that file does not
  exist in the repository. Validation parity was run through
  `test/services/test_catalog_pipeline_edge_cases.py` instead: `25 passed`.
- Phase 2 prescribed suite: `8 passed`.
- Phase 3 prescribed suite: `22 passed`.
- Phase 4 prescribed suite: `23 passed`.
- Full regression after the final Phase 1-4 changes: `781 passed, 4 skipped`
  with four pre-existing framework deprecation warnings in 209.14 seconds.
- Schema version 3 structural preparation is idempotent in Phases 1-4, while
  recording version 3 and transforming legacy YAML/state remain deliberately
  deferred to Phase 8 as required by task 2.28.
- Phase 1-4 relevant files:
  - `modules/services/versioned_config_contracts.py`: typed contracts,
    canonicalization, hashing, secret references, redaction, snapshots.
  - `modules/services/validation_facade.py`: source-qualified explicit-content
    validation.
  - `modules/services/portable_config_service.py`: portable pipeline/schema
    coordinate conversion.
  - `modules/db/schema.sql`, `modules/db/migrations.py`,
    `modules/db/connection.py`, and `modules/db/repositories.py`: target schema,
    structural upgrade, immediate transactions, and persistence operations.
  - `modules/services/review_schema_version_service.py`: review-schema
    lifecycle, drafts, publishing, import/export, and exact loading.
  - `modules/services/pipeline_template_service.py`: pipeline lifecycle,
    dependencies, publishing, clone/diff, eligibility, and exact loading.
  - `test/services/test_versioned_config_contracts.py`,
    `test/db/test_versioned_configuration_schema.py`,
    `test/services/test_review_schema_version_service.py`, and
    `test/services/test_pipeline_template_service.py`: Phase 1-4 coverage.

### 2026-07-25 — Phases 5-7

- Phase 5 prescribed suite: `26 passed`. Prefect emitted a non-test shutdown
  logging error after pytest closed its captured output; the process exit code
  and test result were successful.
- Phase 6 prescribed suite: `14 passed` with four existing FastAPI/Starlette
  deprecation warnings.
- Phase 7 prescribed suite: `21 passed` with one existing Starlette
  deprecation warning.
- Binding API role/CSRF/conflict coverage was also run separately and passed.
- The first full regression found five stale main-composition tests that still
  patched `WatchFolderMonitor` and one legacy helper call that omitted the new
  optional version attribution. The tests were updated to the coordinator
  contract and the helper retained a `None` compatibility default.
- Full regression after those corrections: `803 passed, 4 skipped` with four
  existing framework deprecation warnings in 134.85 seconds.
- Phase 5-7 relevant files:
  - `modules/services/pipeline_definition_service.py`,
    `modules/workflow_loader.py`, `modules/workflow_manager.py`,
    `modules/services/workflow_state_service.py`, and
    `modules/resume_manager.py`: exact pinned execution and continuation.
  - `standard_step/split/llamacloud_split.py`,
    `standard_step/review/review_gate.py`, and
    `modules/services/review_service.py`: inherited split attribution and
    exact review-schema identity.
  - `modules/services/ingestion_assignment_service.py`,
    `modules/services/batch_service.py`, and `modules/api_router.py`: atomic
    upload assignment and redacted selection APIs.
  - `modules/services/ingress_binding_service.py`,
    `modules/services/watch_folder_coordinator.py`, and `main.py`: SQLite
    binding lifecycle and serialized multi-folder ingestion.

### 2026-07-25 — Phase 8

- The prescribed Phase 8 migration/startup suite passed: `24 passed`.
- The first full regression identified that fresh test databases with
  configuration fragments were being treated as v2 upgrades. The migration
  runner now distinguishes fresh schema-v3 initialization from an actual v2
  database or database containing legacy work. Only the latter runs the
  legacy YAML/state importer.
- Representative initialization-heavy API, workflow, processing, resume, and
  upload tests passed together after that correction: `58 passed`.
- Final full regression: `826 passed, 4 skipped` with four existing framework
  deprecation warnings in 148.93 seconds.
- `modules/services/legacy_versioned_config_migration.py` now owns canonical
  schema discovery/import, deterministic keys, exact dependency conversion,
  secret alias extraction, non-terminal compatibility gates, terminal
  provenance, assignment/review backfill, invariants, atomic YAML replacement,
  and compensation.
- `modules/db/migrations.py` records schema version 3 only after the importer,
  invariants, YAML replacement, and audit work succeed. `main.py` blocks
  startup before runtime construction on any migration failure.
