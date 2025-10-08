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
config-check validate --format json config.yaml

# Filter by error severity
config-check validate config.yaml | findstr "ERROR"
config-check validate config.yaml | findstr "WARNING"
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
$result = config-check validate --format json config.yaml
$json = $result | ConvertFrom-Json

foreach ($finding in $json.findings) {
    if ($finding.code -eq "file-not-found") {
        Write-Host "Missing file: $($finding.details.file_path)"
    }
}

exit $json.exit_code
```