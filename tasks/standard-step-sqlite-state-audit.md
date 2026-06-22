# Standard Step SQLite State Audit

This audit supports task 11.0 and task 26.0 in `tasks-prd-refactor-unified-pdfdoc-processing.md`.

## State Boundary

SQLite is the durable workflow-state source. Files may remain when they are source artifacts, split working artifacts, exports, archives, references, configuration, or transient cleanup inputs. Files must not be needed to reconstruct current workflow state, task progress, pause/resume state, review state, or UI/API status.

Post-cleanup status on 2026-06-04:

- Configured workflow lifecycle state is recorded in `task_runs`, `documents`, and fan-in aggregate state.
- Standard steps no longer call `StatusManager` for text status files.
- Storage/archive steps register generated document artifacts in `document_files`.
- Legacy `/api/files` and `/api/status/{file_id}` read SQLite document/task-run state.
- Task authoring guidance now directs new tasks to SQLite task-run state, audit services for business/admin actions, and explicit artifact registration.
- Maintained runtime docs describe SQLite as the primary workflow-state source and treat text status files only as legacy diagnostics/compatibility.

## Artifact Roles

- `source_original`: original uploaded or watched source PDF for the root document.
- `split_pdf`: locally generated child PDF used as the active file for a split child document.
- `export_pdf`, `export_json`, `export_csv`: final business outputs for leaf documents.
- `source_archive`: archived copy of the original source PDF.
- `reference_data`: configured reference CSVs mutated by rule tasks.
- `cleanup_transient`: temporary processing copies that can be removed by housekeeping.

## Final Filesystem Boundary

Remaining filesystem writes are allowed only for durable business artifacts, configured reference/config/schema files, source/working files, archives, exports, and transient cleanup inputs. No text status file is required to reconstruct:

- document status
- task progress
- task failure details
- extraction/review state
- pause/resume state
- split parent/child lineage
- UI/API processing status

If legacy text status files exist from earlier runs, they are diagnostics only. They should not be used by new UI paths or new task implementations.

## Standard Step Inventory

| Module | File Behavior | Classification | SQLite/Service Requirement |
| --- | --- | --- | --- |
| `standard_step.extraction.extract_pdf` | Calls LlamaCloud Extract and writes extracted data to context. | Workflow/business data | Keep context compatibility; persist result/fields through `ExtractionRepository` when `document_id` exists. |
| `standard_step.extraction.extract_pdf_v2` | Calls LlamaCloud Extract v2 and persists normalized extraction. | Workflow/business data | Writes extraction result/fields for SQLite contexts. Continue using document-specific leaf state. |
| `standard_step.rules.update_reference` | Reads and atomically writes configured CSV plus optional `.backup`. | Reference data mutation | Run only for leaf documents after split. Persist selected/updated row counts in task-run output. Serialize same-file writes if child workflows run concurrently. |
| `standard_step.storage.store_metadata_as_json` | Writes JSON output files. | Export/business output | Registers generated file as `export_json`; does not depend on status text. |
| `standard_step.storage.store_metadata_as_json_v2` | Writes JSON output files from normalized data. | Export/business output | Registers generated file as `export_json`; operates on leaf document context. |
| `standard_step.storage.store_metadata_as_csv` | Writes CSV output files. | Export/business output | Registers generated file as `export_csv`; operates on leaf document context. |
| `standard_step.storage.store_file_to_localdrive` | Copies current PDF to configured output directory. | Export/business output | Registers generated file as `export_pdf`; after split it copies the leaf child PDF, not the root bundle. |
| `standard_step.archiver.archive_pdf` | Copies current PDF to configured archive directory. | Archive artifact | Registers generated file as `source_archive`; this is a durable artifact, not workflow state. |
| `standard_step.housekeeping.cleanup_task` | Deletes active processing file. | Cleanup/transient | Delete only explicit transient paths or unregistered processing copies. Preserve registered `source_original`, `split_pdf`, exports, and archives. |
| `standard_step.review.review_gate` | Creates review items and pauses document state. | Workflow/review state | Already SQLite-backed. Must run on leaf documents unless specifically configured before split. |
| `standard_step.context.*` | Adds or transforms context fields. | Workflow context | Persist only if the data is needed after restart/resume; otherwise keep context-compatible. |
| `standard_step.split.llamacloud_split` | Creates child PDFs and child document records. | Split working artifact and fan-out state | Register `source_original` and `split_pdf`, set parent `split_completed`, stop parent workflow, start child workflows from next task. |
| `modules.services.fan_in_service` | Recomputes root/source and batch aggregate state after leaf workflows finish. | Workflow aggregate state | Count leaf documents only, preserve parent/root lineage state, emit idempotent fan-in audit events, and never delete artifacts. |

## Parent And Leaf State Contract

- Root/source documents keep the original source artifact and split metadata.
- Split child documents store `parent_document_id`, shared `batch_id`, `split_category`, `split_confidence`, `page_start`, `page_end`, and exact `split_pages` in metadata.
- Child workflow contexts include parent/root IDs, source filename/path, split pages, page range, category, confidence, and any explicit immutable inherited context.
- Mutable parent extraction/review/export/task-run state must not be blindly copied to children. It remains reachable through parent references.
- Unsplit root documents are leaf documents and continue through extraction, review, rules, export, and housekeeping normally.
- Fan-in finalization marks parent/root and batch aggregate state after leaf completion. It must preserve parent/root lineage records and registered artifacts; deletion remains explicit housekeeping or retention behavior.

## Implementation Deviations And Compatibility Notes

- `StatusManager` remains in the repository for legacy compatibility tests and status endpoints, but configured workflow steps no longer use it as state transport.
- `/api/files` and `/api/status/{file_id}` remain available as compatibility endpoints. They now read SQLite document, task-run, and artifact state.
- `tasks/prd-design-pdf-processing.md`, `tasks/tasks-prd-redesigned-pdf-processing.md`, `tasks/prd-config-checker.md`, and `tasks/tasks-prd-config-checker.md` are historical planning docs after task 26 cleanup.
- `docs/llamacloud_extract_v2_migration.md` is retained as historical migration context after stable Extract v2 configuration and smoke-check content has been merged into maintained docs.

## Validation Evidence

- Focused SQLite-only workflow coverage: `test/integration/test_sqlite_only_workflow_state.py`.
- Focused API/settings/report coverage: `test/integration/test_batch_upload_api.py`, `test/integration/test_reports_api.py`, and `test/integration/test_settings_api.py`.
- Updated legacy unit tests no longer assert text status side effects for standard steps that now rely on workflow-managed task runs.

## Migration Checklist

- [x] Add explicit artifact-role vocabulary to PRD/design/task docs.
- [x] Implement split fan-out so parent/root workflows stop after successful split.
- [x] Start child workflows from the task after split.
- [x] Preserve registered split PDFs from housekeeping cleanup.
- [x] Ensure `update_reference` is executed only in leaf workflows after fan-out.
- [x] Implement split fan-in so parent/root and batch aggregate status is leaf-derived and finalized after all leaf documents are terminal.
- [x] Replace remaining `StatusManager` text writes in standard steps with SQLite task-run/file records.
- [x] Register JSON/CSV/PDF outputs from storage/archive tasks in `document_files`.
- [x] Add SQLite-only integration coverage for extraction, `update_reference`, storage, archiver, and housekeeping.
- [x] Remove new UI/API dependency on `/api/files` and `/api/status/{file_id}` text status files.
