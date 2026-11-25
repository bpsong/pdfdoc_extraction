# R3 implementation plan — CSV reference lookup and enrichment

**Status** · Phases 1–4 complete and verified as of 2026-11-25. Phase 5 is next.

**Acceptance target** · An administrator publishes a pipeline that matches an invoice against a read-only supplier CSV. A reviewer can resolve ambiguity and see the values used for release. The same supplier ID, including its leading zeros, reaches JSON, CSV, and the PDF filename whether the workflow runs straight through or resumes after review. [Agreed design](design-r3-csv-reference-lookup.md)

Build on SQLite and the production `web/` application. Each lookup returns one or more **text values into new document-level fields**. Each input clause independently supports case-sensitive text (default), case-insensitive text, or numeric equality. A numeric match can return `"00042"`. Keep the existing CSV update task compatible. Use temporary databases, synthetic PDFs and registers, and the existing offline extraction fixtures throughout.

Work through the phases in order. Check each item after its implementation and associated tests pass. Record the command, result, and visual evidence location for each completed phase. Proposed new test filenames below give each behavior a verification target.

## Phase 1 — Configuration and deterministic matching

**Prerequisite** · Matching, text outputs, reviewer authority, and reference-file handling are agreed in the design.

- [x] Define typed configuration for a trusted reference path, one to five ANDed field/column bindings, per-clause mode, return-column mappings, required flag, and separate no-match and multiple-match policies. Reject malformed definitions and optional continuation for a required lookup.
- [x] Implement a read-only matcher. Bound the read, hash the exact bytes parsed, validate UTF-8/BOM, headers and row shape, and retain the original text of returned cells. Report a safe reference-data error for malformed or oversized input. The service defaults to 8 MiB and 50 retained candidates per evaluation. Phase 3 can use those defaults when it wires the task.
- [x] Trim and compare strings using exact equality or Unicode case folding. Compare explicitly numeric keys as finite decimals using the design's accepted syntax. Distinguish invalid document inputs, zero matches, a unique match, ambiguity, and invalid reference data. Count all matches even when evidence is truncated. Return mapped values together.
- [x] Add `test/standard_step/rules/test_csv_reference_lookup.py`. Cover mixed-mode AND clauses, leading zeros, unequal case by default, Unicode case folding, ambiguity introduced by folding, decimal equality and invalid numeric forms, blank inputs and returns, missing/duplicate columns, quoting, BOM, malformed rows and size bounds. Verify exact returned spelling, no partial mappings, identical CSV bytes, and existing CSV-update regressions.

**Exit evidence** · The same input bytes and configuration yield the same disposition, count, evidence, and text values across repeated evaluations.

**Verified** · The phase 1 command below passed all 47 tests, including the existing CSV update suite.

## Phase 2 — SQLite decisions, revisions, and recovery

**Prerequisite** · Phase 1 establishes the shape of a lookup result.

- [x] Add `lookup_decisions` to the idempotent schema applied before the startup marker advances to schema 11. Store document and extraction identity, pinned pipeline version and task key, input values and modes, file digest, bounded candidates, state, and the prior revision ID. Preserve selected record number, returned fields, actor and reason.
- [x] Put table operations in `modules/db/repositories.py` and coordinate transactional decision creation, revision checks, and selection in the service. Reuse committed decisions on retry. Keep new evaluations distinguishable from duplicate submissions and include lookup history in previewed retention.
- [x] Merge resolved lookup text into the supplied corrected document values. Reject collisions without changing those values. Project only selected fields and omit keys for skipped lookups.
- [x] Add `test/db/test_lookup_decisions.py`. Cover fresh install, upgrade with pre-existing documents, competing SQLite writes, duplicate and stale submissions, rollback, superseded history, independent task keys and child documents, and previewed retention. Run existing resume tests for documents without lookups.

**Exit evidence** · A restart reconstructs the same stored decision. Concurrent acceptance produces one current revision and a consistent audit history.

**Verified** · The combined focused run passed 132 tests covering matching, existing CSV updates, migrations, repositories, retention, startup, resume, and documentation. Repository Pyright returned zero errors and warnings.

