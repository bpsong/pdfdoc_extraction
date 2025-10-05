# Product Requirements Document: Config.yaml Validator CLI

1. Introduction/Overview

This PRD defines a command-line tool ("config-check") for administrators that validates the application's YAML configuration file before runtime. The tool checks schema correctness, parameter validity, path existence, task definitions, and pipeline sequencing dependencies. It reports clear errors with actionable suggestions to help users fix issues in the config quickly and safely. This tool complements, but does not run, the main application described in [tasks/prd-design-pdf-processing.md](tasks/prd-design-pdf-processing.md).

2. Goals

- Catch configuration problems early (pre-flight) before starting the main server or triggering workflows.
- Validate end-to-end integrity: YAML structure, required keys, types, allowed values, path existence, and cross-field consistency.
- Validate that tasks referenced in pipeline are defined and ordered to satisfy dependencies implied by filename patterns and data requirements.
- Provide precise, line-aware diagnostics and suggestions, suitable for CI/CD gating and local checks.

3. Target Users

- Administrators configuring and operating the PDF processing system.
- CI/CD pipelines enforcing configuration quality gates.

4. User Stories

- As an administrator, I want to run a single command that validates my config.yaml and tells me exactly what to fix so I can deploy safely.
- As an administrator, I want the tool to verify that every pipeline step exists and is correctly ordered so that the runtime pipeline does not fail mid-way.
- As an administrator, I want clear, copy-pastable suggestions for fixes so I can correct errors rapidly.
- As a CI system, I want a non-zero exit code when errors are present, so builds fail fast with actionable output.

5. Functional Requirements

1) CLI Interface
- Command name: config-check
- Syntax:
  - config-check validate --config PATH [--format text|json] [--strict] [--base-dir PATH] [--import-checks]
  - config-check schema [--format json]
- Exit codes:
  - 0: Valid (no errors; warnings allowed)
  - 1: One or more errors found
  - 2: Only warnings found (no errors)
  - 64: Usage error (bad flags, unreadable file)

2) Input
- Default config file path: ./config.yaml (overridable with --config)
- If --base-dir is provided, resolve all relative paths (e.g., *_dir, *_file) against this base; otherwise use process working directory.

3) YAML Parsing and Root Validation
- Must parse YAML safely.
- Root must be a mapping (dictionary), not a list or scalar.
- On parse errors, show file location (line/column if available) and exit with code 1.

4) Schema Validation (Structure and Types)
- Required top-level keys:
  - web (mapping) with key: upload_dir (string)
  - watch_folder (mapping) with key: dir (string)
  - tasks (mapping)
  - pipeline (list of strings)
- Optional sections: authentication, logging, secrets, etc.
- tasks.* entries must be mappings with:
  - module (string), class (string), params (mapping or empty), on_error (string in {"stop","continue"})
- pipeline must be a list of task keys defined under tasks.
- Unknown keys are allowed but flagged as warnings unless --strict is used (then unknown keys are errors).

4.1 Schema Command Output
The schema subcommand outputs a JSON Schema (draft-07) document describing the complete configuration structure, including:
- All required and optional top-level keys with their types and constraints
- Nested schema definitions for tasks, pipeline, web, watch_folder, authentication, logging sections
- Field definitions for extraction.fields with allowed types and properties
- Parameter schemas for storage and archiver tasks
- Examples and descriptions for each configuration section

5) Path Validation (Directories and Files)
- All values whose keys end with _dir must refer to existing directories.
- All values whose keys end with _file must refer to existing files.
- Paths may be relative to --base-dir or current working directory.
- The special key watch_folder.dir must exist and be a directory.
- No directories or files are created by this tool; it only validates.

6) Task Existence and Importability
- For every name in pipeline, verify that tasks.<name> exists; otherwise error.
- If --import-checks is supplied:
  - Attempt import of the configured module and class to ensure they are resolvable on sys.path.
  - Report import errors with module/class and suggested fixes (e.g., check PYTHONPATH, typos).

7) Pipeline Dependency and Ordering Validation

Mandatory Rules:
- Pipeline must include at least one extraction task to ensure metadata is produced before downstream steps.


