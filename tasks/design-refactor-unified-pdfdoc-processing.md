# Design: Unified PDF Document Processing Refactor

## 1. Purpose

This design document translates `tasks/prd-refactor-unified-pdfdoc-processing.md` into implementation guidance.

The goal is to refactor `pdfdoc_extraction` into a unified application with:

- SQLite-backed state.
- Batch and document tracking.
- Preserved web-upload and watch-folder ingestion paths.
- Optional LlamaCloud Split.
- Pipeline fan-out.
- Configurable `ReviewGateTask`.
- Human review UI and API.
- Prototype-modeled UI.

This file is written to be executable by an implementation agent. Prefer small, testable milestones. Do not rewrite working code unnecessarily.

## 2. High-Level Architecture

Keep `pdfdoc_extraction` as the main app.

Add these layers:

```text
FastAPI UI/API
  -> services layer
  -> SQLite repositories
  -> workflow manager
  -> dynamic pipeline tasks
  -> file storage on disk
```

Target processing flow:

```text
Ingest PDF from web upload or configured watch folder
  -> create batch
  -> create root document
  -> run configured pipeline
  -> optional split task creates child documents
  -> child documents continue pipeline
  -> extraction writes fields
  -> review gate may pause document
  -> human review corrects values
  -> resume pipeline after review gate
  -> storage/export/archive
```

## 3. Directory and Module Layout

Add these modules:

```text
modules/
  db/
    __init__.py
    connection.py
    migrations.py
    schema.sql
    repositories.py
  services/
    __init__.py
    batch_service.py
    document_service.py
    workflow_state_service.py
    review_service.py
    audit_service.py
    config_validation_service.py
    pipeline_validation_service.py
    pipeline_config_service.py
    task_catalog_service.py
    admin_settings_service.py
    schema_service.py
  resume_manager.py

standard_step/
  review/
    __init__.py
    review_gate.py
  split/
    __init__.py
    llamacloud_split.py
    llamacloud_split_adapter.py

web/
  templates/
    app_base.html
    upload_process.html
    processing_overview.html
    split_results.html
    extraction_results.html
    review_queue.html
    human_review.html
    schema_editor.html
    config_validation.html
    admin_dashboard.html
    pipeline_config.html
    task_catalog.html
    review_gate_rules.html
    split_settings.html
    admin_audit.html
    pipeline_dry_run.html
    reports.html
    settings.html
  static/
    css/
      app.css
    js/
      app.js
      upload_process.js
      processing_overview.js
      review_queue.js
      human_review.js
      schema_editor.js
      config_validation.js
      admin.js
      pipeline_config.js
      task_catalog.js
      review_gate_rules.js
      split_settings.js
      admin_audit.js
      pipeline_dry_run.js
```

Keep existing modules during migration:

- `modules/config_manager.py`
- `modules/workflow_loader.py`
- `modules/workflow_manager.py`
- `modules/file_processor.py`
- `modules/watch_folder_monitor.py`
- existing `standard_step` tasks

The first implementation should add SQLite state beside the existing file-based status, then move API/UI reads to SQLite. By migration cleanup, SQLite-backed repositories and services must be the only required workflow-state path. Text status files may exist only as temporary compatibility output during migration, not as state needed by orchestration, UI/API reads, pause/resume, or recovery.

## 4. Configuration Design

Extend `config.yaml` with:

```yaml
database:
  path: "data/app_state.sqlite3"
  run_migrations_on_startup: true

watch_folders:
  enabled: true
  input_dir: "data/watch/input"
  processing_dir: "data/watch/processing"
  archive_dir: "data/watch/archive"
  error_dir: "data/watch/error"
  poll_interval_seconds: 5

review:
  lock_timeout_minutes: 60
  default_queue_name: "default_review"

validation:
  config_validation_enabled: true
  allow_ui_config_save: false
  strict_mode_default: false

ui:
  app_name: "DocFlow AI"
  page_size: 25
  admin_enabled: true
  operator_sidebar:
    - upload
    - review
    - reports
    - settings

auth:
  roles_enabled: true
  default_admin_users: []
```

Do not remove old config keys yet. Existing tests and behavior should continue while the migration is in progress.

## 5. SQLite Schema

Create `modules/db/schema.sql`.

Use TEXT primary keys. Generate IDs in Python with UUID strings.

