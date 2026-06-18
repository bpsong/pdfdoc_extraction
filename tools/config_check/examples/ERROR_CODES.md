# Config-Check Error Codes Reference

This document provides a comprehensive reference of all validation error codes used by the config-check tool, organized by validation category.

## Schema Validation Error Codes

### Web Configuration Errors
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `web-host-invalid` | Error | Web host must be a non-empty string | Set `web.host` to a valid hostname or IP address |
| `web-port-invalid` | Error | Web port must be an integer between 1 and 65535 | Set `web.port` to a valid port number (e.g., 8000) |

### Watch Folder Configuration Errors
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `watch-folder-pdf-validation-invalid` | Error | PDF header validation must be a boolean | Set `watch_folder.validate_pdf_header` to `true` or `false` |
| `watch-folder-processing-dir-invalid` | Error | Processing directory must be a non-empty string | Provide a valid directory path for `watch_folder.processing_dir` |

## Import Validation Error Codes

| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `task-import-module-not-found` | Error | Module not found in Python path | Ensure module is installed and path is correct |
| `task-import-module-syntax-error` | Error | Module contains syntax errors | Fix syntax errors in the specified module |
| `task-import-class-not-found` | Error | Class not found in module | Verify class name exists in the specified module |
| `task-import-not-callable` | Error | Specified attribute is not a callable class | Ensure attribute is a class, not a variable or function |

## Pipeline Business Rule Error Codes

### Pipeline Structure And Dependencies
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `tasks-not-mapping` | Error | `tasks` section is not a mapping | Define `tasks` as a mapping keyed by task id |
| `pipeline-not-list` | Error | `pipeline` section is not a list | Define `pipeline` as a list of task identifiers |
| `pipeline-entry-invalid` | Error | Pipeline entry is not a non-empty task id string | Replace the entry with a valid task id |
| `pipeline-missing-task` | Error | Pipeline references a task id not defined under `tasks` | Add the task definition or remove the pipeline entry |
| `pipeline-duplicate-task` | Warning | Same task id appears more than once in `pipeline` | Remove the duplicate unless repeated execution is intentional |
| `pipeline-missing-extraction` | Error | Pipeline has no extraction task | Add an extraction task before downstream metadata work |
| `pipeline-storage-before-extraction` | Error | Storage or rules task uses extracted tokens before extraction runs | Move extraction earlier or remove extracted-field tokens |
| `pipeline-storage-metadata-missing` | Warning | V2 storage task expects extraction metadata but none is produced earlier | Move metadata-producing extraction earlier or define extraction `fields` |
| `pipeline-nanoid-before-context` | Error | Task references `{nanoid}` before a context initializer task | Add/move `AssignNanoidTask` before the task using `{nanoid}` |
| `pipeline-unknown-token` | Error | Template token does not match a known extraction field or context token | Add the extraction field or update the template |
| `pipeline-storage-filename-non-scalar` | Warning | Storage filename token references a table/non-scalar field | Use a scalar extraction field in filenames |

### Pipeline Cardinality And Ordering
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `pipeline-multiple-extract-tasks` | Error | More than one extract task appears in the active pipeline | Keep one active extraction task |
| `pipeline-multiple-split-tasks` | Error | More than one split task appears in the active pipeline | Keep one active split task |
| `pipeline-multiple-review-gate-tasks` | Error | More than one review-gate task appears in the active pipeline | Keep one active review-gate task |
| `pipeline-split-after-extract` | Error | Split task is configured after extraction | Move split before extraction |
| `pipeline-review-before-extract` | Error | Review gate is configured before extraction | Move review gate after extraction |
| `pipeline-duplicate-task-type` | Warning | Same non-singleton module/class pair appears multiple times | Confirm the duplicate is intentional or remove it |

### Task Approval
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `pipeline-task-not-approved` | Error | Active pipeline task uses an unapproved module/class pair | Use an approved built-in task or add an exact `custom_steps.registry` entry |
| `custom-task-registry-not-mapping` | Error | `custom_steps.registry` is not a mapping | Define registry entries as a mapping keyed by approval name |
| `custom-task-registry-entry-invalid` | Error | Custom registry entry is not a mapping | Define each entry with `module` and `class` |
| `custom-task-registry-missing-module` | Error | Custom registry entry lacks `module` | Add a non-empty module name |
| `custom-task-registry-missing-class` | Error | Custom registry entry lacks `class` | Add a non-empty class name |
| `custom-task-registry-invalid-module` | Error | Custom registry module does not use `custom_step.` prefix | Move custom tasks under `custom_step.` or update the registry |

