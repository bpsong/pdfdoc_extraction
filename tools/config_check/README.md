# Config Check CLI Tool

A Windows-friendly command-line utility that validates configuration YAML files for the PDF document processing platform. The validator runs the same structural, path, parameter, and dependency checks used by the main service so administrators can catch mistakes before jobs execute.

## Installation

1. Ensure Python 3.10+ is available (the project tooling uses `C:\Python313\python.exe` by default).
2. Install the tool and its dependencies:
   ```powershell
   C:\Python313\python.exe -m pip install -e .
   ```
   The editable install registers a `config-check` console script and makes the `tools.config_check` package importable.

## Quick Start

Validate a configuration using the exact paths you expect to deploy:

```powershell
# Validate default ./config.yaml
config-check validate

# Validate an explicit file and show JSON output
config-check validate --config .\config\production.yaml --format json

# Run with strict mode and a custom base directory for relative paths
config-check validate --config ..\configs\staging.yaml --base-dir ..\configs --strict

# Perform import checks to ensure task modules/classes resolve
config-check validate --config .\config\tasks.yaml --import-checks

# Print the JSON schema describing the configuration contract
config-check schema --format json
```

All commands are also available by invoking the module directly (`C:\Python313\python.exe -m tools.config_check ...`).

## Output Formats

- **text** (default) - Human readable groups of errors, warnings, and info messages.
- **json** - Machine readable payload that contains finding metadata, suggestions, and the computed exit code.

Exit codes mirror the CLI requirements: `0` (valid), `1` (errors), `2` (warnings only), `64` (usage problems such as missing files or bad flags).

## Validation Coverage Highlights

- Schema checks backed by Pydantic ensure required sections, types, and strict-mode enforcement.
- Parameter validation covers extraction, storage, archiver, context, and rules (UpdateReference) tasks, including csv_match clause bounds (1-5) and required column/from_context fields.
- Pipeline analysis enforces extraction-before-storage, context-before-{nanoid}, and housekeeping ordering rules.
- **New**: Enhanced schema validation for web server and watch folder configuration fields.
- **New**: Import validation to verify task modules and classes are importable.
- **New**: Comprehensive rules task validation for CSV file processing and field references.
- **New**: Runtime file validation mode with `--check-files` flag for file system checks.

## Validated Configuration Fields

### Web Configuration
The validator now checks these web server configuration fields:

- `web.host`: Web server host address (default: "127.0.0.1")
  - Must be a non-empty string
  - Example: `host: "0.0.0.0"` for all interfaces
- `web.port`: Web server port number (default: 8000)
  - Must be an integer between 1 and 65535
  - Example: `port: 8080`

### Watch Folder Configuration
Enhanced validation for watch folder settings:

- `watch_folder.validate_pdf_header`: Enable PDF header validation (default: true)
  - Must be a boolean value
  - Example: `validate_pdf_header: false` to disable validation
- `watch_folder.processing_dir`: Temporary processing directory (default: "processing")
  - Must be a non-empty string representing a directory path
  - Example: `processing_dir: "temp_processing"`

### Configuration Example
```yaml
web:
  host: "127.0.0.1"
  port: 8000
  upload_dir: "web_upload"
  secret_key: "your-secret-key"

watch_folder:
  dir: "watch_folder"
  recursive: false
  validate_pdf_header: true
  processing_dir: "processing"
```

## Import Validation

Use the `--import-checks` flag to verify that task modules and classes can be imported:

```powershell
config-check validate --import-checks config.yaml
```

This validates:
- **Module Resolution**: Task module names are importable Python modules
- **Class Existence**: Specified class names exist within the modules
- **Class Validation**: Specified attributes are actually callable classes

### Import Validation Examples

```powershell
# Basic validation without import checks
config-check validate config.yaml

# Full validation including import verification
config-check validate --import-checks config.yaml

# Import validation with JSON output for automation
config-check validate --import-checks --format json config.yaml
```

### Import Error Types
- `task-import-module-not-found`: Module not found in Python path
- `task-import-module-syntax-error`: Module contains syntax errors
- `task-import-class-not-found`: Class not found in module
- `task-import-not-callable`: Specified attribute is not a callable class

## Rules Task Validation

