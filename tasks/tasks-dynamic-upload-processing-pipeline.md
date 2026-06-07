# Dynamic Upload Processing Pipeline Task Plan

## Background

The Upload & Process flow redirects users to the processing overview after a batch is submitted. The current processing overview renders a fixed visual pipeline of `Uploaded`, `Splitting`, `Extracting`, `Review`, and `Output`, even though actual workflow execution is driven by the configurable YAML `pipeline` list and `tasks` definitions.

This is a medium refactor because the visible pipeline should become data-driven from configured workflow steps, while progress and per-document state must remain accurate across uploaded batches, admin pipeline edits, split fan-out, review pauses, and custom task classes.

## Goals

- Render processing stages from the configured YAML pipeline instead of hard-coded frontend stages.
- Preserve the exact pipeline shape a batch entered at upload time, even if an admin publishes a new pipeline later.
- Derive each visual step state from SQLite `task_runs`, `documents.current_task_key`, and document status.
- Keep the processing page usable for short, long, and custom pipelines.
- Add focused tests around snapshotting, API payload shape, state aggregation, and frontend rendering helpers.

## Non-Goals

- Do not redesign the admin pipeline editor.
- Do not change workflow execution order or task execution semantics.
- Do not expose secret task parameters to non-admin UI APIs.
- Do not remove legacy status compatibility endpoints as part of this change.
- Do not add graph/branch execution support beyond the current ordered pipeline and existing split fan-out behavior.

## Relevant Files

- `web/templates/processing_overview.html` - Current hard-coded visual pipeline and fixed queue table scaffold.
- `web/static/js/processing_overview.js` - Current frontend polling, static stage inference, row rendering, and progress rendering.
- `web/static/css/app.css` - Pipeline step, connector, table, and responsive visual styles.
- `modules/api_router.py` - API routes for batch upload, batch documents, task runs, and future processing-state endpoint.
- `modules/services/batch_service.py` - Batch/document listing and coarse progress helpers.
- `modules/services/pipeline_config_service.py` - Existing YAML-backed active/draft pipeline model conversion.
- `modules/services/workflow_state_service.py` - Runtime task-run start, completion, pause, failure, and current document pointer updates.
- `modules/db/repositories.py` - Batch, document, task-run, and config-version repositories.
- `modules/db/schema.sql` - Existing SQLite schema; only change if a durable snapshot cannot fit cleanly in existing batch metadata.
- `modules/workflow_loader.py` - Confirms runtime task keys and indexes are recorded from configured pipeline steps.
- `test/services/test_batch_service.py` or `test/services/test_processing_state_service.py` - Unit tests for pipeline snapshot and processing state aggregation.
- `test/integration/test_batch_upload_api.py` - Upload API integration tests for stored pipeline snapshot.
- `test/integration/test_new_ui_routes.py` - Authenticated page smoke tests.
- `test/integration/test_dynamic_processing_pipeline_api.py` - New integration coverage for processing-state API payloads.

## Design Decisions

- Store a pipeline snapshot at batch creation time in batch metadata unless a schema migration is clearly justified.
- Use the active YAML-backed pipeline model as the snapshot source.
- Expose a non-admin processing-state API for upload/processing pages; do not make user-facing processing pages call `/api/admin/pipeline`.
- Treat `Uploaded` or `Queued` as a synthetic ingestion stage outside the YAML workflow.
- Treat all configured enabled pipeline tasks as dynamic stages after ingestion.
- Use `task_runs.task_key` and `documents.current_task_key` as primary status inputs.
- Avoid fixed table columns for `Splitting`, `Extracting`, `Review`, and `Output`; prefer `Current Step` and `Last Completed` for arbitrary pipelines.

## Tasks

- [x] 1.0 Define the runtime pipeline snapshot contract
  - Acceptance: A documented payload shape exists for a batch-level pipeline snapshot.
  - Acceptance: Snapshot fields include `key`, `label`, `module`, `class`, `category`, `position`, and `on_error`.
  - Acceptance: Snapshot explicitly excludes secret or full task `params` values from user-facing APIs.
  - Acceptance: There is a fallback behavior for historical batches without snapshots.
  - [x] 1.1 Add a small internal helper/service design for converting the active pipeline model into a safe snapshot.
  - [x] 1.2 Define task category classification rules, reusing the admin pipeline editor categories where possible.
  - [x] 1.3 Decide whether batch metadata is sufficient or whether `schema.sql` needs a dedicated snapshot column.

- [x] 2.0 Snapshot active pipeline during batch creation
  - Acceptance: New uploaded batches persist the pipeline snapshot they entered.
  - Acceptance: The snapshot remains stable if `/api/admin/pipeline/publish` later changes the active pipeline.
  - Acceptance: Existing upload behavior and background processing continue unchanged.
  - [x] 2.1 Capture the active pipeline model in the batch upload path before documents are queued.
  - [x] 2.2 Persist snapshot metadata with batch creation.
  - [x] 2.3 Add unit or integration tests proving snapshot persistence.
  - [x] 2.4 Add a regression test proving later active pipeline changes do not alter an existing batch snapshot.

