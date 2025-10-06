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

### Advanced Troubleshooting
For detailed troubleshooting of path validation, parameter validation, and pipeline dependency issues, see [`docs/config_check_troubleshooting.md`](../../docs/config_check_troubleshooting.md).

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

