# Config Check Troubleshooting Guide

This guide summarizes the most common validation failures and provides corrective actions. Each section includes the typical error signature printed by the CLI and concrete steps to resolve the issue.

## Missing Directories Or Files

**Symptom**
```
[ERROR] web.upload_dir: Directory "C:/missing/uploads" does not exist
Suggestion: Create the directory or update the path in config
```

**Fixes**
- Create the directory on disk before running jobs: `New-Item -ItemType Directory -Path C:/missing/uploads`
- Or adjust the configuration value to point to an existing location.
- When using relative paths, pass `--base-dir` so the validator resolves them correctly.

## Watch Folder Not Prepared

**Symptom**
```
[ERROR] watch_folder.dir: Watch directory does not exist
```

**Fixes**
- Provision the folder manually. The validator intentionally refuses to auto-create watch folders.
- Double check that the account running the service has read/write permissions.

## YAML Parse Errors

**Symptom**
```
[ERROR] config: while scanning a quoted scalar ... found unexpected end of stream
```

**Fixes**
- Run `config-check validate --format json` to get precise line/column hints.
- Verify indentation is two spaces and that all quoted strings are terminated.
- For large files, validate subsets by commenting blocks with `#` until the offending section is isolated.

## Unknown Keys In Strict Mode

**Symptom**
```
[ERROR] web.unexpected: Unknown key is not permitted in strict mode
```

**Fixes**
- Remove the unexpected key or move it under the nearest `params` mapping if it belongs to a task.
- Disable strict mode (`--strict` flag) when validating legacy configs that intentionally carry extra metadata.

## Import Failures

**Symptom**
```
[ERROR] tasks.store_json.module: Unable to import module 'custom.invalid.module'
```

**Fixes**
- Confirm the package is installed in the active Python environment (`python -m pip show package-name`).
- Add the project root to `PYTHONPATH` or install the module in editable mode.
- Verify the class name matches the exported symbol inside the module.


## Missing Extraction Credentials

**Symptom**
```
[ERROR] tasks.extract_metadata.params.api_key: Extraction tasks require 'api_key' to be provided as a non-empty string.
[ERROR] tasks.extract_metadata.params.agent_id: Extraction tasks require 'agent_id' to be provided as a non-empty string.
```

**Fixes**
- Supply the credentials in `tasks.<name>.params` (they may be pulled from a secrets store at runtime, but the validator needs placeholders).
- Store the values in your deployment environment and reference them via templating if you cannot commit them to source control.
- Verify the module path starts with `standard_step.extraction.` or `custom_step.extraction.`; these task families always require both credentials.

## Multiple Table Extraction Fields

**Symptom**
```
[WARNING] tasks.extract_metadata.params.fields: Multiple extraction fields are marked is_table: true; v2 storage tasks currently support only a single table payload.
```

**Fixes**
- Keep only one field with `is_table: true` in the task, or split additional tables into separate extraction tasks.
- Cross-check downstream storage tasks; most v2 writers expect a single table payload and will ignore extra tables even if validation succeeds.

## Local Drive Storage Requirements

**Symptom**
```
[ERROR] tasks.store_local.params.files_dir: Parameter 'files_dir' is required and must be a non-empty string
[ERROR] tasks.store_local.params.filename: Parameter 'filename' is required and must be a non-empty string
```

**Fixes**
- Point `files_dir` at an existing directory where local-drive exports should be written.
- Provide a filename template (for example `{supplier_name}.pdf`) so each processed document is uniquely named.
- Confirm the service account can write to the directory; the validator checks only for configuration shape, not permissions.

## Nested Storage Overrides

**Symptom**
```
[WARNING] tasks.store_json.params.storage.extra: storage overrides do not support key 'extra'; allowed keys are data_dir, filename.
```
```
[ERROR] tasks.store_json.params.storage: storage overrides must be provided as a mapping
```

**Fixes**
- When using `storage:` overrides, keep only the supported keys (`data_dir` and `filename`). Remove or rename any other entries.
- Define overrides as a mapping, e.g. `storage: { data_dir: ./alt-output, filename: {id}.json }`.
- If overrides are unnecessary, drop the `storage` block entirely and keep the legacy top-level `data_dir` and `filename` parameters.

## Rules Task Configuration Errors

**Symptom**
```
[ERROR] tasks.update_reference.params.csv_match.type: csv_match.type must be 'column_equals_all'
[ERROR] tasks.update_reference.params.csv_match.clauses: csv_match.clauses must define between 1 and 5 entries
[ERROR] tasks.update_reference.params.write_value: Parameter 'write_value' must be a string when provided
[ERROR] tasks.update_reference.params.backup: Parameter 'backup' must be a boolean when provided
[ERROR] tasks.update_reference.params.task_slug: Parameter 'task_slug' must be a string when provided
```

**Fixes**
- Confirm `tasks.<name>.module` points at `standard_step.rules.update_reference` (or a compatible custom implementation).
- Provide required strings:
  - `reference_file`: path to the CSV file being updated.
  - `update_field`: the column that will be rewritten.
- Ensure `csv_match` is a mapping with:
  - `type: column_equals_all`.
  - `clauses`: list containing 1-5 clause mappings.
    - Each clause must define `column` (CSV column) and `from_context` (context key); optional `number` must be `true` or `false`.
