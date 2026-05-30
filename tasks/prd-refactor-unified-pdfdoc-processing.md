# Product Requirements Document: Unified PDF Document Processing Refactor

## 1. Overview

This document defines the requirements for refactoring `pdfdoc_extraction` into a unified document processing application that combines:

- PDF ingestion from web upload and watch folders.
- Optional LlamaCloud Split processing for bundled or concatenated PDFs.
- Configurable task pipelines.
- Human review and correction workflows currently represented by `qa_extracted_data`.
- A new web UI modeled after the prototype in `D:\python_code\pdfdoc_extraction\refactor UI prototype`.
- SQLite-backed durable state instead of the current file-based status model.

The target application should keep the useful pipeline architecture from `pdfdoc_extraction`, but replace the simple status-file approach with a durable application state layer. The QA functionality should be incorporated into the main app as review workflow capabilities, not kept as a separate Streamlit application in the final architecture.

## 2. Goals

- Make `pdfdoc_extraction` the main host application for ingestion, processing, review, and export.
- Preserve watch-folder ingestion as a first-class input path alongside web upload, including configuration, monitoring, processing, archive/error handling, and SQLite state creation.
- Introduce SQLite as the source of truth for batches, documents, task runs, extraction results, review queues, locks, audit events, and final outputs.
- Provide a modern operator UI based on the existing prototype screens:
  - Upload and process.
  - Processing overview.
  - Split results.
  - Extraction results.
  - Review queue.
  - Human review.
  - Reports and settings.
- Provide an administrator UI that includes all operator capabilities plus schema management, validation, pipeline task reconfiguration, review-gate rules, task catalog, split settings, admin audit history, and dry-run tools.
- Add a configurable `ReviewGateTask` that administrators can place anywhere in the YAML pipeline.
- Support pause/resume workflow behavior when a document requires human review.
- Support one-to-many processing where one uploaded PDF can produce multiple child documents after splitting.
- Preserve the current ability to define task pipelines from configuration.
- Reuse proven QA behavior from `qa_extracted_data`, especially schema-driven forms, diff generation, file locking concepts, validation, and audit logging.
- Reuse existing YAML/config validation tooling in both CLI and UI so administrators can validate pipeline, schema, and review configuration before runtime.

## 3. Non-Goals

- Do not perform a full rewrite from scratch unless the implementation phase proves that the current app cannot be safely evolved.
- Do not keep Streamlit as the final operator interface.
- Do not require an external database server in the first refactor phase.
- Do not introduce enterprise identity management such as SSO, LDAP, or multi-tenant authorization in the first phase.
- Do not require every existing storage/export task to be rewritten before the first integrated milestone.
- Do not make LlamaCloud Split mandatory for all documents.

## 4. Target Users

### Operators

Operators upload PDFs, monitor processing, review extracted document data, correct low-confidence values, and mark documents complete.

### Administrators

Administrators have all operator capabilities and additionally configure pipelines, watch folders, LlamaCloud settings, review thresholds, schemas, task catalog behavior, validation, and output destinations.

### Technical Maintainers

Maintainers extend pipeline tasks, troubleshoot failed processing, inspect audit history, and maintain migrations.

## 5. Current State

### `pdfdoc_extraction`

Current strengths:

- FastAPI application with upload and dashboard routes.
- Watch folder ingestion.
- Config-driven pipeline loading.
- LlamaCloud Extract v2 support.
- Storage tasks for JSON and CSV.
- Status updates and tests.

Current limitations:

- Processing state is stored in JSON/TXT files under the processing directory.
- Workflows are linear and do not natively model pause/resume.
- Workflows do not cleanly model one source PDF becoming many child documents.
- Human review is not integrated as a first-class pipeline step.
- UI is functional but not aligned with the newer prototype.

### `qa_extracted_data`

Current strengths:

- Operator queue.
- Schema-driven validation and form generation.
- PDF preview.
- Diff visualization.
- Audit trail.
- Locking concepts for multi-operator review.

Current limitations:

- Separate Streamlit app.
- File-directory state model.
- Not integrated with the extraction pipeline.
- No native ability to resume a paused pipeline after correction.

## 6. Target Architecture

The refactored application must use this high-level flow:

```text
PDF ingestion
  -> batch and document records in SQLite
  -> optional Split task
  -> child document records
  -> extraction and configured pipeline tasks
  -> optional ReviewGateTask
  -> human correction when required
  -> pipeline resume
  -> storage, export, archive, reporting
```

## 7. SQLite State Requirements

SQLite must become the durable source of truth for application state.

### 7.1 Database Requirements

- The application must create and migrate the SQLite database at startup.
- The database path must be configurable.
- The app must support a development default such as `data/app_state.sqlite3`.
- Schema migrations must be versioned and repeatable.
- Database writes must be transactionally safe.
- File paths stored in the database must be absolute or resolvable from a configured app data root.
- The system must not rely on status `.txt` files as workflow state after migration.
- All configured workflow steps must read and write workflow state through SQLite-backed services, task-run records, document records, extraction/review records, audit records, or registered document-file records.
- Remaining filesystem writes after migration must be durable business artifacts, input/archive files, reference/config files, or exports; they must not be required to reconstruct in-progress workflow state.

### 7.2 Required Tables

The implementation may adjust names, but the model must support these concepts:

- `batches`
  - Represents one upload operation or one watch-folder ingestion event.
  - Tracks source, original filename, status, created time, and aggregate progress.
- `documents`
  - Represents a processable logical document.
  - Supports parent-child relationships for split documents.
  - Tracks document type, status, current pipeline step, source batch, and active file path.
- `document_files`
  - Tracks original PDFs, split PDFs, previews, exported files, and archived files.
- `task_runs`
  - Tracks every task execution with task key, status, start/end time, error, retry count, and output summary.
- `extraction_results`
  - Stores normalized extraction payloads and extraction metadata.
- `extracted_fields`
  - Stores individual field values, aliases, confidence values when available, source metadata, and review status.
- `review_items`
  - Represents documents or fields waiting for human review.
- `review_locks`
  - Prevents concurrent operators from editing the same review item.
- `audit_events`
  - Stores operator changes, pipeline events, state transitions, and system actions.
- `app_settings`
  - Stores runtime configuration metadata where needed, without replacing `config.yaml`.
- `config_versions`
  - Stores admin-created schema, pipeline, review-gate, split, and settings draft/published versions for audit and rollback.

### 7.3 Status Model

Document statuses must include at least:

- `received`
- `queued`
- `processing`
- `split_pending`
- `split_completed`
- `extraction_pending`
- `extraction_completed`
- `review_required`
- `in_review`
- `review_completed`
- `resuming`
- `completed`
- `failed`
- `cancelled`

Batch statuses must be derived from child document status where possible.

## 8. Pipeline Requirements

### 8.1 YAML-Configured Pipeline

The application must retain YAML-configured task pipelines.

Example:

```yaml
tasks:
  split_documents:
    module: standard_step.split.llamacloud_split
    class: LlamaCloudSplitTask
    params:
      enabled: true
      categories:
        - name: invoice
          description: Invoice documents from suppliers.
        - name: delivery_order
          description: Delivery order or shipment documents.
      allow_uncategorized: include

  extract_document_data:
    module: standard_step.extraction.extract_pdf_v2
    class: ExtractPdfV2Task
    params:
      api_key: "${LLAMA_CLOUD_API_KEY}"
      configuration_id: "cfg-example"
      cite_sources: true
      fields:
        supplier_name:
          alias: "Supplier name"
          type: "str"
        invoice_number:
          alias: "Invoice number"
          type: "str"
        invoice_total:
          alias: "Invoice total"
          type: "Decimal"

  review_gate:
    module: standard_step.review.review_gate
    class: ReviewGateTask
    params:
      mode: field_confidence
      confidence_threshold: 0.90
      require_review_when_missing_confidence: true
      schema_file: "schemas/invoice_schema.yaml"
      queue_name: "invoice_review"
      review_scope: "low_confidence_fields"

  store_json:
    module: standard_step.storage.store_metadata_as_json_v2
    class: StoreMetadataAsJsonV2
    params:
      data_dir: "data"
      filename: "{invoice_number}.json"

pipeline:
  - split_documents
  - extract_document_data
  - review_gate
  - store_json
```

### 8.2 Fan-Out Requirement

The pipeline engine must support tasks that produce child documents.