The config-check tool provides comprehensive validation for rules tasks (update_reference.py) that process CSV files and apply business logic. This validation helps catch configuration errors before runtime.

### Rules Task Validation Features

#### CSV Structure Validation
Validates that reference CSV files can be opened and parsed:

```powershell
# Basic validation (structural checks only)
config-check validate config.yaml

# Full validation including CSV file checks
config-check validate --check-files config.yaml
```

**Validation checks:**
- **File Accessibility**: Verifies CSV files exist and are readable
- **CSV Parsing**: Ensures files can be parsed as valid CSV format
- **Header Detection**: Validates that CSV files contain proper column headers
- **Empty File Detection**: Warns about empty or malformed CSV files

#### Column Existence Validation
Verifies that all referenced columns exist in the target CSV file:

```yaml
tasks:
  update_supplier_status:
    module: "standard_step.rules.update_reference"
    class: "UpdateReference"
    params:
      reference_file: "reference_file/suppliers.csv"
      update_field: "status"  # Must exist in CSV
      csv_match:
        type: "column_equals_all"
        clauses:
          - column: "supplier_name"    # Must exist in CSV
            from_context: "supplier_name"
          - column: "invoice_number"   # Must exist in CSV
            from_context: "invoice_number"
```

#### Clause Uniqueness Detection
Identifies duplicate and potentially conflicting clause definitions:

**Error Conditions:**
- **Duplicate Clauses**: Identical column + context combinations
- **Column Conflicts**: Multiple clauses on the same CSV column (may create impossible AND conditions)
- **Context Reuse**: Multiple clauses using the same context value (informational)

**Example problematic configuration:**
```yaml
csv_match:
  clauses:
    - column: "supplier_name"
      from_context: "supplier_name"
    - column: "supplier_name"      # WARNING: Same column
      from_context: "alt_supplier"
    - column: "supplier_name"      # ERROR: Exact duplicate
      from_context: "supplier_name"
```

#### Context Path Validation
Validates `from_context` paths follow proper dotted notation:

**Valid context paths:**
```yaml
clauses:
  - column: "supplier_name"
    from_context: "supplier_name"        # Simple field reference
  - column: "total_amount"
    from_context: "invoice.total_amount" # Nested field reference
```

**Invalid context paths:**
```yaml
clauses:
  - column: "supplier_name"
    from_context: "data.supplier_name"   # DEPRECATED: data. prefix
  - column: "amount"
    from_context: "invalid..path"        # ERROR: Invalid syntax
```

#### Deprecation Warnings
Detects deprecated "data." prefixes in context paths:

```yaml
# Deprecated (generates warning)
from_context: "data.supplier_name"

# Recommended
from_context: "supplier_name"
```

#### Semantic Validation
Identifies potentially problematic configurations:

**Type Mismatch Detection:**
```yaml
# WARNING: Numeric column with string comparison
- column: "amount"           # Appears numeric
  from_context: "total_amount"
  number: false              # Forces string comparison
```

**Unrealistic Field References:**
```yaml
# INFO: Field doesn't match common patterns
- column: "supplier_name"
  from_context: "unlikely_field_name"  # May not exist in extraction
```

### Rules Task Error Codes

#### CSV Validation Errors
- `rules-csv-not-readable`: CSV file cannot be opened or parsed
- `rules-csv-empty`: CSV file is empty
- `rules-csv-missing-headers`: CSV file has no column headers
- `rules-csv-pandas-missing`: pandas library required but not available
- `file-not-found`: Reference CSV file does not exist

#### Column Validation Errors
- `rules-column-not-found`: Referenced column does not exist in CSV file

#### Clause Validation Issues
- `rules-duplicate-clause`: Identical clause definition found (ERROR)
- `rules-impossible-condition`: Multiple clauses on same column may create impossible condition (WARNING)
- `rules-context-reuse`: Multiple clauses use same context value (INFO)

#### Context Path Issues
- `rules-context-path-invalid`: Invalid context path syntax (ERROR)
- `rules-deprecated-data-prefix`: Deprecated 'data.' prefix in context path (WARNING)
- `rules-field-not-found`: Referenced field not found in extraction configuration (WARNING)
- `rules-context-path-issue`: General context path issue (WARNING)