Recommended schema:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    original_filename TEXT,
    status TEXT NOT NULL,
    total_documents INTEGER NOT NULL DEFAULT 0,
    completed_documents INTEGER NOT NULL DEFAULT 0,
    failed_documents INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    parent_document_id TEXT,
    original_filename TEXT,
    document_type TEXT,
    status TEXT NOT NULL,
    current_task_index INTEGER NOT NULL DEFAULT 0,
    current_task_key TEXT,
    file_path TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    split_category TEXT,
    split_confidence TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(batch_id) REFERENCES batches(id),
    FOREIGN KEY(parent_document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS document_files (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS task_runs (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    task_key TEXT NOT NULL,
    task_index INTEGER NOT NULL,
    module_name TEXT NOT NULL,
    class_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    error TEXT,
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    retry_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(batch_id) REFERENCES batches(id),
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS extraction_results (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    task_run_id TEXT,
    provider TEXT NOT NULL,
    provider_job_id TEXT,
    data_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(task_run_id) REFERENCES task_runs(id)
);

CREATE TABLE IF NOT EXISTS extracted_fields (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    extraction_result_id TEXT,
    field_key TEXT NOT NULL,
    field_alias TEXT,
    extracted_value_json TEXT,
    corrected_value_json TEXT,
    final_value_json TEXT,
    confidence REAL,
    confidence_label TEXT,
    requires_review INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL DEFAULT 'not_required',
    source_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(extraction_result_id) REFERENCES extraction_results(id)
);

CREATE TABLE IF NOT EXISTS review_items (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    queue_name TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    scope TEXT NOT NULL,
    created_by_task_run_id TEXT,
    assigned_to TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(batch_id) REFERENCES batches(id),
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(created_by_task_run_id) REFERENCES task_runs(id)
);

CREATE TABLE IF NOT EXISTS review_locks (
    id TEXT PRIMARY KEY,
    review_item_id TEXT NOT NULL UNIQUE,
    locked_by TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(review_item_id) REFERENCES review_items(id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    batch_id TEXT,
    document_id TEXT,
    review_item_id TEXT,
    user TEXT,
    event_type TEXT NOT NULL,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES batches(id),
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(review_item_id) REFERENCES review_items(id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config_versions (
    id TEXT PRIMARY KEY,
    config_type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    content_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_documents_batch_id ON documents(batch_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_task_runs_document_id ON task_runs(document_id);
CREATE INDEX IF NOT EXISTS idx_review_items_status ON review_items(status);
CREATE INDEX IF NOT EXISTS idx_extracted_fields_document_id ON extracted_fields(document_id);
CREATE INDEX IF NOT EXISTS idx_config_versions_type_status ON config_versions(config_type, status);
```

## 6. Database Layer

### 6.1 `modules/db/connection.py`

Implement:

```python
def get_db_path(config_manager: ConfigManager) -> Path: ...
def connect(config_manager: ConfigManager) -> sqlite3.Connection: ...
def transaction(conn: sqlite3.Connection): ...
```

Connection rules:

- Use `sqlite3.Row` row factory.
- Use `PRAGMA foreign_keys = ON`.
- Use ISO UTC strings for timestamps.
- Store JSON as TEXT using `json.dumps(..., ensure_ascii=False)`.

### 6.2 `modules/db/migrations.py`

Implement:

```python
def initialize_database(config_manager: ConfigManager) -> None:
    """Create database folder, run schema.sql, record migration version."""
```

Initial version can be `1`.

### 6.3 `modules/db/repositories.py`

Keep repositories simple. Avoid large ORM abstractions in the first phase.

Required repository methods:

```python
class BatchRepository:
    create(...)
    get(batch_id: str)
    list(...)
    update_status(...)
    recompute_counts(batch_id: str)

class DocumentRepository:
    create_root(...)
    create_child(...)
    add_file(...)
    get(document_id: str)
    list_by_batch(batch_id: str)
    update_status(...)
    update_current_task(...)

class TaskRunRepository:
    create_started(...)
    mark_completed(...)
    mark_failed(...)
    list_by_document(document_id: str)

class ExtractionRepository:
    save_result(...)
    save_fields(...)
    get_latest_result(document_id: str)
    get_fields(document_id: str)
    apply_corrections(document_id: str, corrections: dict)

class ReviewRepository:
    create_review_item(...)
    list_queue(...)
    claim(...)
    release(...)
    complete(...)
    get_lock(...)

class AuditRepository:
    append(...)
    list_for_document(...)
    list_admin_events(...)

class ConfigVersionRepository:
    create_draft(...)
    get_active(config_type: str, name: str)
    get_draft(config_type: str, name: str)
    publish(...)
    list_versions(...)
```

## 7. Services Layer

Services coordinate repositories and business rules. API routes and tasks should call services, not raw SQL.

### 7.1 Batch Service

Responsibilities:

- Create batch for upload or watch folder ingestion.
- Preserve the ingestion source as `web` or `watch_folder` and retain watch-folder metadata such as source path and original filename.
- Create root document.
- Recompute aggregate status.
- Return UI-ready batch summaries.

### 7.2 Document Service

Responsibilities:

- Create child documents from split segments.
- Update document status.
- Retrieve document details with task runs, fields, and review status.
- Register document files with explicit roles such as `source_original`, `split_pdf`, `export_pdf`, `export_json`, `export_csv`, and `source_archive`.
- Treat child documents from split, or unsplit root documents, as leaf documents for extraction, review, export, and completion.
- Preserve parent/root document traceability for the original bundled PDF without letting successful split roots continue into downstream extraction/export tasks.

### 7.3 Workflow State Service

Responsibilities:

- Map pipeline task index to task key.
- Record task run start/completion/failure.
- Update `documents.current_task_index`.
- Detect paused state.
- Find the next task after a paused review gate.
- Build child workflow context from child document state plus parent/root source metadata after split fan-out.
- Keep child task state independent while preserving parent references through `parent_document_id`, root document metadata, and registered source artifacts.

### 7.4 Fan-In / Workflow Finalization Service

File: `modules/services/fan_in_service.py`

Responsibilities:

- Finalize a leaf document when its workflow reaches the end of the configured pipeline after mandatory housekeeping.
- Recompute aggregate state for the leaf's root/source document and batch.
- Treat child documents from split, or an unsplit root document, as leaf documents for completion counts.
- Preserve the root/source document as durable lineage state; fan-in must never delete parent/root records or registered artifacts.
- Mark a split root as still active while any child leaf is running, paused, or waiting for review.
- Mark a split root `completed` only when all leaf descendants completed successfully.
- Mark a split root `completed_with_errors` when all leaf descendants are terminal and at least one leaf failed.
- Recompute batch counts from leaf documents only so the root source container is not double-counted.
- Emit one idempotent audit event when a root fan-in completes.
- Use one SQLite transaction or an explicit write guard so concurrent child completions cannot produce stale parent/batch counts.

Suggested service shape:

```python
@dataclass(frozen=True)
class FanInResult:
    leaf_document_id: str
    root_document_id: str
    batch_id: str
    leaf_status: str
    root_status: str
    batch_status: str
    all_leaves_terminal: bool
    completed_leaves: int
    failed_leaves: int
    total_leaves: int


class FanInService:
    def finalize_leaf(self, context: dict[str, Any]) -> FanInResult:
        """Persist terminal leaf state and recompute root/batch aggregates."""
```

The service should infer the root document from `context["root_document_id"]`, `context["parent_document_id"]`, or the document row. For unsplit source documents, the document is both root and leaf.

Terminal leaf states:

- Success: `completed`.
- Failure: `failed`.
- Partial terminal success: `completed_with_errors` is allowed only for aggregate root/batch state, not as the default leaf success state.

Non-terminal leaf states:

- `processing`
- `resuming`
- `review_required`
- `in_review`
- `split_completed` on a root/source document with children

Aggregate status priority:

1. `review_required` if any leaf is waiting for or in human review.
2. `processing` if any leaf is running/resuming or not terminal.
3. `completed_with_errors` if all leaves are terminal and any leaf failed.
4. `completed` if all leaves are terminal and all leaves completed successfully.

Fan-in is state finalization only. It can make parent processing copies eligible for later retention cleanup by writing audit/metadata, but it must not delete files. Retention or housekeeping remains responsible for transient filesystem cleanup under explicit artifact rules.

### 7.5 Review Service

Responsibilities:

- Decide claim/release/complete behavior.
- Validate lock ownership before saving changes.
- Apply corrections to extracted fields.
- Mark review item complete.
- Trigger resume after completion.

### 7.6 Audit Service

Responsibilities:

- Append immutable audit events.
- Normalize before/after values.
- Record operator and system events.

### 7.7 Configuration Validation Service

File:

```text
modules/services/config_validation_service.py
```

Responsibilities:

- Wrap and reuse validation logic from `tools/config_check`.
- Validate `config.yaml` without requiring CLI execution.
- Return structured findings for API/UI consumption.
- Preserve CLI behavior by keeping `tools/config_check` as a supported entry point.
- Support strict and non-strict modes.
- Support import checks.
- Support base directory resolution.
- Coordinate all-schema validation results from `SchemaService` for the admin Validation Center.

API-facing finding shape:

```json
{
  "level": "error",
  "code": "missing-required-param",
  "path": "tasks.review_gate.params.schema_file",
  "message": "schema_file does not exist.",
  "suggestion": "Create the schema in Schema Editor or update the path.",
  "location": {
    "line": 42,
    "column": 7
  }
}
```

### 7.8 Pipeline Validation Service

File:

```text
modules/services/pipeline_validation_service.py
```

Responsibilities:

- Validate configured task order.
- Validate task modules and classes are importable.
- Validate `ReviewGateTask` placement and parameters.
- Validate extraction-before-storage dependencies.
- Validate split fan-out assumptions.
- Validate storage filename tokens against known extraction fields.
- Return structured findings compatible with `ConfigValidationService`.

### 7.9 Schema Service

File:

```text
modules/services/schema_service.py
```

Responsibilities are defined in Section 9.6. This service must also expose schema validation to both the schema editor UI and `ReviewGateTask`.

### 7.10 Pipeline Configuration Service

File:

```text
modules/services/pipeline_config_service.py
```

Responsibilities:

- Load the active YAML pipeline into an ordered step model.
- Create and update pipeline drafts.
- Reorder, enable, disable, add, and remove draft steps.
- Normalize task parameter values for form editing.
- Generate YAML preview from the draft model.
- Produce active-vs-draft diffs.
- Call `PipelineValidationService` before publish.
- Publish a validated draft by writing the updated config and recording `config_versions`.
- Append admin audit events for draft, validation, and publish actions.

### 7.11 Task Catalog Service

File:

```text
modules/services/task_catalog_service.py
```

Responsibilities:

- Discover configured and available task classes under `standard_step`.
- Return module path, class name, display label, docstring summary, and expected parameters.
- Mark task classes that cannot be imported.
- Identify known standard tasks such as extraction, split, rules, storage, and `ReviewGateTask`.
- Provide catalog entries for the pipeline configuration UI.

### 7.12 Admin Settings Service

File:

```text
modules/services/admin_settings_service.py
```

Responsibilities:

- Return non-secret runtime settings for operators and admins.
- Save admin-editable non-secret settings such as upload limits, watch folder paths, retention values, review lock timeout, and split settings.
- Redact secrets before returning config-derived values.
- Write settings changes through `config_versions` or `app_settings`.
- Append admin audit events.

## 8. Workflow Execution Design

Current `WorkflowLoader` builds a simple sequential flow. Extend behavior carefully.

### 8.1 Context Shape

Every task receives context like:

```python
{
    "id": "<document_id>",
    "document_id": "<document_id>",
    "batch_id": "<batch_id>",
    "file_path": "D:\\...\\file.pdf",
    "original_filename": "invoice.pdf",
    "source": "web",
    "source_path": "D:\\...\\watch\\input\\invoice.pdf",
    "data": {},
    "metadata": {},
    "error": None,
    "error_step": None,
    "pipeline_state": "running",
    "current_task_index": 0,
}
```

The old `id` field should point to `document_id` for backward compatibility.
For watch-folder ingestion, `source` should be `watch_folder` and `source_path` should identify the discovered file path before it is moved into the app working/originals area.

### 8.2 Task Run Recording

Before each task:

- Create `task_runs` record with `status = running`.
- Update document `current_task_index` and `current_task_key`.

After each task:

- If success, mark task run `completed`.
- If error, mark task run `failed`.
- If paused, mark task run `paused` or `completed` with output showing pause state. Prefer `paused` if implemented.

### 8.3 Skip/Pass-Through

Do not use a special Prefect skip mechanism for `ReviewGateTask`.

Instead:

- Always run `ReviewGateTask` when it appears in the pipeline.
- If no review is required, the task returns context with:

```python
context["review_required"] = False
context["review_gate_status"] = "passed"
```

- Workflow continues normally.

### 8.4 Pause

If review is required:

```python
context["pipeline_state"] = "paused"
context["pause_reason"] = "review_required"
context["review_item_id"] = "<review_item_id>"
```

`WorkflowLoader` must detect this after the task returns:

```python
if current_context.get("pipeline_state") == "paused":
    document_service.update_status(document_id, "review_required")
    return current_context
```

No downstream task should run for that document until resume.

### 8.5 Resume

Add `modules/resume_manager.py`.

Implement:

```python
class ResumeManager:
    def resume_document(self, document_id: str, user: str | None = None) -> bool:
        """Resume pipeline from the next task after current_task_index."""
```

Resume logic:

1. Load document.
2. Confirm document status is `review_completed` or `resuming`.
3. Build context from SQLite:
   - document fields with corrected values as final values.
   - latest extraction metadata.
   - file path.
4. Start workflow from `current_task_index + 1`.
5. Prevent duplicate resume if downstream task run already completed.

To support this cleanly, add optional parameter to workflow loader:

```python
load_workflow(start_task_index: int = 0)
```

or add:

```python
run_pipeline_for_document(document_id: str, start_task_index: int)
```

### 8.6 Fan-In Finalization

Fan-in must be triggered by orchestration after a leaf workflow reaches a terminal state. It should be called after mandatory housekeeping returns so cleanup errors can be reflected in the leaf status.

Recommended integration point:

```python
final_context = run_housekeeping(current_context)
fan_in_result = FanInService(conn).finalize_leaf(final_context)
return final_context
```

Rules:

- Do not run fan-in for a context with `pipeline_state = "fan_out"`; the root/source document has stopped after split and is waiting for child leaves.
- Do not mark a paused leaf terminal. A paused leaf updates the aggregate as `review_required` or `in_review`, then waits for review completion/resume.
- On successful leaf completion, set the leaf document status to `completed`.
- On workflow or housekeeping error, set the leaf document status to `failed`.
- After each leaf status update, recompute root/source and batch aggregate state from leaf descendants.
- For split roots, keep the root/source record as a lineage container. It should move from `split_completed`/`processing` to `completed` or `completed_with_errors` only after all child leaves are terminal.
- For unsplit roots, the root is also the leaf; fan-in updates the batch directly.
- Write one audit event such as `fan_in_completed` when a root transitions into a terminal aggregate state. Repeated fan-in calls after that transition must be no-ops except for recomputing counts.

Fan-in should not be implemented inside `CleanupTask`. Housekeeping handles explicit transient file deletion. Fan-in handles SQLite state finalization and aggregate status.

## 9. ReviewGateTask Design

File: `standard_step/review/review_gate.py`

Class: `ReviewGateTask(BaseTask)`

### 9.1 Parameters

Supported params:

```python
mode: str = "field_confidence"
confidence_threshold: float = 0.90
split_confidence_levels_requiring_review: list[str] | None = None
require_review_when_missing_confidence: bool = True
require_review_for_missing_required_fields: bool = True
always_review: bool = False
business_rule_flags: list[str] | None = None
schema_file: str | None = None
queue_name: str = "default_review"
review_scope: str = "low_confidence_fields"
allow_operator_to_edit_high_confidence_fields: bool = True
resume_policy: str = "next_task"
```

### 9.2 Decision Algorithm

Pseudo-code:

```python
def run(self, context):
    fields = extraction_repository.get_fields(context["document_id"])
    reasons = []

    if always_review:
        reasons.append(("always_review", None))

    for flag in business_rule_flags or []:
        if context.get(flag) is True or context.get("data", {}).get(flag) is True:
            reasons.append(("business_rule", flag))

    split_confidence = context.get("split_confidence")
    if split_confidence in (split_confidence_levels_requiring_review or []):
        reasons.append(("split_confidence", split_confidence))

    for field in fields:
        if field.confidence is None:
            if require_review_when_missing_confidence:
                reasons.append(("missing_confidence", field.field_key))
        elif field.confidence < confidence_threshold:
            reasons.append(("low_confidence", field.field_key))

    if schema_file:
        validation_errors = validate_against_schema(context["data"], schema_file)
        for error in validation_errors:
            reasons.append(("schema_error", error.field_key))

    if not reasons:
        context["review_required"] = False
        context["review_gate_status"] = "passed"
        return context

    review_item_id = review_service.create_review_item(
        batch_id=context["batch_id"],
        document_id=context["document_id"],
        queue_name=queue_name,
        reason="; ".join(unique reason types),
        scope=review_scope,
        metadata={"reasons": reasons},
    )

    context["review_required"] = True
    context["review_gate_status"] = "paused"
    context["pipeline_state"] = "paused"
    context["pause_reason"] = "review_required"
    context["review_item_id"] = review_item_id
    return context
```

### 9.3 Required Tests

- No fields below threshold -> pass-through.
- One field below threshold -> creates review item and pauses.
- Missing confidence with flag true -> pauses.
- Missing confidence with flag false -> pass-through.
- Schema validation error -> pauses.
- Existing review item for same document/task -> do not duplicate.

### 9.4 Review UI Metadata Output

`ReviewGateTask` must create enough metadata for the UI to render a schema-driven review screen.

When creating `review_items.metadata_json`, include:

```json
{
  "schema_file": "schemas/invoice_schema.yaml",
  "schema_version": "optional-version-or-file-hash",
  "review_scope": "low_confidence_fields",
  "editable_fields": ["supplier_name", "invoice_total", "line_items"],
  "highlight_fields": ["invoice_total", "currency"],
  "reasons": [
    {
      "type": "low_confidence",
      "field_key": "invoice_total",
      "confidence": 0.72,
      "message": "Field confidence is below threshold 0.90."
    }
  ],
  "allow_operator_to_edit_high_confidence_fields": true
}
```

The UI must not need to re-run `ReviewGateTask` to know what to show. It should load the review item, schema, extracted fields, document PDF URL, and metadata through API endpoints.

### 9.5 Schema Compatibility Requirements

The review gate and review UI must support schemas migrated from `qa_extracted_data/schemas`.

Supported field types:

- `string`
- `number`
- `integer`
- `boolean`
- `date`
- `datetime`
- `enum`
- `array`
- `object`

Supported complex structures:

- Scalar arrays.
- Object arrays, such as invoice line items.
- Nested objects.

If a schema contains unsupported field options, the UI must still render a fallback text/JSON editor for that field and show a non-blocking warning.

### 9.6 Schema Service

Add a schema service so both `ReviewGateTask` and the UI use the same schema interpretation.

File:

```text
modules/services/schema_service.py
```

Responsibilities:

- Load YAML/JSON schema files from configured schema directories.
- Normalize schema fields into UI field definitions.
- Validate corrected values.
- Provide schema metadata such as title, description, version/hash, and field list.
- Convert existing `qa_extracted_data` schema format to a canonical internal field definition.

Canonical UI field definition:

```json
{
  "field_key": "invoice_total",
  "label": "Invoice Total",
  "type": "number",
  "required": true,
  "help": "Total invoice amount",
  "choices": null,
  "min_value": 0,
  "max_value": null,
  "children": null,
  "item_schema": null
}
```

## 10. Extraction Integration

Modify `ExtractPdfV2Task` after it normalizes data:

1. Continue updating `context["data"]`.
2. Save extraction result to SQLite if `document_id` exists.
3. Save individual fields to `extracted_fields`.
4. Store confidence if available in extraction metadata.

If field-level numeric confidence is not available, store:

- `confidence = NULL`
- `confidence_label = NULL`

Do not fabricate confidence values.

Add helper:

```python
def persist_extraction_result(context, processed_data, metadata, fields_config): ...
```

Keep it in a service or repository, not inside large SQL blocks in the task.

## 11. Split Task Design

### 11.1 Adapter

File: `standard_step/split/llamacloud_split_adapter.py`

Implement:

```python
@dataclass
class SplitSegment:
    category: str | None
    confidence: str | None
    pages: list[int]
    page_start: int
    page_end: int
    metadata: dict

@dataclass
class SplitResult:
    provider_job_id: str | None
    segments: list[SplitSegment]
    raw_response: dict

class LlamaCloudSplitAdapter:
    def split_pdf(self, file_path: str, categories: list[dict]) -> SplitResult:
        ...
```

Keep API-specific parsing here. LlamaCloud Split returns category, confidence category, and a list of 1-indexed pages; it does not create split PDF files. Normalize provider responses in this adapter and keep raw provider fields in `metadata`/`raw_response` so beta API changes are isolated.

Adapter call flow:

- Upload the source PDF through the LlamaCloud Files API with `purpose="split"`.
- Submit configured categories and `allow_uncategorized` behavior to the beta split API.
- Poll for completion through the SDK or HTTP API inside the adapter only.
- Return normalized `SplitSegment` values to the task; never write local files from the adapter.

### 11.2 Task

File: `standard_step/split/llamacloud_split.py`

Class: `LlamaCloudSplitTask(BaseTask)`

Responsibilities:

- Call adapter.
- Persist raw split metadata to the current root document metadata or a registered source/split artifact record.
- Register the root source PDF as `source_original` when it has not already been registered.
- For each segment:
  - Create split PDF in configured split directory.
  - Create child document record.
  - Add `split_pdf` document file record.
  - Store 1-indexed page traceability on the child document and exact returned pages in child metadata.
- Set parent document status to `split_completed`.
- Set context:

```python
context["split_children"] = [child_document_id, ...]
context["pipeline_state"] = "fan_out"
```

The split task must run only for source/root documents. If split is disabled or not needed, it should leave the root document as the leaf document and allow the pipeline to continue normally.

Child metadata should include:

```json
{
  "root_document_id": "doc_root",
  "source_original_filename": "bundle.pdf",
  "source_file_path": "D:/.../bundle.pdf",
  "source_file_artifact_id": "file_source",
  "split_provider_job_id": "spl_123",
  "split_segment_index": 0,
  "split_pages": [1, 2, 3],
  "split_category": "invoice",
  "split_confidence": "high"
}
```

Do not copy mutable parent extraction/review/export state into child documents. If pre-split tasks later produce immutable data needed by all children, copy it deliberately into `metadata_json.inherited_context` with an explicit version marker.

### 11.3 PDF Page Extraction

Use `pypdf` for the first local PDF splitting implementation. It is pure Python, already available in the current development environment, and is sufficient for deterministic page extraction. Do not use `PyPDF2` for new code; that project line has been superseded by `pypdf`.

Page numbers from LlamaCloud are 1-indexed. Convert to 0-indexed only at the local PDF extraction boundary. Preserve the provider's exact 1-indexed `pages` list in metadata, and derive `page_start`/`page_end` as `min(pages)` and `max(pages)` for summary display and filtering.

Local splitting helper shape:

```python
def create_split_pdf(
    source_pdf_path: str,
    output_pdf_path: str,
    pages_1_indexed: list[int],
) -> None:
    """Create one child PDF from 1-indexed source pages."""
```

The helper should validate that every requested page exists, fail before creating a child document when the range is invalid, and write the child document record only after the PDF exists.

### 11.4 Fan-Out Execution

Initial simple implementation:

- Split task returns `pipeline_state = "fan_out"`.
- Workflow stops parent document pipeline after split.
- Workflow manager starts child document pipelines from next task index.
- Child workflow context uses the child `document_id`, child PDF `file_path`, inherited `batch_id`, original source filename, split category, split confidence, and page traceability.
- Child workflow context also includes `parent_document_id`, `root_document_id`, `source_original_filename`, `source_file_path`, `split_pages`, `page_start`, `page_end`, and any explicit immutable `inherited_context` snapshot.
- Downstream extraction, review, rules, reference updates, storage, export, and archive tasks operate on the current child context and must not special-case the original root PDF.

This is simpler than trying to continue multiple child flows inside the same parent Prefect run.

### 11.5 Fan-In After Child Completion

Fan-out creates independent leaf workflows; fan-in closes the loop once those leaf workflows finish.

- Child workflow completion must call `FanInService.finalize_leaf(...)` after mandatory housekeeping.
- The service must recompute aggregate root and batch state from leaf documents, not from the root source container.
- The root/source document remains a durable parent record and should not be deleted or overwritten with child task state.
- Root/source status remains `split_completed`, `processing`, or a review/active aggregate while any child leaf is unfinished.
- Root/source status becomes `completed` only after every child leaf completed successfully.
- Root/source status becomes `completed_with_errors` when every child leaf is terminal and at least one leaf failed.
- Batch status follows the same leaf-derived aggregate. Batch `total_documents`, `completed_documents`, and `failed_documents` must count leaves only.
- Fan-in must record an audit event for the root aggregate transition and must be idempotent across repeated or concurrent child workflow completion callbacks.
- Parent/source processing-copy cleanup can become eligible after fan-in, but actual deletion remains a housekeeping/retention decision and must respect registered artifact roles.

### 11.6 Update Reference Task After Split

`standard_step.rules.update_reference.UpdateReferenceTask` mutates a configured CSV reference file, so it must be handled as a leaf-document side effect.

- Run `update_reference` only in child/leaf workflows after the split task. The parent/root bundle must not execute it after successful fan-out.
- Use the leaf document's extracted `context["data"]` plus inherited source fields when resolving `csv_match.clauses[*].from_context`.
- Treat the CSV file and optional `.backup` as reference data, not workflow state.
- Persist selected-row and updated-row counts through `task_runs.output_json`; add audit metadata when the audit service is available.
- If child workflows are started in parallel, serialize writes to the same `reference_file` with a file-level lock or a dedicated reference-update service. The initial implementation may run child workflows sequentially to avoid introducing a shared CSV write race.
- Resume must be idempotent: a repeated downstream resume must not repeat `update_reference` if the task already has a completed task-run for the same leaf document and task key unless an explicit rerun mode is requested.
- Fan-in runs after the leaf workflow finishes, so `update_reference` completion or failure must be reflected on the leaf document before aggregate root/batch state is computed.

### 11.7 Housekeeping After Split

`standard_step.housekeeping.cleanup_task.CleanupTask` currently deletes the active `context["file_path"]`; that behavior is unsafe for split children because child `file_path` is the registered `split_pdf` artifact.

Refactor housekeeping semantics during the SQLite migration:

- Prefer `context["cleanup_paths"]` or transient artifact records over deleting `context["file_path"]`.
- Delete only transient processing copies under the configured processing directory.
- Never delete registered `source_original`, `split_pdf`, `export_pdf`, `export_json`, `export_csv`, or `source_archive` files from housekeeping.
- Root/source housekeeping after fan-out can remove the transient upload/watch processing copy only after a durable source artifact exists.
- Child housekeeping should normally leave the `split_pdf` in place until a retention task confirms it is no longer needed for review preview, retry, audit, or export traceability.
- Record cleanup actions through task-run output and audit metadata instead of text status files.
- Housekeeping must not decide whether all child documents are complete. That decision belongs to fan-in finalization after housekeeping returns.

### 11.8 Artifact and Archive Semantics

Split fan-out requires artifact roles to stay explicit:

- `source_original`: the original uploaded or watched PDF for the root document.
- `split_pdf`: a locally generated child PDF used as the active file for a child document.
- `export_pdf`, `export_json`, `export_csv`: final business outputs for a leaf document.
- `source_archive`: archived copy of the original source PDF.

Source archival should happen once for the root/source document. Child split PDFs are working artifacts and should not be copied by the source archive task as if they were newly ingested originals. If the business workflow needs final child PDFs in an archive/export folder, use a distinct storage/export task that records `export_pdf` or another explicit role.

Batch status should be computed from leaf documents. A root document that reached `split_completed` is successful only as a source container; the batch is not complete until all created child documents reach terminal states.

## 12. API Design

Add routes in `modules/api_router.py` for the first implementation. If the file becomes too large, split route groups later without changing the endpoint contract.

Recommended endpoints:

```text
POST /api/batches/upload
GET  /api/batches
GET  /api/batches/{batch_id}
GET  /api/batches/{batch_id}/documents

GET  /api/documents/{document_id}
GET  /api/documents/{document_id}/task-runs
GET  /api/documents/{document_id}/fields
GET  /api/documents/{document_id}/extraction
GET  /api/documents/{document_id}/audit
GET  /api/documents/{document_id}/file/pdf
POST /api/documents/{document_id}/resume
GET  /api/documents/{document_id}/export

GET  /api/batches/{batch_id}/split-results

GET  /api/review/items
GET  /api/review/items/{review_item_id}
POST /api/review/items/{review_item_id}/claim
POST /api/review/items/{review_item_id}/release
POST /api/review/items/{review_item_id}/draft
POST /api/review/items/{review_item_id}/diff
POST /api/review/items/{review_item_id}/complete

GET  /api/schemas
GET  /api/schemas/{schema_name}
POST /api/schemas
PUT  /api/schemas/{schema_name}
POST /api/schemas/{schema_name}/validate
POST /api/schemas/{schema_name}/duplicate

GET  /api/config/validation
POST /api/config/validation
POST /api/pipeline/validate

GET  /api/reports/summary
GET  /api/settings

GET  /api/admin/summary
GET  /api/admin/schemas/validation
POST /api/admin/schemas/validate-all
GET  /api/admin/pipeline
PUT  /api/admin/pipeline/draft
POST /api/admin/pipeline/diff
POST /api/admin/pipeline/validate
POST /api/admin/pipeline/publish
GET  /api/admin/task-catalog
GET  /api/admin/review-gate-rules
PUT  /api/admin/review-gate-rules
GET  /api/admin/split-settings
PUT  /api/admin/split-settings
POST /api/admin/split-settings/test-connection
GET  /api/admin/settings
PUT  /api/admin/settings
GET  /api/admin/audit
POST /api/admin/dry-run
```

All `/api/admin/*` endpoints must require an admin role. Schema write endpoints, schema validation-all, and `/api/pipeline/validate` must also require admin authorization when they operate on application configuration rather than review-time data.

### 12.1 Complete Review Payload

Request:

```json
{
  "corrections": {
    "supplier_name": "ACME PTE LTD",
    "invoice_total": "123.45"
  }
}
```

Server behavior:

1. Validate user owns lock.
2. Validate corrections against schema when configured.
3. Update `extracted_fields.corrected_value_json` and `final_value_json`.
4. Mark review item complete.
5. Set document status `review_completed`.
6. Append audit event.
7. Trigger resume.

## 13. UI Refactor Design

The new UI must closely model the static prototype in:

```text
D:\python_code\pdfdoc_extraction\refactor UI prototype
```

Prototype files to use as visual references:

```text
index.html                 -> Upload and Process
processing.html            -> Processing Overview
split-results.html         -> Split Results
extraction-results.html    -> Extraction Results
review-queue.html          -> Review Queue
human-review.html          -> Human Review
overview.html              -> Prototype index only; do not build as app landing page
```

The first implementation should use FastAPI + Jinja templates, not Streamlit. The prototype uses Tailwind and DaisyUI. For the first refactor, keep that visual system:

- Use DaisyUI/Tailwind CDN in development templates if fastest.
- Put app-specific styling in `web/static/css/app.css`.
- Put behavior in small page-specific JS files under `web/static/js/`.
- Do not introduce React/Vue/Svelte in the first UI milestone.

### 13.1 UI Implementation Files

Create:

```text
web/templates/app_base.html
web/templates/upload_process.html
web/templates/processing_overview.html
web/templates/split_results.html
web/templates/extraction_results.html
web/templates/review_queue.html
web/templates/human_review.html
web/templates/schema_editor.html
web/templates/config_validation.html
web/templates/admin_dashboard.html
web/templates/pipeline_config.html
web/templates/task_catalog.html
web/templates/review_gate_rules.html
web/templates/split_settings.html
web/templates/admin_audit.html
web/templates/pipeline_dry_run.html
web/templates/reports.html
web/templates/settings.html

web/static/css/app.css
web/static/js/app.js
web/static/js/upload_process.js
web/static/js/processing_overview.js
web/static/js/review_queue.js
web/static/js/human_review.js
web/static/js/pdf_viewer.js
web/static/js/schema_editor.js
web/static/js/config_validation.js
web/static/js/admin.js
web/static/js/pipeline_config.js
web/static/js/task_catalog.js
web/static/js/review_gate_rules.js
web/static/js/split_settings.js
web/static/js/admin_audit.js
web/static/js/pipeline_dry_run.js
```

Existing templates can stay during migration, but final navigation should point to the new templates.

### 13.2 Page Routes

Add page routes in `web/server.py`:

```text
GET /app                         -> redirect to /app/upload
GET /app/upload                  -> upload_process.html
GET /app/processing              -> processing_overview.html
GET /app/batches/{batch_id}      -> processing_overview.html filtered to one batch
GET /app/batches/{batch_id}/split-results -> split_results.html
GET /app/documents/{document_id}/extraction -> extraction_results.html
GET /app/review                  -> review_queue.html
GET /app/review/{review_item_id} -> human_review.html
GET /app/schemas                 -> schema_editor.html
GET /app/schemas/{schema_name}   -> schema_editor.html
GET /app/settings/validation     -> config_validation.html
GET /app/admin                   -> admin_dashboard.html
GET /app/admin/pipeline          -> pipeline_config.html
GET /app/admin/tasks             -> task_catalog.html
GET /app/admin/review-gate       -> review_gate_rules.html
GET /app/admin/split             -> split_settings.html
GET /app/admin/audit             -> admin_audit.html
GET /app/admin/dry-run           -> pipeline_dry_run.html
GET /app/reports                 -> reports.html
GET /app/settings                -> settings.html
```

Keep `/dashboard` during transition, but it can redirect to `/app/processing` after the new UI is ready.

All `/app/*` routes must require authentication.
All `/app/admin/*`, `/app/schemas`, and `/app/settings/validation` routes must require an admin role.

### 13.2.1 Role-Based UI Model

The UI has two roles:

- `operator`: can use upload, processing, split results, extraction results, review queue, human review, basic reports, and read-only settings.
- `admin`: can use every operator screen plus schema management, validation center, pipeline configuration, task catalog, review-gate rules, split settings, admin audit, and dry run.

The first implementation can use the existing authentication/session mechanism with a simple role field. It does not need SSO or enterprise identity integration.

Server-side authorization is required. Hiding links in the UI is not sufficient.

### 13.3 Shared Layout: `app_base.html`

Model the base layout directly after the prototype:

```html
<body class="bg-base-200 min-h-screen">
  <div class="flex min-h-screen">
    <aside class="w-56 bg-base-100 border-r border-base-200 flex flex-col py-4 px-3 gap-1 shrink-0">
      <!-- Brand -->
      <!-- Sidebar links -->
    </aside>

    <main class="flex-1 flex flex-col min-w-0">
      <header class="bg-base-100 border-b border-base-200 px-6 py-4 flex items-center justify-between">
        <!-- page title + subtitle + actions -->
      </header>

      <div class="flex-1 p-6">
        {% block content %}{% endblock %}
      </div>
    </main>
  </div>
</body>
```

Sidebar requirements:

- Brand label: `DocFlow AI` unless overridden by `ui.app_name`.
- Active route highlight must match prototype: light primary background and primary text.
- Primary sidebar links should match the prototype:
  - Upload and Process -> `/app/upload`
  - Review Queue -> `/app/review`
  - Reports -> `/app/reports`
  - Settings -> `/app/settings`
- Workflow detail pages should use contextual links and buttons:
  - Processing Overview -> `/app/processing` and `/app/batches/{batch_id}`
  - Split Results -> `/app/batches/{batch_id}/split-results`
  - Extraction Results -> `/app/documents/{document_id}/extraction`
  - Human Review -> `/app/review/{review_item_id}`
- Admin subpages should be linked from Settings:
  - Schema Editor -> `/app/schemas`
  - Configuration Validation -> `/app/settings/validation`
- When current user is admin, show an additional compact `Admin` sidebar group below the prototype-style primary links:
  - Admin Home -> `/app/admin`
  - Schemas -> `/app/schemas`
  - Validation -> `/app/settings/validation`
  - Pipeline -> `/app/admin/pipeline`
  - Tasks -> `/app/admin/tasks`
  - Review Gate -> `/app/admin/review-gate`
  - Split Settings -> `/app/admin/split`
  - Audit -> `/app/admin/audit`
  - Dry Run -> `/app/admin/dry-run`
- Operators must not see the `Admin` group.
- Use the same compact, operational sidebar style from the prototype.
- Icons may initially remain inline SVG copied from the prototype. Do not block the refactor on icon library setup.

Header requirements:

- Left side: page title and short subtitle.
- Right side: page-specific actions and notification/user controls.
- Avoid large hero blocks. This is an operational app, not a marketing page.

### 13.4 Shared CSS Rules

Put shared CSS in `web/static/css/app.css`.

Minimum classes:

```css
.nav-link {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.55);
  transition: background 0.15s, color 0.15s;
}

.nav-link:hover {
  background: rgba(0, 0, 0, 0.06);
}

.nav-link.active {
  background: rgba(99, 102, 241, 0.12);
  color: #4f46e5;
}

.page-grid {
  display: grid;
  gap: 1rem;
}

.metric-card {
  min-height: 6rem;
}
```

Do not use Streamlit-style injected CSS in the final app.

### 13.5 Shared JavaScript: `app.js`

Implement small helpers:

```javascript
async function apiGet(url) { ... }
async function apiPost(url, payload) { ... }
function formatDateTime(isoString) { ... }
function showToast(message, type = "info") { ... }
function setActiveNav() { ... }
```

Use normal `fetch`. Keep dependencies minimal.

### 13.6 Upload and Process Page

Prototype reference: `index.html`.

Template: `upload_process.html`.

Route: `GET /app/upload`.

Required visual sections:

1. Drop zone card.
2. Selected file list card.
3. Total files and total size summary.
4. Start processing button.

Layout must match the prototype:

```text
Header: Upload and Process
Content:
  card: drag/drop PDF files
  card: file rows + total + start button
```

Page behavior:

- User can drag and drop one or more PDFs.
- User can choose files through file picker.
- File rows show:
  - PDF icon.
  - Original filename.
  - File size.
  - Validation/upload status icon.
- Client-side validation:
  - extension `.pdf`
  - MIME type when browser provides it
  - size limit from `/api/settings` or template context
- `Start Processing` uploads all selected files as a batch.
- On success, redirect to `/app/batches/{batch_id}`.

API endpoints:

```text
POST /api/batches/upload
```

Request:

- Multipart form.
- Field name: `files`.
- Multiple files allowed.

Response:

```json
{
  "batch_id": "batch_123",
  "document_ids": ["doc_1", "doc_2"],
  "status": "queued"
}
```

JS file: `upload_process.js`.

Functions:

```javascript
handleFileSelection(files)
renderSelectedFiles()
uploadBatch()
```

### 13.7 Processing Overview Page

Prototype reference: `processing.html`.

Template: `processing_overview.html`.

Routes:

```text
GET /app/processing
GET /app/batches/{batch_id}
```

Required visual sections:

1. Pipeline steps card.
2. Overall progress bar.
3. Processing queue table.

Step display must use prototype stages:

```text
Uploaded -> Splitting -> Extracting -> Review -> Output
```

If no split task is configured, the Splitting step should show `Skipped` or be visually inactive.

Processing queue table columns:

```text
File Name
Status
Splitting
Extracting
Review
Output
Progress
Action
```

Status rendering:

- `received`, `queued`: neutral badge.
- `processing`: primary badge.
- `split_completed`, `extraction_completed`, `review_completed`: success check icon.
- `review_required`: warning badge.
- `failed`: error badge.
- `completed`: success badge.

API endpoints:

```text
GET /api/batches
GET /api/batches/{batch_id}
GET /api/batches/{batch_id}/documents
```

Response shape for batch detail:

```json
{
  "batch": {
    "id": "batch_123",
    "status": "processing",
    "total_documents": 5,
    "completed_documents": 2,
    "failed_documents": 0,
    "progress_percent": 40
  },
  "pipeline_steps": [
    {"key": "upload", "label": "Uploaded", "status": "completed"},
    {"key": "split", "label": "Splitting", "status": "completed"},
    {"key": "extract", "label": "Extracting", "status": "running"},
    {"key": "review", "label": "Review", "status": "pending"},
    {"key": "output", "label": "Output", "status": "pending"}
  ],
  "documents": [
    {
      "id": "doc_123",
      "filename": "invoice_batch.pdf",
      "status": "processing",
      "split_status": "completed",
      "extraction_status": "running",
      "review_status": "pending",
      "output_status": "pending",
      "progress_percent": 70
    }
  ]
}
```

JS file: `processing_overview.js`.

Behavior:

- Poll every 3 seconds while any batch/document is active.
- Stop polling when all visible documents are terminal.
- Row action links:
  - Split result available -> `/app/batches/{batch_id}/split-results`.
  - Extraction available -> `/app/documents/{document_id}/extraction`.
  - Review required -> `/app/review/{review_item_id}`.

### 13.8 Split Results Page

Prototype reference: `split-results.html`.

Template: `split_results.html`.

Route:

```text
GET /app/batches/{batch_id}/split-results
```

Required visual sections:

1. Four metric cards:
   - Total Files.
   - Documents Created.
   - Successful.
   - Failed.
2. Results table.
3. Download all button.
4. Link to extraction results.

Results table columns:

```text
Source File
Documents Created
Status
Action
```

Expandable child rows should show:

```text
Child Document
Category
Pages
Split Confidence
Status
Action
```

API endpoint:

```text
GET /api/batches/{batch_id}/split-results
```

Response:

```json
{
  "summary": {
    "total_files": 3,
    "documents_created": 12,
    "successful": 12,
    "failed": 0
  },
  "sources": [
    {
      "document_id": "doc_parent",
      "source_file": "invoice_batch.pdf",
      "documents_created": 5,
      "status": "success",
      "children": [
        {
          "document_id": "doc_child",
          "filename": "invoice_batch_pages_1_2.pdf",
          "category": "invoice",
          "page_start": 1,
          "page_end": 2,
          "split_confidence": "high",
          "status": "extraction_completed"
        }
      ]
    }
  ]
}
```

### 13.9 Extraction Results Page

Prototype reference: `extraction-results.html`.

Template: `extraction_results.html`.

Route:

```text
GET /app/documents/{document_id}/extraction
```

Required visual sections:

1. Left document preview panel.
2. Confidence legend.
3. Document selector.
4. Previous and next buttons.
5. Extraction table.
6. Link to review queue when review is required.

Extraction table columns:

```text
Field
Extracted Value
Final Value
Confidence
Review Status
```

Confidence badge rules:

- `confidence >= 0.90`: success badge.
- `0.70 <= confidence < 0.90`: warning badge.
- `confidence < 0.70`: error badge.
- missing confidence: neutral badge with `N/A`.

API endpoint:

```text
GET /api/documents/{document_id}/extraction
```

Response:

```json
{
  "document": {
    "id": "doc_123",
    "filename": "INV-001.pdf",
    "document_type": "invoice",
    "status": "review_required",
    "preview_url": "/api/documents/doc_123/file/pdf"
  },
  "siblings": [
    {"id": "doc_prev", "label": "INV-000.pdf"},
    {"id": "doc_123", "label": "INV-001.pdf"}
  ],
  "fields": [
    {
      "field_key": "invoice_number",
      "field_alias": "Invoice Number",
      "extracted_value": "INV-001",
      "corrected_value": null,
      "final_value": "INV-001",
      "confidence": 0.95,
      "review_status": "not_required"
    }
  ],
  "review_item_id": "review_123"
}
```

PDF preview:

- First milestone can use browser PDF embed:

```html
<iframe src="/api/documents/{{ document.id }}/file/pdf"></iframe>
```

- If iframe rendering is poor, add image preview later.

### 13.10 Review Queue Page

Prototype reference: `review-queue.html`.

Template: `review_queue.html`.

Route:

```text
GET /app/review
```

Required visual sections:

1. Filter tabs.
2. Search input.
3. Queue table.
4. Pagination.

Filter tabs must match prototype:

```text
All
Low Confidence
In Review
Completed
```

Queue table columns:

```text
Document
Type
Low Confidence Fields
Lowest Confidence
Status
Assigned To
Action
```

Row behavior:

- Clicking a pending row should claim/open if unclaimed.
- If already locked by current user, open.
- If locked by another user, show locked state and disable editing.

API endpoint:

```text
GET /api/review/items?status=pending&q=...
POST /api/review/items/{review_item_id}/claim
```

Response:

```json
{
  "items": [
    {
      "id": "review_123",
      "document_id": "doc_123",
      "document_name": "INV-023.pdf",
      "document_type": "Invoice",
      "low_confidence_fields": ["Total Amount", "Currency"],
      "lowest_confidence": 0.68,
      "status": "pending",
      "assigned_to": null,
      "locked_by": null,
      "lock_expires_at": null
    }
  ],
  "counts": {
    "all": 4,
    "low_confidence": 6,
    "in_review": 1,
    "completed": 2
  },
  "page": 1,
  "page_size": 25,
  "total": 4
}
```

JS file: `review_queue.js`.

Functions:

```javascript
loadReviewItems()
applyFilter(filterName)
claimAndOpen(reviewItemId)
renderPagination()
```

### 13.11 Human Review Page

Prototype reference: `human-review.html`.

Template: `human_review.html`.

Route:

```text
GET /app/review/{review_item_id}
```

Required visual sections:

1. Left document selector.
2. Previous/next buttons.
3. PDF preview panel.
4. Lowest confidence summary.
5. Field correction table.
6. Save draft button.
7. Mark as complete button.
8. Back to queue button.

Layout must match prototype:

```text
Main content:
  left fixed-width document preview column
  right flexible review table card
```

The first version must be more capable than the static prototype. It must reproduce the dynamic behavior of the current Streamlit QA app without using Streamlit.

#### 13.11.1 PDF Viewer Requirements

The PDF viewer is required. Human operators must be able to compare the extracted data against the source document.

Viewer placement:

- Left column on desktop.
- Above the field editor on narrow screens.

Minimum viewer controls:

- Previous page.
- Next page.
- Current page number.
- Total page count when known.
- Zoom in.
- Zoom out.
- Fit width.
- Open original PDF in new tab.

Implementation options:

- First milestone: browser PDF iframe/object using `/api/documents/{document_id}/file/pdf`.
- Better milestone: PDF.js viewer embedded in the page.

Preferred first robust approach:

```text
web/static/vendor/pdfjs/
web/static/js/pdf_viewer.js
GET /api/documents/{document_id}/file/pdf
```

If PDF.js is not added immediately, the HTML must still reserve the viewer panel and use an iframe fallback:

```html
<iframe
  class="w-full h-full min-h-[520px] rounded bg-base-100"
  src="/api/documents/{{ document.id }}/file/pdf"
></iframe>
```

Security requirements:

- The file-serving endpoint must validate that the requested document belongs to a known `documents` record.
- Do not serve arbitrary paths from query parameters.
- Use `FileResponse` only for registered document file paths.

#### 13.11.2 Schema-Driven Dynamic Form Requirements

The review editor must render dynamically from the configured schema, similar to the current Streamlit app.

Do not hardcode invoice fields into the template.

The server must provide a normalized schema and field state to the page. The browser renders inputs from that definition.

Field correction table columns:

```text
Field
Extracted Value
Confidence
Corrected Value
State
```

For complex schemas, the UI may switch from a simple table to grouped sections. The field editor must support:

- Scalar string fields.
- Number/integer fields.
- Boolean fields.
- Date and datetime fields.
- Enum/dropdown fields.
- Multiline text fields.
- Nested objects.
- Scalar arrays.
- Object arrays, especially invoice line items.

Recommended editor layout:

```text
Review table/card
  section: Invoice Header
    row: supplier_name
    row: invoice_number
    row: invoice_total
  section: Line Items
    editable grid:
      description | quantity | unit_price | amount | actions
  section: Metadata / Other Fields
```

For object arrays:

- Render as an editable table/grid.
- Add row button.
- Delete row button.
- Duplicate row button is optional.
- Validate each row against `item_schema`.
- Preserve row order.
- Show row-level validation messages.

For nested objects:

- Render as collapsible field groups.
- Use dotted field keys in the browser only when needed, e.g. `supplier.address.postal_code`.
- Server-side correction payload should remain structured JSON.

#### 13.11.3 UI Field Definition Contract

The review detail API must return schema-normalized field definitions, not only extracted fields.

Each field definition:

```json
{
  "field_key": "invoice_total",
  "label": "Invoice Total",
  "type": "number",
  "required": true,
  "help": "Total invoice amount",
  "choices": null,
  "editable": true,
  "highlight": true,
  "review_reason": "low_confidence",
  "extracted_value": "12,340.00",
  "corrected_value": null,
  "final_value": "12,340.00",
  "confidence": 0.72,
  "validation_errors": []
}
```

Object array field definition:

```json
{
  "field_key": "line_items",
  "label": "Line Items",
  "type": "array",
  "required": false,
  "item_type": "object",
  "item_schema": {
    "fields": [
      {"field_key": "description", "label": "Description", "type": "string", "required": true},
      {"field_key": "quantity", "label": "Quantity", "type": "number", "required": false},
      {"field_key": "amount", "label": "Amount", "type": "number", "required": false}
    ]
  },
  "extracted_value": [
    {"description": "Widget", "quantity": "2", "amount": "10.00"}
  ],
  "corrected_value": null,
  "confidence": null,
  "validation_errors": []
}
```

#### 13.11.4 Dynamic Rendering Functions

`human_review.js` must include:

```javascript
function renderFieldEditor(fieldDefinition, value) { ... }
function renderScalarField(fieldDefinition, value) { ... }
function renderEnumField(fieldDefinition, value) { ... }
function renderObjectField(fieldDefinition, value) { ... }
function renderArrayField(fieldDefinition, value) { ... }
function renderObjectArrayGrid(fieldDefinition, rows) { ... }
function collectFieldValue(fieldDefinition) { ... }
function collectStructuredCorrections() { ... }
function validateClientSide(fieldDefinition, value) { ... }
```

Client-side validation is for operator feedback only. Server-side validation is authoritative.

Input rules:

- Default corrected input value should be:
  - existing corrected value if present,
  - otherwise extracted value for editable high-confidence fields,
  - otherwise blank for low-confidence fields if no correction exists.
- Low-confidence rows should use warning/error background tint.
- Required missing values should show validation message.
- If field type is date/number/boolean/enum, render appropriate input where schema provides enough information.
- Do not fall back to all text inputs for object arrays. Object arrays must have an editable grid because invoice line items are a core use case.
- If an unsupported complex field is encountered, render a JSON text area for that field and show a warning.

#### 13.11.5 Difference Preview

The review editor must show a difference preview before completion.

Minimum behavior:

- Highlight changed scalar fields.
- Highlight added/removed array rows.
- Highlight changed cells in object arrays.
- Show original extracted value and corrected value.

The diff logic can be ported from `qa_extracted_data/utils/diff_utils.py`, but must be exposed through FastAPI/Jinja/JS instead of Streamlit.

API option:

```text
POST /api/review/items/{review_item_id}/diff
```

Request:

```json
{
  "corrections": {
    "invoice_total": "12340.00",
    "line_items": [
      {"description": "Widget", "quantity": 2, "amount": 10.0}
    ]
  }
}
```

Response:

```json
{
  "has_changes": true,
  "summary": [
    {"field_key": "invoice_total", "before": "12,340.00", "after": "12340.00"}
  ],
  "detailed_diff": {}
}
```

#### 13.11.6 Save Draft and Complete Behavior

Save draft:

- Saves corrections without completing the review.
- Keeps document status `in_review`.
- Does not resume the pipeline.
- Records an audit event with event type `review_draft_saved`.

Complete:

- Validates corrections against schema.
- Writes corrected values.
- Marks review item `completed`.
- Releases lock.
- Records audit event with event type `review_completed`.
- Updates document status to `review_completed`.
- Triggers resume from the next pipeline task.

API endpoint:

```text
GET  /api/review/items/{review_item_id}
POST /api/review/items/{review_item_id}/draft
POST /api/review/items/{review_item_id}/diff
POST /api/review/items/{review_item_id}/complete
POST /api/review/items/{review_item_id}/release
```

Detail response:

```json
{
  "review_item": {
    "id": "review_123",
    "status": "in_review",
    "queue_name": "invoice_review",
    "reason": "low_confidence",
    "scope": "low_confidence_fields",
    "locked_by": "operator"
  },
  "document": {
    "id": "doc_123",
    "filename": "INV-023.pdf",
    "document_type": "Invoice",
    "preview_url": "/api/documents/doc_123/file/pdf",
    "page_count": 2
  },
  "schema": {
    "name": "invoice_schema.yaml",
    "title": "Invoice Schema",
    "version": "sha256-or-version",
    "fields": []
  },
  "fields": [
    {
      "field_key": "total_amount",
      "field_alias": "Total Amount",
      "label": "Total Amount",
      "type": "number",
      "extracted_value": "12,340.00",
      "corrected_value": null,
      "final_value": "12,340.00",
      "confidence": 0.72,
      "requires_review": true,
      "input_type": "number",
      "required": true,
      "choices": null,
      "validation_errors": []
    }
  ],
  "navigation": {
    "previous_review_item_id": "review_122",
    "next_review_item_id": "review_124"
  }
}
```

Complete request:

```json
{
  "corrections": {
    "invoice_number": "INV-022",
    "total_amount": "12340.00",
    "currency": "SGD"
  }
}
```

Complete response:

```json
{
  "status": "completed",
  "document_id": "doc_123",
  "resume_triggered": true,
  "redirect_url": "/app/review"
}
```

JS file: `human_review.js`.

Functions:

```javascript
loadReviewItem()
renderPdfViewer()
renderDynamicSchemaForm()
collectCorrections()
previewDiff()
saveDraft()
completeReview()
releaseReview()
renderValidationErrors(errors)
```

### 13.12 Schema Editor Page

The current Streamlit app allows users to edit complex schemas. The new app must preserve this capability without using Streamlit.

Template: `schema_editor.html`.

Routes:

```text
GET /app/schemas
GET /app/schemas/{schema_name}
```

API endpoints:

```text
GET  /api/schemas
GET  /api/schemas/{schema_name}
POST /api/schemas
PUT  /api/schemas/{schema_name}
POST /api/schemas/{schema_name}/validate
POST /api/schemas/{schema_name}/duplicate
```

Schema editor UI requirements:

- List existing schema files.
- Create new schema.
- Edit schema metadata:
  - title
  - description
  - version
- Add/edit/delete fields.
- Reorder fields.
- Edit field properties:
  - key
  - label
  - type
  - required
  - help
  - default
  - min/max length
  - min/max numeric value
  - enum choices
- Support object fields:
  - add child field
  - delete child field
  - nested field tree display
- Support array fields:
  - scalar array editor
  - object array item schema editor
- Show live YAML preview.
- Validate schema before saving.
- Prevent invalid field keys.
- Warn when schema changes may affect active review items.

Implementation approach:

- Port schema parsing and validation concepts from:

```text
D:\python_code\qa_extracted_data\utils\schema_loader.py
D:\python_code\qa_extracted_data\utils\schema_editor_view.py
D:\python_code\qa_extracted_data\utils\model_builder.py
```

- Do not port Streamlit UI code directly.
- Reimplement the UI in Jinja + JavaScript.
- Keep schema files as YAML on disk for now.
- Store schema file name/hash on each review item so older reviews remain traceable.

Schema editor JS file:

```text
web/static/js/schema_editor.js
```

Required functions:

```javascript
loadSchemas()
loadSchema(schemaName)
renderSchemaFieldTree(schema)
renderFieldProperties(fieldPath)
addField(parentPath)
deleteField(fieldPath)
moveField(fieldPath, direction)
updateFieldProperty(fieldPath, propertyName, value)
renderYamlPreview(schema)
validateSchema(schema)
saveSchema(schema)
```

### 13.13 Review and Schema UI Acceptance Criteria

The review and schema UI are acceptable when:

- Operator can view the source PDF next to extracted values.
- Operator can zoom and navigate PDF pages.
- Fields render dynamically from schema, not hardcoded templates.
- Scalar, object, scalar array, and object array fields are editable.
- Invoice line items can be corrected in an editable table.
- Validation errors are shown before completion.
- Diff preview shows what changed.
- Save draft does not resume the pipeline.
- Mark complete saves corrections and resumes the pipeline.
- Schema editor can create/edit/save complex schemas without Streamlit.

### 13.14 Reports Page

Template: `reports.html`.

First milestone can be minimal, but must fit the sidebar route.

Show:

- Total batches.
- Total documents.
- Documents completed.
- Documents failed.
- Documents reviewed.
- Average processing time if available.

API endpoint:

```text
GET /api/reports/summary
```

### 13.15 Settings Page

Template: `settings.html`.

First milestone is read-only.

Show:

- Watch folder path.
- Processing folder path.
- SQLite database path.
- Review lock timeout.
- Configured pipeline steps.
- LlamaCloud Split enabled/disabled.
- Review gate thresholds.

API endpoint:

```text
GET /api/settings
```

Do not expose secrets such as API keys.

The settings page should link to `/app/schemas` for schema management.
The settings page should link to `/app/settings/validation` for configuration validation.
For admins, the settings page should also link to `/app/admin`, `/app/admin/pipeline`, `/app/admin/tasks`, `/app/admin/review-gate`, `/app/admin/split`, `/app/admin/audit`, and `/app/admin/dry-run`.

#### 13.15.1 Configuration Validation Page

Template: `config_validation.html`.

Route:

```text
GET /app/settings/validation
```

This page brings existing YAML/config validation tools into the admin UI. It must not replace the CLI validator; it must call shared validation service logic also used by CLI wrappers.

Required visual sections:

1. Validation controls.
2. Summary cards.
3. Findings table.
4. Raw JSON details panel.

Validation controls:

- Validate current runtime config.
- Validate uploaded/pasted config draft.
- Toggle strict mode.
- Toggle import checks.
- Run validation.

Summary cards:

- Errors.
- Warnings.
- Info.
- Runtime readiness.

Findings table columns:

```text
Level
Code
Path
Message
Suggestion
Location
```

API endpoints:

```text
GET  /api/config/validation
POST /api/config/validation
POST /api/pipeline/validate
GET  /api/admin/schemas/validation
POST /api/admin/schemas/validate-all
```

`GET /api/config/validation` validates the active config file.

`POST /api/config/validation` validates provided YAML content without saving it.

Request:

```json
{
  "yaml_text": "web:\n  host: 127.0.0.1\n",
  "strict": false,
  "import_checks": true
}
```

Response:

```json
{
  "status": "failed",
  "summary": {
    "errors": 1,
    "warnings": 2,
    "info": 0
  },
  "findings": [
    {
      "level": "error",
      "code": "file-not-found",
      "path": "tasks.review_gate.params.schema_file",
      "message": "Referenced schema file does not exist.",
      "suggestion": "Create the schema in Schema Editor or update schema_file.",
      "location": {"line": 22, "column": 9}
    }
  ]
}
```

Validation UI rules:

- Show errors with red badges.
- Show warnings with yellow badges.
- Show info with neutral badges.
- Do not auto-fix config.
- Do not expose secrets from the config.
- If rendering YAML text, redact keys such as `api_key`, `password`, `secret_key`, and `token`.

`config_validation.js` functions:

```javascript
loadActiveValidation()
validateAllSchemas()
runDraftValidation()
renderValidationSummary(summary)
renderFindings(findings)
toggleRawJson()
```

### 13.16 Admin Configuration Pages

Admin pages must use the same compact sidebar/header shell as the operator UI, but they are not constrained to match the static operator prototype page-for-page.

#### 13.16.1 Admin Dashboard

Template: `admin_dashboard.html`.

Route:

```text
GET /app/admin
```

Required sections:

- Configuration health summary.
- Schema validation summary.
- Pipeline draft/published status.
- Review-gate threshold summary.
- Split adapter status.
- Recent admin audit events.

API endpoint:

```text
GET /api/admin/summary
```

#### 13.16.2 Pipeline Configuration Page

Template: `pipeline_config.html`.

Route:

```text
GET /app/admin/pipeline
```

Required sections:

- Active pipeline step list.
- Draft pipeline step list.
- Task parameter form.
- Task add/reorder/enable/disable controls.
- YAML preview.
- Active-vs-draft diff.
- Validation findings.
- Publish button disabled when blocking findings exist.

API endpoints:

```text
GET  /api/admin/pipeline
PUT  /api/admin/pipeline/draft
POST /api/admin/pipeline/diff
POST /api/admin/pipeline/validate
POST /api/admin/pipeline/publish
```

Draft model:

```json
{
  "steps": [
    {
      "key": "review_gate",
      "label": "Review Gate",
      "module": "standard_step.review.review_gate",
      "class": "ReviewGateTask",
      "enabled": true,
      "params": {
        "confidence_threshold": 0.9,
        "review_scope": "low_confidence_fields"
      }
    }
  ]
}
```

`pipeline_config.js` functions:

```javascript
loadPipelineConfig()
renderPipelineSteps()
renderTaskParameterForm(stepKey)
addTaskFromCatalog(taskKey)
moveTask(stepKey, direction)
toggleTask(stepKey, enabled)
renderYamlPreview()
renderPipelineDiff()
validateDraftPipeline()
publishDraftPipeline()
```

#### 13.16.3 Task Catalog Page

Template: `task_catalog.html`.

Route:

```text
GET /app/admin/tasks
```

Required sections:

- Available task table.
- Import status.
- Module/class path.
- Required and optional parameters.
- Expected inputs/outputs when discoverable.
- Add-to-pipeline action.

API endpoint:

```text
GET /api/admin/task-catalog
```

#### 13.16.4 Review Gate Rules Page

Template: `review_gate_rules.html`.

Route:

```text
GET /app/admin/review-gate
```

Required sections:

- Global confidence threshold.
- Per-document-type thresholds.
- Per-field threshold overrides.
- Review scope mode.
- Always-review rules.
- Split-confidence review rules.
- Business-rule flag triggers.
- Review lock timeout.

API endpoints:

```text
GET /api/admin/review-gate-rules
PUT /api/admin/review-gate-rules
```

#### 13.16.5 Split Settings Page

Template: `split_settings.html`.

Route:

```text
GET /app/admin/split
```

Required sections:

- Enable/disable LlamaCloud Split.
- Split categories.
- Split confidence thresholds.
- Adapter status.
- Connection test result.
- Secret redaction.

API endpoints:

```text
GET  /api/admin/split-settings
PUT  /api/admin/split-settings
POST /api/admin/split-settings/test-connection
```

#### 13.16.6 Admin Audit Page

Template: `admin_audit.html`.

Route:

```text
GET /app/admin/audit
```

Required sections:

- Filter by event type.
- Filter by user.
- Filter by date range.
- Event table.
- Before/after JSON details for configuration changes.

API endpoint:

```text
GET /api/admin/audit
```

#### 13.16.7 Pipeline Dry Run Page

Template: `pipeline_dry_run.html`.

Route:

```text
GET /app/admin/dry-run
```

Required sections:

- Sample PDF upload or document selector.
- Pipeline draft selector.
- Run dry-run button.
- Split decision summary.
- Extraction summary.
- Review-gate decision summary.
- Validation findings.

API endpoint:

```text
POST /api/admin/dry-run
```

Dry run rules:

- Do not write final exports.
- Use mocked external calls in tests.
- Store the dry-run result as an admin audit event.
- Redact secrets in request/response details.

### 13.17 UI State and Polling Rules

- Upload page does not poll.
- Processing page polls active batches every 3 seconds.
- Split results page can be static after load, with manual refresh.
- Extraction results page can be static after load, with manual refresh.
- Review queue page refreshes on filter/search changes and after claim/release.
- Human review page must not auto-refresh while editing.
- Admin pipeline page should not auto-refresh while a draft has unsaved edits.
- Admin dashboard may refresh manually.

### 13.18 Mobile and Desktop Requirements

Desktop and laptop are the primary targets.

Minimum responsive behavior:

- Sidebar remains fixed width on desktop.
- Tables remain horizontally scrollable when needed.
- Human review page may stack preview above fields below 900px width.
- Text must not overflow buttons, badges, or table cells.

### 13.19 UI Acceptance Checklist

The UI refactor is acceptable when:

- `/app/upload` visually resembles prototype `index.html`.
- `/app/processing` visually resembles prototype `processing.html`.
- `/app/batches/{batch_id}/split-results` visually resembles prototype `split-results.html`.
- `/app/documents/{document_id}/extraction` visually resembles prototype `extraction-results.html`.
- `/app/review` visually resembles prototype `review-queue.html`.
- `/app/review/{review_item_id}` visually resembles prototype `human-review.html`.
- Operator users see only operator navigation and cannot access admin routes.
- Admin users see operator navigation plus an admin navigation group.
- Admin can validate all schemas.
- Admin can edit schemas and validate before save.
- Admin can create a pipeline draft, validate it, view a diff, and publish it.
- Admin can configure `ReviewGateTask` thresholds and scope from the UI.
- Admin can inspect task catalog import/configuration errors.
- The left sidebar and top header are consistent on every app page.
- Upload creates a batch and redirects to processing overview.
- Processing overview updates without full page reload.
- Review queue can claim and open an item.
- Human review can save corrections and mark review complete.
- Review completion resumes the document pipeline.

## 14. Migration Strategy

### Phase 1

- Add SQLite schema and repositories.
- Initialize database at app startup.
- Add tests for database creation.

### Phase 2

- Update ingestion to create batch and document records.
- Preserve existing watch-folder monitoring behavior while routing discovered PDFs through the same SQLite-backed batch/document creation path as uploads.
- Keep old status files working.
- Add API endpoints backed by SQLite.

### Phase 3

- Add task run tracking to workflow execution.
- Save extraction results to SQLite.

### Phase 4

- Implement `ReviewGateTask`.
- Implement review API.
- Implement resume manager.

### Phase 5

- Audit remaining workflow-state dependencies in orchestration and all `standard_step/*` tasks before UI pages depend on those paths.
- Implement split adapter and split task.
- Add fan-out child document execution.
- Add fan-in finalization so root/source and batch status are derived from leaf completion before UI pages depend on processing status.
- Build validation services for config, pipeline, schemas, review-gate params, and split params.

### Phase 6

- Build role-aware shared UI shell.
- Build upload and processing UI.
- Build schema APIs and schema editor before human review UI consumes schema-driven field definitions.
- Build extraction results API/page before review UI links to persisted fields.
- Build review queue and human review UI.
- Port remaining validation, diff, and audit UI behavior from `qa_extracted_data`.

### Phase 7

- Build Task Catalog service/API before Pipeline Configuration.
- Build Pipeline Configuration with draft, diff, validate, and publish.
- Build Review Gate Rules and Split Settings.
- Build Validation Center after validation services and admin configuration APIs exist.
- Build admin dashboard, audit, settings, and pipeline dry-run.

### Phase 8

- Build reports and operator settings pages.
- Complete the workflow-state audit checklist and verify every configured workflow step, including all `standard_step/*` tasks, has classified filesystem writes as workflow state, business output, source input artifact, split working artifact, archive artifact, reference/config data, or export.
- Replace `StatusManager` text-file writes in orchestration and standard steps with SQLite-backed task-run events, document state updates, audit events, extraction/review records, or document-file registrations.
- Replace status-file API reads with SQLite batch/document/task-run queries.
- Ensure representative workflows can run with text status-file creation disabled.
- Deprecate or remove status-file API reads.

## 15. Testing Plan

Use:

```powershell
C:\Python313\python.exe -m pytest -v
```

Add tests:

```text
test/db/test_migrations.py
test/db/test_repositories.py
test/services/test_batch_service.py
test/services/test_document_service.py
test/services/test_workflow_state_service.py
test/services/test_review_service.py
test/services/test_fan_in_service.py
test/services/test_schema_service.py
test/services/test_config_validation_service.py
test/services/test_pipeline_config_service.py
test/services/test_task_catalog_service.py
test/services/test_admin_settings_service.py
test/services/test_resume_manager.py
test/standard_step/review/test_review_gate.py
test/standard_step/split/test_llamacloud_split_adapter.py
test/standard_step/split/test_llamacloud_split_task.py
test/integration/test_sqlite_ingestion.py
test/integration/test_llamacloud_split_fanout.py
test/integration/test_review_pause_resume.py
test/integration/test_split_fan_in_finalization.py
test/integration/test_config_validation_api.py
test/integration/test_new_ui_routes.py
test/integration/test_admin_routes.py
test/integration/test_admin_pipeline_config_api.py
test/integration/test_pipeline_dry_run.py
test/integration/test_sqlite_only_workflow_state.py
```

Test rules:

- Mock LlamaCloud calls.
- Use temp directories and temp SQLite files.
- Cover both web-upload and watch-folder ingestion in SQLite ingestion tests.
- Do not depend on real API keys.
- Verify no duplicate review item on repeated `ReviewGateTask` execution.
- Verify corrected values are used by downstream storage.
- Verify split fan-in marks the root and batch complete only after all leaf documents are terminal.
- Verify fan-in is idempotent and does not delete parent/root state or registered artifacts.
- Verify operators cannot access admin routes or APIs.
- Verify admin pipeline publish records a config version and audit event.
- Verify representative configured workflows do not require intermediate text status files for workflow state.
- Verify generated PDFs, split working PDFs, archives, JSON/CSV exports, reference CSVs, and config files are registered or documented as artifacts rather than used as workflow state.

## 16. Implementation Guardrails

- Keep existing tests passing as much as possible during each phase.
- Do not delete file-based status code until SQLite-backed UI/API is working.
- Do not consider the migration complete while workflow orchestration or `standard_step/*` tasks require `StatusManager` text files for state, progress, pause/resume, recovery, or UI/API visibility.
- Standard task filesystem outputs may remain where they are business outputs, split working PDFs, archives, references, inputs, or exports, but those files must be registered in SQLite or documented as non-state artifacts when relevant.
- Do not remove or disable watch-folder ingestion; preserve `modules/watch_folder_monitor.py` behavior and adapt it to the shared ingestion/state services.
- Do not put raw SQL in FastAPI route handlers.
- Do not put UI-specific logic in pipeline tasks.
- Do not use Prefect's own UI pause as the primary human review mechanism.
- Implement app-level pause/resume using SQLite document status.
- Use `apply_patch` for code edits.
- Follow Windows path handling rules already used by the project.

## 17. First Implementation Checklist

Start with these tasks:

- [ ] Add `modules/db/schema.sql`.
- [ ] Add `modules/db/connection.py`.
- [ ] Add `modules/db/migrations.py`.
- [ ] Add repository classes.
- [ ] Initialize database in app startup.
- [ ] Add tests for schema creation.
- [ ] Update web upload ingestion to create a batch and root document.
- [ ] Update watch folder ingestion to create a batch and root document.
- [ ] Add `GET /api/batches` and `GET /api/documents/{document_id}`.
- [ ] Add task run tracking around existing pipeline tasks.
- [ ] Persist extraction result and fields from `ExtractPdfV2Task`.
- [ ] Implement and test `ReviewGateTask` pass-through.
- [ ] Implement and test `ReviewGateTask` pause.
- [ ] Implement and test split fan-in finalization.
- [ ] Add role-aware operator/admin route guards.
- [ ] Add admin schema validation-all endpoint.
- [ ] Add pipeline draft/validate/diff/publish endpoints.
## UI Framework and Prototype Alignment

Use DaisyUI as the primary CSS component framework for the refactored FastAPI/Jinja UI.

The layout, navigation model, and information architecture flow must mirror `refactor UI prototype/`. Treat the prototype as the source for page structure, sidebar/topbar behavior, screen-to-screen flow, density, and operator/admin navigation grouping, not merely as loose styling inspiration.

Implementation guidance:

- Prefer DaisyUI components for navigation, menus, buttons, forms, tables, tabs, badges, alerts, modals, drawers, cards, and status indicators.
- Use Tailwind utility classes where needed to compose DaisyUI components and match the prototype spacing, hierarchy, and responsive behavior.
- Keep custom CSS limited to application-specific layout behavior such as PDF/review split panes, dense processing tables, scroll regions, responsive review workspaces, and prototype-specific refinements that DaisyUI does not cover cleanly.
- Do not introduce Streamlit or a separate frontend application for the first UI implementation.
- Keep each UI route focused on the actual usable operator/admin workflow shown in the prototype, not a marketing or explanatory landing page.
