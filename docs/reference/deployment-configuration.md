# Deployment configuration reference

| Item | Value |
| --- | --- |
| Audience | IT support and developers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

This reference describes deployment infrastructure. Pipeline and review-form
definitions are separate SQLite-backed objects. Runtime YAML is selected by
`--config-path`, `CONFIG_PATH`, then repository-root `config.yaml`; relative
paths resolve beside the selected file. YAML changes need coordinated restart.

## High-level Structure

Below is an example configuration snippet with explanations:

```yaml
logging:
  log_file: "app.log"                 # Path to the log file
  log_level: "INFO"                   # Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL

watch_folder:
  dir: "watch_folder"                 # Startup-compatibility path (must pre-exist; not a pipeline binding)
  validate_pdf_header: true           # Validate %PDF header before processing
  processing_dir: "processing"        # Folder where files are moved with UUID name (auto-created if missing)

web:
  upload_dir: "web_upload"            # Web-upload staging directory (must pre-exist; validated at startup)
  max_upload_mb: 50                    # Maximum size of one PDF in MiB
  max_upload_files: 20                 # Maximum PDFs in one request
  max_upload_request_mb: 200           # Maximum complete multipart request in MiB
  max_concurrent_uploads: 2            # Concurrent receivers per web process
  cors_allowed_origins: []            # Keep empty for same-origin browser use

database:
  path: "data/app_state.sqlite3"       # SQLite workflow-state database
  run_migrations_on_startup: true      # Run migrations when the app starts

review:
  default_queue_name: "default_review"
  lock_timeout_minutes: 60

# Workflow tasks and output paths are stored in SQLite pipeline definitions,
# not under top-level `tasks` or `pipeline` keys in this deployment file.
```

## Global Sections

- **logging:** Controls logging behavior.
- **watch_folder:** Defines coordinator timing/header behavior, the shared
  processing directory, and the required startup-compatibility path. Exact
  incoming-folder routing is stored in SQLite bindings.
- **web:** Defines upload directory, server settings (host, port, secret key, optional CORS allowed origins), file and request limits, concurrent uploads, and idle/overall upload timeouts.
- **database:** Defines the SQLite workflow-state path and migration behavior.
- **processing_queue:** Defines worker polling interval, lease duration, maximum attempts, and retry delay.
- **review:** Defines review queue behavior, queue name, and review lock duration.
- **ui:** Defines the application name, default page size, and whether
  administrator pages are enabled.
- **validation:** Defines validation availability, strict-mode default, and the
  allow-list switch for browser configuration saves. A save remains limited to
  the non-secret keys displayed on **Overview**.
- **auth:** Defines login failure rate limiting, attempt window, and cooldown.
  `web.token_exp_minutes` is the browser inactivity timeout. While an
  authenticated user interacts with the app, the browser renews the signed JWT
  periodically. An expired or revoked JWT cannot be renewed.
- **pipeline_secrets:** Maps administrator-visible aliases to deployment-owned
  provider credentials. Pipeline drafts store only `$secret` aliases, never
  resolved values.
- **custom_steps:** Deployment approval for exact `custom_step.*` module/class
  pairs. Enabling or approving a class does not add it to any pipeline.
- **schema.directories** and filesystem schema paths are migration/validation inputs;
  published SQLite review-form versions are authoritative for current review
  gates.
- Task output directories are owned by the exact pipeline version's parameters,
  such as `data_dir`, `files_dir`, `archive_dir`, and `split_dir`. Standard
  tasks create these when they execute. `watch_folder.processing_dir` remains a
  deployment setting shared across workflows.

For normal browser use, where users open the web application directly from the same FastAPI server, keep `web.cors_allowed_origins` as an empty list:

```yaml
web:
  cors_allowed_origins: []
```

This disables cross-origin browser access by default while preserving normal use of the built-in web interface. Only add values when a separate trusted frontend is hosted on another origin, such as a different domain, scheme, or port:

```yaml
web:
  cors_allowed_origins:
    - "https://trusted-frontend.example.com"
```

Do not use `*` for this setting. Command-line tools, Python scripts, and same-origin browser pages do not require CORS.

## Required Folders and Permissions

The system uses several folders for ingestion, processing, and storage. Ensure these folders exist and the system user has the correct permissions.

Startup validation rules:

- `watch_folder.dir` must already exist and be a directory. It is a deployment
  startup-compatibility path; actual multi-pipeline intake is controlled by
  enabled SQLite bindings. If missing or invalid, the application logs a
  CRITICAL error and exits at startup.
