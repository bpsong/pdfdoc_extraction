# Future To-Do Items

- [x] Implement schema validation for config.yaml to ensure configuration integrity and early error detection.
- [x] Refactor ConfigManager's internal path validation logic (_validate_static_paths, _precreate_required_directories, _validate_dynamic_paths) to support the new 'tasks' and 'pipeline' schema, and update test/test_config_manager/config.yaml and its corresponding tests accordingly.

## Upcoming Enhancements for config-check Tool

- [x] Add module-aware extraction validation (standard_step.extraction.*) so config-check enforces presence of `api_key` and `agent_id` before runtime.
- [x] Have config-check warn when more than one extraction field is marked `is_table: true`, reflecting the single-table limitation baked into v2 storage tasks.
- [x] Teach config-check the `store_file_to_localdrive` schema (require `files_dir`/`filename`, validate types) to stop runtime-only failures.
- [x] Allow nested `storage.{data_dir, filename}` blocks for v2 storage tasks and fall back to top-level params; flag unknown keys for clarity.
- [x] Emit a config-check warning when v2 storage tasks cannot locate `extraction.fields` metadata (missing `extract_document_data_v2` task), so alias gaps are expected.
- [x] Extend rules-task validation to type-check optional knobs (`write_value`, `backup`, `task_slug`) and verify `reference_file` looks like a `.csv` path.
- [x] Ensure config-check validates `CleanupTask` `processing_dir` overrides as non-empty strings before they become `Path` objects.
- [x] Cross-check storage filename templates in config-check so every `{token}` maps to an available scalar extraction field.

## Schema Validation Enhancements Needed

- [x] Add `web.host` to schema validation (currently used in `main.py` for web server host configuration)
- [x] Add `web.port` to schema validation (currently used in `main.py` for web server port configuration)
- [x] Add `watch_folder.validate_pdf_header` to schema validation (currently used in `modules/file_processor.py` for PDF header validation)
- [x] Add `watch_folder.processing_dir` to schema validation (currently used throughout codebase for processing directory path)

## Config Checker Tool Improvements

- [x] Add module and class import validation to config-check tool - currently the tool validates structure and dependencies but doesn't verify that module names (e.g., "standard_step.storage.store_metadata_as_jsonx") and class names are actually importable Python modules/classes

### Enhanced Rules Task Validation (update_reference.py) for config-check Tool

- [x] **File Path Validation**: Add validation that `reference_file` parameter points to an existing, readable CSV file before runtime
- [x] **CSV Structure Validation**: Verify that the reference CSV file can be opened/parsed and contains proper headers
- [x] **Column Existence Validation**: Check that `update_field` and all clause `column` values exist as actual columns in the target CSV file
- [x] **Clause Uniqueness Validation**: 
  - Error on completely identical clauses (same column + same from_context)
  - Warning on multiple clauses referencing the same CSV column (potentially impossible AND conditions)
  - Info on multiple clauses using the same context value (might be intentional but worth noting)
- [x] **Context Path Validation**: Validate `from_context` dotted paths follow proper notation and reference realistic pipeline fields
- [x] **Deprecation Warnings**: Emit warnings for deprecated "data." prefixes in `from_context` paths (should use bare field names)
- [x] **Type Consistency Validation**: When `number: true` is specified, validate that the referenced context field is likely to be numeric based on extraction field definitions
- [x] **Cross-Pipeline Validation**: Ensure rules tasks are positioned after extraction tasks in the pipeline and that referenced fields are available from upstream tasks
- [x] **Semantic Validation**: 
  - Warn about potentially problematic configurations (e.g., string comparison on obviously numeric fields)
  - Detect unrealistic field references that don't match common extraction patterns
  - Flag multiple clauses on the same column that might create impossible conditions

### General Config-Check Enhancements for config-check Tool

- [x] **Runtime File Validation Mode**: Add optional `--check-files` flag to validate file paths, CSV structures, and other runtime dependencies
- [x] **Field Consistency Validation**: Cross-reference field names between extraction tasks and downstream storage/rules tasks to catch naming mismatches
- [x] **Pipeline Dependency Analysis**: Validate that tasks are ordered correctly (extraction → rules → storage → archiver) and that required fields flow properly between stages
- [x] **Template Token Validation Enhancement**: Extend existing template validation to check against actual extraction field definitions rather than just basic syntax
- [x] **Configuration Completeness Warnings**: Warn about common missing configurations (e.g., rules tasks without corresponding extraction tasks, storage tasks without required fields)
- [ ] **Performance Impact Analysis**: Flag configurations that might cause performance issues (e.g., too many extraction fields, overly complex rules clauses)
- [ ] **Security Validation**: Check for potential security issues in file paths, ensure proper path traversal protection in directory configurations

## Completed v2 LlamaExtract Array-of-Objects Implementation

### v2 Migration Checklist . (Completed)
- [x] **Validate tests**: All v2 unit tests pass (extraction, storage JSON/CSV, edge cases)
- [x] **Update config.yaml**: Replace v1 storage tasks with v2 modules and add CSV storage to pipeline
- [x] **Test staging**: Deploy to staging environment and validate with sample documents
- [x] **Monitor performance**: Verify no degradation in processing speed or memory usage
- [x] **User acceptance**: Test with actual invoice documents containing line items
- [x] **Rollback plan**: Keep v1 modules available as fallback if issues arise
- [x] **Documentation**: Update user guide and architecture docs with v2 usage examples