- [x] 3.0 Add a processing-state aggregation service
  - Acceptance: Service returns batch, pipeline snapshot, documents, task runs, and aggregate step states.
  - Acceptance: Per-step states support `pending`, `running`, `completed`, `paused`, `failed`, and `skipped`.
  - Acceptance: Aggregation handles root documents, split child documents, review pauses, and failed task runs.
  - Acceptance: Progress is derived from configured steps instead of hard-coded status percentages where task-run data is available.
  - [x] 3.1 Create a service that loads batch documents and task runs in one coherent payload.
  - [x] 3.2 Implement per-document step-state derivation from task runs and `current_task_key`.
  - [x] 3.3 Implement aggregate step-state derivation across visible documents.
  - [x] 3.4 Define split fan-out handling: parent steps before fan-out, child steps after fan-out, and skipped states where not applicable.
  - [x] 3.5 Add unit tests for normal completion, running task, failed task, review pause, and split fan-out cases.

- [x] 4.0 Add non-admin processing-state API endpoints
  - Acceptance: Processing page can load dynamic pipeline state without admin permissions.
  - Acceptance: API payload does not leak secrets or raw full YAML config.
  - Acceptance: Existing `/api/batches`, `/api/batches/{batch_id}`, and `/api/batches/{batch_id}/documents` callers remain compatible.
  - [x] 4.1 Add `GET /api/batches/{batch_id}/processing-state`.
  - [x] 4.2 Consider `GET /api/processing-state` for the active-batches overview, grouping batches by snapshot hash when needed.
  - [x] 4.3 Add 404 and authentication tests.
  - [x] 4.4 Add tests for historical batches without snapshots.

- [x] 5.0 Refactor processing overview frontend rendering
  - Acceptance: Visual pipeline stages are rendered from API `pipeline_snapshot.steps`.
  - Acceptance: The synthetic ingestion step appears before configured YAML steps.
  - Acceptance: The page handles zero documents, active documents, completed documents, failed documents, and paused review documents.
  - Acceptance: Fixed `Splitting`, `Extracting`, `Review`, and `Output` table columns are removed or hidden in favor of dynamic state.
  - [x] 5.1 Replace static HTML step placeholders with an empty dynamic container.
  - [x] 5.2 Replace hard-coded `documentStage` mappings with API-provided step states.
  - [x] 5.3 Render the queue table with `Current Step`, `Last Completed`, `Progress`, and `Action`.
  - [x] 5.4 Preserve useful actions such as Review, Extraction, and Split Results based on document state.
  - [x] 5.5 Keep polling behavior and terminal-state stop logic working.

- [x] 6.0 Improve responsive visual behavior for flexible pipelines
  - Acceptance: Pipelines with 1, 5, 8, and 12 configured steps remain readable.
  - Acceptance: Desktop uses horizontal scrolling or compact stages without layout breakage.
  - Acceptance: Mobile uses a vertical timeline or compact stacked layout.
  - Acceptance: Long labels and task keys do not overlap adjacent stages.
  - [x] 6.1 Update CSS for dynamic stage counts.
  - [x] 6.2 Add compact rendering rules for long pipelines.
  - [x] 6.3 Verify empty, short, and long pipeline layouts manually in browser.

- [x] 7.0 Add regression tests and manual verification
  - Acceptance: All new unit and integration tests pass on Windows using `C:\Python313\python.exe`.
  - Acceptance: Existing batch upload, processing overview route, split results route, review route, and admin pipeline API tests still pass.
  - Acceptance: Manual browser verification confirms dynamic stages reflect a custom YAML pipeline.
  - [x] 7.1 Run focused service/API tests.
  - [x] 7.2 Run existing upload and processing integration tests.
  - [x] 7.3 Run UI route smoke tests.
  - [x] 7.4 Manually verify upload of a PDF redirects to a processing page with configured dynamic stages.
  - [x] 7.5 Manually verify changing pipeline config after upload does not mutate the existing batch's visual pipeline.

## Risk Controls

- Implement backend snapshot and aggregation first, then change frontend rendering.
- Keep existing batch/document endpoints stable and add a new endpoint for richer processing state.
- Avoid changing workflow execution code unless tests prove the state data is insufficient.
- Use snapshot fallback for older batches to avoid breaking existing data.
- Keep per-step progress calculation deterministic and testable; do not infer from display labels.
- Keep category detection cosmetic only; status logic must use task keys and task runs.
- Do not include task params in user-facing processing payloads unless each value is explicitly reviewed for safety.

## Suggested Test Commands

```powershell
C:\Python313\python.exe -m pytest -v test\services\test_processing_state_service.py
C:\Python313\python.exe -m pytest -v test\integration\test_batch_upload_api.py
C:\Python313\python.exe -m pytest -v test\integration\test_dynamic_processing_pipeline_api.py
C:\Python313\python.exe -m pytest -v test\integration\test_new_ui_routes.py
```

## Implementation Notes

- Follow `tasks/process-task-list.mdc`: implement one sub-task at a time, mark it complete, then pause for approval before starting the next sub-task.
- Prefer small helper methods with type hints and Google-style docstrings for snapshot conversion and state aggregation.
- Keep UI logic independent of known built-in task names except for optional display category badges and action links.
- If a schema migration is introduced, include migration tests and backward compatibility tests for databases without the new column.
