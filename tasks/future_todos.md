# Future To-Do Items

- [x] Implement schema validation for config.yaml to ensure configuration integrity and early error detection.
- [x] Refactor ConfigManager's internal path validation logic (_validate_static_paths, _precreate_required_directories, _validate_dynamic_paths) to support the new 'tasks' and 'pipeline' schema, and update test/test_config_manager/config.yaml and its corresponding tests accordingly.

## Upcoming Enhancements for config-check Tool

- [ ] Add module-aware extraction validation (standard_step.extraction.*) so config-check enforces presence of `api_key` and `agent_id` before runtime.
- [ ] Have config-check warn when more than one extraction field is marked `is_table: true`, reflecting the single-table limitation baked into v2 storage tasks.
- [ ] Teach config-check the `store_file_to_localdrive` schema (require `files_dir`/`filename`, validate types) to stop runtime-only failures.
- [ ] Allow nested `storage.{data_dir, filename}` blocks for v2 storage tasks and fall back to top-level params; flag unknown keys for clarity.
- [ ] Emit a config-check warning when v2 storage tasks cannot locate `extraction.fields` metadata (missing `extract_document_data_v2` task), so alias gaps are expected.
- [ ] Extend rules-task validation to type-check optional knobs (`write_value`, `backup`, `task_slug`) and verify `reference_file` looks like a `.csv` path.
- [ ] Ensure config-check validates `CleanupTask` `processing_dir` overrides as non-empty strings before they become `Path` objects.
- [ ] Cross-check storage filename templates in config-check so every `{token}` maps to an available scalar extraction field.

## Completed v2 LlamaExtract Array-of-Objects Implementation

### v2 Migration Checklist . (Completed)
- [x] **Validate tests**: All v2 unit tests pass (extraction, storage JSON/CSV, edge cases)
- [x] **Update config.yaml**: Replace v1 storage tasks with v2 modules and add CSV storage to pipeline
- [x] **Test staging**: Deploy to staging environment and validate with sample documents
- [x] **Monitor performance**: Verify no degradation in processing speed or memory usage
- [x] **User acceptance**: Test with actual invoice documents containing line items
- [x] **Rollback plan**: Keep v1 modules available as fallback if issues arise
- [x] **Documentation**: Update user guide and architecture docs with v2 usage examples
