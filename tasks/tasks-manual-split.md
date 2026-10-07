# Manual split implementation

Approved design: [design-manual-split-task.md](design-manual-split-task.md).

- [x] Persist typed reviews and manual decisions with revisions and identity checks.
- [x] Share local child materialization; implement manual skip/pause/application and resume/fan-out.
- [x] Add authenticated APIs, task catalog/editor validation, production queue and PDF form.
- [x] Verify migrations, skip/split/review/resume/fan-in and cloud regressions with focused tests.
- [x] Run full tests and frontend builds; update maintained documentation.
- [x] Create admin validation pipeline; visually test Superstore single-page, merged, and no-split cases through JSON export.
- [x] Review recovery and draft conflicts; fix confirmed defects and verify regression coverage.
- [x] Restart the app and complete another live visual walkthrough as operator through JSON export; update relevant documentation.
- [x] Fix the submission response waiting for child workflows; verify acknowledgment during slow processing and update the running app when idle.

## Relevant Files

- `modules/db/`: typed review/decision schema, migrations, and repositories.
- `modules/services/manual_split_service.py`: local task and review decision orchestration.
- `modules/services/split_execution_service.py`: shared PDF/child materialization.
- `standard_step/split/manual_split.py`: approved configured manual task.
- `modules/resume_manager.py`, `modules/workflow_manager.py`, `modules/workflow_loader.py`: manual re-entry and fan-out attribution.
- `modules/services/review_service.py`, `modules/api_router.py`, `web/server.py`: typed review and HTTP integration.
- `web/templates/`, `web/static/js/`, `web/static/css/`: production UI and frontend build.
- `test/`: synthetic-data coverage and regressions.
- `docs/`, `tasks/standard_task_creation_guidelines.md`: maintained behavior and task contracts.
- `modules/split_models.py`, `standard_step/split/llamacloud_split_adapter.py`: provider-independent segment/result records.
- `modules/services/pipeline_validation_service.py`, `modules/services/task_registry_service.py`, `modules/services/startup_service.py`: approved task configuration and schema readiness.
- `modules/services/artifact_service.py`, `modules/services/split_result_service.py`: strict artifact writes and typed waiting/skip results.
- `tools/config_check/parameter_validator.py`, `tools/frontend_release_check.py`: manual parameters and release graph/cache updates; bounded Windows file replacement.
- `standard_step/split/llamacloud_split.py`: shared materialization delegation and compatibility PDF writer import.
- `test/integration/test_manual_split.py`, `test/visual/test_manual_split_ui.py`: new service/API/workflow/migration and real browser coverage.
- `test/db/test_migrations.py`, `test/db/test_versioned_config_migration.py`, `test/services/test_startup_service.py`: schema-version assertions.
- `test/integration/test_new_ui_routes.py`, `test/integration/test_versioned_admin_pages.py`, `test/visual/test_operator_page_modules.py`, `test/visual/test_pipeline_controller_modules.py`: route stubs and cache-version assertions.
- `test/standard_step/test_standard_task_edge_cases.py`: shared materializer compensation mocks.
- `.gitignore`: keep local validation screenshots, logs, and database backup out of Git.

## Verification

See [validation evidence](../docs/manual_split_validation.md): full suite 1,586 passed / 4 skipped; final focused suite 41 passed; CSS and 17 release graphs passed. All three real Superstore cases reached reviewed JSON export.

After source review fixes on 2026-10-07: full suite **1,598 passed / 4 skipped**;
manual integration suite **29 passed**; 17 release graphs and diff whitespace
checks passed. An additional operator walkthrough verified draft persistence,
matching boundary markers, no-split continuation, and one correct JSON export
with no child documents or split workflows. App left running.