Task Classification Rules:
- Extraction tasks: modules starting with "standard_step.extraction." or "custom_step.extraction."
- Storage tasks: modules starting with "standard_step.storage." or "custom_step.storage."
- Context initializer tasks: modules starting with "standard_step.context." or "custom_step.context."
- Archiver tasks: modules starting with "standard_step.archiver." or "custom_step.archiver."
- Housekeeping tasks: modules starting with "standard_step.housekeeping." or "custom_step.housekeeping."
- Rules tasks: modules starting with "standard_step.rules." or "custom_step.rules."

- Extraction-before-storage rule:
  - If any storage task references extracted data fields in its params (e.g., filename pattern tokens like {supplier_name}, {invoice_amount}), then at least one extraction task must appear earlier in pipeline; otherwise error.
- Nanoid-before-use rule:
  - If any param contains token {nanoid}, then a context initializer task must appear earlier; otherwise error.
- Housekeeping-last rule:
  - A housekeeping task must exist and be the last step; if not present -> error; if present but not last -> warning with suggestion to move it to the end.
- Unknown token rule:
  - For any template token {token_name} used in params (e.g., filename), validate that token_name is available from either:
    - extraction.fields keys (normalized internal names), or
    - known context keys: id, nanoid, filename, source, original_filename, file_path.
  - If token unknown -> error, with suggestion to add extraction field or adjust the template.
- Duplicate pipeline steps:
  - Warn if a task key appears multiple times (allowed but potentially unintended).

8) Parameter-Level Validation
- on_error must be one of: stop, continue (case-insensitive; normalized internally).

Configuration Schema Details:
- tasks.*.params structure:
  - module: string (required) - Python module path (e.g., "standard_step.extraction.extract_pdf")
  - class: string (required) - Task class name (e.g., "ExtractPdfTask")
  - on_error: string (required) - Error handling strategy: "stop" or "continue"
  - params: mapping (optional) - Task-specific parameters

- For extraction.tasks.params.fields (when module starts with extraction):
  - Each field is a mapping with the following structure:
    - alias: string (required) - Human-readable field name for outputs
    - type: string (required) - Data type from: str, int, float, bool, Any, Optional[T], List[T], List[Any]
    - is_table: boolean (optional, default false) - Marks field as array-of-objects
    - item_fields: mapping (optional) - Required if is_table=true, defines sub-field structure
      - Sub-fields follow same structure as parent fields (alias, type required)

- For storage.tasks.params (when module starts with storage):
  - data_dir: string (required) - Directory path for output files
  - filename: string (required) - Filename pattern, may contain {tokens}

- For archiver.tasks.params (when module starts with archiver):
  - archive_dir: string (required) - Directory path for archived files

- For rules.tasks.params (when module starts with rules/update_reference):
  - reference_file: string (required) - CSV file path to update
  - update_field: string (required) - Column name that will be updated
  - csv_match: mapping (required)
    - type: must be 'column_equals_all'
    - clauses: list with 1-5 items; each clause requires column (string), from_context (string), and optional number (boolean)

- For context.tasks.params (when module starts with context):
  - length: integer (optional, default 10) - Length for nanoid generation (5-21)

9) Output and Reporting
- Default --format text:
  - Summary line: "Validation passed with 0 errors, N warnings" or "Validation failed with E errors, W warnings."
  - Then a sorted list of findings grouped by Severity [ERROR|WARNING|INFO].
  - Each finding includes path to the offending key (e.g., tasks.store_metadata_json.params.data_dir) and a suggested fix.
- --format json:
  - Machine-readable JSON with fields: status, errors[], warnings[], stats, exit_code.

10) Suggestions Engine
- For missing directories/files: "Create directory at '...' or update config: web.upload_dir to a valid path."
- For missing task in pipeline: "Add tasks.<name> or remove '<name>' from pipeline."
- For misordered steps: "Move 'assign_nanoid' before tasks using {nanoid} (e.g., store_metadata_json)."
- For unknown tokens: "Add extraction field '<token>' or change filename template to exclude {<token>}."

11) Performance and Footprint
- Validation of typical configs (< 500 lines) must complete under 300 ms on a modern laptop.
- No network access required; purely local analysis.

12) Documentation
- Provide README section with examples and troubleshooting.

5.1 Upcoming Validation Enhancements (vNext)

