# Pipeline archive and processing-data cleanup

Approved scope: independent archive and cleanup actions in the production
pipeline editor. Permanent pipeline deletion, file deletion, export archives,
and database compaction are excluded.

## Tasks

- [x] Add schema migration and repository support for safe whole-batch cleanup,
  expiring previews, retained audit history, and upload receipt tombstones.
- [x] Implement archive impact previews and transactional cleanup services with
  strict cutoff, confirmation, authorization, and concurrency checks.
- [x] Add production dialogs, archive visibility, blockers, cleanup preview,
  typed confirmation, results, and accessible keyboard behavior.
- [x] Add and run unit, migration, API/security, and browser visual regressions.
- [x] Build CSS, run broader verification, inspect synthetic screenshots, and
  update operator/architecture documentation and verification results.
- [x] Review follow-up: close archive/dropdown and archived-reset gaps, refresh
  all archived choices, and verify overlapping editor loads cannot mix pipelines.
- [x] Review follow-up: verify an archive remains successful if the separate
  list refresh fails, and rerun the complete regression suite after review fixes.
- [x] Review follow-up: update README, API/operator/deployment/watch-folder
  documentation and record final regression results.
- [x] Documentation follow-up: add app-based admin walkthroughs using exact
  control labels, expected results, cancellation, and blocked-action recovery;
  place technical details in an optional IT/support section.

- [x] Documentation audience review: rewrite the user guide for operators and
  business administrators, add app-based procedures, move IT commands and task
  parameters to a separate reference, and verify links and control labels.

## Relevant Files

- `modules/db/schema.sql`, `modules/db/schema_version.py`,
  `modules/db/migrations.py`: cleanup previews and retained audit identities.
- `modules/services/startup_migration_service.py`,
  `modules/services/startup_service.py`: migration ownership and schema checks.
- `modules/db/repositories.py`: cleanup queries and ordered record deletion.
- `modules/services/pipeline_cleanup_service.py`: eligibility and confirmation.
- `modules/services/ingestion_assignment_service.py`,
  `modules/services/upload_submission_service.py`: cleaned submission handling.
- `modules/api_router.py`: authenticated administrative lifecycle endpoints.
- `web/templates/pipeline_config.html`, `web/static/js/pipeline_config.js`,
  `web/static/js/pipeline-config/`: production controls and dialogs.
- `web/templates/upload_process.html`, `web/static/js/upload-process/`: clear
  purged receipt identities without automatically submitting new work.
- `web/static/css/vendor.css`, `web/templates/app_base.html`: rebuilt production
  styles and cache release.
- `test/helpers_cleanup.py`: complete synthetic processing histories.
- `test/services/test_pipeline_cleanup_service.py`: cleanup safety and rollback.
- `test/db/test_pipeline_cleanup_migration.py`: upgrade preservation/idempotency.
- `test/integration/test_pipeline_cleanup_api.py`: endpoint and security coverage.
- `test/integration/test_versioned_pipeline_api.py`: renaming preserves template
  identity, draft, and immutable versions.
- `test/visual/test_pipeline_cleanup_visual.py`: synthetic browser scenarios.
- `test/visual/test_pipeline_metadata_visual.py`: metadata/availability saves
  preserve unsaved task edits and selected steps.
- `test/db/test_migrations.py`, `test/db/test_versioned_config_migration.py`,
  `test/integration/test_manual_split.py`, `test/services/test_startup_service.py`:
  update expected schema markers and verify older-schema startup behavior.
- `test/integration/test_new_ui_routes.py`,
  `test/integration/test_versioned_admin_pages.py`,
  `test/visual/test_operator_page_modules.py`,
  `test/visual/test_pipeline_controller_modules.py`: updated asset releases.
- `test/visual/test_schema_editor_regressions.py`: retain activation/reset UI
  contract after replacing the metadata reload helper.
- `README.md`, `docs/user_guide.md`, `docs/design_architecture.md`: maintained
  feature, workflow, and ownership descriptions.
- `docs/pipeline_retention_admin_guide.md`: operator/API/storage/recovery contract.
- `docs/technical_operations_reference.md`: IT material separated from the
  app-based user guide; task-reference links updated in the review and extraction guides.
- `docs/watch_folder_admin_reference.md`, `docs/frontend_deployment.md`:
  binding consequences, cache versions, schema upgrade, and rollback limits.
- `tasks/design-multiple-pipeline-templates.md`: current lifecycle/retention design.
- `tasks/design-pipeline-cleanup-options.md`: superseded options and approved scope.

## Decisions

- Keep existing audit events unchanged, with historical entity IDs even after
  the operational records are removed; record each cleanup as an admin event.
- Remove artifact registrations with deleted history, while leaving physical
  files untouched. Deleted records disappear from Reports and their application
  preview links no longer resolve.
- Exclude a whole batch when any document, child, job, task, manual split, or
  review still needs processing. Treat `review_completed` as resumable.
- Cutoffs are exclusive UTC dates based on the latest recorded processing
  activity, not just upload time. An expired or changed preview requires refresh.
- Retain minimal upload receipt tombstones so retrying an old submission cannot
  accidentally create duplicate work after cleanup.

## Verification completed 2026-10-09

All commands ran from the repository root with the repository virtual
environment. Server-importing tests used an ignored synthetic configuration;
the developer's active configuration, database, documents, and supplied login
password were not used by these checks.

```powershell
$env:CONFIG_PATH = (Join-Path (Get-Location) 'output/cleanup-verification/config.yaml')
$env:DOCFLOW_STDIO_CAPTURED = '1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q test\visual\test_pipeline_cleanup_visual.py --tb=short
.\.venv\Scripts\python.exe -m pytest -q test\db\test_pipeline_cleanup_migration.py test\services\test_pipeline_cleanup_service.py test\integration\test_manual_split.py::test_version7_migration_preserves_reviews_as_extraction --tb=short
npm run build:css
git -c core.safecrlf=false diff --check
```