- If a split task creates multiple child documents, each child document must receive its own document record.
- Each child document must continue through the configured pipeline from the appropriate next task.
- Parent batch progress must aggregate child document progress.
- Child documents must retain traceability to the original source PDF and page ranges.

### 8.3 Pause/Resume Requirement

The pipeline engine must support pausing a document.

- A task may mark a document as paused for human review.
- When paused, downstream tasks must not run for that document until review is completed.
- Review completion must update corrected values in SQLite.
- The pipeline must resume from the task immediately after the `ReviewGateTask`, unless configuration specifies otherwise.
- Resume behavior must be idempotent. Repeated resume requests must not duplicate downstream outputs.

### 8.4 Task Run Tracking

Every task execution must create or update a `task_runs` record.

Each task run must store:

- Document ID.
- Batch ID.
- Task key from the YAML pipeline.
- Task class and module.
- Status.
- Start and end timestamps.
- Error details.
- Input context summary.
- Output context summary.

## 9. ReviewGateTask Requirements

`ReviewGateTask` is a new standard task that administrators can place anywhere in the pipeline.

### 9.1 Functional Requirements

- The task must inspect the current document context and decide whether human review is required.
- The task must support at least these review triggers:
  - Field confidence below a configured threshold.
  - Missing required field.
  - Schema validation failure.
  - Split confidence below a configured threshold.
  - Explicit business rule flag in context.
  - Always review.
- The task must create one or more `review_items` records when review is required.
- The task must update document status to `review_required`.
- The task must pause the pipeline for the current document when review is required.
- The task must pass through without pausing when review is not required.
- The task must be usable before extraction, after extraction, after rules, or before final storage, depending on the configured pipeline position.

### 9.2 Configuration Requirements

The task must support configuration similar to:

```yaml
review_gate:
  module: standard_step.review.review_gate
  class: ReviewGateTask
  params:
    mode: field_confidence
    confidence_threshold: 0.90
    split_confidence_levels_requiring_review: ["low", "medium"]
    require_review_when_missing_confidence: true
    require_review_for_missing_required_fields: true
    schema_file: "schemas/invoice_schema.yaml"
    queue_name: "invoice_review"
    review_scope: "low_confidence_fields"
    allow_operator_to_edit_high_confidence_fields: true
    resume_policy: "next_task"
```

### 9.3 Review Scope Modes

The task must support these review scopes:

- `document`
  - Operator reviews the entire extracted document.
- `low_confidence_fields`
  - Operator is guided to fields below threshold, but can optionally edit all fields.
- `schema_errors`
  - Operator reviews fields that failed schema validation.
- `split_result`
  - Operator reviews page grouping or document category before extraction.

### 9.4 Output Requirements

When review is required, the task must output context equivalent to:

```json
{
  "pipeline_state": "paused",
  "pause_reason": "review_required",
  "review_item_id": "review_123",
  "document_id": "doc_123"
}
```

When review is not required, the task must leave the pipeline in a runnable state.

## 10. Human Review Requirements

### 10.1 Review Queue

The application must provide a review queue with:

- Filtering by status.
- Filtering by document type.
- Filtering by source batch.
- Filtering by low-confidence fields.
- Search by filename, document ID, supplier, invoice number, or extracted values.
- Lock status and assigned operator display.
- Pagination.

### 10.2 Claim and Lock

- Operators must claim a review item before editing.
- A claimed item must be locked to the operator.
- Locks must expire after a configurable timeout.
- Administrators must be able to release stale locks.
- Lock and release events must be audited.

### 10.3 Review Editor

The review editor must provide:

- PDF preview or rendered page preview.
- Extracted fields.
- Confidence indicators when confidence is available.
- Corrected value inputs.
- Dynamic form rendering from the configured schema.
- Support for complex schema fields, including nested objects and arrays of objects.
- Schema validation feedback.
- Diff preview before submission.
- Submit, save draft, cancel, and release actions.
- Navigation to previous and next review item.

### 10.4 Correction Storage

- Original extracted values must be preserved.
- Corrected values must be stored separately.
- The final payload used by downstream tasks must use corrected values where present.
- The audit log must record before and after values.
- The audit log must record user, timestamp, document ID, review item ID, and reason/action.

### 10.5 Schema Editor

The application must provide a non-Streamlit schema editor so administrators can create and maintain review schemas inside the unified app.

The schema editor must support:

- Listing existing schema files.
- Creating new schemas.
- Editing schema metadata such as title, description, and version.
- Adding, editing, deleting, and reordering fields.
- Editing scalar field properties.
- Editing nested object fields.
- Editing scalar arrays.
- Editing object arrays, such as invoice line items.
- Previewing generated YAML.
- Validating schemas before saving.
- Warning when schema changes may affect active review items.

### 10.6 Configuration and YAML Validation UI

The application must expose existing YAML/config validation capabilities through the administrator UI while preserving CLI validation for development, CI, and deployment.

The validation UI must support:

- Validating `config.yaml`.
- Validating pipeline task definitions and ordering.
- Validating task module/class importability.
- Validating `_dir` and `_file` paths.
- Validating extraction field configuration.
- Validating storage filename tokens against available extracted fields.
- Validating `ReviewGateTask` configuration.
- Validating schema YAML files.
- Showing errors, warnings, and info findings with actionable suggestions.
- Showing the config path/key that caused each finding.
- Running validation without saving changes.
- Preventing schema save when validation returns blocking errors.

The UI must not silently auto-fix YAML. It may offer suggestions, but the user must explicitly save changes through the relevant editor.

## 11. UI Requirements

The new UI must be modeled after `D:\python_code\pdfdoc_extraction\refactor UI prototype`.

### 11.1 Navigation

The primary left sidebar must stay close to the prototype and include:

- Upload and Process.
- Review Queue.
- Reports.
- Settings.

The UI must still include these workflow and admin screens, but they do not all need to be top-level sidebar links:

- Processing Overview, opened after upload or from batch links.
- Split Results, opened from processing actions.
- Extraction Results, opened from processing or split result actions.
- Human Review, opened from the review queue.
- Schema Editor, opened from Settings.
- Configuration Validation, opened from Settings.

#### 11.1.1 Operator View

The operator view must stay close to the existing UI prototype and focus on day-to-day document processing:

- Upload and Process.
- Processing Overview.
- Split Results.
- Extraction Results.
- Review Queue.
- Human Review with PDF viewer.
- Basic reports and read-only settings.

Operators must not see schema editing, pipeline reconfiguration, task catalog, validation center, or admin audit controls.

#### 11.1.2 Admin View

Administrators must have access to every operator screen plus an admin view for configuration and governance.

The admin view must include:

- Schema Management for QA/review schemas.
- Pipeline Configuration for task ordering, task enablement, and task parameters.
- Task Catalog for available `standard_step` modules/classes and their expected parameters.
- Validation Center for schemas, config, pipeline, review gate, imports, paths, and storage filename tokens.
- Review Gate Rules for confidence thresholds, review scope, split-confidence review, always-review rules, and lock timeout behavior.
- LlamaCloud Split Settings for split categories, thresholds, adapter status, and connection checks.
- System Settings for watch folders, output/archive folders, SQLite path, upload limits, and retention settings.
- Admin Audit History for schema, pipeline, validation, settings, and publish events.
- Pipeline Dry Run for testing a sample PDF through split/extract/review-gate decisions without final export.

The first admin implementation should prioritize Schema Management, Validation Center, Pipeline Configuration, and Review Gate Rules. Task Catalog, Split Settings, Admin Audit History, and Pipeline Dry Run may be implemented incrementally but must be represented in the UI architecture.

### 11.2 Upload and Process

The upload screen must support:

- Drag and drop PDF upload.
- File picker upload.
- Multiple PDF files per upload batch.
- Immediate PDF validation feedback.
- Batch creation.
- Start processing action.
- Display of upload status and file sizes.

### 11.3 Processing Overview

The processing overview must show:

- Batch-level progress.
- Pipeline step progress.
- Per-document status.
- Split, extract, review, and output indicators.
- Failed task details.
- Estimated progress based on completed task runs.

### 11.4 Split Results

The split results screen must show:

- Source PDF.
- Number of child documents created.
- Page ranges.
- Document category.
- Split confidence.
- Uncategorized pages where applicable.
- Link to extraction results for each child document.

### 11.5 Extraction Results

The extraction results screen must show:

- PDF preview or page preview.
- Extracted fields.
- Field aliases.
- Extracted values.
- Confidence indicators where available.
- Source/citation metadata where available.
- Review requirement status.