#### Semantic Validation Issues
- `rules-semantic-type-mismatch`: Type mismatch in field comparison (WARNING)
- `rules-unrealistic-field-reference`: Field reference doesn't match common patterns (INFO)

### Rules Task Validation Examples

#### Valid Rules Task Configuration
```yaml
tasks:
  update_invoice_status:
    module: "standard_step.rules.update_reference"
    class: "UpdateReference"
    params:
      reference_file: "reference_file/invoices.csv"
      update_field: "processing_status"
      csv_match:
        type: "column_equals_all"
        clauses:
          - column: "supplier_name"
            from_context: "supplier_name"
          - column: "invoice_number"
            from_context: "invoice_number"
          - column: "total_amount"
            from_context: "total_amount"
            number: true
```

#### Common Rules Task Errors

**Missing CSV File:**
```yaml
# ERROR: file-not-found
reference_file: "missing_file.csv"
```

**Invalid Column Reference:**
```yaml
# ERROR: rules-column-not-found
update_field: "nonexistent_column"
```

**Duplicate Clauses:**
```yaml
# ERROR: rules-duplicate-clause
clauses:
  - column: "supplier_name"
    from_context: "supplier_name"
  - column: "supplier_name"    # Exact duplicate
    from_context: "supplier_name"
```

**Deprecated Context Path:**
```yaml
# WARNING: rules-deprecated-data-prefix
clauses:
  - column: "supplier_name"
    from_context: "data.supplier_name"  # Use "supplier_name" instead
```

## Runtime File Validation

The `--check-files` flag enables runtime file validation that performs file system checks beyond structural validation.

### Runtime File Validation Features

#### File Existence Validation
Verifies that all referenced files exist and are accessible:

```powershell
# Enable runtime file validation
config-check validate --check-files config.yaml
```

**Validation checks:**
- **File Existence**: All referenced files exist on the file system
- **File Accessibility**: Files can be read by the current user
- **Directory Permissions**: Configured directories are accessible
- **CSV File Structure**: CSV files can be parsed and contain expected headers

#### When to Use Runtime File Validation

**Use `--check-files` when:**
- Deploying to a new environment
- Validating file paths and permissions
- Troubleshooting file access issues
- Performing comprehensive pre-deployment checks

**Skip `--check-files` when:**
- Performing quick structural validation
- Files may not exist yet (development/testing)
- Running in CI/CD where files aren't available
- Validating configuration templates

### Runtime File Validation Examples

```powershell
# Basic structural validation (fast)
config-check validate config.yaml

# Full validation including file system checks (slower)
config-check validate --check-files config.yaml

# Runtime validation with JSON output
config-check validate --check-files --format json config.yaml
```

### Runtime File Error Codes
- `file-not-found`: Referenced file does not exist
- `file-not-file`: Path exists but is not a file
- `file-not-readable`: File exists but cannot be read (permission denied)
- `file-access-error`: General file access error

## Sample Configurations

Two ready-to-run sample files live under `tools/config_check/examples/`:

- `valid_config.yaml` - Passes all validators and demonstrates required/optional sections.
- `invalid_missing_paths.yaml` - Shows typical path and dependency failures for smoke testing.

Use them as templates for new environments or as fixtures when extending the validator.

## Troubleshooting

### Common Validation Errors

#### Schema Validation Errors
- **`web-host-invalid`**: Web host must be a non-empty string
  - Fix: Ensure `web.host` is set to a valid hostname or IP address
  - Example: `host: "127.0.0.1"` or `host: "localhost"`

- **`web-port-invalid`**: Web port must be an integer between 1 and 65535
  - Fix: Set `web.port` to a valid port number
  - Example: `port: 8000` (avoid ports below 1024 without admin privileges)

- **`watch-folder-pdf-validation-invalid`**: PDF header validation must be a boolean
  - Fix: Set `watch_folder.validate_pdf_header` to `true` or `false`
  - Example: `validate_pdf_header: true`

- **`watch-folder-processing-dir-invalid`**: Processing directory must be a non-empty string
  - Fix: Provide a valid directory path for `watch_folder.processing_dir`
  - Example: `processing_dir: "processing"`

#### Import Validation Errors
- **`task-import-module-not-found`**: Module not found in Python path
  - Fix: Ensure the module is installed or the path is correct
  - Check: Verify module name spelling and Python path configuration