- When the validator flags a specific clause index (e.g., `clauses[2].column`), edit that entry directly in the YAML to supply the missing value or correct the type.
- Optional parameters must have correct types when provided:
  - `write_value`: string value to write to matched rows (optional, defaults to "Updated").
  - `backup`: boolean flag to create .backup files (optional, defaults to true).
  - `task_slug`: string identifier for status tracking (optional, defaults to "update_csv_reference").

## Housekeeping Task Configuration Errors

**Symptom**
```
[ERROR] tasks.cleanup_task.params.processing_dir: CleanupTask processing_dir must be a non-empty string when provided
```

**Fixes**
- Confirm `tasks.<name>.module` points at `standard_step.housekeeping.cleanup_task` (or a compatible custom implementation).
- The `processing_dir` parameter is optional but when provided must be:
  - A non-empty string value.
  - A valid directory path where status files are written.
- If not provided, the task defaults to using `'processing'` as the directory name.
- Ensure the directory exists and the service account has read/write permissions.

## Web Server Configuration Errors

**Symptoms**
```
[ERROR] web.host: Web host must be a non-empty string
[ERROR] web.port: Web port must be an integer between 1 and 65535
```

**Fixes**
- **Empty or missing host**: Set `web.host` to a valid hostname or IP address:
  - `host: "127.0.0.1"` for localhost access only
  - `host: "0.0.0.0"` to accept connections from any interface
  - `host: "localhost"` for local development
- **Invalid port number**: Set `web.port` to a valid port number between 1 and 65535:
  - `port: 8000` for development (default)
  - `port: 80` for HTTP (requires admin privileges on Windows)
  - `port: 443` for HTTPS (requires admin privileges on Windows)
  - Avoid ports below 1024 unless running with administrator privileges

## Watch Folder Configuration Errors

**Symptoms**
```
[ERROR] watch_folder.validate_pdf_header: PDF header validation must be a boolean value
[ERROR] watch_folder.processing_dir: Processing directory must be a non-empty string
```

**Fixes**
- **Invalid PDF validation setting**: Set `watch_folder.validate_pdf_header` to a boolean value:
  - `validate_pdf_header: true` to enable PDF header validation (recommended)
  - `validate_pdf_header: false` to disable validation (use with caution)
  - Remove quotes around boolean values (not `"true"` but `true`)
- **Empty or missing processing directory**: Set `watch_folder.processing_dir` to a valid directory name:
  - `processing_dir: "processing"` (default)
  - `processing_dir: "temp_processing"` for custom directory
  - Ensure the directory name is not empty or just whitespace

## Enhanced Import Validation Errors

**Symptoms** (when using `--import-checks` flag)
```
[ERROR] tasks.my_task.module: Module 'nonexistent.module' not found
[ERROR] tasks.my_task.class: Class 'NonExistentClass' not found in module 'standard_step.extraction.extract_pdf'
[ERROR] tasks.my_task.class: 'join' is not a callable class in module 'os.path'
```

**Fixes**
- **Module not found**: 
  - Verify the module name spelling: `module: standard_step.extraction.extract_pdf`
  - Ensure the module is installed or available in the Python path
  - Check that the module file exists in the expected location
  - For custom modules, ensure they are properly installed or in PYTHONPATH
- **Class not found in module**:
  - Verify the class name spelling: `class: ExtractPdfTask`
  - Check that the class exists in the specified module
  - Ensure the class hasn't been renamed or moved to a different module
- **Attribute is not a callable class**:
  - Ensure you're referencing a class, not a function or variable
  - Example: `os.path.join` is a function, not a class
  - Use actual task classes like `ExtractPdfTask`, not utility functions

## Token Or Dependency Issues

**Symptoms**
```
[ERROR] pipeline[1]: Storage task 'store_json' uses extracted data tokens but no extraction task runs earlier.
[WARNING] pipeline[2]: Storage task 'store_json_v2' expects extraction metadata but no metadata-producing extraction task runs earlier.
[WARNING] tasks.store_json.params.filename: Filename token '{line_items}' in storage task 'store_json' references non-scalar extraction field 'line_items'. Use a scalar field or update the template.
[ERROR] tasks.store_json.params.filename: Unknown template token 'supplier_code'. Add an extraction field or update the template.
```

**Fixes**
- Ensure at least one extraction task runs before any storage or archive steps, so tokens resolve correctly.
- Schedule a metadata-producing extraction (for example `extract_document_data_v2`) ahead of v2 storage tasks that expect enriched metadata.
- Insert a context initializer task (for example `standard_step.context.generate_ids`) before referencing `{nanoid}` or other context-scoped tokens.
- Expose table columns that need to appear in filenames as scalar extraction fields, or adjust the filename template to avoid table tokens.
- Create the missing extraction field (preferably scalar) or remove the unknown placeholder if the value is not needed.

## Still Stuck?

Run the validator in verbose mode to see detailed logging:
```
config-check validate --config .\config.yaml --verbose
```

For comprehensive validation including import checks:
```
config-check validate --config .\config.yaml --import-checks --verbose
```

Get machine-readable output for automated troubleshooting:
```
config-check validate --config .\config.yaml --format json
```

If the failure persists, attach the JSON output and relevant configuration snippet when contacting the engineering team. Include whether you used the `--import-checks` flag, as this affects which validation errors are reported.