### 11.6 Review Queue and Human Review

The UI must implement the review requirements in Section 10.

#### 11.6.1 Schema Editor

The UI must implement the schema editor requirements in Section 10.5 without using Streamlit.

#### 11.6.2 Configuration Validation

The UI must implement the validation requirements in Section 10.6.

The validation experience should live in:

- Settings page for whole-app configuration validation.
- Schema editor page for schema validation.
- Future pipeline editor or pipeline preview for pipeline-specific validation.

#### 11.6.3 Admin Pipeline Configuration

The admin UI must allow administrators to inspect and reconfigure the task pipeline without editing raw YAML as the only option.

Pipeline configuration must support:

- Viewing the current pipeline as ordered task steps.
- Enabling or disabling tasks.
- Reordering tasks.
- Adding a task from the task catalog.
- Removing a draft task before publish.
- Editing task parameters through forms.
- Inserting `ReviewGateTask` anywhere in the pipeline.
- Showing generated YAML preview.
- Showing a diff between the active pipeline and draft pipeline.
- Validating before publish.
- Publishing only when blocking validation errors are resolved.

#### 11.6.4 Admin Validation Center

The validation center must support:

- Validate all schemas.
- Validate one schema.
- Validate active `config.yaml`.
- Validate draft config YAML.
- Validate active and draft pipeline definitions.
- Validate task importability.
- Validate required task parameters.
- Validate review-gate schema references and thresholds.
- Validate path and storage filename token references.
- Display errors, warnings, and info findings with suggestions.

#### 11.6.5 Admin Audit and Dry Run

The admin UI must record and expose:

- Schema changes.
- Pipeline draft and publish events.
- Validation runs.
- Settings changes.
- Review-gate rule changes.
- Split settings changes.

The dry-run tool must let an administrator upload or select a sample PDF, choose a pipeline draft, and preview split, extraction, and review-gate decisions without writing final exports.

### 11.7 Visual Style

- Use a clean operational dashboard style.
- Preserve the compact left sidebar pattern from the prototype.
- Avoid the current basic dashboard look as the target long-term UI.
- The UI must be responsive enough for laptop and desktop operator workflows.
- The review editor must prioritize dense, scannable fields over marketing-style layouts.

## 12. LlamaCloud Split Requirements

### 12.1 Split Task

The app must add an optional LlamaCloud Split task.

- The task must upload the source PDF for split processing.
- The task must use configured categories.
- The task must persist split job ID, status, categories, page ranges, and confidence.
- The task must support uncategorized page behavior through configuration.
- The task must create child document records for each segment.
- The task must create split PDF files locally from returned page ranges.
- The task must be disabled by default unless configured.

### 12.2 Beta API Isolation

LlamaCloud Split is currently beta, so the integration must be isolated behind an adapter.

- Split API calls must not be embedded directly in pipeline orchestration code.
- Response parsing must be centralized.
- Unknown response fields must be tolerated.
- Breaking API changes must be contained to the adapter and tests.

## 13. API Requirements

The FastAPI backend must expose API endpoints for:

- Authentication.
- Uploading PDFs.
- Listing batches.
- Viewing batch details.
- Listing documents.
- Viewing document details.
- Listing task runs.
- Listing split results.
- Listing extraction results.
- Serving registered document PDFs for review preview.
- Listing review items.
- Claiming review items.
- Saving review drafts.
- Submitting corrected review data.
- Releasing locks.
- Resuming paused documents.
- Exporting final results.
- Reading audit history.
- Listing, creating, updating, duplicating, and validating review schemas.
- Validating all schemas in one admin action.
- Validating config, pipeline, and schema YAML.
- Viewing and editing pipeline drafts.
- Validating and publishing pipeline configuration changes.
- Listing available pipeline task modules/classes in a task catalog.
- Viewing and editing review-gate rules.
- Viewing and editing LlamaCloud Split settings.
- Viewing and editing non-secret system settings.
- Running pipeline dry runs against sample PDFs.
- Viewing admin audit events for schema, pipeline, validation, and settings changes.
- Viewing non-secret runtime settings.
- Viewing basic processing reports.

## 14. Migration Requirements

### 14.1 Existing `pdfdoc_extraction` Migration