## Review Gate Validation Error Codes

| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `review-gate-params-not-mapping` | Error | `ReviewGateTask.params` is not a mapping | Define params as a YAML mapping |
| `review-gate-invalid-confidence-threshold` | Error | Confidence threshold is outside 0 through 1 or not numeric | Set `confidence_threshold` to a number from 0 through 1 |
| `review-gate-invalid-resume-policy` | Error | Unsupported resume policy | Use `resume_policy: next_task` or omit it |
| `review-gate-invalid-split-confidence-levels` | Error | Split review confidence levels are invalid | Use a list containing only `high`, `medium`, or `low` |
| `review-gate-schema-not-found` | Error | Referenced review schema cannot be loaded | Point `schema_file` at a configured schema file |
| `schema-load-failed` | Error | Configured schema file could not be loaded | Fix the schema path or YAML/JSON syntax |
| `schema-invalid` | Error | Schema file structure is invalid | Fix unsupported field types, enum choices, numeric constraints, object properties, or array items |

## Split Task Validation Error Codes

| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `split-params-not-mapping` | Error | `LlamaCloudSplitTask.params` is not a mapping | Define params as a YAML mapping |
| `split-missing-split-dir` | Error | Split task lacks `params.split_dir` | Add a non-empty split output directory |
| `split-missing-categories-or-configuration` | Error | Enabled split task lacks both categories and configuration id | Add `configuration_id` or `categories` |
| `split-missing-runtime-api-key` | Warning | Enabled split task lacks runtime API key and no adapter is configured | Add `api_key` or ensure an adapter is injected by tests |
| `split-invalid-allow-uncategorized` | Error | `allow_uncategorized` has an unsupported value | Use `include`, `forbid`, or `omit` |
| `split-invalid-fail-on-confidence-levels` | Error | Invalid confidence level list | Use a list containing only `high`, `medium`, or `low` |
| `split-invalid-fail-on-unknown-category` | Error | `fail_on_unknown_category` is not boolean | Set it to `true` or `false` |
| `split-invalid-allowed-categories` | Error | `allowed_categories` is not a list of non-empty strings | Provide a valid string list |
| `split-invalid-categories` | Error | `categories` is not a list of mappings with names | Provide category mappings with `name` |
| `split-final-pipeline-step` | Warning | Split task is the final pipeline step | Add downstream child-processing tasks or remove split |

## Rules Task Validation Error Codes

### CSV File Validation
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `file-not-found` | Error | Reference CSV file does not exist | Ensure CSV file path is correct and file exists |
| `rules-csv-not-readable` | Error | CSV file cannot be opened or parsed | Verify file is valid CSV format with proper permissions |
| `rules-csv-empty` | Error | CSV file is empty | Add data to CSV file or use different reference file |
| `rules-csv-missing-headers` | Error | CSV file has no column headers | Add proper column headers to first row of CSV |
| `rules-csv-pandas-missing` | Error | pandas library required but not available | Install pandas: `pip install pandas` |

### Column Reference Validation
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `rules-column-not-found` | Error | Referenced column does not exist in CSV file | Update column names to match CSV headers exactly |

### Clause Validation
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `rules-duplicate-clause` | Error | Identical clause definition found | Remove duplicate clauses or modify to be unique |
| `rules-impossible-condition` | Warning | Multiple clauses on same column may create impossible condition | Review business logic for multiple conditions on same column |
| `rules-context-reuse` | Info | Multiple clauses use same context value | Note: might be intentional but worth reviewing |

### Context Path Validation
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `rules-context-path-invalid` | Error | Invalid context path syntax | Use proper dotted notation (e.g., `field_name` or `nested.field`) |
| `rules-deprecated-data-prefix` | Warning | Deprecated 'data.' prefix in context path | Remove 'data.' prefix (e.g., `data.field` → `field`) |
| `rules-field-not-found` | Warning | Referenced field not found in extraction configuration | Ensure field exists in extraction task configuration |
| `rules-context-path-issue` | Warning | General context path issue | Review context path for potential issues |