- **`task-import-class-not-found`**: Class not found in module
  - Fix: Verify the class name exists in the specified module
  - Check: Ensure class name spelling matches the actual class definition

- **`task-import-not-callable`**: Specified attribute is not a callable class
  - Fix: Ensure the specified attribute is a class, not a variable or function
  - Check: Verify the attribute can be instantiated as a class

#### Rules Task Validation Errors

##### CSV File Issues
- **`file-not-found`**: Reference CSV file does not exist
  - Fix: Ensure the CSV file path is correct and the file exists
  - Check: Verify file path spelling and location relative to config file
  - Example: `reference_file: "reference_file/suppliers.csv"`

- **`rules-csv-not-readable`**: CSV file cannot be opened or parsed
  - Fix: Ensure the file is a valid CSV format and has proper permissions
  - Check: Open the file manually to verify it's not corrupted
  - Common causes: File locked by another process, invalid CSV format

- **`rules-csv-empty`**: CSV file is empty or has no data
  - Fix: Add data to the CSV file or use a different reference file
  - Check: Ensure the CSV file contains at least header rows

- **`rules-csv-missing-headers`**: CSV file has no column headers
  - Fix: Add proper column headers to the first row of the CSV file
  - Example: First row should contain column names like "supplier_name,invoice_number,status"

##### Column Reference Issues
- **`rules-column-not-found`**: Referenced column does not exist in CSV
  - Fix: Update column names to match those in the CSV file
  - Check: Verify column names in CSV headers match configuration exactly
  - Common issue: Case sensitivity or extra spaces in column names

##### Clause Configuration Issues
- **`rules-duplicate-clause`**: Identical clause definitions found
  - Fix: Remove duplicate clauses or modify them to be unique
  - Check: Look for clauses with identical column and from_context values
  - Example: Two clauses both using `column: "supplier_name", from_context: "supplier_name"`

- **`rules-impossible-condition`**: Multiple clauses on same column may create impossible conditions
  - Fix: Review business logic - multiple conditions on same column create AND logic
  - Check: Ensure multiple clauses on same column make logical sense
  - Example: `supplier_name = "A" AND supplier_name = "B"` is impossible

##### Context Path Issues
- **`rules-context-path-invalid`**: Invalid context path syntax
  - Fix: Use proper dotted notation for context paths
  - Valid: `supplier_name`, `invoice.total_amount`
  - Invalid: `supplier..name`, `.supplier_name`

- **`rules-deprecated-data-prefix`**: Deprecated 'data.' prefix in context path
  - Fix: Remove 'data.' prefix from context paths
  - Change: `data.supplier_name` → `supplier_name`
  - Reason: Modern extraction tasks don't use the data. prefix

- **`rules-field-not-found`**: Referenced field not found in extraction configuration
  - Fix: Ensure the field exists in your extraction task configuration
  - Check: Verify field names match between extraction and rules tasks
  - Use: `--check-files` flag for comprehensive field validation

##### Semantic Validation Issues
- **`rules-semantic-type-mismatch`**: Type mismatch in field comparison
  - Fix: Ensure number flag matches the expected data type
  - Example: For numeric columns, use `number: true`
  - Check: Verify CSV column contains numeric vs. text data

- **`rules-unrealistic-field-reference`**: Field reference doesn't match common patterns
  - Fix: Verify the field name exists in your extraction configuration
  - Check: Ensure field names follow your extraction naming conventions
  - Note: This is informational - may be intentional for custom fields

### Advanced Troubleshooting
For detailed troubleshooting of all validation issues including rules task validation, runtime file validation, path validation, parameter validation, and pipeline dependency issues, see [`docs/config_check_troubleshooting.md`](../../docs/config_check_troubleshooting.md).

## Development

Run the focused test suite before committing changes:

```powershell
C:\Python313\python.exe -m pytest test\tools\config_check -q
```

A tagged performance test verifies the validator completes within 300 ms on representative configs:

```powershell
C:\Python313\python.exe -m pytest test\tools\config_check -k performance -q
```

When packaging updates are made, `pyproject.toml` drives builds via setuptools. The `config-check` entry point is defined there so CI/CD pipelines can install and execute the tool with `pip install .`.

