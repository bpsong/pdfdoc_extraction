# Standard Step SQLite State Audit

This audit supports task 11.0 in `tasks-prd-refactor-unified-pdfdoc-processing.md`.

## State Boundary

SQLite is the durable workflow-state source. Files may remain when they are source artifacts, split working artifacts, exports, archives, references, configuration, or transient cleanup inputs. Files must not be needed to reconstruct current workflow state, task progress, pause/resume state, review state, or UI/API status.

## Artifact Roles

- `source_original`: original uploaded or watched source PDF for the root document.
- `split_pdf`: locally generated child PDF used as the active file for a split child document.
- `export_pdf`, `export_json`, `export_csv`: final business outputs for leaf documents.
- `source_archive`: archived copy of the original source PDF.
- `reference_data`: configured reference CSVs mutated by rule tasks.
- `cleanup_transient`: temporary processing copies that can be removed by housekeeping.

## Standard Step Inventory

| Module | File Behavior | Classification | SQLite/Service Requirement |
| --- | --- | --- | --- |
| `standard_step.extraction.extract_pdf` | Calls LlamaCloud Extract and writes extracted data to context. | Workflow/business data | Keep context compatibility; persist result/fields through `ExtractionRepository` when `document_id` exists. |
| `standard_step.extraction.extract_pdf_v2` | Calls LlamaCloud Extract v2 and persists normalized extraction. | Workflow/business data | Already writes extraction result/fields for SQLite contexts. Continue using document-specific leaf state. |
| `standard_step.rules.update_reference` | Reads and atomically writes configured CSV plus optional `.backup`. | Reference data mutation | Run only for leaf documents after split. Persist selected/updated row counts in task-run output and audit metadata. Serialize same-file writes if child workflows run concurrently. |
| `standard_step.storage.store_metadata_as_json` | Writes JSON output files. | Export/business output | Register generated file as `export_json` or document output metadata; do not depend on status text. |
| `standard_step.storage.store_metadata_as_json_v2` | Writes JSON output files from normalized data. | Export/business output | Register generated file as `export_json` or document output metadata; operate on leaf document context. |
| `standard_step.storage.store_metadata_as_csv` | Writes CSV output files. | Export/business output | Register generated file as `export_csv`; operate on leaf document context. |
| `standard_step.storage.store_file_to_localdrive` | Copies current PDF to configured output directory. | Export/business output | Register generated file as `export_pdf`; after split it copies the leaf child PDF, not the root bundle. |
| `standard_step.archiver.archive_pdf` | Copies current PDF to configured archive directory. | Archive artifact | Use `source_archive` for root/source archival. If used after split for child PDFs, record a distinct export/archive role and avoid treating child PDFs as new originals. |
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

## Migration Checklist

- [x] Add explicit artifact-role vocabulary to PRD/design/task docs.
- [x] Implement split fan-out so parent/root workflows stop after successful split.
- [x] Start child workflows from the task after split.
- [x] Preserve registered split PDFs from housekeeping cleanup.
- [x] Ensure `update_reference` is executed only in leaf workflows after fan-out.
- [ ] Implement split fan-in so parent/root and batch aggregate status is leaf-derived and finalized after all leaf documents are terminal.
- [ ] Replace remaining `StatusManager` text writes in standard steps with SQLite task-run/audit/file records.
- [ ] Register JSON/CSV/PDF outputs from storage/archive tasks in `document_files`.
- [ ] Add SQLite-only integration coverage for extraction, `update_reference`, storage, archiver, and housekeeping.
- [ ] Remove new UI/API dependency on `/api/files` and `/api/status/{file_id}` text status files.
