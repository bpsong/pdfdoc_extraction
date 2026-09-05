# Change summary — 2026-09-05

This checkpoint records the accumulated local changes and the previously
unpushed `b41de23` commit ("experiment a"). The associated test suite repairs
are included in the follow-up commit after this checkpoint.

## Processing and workflow state

- Add schema version 4 and a durable `processing_jobs` table, repository,
  queue service, worker implementation, and standalone worker CLI.
- Enqueue web uploads and watch-folder ingestion in SQLite. Start and supervise
  the worker alongside the web server and watch-folder coordinator.
- Support job claims, lease expiry recovery, attempt limits, and retry delays.
  Defaults are a 1-second poll, 3600-second lease, 3 attempts, and 5-second retry
  delay. External calls and task side effects are not transactional.
- Require exact published pipeline assignments for workflow launch, child
  processing, and resume; remove deployment-YAML execution fallbacks.
- Centralize document status transitions with atomic audit events and expose
  status history in processing responses. Remove runtime text-status use while
  retaining SQLite-backed legacy API response shapes.
- Read runtime pipeline settings and task catalog usage from SQLite versions.
  Resolve deployment path validation relative to the YAML configuration file.
- Remove storage-task fallbacks to global extraction settings; use published
  task parameters for storage configuration and field metadata.

## PDF review and operator interface

- Vendor PDF.js 4.10.38 and its worker for same-origin source-PDF rendering.
- Add active-page rendering, zoom, citation navigation, automatic centering,
  and viewer-cache invalidation when review navigation changes.
- Show provider-aware source evidence: LlamaCloud bounding boxes when present,
  and GLM-OCR page navigation without fabricated bounding boxes.
- Include extraction-provider metadata in review responses and account for
  pinned pipeline artifact directories in PDF preview access checks.
- Add aggregate upload transfer progress, cancellation, keyboard activation,
  loading placeholders, fetch retry controls, and contextual help.
- Standardize queue tables, status badges, confidence text bands, and concise
  assistive-technology announcements across operator pages.
- Rebuild the committed frontend CSS and update the npm lock file.

## GLM-OCR and experiments

- Raise the production resolver context default from 8192 to 18000 across
  implementation, catalog/editor defaults, tests, and documentation.
- Include the earlier experiment-A runners for GLM transcription plus Qwen
  page vision, a Qwen-only control, resumable batch comparisons, and analysis.
- Include the standalone experiment-B PDF.js citation viewer and its server
  tests. Tests use temporary synthetic inputs and require no private invoice.
- Keep raw invoice extraction JSON local through an explicit ignore rule;
  PDFs, runtime databases, credentials, and generated experiment results are
  not included in this checkpoint.

## Tests and documentation

- Expand coverage across database repositories, queue processing, workflow
  orchestration, extraction adapters/prompts, storage tasks, configuration
  validators, versioned administration, review services, API routes, and UI.
- Update the README, architecture, user guide, GLM-OCR task notes, config-check
  documentation, and task standards for versioned execution and queue recovery.

## Verification

- `npm run build:css`: passed; Browserslist reported an outdated caniuse-lite
  database (non-blocking).
- `.\.venv\Scripts\python.exe -m pytest -v test/services/test_processing_worker.py test/visual/test_pdf_viewer_regressions.py test/visual/test_operator_feedback_visual.py`:
  8 passed.
- `.\.venv\Scripts\python.exe -m pytest -v experimentb/pdfjs_viewer/test_server.py`:
  2 passed.
- `.\.venv\Scripts\python.exe -m pytest -v`: interrupted after reaching the
  live third-party connection test. The replacement run explicitly excludes it.
- `.\.venv\Scripts\python.exe -m pytest -q --tb=short --ignore=test/third_party/llamacloud_connection_test.py`:
  **1379 passed, 4 skipped, 1 warning** in 168.70 seconds. The warning is a
  Python `runpy` warning from a config-check CLI branch test.
