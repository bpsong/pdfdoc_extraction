# Trace execution through the code

| Item | Value |
| --- | --- |
| Audience | Developers and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Representative request traces

Use these paths as navigation guides when debugging. Names may gain helper
layers, but the ownership boundaries should remain stable.

```text
POST /api/batches/upload
 → api_router.py
 → UploadReceiver
 → UploadSubmissionService
 → repositories
 → processing_jobs
 → ProcessingWorker
 → FileProcessor
 → WorkflowManager
 → WorkflowLoader
 → configured BaseTask
```

```text
Review completion
 → review UI / api_router.py
 → ReviewService
 → review item and document transaction
 → ResumeManager
 → WorkflowManager
 → next configured task
 → cleanup and FanInService
```

```text
Admin pipeline publication
 → api_router.py
 → PipelineConfigService
 → PipelineValidationService
 → PipelineDefinitionService dependencies
 → immutable pipeline_versions row
```

For a representative upload, the same identifiers connect each persistence
layer: `batch_id` groups the accepted submission, `document_id` identifies an
ingested PDF, `processing_jobs.document_id` queues its execution, and each
`task_runs.id` records a task attempt. A review gate creates a `review_items.id`
for that document and links it to the creating task run. Start from the
document ID when tracing one file; then inspect its task runs, review item, job,
and `document_files` rows. For canonical columns and foreign keys, see
[`modules/db/schema.sql`](../../modules/db/schema.sql).

Useful read-only queries (bind IDs rather than copying customer data):

```sql
SELECT id, status, pipeline_version_id FROM batches WHERE id = ?;
SELECT id, status, parent_document_id, current_task_key
FROM documents WHERE id = ?;
SELECT id, status, task_key, task_index, started_at, ended_at
FROM task_runs WHERE document_id = ? ORDER BY started_at, task_index;
SELECT id, status, reason, created_by_task_run_id
FROM review_items WHERE document_id = ? ORDER BY created_at DESC;
SELECT id, status, attempt_count, lease_expires_at
FROM processing_jobs WHERE document_id = ?;
SELECT id, file_type, file_path FROM document_files WHERE document_id = ?;
```


## Watch-folder ingestion

Start at [WatchFolderCoordinator](../../modules/services/watch_folder_coordinator.py).
It rechecks the binding under the database write lock, validates and claims a
PDF, and creates durable work. Follow the job through
[ProcessingJobService](../../modules/services/processing_job_service.py),
[ProcessingWorker](../../modules/services/processing_worker.py),
[FileProcessor](../../modules/file_processor.py), the manager and loader.
Distinguish a successful producer acknowledgement from completed task execution.

## Manual split continuation

Follow the review API into
[ManualSplitReviewService](../../modules/services/manual_split_service.py)
and [SplitExecutionService](../../modules/services/split_execution_service.py).
The accepted decision commits before HTTP 202 is returned. Background work
applies it at the pinned split task, materialises registered child PDFs and
continues each child after that step. Inspect decision/application phase and
task attempts separately. A saved decision does not prove dispatch completed.

## Debugging checklist

1. Identify whether the failure is in the parent, web process, worker, or
   watch-folder thread.
2. Confirm the active configuration file and resolved database path.
3. Capture the batch, document, review-item, or processing-job ID.
4. Inspect the pinned pipeline/review-schema version and task-run timeline.
5. Check processing-job lease state and worker/runtime heartbeats.
6. For review issues, inspect `review_items`, `review_locks`, and resume state.
7. For output issues, inspect `document_files` and artifact registration logs.
8. Check the role-specific log: `.supervisor`, `.web`, or `.worker`.

Common first checks:

| Symptom | First places to inspect |
| --- | --- |
| Upload accepted but not processing | `processing_jobs`, worker heartbeat, worker log |
| Stuck at review | `review_items`, `review_locks`, paused task run |
| Web/worker startup failure | Role log, `StartupReadinessError`, schema version |
| Watch folder does nothing | Binding lifecycle, `watch_folder_health`, source path |
| Extraction succeeded but storage did not | Task runs, `continued_failures`, artifact records |
| Duplicate upload | `upload_submissions` and idempotency key |
| Missing output file | `document_files` and artifact-service warnings |

Do not repair state by editing SQLite rows or deleting runtime files while the
application is running. Use the supported admin/recovery flow, stop the
application before filesystem repair, and preserve the relevant logs and IDs.
