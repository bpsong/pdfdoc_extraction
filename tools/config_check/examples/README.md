# Configuration examples

This directory ships synthetic CSV fixtures and the curated
[finding catalog](ERROR_CODES.md). Deployment YAML, exported definitions and
local test documents are ignored by Git. Historical local filenames such as
`minimal_config.yaml`, `complete_config.yaml`, `valid_config.yaml`,
`invalid_missing_paths.yaml`, and `rules_task_examples.yaml` are not bundled.

## Create a local deployment sample

Copy this structure into an ignored local YAML file, replace the secret locally,
and create the two required roots. It has no active pipeline or account setup.
Use absolute upload/watch/processing paths when the file is outside the
repository; see [path resolution](../../../docs/reference/deployment-configuration.md#path-resolution).

```yaml
web:
  host: 127.0.0.1
  port: 8000
  upload_dir: web_upload
  secret_key: REPLACE-LOCALLY-WITH-A-UNIQUE-RANDOM-SECRET
watch_folder:
  dir: watch_folder
  processing_dir: processing
database:
  path: data/app_state.sqlite3
  run_migrations_on_startup: true
```

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m tools.config_check validate-file --file local-example.yaml --kind runtime
```

Runtime-file validation checks structure/paths without opening SQLite. Full
`validate --config local-example.yaml --all-stored` additionally needs an
initialized database and checks stored configuration read-only. Follow
[installation and provider setup](../../../docs/it-support/installation-and-provider-setup.md)
for startup, fixed accounts, models and a usable published pipeline. Production
also requires the [access settings](../../../docs/it-support/configuration-and-access.md).

## Pipeline and form examples

Create drafts in the production editors and export them for portable validation.
Import updates a draft only; publish explicitly after validation. Pipeline
content uses `kind: pipeline-bundle`, selected by `validate-file --kind pipeline`.
See the [CLI reference](../README.md) and
[task parameter examples](../../../docs/reference/tasks/README.md).

For CSV updates, use the
[Update Reference definition](../../../docs/reference/tasks/rules-context-housekeeping.md#rulesupdate_reference)
and a temporary copy of a synthetic CSV. The task changes existing matching rows;
it does not append records. Do not validate against or update customer CSVs for
routine development checks.

## Bundled CSV cases

- `sample_reference_files/suppliers.csv`: readable headers and synthetic rows.
- `sample_reference_files/empty_suppliers.csv`: empty-file case.
- `sample_reference_files/invalid_format.csv`: malformed-input case.

Automated positive/negative cases live under `test/tools/config_check/`. Run them
from the repository root with the repository interpreter. For a particular
validation run, JSON findings and the exit code are authoritative: 0 is clean,
1 has errors, 2 has only warnings, and 64 indicates invalid usage. The finding
catalog is curated rather than an exhaustive list of every optional analysis.
