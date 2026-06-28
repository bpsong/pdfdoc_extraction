<!--
PDF Processing System: User Guide (Configurable Tasks Edition)
Version: 2.8
Release Date: 2026-06-28
Author: [Your Organization/Name]
-->

# PDF Processing System: User Guide (Configurable Tasks Edition)

---
Version: 2.8
Release Date: 2026-06-28
Author: [Your Organization/Name]

---

## Table of Contents

- [History of Changes](#history-of-changes)
- [Quick Start Guide](#quick-start-guide)
- [1. Overview](#1-overview)
- [2. System Architecture & Data Flow](#2-system-architecture--data-flow)
- [3. Operator Guide](#3-operator-guide)
  - [3.1. Using the Watch Folder](#31-using-the-watch-folder)
  - [3.2. Using the Web Interface](#32-using-the-web-interface)
  - [3.3. Operator Workflows in the Unified App](#33-operator-workflows-in-the-unified-app)
- [4. Administrator Guide](#4-administrator-guide)
  - [4.1. Starting and Stopping Services](#41-starting-and-stopping-services)
  - [4.2. Required Folders and Permissions](#42-required-folders-and-permissions)
  - [4.3. Configuration Management](#43-configuration-management)
    - [4.3.1. High-level Structure](#431-high-level-structure)
    - [4.3.2. Global Sections](#432-global-sections)
    - [4.3.3. Pipeline Configuration](#433-pipeline-configuration)
  - [4.4. Managing Application Accounts and Passwords](#44-managing-application-accounts-and-passwords)
  - [4.5. Database, State, and Artifact Storage](#45-database-state-and-artifact-storage)
  - [4.6. Log Files and Troubleshooting](#46-log-files-and-troubleshooting)
  - [4.7. Graceful Shutdown and Error Recovery](#47-graceful-shutdown-and-error-recovery)
  - [4.8. Task System: Standard Steps and Parameters](#48-task-system-standard-steps-and-parameters)
       - [4.8.1. extraction](#481-extraction)
       - [4.8.2. split.llamacloud_split](#482-splitllamacloud_split)
       - [4.8.3. storage.store_metadata_as_csv](#483-storagestore_metadata_as_csv)
       - [4.8.4. storage.store_metadata_as_json](#484-storagestore_metadata_as_json)
       - [4.8.5. storage.store_file_to_localdrive](#485-storagestore_file_to_localdrive)
       - [4.8.6. archiver.archive_pdf](#486-archiverarchive_pdf)
       - [4.8.7. rules.update_reference](#487-rulesupdate_reference)
       - [4.8.8. review.review_gate](#488-reviewreview_gate)
       - [4.8.9. Assign Nanoid (standard_step/context)](#489-assign-nanoid-standard_stepcontext)
       - [4.8.10. housekeeping.cleanup](#4810-housekeepingcleanup)
       - [4.8.11. Validation and Failure Behavior](#4811-validation-and-failure-behavior)
  - [4.9. LlamaCloud Extract v2 Structured Data Support](#49-llamacloud-extract-v2-structured-data-support)
  - [4.10. Example Workflows](#410-example-workflows)
  - [4.11. Housekeeping and the Processing Folder](#411-housekeeping-and-the-processing-folder)
  - [4.12. Config Check Validation Tool](#412-config-check-validation-tool)
- [5. Frequently Asked Questions (FAQ)](#5-frequently-asked-questions-faq)
- [6. Appendix](#6-appendix)
  - [Glossary](#glossary)
  - [Technical Page Reference](#technical-page-reference)
  - [Example Configuration Files](#example-configuration-files)
  - [Further Documentation](#further-documentation)

---

## History of Changes

| Version | Date       | Author              | Description                                                                 |
|---------|------------|---------------------|-----------------------------------------------------------------------------|
| 1.0     | 2025-04-13 | [Your Organization] | Initial user guide for fixed pipeline system                                |
| 2.0     | 2025-08-01 | [Your Organization] | Redesigned to configurable task-based workflows via `config.yaml`; web TBD    |
| 2.1     | 2025-08-01 | [Your Organization] | Added Quick Start guide, simplified explanations, expanded glossary, and improved configuration editing instructions for non-developers |
| 2.2     | 2025-08-01 | [Your Organization] | Added YAML configuration examples to all 4.7.x subsections for clarity      |
| 2.3     | 2025-08-11 | [Your Organization] | Implemented and documented web interface for PDF upload and status monitoring|
| 2.4     | 2025-08-20 | [Your Organization] | Added config-check administrator overview and cross-references to validation docs |
| 2.5     | 2026-06-03 | [Your Organization] | Updated for the unified operator and administrator interface, SQLite-backed workflow state, review, split, reports, settings, artifact registration, and legacy status endpoint compatibility |
| 2.6     | 2026-06-20 | [Your Organization] | Updated role guidance, UI-led operator procedures, account recovery, failure handling, split policy explanations, v2 task examples, upload limits, and recovery guidance |
| 2.7     | 2026-06-21 | [Your Organization] | Consolidated extraction and metadata storage under canonical module and class names while retaining Extract v2 array-of-objects behavior |
| 2.8     | 2026-06-28 | [Your Organization] | Added typed scalar-list options and flat structured-object extraction with Pipeline editor, validation, review-schema mapping, and operator documentation |

---

## Quick Start Guide

This quick start separates administrator setup from normal operator work.

**Administrator: first-time setup**

1. Create the folders configured by `watch_folder.dir` and `web.upload_dir`. Both must already exist and allow the application account to read and write files.
2. Initialize the fixed administrator and operator accounts:

    ```powershell
    C:\Python313\python.exe tools\setup_users.py --config config.yaml
    ```

3. Start the system from the project folder:

    ```
    C:\Python313\python.exe main.py
    ```

4. Open the configured web address and test both accounts.
5. Run the Config Check tool described in section 4.12 before processing production documents.

**Operator: process documents**

1. Open the web address provided by your administrator and sign in with the operator account.
2. Select **Upload & Process** from the left navigation menu.
3. Select the PDF files and choose **Start Processing**.
4. Follow the batch progress shown after upload.
5. Use **Review Queue** for documents requiring correction and **Failures** for documents that could not be processed.
6. Ask an administrator for help when a failure requires configuration or provider changes.

To stop the service, the administrator presses `Ctrl+C` in the terminal and then checks any document that was processing, as described in section 4.7.

---

## 1. Overview

The PDF Processing System automates extracting information from PDF documents. This version introduces:

Key features:  
- Configurable workflows via YAML “workflows” and “tasks”  
  *(YAML is a human-readable configuration file format that uses indentation to organize settings.)*  
- Extensible standard steps: split, extraction, review, rules, storage, archiving, housekeeping
  *(Standard steps are predefined operations that the system performs on each file.)*  
- Centralized configuration and logging  
- Watch-folder based ingestion and web interface for PDF upload
- SQLite-backed workflow state for batches, documents, task runs, extraction results, review items, artifacts, settings, and audit history
- Role-based web interface for operators and administrators
- Consistent alias-based output for CSV/JSON  
  *(Alias means a friendly name used for data fields in outputs, such as column headers.)*

Internet access is required for cloud-based extraction providers such as LlamaCloud Extract v2.

---

## 2. System Architecture & Data Flow

### Components

- **Watch Folder Monitor:** Detects new PDFs in the configured `watch_folder.dir` (the folder the system watches for new files). This directory must pre-exist; it is not auto-created.
- **Workflow Manager and Loader:** Loads `config.yaml` and runs the single configured pipeline order for every file.  
- **Standard Steps:** Executes ordered tasks for each file (split, extraction, review, rules, storage, archiver, housekeeping).
- **SQLite State Services:** Record ingestion batches, documents, task runs, extracted fields, review queues, artifacts, settings, and audit events.
- **Storage:** Writes extracted data to CSV/JSON and moves PDFs to their final destination.  
- **Logging:** Centralized application log with rotation.  
- **Web Interface:** Provides role-appropriate pages for operators and administrators; see sections 3.2 and 3.3 for user instructions.

When document splitting is enabled, this guide uses two workflow terms:

- **Fan-out:** one source PDF is divided into child PDFs. The system then processes each child separately, so one child may finish while another is still processing or waiting for review.
- **Fan-in:** whenever a child reaches a new state, the application recalculates the overall status of the source document and its batch. Fan-in is automatic status aggregation; it is not a task that an operator starts.

### Data Flow Diagram

```mermaid
  graph TD
      UserWatch[Operator: Watch Folder] -->|Add PDF| Monitor[Folder Monitor]
      UserWeb[Operator: Web Interface] -->|Upload PDF| WebUpload[Web Upload Handler]
      Monitor -->|Trigger| WorkflowLoader[Workflow Loader]
      WebUpload -->|Trigger| WorkflowLoader
      WorkflowLoader -->|Builds| Workflow[Workflow Manager]
      Workflow -->|Executes| Steps[Standard Steps Chain]
      Steps -->|Optional Split| Split[Create Child PDFs - Fan-out]
      Split -->|One Record per Segment| Children[Child Documents]
      Children -->|Run Downstream Tasks| Steps
      Steps -->|Extract| Extractor[LlamaCloud Extract v2 API]
      Extractor -->|Fields & Confidence| ReviewGate[Review Gate]
      ReviewGate -->|Needs Review| ReviewQueue[Human Review Queue]
      ReviewQueue -->|Corrections Complete| Resume[Resume Downstream Workflow]
      ReviewGate -->|Passes Review Rules| Rules[Rules Engine (e.g., update_reference)]
      Resume --> Rules
      Rules -->|Store| Storage[File & Data Storage]
      Storage -->|Organized Files| Output[files/ and data/]
      Storage -->|Child Status Change| FanIn[Update Source and Batch - Fan-in]
      Steps -->|Post-process| Archiver[Archive/Delete Input]
      Steps -->|State Events| SQLite[SQLite State Database]
      Split -->|Parent/Child State| SQLite
      ReviewQueue -->|Drafts, Diffs, Decisions| SQLite
      FanIn -->|Batch/Parent Status| SQLite
      SQLite -->|Batches, Documents, Reviews| AppUI[Unified Web Interface]
```

### What happens to your document?

1. Submission: You place a PDF in the watch folder.  
2. Detection: The system sees the new file and starts the single pipeline configured in `config.yaml`.
3. State record: The system creates SQLite batch/document records and a task-run record for each configured step.
4. Extraction: Information is extracted through LlamaCloud Extract v2 and field values/confidence are persisted.
5. Review gate: Optional rules decide whether the document needs human review.
6. Rules: Optional business logic runs (e.g., update reference files).
7. Storage: The PDF and extracted metadata are written to `files/` (PDF) and `data/` (CSV/JSON), and durable artifacts are registered in SQLite.
8. Post-process: The original input is archived or deleted per configuration.

---

## 3. Operator Guide

This section is for people who submit documents, monitor processing, and correct extracted information. It uses the names shown in the application rather than internal web addresses.

The system has two fixed account roles:

| Role | Intended use |
|------|--------------|
| **Operator** | Daily document upload, monitoring, review, failure investigation, and reporting. |
| **Administrator** | All operator work plus account, schema, pipeline, validation, and audit configuration. |

| Capability | Operator | Administrator |
|------------|:--------:|:-------------:|
| Upload documents and monitor processing | Yes | Yes |
| Review and correct extracted information | Yes | Yes |
| View failures, reports, and runtime settings | Yes | Yes |
| Configure schemas, pipeline tasks, review thresholds, and split behavior | No | Yes |
| Change account passwords and view the administrative audit history | No | Yes |

Use an operator account for normal daily work. Use the administrator account only when configuration or account management is required.

### 3.1. Using the Watch Folder

**What is the Watch Folder?**

- A directory the system monitors for PDFs. Any PDF placed here will be processed automatically.

**How to add files:**

1. Locate the watch folder (ask your administrator for the exact path; configured at `watch_folder.dir`).
2. Copy or move your PDF files into this folder.  
3. The system will automatically begin processing.

**What happens after upload:**

- The system moves accepted files into the configured processing directory (`watch_folder.processing_dir`) with temporary unique filenames.
- The configured pipeline performs extraction and any other enabled steps.
- Output locations depend on the storage tasks configured by the administrator.
- For PDFs detected while the application is running, the monitor checks that the first five bytes are `%PDF-`. A file that fails this check remains in the watch folder and is skipped for the current run.
- **Current limitation:** PDFs already present when the application starts do not receive the same header check before they are moved for processing. Remove invalid or incomplete files from the watch folder before restarting the application.
- Web upload size and file-count limits do not apply to the watch folder, but extraction-provider limits still apply.

**How to check completion:**

- Look for a renamed PDF in `files/` and a corresponding CSV/JSON in `data/`.  
- If outputs do not appear, ask your administrator to check logs.

### 3.2. Using the Web Interface

Ask your administrator for the system's web address and your account password.

**Sign in:**

1. Open the web address in your browser.
2. Select your assigned account, enter the password, and select **Sign In**.
3. After signing in, the application opens at **Upload & Process**.

**Upload PDF files:**

1. Select **Upload & Process** from the left navigation menu.
2. Select or drag the PDF documents into the upload area.
3. Select **Start Processing** to submit the documents.
4. The application opens the batch details so you can follow progress.

Unless an administrator changes the upload settings, the web interface accepts up to 20 files in one upload and up to 50 MB per file. The application also enforces an overall request-size limit. If an upload is rejected as too large, reduce the batch size or ask an administrator to review `web.max_upload_mb`, `web.max_upload_files`, and `web.max_upload_request_mb`.

**Monitor processing:**

1. After an upload, use the batch page that opens automatically to monitor its documents and processing steps.
2. To find an earlier batch, select **Reports** and locate it under **Recent Batches**.
3. Select the batch row to view its details, then select **Processing** for the full processing view.
4. If processing fails, select **Failures** from the left navigation menu for the reason and suggested action.

The application displays the original filename, current status, timestamps, and processing progress. You do not need to manage the temporary filenames or internal records used by the system.

**What happens after upload:**

- The system checks that each upload has a valid PDF header. An invalid file is rejected and is not queued for processing.
- Accepted files are moved into the processing area and handled in the background.
- Depending on the configured workflow, a file may be split, extracted, sent for review, exported, and archived.
- Processing and batch pages update from the application's saved workflow state.

### 3.3. Operator Workflows in the Unified App

The left navigation menu provides the following work areas. If the menu is collapsed, point to an icon to display its name.

| Menu item | Purpose |
|-----------|---------|
| **Upload & Process** | Upload documents and monitor current or recent batches. |
| **Review Queue** | Correct documents that require human review. |
| **Failures** | Investigate documents that could not be processed. |
| **Reports** | View processing and review activity summaries. |
| **Settings** | View non-secret runtime settings and configured paths. |

Administrators also see **Admin Home**, **Users**, **Schemas**, **Validation**, **Pipeline**, **Tasks**, **Audit**, and **Review Simulator**. These administrative areas are not available to operators.

#### Human Review

Documents enter the review queue when the system cannot confidently accept the extracted information or when an administrator requires review.

1. Select **Review Queue** from the left navigation menu.
2. Use the search and filters to find the document.
3. Select **Claim** beside the document to open its review screen.
4. Select **Claim** at the top of the review screen to reserve the item. This prevents another operator from editing it at the same time.
5. Compare the PDF preview with the extracted fields shown beside it.
6. Correct inaccurate or missing values.
7. Select **Preview Diff** to review your changes.
8. Select **Save Draft** if the review is incomplete, or **Complete Review** when all information has been checked.
9. After completion, confirm that the document leaves the active queue and continues processing.

Review actions have the following meanings:

- **Claim:** reserve the item for the current operator.
- **Release:** return the item to the queue so another operator can work on it.
- **Save Draft:** save corrections without completing the review.
- **Preview Diff:** compare the proposed corrections with the originally extracted values.
- **Complete Review:** submit the corrected values and allow the document to continue.

#### Review Gate Example

If the review gate is configured with `confidence_threshold: 0.90`, a field covered by the review rules can route the document to human review when its confidence is below 90%. For example:

1. The system extracts an invoice amount with 86% confidence.
2. Because this is below the configured 90% threshold, the document appears in **Review Queue**.
3. An operator selects **Review Queue**, claims the document, and compares the amount with the PDF preview.
4. The operator corrects the amount if necessary and selects **Preview Diff**.
5. After the operator selects **Complete Review**, the corrected information is saved and processing continues.

#### Schema-Based Review Migration

The current application replaces the previous separate review program. Operators and administrators perform all review work from **Review Queue**.

Migrated capabilities:

- administrators maintain review forms from **Schemas**;
- operators work on documents from **Review Queue**;
- drafts, comparisons, corrections, and completed values remain associated with the document;
- administrators review schema and pipeline findings from **Validation**;
- relevant administrator changes are recorded in **Audit**.

Administrators should use the unified schema editor to maintain review schemas. Operators should use the review queue rather than editing schema files directly.

#### Split Results

When split processing is enabled, one uploaded PDF may create several child documents. The system processes each child separately after the split. One child may finish while another is still processing or waiting in **Review Queue**. Finishing the split does not mean that all child documents have finished; the original PDF is complete only after every child has reached a final status.

To check progress, select **Processing Overview** from the left navigation menu, open the batch, and select its split results. This page shows:

- source document status
- child document IDs
- split category and confidence
- page ranges
- links to extraction results for child documents

#### Failures

Use **Failures** when a document cannot complete processing:

1. Select **Failures** from the left navigation menu.
2. Find the document by filename, batch, or failure details.
3. Open the failure to see the failed processing step, explanation, and suggested operator action.
4. Correct the source document or ask an administrator to correct the configuration, as appropriate.
5. Re-upload the document only after the cause has been addressed.

Repeated failures from child documents may be grouped under their original source PDF so that operators can investigate one source-level problem.

---

## 4. Administrator Guide

This section covers setup, configuration, and troubleshooting for administrators.

### 4.1. Starting and Stopping Services

**Starting the main processing service (Windows):**

1. Open `Command Prompt`.
2. Navigate to the project root folder.
3. Run the following command to start the system:

    ```
    C:\Python313\python.exe main.py
    ```

4. The system will begin monitoring the watch folder and processing files. By default, this command also starts the web interface, which will be accessible at `http://localhost:8000` (or the host/port configured in `config.yaml`).

**Starting only the Watch Folder Monitor (without Web Interface):**

If you only need the watch folder functionality and do not wish to run the web interface, use the `--no-web` argument:

    ```
    C:\Python313\python.exe main.py --no-web
    ```

**Stopping the service:**

To stop the system (both watch folder monitor and web interface, if running): Press `Ctrl+C` in the `Command Prompt` window where `main.py` is running. The system will gracefully shut down after finishing any current file processing.

### 4.2. Required Folders and Permissions

The system uses several folders for ingestion, processing, and storage. Ensure these folders exist and the system user has the correct permissions.

Startup validation rules:
- `watch_folder.dir` must already exist and be a directory. If missing or invalid, the application logs a CRITICAL error and exits at startup.
- `web.upload_dir` must already exist and be a directory. If missing or invalid, the application logs a CRITICAL error and exits at startup.
- Directories referenced by keys ending in `_dir` (except `watch_folder.dir`) are auto-created when possible; failures cause a CRITICAL log and exit.
- All `_dir` paths must exist and are directories; all `_file` paths must exist and are files.

#### 4.2.1 Pre-existing vs Auto-created folders (consolidated)

This subsection summarizes which folders the system expects to already exist, and which the application will create automatically at startup when possible.

Must pre-exist (startup validates and will fail if missing):
- `watch_folder.dir` — Watch folder where PDFs are ingested. The application will not create this folder.
- `web.upload_dir` — Staging folder used by the web upload handler. The application validates this at startup.
- Any config key that ends with `_file` (for example `tasks.*.params.reference_file`) — the referenced file must already exist and be a regular file.
- Any other explicitly-documented required directory in your `config.yaml`.

Auto-created if missing (ConfigManager attempts to create these at startup):
- `watch_folder.processing_dir` — Temporary processing folder where PDFs are moved with UUID filenames.
- Any config key that ends with `_dir` (for example `tasks.*.params.files_dir`, `tasks.*.params.data_dir`, `archive_dir`) — the ConfigManager will attempt to create these directories.
- Common task destinations such as `files/`, `data/`, and `archive_folder/` when specified via `_dir` keys.

Summary table:

| Folder / Pattern | Purpose | Creation behavior |
|------------------|---------|-------------------|
| `watch_folder.dir` | Watch folder where PDFs are ingested | Must pre-exist; startup fails if missing |
| `web.upload_dir` | Web upload staging directory | Must pre-exist; startup fails if missing |
| `watch_folder.processing_dir` | Files moved here prior to processing (UUID names) | Auto-created at startup if missing |
| `tasks.*.params.files_dir` | Destination for processed PDFs (`store_file_to_localdrive`) | Auto-created at startup if missing |
| `tasks.*.params.data_dir` | Destination for metadata (CSV/JSON) | Auto-created at startup if missing |
| `*_file` (pattern) | Files referenced by tasks, e.g., reference CSVs | Must pre-exist (must be an existing file) |

Notes and recommendations:
- If the application cannot create an auto-created directory due to permission errors, it will log a CRITICAL error and exit. To avoid startup failure, either pre-create the directories or ensure the account running the application has permission to create them.
- To pre-create directories on Windows, use File Explorer or a Command Prompt:
```
mkdir watch_folder processing web_upload files data archive_folder
```
- Use absolute paths in `config.yaml` to avoid ambiguity about the working directory, especially when running the system as a service.
- Ensure the user/service account running the application has Modify/Write permissions on directories that will be written to.

### 4.3. Configuration Management

#### 4.3.1. High-level Structure

Below is an example configuration snippet with explanations:

```yaml
logging:
  log_file: "app.log"                 # Path to the log file
  log_level: "INFO"                   # Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL

watch_folder:
  dir: "watch_folder"                 # Folder to watch for incoming PDFs (must pre-exist; startup fails if missing)
  validate_pdf_header: true           # Validate %PDF header before processing
  processing_dir: "processing"        # Folder where files are moved with UUID name (auto-created if missing)

web:
  upload_dir: "web_upload"            # Directory for future web uploads (must pre-exist; validated at startup)
  cors_allowed_origins: []            # Keep empty for same-origin browser use

database:
  path: "data/app_state.sqlite3"       # SQLite workflow-state database
  run_migrations_on_startup: true      # Run migrations when the app starts

review:
  enabled: true
  default_queue_name: "default_review"
  lock_timeout_minutes: 60

# Outputs are defined per task in `tasks`:
# - Processed PDFs destination: tasks.store_file_to_localdrive.params.files_dir (auto-created)
# - Metadata destinations: tasks.store_metadata_{csv,json}.params.data_dir (auto-created)
# - Split child PDFs destination: tasks.<split_task>.params.split_dir (required for split tasks, auto-created)
# - Archive destination: tasks.archive_pdf.params.archive_dir (auto-created)
```

#### 4.3.2. Global Sections

- **logging:** Controls logging behavior.
- **watch_folder:** Defines ingestion and processing folder behavior.
- **web:** Defines web upload directory and web server settings (host, port, secret key, optional CORS allowed origins).
- **database:** Defines the SQLite workflow-state path and migration behavior.
- **review:** Defines review queue behavior, queue name, and review lock duration.
- Task output directories are owned by task parameters such as `data_dir`, `files_dir`, `archive_dir`, `processing_dir`, and `split_dir`. Except for `watch_folder.dir`, directory paths whose keys end in `_dir` are auto-created by `ConfigManager`.

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

Workflows are defined by the ordered list under `pipeline:` and the task registry under `tasks:`. Each item in `pipeline` references a key in `tasks` which specifies `module`, `class`, and `params`.
The current implementation runs the same pipeline for every file; dynamic workflow selection or matching by file metadata is not implemented.
Task classes must be approved before the app imports them. Built-in `standard_step.*` tasks are approved by the application. Customer-specific tasks must be deployed under the `custom_step.` Python package and approved in deployment YAML under `custom_steps.registry`.

Example task categories include:

- `extraction`: Extract data from PDFs.
- `split.llamacloud_split`: Optionally split bundled PDFs into child documents before extraction.
- `review.review_gate`: Pause documents for operator review based on confidence, schema, or policy rules.
- `rules.update_reference`: Update reference CSV files.
- `storage.store_metadata_as_csv` / `storage.store_metadata_as_json`: Persist extracted information.
- `storage.store_file_to_localdrive`: Persist the processed PDF.
- `archiver.archive_pdf`: Archive the original input PDF.

The housekeeping cleanup step is appended automatically by the WorkflowLoader and runs last for every file. In the current implementation it only deletes the processed PDF in the processing directory; it does not archive files or remove status records.

### 4.4. Managing Application Accounts and Passwords

The application has two fixed accounts:

- **admin:** can use all operator and administrator features.
- **operator:** can upload, monitor, review, investigate failures, view reports, and view non-secret settings.

The account names and roles cannot be changed. Passwords are stored in the SQLite database configured by `database.path`; they are not read from an `authentication` section in runtime YAML.

#### First-Time Account Setup

Before the first login, open PowerShell in the project folder and run:

```powershell
C:\Python313\python.exe tools\setup_users.py --config config.yaml
```

The tool asks for an administrator password and an operator password, then asks you to confirm each one. Setup stops if the accounts already exist; do not use the reset option for routine setup.

For an upgrade from an older installation, an administrator may import the existing administrator bcrypt hash while setting a new operator password:

```powershell
C:\Python313\python.exe tools\setup_users.py --config config.yaml --legacy-config config.yaml
```

After a successful migration, remove the obsolete `authentication` section from the runtime YAML.

#### Change a Password Normally

An administrator can change either account password from the application:

1. Sign in with the **admin** account.
2. In the left navigation menu, select **Users** under the **Admin** section.
3. In the card for the account being changed, enter the current administrator password.
4. Enter and confirm the new password.
5. Select **Change admin password** or **Change operator password**.
6. Confirm that the application reports that the password was changed.

Changing a password this way signs out existing sessions for the changed account. The administrator must sign in again if changing the administrator password.

#### Recover Access When the Administrator Cannot Sign In

Use the setup tool's reset option only when the administrator password is unavailable:

```powershell
C:\Python313\python.exe tools\setup_users.py --config config.yaml --reset
```

The tool asks for new passwords and replaces the credentials for **both** fixed accounts. Run it against the same configuration file, and therefore the same `database.path`, used by the application. After the reset, test both accounts before returning the system to normal use.

#### Password and Login Rules

- Passwords must be 12–72 UTF-8 bytes long.
- Every password must contain an uppercase letter, a lowercase letter, a number, and a symbol.
- A new password must differ from the account's current password.
- Repeated failed login attempts are temporarily limited. Wait for the cooldown period before trying again, or review the `auth.login_*` settings if the lockout is unexpected.
- Use strong, unique passwords and do not share the administrator account for routine operator work.

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
Tailwind and DaisyUI are bundled locally; run `npm install` and
`npm run build:css` after changing frontend utility classes or package versions.
- Do not commit password hashes or secret-bearing config files to version control.
- Rotate passwords and audit access regularly.

### 4.5. Database, State, and Artifact Storage

The unified application uses SQLite as the primary source of workflow state.

#### 4.5.1. Database Initialization

The database location is configured by `database.path`, with a default of `data/app_state.sqlite3`. When `database.run_migrations_on_startup` is true, migrations run during startup for the web server and workflow ingestion paths.

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

#### 4.5.4. Operator and Administrator State Views

- Operators use **Upload & Process**, **Processing Overview**, **Review Queue**, **Failures**, **Reports**, and **Settings**.
- Administrators can use all operator areas and the additional configuration areas shown under **Admin**.
- The technical page paths are listed in the appendix for troubleshooting and support use.

#### 4.5.5. Administrator Workflow Details

The administrator menu provides these workflows:

- **Admin Home:** review configuration health, pipeline and review summaries, split status, and recent audit events.
- **Users:** change the administrator or operator password after confirming the current administrator password.
- **Pipeline:** prepare a draft, maintain task order and task parameters including review thresholds and split behavior, compare it with the active configuration, validate it, and publish it when no blocking errors remain.
- **Tasks:** inspect the workflow task classes available to the pipeline.
- **Review Simulator:** evaluate review-gate decisions with sample JSON without processing a PDF or writing final workflow results.
- **Audit:** inspect relevant configuration and governance events.
- **Validation:** review active configuration, schema, and pipeline findings.

For schema-driven review fields, see the [review schema administrator guide](review_schema_admin_guide.md).

Administrator access is determined by the immutable SQLite role. The fixed `admin` account can access all pages and APIs; the fixed `operator` account cannot access administrative pages or APIs. Secret values are not exposed through runtime settings. Configure provider secrets such as `api_key` through `config.yaml`, deployment secret management, or the masked credential control in the administrator Pipeline editor; saved values remain redacted when the pipeline is loaded again.

#### 4.5.6. Backup and Recovery

For a complete operational backup, include:

- the SQLite database file configured at `database.path`
- task-owned output folders such as `files/`, `data/`, `archive_folder/`, and any split task `split_dir` used by configured tasks
- reference CSVs and schema/config files

If the database is restored without the files, the UI may show registered artifacts whose paths no longer exist. If files are restored without the database, the system may still have exports on disk, but batch/task/review history will be incomplete.

### 4.6. Log Files and Troubleshooting

- The main log file is `app.log` in the project root.
- To see more detailed logs, set `logging.log_level` to `DEBUG` in `config.yaml`.
- Common startup errors include:
  - Invalid YAML syntax (check your config file with a YAML validator).
  - Missing folders (create required folders like `watch_folder`, `web_upload` before starting).
  - Missing or invalid provider credentials, such as a LlamaCloud `api_key`.
  - Permission errors (ensure the system user has read/write access to all configured directories).
- Performance considerations for large files:
  - Larger PDFs require more disk, memory, network, split, and provider processing time.
  - Process unusually large documents individually and during quieter periods.
  - Monitor **Processing Overview**, `app.log`, Windows Task Manager, free disk space, and provider quotas.
- During runtime troubleshooting:
  - Failed tasks log detailed errors to `app.log` with timestamps and context information.
  - Files with processing errors may remain in the processing directory; check **Processing Overview**, **Failures**, and `app.log`.
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
  - Use the web interface to monitor processing status in real-time.

### 4.7. Graceful Shutdown and Error Recovery

To stop the system, press `Ctrl+C` in the terminal where `main.py` is running. This asks the watch-folder monitor and web server to stop and runs registered cleanup handlers. It does not guarantee that every in-progress document finishes before the processes exit.

After stopping or restarting:

1. Check the final shutdown messages in `app.log`.
2. Sign in and open **Processing Overview** and **Failures**.
3. Inspect any document that was processing when shutdown began.
4. Confirm whether its outputs were created before deciding to re-upload it.
5. Do not delete processing files or database records unless the document state and recovery need are understood.

If the system fails to start, check `app.log`, validate `config.yaml`, confirm that the required watch and upload folders exist, and verify folder permissions and provider connectivity. The Config Check tool described in section 4.12 should be the first configuration diagnostic.

### 4.8. Task System: Standard Steps and Parameters

Standard steps are predefined operations configured in workflows. Below are the main task types and their parameters.

#### 4.8.1. extraction

- **Current module/class:** `standard_step.extraction.extract_pdf` / `ExtractPdfTask`
- **Purpose:** Extracts structured data and confidence information from PDF documents through LlamaCloud Extract v2.
- **params:**
  - `api_key`: string, required LlamaCloud credential.
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
  - Storage tasks can transform workflow field keys to configured aliases for CSV/JSON output.
- **Notes:**
  - Use `configuration_id` when you want LlamaCloud to use a saved Extract v2 configuration. Omit it when you want the application to build the extraction schema from the YAML `fields` block.
  - In saved-configuration mode, `tier`, `parse_tier`, `extraction_target`, `cite_sources`, and `confidence_scores` come from the saved LlamaCloud configuration. Local `fields` remain the workflow mapping used to normalize results for review and storage.
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
      api_key: "llx-REDACTED"
      tier: "agentic"
      extraction_target: "per_doc"
      fields:
        supplier_name:        { alias: "Supplier name",       type: "str" }
        client_name:          { alias: "Client name",         type: "str" }
        client_address:       { alias: "Client",              type: "str" }
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

`standard_step.extraction.extract_pdf.ExtractPdfTask` is the only registered PDF extraction task.

#### 4.8.2. split.llamacloud_split

- **type:** `"split.llamacloud_split"`
- **Purpose:** Optionally splits a source PDF into child PDF documents before downstream extraction and storage tasks run.
- **params:**
  - `enabled`: boolean. If `false`, the task records a skipped split result and the source document continues as a normal document.
  - `api_key`: string. Required at runtime when the real LlamaCloud split adapter is used.
  - `configuration_id`: optional saved LlamaCloud split configuration ID.
  - `categories`: optional list of category definitions. Required when `configuration_id` is not provided.
  - `allow_uncategorized`: controls what LlamaCloud does with pages that do not match a configured category. The default is `"include"`; see the decision table below.
  - `fail_on_confidence_levels`: list of split confidence labels that cause the whole split task to fail before child documents are created. Default is `["low"]`.
  - `fail_on_unknown_category`: boolean. When `true`, blank, `other`, `uncategorized`, and disallowed category results fail the whole split task. Default is `true`.
  - `allowed_categories`: optional list of accepted category names. If omitted, inline `categories` are used as the allowed list.
  - `split_dir`: string, required. Destination for generated child PDFs. Because the key ends in `_dir`, `ConfigManager` auto-creates it at startup when possible.
  - `project_id` / `organization_id`: optional provider scoping values.
  - `poll_interval_seconds`: optional polling interval. Default is `1.0`.
  - `timeout_seconds`: optional timeout. Default is `7200.0`.
- **Behavior:**
  - Runs only for root/source documents; split child documents skip the split task.
  - Creates one child document record and one split PDF for each provider segment.
  - Records split category, confidence, page range, and source metadata in SQLite.
  - Sets the parent/source document to `split_completed`, then child documents continue from the next pipeline task.
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
      api_key: "llx-REDACTED"
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
  - Advanced compatibility parameters may use nested `storage.data_dir` / `storage.filename`, a task-specific `extraction.fields` mapping, and an operational `task_slug`. New configurations should normally use the top-level directory and filename with the extraction task's shared fields.
- **Behavior:**
  - Uses configured field aliases for column names.
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
- **Behavior:**
  - Reads `context["data"]` (dict).
  - Writes a JSON file with keys transformed to aliases (if configured in extraction fields).
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
  - `schema_file`: optional schema name or path used to validate corrected/final field values. It must resolve under a configured schema directory such as `schema.directories`; by default this is `schemas` relative to the config file.
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
- **Locking:** Review claims use `review.lock_timeout_minutes`, defaulting to 60 minutes.

For schema-driven review field types, validation behavior, and LlamaCloud date-format guidance, see the [review schema administrator guide](review_schema_admin_guide.md).

**YAML configuration example:**

```yaml
tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: "llx-REDACTED"
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
  - Writes the generated ID to `context["nanoid"]`.
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

- **type:** `"housekeeping.cleanup"`
- **Purpose:** Performs final cleanup after workflow execution by deleting the processed PDF from the processing directory so the folder does not accumulate UUID-named files.
- **params:**
  - `processing_dir`: string (optional). Directory containing processed files. Defaults to "processing".
- **Behavior:**
  - Deletes the processed file referenced in the context if it exists in `processing_dir`.
  - Logs successes and warnings for missing files and preserves registered business artifacts.
  - Raises exceptions on critical delete failures.
  - Executes unconditionally as the final step, even if previous tasks failed, to keep the processing directory tidy.
- **Notes:**
  - This task is automatically invoked by the WorkflowLoader as a mandatory final step in every Prefect flow.
  - It does not require definition in the `tasks` section or inclusion in the `pipeline` list of `config.yaml`.
  - Ensures the processing directory remains clean by removing only the processed PDF.
#### 4.8.11. Validation and Failure Behavior

- Config validation happens at startup via the `ConfigManager`:
  - Validates that `web.upload_dir` exists and is a directory.
  - Validates that `watch_folder.dir` exists and is a directory; if missing/invalid, logs CRITICAL and exits. This path is NOT auto-created.
  - Pre-creates directories for any keys ending with `_dir` found across the config (e.g., task params) when possible, excluding `watch_folder.dir`.
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

To configure array-of-objects extraction, update your `config.yaml` to:

1. Use the canonical extraction task:
   ```yaml
   extract_document_data:
     module: standard_step.extraction.extract_pdf
     class: ExtractPdfTask
     params:
       api_key: "llx-REDACTED"
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

##### Confidence Persistence
- Scalar fields persist the provider's numeric confidence when available.
- Object, scalar-array, and object-array fields persist an aggregate confidence using the minimum nested numeric confidence.
- Nested confidence details are stored under each field's existing `source_json.confidence_details` payload, including per-cell paths such as `0.itemName` or `0.quantity`.
- No database migration is required; the existing `extracted_fields.confidence` and `source_json` columns are used.
- This behavior applies to new extraction runs only. Existing completed extraction/review records are not rewritten automatically.

##### JSON Storage
- Preserves the list-of-objects structure for table fields.
- Configured fields are written under their aliases when aliases are present; otherwise workflow field keys are preserved.
- Maintains backward compatibility with scalar-only data.

##### CSV Storage
- **Row-per-item mode**: Creates one CSV row for each item in the array, repeating invoice-level fields.
- **Column naming**: Scalar and item columns use configured aliases. Item columns are prefixed with `item_` (e.g., `item_description`, `item_quantity`).
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

5. Validate a saved LlamaCloud configuration with the smoke checker:

   ```powershell
   C:\Python313\python.exe tools\llamacloud_extract_smoke.py --config dev_config.yaml --file sample_invoice.pdf --configuration-id "cfg-..."
   ```

   If `configuration_id` is already set in the selected config file, omit the override flag. The smoke checker writes `raw_extract_result.json`, `workflow_normalized_data.json`, and `workflow_fit_report.json`.

#### 4.9.5. Current Limitations

- Only one `is_table: true` field is supported per extraction.
- `object_fields` supports flat primitive properties only; nested objects and lists are not supported.
- Items must be simple dictionaries (no nested arrays or objects).
- Complex nested structures may require additional processing logic.

---

### 4.10. Example Workflows

**Example pipeline using the canonical extraction and storage tasks:**

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

# Tasks registry: name -> module/class/params
tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: "llx-REDACTED"
      tier: "agentic"
      extraction_target: "per_doc"
      fields:
        supplier_name:        { alias: "Supplier name",       type: "str" }
        client_name:          { alias: "Client name",         type: "str" }
        client_address:       { alias: "Client",              type: "str" }
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

Housekeeping runs automatically as the final step after the pipeline completes to remove the processed PDF from the processing directory. It is not included in the `tasks` registry or `pipeline` list.

Notes:
- The pipeline is an ordered list of task names defined under `tasks:`.
- Housekeeping runs automatically as the final step of the workflow, invoked directly by the WorkflowLoader. It deletes temporary processing-folder PDFs while preserving registered business artifacts.
- Each task references a Python module and class from the `standard_step` package and receives `params`.
- Customer custom task modules can be used only after deployment approval in `custom_steps.registry`, and custom modules must use the `custom_step.` prefix.
- The three storage-related tasks are separate:
  - `store_metadata_csv` writes CSV to `data_dir` using `filename` template.
  - `store_metadata_json` writes JSON to `data_dir` using `filename` template.
  - `store_file_to_localdrive` moves the original PDF to `files_dir` using `filename`.
- Field placeholders in `filename` come from extracted data keys (e.g., `{supplier_name}`, `{invoice_amount}`, `{policy_number}`).
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

The `module` and `class` values under `tasks:` still stay in the normal pipeline configuration. The registry only approves which custom task classes may be imported.
### 4.11. Housekeeping and the Processing Folder

- The `processing_dir` contains temporary working files during processing. Workflow state is stored in SQLite.
- The workflow attempts the housekeeping cleanup task after the configured pipeline, including after ordinary task failures. It deletes the processed PDF from `processing_dir` and does not remove durable registered artifacts.
- An interrupted process or cleanup error can leave a working file behind. Check document state and logs before removing it manually.
- Any old text status files are legacy diagnostics only and are not required for current workflow state.

---

### 4.12. Config Check Validation Tool

**Audience:** Administrators. Operators should contact an administrator when configuration changes are required.

The `config-check` utility lives under `tools/config_check` and validates `config.yaml` before you deploy or restart services. Run it whenever you modify tasks, pipelines, or environment-specific paths--especially after applying workflow updates from product tasks 13-19.

**Core workflow**
- Use `C:\Windows\System32\cmd.exe` or PowerShell from the project root.
- Execute `C:\Python313\python.exe -m tools.config_check validate --config config.yaml --base-dir .` to lint the active configuration.
- Pass `--format json` when you need machine-readable output for ticket attachments or CI logs.
- Treat exit code `0` as success, `1` as blocking errors, and `2` as warnings that still need follow-up.

**When to escalate**
- Review `tools/config_check/README.md` for CLI flag details and examples.
- Cross-reference `docs/config_check_troubleshooting.md` to resolve the common findings surfaced by tasks 13-19 (credential gaps, storage overrides, token mismatches, and similar issues).
- If operators report workflow failures, run the validator before restarting production work; many configuration problems can be found without rerunning documents.

Operators do not need to run this tool. Administrators should share only the part of a validation report needed to request missing information or explain an action.

## 5. Frequently Asked Questions (FAQ)

**Q: Does the program require internet access?**  
A: Yes, for cloud providers such as LlamaCloud Extract v2 via HTTPS.

**Q: Where are my processed files stored?**
A: Processed PDF documents are saved by the "`store_file_to_localdrive`" task to the folder configured at `tasks.store_file_to_localdrive.params.files_dir`. Extracted metadata is saved separately:
- CSV files: `tasks.store_metadata_csv.params.data_dir`
- JSON files: `tasks.store_metadata_json.params.data_dir`

When SQLite document context exists, generated PDFs, CSV files, JSON files, archives, source originals, and split PDFs are also registered as document artifacts in SQLite. Split child PDFs are written to the configured split task directory at `tasks.<split_task>.params.split_dir`.

**Q: What happens if the same filename already exists?**
A: Storage tasks generate unique filenames automatically by appending a numeric suffix (`_1`, `_2`, …) to avoid overwriting. See the [filename utility](../modules/utils.py) for the implementation.

**Q: What are provider limits?**  
A: LlamaCloud Extract and LlamaParse limits include max file size and processing time; consult the current provider documentation for your workspace and tier.

**Q: How do I edit the configuration file safely?**  
A: Use a plain text editor, preserve indentation, back up before changes, and restart the system after saving.

**Q: How do I set folder permissions on Windows?**
A: Right-click the folder, select Properties > Security tab, and ensure the system user has Modify or Write permissions.

**Q: Why do I get "Invalid credentials" error when logging into the web interface?**
A: Confirm that user setup was run against the same `database.path` used by the application and select the correct fixed account on the login page. If setup has not run, use `tools/setup_users.py` as described in section 4.4.

After repeated failed login attempts, the system may temporarily throttle additional attempts. Wait for the cooldown period or ask an administrator to review the `auth.login_*` settings if the lockout is unexpected.

**Q: Why does my login session expire quickly or tokens become invalid?**
A: Authentication tokens are valid for 30 minutes by default. If sessions are expiring too quickly, ensure your system's clock is accurate, as token expiration is time-sensitive. Administrators can adjust the timeout with `web.token_exp_minutes` in `config.yaml`.

**Q: How do I reset or change the web interface password?**
A: For a normal change, sign in as the administrator and select **Users** from the **Admin** section of the left navigation menu. For recovery when the administrator cannot sign in, run `tools/setup_users.py --config config.yaml --reset`; this replaces both account passwords. See section 4.4.

**Q: How do I verify my authentication configuration is correct?**
A: Ensure `web.secret_key` and `database.path` are correct, initialize both users with the setup CLI, and test both fixed accounts. Runtime YAML must not contain usernames or password hashes.

**Q: Why is processing slow for large PDF files?**
A: Larger files require more disk, memory, network, split, and extraction work. Process very large files individually or during quieter periods, keep enough free disk space for working files and exports, and monitor **Processing Overview** and `app.log`. The web interface rejects files above its configured upload limit before processing starts.

**Q: What should I do if the system appears stuck processing a file?**
A: Open **Processing Overview** and inspect the batch and document steps. Then check **Failures** and `app.log` for provider errors, timeouts, validation problems, or folder-permission errors. Use Windows Task Manager to check CPU, memory, and disk usage. If shutdown is necessary, follow section 4.7 and inspect the document before re-uploading it.

**Q: How do I handle API rate limiting from extraction providers?**
A: The system retries temporary extraction failures, but a persistent provider limit can still cause the document to fail. Check **Failures**, `app.log`, and the provider quota dashboard. Wait for the limit to clear before re-uploading, and reduce batch volume if the problem repeats.

**Q: What should I do if archiving fails due to directory permissions?**
A: Ensure the `archive_dir` configured in `tasks.archive_pdf.params.archive_dir` exists and grants Modify permission to the account running the application. Check **Processing Overview**, **Failures**, and `app.log`. A successful archive is recorded with the document's files.

**Q: What happens when reference file matching fails in the update_reference task?**
A: When field values required for matching are not found in the pipeline context, the task logs a warning and continues without matching any rows. The task will not append new rows. It updates matched rows only, creating the configured `update_field` column at runtime if needed. Check your extraction field configuration and ensure the required fields (like `purchase_order_number` or `invoice_amount`) are being extracted correctly.

**Q: Why is my document waiting for review?**
A: Review rules may pause a document because confidence is low or missing, required information is missing or invalid, split confidence requires attention, a business rule requests review, or every document is configured for review. Select **Review Queue**, claim the item, compare the PDF with the extracted fields, and select **Complete Review** when the information is correct.

**Q: What happens after review is completed?**
A: Corrected values are persisted in SQLite with the document extraction state. If the review gate uses `resume_policy: "next_task"`, the document resumes the downstream workflow steps after review completion.

**Q: Why did one uploaded PDF become multiple documents?**
A: When split processing is enabled, the source PDF can create child documents based on document category and page range. Open the batch from **Processing Overview**, then select its split results to inspect the source and child documents.

**Q: Can administrators change pipeline review or split behavior in the UI?**
A: Yes. Sign in as the administrator and use **Pipeline** to adjust task parameters, **Review Simulator** to preview review-gate behavior, and **Validation** to check configuration health. Secret provider values such as API keys can be configured through `config.yaml`, deployment secret management, or the masked administrator Pipeline control.

**Q: How do I troubleshoot "Invalid credentials" errors during PDF extraction?**
A: The system validates the required LlamaCloud `api_key` before processing. If you use a saved Extract v2 configuration, ensure `configuration_id` exists in the correct LlamaCloud project. Check `app.log` for detailed credential and extraction errors.

---


## 6. Appendix

### Glossary

- **Administrator:** The fixed account role that can use all operator features and change application configuration and account passwords.
- **Operator:** The fixed account role intended for daily upload, monitoring, review, failure investigation, and reporting.
- **Pipeline:** The ordered list of processing tasks applied to every submitted PDF.
- **Task (standard step):** One configured operation, such as split, extraction, review, storage, or archiving.
- **Review gate:** Rules that decide whether a document can continue automatically or must be checked by an operator.
- **Review queue:** The application area containing documents that require an operator decision.
- **Source document:** The original PDF submitted for processing.
- **Child document:** A PDF created from selected pages when a source document is split.
- **Fan-out:** Creation of child documents that each run the remaining pipeline tasks.
- **Fan-in:** Automatic recalculation of source-document and batch status from the child-document statuses.
- **Alias:** A user-friendly field name used in the interface or exported CSV/JSON.
- **Watch folder:** A folder monitored for newly added PDFs.
- **Recovery reset:** The administrator command-line procedure that replaces the passwords for both fixed accounts when normal sign-in is unavailable.
- **YAML:** The indentation-based text format used for application configuration.
- **API key:** A credential used by the application to access an external provider.

### Technical Page Reference

Normal users should navigate with the left menu. The paths below are provided for administrators, support staff, bookmarks, and troubleshooting.

| Interface area | Path | Access | How to navigate to this area |
|----------------|------|--------|------------------------------|
| Upload & Process | `/app/upload` | Operator and administrator | Select **Upload & Process** from the left navigation menu. |
| Processing Overview | `/app/processing` | Operator and administrator | Start an upload from **Upload & Process**; its processing page opens automatically. To view other processing activity, select **Reports**, then **Processing**. |
| Batch details | `/app/batches/{batch_id}` | Operator and administrator | Select **Reports**, choose a batch under **Recent Batches**, then select **Processing** in the batch details window. |
| Split results | `/app/batches/{batch_id}/split-results` | Operator and administrator | Open the batch's **Processing Overview**, then select **View Split Results**. |
| Extraction results | `/app/documents/{document_id}/extraction` | Operator and administrator | Open **Processing Overview** and select **Extraction** beside the document. For a split PDF, open **Split Results** and select **Extraction** beside a child document. |
| Review Queue | `/app/review` | Operator and administrator | Select **Review Queue** from the left navigation menu. |
| Review item | `/app/review/{review_item_id}` | Operator and administrator | Select **Review Queue**, find the document, then select **Claim** or **View**. |
| Failures | `/app/failures` | Operator and administrator | Select **Failures** from the left navigation menu. |
| Reports | `/app/reports` | Operator and administrator | Select **Reports** from the left navigation menu. |
| Settings | `/app/settings` | Operator and administrator | Select **Settings** from the left navigation menu. |
| Admin Home | `/app/admin` | Administrator only | Sign in as the administrator, then select **Admin Home** from the left navigation menu. |
| Users | `/app/admin/users` | Administrator only | Sign in as the administrator, then select **Users** from the left navigation menu. |
| Schemas | `/app/schemas` | Administrator only | Sign in as the administrator, then select **Schemas** from the left navigation menu. |
| Validation | `/app/settings/validation` | Administrator only | Sign in as the administrator, then select **Validation** from the left navigation menu. |
| Pipeline | `/app/admin/pipeline` | Administrator only | Sign in as the administrator, then select **Pipeline** from the left navigation menu. |
| Tasks | `/app/admin/tasks` | Administrator only | Sign in as the administrator, then select **Tasks** from the left navigation menu. |
| Audit | `/app/admin/audit` | Administrator only | Sign in as the administrator, then select **Audit** from the left navigation menu. |
| Review Simulator | `/app/admin/dry-run` | Administrator only | Sign in as the administrator, then select **Review Simulator** from the left navigation menu. |

The `/api/files` and `/api/status/{file_id}` endpoints are retained only for compatibility and are not the primary operator interface.

### Example Configuration Files

See sections 4.3.1 and 4.8 for complete examples. Use them as templates and adjust paths and credentials to your environment.

### Further Documentation

- System Architecture: [design_architecture.md](design_architecture.md)
- Historical Unified Refactor Requirements: [prd-refactor-unified-pdfdoc-processing.md](../tasks/archive/unified-refactor/prd-refactor-unified-pdfdoc-processing.md)
- Review Schema Administration: [review_schema_admin_guide.md](review_schema_admin_guide.md)
- LlamaCloud document splitting: [official LlamaIndex guide](https://developers.llamaindex.ai/llamaparse/split/getting_started)

---

This guide documents operator workflows and administrator configuration for the current PDF processing application.