### Semantic Validation
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `rules-semantic-type-mismatch` | Warning | Type mismatch in field comparison | Ensure `number` flag matches expected data type |
| `rules-unrealistic-field-reference` | Info | Field reference doesn't match common patterns | Verify field name exists in extraction configuration |

## Runtime File Validation Error Codes

| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `file-not-found` | Error | Referenced file does not exist | Ensure file path is correct and file exists |
| `file-not-file` | Error | Path exists but is not a file | Ensure path points to a file, not a directory |
| `file-not-readable` | Error | File exists but cannot be read | Check file permissions and ensure read access |
| `file-access-error` | Error | General file access error | Review file path and permissions |

## Parameter Validation Error Codes

### Rules Task Parameters
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `param-rules-not-mapping` | Error | Rules task params must be a mapping | Define params as a dictionary with required fields |
| `param-rules-missing-reference-file` | Error | Missing reference_file parameter | Set `reference_file` to CSV file path |
| `param-rules-missing-update-field` | Error | Missing update_field parameter | Set `update_field` to column name to update |
| `param-rules-csv-match-mapping` | Error | csv_match must be a mapping | Provide csv_match as dictionary with type and clauses |
| `param-rules-csv-type` | Error | Invalid csv_match.type value | Set `csv_match.type` to 'column_equals_all' |
| `param-rules-clauses-type` | Error | csv_match.clauses must be a list | Define clauses as list of clause mappings |
| `param-rules-clauses-count` | Error | Invalid number of clauses | Provide between 1 and 5 clause definitions |
| `param-rules-clause-not-mapping` | Error | Clause must be a mapping | Ensure each clause is a dictionary |
| `param-rules-clause-column` | Error | Clause column must be non-empty string | Provide valid column name for each clause |
| `param-rules-clause-context` | Error | Clause from_context must be non-empty string | Provide valid from_context for each clause |
| `param-rules-clause-number-type` | Error | Clause number flag must be boolean | Set number to true/false or remove it |

### Split Task Parameters
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `param-split-missing-split-dir` | Error | LlamaCloud split task requires `params.split_dir` | Add a non-empty split output directory under the split task params |
| `param-split-not-mapping` | Error | Split task params are not a mapping | Define split params as a YAML mapping |
| `param-split-invalid-fail-on-confidence-levels` | Error | Invalid confidence level list | Use a list containing only `high`, `medium`, or `low` |
| `param-split-invalid-fail-on-unknown-category` | Error | `fail_on_unknown_category` is not boolean | Set it to `true` or `false` |
| `param-split-invalid-allowed-categories` | Error | `allowed_categories` is not a list of non-empty strings | Provide a valid string list |

### Extraction Task Parameters
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `param-extraction-not-mapping` | Error | Extraction task params are not a mapping | Define params as a YAML mapping |
| `param-extraction-missing-api-key` | Error | Extraction task lacks `api_key` | Add a non-empty API key or deployment placeholder |
| `param-extraction-invalid-configuration-id` | Error | `configuration_id` is present but empty or not a string | Use a non-empty configuration id or omit it |
| `param-extraction-missing-fields` | Error | Extraction task lacks field definitions | Add a non-empty `fields` mapping |
| `param-extraction-multiple-tables` | Error | More than one extraction field is marked `is_table: true` | Keep one table field or split extraction design |
| `param-field-invalid` | Error | Field definition is not a mapping | Define field settings as a mapping |
| `param-field-missing-alias` | Error | Field lacks a non-empty alias | Add a non-empty `alias` |
| `param-field-invalid-type` | Error | Field type is unsupported | Use a supported type such as `str`, `float`, `Optional[str]`, or `List[Any]` |
| `param-field-istable-bool` | Error | `is_table` is not boolean | Set `is_table` to `true` or `false` |
| `param-field-missing-item-fields` | Error | Table field lacks `item_fields` | Add non-empty nested item fields |

