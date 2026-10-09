# Technical Operations Reference

This reference is for IT staff and application support. It contains installation,
configuration, database, task-parameter, and recovery details moved from the user
guide. Operators and business administrators should follow the app instructions
in the [User Guide](user_guide.md).

Pipeline archiving and processing-history cleanup have a separate
[administrator walkthrough and IT reference](pipeline_retention_admin_guide.md).

The section numbers below match the user guide so existing task references remain
easy to find. For creating and publishing pipelines, forms, or watch folders in
the app, use [Administrator Workflow Details](user_guide.md#455-administrator-workflow-details).

## Find the technical details

- [Start and stop the application](#41-starting-and-stopping-services)
- [Folders and permissions](#42-required-folders-and-permissions)
- [Configuration structure](#43-configuration-management)
- [Account provisioning and recovery](#account-provisioning-and-recovery)
- [Database and artifact storage](#45-database-state-and-artifact-storage)
- [Backup and recovery](#456-backup-and-recovery)
- [Logging and troubleshooting](#46-log-files-and-troubleshooting)
- [Task types and parameters](#48-task-system-standard-steps-and-parameters)
- [Structured extraction](#49-llamacloud-extract-v2-structured-data-support)
- [Config-check validation](#412-config-check-validation-tool)

### 4.1. Starting and Stopping Services

**Starting the main processing service (Windows):**

1. Open PowerShell.
2. Navigate to the project root folder.
3. Run the following command to start the system:

    ```
    .\.venv\Scripts\python.exe main.py
    ```

4. The system will begin scanning enabled SQLite watch-folder bindings and
   processing files. By default, this command also starts the web interface,
   which will be accessible at `http://localhost:8000` (or the host/port
   configured in `config.yaml`).

**Starting only watch-folder processing (without Web Interface):**

If you only need the watch folder functionality and do not wish to run the web interface, use the `--no-web` argument:

    ```
    .\.venv\Scripts\python.exe main.py --no-web
    ```

This mode still starts the supervised processing worker and watch-folder
coordinator, but browser upload, review, reports, and administration are
unavailable. A web-only process cannot scan watch folders.

**Stopping the service:**

To stop the coordinator and web interface, press `Ctrl+C` in the terminal where
`main.py` is running. This requests an orderly shutdown but does not guarantee
that an in-progress provider job finishes first; follow section 4.7 afterward.

### 4.2. Required Folders and Permissions

The system uses several folders for ingestion, processing, and storage. Ensure these folders exist and the system user has the correct permissions.

Startup validation rules:

- `watch_folder.dir` must already exist and be a directory. It is a deployment
  startup-compatibility path; actual multi-pipeline intake is controlled by
  enabled SQLite bindings. If missing or invalid, the application logs a
  CRITICAL error and exits at startup.
- `web.upload_dir` must already exist and be a directory. If missing or invalid, the application logs a CRITICAL error and exits at startup.
- Directories referenced by keys ending in `_dir` (except `watch_folder.dir`) are auto-created when possible; failures cause a CRITICAL log and exit.
- All `_dir` paths must exist and are directories; all `_file` paths must exist and are files.

#### 4.2.1 Pre-existing vs Auto-created folders (consolidated)

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

### 4.3. Configuration Management

#### 4.3.1. High-level Structure

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

#### 4.3.2. Global Sections

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

#### 4.3.3. Pipeline Configuration

SQLite is authoritative for pipeline templates, their editable drafts,
immutable published versions, exact review-schema dependencies, and
watch-folder bindings. Use **Pipeline** to create or clone a named template,
edit and save its draft, validate it, and publish a numbered version. A
published version cannot be edited or deleted. To change behavior, update the
draft and publish a new version; existing documents continue with the version
already assigned to them.

The pipeline name, description, and document type save when you leave the
edited field. A successful save shows **Pipeline details saved** and updates
the template selector without reloading the task editor. Unsaved task edits
and the selected step are preserved; use **Save Draft** to save those edits
separately. Renaming preserves the template ID/key and published versions.

After at least one pipeline has been published into SQLite, runtime
`config.yaml` does not need top-level `pipeline` or `tasks` sections. Retain
deployment settings such as paths, database configuration, custom-task
approvals, and `pipeline_secrets`; published definitions refer to secret
aliases and never store resolved secret values.

YAML blocks containing `tasks:` and `pipeline:` elsewhere in this guide are
portable definition examples and legacy migration shapes. They are useful for
understanding task parameters, **Pipeline** import/export, and the
`config-check validate-file` command; do not paste them into the active
deployment `config.yaml` for a newly created workflow. Normal authoring is
visual: **Pipeline** writes the draft and published versions to SQLite.

Each definition contains an ordered `pipeline` list and a `tasks` registry.
Each pipeline entry references a task key with `module`, `class`, and `params`.
That key is the task's authoritative identity in task-run state, errors, and
artifact producer metadata.
The legacy `task_slug` parameter is temporarily accepted for compatibility but is ignored and produces a deprecation warning. Remove it from existing task parameters; do not add it to new configurations.
The runner reserves `cleanup_task` for automatic housekeeping. It is recorded as an internal task run after configured execution finishes, but it is not added to `tasks` or `pipeline` and does not replace the document's configured pipeline position.
The upload page requires one eligible published version before it creates a
batch. Each enabled watch folder likewise requires an exact version binding.
There is no silent default or “latest” fallback. Automatic classification,
mixed-document routing to different child pipelines, and conditional workflow
graphs remain deferred.

Pipeline lifecycle has an operational effect:

- **Inactive** is the creation/editing state. A template can have published
  versions while inactive, but those versions are not eligible for new intake.
- **Active** makes its published versions eligible for upload selection and
  enabled watch-folder bindings.
- **Archived** is terminal. First set a template to inactive and ensure no
  enabled watch-folder binding refers to it. Archived templates cannot be
  restored or published again. Historical documents remain pinned and readable.

**Archive pipeline** and **Clean up processing data** are independent admin
actions. Save or discard unsaved draft changes before archiving. The archive
dialog shows retained history and linked watch folders; enabled bindings block
confirmation. Pause, reassign, unbind, or retire those bindings on **Watch
folders** first. Paused/unbound paths stay reserved and incoming files wait;
retiring releases the path. Archiving retains the template, draft, versions,
files, and history, and existing assigned work can continue. Archived templates
are hidden by default; enable **Show archived** to inspect, clone published
versions, or clean up history. The editor keeps Show archived enabled immediately
after archiving so the selected pipeline remains visible. Permanent pipeline
deletion and restoration are not offered.

Use the dedicated **Archive pipeline** button to review and confirm this action;
the availability dropdown changes only **Active** and **Inactive**. Metadata and
availability saves preserve unsaved task edits and the selected task. After
archiving, **Show archived** refreshes the full list while retaining the selected
pipeline. Archived task and metadata controls, including **Reset Draft**, are
read-only; cloning a published definition and cleaning history remain available.

To reduce SQLite processing data, select an active, inactive, or archived
pipeline and choose **Clean up processing data**:

1. Choose **Finished before** and run **Preview cleanup**. The date is exclusive:
   `2026-01-01` means all recorded processing activity must be earlier than
   `2026-01-01 00:00 UTC`, not local midnight or the original upload date.
2. Review eligible batches/documents, jobs, task runs, extraction results and
   fields, completed reviews, split decisions, expired review locks, file
   registrations, and upload receipts. Exclusion counts explain protected work.
3. Type the exact pipeline name and choose **Delete processing data**. The
   preview belongs to the current admin, expires after 15 minutes, and is checked
   again in the deletion transaction. Changed eligible records require a new
   preview. Deletion cannot be undone in the app.

Cleanup removes whole batches only. A batch is protected if any document/child,
job, task, manual split, or review is active or resumable, a review lock is live,
activity is on/after the cutoff, or its history has inconsistent links. In
particular, a completed review awaiting resumed processing is protected.
Pipeline definitions/versions and audit events remain. Reports and document or
review pages lose deleted history, and its file preview links stop resolving.
Physical source PDFs, split PDFs, CSV/JSON exports, and other files remain on
disk. Old upload receipt payloads are trimmed while their minimal idempotency
keys remain; retrying a cleaned submission cannot recreate it automatically.

Deleted database pages become available for SQLite to reuse. The `.sqlite3`
file usually does not shrink just because rows are deleted; database compaction
is separate maintenance and is not performed by this action. Cleanup therefore
reduces retained processing data without promising an immediate reduction in
the database file's size.

For click-by-click instructions, see
[Archive a pipeline](pipeline_retention_admin_guide.md#archive-a-pipeline),
[Pause linked watch folders](pipeline_retention_admin_guide.md#pause-linked-watch-folders),
and [Clean up processing data](pipeline_retention_admin_guide.md#clean-up-processing-data).
These walkthroughs explain what to select, how to confirm or cancel, how to check
the result, and what to do when an action is blocked. The same guide keeps API,
database maintenance, and deployment details in an optional IT/support section.

Publishing creates an immutable version but does not by itself make the
template eligible for new intake. Set the template to **Active** separately,
then confirm that the intended version appears on **Upload & Process** or is
selected by an enabled watch-folder binding.

Task classes must be approved before the app imports them. Built-in `standard_step.*` tasks are approved by the application. Customer-specific tasks must be deployed under the `custom_step.` Python package and approved in deployment YAML under `custom_steps.registry`.

Each pipeline draft/version may contain at most one split task, one extraction
task, and one review-gate task. Alternate task definitions may remain under
`tasks`, but listing more than one singleton type in the ordered `pipeline` is
a blocking validation error. When used, split must precede extraction and the
review gate must follow extraction.

Example task categories include:

- `extraction`: Extract data from PDFs.
- `split.llamacloud_split`: Optionally split bundled PDFs into child documents before extraction.
- `review.review_gate`: Pause documents for operator review based on confidence, schema, or policy rules.
- `rules.update_reference`: Update reference CSV files.
- `storage.store_metadata_as_csv` / `storage.store_metadata_as_json`: Persist extracted information.
- `storage.store_file_to_localdrive`: Persist the processed PDF.
- `archiver.archive_pdf`: Archive the original input PDF.

The housekeeping cleanup step is managed automatically by the WorkflowLoader and runs after configured execution finishes or stops on an ordinary failure. Review pauses and split fan-out return first; cleanup runs after resumed work or each split child's configured work finishes. It deletes transient processing files but does not archive files or remove status records.


## Account provisioning and recovery

#### First-Time Account Setup

Before the first login, open PowerShell in the project folder and run:

```powershell
.\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml
```

The tool asks for an administrator password and an operator password, then asks you to confirm each one. Setup stops if the accounts already exist; do not use the reset option for routine setup.

For an upgrade from an older installation, an administrator may import the existing administrator bcrypt hash while setting a new operator password:

```powershell
.\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml --legacy-config config.yaml
```

After a successful migration, remove the obsolete `authentication` section from the runtime YAML.

#### Recover Access When the Administrator Cannot Sign In

Use the setup tool's reset option only when the administrator password is unavailable:

```powershell
.\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml --reset
```

The tool asks for new passwords and replaces the credentials for **both** fixed accounts. Run it against the same configuration file, and therefore the same `database.path`, used by the application. After the reset, test both accounts before returning the system to normal use.

#### Production Web Hardening

Set `APP_ENV=production` (or `ENV`/`ENVIRONMENT`) and configure every hostname
that clients or a reverse proxy will send in the HTTP `Host` header:

```yaml
web:
  allowed_hosts:
    - app.example.com
  production_docs_enabled: false
```

Production startup rejects an empty or wildcard host allowlist. Include the
public application hostname and, only when applicable, the hostname forwarded
by a trusted reverse proxy. OpenAPI endpoints (`/docs`, `/redoc`, and
`/openapi.json`) are disabled in production unless
`production_docs_enabled` is explicitly enabled. The application also sends
baseline anti-framing, MIME-sniffing, referrer, and browser-permission headers.
Production startup also requires `web.secret_key` to be at least 32 characters
and rejects common placeholders. Generate a unique random key and keep it out
of version control. Changing it invalidates existing login sessions.
Production login and CSRF cookies use the `Secure` attribute, so serve the
browser-facing app over HTTPS (directly or through a trusted TLS proxy).
Local development without a production environment flag can still use HTTP.
Tailwind and DaisyUI are bundled locally; run `npm install` and
`npm run build:css` after changing frontend utility classes or package versions.
- Do not commit password hashes or secret-bearing config files to version control.
- Rotate passwords and audit access regularly.

### 4.5. Database, State, and Artifact Storage

The unified application uses SQLite as the primary source of workflow state.

#### 4.5.1. Database Initialization

The database location is configured by `database.path`, with a default of
`data/app_state.sqlite3`. During normal `main.py` startup, the parent process is
the only migration owner. The web and worker children open the database in
verification mode and refuse to start when the schema is missing, incomplete,
older, or newer than the supported version. HTTP requests do not run schema
migrations.

A directly launched worker verifies an already prepared database by default.
Pass `--startup-mode migrate` only when that standalone worker must own
migration. A directly launched Uvicorn process uses verification mode; set
`DOCFLOW_STARTUP_MODE=migrate` explicitly when it must initialize a fresh
database.

Administrators should back up the SQLite database together with durable business artifacts. The database contains operational state and review decisions; exported CSV/JSON/PDF files remain filesystem artifacts.

#### 4.5.2. What SQLite Stores

SQLite stores:

- ingestion batches and source documents
- split child documents and page/category metadata
- task runs, status, error details, and task output summaries
- extraction results, extracted fields, confidence, review state, and corrected values
- review queue items, claims, drafts, diffs, and completions
- document artifact records in `document_files`
- non-secret runtime settings, admin configuration versions, and audit events
- fixed admin/operator identities, bcrypt password hashes, roles, and session-revocation versions

Text status files are not required for configured workflow state.

#### 4.5.3. Filesystem Artifact Boundaries

The filesystem still stores durable business files and operational inputs:

| Artifact type | Examples | State source |
|---------------|----------|--------------|
| Source input files | watch-folder PDFs, upload staging PDFs | Registered as original/source files where SQLite context exists |
| Working files | processing-folder PDFs, split working PDFs | Temporary or registered by split/source role |
| Archive files | archived source PDFs | Registered as `source_archive` |
| Final exports | JSON, CSV, renamed PDFs | Registered as `export_json`, `export_csv`, `export_pdf` |
| Reference/config files | reference CSVs, YAML config, schema files | Managed by configuration and admin settings flows |

No remaining text file should be required to reconstruct workflow state. If a legacy endpoint returns status, it should be treated as a SQLite compatibility response.

PDF previews in the web app are served only when the registered file path resolves under configured artifact directories, such as upload, watch, processing, split, archive, data, or files directories. Records that point outside those configured roots are not served through the preview endpoint.

#### 4.5.6. Backup and Recovery

For a complete operational backup, include:

- the SQLite database file configured at `database.path` (including templates,
  drafts, immutable versions, dependencies, and ingress bindings)
- task-owned output folders such as `files/`, `data/`, `archive_folder/`, and any split task `split_dir` used by configured tasks
- reference CSVs, deployment configuration, and any portable configuration
  exports retained by your organization

Stop the application before copying the SQLite database, or use SQLite's
online backup mechanism. Do not assume that copying only the main database
file while the service is running captures the complete state; account for
SQLite WAL/SHM files or use a consistent SQLite backup operation. Capture the
database and durable artifacts from the same backup point.

Restore the database and durable artifacts from the same backup point. If the
database is restored without the files, the UI may show registered artifacts
whose paths no longer exist. If files are restored without the database,
batch/task/review history and the exact executable versions needed for resume
will be incomplete. Do not reconstruct an interrupted run from the newest
draft or version. A legacy deployment YAML can be imported as a draft during
migration, but import never publishes and never replaces an already pinned
definition.

### 4.6. Log Files and Troubleshooting

The configured `logging.log_file` is used as the base for role-specific logs. The
default base name `app.log` produces `app.supervisor.log`, `app.web.log`, and
`app.worker.log`.
Normal supervised startup produces separate supervisor, web, and worker log
files. Check the supervisor log for startup, shutdown, and child-process
failures; the web log for browser/API errors; and the worker log for task,
provider, retry, and artifact failures.

- `logging.log_file` supplies the base log path. The default `app.log` produces
  `app.supervisor.log`, `app.web.log`, and `app.worker.log` beside the active
  configuration file.
- To see more detailed logs, set `logging.log_level` to `DEBUG` in `config.yaml`.
- Common startup errors include:
  - Invalid YAML syntax (check your config file with a YAML validator).
  - A missing, incomplete, older, or newer SQLite schema.
  - Missing folders (create required folders like `watch_folder`, `web_upload` before starting).
  - Missing or invalid provider credentials, such as a LlamaCloud `api_key`.
  - Permission errors (ensure the system user has read/write access to all configured directories).
- Performance considerations for large files:
  - Larger PDFs require more disk, memory, network, split, and provider processing time.
  - Process unusually large documents individually and during quieter periods.
  - Monitor **Processing Overview**, the role-specific logs, Windows Task Manager, free disk space, and provider quotas.
- During runtime troubleshooting:
  - Failed tasks log detailed errors to `app.worker.log` with timestamps and context information when the default base path is used.
  - Files with processing errors may remain in the processing directory; check **Processing Overview**, **Failures**, and the worker log.
  - Use the application pages for current status and the log for technical details.
  - Use `Ctrl+C` to request an orderly shutdown, then verify any document that was processing at the time.
- Common runtime issues and solutions:
  - **High memory usage**: Reduce batch size and process large PDFs individually.
  - **Slow processing**: Check internet connectivity for cloud extraction providers.
  - **Files stuck in processing**: Verify API credentials and rate limits with your extraction provider.
  - **Permission errors**: Ensure all configured directories have proper read/write permissions.
- Log monitoring tips:
  - Look for "CRITICAL" messages that indicate startup failures.
  - "ERROR" messages show task failures with specific details.
  - "WARNING" messages indicate non-fatal issues that may affect performance.
  - Use the web interface to monitor processing status through its periodic refreshes.

### 4.7. Graceful Shutdown and Error Recovery

To stop the system, press `Ctrl+C` in the terminal where `main.py` is running.
This asks the watch-folder coordinator, web server, and durable worker to stop,
then runs registered cleanup handlers. It does not guarantee that every
in-progress document finishes before the processes exit. An unexpected web,
worker, or coordinator exit stops the remaining components and returns a
nonzero process exit code. On Windows, the supervisor gives child processes a
bounded graceful-stop period before force-terminating their process trees.

For service monitoring, `GET /health/live` confirms that the web process can
respond and `GET /health/ready` returns `503` until the current supervised run
is ready. Administrators can use `GET /api/admin/runtime-health` for component,
heartbeat, watch-folder degradation, and database details.

After stopping or restarting:

1. Check the final shutdown messages in `app.supervisor.log` when using the
   default log base path.
2. Sign in and open **Processing Overview** and **Failures**.
3. Inspect any document that was processing when shutdown began.
4. Confirm whether its outputs were created before deciding to re-upload it.
5. Do not delete processing files or database records unless the document state and recovery need are understood.

If the system fails to start, check the supervisor and component logs, validate
`config.yaml`, confirm that the required watch and upload folders exist, and
verify folder permissions and provider connectivity. The Config Check tool
described in section 4.12 should be the first configuration diagnostic.

### 4.8. Task System: Standard Steps and Parameters

Standard steps are predefined operations configured in workflows. Below are the main task types and their parameters.

The YAML snippets in sections 4.8-4.10 show the portable definition shape used
by **Pipeline** import/export and migration tools. For a new workflow, configure
the same values with the visual editor. Do not add these `tasks` and `pipeline`
blocks to runtime `config.yaml`. In published definitions, secret parameters
must use `{ $secret: "alias" }`, where the alias exists under deployment-owned
`pipeline_secrets`.

#### 4.8.1. extraction

- **Current module/class:** `standard_step.extraction.extract_pdf` / `ExtractPdfTask`
- **Purpose:** Extracts structured data and confidence information from PDF documents through LlamaCloud Extract v2.
- **params:**
  - `api_key`: required secret reference in a versioned pipeline, for example
    `{ $secret: "llamacloud-primary" }`. Resolved credentials exist only in
    deployment `pipeline_secrets`.
  - `configuration_id`: optional saved Extract v2 configuration ID from the LlamaCloud UI. If omitted, the task builds an inline schema from `fields`.
  - `tier`: optional inline Extract v2 tier. Supported values are `"agentic"` and `"cost_effective"`; the default is `"agentic"`.
  - `parse_tier`: optional Parse tier for inline extraction.
  - `extraction_target`: optional target, default `"per_doc"`.
  - `cite_sources`: optional boolean to request citation metadata.
  - `confidence_scores`: optional boolean to request confidence metadata. Default is `true`.
  - `project_id` / `organization_id`: optional advanced provider-scoping values.
  - `poll_interval_seconds`: optional advanced polling interval. Default is `2.0`.
  - `timeout_seconds`: optional advanced timeout. Default is `1800.0`.
  - `fields`: map of field keys to alias and type, e.g.:

    ```yaml
    fields:
      name: { alias: "Name", type: "str" }
      amount: { alias: "Amount", type: "float" }
    ```

- **Behavior:**
  - Sends the PDF to the extraction provider.
  - Validates returned data against configured fields and types.
  - Normalizes extracted output to workflow field keys in `context["data"]`. Saved LlamaCloud configurations may return either field keys or aliases; both are accepted.
  - Storage tasks can transform workflow field keys only when their own
    task-specific `extraction.fields` mapping defines output aliases.
- **Notes:**
  - Use `configuration_id` when you want LlamaCloud to use a saved Extract v2 configuration. Omit it when you want the application to build the extraction schema from the YAML `fields` block.
  - In saved-configuration mode, `tier`, `parse_tier`, `extraction_target`,
    `cite_sources`, and `confidence_scores` come from the saved LlamaCloud
    configuration. Local `fields` normalize provider keys/aliases into stable
    workflow keys. Configure any CSV/JSON output aliases separately on that
    storage task.
  - Do not use `agent_id` for new configurations. It is a legacy Extract v1/LlamaExtract-era parameter and is not required by the current Extract v2 runtime.
  - Field names and types must match the provider's schema.
  - Internet access over HTTPS is required.

**Inline YAML configuration example:**

```yaml
tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: { $secret: "llamacloud-primary" }
      tier: "agentic"
      extraction_target: "per_doc"
      fields:
        supplier_name:        { alias: "Supplier name",       type: "str" }
        client_name:          { alias: "Client name",         type: "str" }
        client_address:       { alias: "Client",              type: "str" }
        purchase_order_number: { alias: "Purchase order",     type: "str" }
        invoice_amount:       { alias: "Invoice amount",      type: "float" }
        insurance_start_date: { alias: "Insurance Start Date",type: "str" }
        insurance_end_date:   { alias: "Insurance End Date",  type: "str" }
        policy_number:        { alias: "Policy Number",       type: "str" }
        serial_numbers:       { alias: "Serial Numbers",      type: "Optional[List[str]]" }
        invoice_type:         { alias: "Invoice type",        type: "str" }
    on_error: stop

pipeline:
  - extract_document_data
```

##### GLM-OCR extraction (local Ollama)

- **Module/class:** `standard_step.extraction.glm_ocr_extract` /
  `GlmOcrExtractTask`
- **Purpose:** Extracts configured structured data from PDF document types
  through a locally reachable Ollama server and the `glm-ocr:latest` vision
  model.
- **Prerequisites:** Install Ollama separately, pull `glm-ocr:latest`, start
  Ollama, and confirm the configured HTTP endpoint is reachable. Document mode
  also requires its configured resolver model to be installed.
  The application does not install, start, stop, or pull models from Ollama.
- **Parameters:**
  - `ollama_host`: HTTP(S) base URL, normally
    `http://127.0.0.1:11434`. Embedded credentials, query strings, and fragments
    are rejected.
  - `model`: installed Ollama model name, normally `glm-ocr:latest`.
  - `document_instructions`: optional document-level extraction guidance. Do not
    place secrets in instructions.
  - `prompt_style`: `detailed` (default) repeats deterministic field descriptors
    and the schema in the text prompt for compatibility with existing
    pipelines. `compact` keeps the schema only in Ollama's native `format`
    parameter and sends the document instructions with a short extraction
    contract. Compact mode can work better with smaller local models when a
    long duplicated prompt distracts from the document's visual relationships.
    `verbatim` is an advanced option that sends non-empty
    `document_instructions` exactly as written, with no framework prompt text,
    while still enforcing the native JSON Schema. Use it only after controlled
    testing because the instructions become the complete model prompt.
  - `resolution_mode`: `document` resolves each scalar or flat object against
    the complete ordered PDF and reconciles the configured table from page-level
    GLM-OCR evidence. `page_merge` retains the first supported page value and is
    the compatibility default when an older published definition omits this
    parameter. Newly added visual-editor tasks default to `document`.
  - `resolver_model`: installed local model used in `document` mode. It is
    required in that mode; the visual editor initially suggests
    `qwen3.5:9b-q4_K_M`.
  - `resolver_max_dimension`: longest edge, in pixels, for page images sent to
    resolver calls; default `1280`, allowed range 256 through 4096. Scalar and
    object fields use all ordered pages. Each table evidence chunk uses only its
    referenced source pages so the resolver can inspect visible table and
    section boundaries without loading unrelated pages.
  - `resolver_num_ctx`: positive resolver context size; default `18000`.
  - `resolver_num_predict`: positive resolver output-token limit; default
    `10000`. The resolver context must still be large enough for the prompt and
    requested output; increase `resolver_num_ctx` separately when required.
  - `resolver_max_attempts`: maximum attempts for a field or table evidence
    chunk; default `2`, allowed range 1 through 5. A table chunk that reaches the
    resolver output limit is split into smaller evidence chunks instead of
    repeating the same oversized request.
  - `dpi`: positive integer PDF render resolution; default `216`.
  - `num_ctx`: positive integer model context size; default `8192`.
  - `num_predict`: positive integer output-token limit; default `2048`.
  - `timeout_seconds`: positive request timeout; default `300`.
  - `fields`: the same stable extraction-field mapping used by downstream
    review and storage. Scalar fields, scalar lists, flat objects, and one
    `List[Any]` table with `item_fields` are supported. Text fields may define
    `choices` to constrain the Ollama JSON schema, and may opt into the
    `iso_date` normalizer to convert a transcribed source date to `YYYY-MM-DD`
    after extraction. A field or flat child property may set a positive,
    sibling-unique `schema_order`; the GLM editor exposes this as **Schema
    position**. Explicit positions control JSON Schema property order even
    though versioned JSON mappings are stored canonically.

Configure this task from **Admin > Pipeline** by adding **Glm Ocr Extract**.
Its properties panel is separate from the LlamaCloud Extract editor. Set the
local model values, choose **Complete document** for multi-page resolution, add
scalar fields, and use **List of objects > Edit row schema** for repeated logical
rows. Add and configure **Review Gate** after extraction, pin an exact published
review-form version, then add CSV or JSON storage. Save, validate, and publish
the pipeline before assigning it to an upload or watch-folder binding.

The task does not contain invoice-specific fields or parsing rules. Field keys,
aliases, descriptions, types, constraints, and document instructions define the
document semantics for each pipeline. For example, a bill-of-lading pipeline can
request a bill-of-lading number, shipper, consignee, notify party, carrier,
vessel/voyage, ports, and one containers or cargo table. Do not submit it to an
invoice pipeline and expect those fields to change automatically; create a
dedicated pipeline and matching review form using the same GLM-OCR task.

###### Multiline field extraction guidance

Use field-level **Extraction guidance** when one text value occupies several
printed lines or sits next to a visually similar field. Typical examples include
addresses, consignee blocks, notify-party details, cargo descriptions, payment
instructions, and free-text notes. The guidance is part of that pipeline's
document schema; it does not change the generic GLM-OCR task for other document
types.

Configure the field in the visual editor:

1. Open **Admin > Pipeline**, select the intended pipeline template, and select
   its **Glm Ocr Extract** task.
2. Under **Extraction fields**, expand the text field that needs adjustment.
3. In **Extraction guidance**, identify the printed label or visual anchor,
   state that the value may span multiple lines, define where extraction must
   stop, say which lines must be retained, and exclude nearby fields that must
   not be copied.
4. Review **Document instructions** in the same task. Make its field definition
   consistent with the field-level rule. For example, do not describe `billTo`
   as a name and address at document level while its field guidance requests a
   name only.
5. Select **Save Draft**, then **Validate**. Resolve every blocking finding and
   publish a new immutable pipeline version.
6. Submit representative PDFs against the new version one at a time. At Review
   Gate, compare the entire field value with the source PDF, including embedded
   line breaks, and check every other field for prompt regressions before
   completing review.

Use this general pattern and replace each placeholder with document-specific
semantics:

> Extract the complete `<value>` block directly under the `<printed label>`
> label. The value may span multiple lines. Continue until `<clear stopping
> boundary>`. Preserve `<required line types>` and join the lines with `, `.
> Do not include `<adjacent or unrelated fields>`.

For a shipping destination printed over several lines:

> Extract the complete shipping destination block directly under the "Ship To"
> label. The value may span multiple lines. Continue reading until the next
> labelled field or document section. Preserve every visible address line,
> including repeated city or region lines and the country, and join the lines
> with ", ". Do not substitute the Bill To customer or customer name.

When an adjacent field must contain a name only, use a separate and explicit
boundary rule:

> Extract only the person name directly beneath the "Bill To" label. Do not
> include any address, city, region, country, or values from the adjacent "Ship
> To" block. Stop after the name.

Do not copy literal names, addresses, invoice numbers, or other sample values
into production guidance. Describe the label, role, layout boundary, and value
shape instead. Keep the rule as short as the document permits; local models can
degrade unrelated fields when prompts become repetitive or contradictory. If a
field legitimately contains both a name and address and downstream systems need
them separately, prefer an **Object with defined fields** containing `name` and
`address` rather than forcing both into one scalar string.

The review form's `multiline: true` option only displays a larger editing box.
It does not make extraction capture additional lines. Configure extraction in
the GLM-OCR field guidance, and configure `multiline` separately in the matching
review form when operators need to inspect or edit a long value comfortably.

Treat every guidance change as model-affecting configuration. Keep a fixed
regression set that includes short values, long multiline values, repeated
city/region lines, adjacent labelled blocks, and documents where the optional
field is absent. A successful result from one PDF or one invocation is not
sufficient evidence for production use.

The current task supports at most 100 top-level fields, flat structured objects,
and one logical array-of-objects table. Documents requiring separate container,
cargo, and charges tables do not fit that schema in one extraction task. Keep
only the business-critical repeated section as the table and model other values
as supported scalar or flat-object fields, or reassess the task boundary before
production use.

Use an **Object with defined fields** when several values must come from the
same visual block. This is important for documents that contain multiple
organizations or addresses. For example, configure the insured or billed
customer as one `customer` object with `name` and `address` properties, while
keeping `insurance_company` as a separate scalar. The object tells GLM-OCR that
the customer name and address belong together; two independent scalar fields
can otherwise be selected from different parties on the page. Objects are flat:
their properties may be text, integer, number, or yes/no fields, but cannot
contain another object or list. The same technique can group a coverage
period's `start_date` and `end_date` when both must come from one labelled date
range rather than from unrelated issue or due dates elsewhere on the page.

The task renders pages locally in memory and makes schema-directed vision calls.
GLM-OCR first produces scalar/object candidates and table rows per page. In
`document` mode, the resolver then evaluates one scalar or flat object at a time
against bounded copies of all ordered page images; it reconciles a table from
bounded structured row-evidence chunks. This field isolation helps prevent a
prominent value from one page or party from replacing a differently labelled
role elsewhere in the document. Results are normalized under `context["data"]`,
persisted to SQLite with provider `glm_ocr_ollama`, and are available to every
downstream task. The task does not provide field confidence, citations, or
PP-DocLayout output. Confidence therefore remains null; no score is invented.

Prompt style does not select the resolution strategy. Every mode first makes one
scalar/object GLM call per page; a required null may cause one focused recovery
call, and a configured array-of-objects table adds one table call per page.
`page_merge` stops after deterministic page merging. `document` additionally
runs isolated resolver calls for configured scalars/objects and one or more
bounded evidence-resolution calls for the table. In compact mode the same JSON
Schema is still enforced through Ollama; it is simply not duplicated inside the
text prompt. Put precise, document-specific selection rules in
`document_instructions`, and avoid literal example values that a small model
could copy into its answer.

###### Prompt and schema-order sensitivity

GLM-OCR is a small local vision-language model and can be highly sensitive to
both prompt construction and JSON Schema property order. Do not assume that two
schemas containing the same fields are equivalent for model behaviour. Changing
the order of top-level fields or object properties can change which visual value
the model assigns to a field. Adding, removing, or renaming a field can also
change the effective order of the generated schema and affect unrelated values.

More instructions are not always better. A longer prompt, repeated schema
descriptions, or an additional rule for one field can distract the model and
degrade other fields that previously extracted correctly. Start with concise,
meaning-based instructions. Add only the disambiguation needed for the tested
document type, avoid repeating the same rule in several forms, and avoid literal
example values. Try `compact` prompt style when the detailed prompt is too long
or repeats information already enforced by Ollama's native schema parameter.
Use `verbatim` only when a concise prompt has been tested as a complete unit and
the compact framework wrapper itself changes model behaviour.

Treat field order, object grouping, prompt style, and document instructions as
model-affecting configuration. Before publishing a changed pipeline:

1. Set **Schema position** for every top-level field and structured child whose
   order matters, then inspect the YAML preview or exported definition to
   confirm the effective order. Positions must be positive and unique among
   siblings.
2. Change one variable at a time so that a regression can be attributed to a
   schema-order, field, object, or prompt change.
3. Test several representative PDFs for the document type using the same model
   tag, DPI, context size, and output-token limit as production.
4. Repeat important samples because a successful result from one invocation is
   not sufficient evidence that the configuration is stable.
5. Compare every extracted field with the source PDF, not only the field whose
   rule changed. Keep a known-good result as a regression baseline.
6. Publish the change as a new immutable pipeline version and retain a Review
   Gate when operators must verify local-model output. GLM-OCR supplies no field
   confidence, so the review workflow should treat all extracted values as
   requiring human confirmation.

Objects remain useful for keeping values from one visual block together, but
their child-property order must also be tested. If reordering fixes one field
while degrading another, restore the last known-good version and simplify the
prompt or schema in a separate draft instead of accumulating more instructions.

When a review gate follows GLM extraction, the task's structured unscored-output
flag makes every configured top-level field reviewable. Use document review
scope when the operator must inspect all scalar values and every line-item cell.
The queue displays missing confidence instead of a percentage. The operator
compares values with the PDF, corrects them, and completes review; resume then
reconstructs `context["data"]` from final SQLite values before CSV/JSON storage.
If no review gate is present, the flag is inert and the pipeline continues.

For portal ingestion, select the published GLM pipeline on **Upload & Process**.
For watch-folder ingestion, create an enabled binding to that exact published
version. Use a unique output filename such as `{id}`. CSV storage expands an
array-of-objects field to one row per item and repeats document-level scalar
values on each row.

```yaml
tasks:
  glm_extract:
    module: standard_step.extraction.glm_ocr_extract
    class: GlmOcrExtractTask
    params:
      ollama_host: http://127.0.0.1:11434
      model: glm-ocr:latest
      document_instructions: Extract only values visibly supported by the document.
      resolution_mode: document
      resolver_model: qwen3.5:9b-q4_K_M
      resolver_max_dimension: 1280
      resolver_num_ctx: 18000
      resolver_num_predict: 10000
      resolver_max_attempts: 2
      dpi: 216
      num_ctx: 8192
      num_predict: 2048
      timeout_seconds: 300
      fields:
        invoice_number: { alias: Invoice number, type: str }
        customer:
          alias: Customer
          type: Dict[str, Any]
          object_fields:
            name: { alias: Customer name, type: str }
            address: { alias: Customer address, type: str }
        note_type:
          alias: Note type
          type: str
          choices: [debit, credit]
        coverage_period:
          alias: Coverage period
          type: Dict[str, Any]
          object_fields:
            start_date:
              alias: Coverage start date
              type: str
              normalizer: iso_date
            end_date:
              alias: Coverage end date
              type: str
              normalizer: iso_date
        total: { alias: Total, type: float }
        line_items:
          alias: Line items
          type: List[Any]
          is_table: true
          item_fields:
            description: { alias: Description, type: str }
            quantity: { alias: Quantity, type: int }
            unit_price: { alias: Unit price, type: float }
pipeline:
  - glm_extract
```

##### LiteParse extraction (local Ollama)

Use `standard_step.extraction.liteparse_extract` / `LiteParseExtractTask` for
local text/layout parsing followed by configurable Ollama extraction. It reads
embedded text from generated PDFs and uses local OCR for scanned pages. The
default model is `qwen3.5:9b-q4_K_M`. Fields, flat objects and one optional table
are configurable for any document type. No cloud credentials are required.

Add this task visually in **Pipeline**, configure its fields, then add a
**Review Gate** with a matching published form version and **Store Metadata As
Json**. All extracted fields are unscored and sent for review when a gate follows.
Retained word boxes are diagnostic evidence, not verified approval highlights.
See [LiteParse task setup and limits](liteparse_extract_task.md) for parameters,
local dependencies, page selection and context/output limits.

LiteParse can offer faster processing through fewer Ollama calls: a normal
attempt uses one request for all selected pages, whereas GLM-OCR makes separate
page extraction calls and may add recovery or resolver calls. This advantage
applies when the complete input and output fit comfortably in one request;
actual speed also depends on OCR, model choice, document size, and memory.

For larger documents, prefer GLM-OCR when the complete parsed evidence or item
output cannot fit comfortably in LiteParse's single inference request. GLM-OCR
extracts pages separately and chunks table evidence during document resolution;
its scalar/object resolver still receives all page images, and rendering uses
memory for the whole PDF. This makes GLM-OCR better positioned for larger
documents, without proving better accuracy or speed. See the
[selection criteria and resolution-mode limits](liteparse_extract_task.md#choosing-liteparse-or-glm-ocr-for-larger-documents)
before choosing a pipeline, and validate representative documents with review.

Ollama must be running separately and the configured local model must already
be installed. The app does not start Ollama or download models. Each normal
attempt uses one inference; an automatic retry may make another call.
`keep_alive: 0` releases model memory after each request, so the next request
can include loading time. Large OCR inputs and a 32K context can exceed GPU
capacity; see the task guide before changing input or context limits.

The published **LiteParse Invoice Review JSON** pipeline was tested with three
Superstore and three FTS invoices. See the
[validation report](liteparse_pipeline_validation.md) for original extraction
accuracy separately from human-corrected exports and the sample limitations.

The registered PDF extraction choices are the existing LlamaCloud
`ExtractPdfTask`, local `GlmOcrExtractTask`, and local `LiteParseExtractTask`.
A pipeline may contain only one extraction task.

#### 4.8.2. split.llamacloud_split

- **type:** `"split.llamacloud_split"`
- **Purpose:** Optionally splits a source PDF into child PDF documents before downstream extraction and storage tasks run.
- **params:**
  - `enabled`: boolean. If `false`, the task records a skipped split result and the source document continues as a normal document.
  - `api_key`: required secret reference when the real LlamaCloud split adapter
    is used, for example `{ $secret: "llamacloud-primary" }`.
  - `configuration_id`: optional saved LlamaCloud split configuration ID.
  - `categories`: optional list of category definitions. Required when `configuration_id` is not provided.
  - `allow_uncategorized`: controls what LlamaCloud does with pages that do not match a configured category. The default is `"include"`; see the decision table below.
  - `fail_on_confidence_levels`: list of split confidence labels that cause the whole split task to fail before child documents are created. Default is `["low"]`.
  - `fail_on_unknown_category`: boolean. When `true`, blank, `other`, `uncategorized`, and disallowed category results fail the whole split task. Default is `true`.
  - `allowed_categories`: optional list of accepted category names. If omitted, inline `categories` are used as the allowed list.
  - `split_dir`: string, required. Destination for generated child PDFs. The
    task creates it when child PDFs are needed if the application account has
    the required filesystem permission. Whole-document continuation creates no
    split PDF.
  - `project_id` / `organization_id`: optional provider scoping values.
  - `poll_interval_seconds`: optional polling interval. Default is `1.0`.
  - `timeout_seconds`: optional timeout. Default is `7200.0`.
- **Behavior:**
  - Runs only for root/source documents; split child documents skip the split task.
  - Applies category/confidence policy and page validation before continuation or child creation.
  - When exactly one segment covers every source page once in source order,
    saves classification on the original document and continues at the next
    pipeline task, preserving its ID and PDF. Retries reuse a matching saved
    decision; review resume restores its classification.
  - Otherwise creates one child document record and one split PDF for each
    provider segment, including a single segment containing only some pages or
    changing page order.
  - Records split category, confidence, page range, and source metadata in SQLite.
  - When children are created, sets the parent/source document to
    `split_completed`, then child documents continue from the next pipeline task.
  - Fan-in recomputes the parent and batch status after child documents complete, fail, or enter review.
- **Ordering rules:**
  - Configure split before extraction, so child PDFs are extracted independently.
  - Configure the review gate after extraction, so it can evaluate extracted fields and confidence.

**Choosing how to handle unmatched pages:**

| Value | What LlamaCloud does | Effect in this application | When to use it |
|-------|----------------------|----------------------------|----------------|
| `"include"` | Returns unmatched pages in an `uncategorized` segment. | Pages are retained, but the default `fail_on_unknown_category: true` rejects that segment and fails the split before creating any children. | Use when retaining every page matters, after deciding whether uncategorized segments should fail or continue for review. |
| `"forbid"` | Forces every page into one of the defined categories. | No page is omitted, but a cover sheet, receipt, or other unexpected page may be assigned to the wrong category and processed as that document type. | Use only when the category list covers every page type you expect and has been tested with representative documents. |
| `"omit"` | Excludes unmatched pages from the split results. | Omitted pages do not become child documents and do not proceed to extraction, review, or export. | Use only when discarding unmatched pages is an explicit business decision. |

`"forbid"` does not mean “reject a document containing an unknown page.” For example, if `invoice` is the only category, every page must be labelled as an invoice even when a page is actually a cover sheet or supporting document.

Before enabling split processing for production documents:

1. Define categories in clear business language and include expected supporting pages.
2. Test all three policies with representative combined PDFs.
3. Decide whether low confidence or unknown categories should stop the whole source document.
4. Confirm in **Split Results** that every page that must be retained appears in a child document.
5. Configure the review gate to catch the split confidence levels that require an operator decision.

**Inline YAML configuration example:**

```yaml
tasks:
  split_documents:
    module: standard_step.split.llamacloud_split
    class: LlamaCloudSplitTask
    params:
      enabled: true
      api_key: { $secret: "llamacloud-primary" }
      categories:
        - name: "invoice"
          description: "Supplier invoice pages"
        - name: "supporting_document"
          description: "Delivery orders, receipts, or supporting pages"
      allow_uncategorized: "include"
      fail_on_confidence_levels:
        - "low"
      fail_on_unknown_category: true
      allowed_categories:
        - "invoice"
        - "supporting_document"
      split_dir: "data/app/split"
      poll_interval_seconds: 1.0
      timeout_seconds: 7200
    on_error: stop

pipeline:
  - split_documents
  - extract_document_data
  - store_metadata_json
```

For a saved LlamaCloud split configuration, set `configuration_id` instead of `categories` and `allow_uncategorized`. The confidence policy, allowed-category checks, output directory, and advanced provider settings remain local task behavior.

After fan-out, each child document is a **leaf document** because it is processed independently. Fan-in summarizes those child statuses for the source document and batch:

- **Processing** (`processing`): at least one child is still running.
- **Review required** (`review_required`): at least one child is waiting for or undergoing operator review.
- **Completed** (`completed`): every child completed successfully.
- **Completed with errors** (`completed_with_errors`): all children finished, with a mixture of successful and failed children.
- **Failed** (`failed`): every child failed.

#### 4.8.3. storage.store_metadata_as_csv

- **Current module/class:** `standard_step.storage.store_metadata_as_csv` / `StoreMetadataAsCsv`
- **Purpose:** Stores extracted metadata as CSV and expands a configured table field into one row per item.
- **params:**
  - `data_dir`: string (required). Destination folder for CSV.
  - `filename`: string (required). Base filename template; `.csv` is auto-added.
  - Advanced compatibility parameters may use nested `storage.data_dir` /
    `storage.filename`. Add a task-specific `extraction.fields` mapping when
    CSV aliases or explicit table metadata are required; the extraction task's
    mapping is not inherited by a published versioned storage task.
- **Behavior:**
  - Uses task-specific configured field aliases for column names when present;
    otherwise it uses workflow data keys.
  - In a published versioned pipeline, columns come from that version's
    extracted data (or an explicit task-specific `extraction.fields` mapping);
    deployment-level YAML field mappings are not inherited.
  - If one extraction field has `is_table: true`, writes one row per item and repeats the document-level values.
  - Prefixes item columns with `item_` and falls back to one row when no table data is present.
  - Sanitizes values and generates a unique filename to avoid overwrites.

**YAML configuration example:**

```yaml
tasks:
  store_metadata_csv:
    module: standard_step.storage.store_metadata_as_csv
    class: StoreMetadataAsCsv
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

pipeline:
  - store_metadata_csv
```

#### 4.8.4. storage.store_metadata_as_json

- **Current module/class:** `standard_step.storage.store_metadata_as_json` / `StoreMetadataAsJson`
- **Purpose:** Stores extracted metadata as JSON while preserving arrays of objects such as invoice line items.
- **params:**
  - `data_dir`: string (required). Destination folder for JSON.
  - `filename`: string (required). Base filename template; `.json` is auto-added.
  - Optional task-specific `extraction.fields`: mapping used only when this JSON
    task should emit aliases or retain explicit table metadata. It is not
    inherited from another pipeline or deployment YAML.
- **Behavior:**
  - Reads `context["data"]` (dict).
  - Writes a JSON file with keys transformed to aliases when a task-specific
    `extraction.fields` mapping is configured.
  - In a published versioned pipeline, deployment-level YAML extraction fields
    are not inherited. Without a task-specific mapping, it writes the exact
    workflow data keys produced by that pipeline version, preventing unrelated
    columns or aliases from another workflow from leaking into the export.
  - Generates a unique filename to avoid overwrites.

**YAML configuration example:**

```yaml
tasks:
  store_metadata_json:
    module: standard_step.storage.store_metadata_as_json
    class: StoreMetadataAsJson
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

pipeline:
  - store_metadata_json
```

These canonical CSV and JSON classes support both scalar fields and one configured array-of-objects table field.

#### 4.8.5. storage.store_file_to_localdrive

- **type:** `"storage.store_file_to_localdrive"`
- **Purpose:** Stores processed PDF files with descriptive filenames based on extracted data.
- **params:**
  - `files_dir`: string (required). Destination for processed PDFs.
  - `filename`: string (required). Template for filename; `.pdf` is auto-added.
    - Placeholders: extracted field keys (e.g., `{company}`, `{name}`) and context variables `{id}`, `{original_filename}`, `{timestamp}`.
- **Behavior:**
  - Copies the original PDF from processing into `files_dir` with a unique filename derived from `filename`.
  - Missing keys in the template raise a configuration error.

**YAML configuration example:**

```yaml
tasks:
  store_file_to_localdrive:
    module: standard_step.storage.store_file_to_localdrive
    class: StoreFileToLocaldrive
    params:
      files_dir: "files"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

pipeline:
  - store_file_to_localdrive
```

#### 4.8.6. archiver.archive_pdf

- **type:** `"archiver.archive_pdf"`
- **Purpose:** Archives the original input PDF to a designated archive directory with a sanitized, unique filename.
- **params:**
  - `archive_dir`: string (required). Destination folder for archived PDFs.
- **Behavior:**
  - Copies the original PDF from the processing directory to the archive directory.
  - Creates a unique filename to avoid overwrites using the original filename as a base.
  - Preserves file metadata during the copy operation.

**YAML configuration example:**

```yaml
tasks:
  archive_pdf:
    module: standard_step.archiver.archive_pdf
    class: ArchivePdfTask
    params:
      archive_dir: "archive_folder"
    on_error: continue

pipeline:
  - archive_pdf
```

#### 4.8.7. rules.update_reference

- **type:** `"rules.update_reference"`
- **Purpose:** Update a reference CSV file using extracted data.
- **params:**
  - `reference_file`: string (required). Path to the CSV file to update.
  - `update_field`: string (required). The name of the column to write the `write_value` into.
  - `write_value`: string (required). The value to write into the `update_field` for matched rows.
  - `backup`: boolean (optional). If `true`, creates a `.backup` file before writing (default `true`).
  - `csv_match`: dictionary (required). Defines the matching criteria:
    - `type`: string, must be `"column_equals_all"`.
    - `clauses`: list of 1 to 5 dictionaries, each defining a comparison:
      - `column`: string (required). The CSV column name to compare.
      - `from_context`: string (required). A field path to resolve the comparison value from the pipeline context (e.g., `"invoice_number"`).
      - `number`: boolean (optional). If `true`, forces numeric comparison; if `false`, forces string comparison; if `null` or omitted, auto-detects based on context value.
- **Behavior:**
  - Loads the configured CSV file.
  - Updates matching rows only; it does not append new rows.
  - Creates the configured `update_field` column at runtime if it is missing from the loaded CSV.
  - Saves the CSV, creating a backup if enabled.
- **Notes:**
  - Use workflow field keys in `from_context` (for example, `purchase_order_number`). Use CSV `column` names to match the external reference file headers.
  - If a field value is not found in context (e.g., missing purchase_order_number), the task does not throw an error but simply does not match any rows, logging the issue and continuing with on_error: continue.

**YAML configuration example:**

```yaml
tasks:
  update_reference:
    module: standard_step.rules.update_reference
    class: UpdateReferenceTask
    params:
      reference_file: "reference_file/reference_file.csv"
      update_field: "MATCHED"
      write_value: "match_all"
      backup: true
      csv_match:
        type: "column_equals_all"
        clauses: # List of 1 to 5 clauses for matching
          - column: "P/O NO."
            from_context: "purchase_order_number"
            number: false
          - column: "AMOUNT"
            from_context: "invoice_amount"
            number: true
    on_error: continue

pipeline:
  - update_reference
```

> **Migration Note:** Update Reference Configuration Update: Bare field names (e.g., 'purchase_order_number') are now preferred over dotted paths (e.g., 'data.purchase_order_number'). The dotted format is still supported for backward compatibility but will be deprecated in future releases. Deprecation warnings are logged when the old format is used.

#### 4.8.8. review.review_gate

- **type:** `"review.review_gate"`
- **Purpose:** Pauses a document for operator review when extracted fields or configured policies indicate human review is required.
- **params:**
  - `confidence_threshold`: float from `0.0` to `1.0`. Default is `0.8`; use `0.9` for a 90% review threshold.
  - `per_document_type_thresholds`: optional map of document type or split category to threshold.
  - `field_threshold_overrides`: optional map of field key to threshold.
  - `split_confidence_levels_requiring_review`: optional list of split confidence labels such as `high`, `medium`, or `low` that should force review.
  - `require_review_when_missing_confidence`: boolean. Default is `true`. When `schema_file` is configured, missing-confidence review gating applies to fields marked `required: true` in the schema and to fields explicitly listed in `field_threshold_overrides`; optional schema fields do not force review solely because confidence is missing.
  - `require_review_for_missing_required_fields`: boolean. Default is `true` when schema validation is used.
  - `always_review`: boolean. If `true`, every document entering this task requires review.
  - `schema_version_id`: exact published review-schema version selected in the
    pipeline editor. The runtime injects its immutable definition into the
    task. The task never reloads a schema draft, newest version, or filesystem
    file.
  - `schema_file`: accepted only by legacy YAML/file migration and validation
    surfaces. Import it into a review-schema draft, publish the schema, and
    select the resulting exact version before production use.
  - `queue_name`: review queue name. Defaults to `review.default_queue_name` or `default_review`.
  - `review_scope`: controls the reviewer editing scope. Use `"document"` or `"low_confidence_fields"`; it does not decide which review conditions trigger the gate.
  - `allow_operator_to_edit_high_confidence_fields`: boolean. Default is `true`.
  - `resume_policy`: fixed to `"next_task"`; the Pipeline editor does not expose it as a choice.
- **Behavior:**
  - Evaluates persisted extracted fields, confidence values, missing-confidence conditions for mandatory schema fields, schema errors, split confidence, and business rule flags.
  - For object, scalar-array, and object-array fields, the persisted field confidence uses the minimum numeric nested confidence returned by LlamaCloud Extract. For example, an invoice `items` field is gated by the lowest line-item cell confidence.
  - Marks fields requiring review and creates a review queue item in SQLite when review is required.
  - Sets document state to `review_required` and pauses the workflow.
  - Operators use **Review Queue** to claim an item, save draft corrections, preview changes, and complete review.
  - Completed corrections are persisted in SQLite and the document resumes downstream workflow steps according to `resume_policy`.
- **Locking:** Review claims use `review.lock_timeout_minutes`, defaulting to 60 minutes. Claims are atomic: the current operator can renew a claim, another operator can take over an expired claim, and an active claim cannot be overwritten.

For schema-driven review field types, validation behavior, and LlamaCloud date-format guidance, see the [review schema administrator guide](review_schema_admin_guide.md).

**YAML configuration example:**

```yaml
tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: { $secret: "llamacloud-primary" }
      fields:
        supplier_name: { alias: "Supplier name", type: "str" }
        invoice_amount: { alias: "Invoice Amount", type: "float" }
    on_error: stop

  review_gate:
    module: standard_step.review.review_gate
    class: ReviewGateTask
    params:
      confidence_threshold: 0.90
      queue_name: "default_review"
      review_scope: "low_confidence_fields"
      require_review_when_missing_confidence: true
      require_review_for_missing_required_fields: true
      always_review: false
      resume_policy: "next_task"
    on_error: stop

  store_metadata_json:
    module: standard_step.storage.store_metadata_as_json
    class: StoreMetadataAsJson
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}"
    on_error: continue

pipeline:
  - extract_document_data
  - review_gate
  - store_metadata_json
```

#### 4.8.9. Assign Nanoid (standard_step/context)

- **type:** `"context.assign_nanoid"`
- **Purpose:** Assigns a short, URL-safe unique identifier to the shared task context for downstream use in filename construction (e.g., `{nanoid}_{purchase_order_number}_{supplier_name}`).
- **params:**
  - `length`: int (optional). Desired ID length. Valid range is 5–21. Default is 10.
- **Behavior:**
  - Generates a secure, URL-friendly ID using the Python `nanoid` package.
  - Validates `length` is an integer within 5–21; initialization fails with a configuration error otherwise.
  - Writes the generated ID to `context["data"]["nanoid"]`.
  - Downstream tasks can reference `{nanoid}` in their filename/rename templates.

**YAML configuration example:**
```yaml
tasks:
  assign_nanoid:
    module: standard_step.context.assign_nanoid
    class: AssignNanoidTask
    params:
      length: 10
    on_error: stop

pipeline:
  - extract_document_data
  - assign_nanoid
  - store_metadata_json
  - store_file_to_localdrive
```

**Usage notes and migration:**

- Update existing filename templates to include `{nanoid}` where a short unique prefix is desired; for example:
  - `{nanoid}_{purchase_order_number}_{supplier_name}`
- This change ensures filenames are unique and traceable while remaining short.

#### 4.8.10. housekeeping.cleanup

- **Current module/class:** `standard_step.housekeeping.cleanup_task` / `CleanupTask`
- **type:** `"housekeeping.cleanup"`
- **Purpose:** Performs final cleanup after workflow execution by deleting the processed PDF from the processing directory so the folder does not accumulate UUID-named files.
- **params:**
  - `processing_dir`: string (optional). Directory containing processed files. Defaults to "processing".
- **Behavior:**
  - Deletes the processed file referenced in the context if it exists in `processing_dir`.
  - Logs successes and warnings for missing files and preserves registered business artifacts.
  - Raises exceptions on critical delete failures.
  - Executes after configured tasks finish or stop on an ordinary failure. Review pause and split fan-out return before cleanup.
  - Records a completed or failed internal task run under the reserved `cleanup_task` key without changing the document's configured pipeline cursor.
- **Notes:**
  - This task is automatically invoked by the WorkflowLoader when a flow reaches its cleanup phase.
  - It does not require definition in the portable `tasks` registry or
    inclusion in the `pipeline` list.
  - Ensures the processing directory remains clean by removing only the processed PDF.

#### 4.8.11. Validation and Failure Behavior

- The administrator Pipeline editor validates drafts before publication:
  - Each draft/version may contain at most one split task, one extraction task,
    and one review-gate task.
  - Extract tasks support at most one table field. A field is a table when `is_table: true` or its type is `List[Any]`, including the optional form.
  - Task parameter constraints, including the Nanoid length range of 5-21, are blocking findings.
  - Publish performs server-side validation again and atomically creates the
    next immutable SQLite version. A rejected publish creates no version and
    leaves the draft unchanged.
- Config validation happens at startup via the `ConfigManager`:
  - Validates that `web.upload_dir` exists and is a directory.
  - Validates that `watch_folder.dir` exists and is a directory; if missing/invalid, logs CRITICAL and exits. This path is NOT auto-created.
  - Pre-creates directories for deployment YAML keys ending with `_dir` when
    possible, excluding `watch_folder.dir`. SQLite task output paths are
    validated with the draft and created by their standard task at execution.
  - Validates all `_dir` paths exist and are directories; all `_file` paths exist and are files; exits on critical failure.
- At runtime, tasks validate their own required parameters.
- On validation failure or error:
  - The system logs the error.
  - Task-run and document state are updated in SQLite when document context exists; pipeline flow may continue or stop per each task’s `on_error`.
- **Tip:** Set `logging.log_level = DEBUG` in `config.yaml` for detailed diagnostics.

### 4.9. LlamaCloud Extract v2 Structured Data Support

#### 4.9.1. Flat objects

Use `Dict[str, Any]` with `object_fields` when one extracted field contains a
fixed object whose properties have different primitive types. The Pipeline
properties editor exposes this as **Object with defined fields**.

```yaml
summary:
  alias: "Summary"
  type: "Dict[str, Any]"
  object_fields:
    customer_name:
      alias: "Customer name"
      type: "str"
    invoice_count:
      alias: "Invoice count"
      type: "int"
    total_amount:
      alias: "Total amount"
      type: "float"
    approved:
      alias: "Approved"
      type: "bool"
    notes:
      alias: "Notes"
      type: "Optional[str]"
```

`object_fields` is intentionally flat. Its properties support text, integer,
number, and yes/no values; nested objects and lists are not supported. The
normalized workflow context uses the configured stable property keys.

Review schemas are configured separately. To display the same value in the
review gate, define a matching review field with `type: object` and matching
keys under `properties`.

#### 4.9.2. Scalar lists

The Pipeline properties editor supports lists containing one primitive value
type. Use the corresponding extraction type:

| Editor option | Extraction type | Review schema item type |
| --- | --- | --- |
| List of text | `List[str]` | `string` |
| List of integers | `List[int]` | `integer` |
| List of numbers | `List[float]` | `number` |
| List of yes/no | `List[bool]` | `boolean` |

For human review, configure the matching field as `type: array` and set
`items.type` to the review-schema item type shown above. Extraction and review
schemas remain separate configurations, so their field keys and item types
must stay aligned.

#### 4.9.3. Arrays of objects

The canonical extraction and storage tasks handle LlamaCloud Extract v2 responses containing arrays of objects, such as invoice line items or multiple entries that need to be processed individually.

##### Overview

The canonical tasks allow extraction of structured data where certain fields return lists of sub-objects. For example, an invoice might have an "Items" field containing multiple line items with descriptions, quantities, and prices.

##### Configuration

To configure array-of-objects extraction, edit a pipeline draft visually or
import a portable definition containing the following task parameters:

1. Use the canonical extraction task:
   ```yaml
   extract_document_data:
     module: standard_step.extraction.extract_pdf
     class: ExtractPdfTask
     params:
       api_key: { $secret: "llamacloud-primary" }
       configuration_id: "YOUR-EXTRACT-V2-CONFIGURATION-ID"
       project_id: "YOUR-PROJECT-ID"  # optional advanced scope
       organization_id: "YOUR-ORGANIZATION-ID"  # optional advanced scope
       poll_interval_seconds: 2       # optional
       timeout_seconds: 1800          # optional
   ```

   The current runtime uses the `llama-cloud` SDK and `LlamaCloud` client. New configurations should use `configuration_id` or inline `fields`; `agent_id` is legacy.

2. Mark array fields with `is_table: true`:
   ```yaml
   items:
     alias: "Items"
     type: "List[Any]"
     is_table: true
     item_fields:
       Description:
         alias: "description"
         type: "str"
       Quantity:
         alias: "quantity"
         type: "str"
   ```

##### Storage Behavior

Storage remains isolated to the selected pipeline version. Add a task-specific
`extraction.fields` mapping to the CSV/JSON task when aliases or explicit table
metadata are required.

##### Confidence Persistence

- Scalar fields persist the provider's numeric confidence when available.
- Object, scalar-array, and object-array fields persist an aggregate confidence using the minimum nested numeric confidence.
- Nested confidence details are stored under each field's existing `source_json.confidence_details` payload, including per-cell paths such as `0.itemName` or `0.quantity`.
- No database migration is required; the existing `extracted_fields.confidence` and `source_json` columns are used.
- This behavior applies to new extraction runs only. Existing completed extraction/review records are not rewritten automatically.

##### JSON Storage

- Preserves the list-of-objects structure for table fields.
- Task-specific configured fields are written under their aliases when present;
  otherwise workflow field keys are preserved.
- Maintains backward compatibility with scalar-only data.

##### CSV Storage

- **Row-per-item mode**: Creates one CSV row for each item in the array, repeating invoice-level fields.
- **Column naming**: Scalar and item columns use task-specific configured
  aliases when present. Item columns are prefixed with `item_` (e.g.,
  `item_description`, `item_quantity`).
- **Fallback**: If no table field is configured or the list is empty, falls back to single-row format.
- **Example CSV output**:
  ```csv
  supplier_name,invoice_amount,item_description,item_quantity
  ALLIGATOR SINGAPORE PTE LTD,44.62,ELECTRODE G-300 3.2MM 5KG,4.0 PKT
  ALLIGATOR SINGAPORE PTE LTD,44.62,QUICK COUPLER SOCKET,2.0 PCS
  ```

#### 4.9.4. Migration Guide

To use the canonical array-of-objects tasks:

1. Configure the canonical extraction task:
   ```yaml
   module: standard_step.extraction.extract_pdf
   class: ExtractPdfTask
   ```

2. Add `is_table: true` to array fields in your extraction configuration.

3. Configure the canonical storage tasks:
   ```yaml
   # JSON
   module: standard_step.storage.store_metadata_as_json
   class: StoreMetadataAsJson

   # CSV
   module: standard_step.storage.store_metadata_as_csv
   class: StoreMetadataAsCsv
   ```

4. After the LlamaCloud UI configuration is ready, test with a small set of documents before full deployment.

5. Validate a saved LlamaCloud configuration with the manual smoke checker.
   The script reads a YAML task definition; it does not load SQLite or resolve
   `pipeline_secrets`. Export/copy the selected pipeline definition to an
   ignored local smoke-input file and supply the credential through the current
   PowerShell process:

   ```powershell
   $env:LLAMA_CLOUD_API_KEY = "set-locally"
   .\.venv\Scripts\python.exe tools\llamacloud_extract_smoke.py --config smoke-pipeline.yaml --file sample_invoice.pdf --configuration-id "cfg-..."
   ```

   If `configuration_id` is already in the task definition, omit the override.
   Use `--raw-json path\to\result.json` for an offline fit check without a cloud
   call. The checker writes `raw_extract_result.json`,
   `workflow_normalized_data.json`, and `workflow_fit_report.json` under its
   output directory. Do not commit those files or the smoke input.

#### 4.9.5. Current Limitations

- Only one `is_table: true` field is supported per extraction.
- `object_fields` supports flat primitive properties only; nested objects and lists are not supported.
- Items must be simple dictionaries (no nested arrays or objects).
- Complex nested structures may require additional processing logic.

---

### 4.10. Example Workflows

The deployment file and the portable pipeline definition are separate. A
minimal deployment excerpt can contain the shared runtime settings and a local
secret alias:

> **Important:** the task YAML later in this section is a portable pipeline
> definition, not a complete runtime `config.yaml`. Do not paste the
> `tasks:`/`pipeline:` block into a newly created deployment file.

```yaml
# Top-level configuration keys (abbreviated for example)
web:
  host: "0.0.0.0"
  port: 8000
  secret_key: "your_secret_key"
  upload_dir: "web_upload"
  cors_allowed_origins: []

watch_folder:
  dir: "watch_folder"
  validate_pdf_header: true
  processing_dir: "processing"

logging:
  log_file: "app.log"
  log_level: "INFO"

pipeline_secrets:
  llamacloud-primary: "SET-THIS-ONLY-IN-THE-LOCAL-IGNORED-CONFIG"
```

Use a long, random, deployment-specific value for `web.secret_key`; do not
reuse it across environments. Changing it invalidates existing browser tokens
and requires users to sign in again. Setting `web.host` to `0.0.0.0` exposes
the service on all network interfaces. Use that value only when remote access
is intentional and firewall, TLS, reverse-proxy, and access-control measures
are in place; use `127.0.0.1` for local-only operation.

Never commit or export the resolved value under `pipeline_secrets`. The
portable definition stores only its alias:

```yaml
schema_version: 1

# Tasks registry: name -> module/class/params
tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: { $secret: "llamacloud-primary" }
      tier: "agentic"
      extraction_target: "per_doc"
      fields:
        supplier_name:        { alias: "Supplier name",       type: "str" }
        client_name:          { alias: "Client name",         type: "str" }
        client_address:       { alias: "Client",              type: "str" }
        purchase_order_number: { alias: "Purchase order",     type: "str" }
        invoice_amount:       { alias: "Invoice amount",      type: "float" }
        insurance_start_date: { alias: "Insurance Start Date",type: "str" }
        insurance_end_date:   { alias: "Insurance End Date",  type: "str" }
        policy_number:        { alias: "Policy Number",       type: "str" }
        serial_numbers:       { alias: "Serial Numbers",      type: "Optional[List[str]]" }
        invoice_type:         { alias: "Invoice type",        type: "str" }
    on_error: stop

  update_reference:
    module: standard_step.rules.update_reference
    class: UpdateReferenceTask
    params:
      reference_file: "reference_file/reference_file.csv"
      update_field: "MATCHED"
      write_value: "match_all"
      backup: true
      csv_match:
        type: "column_equals_all"
        clauses:
          - column: "P/O NO."
            from_context: "purchase_order_number"
            number: false
          - column: "AMOUNT"
            from_context: "invoice_amount"
            number: true
    on_error: continue

  assign_nanoid:
    module: standard_step.context.assign_nanoid
    class: AssignNanoidTask
    params:
      length: 10
    on_error: stop

  store_metadata_csv:
    module: standard_step.storage.store_metadata_as_csv
    class: StoreMetadataAsCsv
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

  store_metadata_json:
    module: standard_step.storage.store_metadata_as_json
    class: StoreMetadataAsJson
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

  store_file_to_localdrive:
    module: standard_step.storage.store_file_to_localdrive
    class: StoreFileToLocaldrive
    params:
      files_dir: "files"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

  archive_pdf:
    module: standard_step.archiver.archive_pdf
    class: ArchivePdfTask
    params:
      archive_dir: "archive_folder"
    on_error: continue

# Ordered pipeline: executes tasks by name
pipeline:
  - extract_document_data
  - update_reference
  - assign_nanoid
  - store_metadata_csv
  - store_metadata_json
  - store_file_to_localdrive
  - archive_pdf
```

Housekeeping runs automatically after configured execution completes or stops on an ordinary task failure to remove the processed PDF from the processing directory. It is not included in the `tasks` registry or `pipeline` list. The operation is recorded in SQLite as an internally managed task run with the reserved key `cleanup_task` and an index immediately after the configured pipeline.

Notes:
- The pipeline is an ordered list of task names defined under `tasks:`.
- Housekeeping is invoked directly by the WorkflowLoader. It deletes temporary processing-folder PDFs while preserving registered business artifacts and does not move the document's configured pipeline cursor.
- Review pause and split fan-out return before housekeeping. Cleanup runs when resumed work or each split child's configured work finishes.
- Each task references a Python module and class from the `standard_step` package and receives `params`.
- Customer custom task modules can be used only after deployment approval in `custom_steps.registry`, and custom modules must use the `custom_step.` prefix.
- The three storage-related tasks are separate:
  - `store_metadata_csv` writes CSV to `data_dir` using `filename` template.
  - `store_metadata_json` writes JSON to `data_dir` using `filename` template.
  - `store_file_to_localdrive` copies the processed PDF to `files_dir` using `filename`; housekeeping later removes the temporary processing copy.
- Field placeholders in `filename` come from extracted data keys (e.g., `{supplier_name}`, `{invoice_amount}`, `{policy_number}`).
- Keep filename templates short and Windows-safe. Avoid path separators and
  invalid filename characters such as `\\ / : * ? " < > |`; also account for
  missing fields, long extracted values, and duplicate output names. Test the
  rendered filename with representative documents before production use.
- Use `on_error: stop|continue` per task to control failure behavior.

Example custom task approval block:

```yaml
custom_steps:
  enabled: true
  registry:
    customer_validation:
      module: custom_step.customer_validation
      class: CustomerValidationTask
```

The `module` and `class` values stay in the portable/SQLite pipeline definition.
The deployment registry only approves which custom task classes may be
imported; it does not add a task to a pipeline.

### 4.11. Housekeeping and the Processing Folder

- The `processing_dir` contains temporary working files during processing. Workflow state is stored in SQLite.
- The workflow attempts the housekeeping cleanup task after the configured pipeline, including after ordinary task failures. It deletes the processed PDF from `processing_dir` and does not remove durable registered artifacts.
- An interrupted process or cleanup error can leave a working file behind. Check document state and logs before removing it manually.
- Any old text status files are legacy diagnostics only and are not required for current workflow state.

---

### 4.12. Config Check Validation Tool

**Audience:** Administrators. Operators should contact an administrator when configuration changes are required.

The `config-check` utility lives under `tools/config_check`. It validates
deployment YAML, reads SQLite drafts/versions and bindings without modifying
them, and validates portable pipeline or review-schema files before import.

**Core workflow**

- Use `C:\Windows\System32\cmd.exe` or PowerShell from the project root.
- Execute `.\.venv\Scripts\python.exe -m tools.config_check validate --config config.yaml --base-dir .` to validate deployment settings and the database-backed default selection.
- Add `--pipeline KEY` or `--review-schema KEY`, with `--draft` or `--version N`,
  for a stored definition. Use `--all-stored` for all drafts, versions, and
  bindings.
- Execute `.\.venv\Scripts\python.exe -m tools.config_check validate-file
  --file path\to\bundle.yaml --kind pipeline` for a portable definition.
- Use `--kind review-schema` instead when validating a portable review-form
  definition.
- Files left under `schemas/` are migration/import sources, not live workflow
  authority. A warning about filesystem schema files means they should be
  imported, published, and pinned from SQLite before the directory is retired;
  it is not evidence that a published review form is missing.
- Database access is read-only. Exit codes are `0` clean, `1` errors, `2`
  warnings only, and `64` command usage problems.
- Pass `--format json` when you need machine-readable output for ticket attachments or CI logs.
- Treat exit code `0` as success, `1` as blocking errors, and `2` as warnings that still need follow-up.

**When to escalate**

- Review `tools/config_check/README.md` for CLI flag details and examples.
- Cross-reference `docs/config_check_troubleshooting.md` to resolve the common findings (credential gaps, storage overrides, token mismatches, and similar issues).
- If operators report workflow failures, run the validator before restarting production work; many configuration problems can be found without rerunning documents.

Operators do not need to run this tool. Administrators should share only the part of a validation report needed to request missing information or explain an action.

### Technical Page Reference

Normal users should navigate with the left menu. The paths below are provided for administrators, support staff, bookmarks, and troubleshooting.

| Interface area | Path | Access | How to navigate to this area |
|----------------|------|--------|------------------------------|
| Upload & Process | `/app/upload` | Operator and administrator | Select **Upload & Process** from the left navigation menu. |
| Processing Overview | `/app/processing` | Operator and administrator | Start an upload from **Upload & Process**; its processing page opens automatically. To view other processing activity, select **Reports**, then **Open processing dashboard**. |
| Batch details | `/app/batches/{batch_id}` | Operator and administrator | Select **Reports**, choose a batch under **Recent Batches**, then select **Open processing dashboard** in the batch details window. |
| Split results | `/app/batches/{batch_id}/split-results` | Operator and administrator | Open the batch's **Processing Overview**, then select **View Split Results**. |
| Extraction results | `/app/documents/{document_id}/extraction` | Operator and administrator | Open **Processing Overview** and select **Extraction** beside the document. For a split PDF, open **Split Results** and select **Extraction** beside a child document. |
| Review Queue | `/app/review` | Operator and administrator | Select **Review Queue** from the left navigation menu. |
| Review item | `/app/review/{review_item_id}` | Operator and administrator | Select **Review Queue**, find the document, then select **Claim** or **View**. |
| Failures | `/app/failures` | Operator and administrator | Select **Failures** from the left navigation menu. |
| Reports | `/app/reports` | Operator and administrator | Select **Reports** from the left navigation menu. |
| Overview | `/app/admin` | Administrator only | Sign in as the administrator, then select **Overview** from the left navigation menu. |
| Users | `/app/admin/users` | Administrator only | Sign in as the administrator, then select **Users** from the left navigation menu. |
| Pipeline | `/app/admin/pipeline` | Administrator only | Select **Pipeline** to manage templates and publications. |
| Watch folders | `/app/admin/watch-folders` | Administrator only | Select **Watch folders** to manage routing, lifecycle, health, and history. |
| Review Forms | `/app/schemas` | Administrator only | Sign in as the administrator, then select **Review Forms** from the left navigation menu. |
| Review form draft | `/app/schemas/{schema_name}` | Administrator only | Select a form in **Review Forms**; this is the bookmarkable editor view for that stable key. |
| Task Catalog | `/app/admin/tasks` | Administrator only | Sign in as the administrator, then select **Task Catalog** from the left navigation menu. |
| Validation | `/app/settings/validation` | Administrator only | Sign in as the administrator, then select **Validation** from the left navigation menu. |
| Audit Log | `/app/admin/audit` | Administrator only | Sign in as the administrator, then select **Audit Log** from the left navigation menu. |

The `/api/files` and `/api/status/{file_id}` endpoints are retained only for compatibility and are not the primary operator interface. Their Singapore-time fields treat timestamps without an offset as UTC and preserve explicit source offsets before displaying GMT+8.

The old `/app/admin/review-gate` and `/app/admin/split` addresses redirect to
**Pipeline**. Review and split settings now belong to their corresponding task
cards in a versioned pipeline draft; they are not separate administrator pages.

### Example Configuration Files

See section 4.3.1 for deployment YAML and sections 4.8-4.10 for portable
pipeline definitions. Keep those two scopes separate. Adjust local paths and
secret aliases for the environment, and never copy resolved credentials into a
portable file.