- `git -c core.safecrlf=false diff --check`: passed before staging.
- Reviewed changed/new file paths and credential-pattern matches; matches were
  documentation placeholders or synthetic test values. Raw extraction data was
  excluded. No extraction smoke check, Pyright, or Ruff run was performed. The initial
  suite reached the live connection test before it was stopped; whether a
  remote request completed was not verified.

## Follow-up

- [x] Update stale tests for version-pinned workflow execution, durable queue
  processing, explicit task configuration, and active-page PDF rendering.
- [x] Repair child-workflow rollback to use the active SQLite connection.

## File inventory for this checkpoint

The earlier `b41de23` commit additionally contains the experiment-A scripts
and related GLM-OCR adapter/prompt changes described above.

- `.gitignore`
- `README.md`
- `docs/change-summary-2026-09-05.md`
- `docs/design_architecture.md`
- `docs/user_guide.md`
- `experimentb/pdfjs_viewer/README.md`
- `experimentb/pdfjs_viewer/public/app.js`
- `experimentb/pdfjs_viewer/public/index.html`
- `experimentb/pdfjs_viewer/public/styles.css`
- `experimentb/pdfjs_viewer/server.py`
- `experimentb/pdfjs_viewer/test_server.py`
- `main.py`
- `modules/api_router.py`
- `modules/config_manager.py`
- `modules/db/migrations.py`
- `modules/db/repositories.py`
- `modules/db/schema.sql`
- `modules/exceptions.py`
- `modules/file_processor.py`
- `modules/resume_manager.py`
- `modules/services/document_service.py`
- `modules/services/fan_in_service.py`
- `modules/services/ingestion_assignment_service.py`
- `modules/services/processing_job_service.py`
- `modules/services/processing_state_service.py`
- `modules/services/processing_worker.py`
- `modules/services/review_service.py`
- `modules/services/runtime_settings_service.py`
- `modules/services/task_catalog_service.py`
- `modules/services/task_registry_service.py`
- `modules/services/watch_folder_coordinator.py`
- `modules/services/workflow_state_service.py`
- `modules/workflow_loader.py`
- `modules/workflow_manager.py`
- `package-lock.json`
- `package.json`
- `standard_step/archiver/archive_pdf.py`
- `standard_step/extraction/glm_ocr_adapter.py`
- `standard_step/extraction/glm_ocr_extract.py`
- `standard_step/review/review_gate.py`
- `standard_step/split/llamacloud_split.py`
- `standard_step/storage/store_file_to_localdrive.py`
- `standard_step/storage/store_metadata_as_csv.py`
- `standard_step/storage/store_metadata_as_json.py`
- `tasks/design-and-implementation-glm-ocr-extract-task.md`
- `tasks/standard_task_creation_guidelines.md`
- `test/core/test_misc_edge_coverage.py`
- `test/core/test_runtime_orchestration.py`
- `test/db/test_migrations.py`
- `test/db/test_repository_remaining_coverage.py`
- `test/extraction/test_extract_pdf_edge_cases.py`
- `test/extraction/test_glm_ocr_adapter_complete.py`
- `test/extraction/test_glm_ocr_extract.py`
- `test/extraction/test_glm_ocr_extract_complete.py`
- `test/extraction/test_glm_ocr_prompt_complete.py`
- `test/extraction/test_structured_fields_complete.py`
- `test/integration/test_api_edge_paths.py`
- `test/integration/test_api_router_helpers.py`
- `test/integration/test_batch_upload_api.py`
- `test/integration/test_extraction_results_api.py`
- `test/integration/test_new_ui_server_branches.py`
- `test/integration/test_review_ui_api.py`
- `test/integration/test_upload_pipeline_selection_ui.py`
- `test/integration/test_versioned_admin_route_matrix.py`
- `test/services/test_admin_settings_edge_cases.py`
- `test/services/test_batch_document_workflow_audit_services.py`
- `test/services/test_catalog_pipeline_edge_cases.py`
- `test/services/test_failure_service.py`
- `test/services/test_fan_in_service.py`
- `test/services/test_ingestion_assignment_service.py`
- `test/services/test_ingress_binding_service.py`
- `test/services/test_legacy_migration_helpers.py`
- `test/services/test_pipeline_config_service.py`
- `test/services/test_pipeline_template_branches.py`
- `test/services/test_portable_config_branches.py`
- `test/services/test_processing_state_branches.py`
- `test/services/test_processing_state_service.py`
- `test/services/test_processing_worker.py`
- `test/services/test_review_schema_version_branches.py`
- `test/services/test_review_service_branches.py`
- `test/services/test_task_registry_service.py`
- `test/services/test_validation_facade_branches.py`
- `test/services/test_versioned_admin_serializers.py`
- `test/services/test_versioned_config_contracts.py`
- `test/services/test_watch_folder_coordinator.py`
- `test/standard_step/test_standard_task_edge_cases.py`
- `test/storage/test_storage_edge_cases.py`
- `test/test_remaining_standard_step_coverage.py`
- `test/test_remaining_storage_coverage.py`
- `test/test_remaining_unit_coverage.py`
- `test/tools/config_check/test_parameter_validator_complete.py`
- `test/tools/config_check/test_remaining_branches.py`
- `test/tools/config_check/test_schema_task_validator_complete.py`
- `test/tools/config_check/test_stored_validator_complete.py`
- `test/tools/config_check/test_suggestions_complete.py`
- `test/tools/config_check/test_yaml_parser_complete.py`
- `test/utils/test_utilities.py`
- `test/visual/test_glm_ocr_pipeline_editor.py`
- `test/visual/test_operator_feedback_visual.py`
- `test/visual/test_pdf_viewer_regressions.py`
- `test/visual/test_schema_review_visual.py`
- `test/visual/test_ui_performance_assets.py`
- `test/workflow/test_workflow_edge_cases.py`
- `tools/config_check/README.md`
- `tools/processing_worker.py`
- `web/static/css/app.css`
- `web/static/css/vendor.css`
- `web/static/js/app.js`
- `web/static/js/extraction_results.js`
- `web/static/js/failures.js`
- `web/static/js/human_review.js`
- `web/static/js/pdf_viewer.js`
- `web/static/js/pipeline_config.js`
- `web/static/js/processing_overview.js`
- `web/static/js/reports.js`
- `web/static/js/review_queue.js`
- `web/static/js/split_results.js`
- `web/static/js/upload_process.js`
- `web/static/vendor/pdfjs/pdf.min.mjs`
- `web/static/vendor/pdfjs/pdf.worker.min.mjs`
- `web/templates/app_base.html`
- `web/templates/extraction_results.html`
- `web/templates/failures.html`
- `web/templates/human_review.html`
- `web/templates/processing_overview.html`
- `web/templates/reports.html`
- `web/templates/review_queue.html`
- `web/templates/split_results.html`
- `web/templates/upload_process.html`

