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

## Rules Task Configuration Errors

**Symptom**
```
[ERROR] tasks.update_reference.params.csv_match.type: csv_match.type must be 'column_equals_all'
[ERROR] tasks.update_reference.params.csv_match.clauses: csv_match.clauses must define between 1 and 5 entries
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

## Token Or Dependency Issues

**Symptom**
```
[ERROR] pipeline[1]: Storage task 'store_json' uses extracted data tokens but no extraction task runs earlier.
```

**Fixes**
- Ensure at least one extraction task runs before any storage/archive step.
- Add missing field definitions under the extraction task (`tasks.extract_metadata.params.fields`).
- Insert context tasks (e.g., `standard_step.context.*`) before using `{nanoid}` or other context tokens.

## Still Stuck?

Run the validator in verbose mode to see detailed logging:
```
config-check validate --config .\config.yaml --verbose
```

If the failure persists, attach the JSON output and relevant configuration snippet when contacting the engineering team.