### Storage, Context, And Housekeeping Parameters
| Code | Severity | Description | Fix |
|------|----------|-------------|-----|
| `param-storage-missing-data-dir` | Error | Storage task lacks `data_dir` | Add a non-empty data directory |
| `param-storage-missing-filename` | Error | Storage task lacks `filename` | Add a non-empty filename template |
| `param-storage-unknown-storage-key` | Warning | Nested storage override contains unsupported key | Use only `data_dir` and `filename` in `storage` overrides |
| `param-storage-storage-block-type` | Error | Nested storage override is not a mapping | Define `storage` as a mapping or remove it |
| `param-localdrive-missing-files-dir` | Error | Local-drive storage lacks `files_dir` | Add a non-empty file output directory |
| `param-localdrive-missing-filename` | Error | Local-drive storage lacks `filename` | Add a non-empty filename template |
| `param-archiver-missing-archive-dir` | Error | Archive task lacks `archive_dir` | Add a non-empty archive directory |
| `param-context-length-type` | Error | Context task `length` is not an integer | Set `length` to an integer |
| `param-context-length-bounds` | Error | Context task `length` is outside bounds | Set `length` between 5 and 21 |
| `param-housekeeping-not-mapping` | Error | Housekeeping params are not a mapping | Define params as a YAML mapping |
| `param-housekeeping-processing-dir-invalid` | Error | Cleanup `processing_dir` is empty or not a string | Use a non-empty directory string |

## Error Severity Levels

### Error (Exit Code 1)
- Configuration is invalid and will cause runtime failures
- Must be fixed before deployment
- Examples: Missing required fields, invalid syntax, file not found

### Warning (Exit Code 2)
- Configuration may cause issues or uses deprecated features
- Should be addressed but won't prevent operation
- Examples: Deprecated syntax, potential type mismatches, impossible conditions

### Info (Exit Code 0)
- Informational messages about configuration
- No action required but worth noting
- Examples: Context reuse, unrealistic field references

## Common Error Patterns

### File Path Issues
```yaml
# ERROR: file-not-found
reference_file: "missing_file.csv"

# FIX: Use correct path
reference_file: "reference_file/suppliers.csv"
```

### Column Name Mismatches
```yaml
# ERROR: rules-column-not-found
update_field: "Status"  # CSV has "status" (lowercase)

# FIX: Match exact column name
update_field: "status"
```

### Duplicate Clauses
```yaml
# ERROR: rules-duplicate-clause
clauses:
  - column: "supplier_name"
    from_context: "supplier_name"
  - column: "supplier_name"    # Exact duplicate
    from_context: "supplier_name"

# FIX: Remove duplicate or make unique
clauses:
  - column: "supplier_name"
    from_context: "supplier_name"
  - column: "invoice_number"   # Different column
    from_context: "invoice_number"
```

### Deprecated Context Paths
```yaml
# WARNING: rules-deprecated-data-prefix
from_context: "data.supplier_name"

# FIX: Remove data. prefix
from_context: "supplier_name"
```

### Type Mismatches
```yaml
# WARNING: rules-semantic-type-mismatch
- column: "amount"           # Numeric column
  from_context: "total_amount"
  number: false              # Forces string comparison

# FIX: Use appropriate type
- column: "amount"
  from_context: "total_amount"
  number: true               # Numeric comparison
```

## Using Error Codes

### Command Line Usage
```powershell
# Get detailed error information
config-check validate --config config.yaml --format json

# Filter by error severity
config-check validate --config config.yaml | findstr "ERROR"
config-check validate --config config.yaml | findstr "WARNING"
```

### JSON Output Format
```json
{
  "findings": [
    {
      "path": "tasks.update_supplier.params.reference_file",
      "message": "Reference CSV file 'missing.csv' not found",
      "code": "file-not-found",
      "severity": "error",
      "details": {
        "file_path": "missing.csv"
      }
    }
  ],
  "exit_code": 1
}
```

### Automation Integration
Use error codes in CI/CD pipelines to handle different validation outcomes:

```powershell
# PowerShell example
$result = config-check validate --config config.yaml --format json
$json = $result | ConvertFrom-Json

foreach ($finding in $json.findings) {
    if ($finding.code -eq "file-not-found") {
        Write-Host "Missing file: $($finding.details.file_path)"
    }
}

exit $json.exit_code
```
