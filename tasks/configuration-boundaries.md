# Configuration and migration boundaries

## Phases

- [x] 1. Shared config-relative path resolution and CLI regression tests.
- [x] 2. Configuration exceptions and separate directory preparation.
- [x] 3. Explicit configuration instances, defensive snapshots, migration refresh.
- [x] 4. Startup migration orchestration and public schema-path resolution.
- [x] 5. Integration verification, documentation, and final diff review.

After each phase record focused verification and whether an actual visual test
is necessary. Use synthetic configuration and databases throughout.

## Verification and visual-test decisions

Phase 1: 39 tests passed (configuration boundaries/manager, schema service,
path validator, stored validator). Visual test unnecessary: filesystem resolution
only; no rendered UI or browser behavior changed. Explicit --base-dir affects
filesystem validation only, never the database selected by deployment YAML.

Phase 2: 56 tests passed (configuration, runtime orchestration, defensive unit
coverage, startup migration gates). Visual test unnecessary: startup failure
handling and filesystem preparation do not alter rendered pages.

Phase 3: 77 focused tests and a real Chromium smoke test passed. Inspected
screenshots of Upload, Admin Overview, and Validation Center from a fresh
synthetic app. Login, navigation, validation, and reload exercised the new
request dependency binding. Existing validation presentation overflow is outside
this backend change; synthetic empty legacy pipeline fields produce findings.

Phase 4: 119 passed, 3 platform-specific skips across migration, startup, schema,
and path checks. Database imports no longer load services; real ConfigManager
refresh after legacy cutover is covered. No additional visual test required:
this phase changes startup orchestration and import boundaries, covered by
database rollback/idempotency and startup tests. Final verification reruns the
fresh-app browser smoke test through the relocated migration entry point.

Phase 5: final full run passed (1453 passed, 4 skipped in 291.33s). The first
run's 8 setup errors came from an obsolete workflow test mock of
ConfigManager.sys.exit; that mock was removed and the affected focused tests
passed. Direct supervisor/worker/web process rejection of malformed YAML passed.
The Codex browser smoke run uploaded invoice_Steven Roelle_14184.pdf through
Superstore GLM-OCR Review JSON v4, completed GLM-OCR extraction, paused at the
Review Gate, and displayed the item in Human Review with extracted fields.
The phase is ready for release commit.

Pyright reports two errors at test/integration/test_review_ui_api.py:241,244:
TestClient.app may be _WrapASGI2 and does not expose dependency_overrides.
These statements are unchanged from HEAD. No production typing errors reported.

## Verification commands

Run from the repository root using the repository virtual environment:

```powershell
$env:RUN_LLAMACLOUD_SPLIT_SMOKE = '0'
.\.venv\Scripts\python.exe -m pytest -v --tb=short
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_configuration_boundaries_visual.py
.\.venv\Scripts\python.exe -m pytest -q test/core/test_configuration_boundaries.py test/core/test_config_manager.py test/extraction/test_extraction.py test/workflow/test_workflow_loader.py --tb=short
pyright
git -c core.safecrlf=false diff --check
```

No frontend build is required: no templates, JavaScript, CSS, or frontend
dependencies changed. Live provider calls are not part of verification.

## Change map

- modules/config_paths.py and config-check path validators: shared resolution.
- modules/config_manager.py: exceptions, directory preparation, isolated snapshots.
- main.py, tools/processing_worker.py, web/server.py: startup error boundaries.
- modules/request_dependencies.py and modules/api_router.py: per-app request binding.
- modules/db/migrations.py and schema_version.py: structural upgrades and markers.
- modules/services/startup_migration_service.py: startup cutover coordination.
- modules/services/legacy_versioned_config_migration.py and schema_service.py:
  explicit snapshot replacement and public root-constrained schema resolution.
- Production consumers and test modules: migrate imports to the service owner.
- New configuration-boundary tests in core, db, integration, and visual folders.
- docs/design_architecture.md, docs/user_guide.md,
  docs/config_check_troubleshooting.md, tools/config_check/README.md: operational
  rules and API ownership.
