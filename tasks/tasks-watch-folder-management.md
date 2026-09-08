# Watch-folder management P0 and P1

Approved visual target: dedicated Watch folders navigation, binding table, and
edit drawer from the September 8, 2026 image concept.

## Delivery rules

Use synthetic data for verification. Preserve exact assignments on historical
batches. Re-read updated documentation, compare complete files against the
baseline, and review diffs for unintended removals. Do not mark phases complete
until verification passes.

## Phases

- [x] 1. Lifecycle and migration: paused, unbound, retired, path reuse, revisions,
  history, and lifecycle/migration unit tests.
- [x] 2. Management APIs and coordinator consistency: exact-version selection,
  concurrent edits/claims, authorization, and API/coordinator tests.
- [x] 3. Dedicated page: navigation, table, accessible drawer, lifecycle actions,
  validation, unit/browser tests, and CSS build.
- [x] 4. Diagnostics: persisted scan health, stale state, non-ingesting access
  checks, and unit/integration tests.
- [x] 5. Search, filters, retired view, activity, audit and report navigation,
  with unit/integration tests.
- [x] 6. Maintained documentation updated, re-read, and diff-reviewed
  for preservation of unrelated content and accurate behavior.
- [x] 7. Full regression, final browser visual comparison, screenshots, and
  review of all changes.
- [x] 7.1. Fix CSS overriding hidden lifecycle actions in the Add drawer; verify
  desktop/mobile visibility and regenerate screenshots.

## Relevant Files

- `tasks/tasks-watch-folder-management.md`: implementation and verification log.
- `modules/db/migrations.py`, `modules/db/schema.sql`: version 7 lifecycle
  migration, preserved references, and per-binding health storage.
- `modules/db/repositories.py`: lifecycle revisions, health, activity, and audit queries.
- `modules/services/ingress_binding_service.py`: lifecycle, exact-version
  validation, conflict checks, diagnostics, and management summaries.
- `modules/services/watch_folder_coordinator.py`: current-binding serialized
  claims, assignment snapshots, and scan observations.
- `modules/services/startup_service.py`: required health-table readiness check.
- `modules/api_router.py`: admin management, diagnostics, and activity endpoints.
- `web/server.py`, `web/templates/app_base.html`: authenticated page and navigation.
- `web/templates/watch_folders.html`, `web/static/js/watch_folders.js`,
  `web/static/js/watch_folder_view_models.js`, `web/static/css/watch_folders.css`:
  management table, drawer, lifecycle, filters, and activity UI.
- `web/templates/pipeline_config.html`, `web/static/js/pipeline_config.js`:
  replace embedded management with a dedicated-page summary link.
- `web/templates/reports.html`, `web/static/js/reports.js`: binding-scoped batch view.
- `web/static/css/vendor.css`: rebuilt production Tailwind/DaisyUI output.
- `test/services/test_watch_folder_management.py`: migration/lifecycle/claim/
  health tests and Node-executed frontend helper tests.
- `test/integration/test_watch_folder_management_api.py`: admin access,
  validation, revision conflicts, lifecycle, and paginated API history.
- `test/visual/test_watch_folder_management_visual.py`: end-to-end lifecycle,
  version upgrade, history/Reports, missing-folder deletion, and responsive evidence.
- `test/db/test_migrations.py`, `test/db/test_versioned_config_migration.py`,
  `test/services/test_startup_service.py`: schema-version expectations.
- `test/integration/test_new_ui_routes.py`,
  `test/integration/test_versioned_admin_pages.py`,
  `test/visual/test_schema_editor_regressions.py`,
  `test/visual/test_schema_review_visual.py`: updated navigation/layout regressions;
  unrelated schema, upload, and editor checks retained.
- `docs/design_architecture.md`, `docs/user_guide.md`,
  `tasks/future-multi-document-routing.md`: maintained behavior and operator guidance.

## Verification evidence

All Python commands run from the repository root using the repository venv.
Tests use an ignored synthetic bootstrap configuration, not the active runtime DB:

```powershell
$env:CONFIG_PATH = (Resolve-Path output/watch-folder-test-bootstrap/config.yaml).Path
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m pytest -v test/visual/test_watch_folder_management_visual.py
npm run build:css
git diff --check
```

- Lifecycle/API/coordinator tests cover unbind, revision conflicts, retirement,
  path reuse, missing folders, version pinning, historical reference preservation,
  repeated migration, stale health, non-ingesting checks, and malformed requests.
- Final full suite: **1457 passed, 4 skipped in 181.35 seconds**. Focused visual
  rerun after the hidden-action correction: **2 passed in 21.41 seconds**.
  CSS build and `git diff --check` passed. Final mobile screenshot was re-opened
  and verified: new-folder lifecycle actions are hidden, the footer is reachable,
  and the drawer does not overflow the viewport horizontally.
- Documentation was re-read after edits and reviewed against the Git baseline.
  Complete-file heading and fenced-code comparisons found no removed headings
  or changed/removed original code examples: architecture 26 → 27 headings / 8
  preserved blocks; user guide 87 → 87 / 23; routing direction 20 → 20 / 2.
  The diff changes only relevant watch-folder/audit/navigation guidance and the
  guide release entry. An extra changelog blank line was corrected on re-read.
- Live login verified the dedicated navigation, three unchanged existing
  bindings, available upgrades, and the edit drawer without saving user settings.
- Synthetic screenshots: `output/playwright/watch-folder-management/` contains
  desktop table, edit drawer, update badge, retired activity, empty filter,
  inaccessible-folder, and mobile drawer evidence.
- The local database was backed up with SQLite backup before version 7 migration:
  `data/backups/before-watch-folder-v7-20260908-215327.sqlite3` (ignored).
- The web interface is running at `http://127.0.0.1:8000`; no real-data coordinator
  or processing worker was started. Scan health is therefore correctly stale.
- Live provider checks and unconfigured Pyright/Ruff were not run. CSS build
  succeeds with the existing non-blocking Browserslist database-age warning.