The full suite passed 2,097 tests with 5 skips in 515.89 seconds, including the existing browser regressions. R3 visual acceptance is tracked in phase 5.

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/standard_step/rules/test_csv_reference_lookup.py test/standard_step/rules/test_rules.py test/db/test_lookup_decisions.py test/db/test_migrations.py test/db/test_repositories.py test/db/test_migration_boundaries.py test/db/test_pipeline_cleanup_migration.py test/services/test_pipeline_cleanup_service.py test/integration/test_pipeline_cleanup_api.py test/integration/test_migration_startup_gate.py test/services/test_resume_manager.py test/tools/test_documentation_structure.py
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe -m pytest -v --tb=short
```

## Phase 3 — Task execution, publication, and configuration checks

**Prerequisite** · Phases 1–2 pass. Finish backend review enforcement in phase 4 before exposing the lookup in the production editor.

- [x] Bind the matcher and decision service to the approved built-in `CsvReferenceLookupTask`. Use pinned parameters, stop on errors, keep source extraction evidence, and merge text on a unique match. A review outcome persists a pending decision and stops this preview run before release.
- [x] Wire the backend catalog, exact-version loader, publication, and config-check. Validate known field types, duplicate and reserved targets, lookup and gate order, and output template dependencies. Stop on runtime collisions. Resolve literal paths relative to deployment configuration and validate the worker's file. Publication warns when the file cannot be checked locally.
- [x] Exercise the published task, draft and portable round trip, pinned execution after a draft edit, worker-only file access, changed and deleted files, multiple independent lookups, and legacy CSV update in `test/integration/test_lookup_pipeline.py`.

**Exit evidence** · A published synthetic pipeline can resolve a unique match. Invalid policies and placement are rejected before publication. A reference error stops release even on an optional lookup.

**Preview behavior** · The backend catalog recognizes CSV lookup. The lookup appears in the production editor when its authoring controls arrive in phase 5. A gate that would pause after a lookup stops the preview run before creating a review because R3 resume support arrives in phase 4. All lookups precede business outputs so an optional lookup can still stop release on a broken register.

**Focused verification** · 59 tests passed with the command below.

**Full verification** · 2,120 tests passed with 5 skips in 503.95 seconds, including existing browser regressions. Pyright returned zero errors and warnings. R3 visual acceptance remains in phase 5.

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/integration/test_lookup_pipeline.py test/tools/test_documentation_structure.py test/tools/config_check/test_remaining_branches.py --tb=short
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe
```

## Phase 4 — Review gate, acceptance, and next-task resume

**Prerequisite** · Published lookup steps can persist matched, skipped, and pending decisions.

- [x] Use persisted lookup decisions in the extraction gate and review service. A pending lookup triggers review, and its match inputs are eligible for correction under low-confidence-only editing. The pinned form can validate lookup returns as text. R4 reports record reference provenance.
- [x] Support preview, candidate selection with reason, optional skip with reason, and explicit adoption of the current file. Bind candidate evidence to the document, task, input values, and source digest. A changed input invalidates its selection. A truncated match set blocks selection and returned fields are read-only.
- [x] Rematch corrected inputs against the original digest. Hold review when those bytes are unavailable, then accept a replacement file only after explicit adoption and revalidation. Retain the prior and replacement digests in the linked decision revisions.
- [x] Validate the live claim, review revision, and lookup preview before completion. Commit corrections, decisions, accepted report, audit, and workflow state together. Resume from SQLite at the next task using the accepted decision. A gate placed before a lookup can correct source fields passed to that lookup on resume.
- [x] Cover missing and ambiguous matches, truncated candidates, required versus optional outcomes, multiple pending lookups, stale preview, lost claim, mismatched candidate, duplicate submit, interrupted transactions, worker restart at the lookup/gate, explicit resume after acceptance, and register replacement. Blocked cases produce no downstream artifacts.

**Exit evidence** · Actual review and resume produce the accepted supplier ID. A stale or unauthorized action cannot release a document or alter the accepted revision.

An expired root worker claim can recover a persisted lookup or its review gate
when preceding execution can be reconstructed from SQLite. A committed gate
keeps its existing review item on reclaim. If an interruption occurs after
acceptance and before the resume claim, the existing authenticated document
resume endpoint can launch the accepted continuation. A previously started
downstream operation is outside the automatic replay boundary.

**Focused verification** · 104 tests passed. The R3 integration tests use the
real publication, gate, review API, SQLite, resume, and storage code with
synthetic extraction.

