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

## Rules Task Validation Errors

### CSV File Issues

**Symptoms**
```
[ERROR] tasks.update_reference.params.reference_file: Reference CSV file 'suppliers.csv' not found
[ERROR] tasks.update_reference.params.reference_file: Cannot read CSV file 'suppliers.csv': [Errno 13] Permission denied
[ERROR] tasks.update_reference.params.reference_file: Reference CSV file 'suppliers.csv' is empty
[ERROR] tasks.update_reference.params.reference_file: Reference CSV file 'suppliers.csv' is empty or has no columns
```

**Fixes**
- **File not found (`file-not-found`)**:
  - Verify the CSV file path is correct: `reference_file: "reference_file/suppliers.csv"`
  - Ensure the file exists at the specified location
  - Use absolute paths for testing: `reference_file: "C:/full/path/to/suppliers.csv"`
  - Check working directory with `--base-dir` flag if using relative paths
- **Cannot read CSV (`rules-csv-not-readable`)**:
  - Check file permissions: ensure the file is readable by the current user
  - Close the file in Excel or other applications that might have it locked
  - Verify the file is not corrupted by opening it manually
  - Ensure the file is in valid CSV format
- **Empty CSV file (`rules-csv-empty`)**:
  - Add data to the CSV file or use a different reference file
  - Ensure the CSV contains at least header rows with column names
- **Missing headers (`rules-csv-missing-headers`)**:
  - Add proper column headers to the first row of the CSV file
  - Example: `supplier_name,invoice_number,total_amount,status`

### Column Reference Issues

**Symptoms**
```
[ERROR] tasks.update_reference.params.update_field: Update field 'Status' not found in CSV columns: supplier_name, invoice_number, status
[ERROR] tasks.update_reference.params.csv_match.clauses[0].column: Clause column 'Supplier_Name' not found in CSV columns: supplier_name, invoice_number, status
```

**Fixes**
- **Column not found (`rules-column-not-found`)**:
  - Check exact column names in CSV file (case-sensitive)
  - Fix case mismatches: `Status` → `status`, `Supplier_Name` → `supplier_name`
  - Verify column names don't have extra spaces or special characters
  - Add missing columns to CSV file if needed
  - Use `Get-Content "file.csv" | Select-Object -First 1` to view actual headers

### Clause Configuration Issues

**Symptoms**
```
[ERROR] tasks.update_reference.params.csv_match.clauses[1]: Duplicate clause: column='supplier_name', from_context='supplier_name'
[WARNING] tasks.update_reference.params.csv_match.clauses: Multiple clauses reference column 'supplier_name' (indices: [0, 2]). This may create impossible AND conditions.
[INFO] tasks.update_reference.params.csv_match.clauses: Multiple clauses use context 'supplier_name' (indices: [0, 3]). This might be intentional but worth noting.
```

**Fixes**
- **Duplicate clauses (`rules-duplicate-clause`)**:
  - Remove exact duplicate clauses with identical column and from_context values
  - Make clauses unique by using different columns or contexts
  - Check for copy-paste errors in configuration
- **Impossible conditions (`rules-impossible-condition`)**:
  - Review business logic: multiple clauses on same column create AND conditions
  - Example: `supplier_name = "A" AND supplier_name = "B"` is impossible
  - Use different columns for different conditions
  - Consider if OR logic is needed (may require separate rules tasks)
- **Context reuse (`rules-context-reuse`)**:
  - This is informational - multiple clauses using same context may be intentional
  - Review if this matches your business requirements
  - Consider using different context values if clauses should be independent

### Context Path Issues

**Symptoms**
```
[ERROR] tasks.update_reference.params.csv_match.clauses[0].from_context: Invalid dotted path syntax: 'supplier..name'
[WARNING] tasks.update_reference.params.csv_match.clauses[1].from_context: Deprecated 'data.' prefix in context path: 'data.supplier_name'. Use bare field name 'supplier_name' instead.
[WARNING] tasks.update_reference.params.csv_match.clauses[2].from_context: Field 'nonexistent_field' not found in extraction fields
```

**Fixes**
- **Invalid path syntax (`rules-context-path-invalid`)**:
  - Fix malformed dotted notation: `supplier..name` → `supplier_name`
  - Remove leading/trailing dots: `.supplier_name` → `supplier_name`
  - Use proper dotted notation: `invoice.total_amount` for nested fields
- **Deprecated data prefix (`rules-deprecated-data-prefix`)**:
  - Remove 'data.' prefix from context paths
  - Change: `data.supplier_name` → `supplier_name`
  - Modern extraction tasks don't use the data. prefix
- **Field not found (`rules-field-not-found`)**:
  - Ensure the field exists in your extraction task configuration
  - Verify field names match between extraction and rules tasks
  - Add missing fields to extraction task if needed
  - Use `--check-files` flag for comprehensive field validation

### Semantic Validation Issues

**Symptoms**
```
[WARNING] tasks.update_reference.params.csv_match.clauses[0]: Column 'amount' appears to be numeric but clause forces string comparison. Consider removing 'number: false' or verify the column type.
[INFO] tasks.update_reference.params.csv_match.clauses[1]: Field reference 'unlikely_field_name' doesn't match common extraction patterns. Verify this field exists in your extraction configuration.
```

**Fixes**
- **Type mismatch (`rules-semantic-type-mismatch`)**:
  - Use correct type flag for numeric columns: `number: true`
  - For text columns, use `number: false` or omit (default is false)
  - Verify CSV column actually contains the expected data type
  - Example: For amount columns, use `number: true` for numeric comparison
- **Unrealistic field reference (`rules-unrealistic-field-reference`)**:
  - This is informational - verify the field name exists in extraction configuration
  - Check field names follow your extraction naming conventions
  - May be intentional for custom fields, but worth double-checking

### Runtime File Validation Issues (--check-files flag)

**Symptoms**
```
[ERROR] tasks.update_reference.params.reference_file: Reference file does not exist: C:/path/to/suppliers.csv
[ERROR] tasks.update_reference.params.reference_file: Reference file is not readable (permission denied): C:/path/to/suppliers.csv
[ERROR] tasks.update_reference.params.reference_file: Reference path is not a file: C:/path/to/directory
```

**Fixes**
- **File not found (`file-not-found`)**:
  - Ensure file exists at the specified path
  - Check file path spelling and location
  - Verify working directory is correct
- **File not readable (`file-not-readable`)**:
  - Check file permissions for the current user
  - Ensure file is not locked by another application
  - Verify file system permissions allow read access
- **Path is not a file (`file-not-file`)**:
  - Ensure path points to a file, not a directory
  - Check for typos in file path that might point to directory instead

### Pandas Dependency Issues

**Symptoms**
```
[ERROR] tasks.update_reference.params.reference_file: pandas is required for CSV validation but is not available
```

**Fixes**
- **Missing pandas (`rules-csv-pandas-missing`)**:
  - Install pandas: `C:\Python313\python.exe -m pip install pandas`
  - Verify pandas is available in the current Python environment
  - Check that the correct Python environment is being used

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

For full validation including file system checks:
```
config-check validate --config .\config.yaml --check-files --verbose
```

For complete validation with all features:
```
config-check validate --config .\config.yaml --import-checks --check-files --verbose
```

Get machine-readable output for automated troubleshooting:
```
config-check validate --config .\config.yaml --format json
config-check validate --config .\config.yaml --check-files --format json
```

If the failure persists, attach the JSON output and relevant configuration snippet when contacting the engineering team. Include whether you used the `--import-checks` and `--check-files` flags, as these affect which validation errors are reported.
