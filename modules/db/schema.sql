CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY CHECK (username IN ('admin', 'operator')),
    role TEXT NOT NULL CHECK (role IN ('admin', 'operator')),
    password_hash TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 1 CHECK (token_version > 0),
    created_at TEXT NOT NULL,
    password_updated_at TEXT NOT NULL,
    CHECK (username = role)
);

CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    original_filename TEXT,
    status TEXT NOT NULL,
    pipeline_template_id TEXT,
    pipeline_version_id TEXT,
    pipeline_assignment_source TEXT CHECK (
        pipeline_assignment_source IS NULL OR
        pipeline_assignment_source IN ('upload', 'watch_folder', 'legacy_migration')
    ),
    ingress_binding_id TEXT,
    total_documents INTEGER NOT NULL DEFAULT 0,
    completed_documents INTEGER NOT NULL DEFAULT 0,
    failed_documents INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(pipeline_version_id, pipeline_template_id)
        REFERENCES pipeline_versions(id, template_id),
    FOREIGN KEY(ingress_binding_id) REFERENCES watch_folder_bindings(id)
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
    pipeline_template_id TEXT,
    pipeline_version_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(batch_id) REFERENCES batches(id),
    FOREIGN KEY(parent_document_id) REFERENCES documents(id),
    FOREIGN KEY(pipeline_version_id, pipeline_template_id)
        REFERENCES pipeline_versions(id, template_id)
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
    pipeline_version_id TEXT,
    FOREIGN KEY(batch_id) REFERENCES batches(id),
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(pipeline_version_id) REFERENCES pipeline_versions(id)
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
    review_schema_version_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(batch_id) REFERENCES batches(id),
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(created_by_task_run_id) REFERENCES task_runs(id),
    FOREIGN KEY(review_schema_version_id) REFERENCES review_schema_versions(id)
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

CREATE TABLE IF NOT EXISTS review_schema_templates (
    id TEXT PRIMARY KEY,
    schema_key TEXT NOT NULL COLLATE NOCASE UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('active', 'inactive', 'archived')),
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS review_schema_versions (
    id TEXT PRIMARY KEY,
    schema_template_id TEXT NOT NULL,
    version_number INTEGER NOT NULL CHECK(version_number > 0),
    format_version INTEGER NOT NULL CHECK(format_version > 0),
    schema_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    validation_summary_json TEXT NOT NULL DEFAULT '{}',
    published_by TEXT,
    published_at TEXT NOT NULL,
    FOREIGN KEY(schema_template_id) REFERENCES review_schema_templates(id),
    UNIQUE(schema_template_id, version_number),
    UNIQUE(id, schema_template_id)
);

CREATE TABLE IF NOT EXISTS review_schema_drafts (
    schema_template_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK(revision > 0),
    base_version_id TEXT,
    schema_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(schema_template_id) REFERENCES review_schema_templates(id),
    FOREIGN KEY(base_version_id, schema_template_id)
        REFERENCES review_schema_versions(id, schema_template_id)
);

CREATE TABLE IF NOT EXISTS pipeline_templates (
    id TEXT PRIMARY KEY,
    template_key TEXT NOT NULL COLLATE NOCASE UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    document_type TEXT,
    operator_instructions TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('active', 'inactive', 'archived')),
    operator_selectable INTEGER NOT NULL DEFAULT 1 CHECK(operator_selectable IN (0, 1)),
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_versions (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    version_number INTEGER NOT NULL CHECK(version_number > 0),
    schema_version INTEGER NOT NULL CHECK(schema_version > 0),
    definition_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    display_snapshot_json TEXT NOT NULL,
    validation_summary_json TEXT NOT NULL DEFAULT '{}',
    published_by TEXT,
    published_at TEXT NOT NULL,
    FOREIGN KEY(template_id) REFERENCES pipeline_templates(id),
    UNIQUE(template_id, version_number),
    UNIQUE(id, template_id)
);

CREATE TABLE IF NOT EXISTS pipeline_drafts (
    template_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK(revision > 0),
    base_version_id TEXT,
    definition_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(template_id) REFERENCES pipeline_templates(id),
    FOREIGN KEY(base_version_id, template_id)
        REFERENCES pipeline_versions(id, template_id)
);

CREATE TABLE IF NOT EXISTS pipeline_version_schema_dependencies (
    pipeline_version_id TEXT NOT NULL,
    task_key TEXT NOT NULL,
    schema_version_id TEXT NOT NULL,
    PRIMARY KEY(pipeline_version_id, task_key),
    FOREIGN KEY(pipeline_version_id) REFERENCES pipeline_versions(id),
    FOREIGN KEY(schema_version_id) REFERENCES review_schema_versions(id)
);

