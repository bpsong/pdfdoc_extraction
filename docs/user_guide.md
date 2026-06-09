<!--
PDF Processing System: User Guide (Configurable Tasks Edition)
Version: 2.5
Release Date: 2026-06-03
Author: [Your Organization/Name]
-->

# PDF Processing System: User Guide (Configurable Tasks Edition)

---
Version: 2.5
Release Date: 2026-06-03
Author: [Your Organization/Name]

---

## Table of Contents

- [History of Changes](#history-of-changes)
- [Quick Start Guide](#quick-start-guide)
- [1. Overview](#1-overview)
- [2. System Architecture & Data Flow](#2-system-architecture--data-flow)
- [3. End User Guide](#3-end-user-guide)
  - [3.1. Using the Watch Folder](#31-using-the-watch-folder)
  - [3.2. Using the Web Interface](#32-using-the-web-interface)
  - [3.3. Operator Workflows in the Unified App](#33-operator-workflows-in-the-unified-app)
- [4. Administrator Guide](#4-administrator-guide)
  - [4.1. Starting and Stopping Services](#41-starting-and-stopping-services)
  - [4.2. Required Folders and Permissions](#42-required-folders-and-permissions)
  - [4.3. Configuration Management](#43-configuration-management)
    - [4.3.1. High-level Structure](#431-high-level-structure)
    - [4.3.2. Global Sections](#432-global-sections)
    - [4.3.3. Workflows and Matching](#433-workflows-and-matching)
  - [4.4. Managing Web Interface Passwords](#44-managing-web-interface-passwords)
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
  - [4.9. LlamaCloud Extract v2 Array-of-Objects Support](#49-llamacloud-extract-v2-array-of-objects-support)
  - [4.10. Example Workflows](#410-example-workflows)
  - [4.11. Housekeeping and the Processing Folder](#411-housekeeping-and-the-processing-folder)
  - [4.12. Config Check Validation Tool](#412-config-check-validation-tool)
- [5. Frequently Asked Questions (FAQ)](#5-frequently-asked-questions-faq)
- [6. Appendix](#6-appendix)
  - [Glossary](#glossary)
  - [Example Configuration Files](#example-configuration-files)
  - [Further Documentation](#further_documentation)

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
| 2.5     | 2026-06-03 | [Your Organization] | Updated for unified `/app/*` operator/admin UI, SQLite-backed workflow state, review, split, reports, settings, artifact registration, and legacy status endpoint compatibility |

---

## Quick Start Guide

This quick start guide helps you get the system running with minimal steps. It is designed for administrators who may not have programming experience.

1.  **Prepare the Watch Folder (must pre-exist)**
    Ensure the folder where PDFs will be placed exists and has read/write permissions. This folder is configured as `watch_folder.dir` in `config.yaml`.
    Important: The application will not create this folder for you. If `watch_folder.dir` does not already exist or is not a directory, startup will fail with a CRITICAL log and the program will exit.

2.  **Place PDF Files**
    Copy or move your PDF documents into the watch folder.

3.  **Start the System**
    Open a `Command Prompt`, navigate to the project folder, and run:

    ```
    C:\Python313\python.exe main.py
    ```

    The system will monitor the watch folder and process new files automatically.

4.  **Check Processing State**
    Use `/app/processing` or the batch page shown after upload to track the document. Workflow state is stored in SQLite, not intermediate text status files.

5.  **Check Output**
    Processed PDFs will appear in the `files/` folder (renamed if configured). Extracted data will be saved in the `data/` folder as CSV or JSON files.

6.  **Stop the System**
    Press `Ctrl+C` in the `Command Prompt` to stop the system safely.

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
- Operator and administrator UI pages under `/app/*`
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
- **Web Interface:** Operator and admin pages are available under `/app/*`; see section 3.2 and 3.3 for user instructions.

### Data Flow Diagram

```mermaid
  graph TD
      UserWatch[End User: Watch Folder] -->|Add PDF| Monitor[Folder Monitor]
      UserWeb[End User: Web Interface] -->|Upload PDF| WebUpload[Web Upload Handler]
      Monitor -->|Trigger| WorkflowLoader[Workflow Loader]
      WebUpload -->|Trigger| WorkflowLoader
      WorkflowLoader -->|Builds| Workflow[Workflow Manager]
      Workflow -->|Executes| Steps[Standard Steps Chain]
      Steps -->|Optional Split| Split[Split Fan-out]
      Split -->|Child PDFs| Children[Child Documents]
      Children -->|Run Downstream Tasks| Steps
      Steps -->|Extract| Extractor[LlamaCloud Extract v2 API]
      Extractor -->|Fields & Confidence| ReviewGate[Review Gate]
      ReviewGate -->|Needs Review| ReviewQueue[Human Review Queue]
      ReviewQueue -->|Corrections Complete| Resume[Resume Downstream Workflow]
      ReviewGate -->|Passes Review Rules| Rules[Rules Engine (e.g., update_reference)]
      Resume --> Rules
      Rules -->|Store| Storage[File & Data Storage]
      Storage -->|Organized Files| Output[files/ and data/]
      Storage -->|Child Completion| FanIn[Fan-in Aggregate Status]
      Steps -->|Post-process| Archiver[Archive/Delete Input]
      Steps -->|State Events| SQLite[SQLite State Database]
      Split -->|Parent/Child State| SQLite
      ReviewQueue -->|Drafts, Diffs, Decisions| SQLite
      FanIn -->|Batch/Parent Status| SQLite
      SQLite -->|Batches, Documents, Reviews| AppUI[Unified /app UI]
```

### What happens to your document?

1. Submission: You place a PDF in the watch folder.  
2. Detection: The system sees the new file and chooses a workflow via match rules.  
3. State record: The system creates SQLite batch/document records and a task-run record for each configured step.
4. Extraction: Information is extracted through LlamaCloud Extract v2 and field values/confidence are persisted.
5. Review gate: Optional rules decide whether the document needs human review.
6. Rules: Optional business logic runs (e.g., update reference files).
7. Storage: The PDF and extracted metadata are written to `files/` (PDF) and `data/` (CSV/JSON), and durable artifacts are registered in SQLite.
8. Post-process: The original input is archived or deleted per configuration.

---

## 3. End User Guide

This section is for users submitting PDFs for processing.

### 3.1. Using the Watch Folder

**What is the Watch Folder?**

- A directory the system monitors for PDFs. Any PDF placed here will be processed automatically.

**How to add files:**

1. Locate the watch folder (ask your administrator for the exact path; configured at `watch_folder.dir`).
2. Copy or move your PDF files into this folder.  
3. The system will automatically begin processing.

**What happens after upload:**

- The system moves files into the configured processing directory (`watch_folder.processing_dir`) with UUID filenames.
- Data extraction is performed.
- Outputs are saved into `data/` (CSV/JSON) and `files/` (renamed PDF via the `store_file_to_localdrive` task).
- If there's a problem, errors are logged and the file may be moved to `invalid_files/`.
- Header validation: the watch-folder monitor performs a minimal PDF header (magic-bytes) validation before moving files into processing. The monitor reads the first 5 bytes of the file and expects them to be `b"%PDF-"`. The monitor retries this read a configurable number of times to avoid false negatives from partial writes. Files that fail this validation are skipped/removed and not moved into processing.
- **File size considerations:** Very large files (>100MB) may take significant time to process and could cause performance issues. Monitor the log files during large file processing.

**How to check completion:**

- Look for a renamed PDF in `files/` and a corresponding CSV/JSON in `data/`.  
- If outputs do not appear, ask your administrator to check logs.

### 3.2. Using the Web Interface

The web interface provides a user-friendly way to upload PDF documents and monitor their processing status.

**Accessing the Web Interface:**

1.  Open your web browser.
2.  Navigate to the system's web address (e.g., `http://localhost:8000/app/upload`). Ask your administrator for the exact URL.
3.  Log in using your provided username and password.

**Uploading PDF Files:**

1.  After logging in, navigate to the "Upload" page (typically accessible via `/app/upload` or a link on the app sidebar).
2.  Click the "Choose File" or "Browse" button to select the PDF document(s) from your local machine.
3.  Click the "Upload" button to submit the file(s).
4.  The system will redirect you to the batch processing page, where you can monitor the status of your uploaded file or batch.

**Monitoring File Status:**

1.  On `/app/processing` or `/app/batches/{batch_id}`, you will see recent batches and documents.
2.  Each entry displays the document, original name, status, created/updated timestamps, and task progress.
3.  The processing view reads SQLite batch/document/task-run state.
4.  If a file fails, an error message will be displayed to assist with troubleshooting.

**What happens after upload:**

-   The system saves the uploaded PDF to the `web.upload_dir` (configured in `config.yaml`) with a unique ID.
-   Immediate header validation: the web upload flow performs a minimal PDF header (magic-bytes) validation at ingestion time (server-side) before persisting uploads to the staging area. The system reads the first 5 bytes and expects `b"%PDF-"`. If this check fails the upload is rejected with a 400 response and the file is not saved. This complements the watch-folder validation and helps reject invalid or non-PDF uploads early.
-   The file is then moved to the `watch_folder.processing_dir` for workflow execution.
-   Data extraction and subsequent tasks are performed in the background.
-   Outputs are saved into `data/` (CSV/JSON) and `files/` (renamed PDF via the `store_file_to_localdrive` task).
-   `/app/processing` and the batch detail page provide real-time status updates from SQLite state.

### 3.3. Operator Workflows in the Unified App

The primary operator experience is under `/app/*`.

| Page | Purpose |
|------|---------|
| `/app/upload` | Upload one or more PDFs as a batch. |
| `/app/processing` | View current and recent batches/documents. |
| `/app/batches/{batch_id}` | Track one batch through splitting, extraction, review, and completion. |
| `/app/batches/{batch_id}/split-results` | Inspect split source files and generated child documents. |
| `/app/documents/{document_id}/extraction` | Review extracted fields, confidence, metadata, and source PDF access. |
| `/app/review` | Work the review queue for documents requiring human intervention. |
| `/app/review/{review_item_id}` | Claim, inspect, edit, diff, and complete a review item. |
| `/app/reports` | View processing and review activity summaries. |
| `/app/settings` | View non-secret runtime settings and configured paths. |
| `/app/settings/validation` | View configuration, schema, and pipeline validation findings. |
| `/app/schemas` | Admin-only schema list and creation workflow. |
| `/app/schemas/{schema_name}` | Admin-only schema editor for extraction/review schemas. |

#### Human Review

Documents enter review when configured review-gate rules require it, such as low confidence, missing required fields, or an always-review policy. Operators should:

1. Open `/app/review`.
2. Filter or search for pending review items.
3. Claim an item.
4. Review the source PDF and extracted fields.
5. Save draft values if more work is needed.
6. Complete review when corrected values are ready.

Completed review values are persisted in SQLite with the extracted fields. The document can then be resumed through downstream workflow steps.

#### Review Gate Example

If the review gate is configured with `confidence_threshold: 0.90`, any extracted field below 90% confidence can route the document to human review. For example:

1. LlamaCloud extracts `invoice_amount` with confidence `0.86`.
2. The review gate marks the document as `review_required` and creates a review item in the configured queue.
3. An operator opens `/app/review`, claims the item, checks the source PDF, and corrects the field value if needed.
4. The operator may save a draft while working or preview the diff before completion.
5. When the operator completes review, corrected values are persisted in SQLite and the document resumes the downstream workflow steps.

#### Schema-Based Review Migration

The unified app replaces the previous separate `qa_extracted_data` Streamlit review workflow. Operators and administrators no longer need to run a separate Streamlit application.

Migrated capabilities:

- schema-driven review forms are served from `/app/schemas` and `/app/schemas/{schema_name}`;
- review items are queued in SQLite and worked through `/app/review`;
- field corrections, drafts, diffs, and final values are stored with the document extraction state;
- schema validation is exposed through `/app/settings/validation` and admin schema validation APIs;
- audit/config-version flows record administrator changes where applicable.

Administrators should use the unified schema editor to maintain review schemas. Operators should use the review queue rather than editing schema files directly.

#### Split Results

When split processing is enabled, a batch may create child documents from one source PDF. Use `/app/batches/{batch_id}/split-results` to see:

- source document status
- child document IDs
- split category and confidence
- page ranges
- links to extraction results for child documents

#### Legacy Dashboard

Legacy `/dashboard`, `/api/files`, and `/api/status/{file_id}` routes may still exist for compatibility. New operational workflows should use `/app/*` pages. The legacy status APIs are backed by SQLite compatibility responses and should not be treated as the primary state model.

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

This disables cross-origin browser access by default while preserving the normal `/app/*` user experience. Only add values when a separate trusted frontend is hosted on another origin, such as a different domain, scheme, or port:

```yaml
web:
  cors_allowed_origins:
    - "https://trusted-frontend.example.com"
```

Do not use `*` for this setting. Command-line tools, Python scripts, and same-origin browser pages do not require CORS.

#### 4.3.3. Workflows and Matching

Workflows are defined by the ordered list under `pipeline:` and the task registry under `tasks:`. Each item in `pipeline` references a key in `tasks` which specifies `module`, `class`, and `params`.
The current implementation runs the same pipeline for every file; dynamic workflow selection or matching by file metadata is not implemented.

Example task categories include:

- `extraction`: Extract data from PDFs.
- `split.llamacloud_split`: Optionally split bundled PDFs into child documents before extraction.
- `review.review_gate`: Pause documents for operator review based on confidence, schema, or policy rules.
- `rules.update_reference`: Update reference CSV files.
- `storage.store_metadata_as_csv` / `storage.store_metadata_as_json`: Persist metadata.
- `storage.store_file_to_localdrive`: Persist the processed PDF.
- `archiver.archive_pdf`: Archive the original input PDF.

The housekeeping cleanup step is appended automatically by the WorkflowLoader and runs last for every file. In the current implementation it only deletes the processed PDF in the processing directory; it does not archive files or remove status records.

### 4.4. Managing Web Interface Passwords

The web interface uses a simple username/password authentication system. Passwords are stored securely as bcrypt hashes in the `config.yaml` file by default. The sections below show how to generate hashes and provide security recommendations for storing them safely.

Generating bcrypt password hashes:

1.  Install the `bcrypt` package (pinned for this project):

    Open a `Command Prompt` and run:

    ```
    C:\Python313\python.exe -m pip install "bcrypt==5.0.0"
    ```

2.  Generate a bcrypt hash using a Python one-liner:

    ```
    C:\Python313\python.exe -c "import bcrypt; print(bcrypt.hashpw(b'your_new_password', bcrypt.gensalt()).decode())"
    ```

    This will output a hashed password string, e.g.:

    ```
    $2b$12$KIXQJ1eYQ1vQ9Z1Q1Q1Q1u1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1
    ```

3.  Update `config.yaml`:

    Open `config.yaml` and locate the `authentication` section. Add or update the user's entry with the generated hash:

    ```yaml
    authentication:
      username: "admin"
      password_hash: "$2b$12$KIXQJ1eYQ1vQ9Z1Q1Q1Q1u1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1Q1"
    ```

4.  Restart the system for changes to take effect (see section 4.1).

Notes:
- bcrypt enforces a hard 72-byte password limit; choose passwords under that length or generation/verification will fail.
- Keep the `bcrypt` version aligned with `requirements.txt` (currently `5.0.0`) to avoid compatibility issues.

Optional helper script:

You can use the included helper script `tools/generate_password_hash.py` to generate bcrypt hashes.

Usage:

```
C:\Python313\python.exe tools\generate_password_hash.py
C:\Python313\python.exe tools\generate_password_hash.py --password "new_password"
```

The script prints a bcrypt hash suitable for `authentication.password_hash` in `config.yaml`.

Security recommendations for storing password hashes

- Prefer not to store secrets in plaintext or publicly-readable files. Although bcrypt hashes are not reversible, storing them in a configuration file means an attacker with read access can attempt offline attacks or reuse the hash if your application accepts the hash directly. For production, use a dedicated secret store or environment-variable approach where possible.

- If you must keep bcrypt hashes in `config.yaml`, restrict access to that file on Windows using NTFS ACLs. Example commands (run in an elevated Command Prompt; replace `MYDOMAIN\MyServiceAccount` with your service account or `%USERNAME%` as appropriate):

  - Inspect current ACL:
    ```
    icacls "config.yaml"
    ```

  - Remove inherited permissions:
    ```
    icacls "config.yaml" /inheritance:r
    ```

  - Grant full control to SYSTEM and Administrators, and read-only to a specific service account:
    ```
    icacls "config.yaml" /grant:r "SYSTEM:F" "Administrators:F" "MYDOMAIN\MyServiceAccount:R"
    ```

  - Remove broad group access (example):
    ```
    icacls "config.yaml" /remove "Users"
    ```

  Notes:
  - Use `/grant:r` to replace existing explicit grants, and be careful when removing permissions to avoid locking yourself out.
  - To view the effective permissions after changes, run `icacls "config.yaml"` again.

- Consider encrypting the file with EFS (Encrypting File System) if the file must remain on disk and the service runs under a user account with a key:
  ```
  cipher /e "config.yaml"
  ```
  Note: EFS ties the encryption to a user account and may complicate access for service accounts or cross-machine deployments.

- Use environment variables for secret material (recommended for many deployments). Instead of embedding the hash directly in `config.yaml`, use an environment variable and inject the secret at runtime or during service start. Example `config.yaml` snippet (requires the application or a startup wrapper to perform environment substitution):

  ```yaml
  authentication:
    username: "admin"
    password_hash: "${WEB_ADMIN_HASH}"  # Replace at runtime or inject before starting the service
  ```

  Set the environment variable in Windows (system-level or service-specific; `setx` persists to the user environment and requires a new session to take effect):

  ```
  setx WEB_ADMIN_HASH "$2b$12$..."   # Persistent for the current user (restart required)
  ```

  For services, prefer setting environment variables at the service configuration level or use a process manager that injects env vars.

- Use an OS or cloud secret store for production deployments (recommended):
  - Windows: Credential Manager, DPAPI wrappers, or local secret stores integrated with the service account.
  - Cloud: Azure Key Vault, AWS Secrets Manager, Google Secret Manager.
  - Other: HashiCorp Vault, Kubernetes Secrets (when running in k8s).
  These services provide access controls, audit logs, secret rotation, and secure APIs for retrieving secrets at runtime.

- Avoid committing `config.yaml` containing secrets or hashes to version control. Use `.gitignore` or other repository safeguards.

- Rotate admin passwords and hashes regularly, log access to the configuration file, and apply the principle of least privilege to any accounts that can read the file.

- If you adopt an environment-variable or secret-store approach, ensure the application loads secrets securely at startup and does not inadvertently log secret values.

Updated Security Notes (summary from existing section):

- Always use strong, unique passwords.
- Protect `config.yaml` and any backups containing password hashes by restricting NTFS permissions and avoiding public sharing.
- Prefer environment variables or a dedicated secret store (Azure Key Vault, HashiCorp Vault, AWS Secrets Manager, Windows Credential Manager) for production secrets.
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

#### 4.5.4. Operator and Admin State Views

- Operators use `/app/processing`, `/app/batches/{batch_id}`, `/app/documents/{document_id}/extraction`, `/app/review`, `/app/reports`, and `/app/settings`.
- Administrators use `/app/admin`, `/app/admin/pipeline`, `/app/admin/tasks`, `/app/admin/review-gate`, `/app/admin/split`, `/app/admin/audit`, and `/app/admin/dry-run`.
- Legacy `/dashboard`, `/api/files`, and `/api/status/{file_id}` are compatibility paths only.

#### 4.5.5. Admin Workflow Details

The `/app/admin/*` pages provide configuration and governance workflows for administrators:

- `/app/admin`: configuration health, schema validation summary, pipeline summary, review-gate status, split status, and recent audit events.
- `/app/admin/pipeline`: create or update a pipeline draft, review a diff against the active configuration, validate the draft, and publish it when validation has no blocking errors.
- `/app/admin/tasks`: inspect available task classes and their configured module/class information.
- `/app/admin/review-gate`: maintain review thresholds, field/document-type overrides, review scope, queue name, schema reference, and resume policy.
- `/app/admin/split`: maintain non-secret split settings such as enablement, categories, uncategorized behavior, split directory, saved configuration ID, project/organization IDs, polling interval, and timeout.
- `/app/admin/dry-run`: preview split, extraction, review-gate, and export decisions without writing final exports or workflow state.
- `/app/admin/audit`: review administrative and governance events such as settings changes, pipeline publishing, split tests, and schema changes.
- `/app/settings/validation`: review active configuration, schema, and pipeline validation findings.

Admin access is role-aware. When roles are enabled, users listed in `auth.default_admin_users` or `ui.default_admin_users` can access admin pages. If no admin list is configured, the configured `authentication.username` is treated as the administrator. Secret values are not exposed through runtime settings, and split settings updates do not save secret keys such as `api_key`; configure those secrets through `config.yaml` or your deployment secret-management process.

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
  - Files over 10MB may cause noticeable processing delays.
  - Files over 100MB may cause significant delays or memory issues.
  - Monitor system resources during large file processing (check Task Manager on Windows).
  - Consider processing very large files during off-peak hours.
  - The system processes files sequentially, so large files will block other files until complete.
- During runtime troubleshooting:
  - Failed tasks log detailed errors to `app.log` with timestamps and context information.
  - Files with processing errors may remain in the `processing/` directory; inspect `/app/processing`, document task runs, and `app.log`.
  - Check the unified web app for real-time status updates on file processing.
  - Use `Ctrl+C` for graceful shutdown to allow current tasks to complete before stopping.
- Common runtime issues and solutions:
  - **High memory usage**: Large PDF files (>50MB) can consume significant RAM during processing.
  - **Slow processing**: Check internet connectivity for cloud extraction providers.
  - **Files stuck in processing**: Verify API credentials and rate limits with your extraction provider.
  - **Permission errors**: Ensure all configured directories have proper read/write permissions.
- Log monitoring tips:
  - Look for "CRITICAL" messages that indicate startup failures.
  - "ERROR" messages show task failures with specific details.
  - "WARNING" messages indicate non-fatal issues that may affect performance.
  - Use the web interface to monitor processing status in real-time.

### 4.7. Graceful Shutdown and Error Recovery

- To stop the system, press `Ctrl+C` in the terminal where `main.py` is running.
- The system will finish processing any files currently in progress before shutting down.
- The system automatically runs cleanup tasks during shutdown to ensure proper resource cleanup.
- Shutdown progress is logged to `app.log` for monitoring.
- If shutdown appears to hang, check the log file for any errors during cleanup tasks.
- Graceful shutdown process:
  1. `Ctrl+C` signal is received
  2. Watch folder monitor stops accepting new files
  3. Current file processing completes
  4. Web server (if running) terminates gracefully
  5. Cleanup tasks run to remove temporary files
  6. All connections and resources are closed
  7. Final log message confirms clean shutdown
- If the system fails to start:
  - Check `app.log` for detailed error messages with timestamps.
  - Verify all required folders exist (watch_folder, web_upload must pre-exist).
  - Validate `config.yaml` syntax using a YAML validator.
  - Ensure internet access if using cloud extraction providers.
  - Check that the LlamaCloud `api_key` is valid and not expired. If using a saved Extract v2 configuration, also verify `configuration_id`.
  - Verify user permissions on all configured directories.
  - The system logs detailed startup progress including folder validation and cleanup task registration.
- Recovery from crashes:
  - Restart the system using the startup command.
  - Check `app.log` for any corrupted files or incomplete operations.
  - Files in `processing/` directory may need manual cleanup if marked as failed.
  - The system will automatically resume monitoring the watch folder after restart.

### 4.8. Task System: Standard Steps and Parameters

Standard steps are predefined operations configured in workflows. Below are the main task types and their parameters.

#### 4.8.1. extraction

- **type:** `"extraction"`
- **Purpose:** Extracts structured data from PDF documents using external extraction services.
- **params:**
  - `provider`: string, currently LlamaCloud Extract v2 through the `llama-cloud` SDK.
  - `api_key`: string, required LlamaCloud credential.
  - `configuration_id`: optional saved Extract v2 configuration ID from the LlamaCloud UI. If omitted, the task builds an inline schema from `fields`.
  - `tier`: optional Extract v2 tier, default `"agentic"`.
  - `parse_tier`: optional Parse tier for inline extraction.
  - `extraction_target`: optional target, default `"per_doc"`.
  - `cite_sources`: optional boolean to request citation metadata.
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
  - Do not use `agent_id` for new configurations. It is a legacy Extract v1/LlamaExtract-era parameter and is not required by the current Extract v2 runtime.
  - Field names and types must match the provider's schema.
  - Internet access over HTTPS is required.

**YAML configuration example:**

```yaml
tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: "llx-REDACTED"
      configuration_id: "YOUR-EXTRACT-V2-CONFIGURATION-ID"  # optional
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

#### 4.8.2. split.llamacloud_split

- **type:** `"split.llamacloud_split"`
- **Purpose:** Optionally splits a source PDF into child PDF documents before downstream extraction and storage tasks run.
- **params:**
  - `enabled`: boolean. If `false`, the task records a skipped split result and the source document continues as a normal document.
  - `api_key`: string. Required at runtime when the real LlamaCloud split adapter is used.
  - `configuration_id`: optional saved LlamaCloud split configuration ID.
  - `categories`: optional list of category definitions. Required when `configuration_id` is not provided.
  - `allow_uncategorized`: string, one of `"include"`, `"forbid"`, or `"omit"`. Default is `"include"`.
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

**YAML configuration example:**

```yaml
tasks:
  split_documents:
    module: standard_step.split.llamacloud_split
    class: LlamaCloudSplitTask
    params:
      enabled: true
      api_key: "llx-REDACTED"
      configuration_id: "YOUR-SPLIT-CONFIGURATION-ID"  # optional
      categories:
        - name: "invoice"
          description: "Supplier invoice pages"
        - name: "supporting_document"
          description: "Delivery orders, receipts, or supporting pages"
      allow_uncategorized: "include"
      split_dir: "data/app/split"
      poll_interval_seconds: 1.0
      timeout_seconds: 7200
    on_error: stop

pipeline:
  - split_documents
  - extract_document_data
  - store_metadata_json
```

Fan-in aggregate statuses shown in the app include:

- `completed`: all leaf documents completed successfully.
- `completed_with_errors`: one or more leaf documents failed after all leaves reached a terminal state.
- `review_required`: one or more leaf documents require review or are in review.
- `processing`: at least one leaf document is still running.

#### 4.8.3. storage.store_metadata_as_csv

- **type:** `"storage.store_metadata_as_csv"`
- **Purpose:** Stores extracted metadata as CSV files with consistent column headers.
- **params:**
  - `data_dir`: string (required). Destination folder for CSV.
  - `filename`: string (required). Base filename template; `.csv` is auto-added.
- **Behavior:**
  - Accepts `context["data"]` as a dict or list of dicts.
  - Writes a CSV with headers based on field aliases (if `fields` were provided in extraction).
  - Sanitizes values for CSV (replaces newlines with spaces, joins lists with commas).
  - Generates a unique filename to avoid overwrites.

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

- **type:** `"storage.store_metadata_as_json"`
- **Purpose:** Stores extracted metadata as JSON files with consistent key naming.
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
  - `require_review_when_missing_confidence`: boolean. Default is `true`.
  - `require_review_for_missing_required_fields`: boolean. Default is `true` when schema validation is used.
  - `always_review`: boolean. If `true`, every document entering this task requires review.
  - `schema_file`: optional schema name used to validate corrected/final field values.
  - `queue_name`: review queue name. Defaults to `review.default_queue_name` or `default_review`.
  - `review_scope`: review scope, commonly `"low_confidence_fields"`.
  - `allow_operator_to_edit_high_confidence_fields`: boolean. Default is `true`.
  - `resume_policy`: currently supports `"next_task"`.
- **Behavior:**
  - Evaluates persisted extracted fields, confidence values, missing-confidence conditions, schema errors, split confidence, and business rule flags.
  - Marks fields requiring review and creates a review queue item in SQLite when review is required.
  - Sets document state to `review_required` and pauses the workflow.
  - Operators can claim the item, save draft corrections, preview diffs, and complete review from `/app/review/{review_item_id}`.
  - Completed corrections are persisted in SQLite and the document resumes downstream workflow steps according to `resume_policy`.
- **Locking:** Review claims use `review.lock_timeout_minutes`, defaulting to 60 minutes.

**YAML configuration example:**

```yaml
tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf_v2
    class: ExtractPdfV2Task
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
    module: standard_step.storage.store_metadata_as_json_v2
    class: StoreMetadataAsJsonV2
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

### 4.9. LlamaCloud Extract v2 Array-of-Objects Support

The v2 extraction and storage system handles LlamaCloud Extract v2 responses containing arrays of objects, such as invoice line items or multiple entries that need to be processed individually.

#### 4.9.1. Overview

The v2 system allows extraction of structured data where certain fields return lists of sub-objects. For example, an invoice might have an "Items" field containing multiple line items with descriptions, quantities, and prices.

#### 4.9.2. Configuration

To use v2 features, update your `config.yaml` to:

1. Use the v2 extraction task:
   ```yaml
   extract_document_data:
     module: standard_step.extraction.extract_pdf_v2
     class: ExtractPdfV2Task
     params:
       api_key: "llx-REDACTED"
       configuration_id: "YOUR-EXTRACT-V2-CONFIGURATION-ID"  # optional
       tier: "agentic"
       parse_tier: "agentic"          # optional
       extraction_target: "per_doc"   # optional
       cite_sources: true             # optional
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

#### 4.9.3. Storage Behavior

##### JSON Storage (v2)
- Preserves the list-of-objects structure for table fields.
- Configured fields are written under their aliases when aliases are present; otherwise workflow field keys are preserved.
- Maintains backward compatibility with scalar-only data.

##### CSV Storage (v2)
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

To migrate from v1 to v2:

1. Update extraction task to use v2 module:
   ```yaml
   module: standard_step.extraction.extract_pdf_v2
   class: ExtractPdfV2Task
   ```

2. Add `is_table: true` to array fields in your extraction configuration.

3. Optionally update storage tasks to use v2 modules:
   ```yaml
   # JSON v2
   module: standard_step.storage.store_metadata_as_json_v2
   class: StoreMetadataAsJsonV2

   # CSV v2
   module: standard_step.storage.store_metadata_as_csv_v2
   class: StoreMetadataAsCsvV2
   ```

4. After the LlamaCloud UI configuration is ready, test with a small set of documents before full deployment.

5. Validate a saved LlamaCloud configuration with the smoke checker:

   ```powershell
   C:\Python313\python.exe tools\llamacloud_extract_smoke.py --config dev_config.yaml --file sample_invoice.pdf --configuration-id "cfg-..."
   ```

   If `configuration_id` is already set in the selected config file, omit the override flag. The smoke checker writes `raw_extract_result.json`, `workflow_normalized_data.json`, and `workflow_fit_report.json`.

#### 4.9.5. Current Limitations

- Only one `is_table: true` field is supported per extraction.
- Items must be simple dictionaries (no nested arrays or objects).
- Complex nested structures may require additional processing logic.

---

### 4.10. Example Workflows

**Production-style pipeline example (matches current code and `config.yaml`):**

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
    class:  ExtractPdfTask
    params:
      api_key: "llx-REDACTED"
      configuration_id: "YOUR-EXTRACT-V2-CONFIGURATION-ID"  # optional
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
    class:  StoreMetadataAsCsv
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

  store_metadata_json:
    module: standard_step.storage.store_metadata_as_json
    class:  StoreMetadataAsJson
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

  store_file_to_localdrive:
    module: standard_step.storage.store_file_to_localdrive
    class:  StoreFileToLocaldrive
    params:
      files_dir: "files"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

  archive_pdf:
    module: standard_step.archiver.archive_pdf
    class:  ArchivePdfTask
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
- The three storage-related tasks are separate:
  - `store_metadata_csv` writes CSV to `data_dir` using `filename` template.
  - `store_metadata_json` writes JSON to `data_dir` using `filename` template.
  - `store_file_to_localdrive` moves the original PDF to `files_dir` using `filename`.
- Field placeholders in `filename` come from extracted data keys (e.g., `{supplier_name}`, `{invoice_amount}`, `{policy_number}`).
- Use `on_error: stop|continue` per task to control failure behavior.
### 4.11. Housekeeping and the Processing Folder

- The `processing_dir` contains temporary working files during processing. Workflow state is stored in SQLite.
- The housekeeping cleanup task automatically executes as the final step in every workflow, deleting the processed PDF from `processing_dir` so the folder stays small. It does not remove durable registered artifacts.
- It always runs, regardless of pipeline success or failure, to guarantee the processing directory is cleared of that PDF.
- Any old text status files are legacy diagnostics only and are not required for current workflow state.

---

### 4.12. Config Check Validation Tool

**Audience:** Administrators (end users should contact an administrator if configuration changes are required).

The `config-check` utility lives under `tools/config_check` and validates `config.yaml` before you deploy or restart services. Run it whenever you modify tasks, pipelines, or environment-specific paths--especially after applying workflow updates from product tasks 13-19.

**Core workflow**
- Use `C:\Windows\System32\cmd.exe` or PowerShell from the project root.
- Execute `C:\Python313\python.exe -m tools.config_check validate --config config.yaml --base-dir .` to lint the active configuration.
- Pass `--format json` when you need machine-readable output for ticket attachments or CI logs.
- Treat exit code `0` as success, `1` as blocking errors, and `2` as warnings that still need follow-up.

**When to escalate**
- Review `tools/config_check/README.md` for CLI flag details and examples.
- Cross-reference `docs/config_check_troubleshooting.md` to resolve the common findings surfaced by tasks 13-19 (credential gaps, storage overrides, token mismatches, and similar issues).
- If end users report workflow failures, run the validator before redeploying--most misconfigurations are caught here without rerunning full jobs.

Administrators should share validator output with end users only when requesting missing information (for example, credential placeholders or directory paths). End users do not need to run the tool directly but should know that configuration changes will be certified via `config-check` before they go live.

## 5. Frequently Asked Questions (FAQ)

**Q: Does the program require internet access?**  
A: Yes, for cloud providers such as LlamaCloud Extract v2 via HTTPS.

**Q: Where are my processed files stored?**
A: Processed PDF documents are saved by the "`store_file_to_localdrive`" task to the folder configured at `tasks.store_file_to_localdrive.params.files_dir`. Extracted metadata is saved separately:
- CSV files: `tasks.store_metadata_csv.params.data_dir`
- JSON files: `tasks.store_metadata_json.params.data_dir`

When SQLite document context exists, generated PDFs, CSV files, JSON files, archives, source originals, and split PDFs are also registered as document artifacts in SQLite. Split child PDFs are written to the configured split task directory at `tasks.<split_task>.params.split_dir`.

**Q: What happens if the same filename already exists?**
A: Storage tasks generate unique filenames automatically by appending a numeric suffix (`_1`, `_2`, …) to avoid overwriting, as implemented by the utility in [`modules.utils.generate_unique_filepath()`](modules/utils.py:95).

**Q: What are provider limits?**  
A: LlamaCloud Extract and LlamaParse limits include max file size and processing time; consult the current provider documentation for your workspace and tier.

**Q: How do I edit the configuration file safely?**  
A: Use a plain text editor, preserve indentation, back up before changes, and restart the system after saving.

**Q: How do I set folder permissions on Windows?**
A: Right-click the folder, select Properties > Security tab, and ensure the system user has Modify or Write permissions.

**Q: Why do I get "Invalid credentials" error when logging into the web interface?**
A: Verify that the `authentication.username` and `authentication.password_hash` values in `config.yaml` match your intended login credentials. The username should be a plain text string, and the password_hash should be a valid bcrypt hash. If you've forgotten your password, regenerate the hash using the bcrypt command shown in section 4.4 and update the configuration.

**Q: Why does my login session expire quickly or tokens become invalid?**
A: Authentication tokens are valid for 30 minutes by default. If sessions are expiring too quickly, ensure your system's clock is accurate, as token expiration is time-sensitive. Administrators can adjust the timeout with `web.token_exp_minutes` in `config.yaml`.

**Q: How do I reset or change the web interface password?**
A: Update the `authentication.password_hash` value in `config.yaml` with a new bcrypt hash. Generate the hash using the helper shown in section 4.4:
```
C:\Python313\python.exe tools\generate_password_hash.py --password "new_password"
```
Replace `new_password` with your desired password and update the configuration file.

**Q: How do I verify my authentication configuration is correct?**
A: Ensure these values are properly set in `config.yaml`: `authentication.username` (plain text username), `authentication.password_hash` (bcrypt hash starting with $2b$), and `web.secret_key` (random string for token signing). Test the configuration by restarting the system and attempting to log in through the web interface.

**Q: Why is processing slow for large PDF files?**
A: Files over 10MB may cause noticeable delays due to synchronous file I/O operations and external extraction processing. Files over 100MB may cause significant delays or memory pressure. The system processes workflow files sequentially, so one large file can delay later files. Monitor `/app/processing`, document task runs, and `app.log` during large file processing.

**Q: What should I do if the system appears stuck processing a file?**
A: Check `/app/processing` or `/app/batches/{batch_id}` first to see the document, task-run, split, extraction, and review state. Then check `app.log` for provider errors, timeouts, validation errors, or filesystem issues. Large files (>100MB) may take considerable time to process. If the app itself is unresponsive, check system resources such as CPU, memory, and disk space.

**Q: How can I improve performance for many files or large files?**
A: For many files, ensure adequate CPU, memory, disk, and network capacity, and monitor provider quota or rate-limit messages. For very large files, process them during off-peak hours, keep enough free disk space for processing/split/export artifacts, and watch `/app/processing` plus `app.log` for slow task runs.

**Q: What are the recommended system requirements for optimal performance?**
A: For basic operation: 4GB RAM, 2GB free disk space, stable internet connection. For processing many large files (>50MB): 8GB+ RAM, SSD storage, high-speed internet. The system is designed to run on modest hardware but performance scales with available resources.

**Q: How can I monitor system performance during operation?**
A: Use Windows Task Manager to monitor CPU, memory, and disk usage. Watch the `app.log` file for performance warnings. Use `/app/processing`, `/app/batches/{batch_id}`, and `/app/reports` to monitor processing queue length, file status, and review activity. Check system resources before processing large batches of files.

**Q: What should I do if the system becomes unresponsive during large file processing?**
A: Large files (>100MB) can cause temporary unresponsiveness. Wait for current processing to complete when `/app/processing` or `app.log` still shows progress. If the system remains unresponsive for more than 30 minutes and no progress is visible, stop it with `Ctrl+C`, restart with the normal startup command, and inspect the affected document state before reprocessing. Consider processing very large files individually during off-peak hours.

**Q: How do I handle API rate limiting from extraction providers?**
A: The v2 extraction task retries transient extraction failures, and workflow task wrappers also retry task execution. Persistent provider rate limits may still fail after retries. Monitor `app.log`, provider quota dashboards, and document task-run errors, then retry or reprocess after the provider limit clears. For recurring rate limits, reduce ingestion volume, process during off-peak hours, or upgrade the provider plan.

**Q: What should I do if archiving fails due to directory permissions?**
A: Ensure the `archive_dir` configured in `tasks.archive_pdf.params.archive_dir` exists, is a directory, and grants write/Modify permission to the account running the application. Startup path validation checks configured `_dir` paths, but archive copy permission failures can still appear at runtime. If archiving fails, inspect `/app/processing`, the document task runs, and `app.log`. When document context exists, successful archive copies are registered as `source_archive` artifacts in SQLite.

**Q: Why do large PDF files (>50MB) cause extended processing times?**
A: Large files require more processing time due to increased I/O, PDF handling, split/extraction work, and provider processing time. This is the same underlying cause described in the large-file performance questions above. Monitor system resources, `/app/processing`, and `app.log`, and consider processing very large files individually.

**Q: What happens when reference file matching fails in the update_reference task?**
A: When field values required for matching are not found in the pipeline context, the task logs a warning and continues without matching any rows. The task will not append new rows. It updates matched rows only, creating the configured `update_field` column at runtime if needed. Check your extraction field configuration and ensure the required fields (like `purchase_order_number` or `invoice_amount`) are being extracted correctly.

**Q: Why is my document waiting for review?**
A: A configured review gate can pause a document when extracted field confidence is below threshold, confidence is missing, required/schema fields are missing or invalid, split confidence rules require review, business-rule flags request review, or `always_review` is enabled. Operators should open `/app/review`, claim the item, inspect the PDF and fields, then complete review when corrected values are ready.

**Q: What happens after review is completed?**
A: Corrected values are persisted in SQLite with the document extraction state. If the review gate uses `resume_policy: "next_task"`, the document resumes the downstream workflow steps after review completion.

**Q: Why did one uploaded PDF become multiple documents?**
A: If the split task is configured and enabled, the source PDF can be split into child documents based on provider segments, categories, confidence, and page ranges. Use `/app/batches/{batch_id}/split-results` to inspect source documents, child document IDs, categories, confidence, pages, and statuses.

**Q: Can administrators change pipeline, review, or split settings in the UI?**
A: Yes. Admin users can use `/app/admin/pipeline` for pipeline draft/diff/validate/publish workflows, `/app/admin/review-gate` for review rules, `/app/admin/split` for non-secret split settings, `/app/admin/dry-run` for previews, and `/app/settings/validation` for validation findings. Secret values such as `api_key` are not saved through split settings and should be managed through `config.yaml` or deployment secret management.

**Q: How do I troubleshoot "Invalid credentials" errors during PDF extraction?**
A: The system validates the required LlamaCloud `api_key` before processing. If you use a saved Extract v2 configuration, ensure `configuration_id` exists in the correct LlamaCloud project. Check `app.log` for detailed credential and extraction errors.

---


## 6. Appendix

### Glossary

- **Workflow:** An ordered list of tasks configured in `config.yaml` applied to every processed file.  
- **Task (Standard Step):** A single operation in the pipeline, e.g., `split.llamacloud_split`, `extraction`, `review.review_gate`, `rules.update_reference`, `storage.store_metadata_as_csv`, `storage.store_metadata_as_json`, `archiver.post_process`, `housekeeping.cleanup`.
- **Alias:** Display/output field name used as CSV headers/JSON keys and in reference files for consistency.  
- **Watch Folder:** The `watch_folder.dir` monitored for new PDFs.  
- **YAML:** A human-readable configuration file format that uses indentation to organize settings.  
- **API Key:** A secret credential used to authenticate with external services.  
- **Regex:** A pattern used to match text, such as filenames.

### Example Configuration Files

See sections 4.3.1 and 4.8 for complete examples. Use them as templates and adjust paths and credentials to your environment.

### Further Documentation

- System Architecture: [`docs/design_architecture.md`](docs/design_architecture.md)  
- Product Requirements: [`tasks/prd-redesigned-pdf-processing.md`](tasks/prd-redesigned-pdf-processing.md)  
### Legacy Code Notice

Please note that the code located in the `OLD_VERSION/llamaextract` directory is legacy code from a previous iteration of the program. It is not part of the current rewritten system and should be ignored for current development and usage.

---

This guide documents the configurable, task-based workflow system, including the unified `/app/*` interface for upload, processing, review, reporting, settings, and administration.