- Full suite: **1,647 passed, 4 skipped** in 330.79 seconds.
- Final lifecycle browser run: **4 passed** in 20.31 seconds. Tested archive
  blockers, pause/inactivate/archive, visibility, exact-name confirmation,
  cleanup results, empty eligibility, cancellation/Escape/focus, protected
  reviews, stale previews, CSRF, and purged upload receipt recovery.
- Focused migration/service checks: **32 passed** in 6.36 seconds, including
  version-8 upgrade, original audit rowids/payloads, rollback, cross-batch links,
  changed/expired/actor-bound previews, and processing dependencies.
- CSS build and diff whitespace checks passed. The build reported an existing
  outdated Browserslist database warning; dependency versions were not changed.
- Inspected the settled desktop and 390px mobile screenshots in
  `output/playwright/pipeline-cleanup/`: archive blockers, cleanup preview,
  confirmation, and successful results. Only synthetic document data appears.
- Pyright was not run: the repository virtual environment has no `pyright`
  module. No live provider checks or compaction were performed.

Deployment: restart through the normal application entry point so the parent
applies schema 9 before its web/worker children verify it. A standalone web
process remains verification-only unless explicitly started in migration mode.
No production history is automatically cleaned by startup or this migration.

## Code review follow-up, 2026-10-09

The review found and corrected these editor regressions:

- Selecting archived availability could bypass the dedicated impact/confirmation
  flow. The dropdown now selects only active/inactive states; archive has its
  own action and unsaved-edit guard.
- Archived drafts still enabled Reset. Reset and other draft mutations are now
  disabled for archived or loading selections.
- Archiving checked Show archived without fetching the other archived templates.
  The complete list now refreshes while retaining the current selection. A
  failed list refresh reports a warning without misreporting a completed archive.
- Overlapping template reads could mix one pipeline's selected ID with another
  pipeline's draft. Loads now stage a complete snapshot and ignore stale reads;
  mutation controls are disabled while loading.
- Availability/activation reloaded the editor and discarded unsaved task edits.
  These saves now apply only their saved fields, preserving draft edits and
  selection just like metadata saves.

The pipeline release is `pipeline-lifecycle-2`, including the parent-relative
entry/controller imports that the release tool does not currently scan.
Regression coverage exercises all five cases and archive-list refresh failure.
An older source-text assertion referenced the removed metadata helper; it was
updated while retaining the activation/reset UI contract. Real-browser tests
cover the resulting availability behavior.

Additional maintained documentation: README, user guide, architecture,
watch-folder reference, deployment/rollback guidance, versioned-pipeline design,
historical options, and the new operator/API/storage retention guide. Local link
targets and balanced code fences were checked across all nine Markdown files.

Focused review checks:

```powershell
$env:CONFIG_PATH = (Join-Path (Get-Location) 'output/cleanup-verification/config.yaml')
$env:DOCFLOW_STDIO_CAPTURED = '1'
.\.venv\Scripts\python.exe -m pytest -q test\visual\test_pipeline_cleanup_visual.py test\visual\test_pipeline_metadata_visual.py test\visual\test_pipeline_controller_modules.py test\integration\test_pipeline_cleanup_api.py test\integration\test_versioned_admin_pages.py test\integration\test_versioned_pipeline_api.py test\db\test_pipeline_cleanup_migration.py test\services\test_pipeline_cleanup_service.py --tb=short
.\.venv\Scripts\python.exe -m pytest -q test\visual\test_schema_editor_regressions.py --tb=short
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
npm run build:css
git -c core.safecrlf=false diff --check
```

- Focused migration/service/API/browser checks: **71 passed** in 57.19 seconds
  before adding the archive-list refresh failure scenario to the full suite.
- Nearby editor source checks after updating the old assertion: **15 passed**
  in 0.13 seconds.
- Release checker: all **16** feature graphs passed; parent-relative pipeline
  entry/controller imports were also inspected and aligned manually.
- CSS rebuild, whitespace, local documentation links, and code fences passed.
  The existing Browserslist database warning remains informational.
- Re-inspected synthetic desktop archive blockers/cleanup results and 390px
  mobile preview/confirmation screenshots, including scrolling to confirmation.

Final review validation used the same isolated configuration and environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
```

- Final full suite: **1,653 passed, 4 skipped** in **334.15 seconds**, including
  all 12 pipeline lifecycle/metadata browser scenarios and the corrected
  activation/reset source assertion. No remaining test failures were found.
- No additional data-deletion or migration defects were found in the final diff
  review. The developer's active database, configuration, and customer documents
  were not modified by verification.
- Pyright remains unavailable in the repository virtual environment. Live
  provider checks, physical-file deletion, and compaction were not run.

## User-guide audience review verification

- Documentation-only follow-up: updated `docs/user_guide.md` to version 3.13,
  added `docs/technical_operations_reference.md`, and updated README plus
  extraction/review-form task-reference links.
- Compared instructions with the production templates and controllers for
  pipeline creation/publication, review forms, watch folders, review actions,
  and password changes. Documented the existing Operator password-field label
  mismatch; both account changes require the current administrator password.
- Ran a local Markdown checker through `.\.venv\Scripts\python.exe -`:
  **139 local links/anchors and code fences across seven documents passed**;
  both maintained incoming user-guide anchor links also passed.
- Ran `git -c core.safecrlf=false diff --check`: passed.
- No application code changed in this follow-up. Unit and browser tests were
  not rerun for prose changes; the implementation's full-suite and visual-test
  results are recorded above.