- **Module-aware extraction prerequisites**: For modules under standard_step.extraction.* (and custom equivalents), require configs to declare api_key and agent_id before runtime and emit actionable errors when they are missing or empty.
- **Single-table guardrail**: Surface a warning when more than one extraction field advertises is_table: true so operators understand the v2 storage limitation to a single tabular payload.
- **store_file_to_localdrive schema support**: Validate that store_file_to_localdrive tasks declare files_dir and filename parameters with correct types and presence, preventing runtime-only schema failures.
- **Nested storage overrides**: Accept nested storage.{data_dir, filename} blocks for v2 storage tasks, fall back to top-level params when absent, and flag unknown keys inside the storage block to preserve clarity.
- **Storage metadata readiness signal**: Emit a warning when v2 storage tasks cannot locate extraction.fields metadata (e.g., missing extract_document_data_v2 task) so teams can reconcile alias gaps before deployment.
- **Rules task optional knobs**: Type-check optional parameters write_value, backup, and task_slug on rules tasks and ensure reference_file values resolve to .csv-like paths.
- **Filename token cross-check**: Validate that every token in storage filename templates matches an available scalar extraction field; highlight extraneous tokens with guidance for field creation or template updates.


6. Non-Goals (Out of Scope)

- The tool does not run the application, orchestrate tasks, or contact external services.
- The tool does not modify or auto-correct config.yaml; it only suggests fixes.
- The tool does not pre-create directories (unlike runtime behavior in [modules/config_manager.py](modules/config_manager.py)); it only validates existence.

7. Design Considerations

- The validator mirrors key runtime expectations described in [tasks/prd-design-pdf-processing.md](tasks/prd-design-pdf-processing.md), especially Path Validation and dynamic Pipeline behavior.
- Use a tolerant parser (e.g., ruamel.yaml) to retain line/column for better diagnostics. If unavailable, fall back to pyyaml with best-effort location info.
- Implement rules as a pass-based validator to keep concerns separated:
  - Pass A: YAML parsing + root/type checks
  - Pass B: Structural schema checks
  - Pass C: Path existence checks
  - Pass D: Task existence and importability (optional)
  - Pass E: Pipeline dependency/order and token analysis
  - Pass F: Reporting and exit code resolution
- Ensure findings include a "config path" (dot-notation) to the offending key and a short suggestion string.

8. Technical Considerations

- Language: Python 3.11+ (same environment as the main app).
- Packaging: console_script entry point "config-check" using pyproject.toml.
- Parsing: ruamel.yaml (preferred) or pyyaml for fallback.
- Schema: pydantic models for structure/type checks; custom validators for token and order rules.
- Token parsing: strictly match {...} tokens within string params; ignore escaped braces {{...}} used for secrets templates.
- Import checks (--import-checks): use importlib to resolve module/class; handle ImportError gracefully with suggestions.
- Compatibility with runtime constraints documented in [modules/config_manager.py](modules/config_manager.py) (e.g., watch_folder.dir must pre-exist).
- Logging: to stdout; optional --verbose for debug traces.

9. Success Metrics

- 0 false negatives on known bad configs from test suite.
- < 5% false positive warnings after initial tuning.
- Adoption in CI for all deployments.
- Reduced runtime failures due to configuration issues by >80%.

10. Open Questions

- Should unknown top-level keys be errors by default (instead of warnings)?
- Should we support environment-variable substitution (e.g., ${VAR}) during validation?
- Should we provide an optional --create-missing-dirs preview that only prints mkdir commands without executing them?
- Should we enforce that archive_pdf occurs after store_file_to_localdrive, or keep it as a recommendation?

Appendix A: Examples

A.1 Success
$ config-check validate --config ./config.yaml
Validation passed with 0 errors, 1 warning
[WARNING] tasks.store_metadata_json.params.filename: Token {policy_number} not present in extraction.fields; consider adding field or removing token.

A.2 Errors
$ config-check validate --config ./config.yaml --strict --format text
Validation failed with 3 errors, 1 warning
[ERROR] web.upload_dir: Directory does not exist: ./web_upload. Create the directory or update web.upload_dir.
[ERROR] pipeline[2]: Task name 'store_metadata_json' not found under tasks. Add tasks.store_metadata_json or remove it from pipeline.
[ERROR] tasks.store_file_to_localdrive.params.filename: Uses {nanoid} but 'assign_nanoid' is not scheduled before this step. Move 'assign_nanoid' earlier in pipeline.
[WARNING] pipeline[3]: Task 'extract_metadata' appears multiple times in pipeline. Confirm whether 'extract_metadata' needs to run twice or remove the duplicate pipeline entry.