CREATE TABLE IF NOT EXISTS watch_folder_bindings (
    id TEXT PRIMARY KEY,
    folder_path TEXT NOT NULL,
    normalized_path TEXT NOT NULL COLLATE NOCASE UNIQUE,
    pipeline_template_id TEXT NOT NULL,
    pipeline_version_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_version_id, pipeline_template_id)
        REFERENCES pipeline_versions(id, template_id)
);

CREATE INDEX IF NOT EXISTS idx_documents_batch_id ON documents(batch_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_task_runs_document_id ON task_runs(document_id);
CREATE INDEX IF NOT EXISTS idx_review_items_status ON review_items(status);
CREATE INDEX IF NOT EXISTS idx_extracted_fields_document_id ON extracted_fields(document_id);
CREATE INDEX IF NOT EXISTS idx_config_versions_type_status ON config_versions(config_type, status);
CREATE INDEX IF NOT EXISTS idx_review_schema_templates_status ON review_schema_templates(status);
CREATE INDEX IF NOT EXISTS idx_review_schema_versions_template
    ON review_schema_versions(schema_template_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_templates_status ON pipeline_templates(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_versions_template
    ON pipeline_versions(template_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_dependencies_schema
    ON pipeline_version_schema_dependencies(schema_version_id);
CREATE INDEX IF NOT EXISTS idx_watch_folder_bindings_enabled
    ON watch_folder_bindings(enabled, normalized_path);
CREATE INDEX IF NOT EXISTS idx_batches_pipeline_version ON batches(pipeline_version_id);
CREATE INDEX IF NOT EXISTS idx_documents_pipeline_version ON documents(pipeline_version_id);
CREATE INDEX IF NOT EXISTS idx_task_runs_pipeline_version ON task_runs(pipeline_version_id);
CREATE INDEX IF NOT EXISTS idx_review_items_schema_version ON review_items(review_schema_version_id);

CREATE TRIGGER IF NOT EXISTS trg_review_schema_versions_immutable_update
BEFORE UPDATE ON review_schema_versions
BEGIN
    SELECT RAISE(ABORT, 'published review schema versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_review_schema_versions_immutable_delete
BEFORE DELETE ON review_schema_versions
BEGIN
    SELECT RAISE(ABORT, 'published review schema versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_pipeline_versions_immutable_update
BEFORE UPDATE ON pipeline_versions
BEGIN
    SELECT RAISE(ABORT, 'published pipeline versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_pipeline_versions_immutable_delete
BEFORE DELETE ON pipeline_versions
BEGIN
    SELECT RAISE(ABORT, 'published pipeline versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_pipeline_dependencies_immutable_update
BEFORE UPDATE ON pipeline_version_schema_dependencies
BEGIN
    SELECT RAISE(ABORT, 'published pipeline dependencies are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_pipeline_dependencies_immutable_delete
BEFORE DELETE ON pipeline_version_schema_dependencies
BEGIN
    SELECT RAISE(ABORT, 'published pipeline dependencies are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_review_schema_key_immutable
BEFORE UPDATE OF schema_key ON review_schema_templates
WHEN NEW.schema_key IS NOT OLD.schema_key AND EXISTS (
    SELECT 1 FROM review_schema_versions
    WHERE schema_template_id = OLD.id
)
BEGIN
    SELECT RAISE(ABORT, 'published review schema key is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_pipeline_template_key_immutable
BEFORE UPDATE OF template_key ON pipeline_templates
WHEN NEW.template_key IS NOT OLD.template_key AND EXISTS (
    SELECT 1 FROM pipeline_versions
    WHERE template_id = OLD.id
)
BEGIN
    SELECT RAISE(ABORT, 'published pipeline template key is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_batch_pipeline_assignment_immutable
BEFORE UPDATE OF pipeline_template_id, pipeline_version_id ON batches
WHEN OLD.pipeline_version_id IS NOT NULL AND (
    NEW.pipeline_version_id IS NOT OLD.pipeline_version_id OR
    NEW.pipeline_template_id IS NOT OLD.pipeline_template_id
)
BEGIN
    SELECT RAISE(ABORT, 'batch pipeline assignment is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_document_pipeline_assignment_immutable
BEFORE UPDATE OF pipeline_template_id, pipeline_version_id ON documents
WHEN OLD.pipeline_version_id IS NOT NULL AND (
    NEW.pipeline_version_id IS NOT OLD.pipeline_version_id OR
    NEW.pipeline_template_id IS NOT OLD.pipeline_template_id
)
BEGIN
    SELECT RAISE(ABORT, 'document pipeline assignment is immutable');
END;