**Full regression and retry** · The full run recorded 2,125 passes, 5 skips,
and four failures in older test fixtures that bypassed service initialization
or supplied a connection without transaction support. The corrected fixtures
passed alongside the R3 review and documentation tests on a 31-test retry.
Across both runs, all 2,129 non-skipped cases passed. Pyright reported zero
errors and warnings.

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/integration/test_lookup_review.py test/integration/test_lookup_pipeline.py test/integration/test_review_business_validation_api.py test/integration/test_review_pause_resume.py test/services/test_resume_manager.py test/services/test_review_service.py test/standard_step/review/test_review_gate.py test/db/test_lookup_decisions.py test/services/test_processing_worker.py test/workflow/test_workflow_manager.py test/tools/test_documentation_structure.py --tb=short
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q test/services/test_review_service_branches.py test/test_remaining_unit_coverage.py::test_resume_manager_defensive_resume_and_failure_context_paths test/integration/test_lookup_review.py test/tools/test_documentation_structure.py --tb=short
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe
```

## Phase 5 — Production editor, reviewer controls, and visual tests

**Prerequisite** · The publication and review APIs enforce the phase 3–4 contracts.

- [ ] In the production pipeline editor, add the source, ordered clauses, comparison-mode selector per clause, text return mappings, release requirement, and independent outcome policies. Show validation at the affected control. Preserve settings across save, publish and reopen. Use the existing pipeline controller and task editor entry points.
- [ ] In the extraction review UI, show original inputs, mode, outcome, returned text and bounded candidate evidence. Support keyboard selection, correction/revalidation, audited optional skip, and **Use current reference file** with reason. Clear selection and preview tokens after relevant edits, then submit the final revalidation token with completion. Make blocking, stale, truncated, and read-only states understandable. Keep the PDF and existing R4 findings usable.
- [ ] Add Chromium tests in `test/visual/test_lookup_editor_visual.py` and `test/visual/test_lookup_review_visual.py`. Run the real local application with synthetic users and files following the existing [browser acceptance fixture](../test/visual/test_business_validation_acceptance_visual.py). Use a 1366 × 768 desktop and a 390 × 844 mobile viewport.
- [ ] In the editor, visually verify the default, change one of two clauses to case-insensitive, fix a mapping error, publish and reopen. In review, inspect a unique match, a multiple-match selection, a corrected miss, a stale-file hold and a completed read-only result. Exercise keyboard focus, long labels/values, candidate truncation, and narrow-screen scrolling.
- [ ] Assert visible text and control state, focus, absence of page-level horizontal overflow, persistence after reload and absence of browser errors. Capture and inspect screenshots of editor validation, ambiguous candidates, file adoption and accepted values on both viewports. Save synthetic evidence in the test output directory. Rebuild committed CSS if template utilities or Tailwind inputs change.

**Exit evidence** · An administrator can configure the lookup and a reviewer can resolve it on each viewport. Record the browser test results and inspected screenshot paths.

## Phase 6 — End-to-end release and regression verification

**Prerequisite** · Backend and UI acceptance paths are connected.

- [ ] Add `test/integration/test_lookup_exports.py`. Run a synthetic invoice through the pinned pipeline with a unique match and again through ambiguous-match review, completion, worker resume and storage. Compare effective values across paths. Parse the actual JSON and CSV for string `00042`, check the registered PDF filename and document identity, and verify the original extraction and reference CSV bytes.
- [ ] Exercise an optional miss, a required unresolved ID, R4 blocking after revalidation, a repaired register with an explicit revision, and two split children with different suppliers. Assert no leakage across children, no stale accepted IDs, and no candidate data in output. Verify pipelines without lookup and existing CSV updates still work.
- [ ] Drive at least one complete browser path from published editor configuration to operator acceptance and registered outputs. Run focused suites first, then full pytest and repository Pyright. Record failures, skips, retries, and their disposition before documentation sign-off.

**Verification commands** · Run these from the repository root as the corresponding phase delivers its tests. Use `npm run build:css` when the phase 5 rebuild condition applies.

```powershell
.\.venv\Scripts\python.exe -m pytest -v test/standard_step/rules/test_csv_reference_lookup.py test/standard_step/rules/test_rules.py
.\.venv\Scripts\python.exe -m pytest -v test/db/test_lookup_decisions.py test/db/test_migrations.py test/db/test_repositories.py
.\.venv\Scripts\python.exe -m pytest -v test/integration/test_lookup_pipeline.py test/workflow/test_workflow_loader_task_approval.py test/tools/config_check/test_rules_task_validator.py
.\.venv\Scripts\python.exe -m pytest -v test/integration/test_lookup_review.py test/integration/test_review_business_validation_api.py test/services/test_resume_manager.py
.\.venv\Scripts\python.exe -m pytest -v test/visual/test_lookup_editor_visual.py test/visual/test_lookup_review_visual.py
.\.venv\Scripts\python.exe -m pytest -v test/integration/test_lookup_exports.py test/integration/test_business_validation_acceptance.py
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe
```

## Phase 7 — Update documentation and close R3

**Prerequisite** · Phase 6 establishes the shipped behavior and verification results. This is the final phase.

- [ ] **Administrators and configuration.** Update the pipeline authoring and task guides, the rules-task reference, pipeline-definition reference, and config-check examples. Include a copyable synthetic supplier example with two comparison modes and a text return. Document input normalization, limits, policy combinations, task ordering, and how lookup differs from CSV update.
- [ ] **Operators.** Update the extraction review guide and review-gate reference with candidate selection, corrected inputs, optional skips, stale files, explicit adoption, and blocked release. Use verified UI labels and synthetic screenshots wherever the guides illustrate a changed screen.
- [ ] **IT support.** Update deployment/configuration, upgrades, backup/restore, retention and troubleshooting where affected. Explain Windows worker access, CSV encoding, atomic replacement, size limits, SQLite migration, digest evidence and recovery when original bytes are unavailable.
- [ ] **Developers and integrators.** Update workflow/state, persistence, review API and storage/output contracts, relevant schema/version references and testing guidance. Record the shared projection and transaction boundary. Update the standard task guidelines alongside any earlier change establishing a new task standard, and cross-check them here.
- [ ] **Discoverability and sign-off.** Update navigation/indexes and the documentation map where pages change. Validate documented examples with the repository config-check CLI using temporary files. Run `.\.venv\Scripts\python.exe -m pytest -v test/tools/test_documentation_structure.py` and `git diff --check`. Verify screenshots and sample exports against phase 6, record exact outcomes, update roadmap and design status, and archive the completed plan with working links per repository convention.

**Done when** · The published example produces the documented outputs, support staff can recover a paused lookup using the guide, and the roadmap links to the final verification record.
