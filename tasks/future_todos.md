# Future To-Do Items

- [x] Implement schema validation for config.yaml to ensure configuration integrity and early error detection.
- [x] Refactor ConfigManager's internal path validation logic (_validate_static_paths, _precreate_required_directories, _validate_dynamic_paths) to support the new 'tasks' and 'pipeline' schema, and update test/test_config_manager/config.yaml and its corresponding tests accordingly.

## Completed v2 LlamaExtract Array-of-Objects Implementation

### v2 Migration Checklist ✅ (Completed)
- [x] **Validate tests**: All v2 unit tests pass (extraction, storage JSON/CSV, edge cases)
- [x] **Update config.yaml**: Replace v1 storage tasks with v2 modules and add CSV storage to pipeline
- [x] **Test staging**: Deploy to staging environment and validate with sample documents
- [x] **Monitor performance**: Verify no degradation in processing speed or memory usage
- [x] **User acceptance**: Test with actual invoice documents containing line items
- [x] **Rollback plan**: Keep v1 modules available as fallback if issues arise
- [x] **Documentation**: Update user guide and architecture docs with v2 usage examples