- `web.upload_dir` must already exist and be a directory. If missing or invalid, the application logs a CRITICAL error and exits at startup.
- Directories referenced by keys ending in `_dir` (except `watch_folder.dir`) are auto-created when possible; failures cause a CRITICAL log and exit.
- All `_dir` paths must exist and are directories; all `_file` paths must exist and are files.

### Pre-existing vs Auto-created folders (consolidated)

This subsection summarizes which folders the system expects to already exist, and which the application will create automatically at startup when possible.

Must pre-exist (startup validates and will fail if missing):

- `watch_folder.dir` — Startup-compatibility folder. The application will not
  create it; do not rely on it as an implicit pipeline binding.
- `web.upload_dir` — Staging folder used by the web upload handler. The application validates this at startup.
- Each directory entered in **Watch folders** — the
  binding service requires it to exist, be accessible, and not overlap another
  bound path.
- Each bound watch-folder account needs permission to list the directory, read
  incoming PDFs, move them into processing, and delete or replace files when
  the configured lifecycle requires it.
- Any deployment config key that ends with `_file` — the referenced file must
  already exist and be a regular file.
- Any other explicitly-documented required directory in your `config.yaml`.

Created automatically when needed:

- `watch_folder.processing_dir` — Temporary processing folder where PDFs are moved with UUID filenames.
- Any deployment `config.yaml` key that ends with `_dir` — the ConfigManager
  attempts to create it. This startup scan does not read task parameters from
  SQLite pipeline versions.
- Standard storage, split, and archive tasks create their configured output
  directories when they execute. The application account still needs permission
  to create and write them; create them in advance when the parent directory is
  controlled or when early permission verification is required.

Summary table:

| Folder / Pattern | Purpose | Creation behavior |
|------------------|---------|-------------------|
| `watch_folder.dir` | Startup-compatibility path, not multi-pipeline routing | Must pre-exist; startup fails if missing |
| SQLite watch-folder binding path | Actual incoming folder for one exact pipeline version | Administrator creates the folder first; binding rejects missing, duplicate, or nested paths |
| `web.upload_dir` | Web upload staging directory | Must pre-exist; startup fails if missing |
| `watch_folder.processing_dir` | Files moved here prior to processing (UUID names) | Auto-created at startup if missing |
| Pipeline task `files_dir`, `data_dir`, `split_dir`, or `archive_dir` | Durable or intermediate task output | Stored in the immutable pipeline version; standard task creates it at execution when permitted |
| Pipeline task `reference_file` | Existing reference file used by a rule task | Create and permission-test before publishing/processing |

Notes and recommendations:

- A failure to create a deployment `_dir` during startup logs a CRITICAL error
  and exits. A standard task that cannot create its SQLite-configured output
  directory fails that task at runtime. Pre-create important destinations and
  verify permissions to catch either condition early.
- To pre-create directories on Windows, use File Explorer or a Command Prompt:
```
mkdir watch_folder processing web_upload files data archive_folder
```
- Relative deployment paths resolve beside `config.yaml`, independent of the
  service's working directory. Absolute paths are also supported.
- Restart the supervisor, web, and worker together after editing deployment
  YAML. Each process holds its own configuration snapshot; editing one process's
  in-memory settings does not synchronize the others. Operational settings
  managed through the UI remain stored in SQLite.
- Ensure the user/service account running the application has Modify/Write permissions on directories that will be written to.

For a bound watch folder, **Test access** confirms that the directory exists
and can be listed; it does not prove that the application can move or delete a
file. Test with a representative PDF before enabling production intake.


## Credentials and validation

Provision fixed accounts in SQLite with [setup_users](../../tools/setup_users.py).
The obsolete `authentication` block is a migration source, not the current
account store. Keep `pipeline_secrets` and `web.secret_key` deployment-owned.
Use unique non-placeholder secrets and the [production access procedure](../it-support/configuration-and-access.md).

```powershell
.\.venv\Scripts\python.exe -m tools.config_check validate --config path\to\config.yaml --import-checks
```

The validator does not migrate or mutate SQLite. Read warnings (exit 2) before
accepting the result. See [CLI documentation](../../tools/config_check/README.md),
[finding codes](../../tools/config_check/examples/ERROR_CODES.md), and
[troubleshooting](../it-support/config-check-troubleshooting.md).

Configuration semantics are implemented by [ConfigManager](../../modules/config_manager.py)
and [config schema](../../tools/config_check/schema.py). For process ownership
see [configuration architecture](../architecture/configuration-and-versioning.md).
