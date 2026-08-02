# Configuration Examples

This directory contains deployment-YAML samples, legacy fixtures, illustrative
rules-task documents, and the error-code reference. Pipeline and review-form
definitions are normally authored and published in SQLite through the admin UI.

## Valid Configuration Examples

### `complete_config.yaml`

An expanded deployment-settings sample covering database, review, validation,
UI, and authentication options. Despite its historical filename, it is not an
inventory of every `config.yaml` setting and intentionally contains no workflow
`tasks` or `pipeline`.

### `minimal_config.yaml`

A compact structural sample for SQLite-backed deployment settings. It is useful
for `validate-file --kind runtime`, but it is not by itself a runnable
application configuration: a real deployment must also provide its required
folders/web settings and point at an initialized database.

### `valid_config.yaml` (Legacy)
The original deployment-schema fixture, retained for backward compatibility.

## Invalid Configuration Examples

`invalid_missing_paths.yaml` is a legacy-named fixture. Its current content is a
deployment-settings mapping and no longer guarantees a validation failure. For
stable automated negative cases, use the focused fixtures under
`test/tools/config_check/`; do not depend on a human example's filename.

## Testing Examples

You can test these examples with the config-check tool:

```powershell
# From the repository root, validate deployment-file structure without opening SQLite
.\.venv\Scripts\python.exe -m tools.config_check validate-file --file tools\config_check\examples\complete_config.yaml --kind runtime
.\.venv\Scripts\python.exe -m tools.config_check validate-file --file tools\config_check\examples\minimal_config.yaml --kind runtime
```

Use `validate --config <real-config> --all-stored` for an initialized deployment
whose database, folders, published versions, and bindings should also be checked.

## Rules Task Validation Examples

### `rules_task_examples.yaml`

A multi-document illustration of rules-task validation scenarios:

- **Valid Rules Task**: Properly configured rules task with all required fields
- **Rules Task with Issues**: Examples of common validation errors and warnings
- **Semantic Issues**: Type mismatches and unrealistic field references
- **Corrected Configuration**: Fixed versions of problematic configurations
- **Complex Rules Task**: Advanced scenarios with extraction and rules tasks

### Sample Reference Files (`sample_reference_files/`)

Synthetic CSV fixtures are bundled for rules validation:

- `suppliers.csv`: readable CSV with headers and data;
- `empty_suppliers.csv`: empty-file case; and
- `invalid_format.csv`: malformed-input case.

### Testing Rules Task Validation

The file is documentation, not one runnable runtime configuration: it contains
several YAML documents and references example CSV paths that are not bundled in
this directory. Copy one scenario into a temporary, ignored portable pipeline
definition, replace credentials with `$secret` references, and supply your own
synthetic CSV before validating it. Automated rules validation is covered by
`test/tools/config_check/`.

For detailed troubleshooting of rules task validation issues, see the main troubleshooting guide at [`docs/config_check_troubleshooting.md`](../../../docs/config_check_troubleshooting.md).

## Error Code Reference

See `ERROR_CODES.md` for the operator-facing validation codes and corrective
actions. Machine-readable output remains authoritative for a particular run.

## Using Examples as Templates

These examples can serve as templates for creating your own configurations:

1. Start with `minimal_config.yaml` for deployment-setting structure.
2. Consult `complete_config.yaml` for the additional settings it demonstrates.
3. Create and publish workflow definitions in the Pipeline and Review Form
   editors; do not add them back to deployment YAML.
4. Use `ERROR_CODES.md` and JSON findings to troubleshoot validation errors.

## Configuration Best Practices

Based on these examples, follow these best practices:

1. **Always specify required fields** explicitly rather than relying on defaults
2. Use meaningful task keys in portable or stored pipeline definitions.
3. Include appropriate `on_error` behavior in each configured task.
4. Validate import paths using `--import-checks` before publication/deployment.
5. Run `--all-stored` against an initialized deployment before operations.
6. Document non-obvious settings without including credentials or customer data.
