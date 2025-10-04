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

## Sample Configurations

Two ready-to-run sample files live under `tools/config_check/examples/`:

- `valid_config.yaml` - Passes all validators and demonstrates required/optional sections.
- `invalid_missing_paths.yaml` - Shows typical path and dependency failures for smoke testing.

Use them as templates for new environments or as fixtures when extending the validator.

## Troubleshooting

Common failure modes and their remedies (missing directories, import errors, malformed YAML, token mismatches, etc.) are documented in [`docs/config_check_troubleshooting.md`](../../docs/config_check_troubleshooting.md).

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