## Initial failing checks repaired in the follow-up

These test identifiers failed in the original checkpoint run. They now pass in
the complete offline suite recorded above; this list is retained as the repair
scope, without private payloads or traceback contents.

- `FAILED test/core/test_core_components.py::test_file_processor_initialization_and_process_file`
- `FAILED test/core/test_misc_edge_coverage.py::test_file_processor_configuration_and_io_failures`
- `FAILED test/core/test_misc_edge_coverage.py::test_runtime_settings_invalid_pipeline_and_redaction`
- `FAILED test/db/test_versioned_config_migration.py::test_active_yaml_and_schemas_import_idempotently_with_collisions`
- `FAILED test/db/test_versioned_config_migration.py::test_committed_partial_attempt_with_matching_hash_resumes_without_duplicates`
- `FAILED test/integration/test_admin_routes.py::test_admin_task_catalog_api_returns_catalog`
- `FAILED test/integration/test_dynamic_processing_pipeline_api.py::test_processing_state_api_falls_back_for_historical_batch_without_snapshot`
- `FAILED test/integration/test_glm_ocr_pipeline.py::test_upload_and_watch_workflows_pause_review_resume_and_export_separately`
- `FAILED test/integration/test_input_processing.py::test_process_web_upload_success_pdf_header_valid`
- `FAILED test/integration/test_input_processing.py::test_process_web_upload_header_validation_disabled`
- `FAILED test/integration/test_input_processing.py::test_process_web_upload_supports_bytes_like_input`
- `FAILED test/integration/test_llamacloud_split_fanout.py::test_split_fanout_starts_child_workflows_and_skips_parent_reference_update`
- `FAILED test/integration/test_llamacloud_split_fanout.py::test_split_fanout_extract_preflight_failure_stops_children_once`
- `FAILED test/integration/test_review_pause_resume.py::test_review_pause_and_completion_resumes_from_next_task`
- `FAILED test/integration/test_settings_api.py::test_settings_api_returns_non_secret_runtime_settings[operator]`
- `FAILED test/integration/test_settings_api.py::test_settings_api_returns_non_secret_runtime_settings[admin]`
- `FAILED test/integration/test_split_fan_in_finalization.py::test_split_fan_in_finalizes_root_and_batch_after_child_workflows`
- `FAILED test/integration/test_sqlite_ingestion.py::test_web_upload_creates_sqlite_batch_document_and_workflow_context`
- `FAILED test/integration/test_sqlite_ingestion.py::test_watch_folder_ingestion_creates_matching_sqlite_records`
- `FAILED test/integration/test_sqlite_ingestion.py::test_retried_watch_processing_reuses_sqlite_ingestion_state`
- `FAILED test/integration/test_sqlite_ingestion.py::test_batch_api_endpoints_return_sqlite_state`
- `FAILED test/integration/test_sqlite_only_workflow_state.py::test_configured_workflow_uses_sqlite_state_without_status_text_files`
- `FAILED test/services/test_resume_manager.py::test_resume_manager_resumes_next_task_and_guards_duplicate_resume`
- `FAILED test/services/test_resume_manager.py::test_resume_manager_atomically_rejects_concurrent_resume`
- `FAILED test/services/test_resume_manager.py::test_resume_manager_finalizes_when_review_gate_is_last`
- `FAILED test/services/test_task_registry_service.py::test_startup_validation_logs_prints_waits_and_exits_for_unapproved_task`
- `FAILED test/services/test_task_registry_service.py::test_registry_malformed_custom_config_and_relative_log_fallbacks`
- `FAILED test/standard_step/test_standard_steps.py::test_init_with_param_and_fallback`
- `FAILED test/standard_step/test_standard_task_edge_cases.py::test_split_child_creation_and_rollback_compensation`
- `FAILED test/storage/test_storage_csv.py::test_scalar_only_fallback_writes_single_row`
- `FAILED test/storage/test_storage_csv.py::test_versioned_pipeline_does_not_inherit_yaml_extraction_fields`
- `FAILED test/storage/test_storage_csv.py::test_versioned_pipeline_uses_explicit_csv_extraction_fields`
- `FAILED test/storage/test_storage_csv.py::test_table_expands_rows_per_item_and_prefixes_item_columns`
- `FAILED test/storage/test_storage_csv.py::test_empty_table_fallbacks_to_single_row`
- `FAILED test/storage/test_storage_csv.py::test_filename_generation_template_and_uniqueness`
- `FAILED test/storage/test_storage_csv.py::test_error_handling_updates_context_and_status_on_exception`
- `FAILED test/storage/test_storage_csv.py::test_empty_data_dict_creates_minimal_csv`
- `FAILED test/storage/test_storage_csv.py::test_non_list_table_field_treated_as_scalar`
- `FAILED test/storage/test_storage_csv.py::test_mixed_table_items_converts_non_dicts`
- `FAILED test/storage/test_storage_csv.py::test_special_characters_and_newlines_in_csv_data`
- `FAILED test/storage/test_storage_csv.py::test_large_dataset_csv_handling - as...`
- `FAILED test/storage/test_storage_edge_cases.py::test_csv_run_handles_missing_invalid_and_irregular_table_data`
- `FAILED test/storage/test_storage_edge_cases.py::test_csv_defensive_table_and_header_shape_branches`
- `FAILED test/storage/test_storage_json.py::test_non_dict_items_in_table_converts_to_string`
- `FAILED test/test_remaining_unit_coverage.py::test_config_manager_missing_and_invalid_paths`
- `FAILED test/test_remaining_unit_coverage.py::test_document_artifact_user_and_portable_defensive_paths`
- `FAILED test/test_remaining_unit_coverage.py::test_workflow_loader_and_manager_defensive_child_paths`
- `FAILED test/tools/config_check/test_stored_validator_complete.py::test_readonly_database_and_schema_findings`
- `FAILED test/tools/config_check/test_stored_validator_complete.py::test_stored_validator_remaining_success_paths`
- `FAILED test/visual/test_schema_review_visual.py::test_review_visual_schema_driven_fields_desktop_and_mobile`
- `FAILED test/visual/test_schema_review_visual.py::test_extraction_results_visual_uses_shared_pdfjs_viewer`
- `FAILED test/visual/test_schema_review_visual.py::test_phase14_processing_identity_split_failure_review_and_reflow`
- `FAILED test/workflow/test_workflow_edge_cases.py::test_workflow_records_continuing_and_system_exit_failures_with_state`
- `FAILED test/workflow/test_workflow_edge_cases.py::test_load_workflow_rejects_invalid_unknown_and_incomplete_steps`
- `FAILED test/workflow/test_workflow_edge_cases.py::test_workflow_handles_future_results_and_housekeeping_failure`
- `FAILED test/workflow/test_workflow_edge_cases.py::test_workflow_records_task_exceptions[error0-stop-TaskError]`
- `FAILED test/workflow/test_workflow_edge_cases.py::test_workflow_records_task_exceptions[error1-stop-Unexpected error]`
- `FAILED test/workflow/test_workflow_edge_cases.py::test_workflow_manager_load_trigger_and_child_edge_paths`
- `FAILED test/workflow/test_workflow_edge_cases.py::test_workflow_manager_skips_missing_children_and_missing_failure_roots`
- `FAILED test/workflow/test_workflow_loader.py::test_valid_flow_execution_param[pipeline_slice0]`
- `FAILED test/workflow/test_workflow_loader.py::test_valid_flow_execution_param[pipeline_slice1]`
- `FAILED test/workflow/test_workflow_loader.py::test_flow_stops_on_error_param[pipeline_indices0]`
- `FAILED test/workflow/test_workflow_loader.py::test_housekeeping_runs_unconditionally_last`
- `FAILED test/workflow/test_workflow_loader.py::test_housekeeping_runs_despite_previous_task_failures`
- `FAILED test/workflow/test_workflow_loader.py::test_housekeeping_runs_with_empty_pipeline`
- `FAILED test/workflow/test_workflow_loader.py::test_housekeeping_execution_order_verification`
- `FAILED test/workflow/test_workflow_manager.py::test_workflow_manager_propagates_source_web`
- `FAILED test/workflow/test_workflow_manager.py::test_split_child_preflight_is_provider_specific_for_llama_and_glm`
- `FAILED test/workflow/test_workflow_task_run_tracking.py::test_workflow_loader_records_task_runs_and_stops_when_paused`
- `FAILED test/workflow/test_workflow_task_run_tracking.py::test_workflow_loader_contains_runtime_task_import_failure`
- `FAILED test/workflow/test_workflow_task_run_tracking.py::test_workflow_loader_records_internal_cleanup_without_moving_pipeline_cursor`
- `FAILED test/workflow/test_workflow_task_run_tracking.py::test_workflow_loader_records_failed_internal_cleanup`
- `FAILED test/workflow/test_workflow_task_run_tracking.py::test_workflow_loader_continue_does_not_fail_downstream_task`
- `ERROR test/workflow/test_workflow_manager.py::test_end_to_end_workflow_execution`