- Existing upload and watch folder behavior must keep working during migration.
- Watch-folder monitoring must remain available after migration; the refactor must not replace it with web upload only.
- PDFs discovered from configured watch folders must enter the same batch/document/workflow path as web uploads while retaining source metadata that identifies the watch-folder origin.
- Existing watch-folder processing, archive, and error-folder semantics should be preserved unless a later task explicitly changes them.
- Existing extraction tasks should be adapted to write SQLite state while still returning context.
- Existing storage tasks should continue to work with the corrected final payload.
- Existing tests should be updated incrementally instead of discarded.

### 14.2 Existing `qa_extracted_data` Migration

The following concepts should be ported or reimplemented:

- Schema loading.
- Dynamic validation.
- Form generation logic.
- Diff generation.
- Audit payload structure.
- Review locking behavior.
- Queue filtering behavior.
- PDF preview behavior.
- YAML/schema validation behavior and reusable validation logic.

The final app should not depend on running `streamlit_app.py`.

### 14.3 Status File Migration

- The first migration phase may keep status files as compatibility output.
- SQLite must become the only required source for workflow state.
- Once UI and APIs read from SQLite, status files must be deprecated or removed from primary workflow paths.
- `StatusManager` calls in workflow orchestration and `standard_step/*` tasks must be audited and replaced with SQLite-backed task-run events, document state updates, audit events, or document-file registrations.
- `/api/files`, `/api/status/{file_id}`, and new UI status reads must be backed by SQLite instead of enumerating or loading text status files.
- A workflow must be able to run without creating intermediate status `.txt` files once migration cleanup is complete.
- A one-time import tool should be considered for historical status files if needed.

## 15. Security Requirements

- Authentication must be required for all operator UI pages and state-changing API calls.
- Admin pages and admin APIs must require an admin role.
- Administrators must be able to use all operator features.
- Operators must not be able to edit schemas, publish pipeline changes, change review-gate rules, edit split settings, or view admin audit screens.
- Uploaded file paths must be sanitized.
- File serving must prevent path traversal.
- Review locks must be enforced server-side.
- Audit events must not be editable through normal UI actions.
- API keys must not be stored in plain text in SQLite.
- Configuration should support environment variable interpolation for secrets.

## 16. Reliability Requirements

- Processing must be restartable after application shutdown.
- Documents paused for review must remain available after restart.
- Documents in progress at shutdown must be recoverable or marked for retry.
- Task runs must be idempotent where possible.
- Downstream resume after review must not duplicate exports.
- Database writes and file creation must be ordered so records do not point to missing files unless the task failed.

## 17. Testing Requirements

The refactor must include tests for:

- SQLite schema creation and migrations.
- Batch and document state transitions.
- Pipeline fan-out after split.
- ReviewGateTask pass-through behavior.
- ReviewGateTask pause behavior.
- Review submission and pipeline resume.
- Lock creation, expiry, and release.
- Audit event creation.
- API endpoints for review queue and review submission.
- UI workflow smoke tests for upload, status, review queue, and review submission.
- Schema editor tests for create, edit, validate, and save behavior.
- Config validation UI/API tests for config, pipeline, review gate, all-schema validation, and schema findings.
- Admin route access tests for operator/admin authorization boundaries.
- Pipeline configuration tests for draft, diff, validation, and publish behavior.
- Task catalog tests for module/class discovery and import failure reporting.
- Review-gate rules UI/API tests.
- Pipeline dry-run tests with mocked extraction and split calls.
- LlamaCloud Split adapter with mocked HTTP responses.

All tests must use pytest and follow the project Windows command convention:

```powershell
C:\Python313\python.exe -m pytest -v
```

## 18. Acceptance Criteria

The refactor is acceptable when:

- A user can upload a PDF from the new UI.
- A PDF dropped into the watch folder creates the same kind of batch/document records as a web upload.
- Watch-folder ingestion remains configurable and operational after the SQLite/UI refactor.
- Processing state is visible from SQLite-backed API endpoints.
- A configured pipeline can include `ReviewGateTask` at an administrator-chosen position.
- A document requiring review pauses before downstream tasks.
- An operator can claim, edit, validate, submit, and audit corrections.
- After review submission, the document resumes from the correct next pipeline step.
- Final JSON/CSV/export output uses corrected values.
- Optional Split can turn one source PDF into multiple child documents.
- The UI follows the prototype navigation and screen model.
- Operator and admin views are separated by role, with admins retaining all operator features.
- Schema editor supports complex schemas without depending on Streamlit.
- Settings/admin UI can run config, pipeline, review-gate, and all-schema validation and display actionable findings.
- Admin can reconfigure pipeline tasks through a draft/validate/publish workflow.
- Admin can insert and configure `ReviewGateTask` from the UI.
- Admin can inspect task catalog entries and import/configuration errors.
- Admin changes to schemas, pipeline configuration, validation runs, and settings are auditable.
- Existing core extraction/storage behavior remains covered by tests.
- All configured workflow steps can run with SQLite as the workflow-state store and without intermediate text status files.
- Any remaining filesystem writes are documented as business artifacts, input/archive files, reference/config files, or exports rather than state required by the application workflow.

## 19. Open Questions

- Should the first SQLite implementation use raw `sqlite3`, SQLAlchemy, or SQLModel?
- Should the new UI be server-rendered FastAPI templates, HTMX, or a separate frontend app?
- Should review be field-level only, document-level only, or both from the first milestone?
- How should field confidence be normalized when LlamaCloud does not return numeric confidence for every field?
- Should split page correction be included in the first release or deferred?
- Should operator/admin role assignment come from local config first, or from the existing login/user model if one is already available?

## 20. Suggested Milestones

### Milestone 1: State Foundation

- Add SQLite schema and migration runner.
- Add repository/service layer for batches, documents, task runs, reviews, and audits.
- Write state transition tests.

### Milestone 2: Pipeline State Integration

- Update ingestion to create batch and document records.
- Update workflow execution to write task runs.
- Keep existing extraction and storage behavior working.

### Milestone 3: ReviewGateTask

- Implement configurable `ReviewGateTask`.
- Add review item creation.
- Add pause/resume semantics.
- Add tests for pass-through, pause, and resume.

### Milestone 4: Backend Dependency Hardening

- Audit every `standard_step/*` task and classify file operations before building UI on top of incomplete state paths.
- Add isolated Split adapter and Split task.
- Create child PDFs and child document records.
- Add validation services for config, pipeline, schemas, review-gate params, and split params.
- Add mocked Split and validation tests.

### Milestone 5: Prototype-Aligned Operator UI Foundation

- Add role-aware operator/admin navigation and shared DaisyUI/FastAPI shell.
- Build upload and processing pages on SQLite batch/document/task-run APIs.
- Build schema APIs and schema editor before the review editor depends on schema-driven fields.
- Build extraction results API/page before review UI links to persisted fields.

### Milestone 6: Human Review UI

- Build review queue and review editor in the new UI.
- Use normalized schema APIs, persisted extraction fields, review APIs, and secure PDF serving.
- Add UI smoke tests for claim, draft, diff, complete, release, and resume.

### Milestone 7: Admin Configuration UI

- Build Task Catalog service/API before Pipeline Configuration.
- Build Pipeline Configuration with draft, diff, validate, and publish.
- Build Review Gate Rules and Split Settings screens.
- Build Validation Center after the validation services and admin configuration APIs exist.
- Add admin dashboard, audit visibility, settings, and pipeline dry-run scaffolding.

### Milestone 8: Reports, Migration Cleanup, and Documentation

- Add basic reports and operator settings pages.
- Deprecate or remove file-based status as workflow state.
- Replace old status APIs and UI reads with SQLite batch/document/task-run queries.
- Add an integration test proving representative configured workflows run with text status-file creation disabled.
- Update documentation and migration notes for existing deployments.
- Run full test suite.
## UI Framework and Prototype Alignment

The refactored UI must use DaisyUI as the primary CSS component framework for the FastAPI/Jinja implementation.

The UI layout, navigation model, and information architecture flow must mirror `refactor UI prototype/`. The prototype should be treated as the product reference for page structure, operator/admin navigation, workflow progression, screen density, and review workspace layout, not only as loose visual inspiration.

Implementation should prefer DaisyUI components for navigation, menus, buttons, forms, tables, tabs, badges, alerts, modals, drawers, cards, and status indicators. Custom CSS should be limited to app-specific layout behavior such as PDF/review split panes, dense processing tables, scroll regions, responsive review workspaces, and prototype-specific refinements that DaisyUI does not cover cleanly.
