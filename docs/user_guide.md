<!--
PDF Processing System: User Guide (Configurable Tasks Edition)
Version: 3.0
Release Date: 2026-08-02
Author: [Your Organization/Name]
-->

# PDF Processing System: User Guide (Configurable Tasks Edition)

---
Version: 3.0
Release Date: 2026-08-02
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
    - [4.2.1. Pre-existing vs Auto-created folders](#421-pre-existing-vs-auto-created-folders-consolidated)
  - [4.3. Configuration Management](#43-configuration-management)
    - [4.3.1. High-level Structure](#431-high-level-structure)
    - [4.3.2. Global Sections](#432-global-sections)
    - [4.3.3. Pipeline Configuration](#433-pipeline-configuration)
  - [4.4. Managing Application Accounts and Passwords](#44-managing-application-accounts-and-passwords)
  - [4.5. Database, State, and Artifact Storage](#45-database-state-and-artifact-storage)
    - [4.5.1. Database Initialization](#451-database-initialization)
    - [4.5.2. What SQLite Stores](#452-what-sqlite-stores)
    - [4.5.3. Filesystem Artifact Boundaries](#453-filesystem-artifact-boundaries)
    - [4.5.4. Operator and Administrator State Views](#454-operator-and-administrator-state-views)
    - [4.5.5. Administrator Workflow Details](#455-administrator-workflow-details)
      - [Create and publish a pipeline visually](#create-and-publish-a-pipeline-visually)
      - [Create and publish a review form visually](#create-and-publish-a-review-form-visually)
      - [Add a watch-folder binding visually](#add-a-watch-folder-binding-visually)
      - [Use Overview, Settings, Task Catalog, and Validation](#use-overview-settings-task-catalog-and-validation)
      - [Administrator Audit History](#administrator-audit-history)
    - [4.5.6. Backup and Recovery](#456-backup-and-recovery)
  - [4.6. Log Files and Troubleshooting](#46-log-files-and-troubleshooting)
  - [4.7. Graceful Shutdown and Error Recovery](#47-graceful-shutdown-and-error-recovery)
  - [4.8. Task System: Standard Steps and Parameters](#48-task-system-standard-steps-and-parameters)
       - [4.8.1. extraction](#481-extraction)
         - [GLM-OCR extraction (local Ollama)](#glm-ocr-extraction-local-ollama)
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
| 2.9     | 2026-07-26 | [Your Organization] | Documented SQLite-backed, immutable pipeline and review-schema versions, explicit upload selection, watch-folder bindings, exact-version execution, migration, recovery, and stored-definition validation |
| 3.0     | 2026-08-02 | [Your Organization] | Completed the operator and administrator procedures for multi-pipeline routing, review forms, watch-folder bindings, outputs, validation, settings, audit visibility, and portable definitions; corrected remaining single-pipeline and task-behavior guidance |

---

## Quick Start Guide

This quick start separates administrator setup from normal operator work.

**Administrator: first-time setup**

1. Create the startup compatibility folder configured by `watch_folder.dir`
   and the upload staging folder configured by `web.upload_dir`. Both must
   already exist and allow the application account to read and write files.
2. Initialize the fixed administrator and operator accounts:

    ```powershell
    .\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml
    ```

3. Start the system from the project folder:

    ```
    .\.venv\Scripts\python.exe main.py
    ```

4. Open the configured web address and test both accounts.
5. As the administrator, create or import a review form when the workflow needs
   human review, publish an immutable form version, then create a pipeline,
   save and validate its draft, publish a version, and set the pipeline to
   **Active**. Section 4.5.5 gives the complete procedure.
6. For folder ingestion, create each real incoming folder on disk and add its
   exact-version binding in the **Watch-folder bindings** panel on **Pipeline**.
7. Run the Config Check tool described in section 4.12 before processing production documents.

**Operator: process documents**

1. Open the web address provided by your administrator and sign in with the operator account.
2. Select **Upload & Process** from the left navigation menu.
3. Select the PDF files, choose an eligible published pipeline version, and
   choose **Start Processing**. One selection applies to the entire batch.
4. Follow the batch progress shown after upload.
5. Use **Review Queue** for documents requiring correction and **Failures** for documents that could not be processed.
6. Ask an administrator for help when a failure requires configuration or provider changes.

To stop the service, the administrator presses `Ctrl+C` in the terminal and then checks any document that was processing, as described in section 4.7.

---

## 1. Overview

The PDF Processing System automates extracting information from PDF documents. This version introduces:

Key features:  
- Multiple named pipeline templates with editable drafts and immutable
  published versions stored in SQLite.
- Explicit pipeline-version selection for uploads and exact version bindings
  for watch folders.
- YAML and JSON for deployment settings, validation, migration, and portable
  import/export rather than mutable runtime pipeline authority.
- Extensible standard steps: split, extraction, review, rules, storage, archiving, housekeeping
  *(Standard steps are predefined operations that the system performs on each file.)*  
- Centralized configuration and logging  
- Watch-folder based ingestion and web interface for PDF upload
- SQLite-backed workflow state for batches, documents, task runs, extraction results, review items, artifacts, settings, and audit history
- Role-based web interface for operators and administrators
- Isolated per-pipeline CSV/JSON output with optional task-specific aliases
  *(Alias means a friendly name used for data fields in outputs, such as column headers.)*

Internet access is required for cloud-based extraction providers such as LlamaCloud Extract v2.

---

## 2. System Architecture & Data Flow

### Components

- **Watch Folder Coordinator:** Scans every enabled SQLite watch-folder binding.
  Each binding maps one existing, non-overlapping directory to one exact
  published pipeline version. `watch_folder.processing_dir` is the shared
  temporary work area. The deployment key `watch_folder.dir` must still
  pre-exist for startup compatibility, but it does not choose the pipeline or
  replace the SQLite bindings.
- **Workflow Manager and Loader:** Loads the exact immutable pipeline version
  assigned at ingestion and carries that version through split, review resume,
  retry, and recovery.
- **Standard Steps:** Executes ordered tasks for each file (split, extraction, review, rules, storage, archiver, housekeeping).
- **SQLite State Services:** Record ingestion batches, documents, task runs, extracted fields, review queues, artifacts, settings, and audit events.
- **Storage:** Writes extracted data to CSV/JSON and copies PDFs to their final destination.
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
      Storage -->|Organized Files| Output[Pipeline-version output folders]
      Storage -->|Child Status Change| FanIn[Update Source and Batch - Fan-in]
      Steps -->|Post-process| Archiver[Archive/Delete Input]
      Steps -->|State Events| SQLite[SQLite State Database]
      Split -->|Parent/Child State| SQLite
      ReviewQueue -->|Drafts, Diffs, Decisions| SQLite
      FanIn -->|Batch/Parent Status| SQLite
      SQLite -->|Batches, Documents, Reviews| AppUI[Unified Web Interface]
```

### What happens to your document?

1. Submission: You upload PDFs and select a published version, or place a PDF
   in an administrator-provided bound watch folder.
2. Assignment: An upload uses the operator-selected published version; a
   watched file uses the exact published version in its folder binding.
3. State record: The system creates SQLite batch/document records and a task-run record for each configured step.
4. Extraction: Information is extracted through LlamaCloud Extract v2 and field values/confidence are persisted.
5. Review gate: Optional rules decide whether the document needs human review.
6. Rules: Optional business logic runs (e.g., update reference files).
7. Storage: The PDF and extracted metadata are written to the exact pipeline
   version's configured output folders, and durable artifacts are registered in
   SQLite.
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

- A directory the administrator has bound to one exact published pipeline
  version. The application can monitor several independent folders at the same
  time, including several folders that use the same pipeline version.

**How to add files:**

1. Ask your administrator for the incoming folder assigned to your document
   type and confirm the pipeline name and version attached to it. Do not assume
   that the startup path in `watch_folder.dir` is the folder for your workflow.
2. Copy or move complete PDF files into that folder. Do not copy partial files
   or non-PDF content with a `.pdf` extension.
3. The coordinator detects the file and creates a batch pinned to the binding's
   exact pipeline version. Publishing a newer version does not change an
   existing binding automatically.

**What happens after upload:**

- The system moves accepted files into the configured processing directory (`watch_folder.processing_dir`) with temporary unique filenames.
- The exact pipeline version attached to the folder performs extraction and
  any other configured steps.
- Output locations depend on the storage tasks configured by the administrator.
- The coordinator checks the first five bytes for `%PDF-`, including files
  already present when the application starts. A file that fails remains in
  the incoming folder and is skipped. Replace or remove it before a later scan.
- Web upload size and file-count limits do not apply to the watch folder, but extraction-provider limits still apply.

**How to check completion:**

- Select **Reports**, find the watch-folder batch, and open **Processing** to
  confirm the batch, document, and task statuses.
- Select **Extraction** for a document to compare extracted and final values,
  confidence, the raw provider payload, the PDF preview, and registered files.
- A successful storage workflow normally registers a renamed PDF and its
  configured CSV/JSON exports. Their actual folders come from that pipeline
  version's task parameters; they are not necessarily `files/` and `data/`.
- If the document is waiting for review, use **Review Queue**. If it failed or
  expected artifacts do not appear, use **Failures** and ask an administrator
  to check `app.log` and the selected pipeline version.

### 3.2. Using the Web Interface

Ask your administrator for the system's web address and your account password.

**Sign in:**

1. Open the web address in your browser.
2. Select your assigned account, enter the password, and select **Sign In**.
3. After signing in, the application opens at **Upload & Process**.

**Upload PDF files:**

1. Select **Upload & Process** from the left navigation menu.
2. Under **Choose a processing pipeline**, select the exact published version
   appropriate for every file in this batch. No version is selected silently.
3. Select or drag the PDF documents into the upload area.
4. Review the selected-file list and remove any unintended file.
5. Select **Start Processing** to submit the documents.
6. The application opens the batch details so you can follow progress.

Only active, eligible pipeline versions appear. One choice applies to the
entire batch. If different documents need different pipelines, submit separate
batches. If the required version is missing, select **Refresh** once and then
ask an administrator to publish and activate it; do not choose a similar
pipeline merely to continue.

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

Administrators also see **Overview**, **Users**, **Pipeline**, **Review Forms**, **Task Catalog**, **Validation**, and **Audit Log**. These administrative areas are not available to operators.

**How to use the remaining operator pages:**

- **Processing Overview** is reached automatically after upload or through
  **Reports** > **Processing**. It shows pipeline steps, batch/document status,
  and links to extraction, split, review, or failure details as applicable.
- **Extraction** shows the source or stored PDF, registered artifacts,
  extracted versus final values, confidence bands, review status, and the raw
  provider payload. **Previous** and **Next** move among documents in the same
  batch. This page is evidence of processing, not an editing screen.
- **Reports** summarizes batches and documents, persisted statuses, ingestion
  sources, review counts, completed/failed totals, average task-run span, and
  recent batches. Select a recent batch for details and its **Processing** link.
- **Settings** is read-only for operators. It exposes safe deployment paths and
  runtime summaries with secret-like values redacted. In a multi-pipeline
  deployment, a zero or empty legacy pipeline summary on this page does not
  mean that SQLite pipeline versions are absent; use the pipeline shown on the
  batch/document instead.

#### Human Review

Documents enter the review queue when the system cannot confidently accept the extracted information or when an administrator requires review.

1. Select **Review Queue** from the left navigation menu.
2. Use the search and filters to find the document.
3. Select **Claim** beside an available document. This atomically reserves the
   item and opens its review screen. Select **View** when you only need to
   inspect it.
4. If you opened an unclaimed item through **View**, select **Claim** at the top
   before editing. An active claim prevents another operator from editing it.
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

- administrators maintain review forms from **Review Forms**;
- operators work on documents from **Review Queue**;
- drafts, comparisons, corrections, and completed values remain associated with the document;
- administrators validate stored drafts in **Review Forms** and **Pipeline**;
  **Validation** remains the deployment/pasted-file diagnostic surface;
- administrator actions are retained in SQLite audit history; the current
  **Audit Log** page shows the `admin_` subset described in section 4.5.5.

Administrators should use the unified Review Form Editor to maintain review schemas. Operators should use the review queue rather than editing schema files directly.

#### Split Results

When split processing is enabled, one uploaded PDF may create several child documents. The system processes each child separately after the split. One child may finish while another is still processing or waiting in **Review Queue**. Finishing the split does not mean that all child documents have finished; the original PDF is complete only after every child has reached a final status.

To check progress, select **Reports**, open the batch's **Processing** view, and
select **View Split Results**. This page shows:

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
- Each directory entered in **Pipeline** > **Watch-folder bindings** — the
  binding service requires it to exist, be accessible, and not overlap another
  bound path.
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
  dir: "watch_folder"                 # Startup-compatibility path (must pre-exist; not a pipeline binding)
  validate_pdf_header: true           # Validate %PDF header before processing
  processing_dir: "processing"        # Folder where files are moved with UUID name (auto-created if missing)

web:
  upload_dir: "web_upload"            # Web-upload staging directory (must pre-exist; validated at startup)
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
- **web:** Defines web upload directory and web server settings (host, port, secret key, optional CORS allowed origins).
- **database:** Defines the SQLite workflow-state path and migration behavior.
- **review:** Defines review queue behavior, queue name, and review lock duration.
- **ui:** Defines the application name, default page size, and whether
  administrator pages are enabled.
- **validation:** Defines validation availability, strict-mode default, and the
  allow-list switch for browser configuration saves. A save remains limited to
  the non-secret keys displayed on **Overview**.
- **auth:** Defines login failure rate limiting, attempt window, and cooldown.
  Session duration is `web.token_exp_minutes`.
- **pipeline_secrets:** Maps administrator-visible aliases to deployment-owned
  provider credentials. Pipeline drafts store only `$secret` aliases, never
  resolved values.
- **custom_steps:** Deployment approval for exact `custom_step.*` module/class
  pairs. Enabling or approving a class does not add it to any pipeline.
- **schema_config** and filesystem schema paths are migration/validation inputs;
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

### 4.4. Managing Application Accounts and Passwords

The application has two fixed accounts:

- **admin:** can use all operator and administrator features.
- **operator:** can upload, monitor, review, investigate failures, view reports, and view non-secret settings.

The account names and roles cannot be changed. Passwords are stored in the SQLite database configured by `database.path`; they are not read from an `authentication` section in runtime YAML.

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
.\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml --reset
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

The database location is configured by `database.path`, with a default of `data/app_state.sqlite3`. When `database.run_migrations_on_startup` is true, migrations run during application process startup rather than during individual HTTP requests. Legacy or direct ingestion helpers may also perform defensive idempotent initialization before creating workflow state.

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

- **Overview:** review configuration health, pipeline and review summaries, split status, and recent audit events.
- **Users:** change the administrator or operator password after confirming the current administrator password.
- **Pipeline:** create or clone templates, manage lifecycle state, maintain task
  order and parameters, select exact published review-schema versions, compare
  versions with redacted diffs, and use **Save Draft** -> **Validate** ->
  **Publish**. Publishing creates the next immutable version in SQLite and
  never writes `config.yaml`. **New** and **Clone** open an application dialog
  for the stable key and display name.
- **Review Forms:** create or import a schema draft, configure its fields,
  validate it, publish immutable versions, inspect version history and
  dependencies, and export a portable definition. A schema must be published
  before it can be selected in a pipeline draft.
- **Watch-folder bindings:** in the bottom panel of **Pipeline**, add an
  existing incoming folder and pin it to an exact published version of the
  selected pipeline. The current visual page lists existing bindings but does
  not provide edit, disable, or delete controls; see the procedure below.
- **Task Catalog:** inspect the workflow task classes available to the pipeline.
- **Validation:** review active configuration, schema, and pipeline findings.
- **Audit Log:** inspect the legacy `admin_` configuration/governance event
  subset; newer dot-named versioned events require the support path below.

##### Create and publish a pipeline visually

1. Sign in as `admin`, select **Pipeline**, then select **New**.
2. Enter a permanent lowercase kebab-case key and a clear display name. The key
   cannot be changed later. Complete **Document type** and **Description** so
   operators can distinguish otherwise similar choices.
3. In **Draft Pipeline**, choose a task from **Add task** and select **Add**.
   Repeat for each task, then use the step controls to order, rename, duplicate,
   or remove steps. **Task Catalog** explains each importable class.
4. Select each draft step and complete its properties. For LlamaCloud tasks,
   select a configured secret alias; the editor does not reveal the API key.
   For a review gate, select an exact **Published review form version**.
5. Select **Save Draft**. Saving is not publishing and cannot affect a running
   or future document until a version is published and eligible.
6. Select **Validate** and resolve every blocking finding. Use **Diff** to
   compare the saved draft with its published base. The diff is redacted.
7. Select **Publish** and confirm. Publication creates the next immutable
   numbered version. A draft with no change from its base cannot create a new
   version.
8. Use the status selector beside **Clone** and choose **Active**. An inactive
   pipeline, even one with a published version, is not available for new
   uploads or enabled bindings.
9. Sign in as an operator or open **Upload & Process**, select **Refresh**, and
   confirm the intended name and version appear before processing documents.

**Draft and version controls:** **Reset to Active** discards the current draft
model in the browser in favor of the published base, while **Refresh** reloads
saved state and warns about unsaved changes. **Clone** creates a new template
from a published source and requires a new permanent key/name. **Export** saves
the selected draft as portable YAML; **Import** replaces the selected
template's draft only and never publishes it. Always validate and inspect the
diff after an import. Existing batches, review resumes, split children, retries,
and recovery continue with their originally assigned version.

##### Create and publish a review form visually

1. Select **Review Forms**, then **New Review Form**. Enter its stable key and
   name in the prompts, then complete the title and description in the draft.
   Use a key that clearly identifies the business document type.
2. Add top-level fields with **String**, **Number**, **Boolean**, **Enum**,
   **Object**, or **Array**. For object fields use the nested **Add** controls;
   for arrays define their item type. Configure labels, required status,
   validation constraints, and field keys to match extraction output.
3. Select **Save draft**, then **Validate**. Resolve blocking findings and use
   the canonical preview to verify the complete structure.
4. Select **Publish** to create an immutable version, then set the form
   lifecycle to **Active** before selecting it in a pipeline review-gate task.
5. Return to **Pipeline**, select the review gate, and choose that exact
   published version. Save, validate, and publish the pipeline again.

The **Version history & dependencies** panel shows immutable form versions and
which published pipeline tasks depend on them. Changing and republishing a form
does not retarget an existing pipeline version. **Import** loads YAML/JSON into
a draft; **Export** downloads the current portable draft. For detailed field
constraints and patterns, use the [review schema administrator guide](review_schema_admin_guide.md).

##### Add a watch-folder binding visually

1. Create the real incoming folder on disk and grant the application account
   read, move/delete, and directory-list permissions. Do not bind a drive root.
2. On **Pipeline**, select the active template whose version will process the
   folder. In **Watch-folder bindings**, enter the absolute folder path, choose
   an exact published version, and select **Add binding**.
3. Confirm the list shows the normalized path, **enabled**, pipeline name, and
   version. Resolve any accessibility or eligibility finding before adding a PDF.
4. Place a test PDF in the folder and verify its watch-folder batch in
   **Reports** and **Processing Overview**.

Paths must be unique and non-overlapping: a folder cannot duplicate, contain,
or be contained by another binding. Multiple distinct folders may use the same
pipeline version. A binding never follows “latest”; publish does not retarget
it. Changes affect only files claimed afterward, while existing documents keep
their assigned version.

The current visual editor can add and list bindings only. To correct, disable,
retarget, or delete a binding, use the authenticated administrator API
`PATCH /api/admin/watch-folder-bindings/{binding_id}` or
`DELETE /api/admin/watch-folder-bindings/{binding_id}` through an approved
administration tool, or ask the application maintainer. Do not edit SQLite
directly. Disable a binding before archiving its pipeline. Deletion is rejected
after a batch references the binding so ingestion history remains explainable.

##### Use Overview, Settings, Task Catalog, and Validation

- **Overview** displays deployment/filesystem configuration health, legacy
  pipeline/review/split summaries, recent `admin_` events, and the allow-list of
  editable non-secret settings. Its Pipeline and published/draft metrics do not
  enumerate all new SQLite pipeline/review-form templates; use **Pipeline**,
  **Review Forms**, and config-check `--all-stored` for that inventory. **Save
  Settings** writes only the displayed keys (application name/page size,
  validation options, review queue name, and review lock timeout) to deployment
  configuration and SQLite history. It cannot save credentials.
- **Settings** is the read-only operator-safe view of deployment paths and
  redacted runtime summaries. It is not the authoritative list of all SQLite
  pipeline versions.
- **Task Catalog** is an inventory and diagnostic view: search or filter by
  category/import state, select a task to inspect its metadata, and use **Add in
  Pipeline** to open the editor. It does not alter a draft by itself.
- **Validation** can check the running deployment config, pasted YAML without
  saving it, the legacy active pipeline surface, and filesystem schema files.
  Review errors before warnings. For all SQLite templates, drafts, versions,
  review forms, and bindings, use section 4.12's `--all-stored` command.

##### Administrator Audit History

The **Audit Log** page at `/app/admin/audit` shows the append-only subset of
administrator history whose event type begins with `admin_`. It is available
only to the administrator role. Operational document events such as review
activity, processing failures, splitting, and fan-in completion are stored in
the same audit stream but are not shown on this page.

The following administrator events are currently recorded:

| Event type | Recorded when |
|------------|---------------|
| `admin_user_password_changed` | An administrator successfully changes the administrator or operator password. The event identifies the target account and successful outcome, but never contains either password. |
| `admin_user_password_change_rejected` | A password-change request is rejected, for example because the current administrator password is incorrect, the target account is unknown, the confirmation does not match, or the new password violates policy. The target, rejected outcome, and reason are recorded without credential material. |
| `admin_settings_updated` | An administrator changes an allow-listed, non-secret runtime setting. |
| `admin_review_gate_rules_updated` | Review queue, confidence threshold, field override, or related review-gate settings are changed. |
| `admin_split_settings_updated` | Non-secret split settings are changed. |
| `admin_split_connection_tested` | An administrator runs the split connection/status test. This records adapter status; the current test does not make a provider network request. |
| `admin_pipeline_draft_saved` | A pipeline draft is saved. |
| `admin_pipeline_validated` | A pipeline draft is validated. The result includes validity, a summary, and validation finding codes. |
| `admin_pipeline_published` | A validated pipeline draft is published as the active configuration. |
| `admin_schemas_validated` | Validation is run for all configured schemas. |
| `admin_schema_validated` | An individual schema draft is validated without being saved. |
| `admin_schema_created` | A schema is created. |
| `admin_schema_updated` | An existing schema is changed. |
| `admin_schema_duplicated` | An existing schema is copied to a new schema name. |

The versioned pipeline, review-form, and watch-binding services record newer
events with names such as `pipeline.template.created`,
`pipeline.version.published`, `review_schema.version.published`, and
`watch_binding.created`. These records are retained in SQLite but do not begin
with `admin_`, so the current **Audit Log** page does not display them. Use
SQLite backup/retention controls and an approved support query when that newer
governance history must be inspected; never change or delete audit rows. Do not
interpret an empty **Recent Admin Activity** panel as evidence that no
versioned configuration change occurred.

Each audit row has an immutable event ID, event type, acting user, and creation
time. Depending on the action, **Details** can also show structured `before` and
`after` values and metadata such as a configuration-version ID, validation
summary, finding codes or paths, schema name, schema hash, field count, or source
schema name. Fields that do not apply to an event are omitted or empty. Secret
settings and password values are not included in administrator audit payloads.

Events are displayed newest first. The page loads up to 100 matching events and
supports exact filtering by event type and user, plus inclusive **From** and
**To** creation timestamps. Select **Apply** to run the filters, **Clear** to
remove them, **Refresh** to reload the current view, and **Details** on an event
to inspect its complete structured payload. The event-type suggestions are
derived from the events in the current result set, but an exact event type can
also be typed directly.

Audit history is evidence of actions performed through these application
workflows; it is not a substitute for protecting the SQLite database and its
backups. Include the configured database in backup, access-control, and
retention procedures. There is no delete or edit action for audit events in the
administrator interface.

For schema-driven review fields, see the [review schema administrator guide](review_schema_admin_guide.md).

Administrator access is determined by the immutable SQLite role. The fixed `admin` account can access all pages and APIs; the fixed `operator` account cannot access administrative pages or APIs. Secret values are not exposed through runtime settings. Store provider secrets such as `api_key` under deployment-owned `pipeline_secrets`. The administrator Pipeline editor displays and edits only the corresponding secret alias; it never displays or versions the resolved value.

#### 4.5.6. Backup and Recovery

For a complete operational backup, include:

- the SQLite database file configured at `database.path` (including templates,
  drafts, immutable versions, dependencies, and ingress bindings)
- task-owned output folders such as `files/`, `data/`, `archive_folder/`, and any split task `split_dir` used by configured tasks
- reference CSVs, deployment configuration, and any portable configuration
  exports retained by your organization

Restore the database and durable artifacts from the same backup point. If the
database is restored without the files, the UI may show registered artifacts
whose paths no longer exist. If files are restored without the database,
batch/task/review history and the exact executable versions needed for resume
will be incomplete. Do not reconstruct an interrupted run from the newest
draft or version. A legacy deployment YAML can be imported as a draft during
migration, but import never publishes and never replaces an already pinned
definition.

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
  - Use the web interface to monitor processing status through its periodic refreshes.

### 4.7. Graceful Shutdown and Error Recovery

To stop the system, press `Ctrl+C` in the terminal where `main.py` is running.
This asks the watch-folder coordinator and web server to stop and runs
registered cleanup handlers. It does not guarantee that every in-progress
document finishes before the processes exit.

After stopping or restarting:

1. Check the final shutdown messages in `app.log`.
2. Sign in and open **Processing Overview** and **Failures**.
3. Inspect any document that was processing when shutdown began.
4. Confirm whether its outputs were created before deciding to re-upload it.
5. Do not delete processing files or database records unless the document state and recovery need are understood.

If the system fails to start, check `app.log`, validate `config.yaml`, confirm that the required watch and upload folders exist, and verify folder permissions and provider connectivity. The Config Check tool described in section 4.12 should be the first configuration diagnostic.

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
- **Purpose:** Extracts schema-directed structured data through a locally
  reachable Ollama server and the `glm-ocr:latest` vision model.
- **Prerequisites:** Install Ollama separately, pull `glm-ocr:latest`, start
  Ollama, and confirm the configured HTTP endpoint is reachable. The application
  does not install, start, or stop Ollama.
- **Parameters:**
  - `ollama_host`: HTTP(S) base URL, normally
    `http://127.0.0.1:11434`. Embedded credentials, query strings, and fragments
    are rejected.
  - `model`: installed Ollama model name, normally `glm-ocr:latest`.
  - `document_instructions`: optional document-level extraction guidance. Do not
    place secrets in instructions.
  - `dpi`: positive integer PDF render resolution; default `216`.
  - `num_ctx`: positive integer model context size; default `8192`.
  - `num_predict`: positive integer output-token limit; default `2048`.
  - `timeout_seconds`: positive request timeout; default `300`.
  - `fields`: the same stable extraction-field mapping used by downstream
    review and storage. Scalar fields, scalar lists, flat objects, and one
    `List[Any]` table with `item_fields` are supported. Text fields may define
    `choices` to constrain the Ollama JSON schema, and may opt into the
    `iso_date` normalizer to convert a transcribed source date to `YYYY-MM-DD`
    after extraction.

Configure this task from **Admin > Pipeline** by adding **Glm Ocr Extract**.
Its properties panel is separate from the LlamaCloud Extract editor. Set the
local model values, add scalar fields, and use **List of objects > Edit row
schema** for invoice lines. Add and configure **Review Gate** after extraction,
pin an exact published review-form version, then add CSV or JSON storage. Save,
validate, and publish the pipeline before assigning it to an upload or
watch-folder binding.

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
Scalar/object fields and the object-array table use separate calls so table
instructions can focus on visible rows. Results are normalized under
`context["data"]`, persisted to SQLite with provider `glm_ocr_ollama`, and are
available to every downstream task. The task does not provide field confidence,
citations, or PP-DocLayout output. Confidence therefore remains null; no score
is invented.

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
      document_instructions: Extract only values printed on the invoice.
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

The registered PDF extraction choices are the existing LlamaCloud
`ExtractPdfTask` and the independent local `GlmOcrExtractTask`. A pipeline may
contain only one extraction task.

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
    task creates it when execution begins if the application account has the
    required filesystem permission.
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
- Cross-reference `docs/config_check_troubleshooting.md` to resolve the common findings surfaced by tasks 13-19 (credential gaps, storage overrides, token mismatches, and similar issues).
- If operators report workflow failures, run the validator before restarting production work; many configuration problems can be found without rerunning documents.

Operators do not need to run this tool. Administrators should share only the part of a validation report needed to request missing information or explain an action.

## 5. Frequently Asked Questions (FAQ)

**Q: Does the program require internet access?**  
A: Yes, for cloud providers such as LlamaCloud Extract v2 via HTTPS.

**Q: Where are my processed files stored?**
A: Locations belong to the exact pipeline version assigned to the document:

- processed PDF: the `files_dir` of its `StoreFileToLocaldrive` task;
- CSV/JSON: the `data_dir` of the corresponding metadata storage task;
- split children: the split task's `split_dir`;
- source archive: the archive task's `archive_dir`.

Generated PDFs, CSV/JSON, archives, source originals, and split PDFs are also
registered as document artifacts when SQLite document context exists. Open the
document's **Extraction** page to see registered files; use **Pipeline** as an
administrator to inspect the immutable version's task paths. Do not look for
these values under runtime `config.yaml` `tasks`, because new pipelines are
stored in SQLite.

**Q: What happens if the same filename already exists?**
A: Storage tasks generate unique filenames automatically by appending a numeric suffix (`_1`, `_2`, …) to avoid overwriting. See the [filename utility](../modules/utils.py) for the implementation.

**Q: What are provider limits?**  
A: LlamaCloud Extract and LlamaParse limits include max file size and processing time; consult the current provider documentation for your workspace and tier.

**Q: How do I edit the configuration file safely?**  
A: Use `config.yaml` only for deployment settings, approvals, and secret aliases.
Stop the application when changing paths or secrets, back up the ignored local
file, preserve YAML indentation, run section 4.12's validator, and restart.
Create or change workflow tasks visually in **Pipeline**; do not add new
top-level `tasks` or `pipeline` blocks to deployment YAML.

**Q: Does every new pipeline need to be defined in `config.yaml`?**
A: No. Create its draft, tasks, review-form dependency, and immutable versions
in SQLite through **Pipeline** and **Review Forms**. `config.yaml` remains the
deployment source for the database path, web/watch processing paths, logging,
custom-task approvals, and provider secret aliases.

**Q: How do I give each pipeline a watch folder?**
A: Create the incoming directory first. In **Pipeline**, select the active
template, enter the absolute path under **Watch-folder bindings**, choose an
exact published version, and select **Add binding**. Paths cannot overlap.
Publishing a newer version does not update the binding. See section 4.5.5 for
the current UI limitation on correcting, disabling, or deleting bindings.

**Q: Why is a published pipeline missing from Upload & Process?**
A: Publication and activation are separate. Confirm that the template lifecycle
is **Active**, the version validates, and—when an operator is using the
page—that it is eligible for operator selection. Select **Refresh** on the
upload page after the administrator change.

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
A: Inspect the failed document's exact pipeline version and ensure its archive
task `archive_dir` exists or can be created and grants Modify permission to the
account running the application. Check **Processing Overview**, **Failures**,
and `app.log`. A successful archive is registered with the document's files.

**Q: What happens when reference file matching fails in the update_reference task?**
A: When field values required for matching are not found in the pipeline context, the task logs a warning and continues without matching any rows. The task will not append new rows. It updates matched rows only, creating the configured `update_field` column at runtime if needed. Check your extraction field configuration and ensure the required fields (like `purchase_order_number` or `invoice_amount`) are being extracted correctly.

**Q: Why is my document waiting for review?**
A: Review rules may pause a document because confidence is low or missing, required information is missing or invalid, split confidence requires attention, a business rule requests review, or every document is configured for review. Select **Review Queue**, claim the item, compare the PDF with the extracted fields, and select **Complete Review** when the information is correct.

**Q: What happens after review is completed?**
A: Corrected values are persisted in SQLite with the document extraction state. If the review gate uses `resume_policy: "next_task"`, the document resumes the downstream workflow steps after review completion.

**Q: Why did one uploaded PDF become multiple documents?**
A: When split processing is enabled, the source PDF can create child documents based on document category and page range. Open the batch from **Processing Overview**, then select its split results to inspect the source and child documents.

**Q: Can administrators change pipeline review or split behavior in the UI?**
A: Yes. Sign in as the administrator and use **Pipeline** to adjust the split
or review-gate step, then **Save Draft**, **Validate**, and **Publish**. Use
**Review Forms** for the pinned review UI schema. **Validation** checks
deployment/pasted-file surfaces; it does not publish the stored draft. Keep API
keys under deployment `pipeline_secrets`; the editor stores only their aliases.

**Q: How do I troubleshoot "Invalid credentials" errors during PDF extraction?**
A: Confirm that the pipeline step's `$secret` alias exists under deployment
`pipeline_secrets`, without copying the key into the draft or logs. If you use
a saved Extract v2 configuration, ensure `configuration_id` exists in the
correct LlamaCloud project. Check `app.log` for the redacted provider error and
run config-check against the stored version.

---


## 6. Appendix

### Glossary

- **Administrator:** The fixed account role that can use all operator features and change application configuration and account passwords.
- **Operator:** The fixed account role intended for daily upload, monitoring, review, failure investigation, and reporting.
- **Pipeline template:** A named workflow identity with one editable draft and
  a history of immutable published versions.
- **Pipeline version:** One immutable, numbered task definition. Every batch
  and document is pinned to an exact version at ingestion.
- **Pipeline draft:** The editable working definition. Saving or validating a
  draft does not change processing until it is published and eligible.
- **Task (standard step):** One configured operation, such as split, extraction, review, storage, or archiving.
- **Artifact:** A registered business file associated with a document, such as
  a source PDF, split PDF, archive, renamed PDF, CSV, or JSON export.
- **Review gate:** Rules that decide whether a document can continue automatically or must be checked by an operator.
- **Review form:** A versioned UI/validation schema that defines the fields and
  constraints shown during human review. A review-gate task pins one exact
  published form version when schema-driven review is used.
- **Review queue:** The application area containing documents that require an operator decision.
- **Source document:** The original PDF submitted for processing.
- **Child document:** A PDF created from selected pages when a source document is split.
- **Fan-out:** Creation of child documents that each run the remaining pipeline tasks.
- **Fan-in:** Automatic recalculation of source-document and batch status from the child-document statuses.
- **Alias:** A user-friendly field name used in the interface or exported CSV/JSON.
- **Watch folder:** An existing incoming folder monitored for newly added PDFs.
- **Watch-folder binding:** The SQLite record that maps one non-overlapping
  watch folder to one exact published pipeline version.
- **Claim:** A time-limited reservation that prevents two operators from
  editing the same review item concurrently.
- **Secret alias:** A non-secret name stored in a pipeline definition and
  resolved at runtime from deployment-owned `pipeline_secrets`.
- **Recovery reset:** The administrator command-line procedure that replaces the passwords for both fixed accounts when normal sign-in is unavailable.
- **YAML:** The indentation-based text format used for deployment configuration
  and portable pipeline/review-form import or export; SQLite remains the
  workflow authority.
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
| Overview | `/app/admin` | Administrator only | Sign in as the administrator, then select **Overview** from the left navigation menu. |
| Users | `/app/admin/users` | Administrator only | Sign in as the administrator, then select **Users** from the left navigation menu. |
| Pipeline and watch-folder bindings | `/app/admin/pipeline` | Administrator only | Sign in as the administrator, select **Pipeline**, and use the binding panel at the bottom for folder routing. |
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

### Further Documentation

- System Architecture: [design_architecture.md](design_architecture.md)
- Historical Unified Refactor Requirements: [prd-refactor-unified-pdfdoc-processing.md](../tasks/archive/unified-refactor/prd-refactor-unified-pdfdoc-processing.md)
- Review Schema Administration: [review_schema_admin_guide.md](review_schema_admin_guide.md)
- LlamaCloud document splitting: [official LlamaIndex guide](https://developers.llamaindex.ai/llamaparse/split/getting_started)

---

This guide documents operator workflows and administrator configuration for the current PDF processing application.
