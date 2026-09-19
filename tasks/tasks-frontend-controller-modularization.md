# Frontend Controller Modularization Plan

## Objective

Reduce production frontend risk by replacing large page-level vanilla JavaScript
controllers with explicit feature modules, while preserving the current
FastAPI/Jinja multi-page application, native browser runtime, security controls,
and user-visible behavior.

The migration is incremental. Every phase must be independently deployable and
must pass focused automated tests plus an authenticated visual workflow in a
real browser before the next phase begins.

## Architectural rules

- Keep production code under `web/`; do not implement this work in the visual
  editor prototype.
- Use native ES modules. Do not add a production Node.js server or JavaScript
  framework.
- Keep page entry points thin: locate the page root, construct dependencies,
  bind the controller, and start it.
- Put HTTP paths and response/error translation in feature API modules.
- Put browser-independent transformations in model modules.
- Put DOM rendering in view modules.
- Keep controllers responsible for orchestration and event-to-action mapping.
- Preserve CSRF headers, same-origin credentials, authorization, focus
  restoration, unsaved-change guards, accessibility behavior, and secret
  redaction.
- Do not rely only on source-text assertions. Prefer behavior tests and focused
  contracts for extracted pure modules.

## Phase 1 — Pipeline model boundary and ES-module entry

- [x] Add the pipeline feature directory and native module entry.
- [x] Extract cloning, definition/model conversion, step classification,
  housekeeping filtering, and nested parameter-path operations into pure
  modules.
- [x] Retain the existing controller as the page orchestrator and preserve its
  public UI behavior.
- [x] Update the pipeline template to load the native module entry with an asset
  version.
- [x] Add focused tests for the extracted model and parameter-path contracts.
- [x] Run the focused route and frontend regression tests.
- [x] Visually verify the pipeline editor by creating a disposable pipeline,
  adding and editing a task, saving its draft, and modifying an existing
  pipeline without publishing unintended changes.

Exit criterion: model and parameter transformations no longer depend on the DOM
or `window`, and the browser workflow behaves as before.

## Phase 2 — Pipeline transport boundary

- [x] Add a pipeline API client that owns every pipeline-editor endpoint,
  HTTP verb, URL encoding rule, import content type, and error translation.
- [x] Replace direct `fetch` and direct `DocFlow.api*` calls in the controller
  with intent-named API operations.
- [x] Add focused API-client tests and enforce that the controller contains no
  direct network calls.
- [x] Run the focused route, service, and frontend regression tests.
- [x] Visually verify creation and modification flows, including draft save,
  validation, diff, metadata update, and template switching.

Exit criterion: the pipeline controller coordinates operations but owns no HTTP
implementation details.

## Phase 3 — Pipeline summary and validation views

- [x] Extract YAML preview generation and secret redaction into a pure preview
  module.
- [x] Extract active-step, draft-step, task-catalog, and validation rendering
  into a pipeline workspace view.
- [x] Preserve disabled task definitions across save/reload; the Phase 3 visual
  gate found that the legacy reconstruction used only enabled pipeline keys.
- [x] Keep task-property editing in the controller temporarily so the migration
  remains reviewable and independently reversible.
- [x] Add focused tests for preview redaction and view module structure.
- [x] Run the focused route and visual regression tests.
- [x] Visually verify creation and modification flows at desktop and narrow
  viewport sizes, checking step selection, ordering, enable/disable state,
  validation findings, YAML preview, keyboard focus, and unsaved-change state.

Exit criterion: list/summary/validation presentation is isolated from page
orchestration and no secret value can appear in the YAML preview.

## Phase 4 — Pipeline task-property editors

- [x] Extract shared controls and task-specific editors for extraction, split,
  review, rules, storage, archive, and context tasks.
- [x] Define a small editor contract based on selected step, findings, and
  dispatched actions.
- [x] Extract directory/file browsing and CSV metadata behavior.
- [x] Add pure tests per task editor and update browser coverage.
- [x] Visually create and modify pipelines covering every task family, including
  structured extraction fields and file/directory selection.

Exit criterion: the pipeline controller is a thin orchestration layer and no
task-specific HTML generation remains in it.

## Phase 5 — Review-form/schema editor

- [x] Create `schema-editor` model, API, controller, and view modules.
- [x] Extract nested field operations, property coercion, validation, outline,
  search, focus restoration, lifecycle, and import/export behavior.
- [x] Replace brittle source-text assertions with behavior-oriented coverage.
- [x] Visually create a disposable form and add, reorder, edit, validate, and
  remove fields; then modify and save an existing form and confirm lifecycle
  and version information remains correct.

Exit criterion: schema operations are testable without a DOM and the schema
controller contains only orchestration.

## Phase 6 — Human review editor

- [x] Create human-review model, API, controller, and field-view modules.
- [x] Extract nested value paths, correction collection, lock policy,
  source-value visibility, scalar/object/array renderers, diff rendering, PDF
  selection integration, and pane layout.
- [x] Visually claim a synthetic review, edit each supported field family, save
  a draft, preview the diff, exercise PDF highlighting, release/reclaim, and
  complete a disposable review item.

Exit criterion: field rendering and correction logic are independently testable
and lock/completion behavior is unchanged.

## Phase 7 — Remaining page controllers and shared browser services

- [x] Modularize upload, processing overview, reports, failures, and other
  medium-sized controllers where the change provides a clear boundary.
- [x] Consolidate stable shared services such as request handling, status
  presentation, notifications, storage, and polling without creating a broad
  mutable global namespace.
- [x] Visually exercise each affected end-to-end workflow, including upload
  selection/cancellation and processing polling/failure actions.
- [x] Complete isolated browser upload file selection/cancellation and
  failure-action checks; the live administrator session remains read-only QA
  data.

Exit criterion: no production page controller combines transport, model,
rendering, and orchestration responsibilities.

## Phase 8 — Performance and deployment hardening

- [x] Measure parse/evaluation time, interaction latency, request concurrency,
  and DOM update cost before applying optimizations.
- [x] Lazy-load heavy optional surfaces where measurements justify it.
- [x] Prevent overlapping requests and polling; suspend polling for hidden tabs.
- [x] Establish cache-safe module versioning or content-hashed asset mapping.
- [x] Document rollout and rollback procedures for modular frontend releases.
- [x] Run the full test suite and complete a final authenticated browser sweep.

Exit criterion: measured performance is no worse than baseline, cache behavior
is deterministic, and each feature entry can be rolled back independently.

## Visual verification record

Record the date, application URL, tested data, viewport, browser result, console
errors, failed network requests, and screenshot paths for every implemented
phase. Disposable templates must be clearly named and left inactive unless the
test explicitly verifies activation.

### 2026-09-14 — Phases 1–3

- Application: `http://localhost:8000/app/admin/pipeline`, authenticated as an
  administrator in both a dedicated automation browser and the Codex in-app
  browser.
- Phase 1: created inactive `Codex Controller Phase 1 QA 2026-09-14`, added and
  configured an archive task, saved/reloaded the draft, and edited/restored the
  description of `Standard invoice extraction`.
- Phase 2: created inactive `Codex Controller Phase 2 QA 2026-09-14`, configured
  and saved an archive task, ran validation and diff, switched templates, and
  edited/restored existing-pipeline metadata.
- Phase 3: created inactive `Codex Controller Phase 3 QA 2026-09-14`, added two
  task types, reordered and disabled a task, saved/reloaded, inspected validation
  findings and redacted YAML, and temporarily toggled/restored a task on
  `Standard invoice extraction` without saving the temporary edit.
- Responsive check: desktop and 768x900 override; measured document widths were
  753px client and 753px scroll width (no horizontal overflow).
- Browser result: no console errors in the final live sweep. The focused
  Playwright workflows passed. One combined Playwright run observed a transient
  teardown-time 404 console entry; the affected test passed cleanly when rerun.
- Evidence: `qa_artifacts/controller-modularization-phase1-pipeline-created.png`,
  `qa_artifacts/controller-modularization-phase1-existing-pipeline-edited.png`,
  `qa_artifacts/controller-modularization-phase2-pipeline-created.png`, and
  inline Codex-browser desktop/narrow screenshots.
- Finding corrected: disabled tasks disappeared after save/reload because the
  legacy model reconstruction ignored task keys outside the enabled pipeline
  list. The extracted model now preserves those tasks as disabled.
- Follow-up corrected: disabled tasks now retain their interleaved editor order
  through draft save/reload via `editor_order`, and the selected task is restored
  by key after save rather than by a stale array index.
- Deployment correction: the entry, controller, and imported modules share the
  same release query version to prevent mixed cached module generations.

### 2026-09-15 — Phase 4

- Application: `http://localhost:8000/app/admin/pipeline`, authenticated as an
  administrator in the Codex in-app browser at the normal desktop viewport.
- Created inactive `Codex Controller Phase 4 QA 2026-09-15` and saved a draft
  containing split, PDF extraction, GLM-OCR extraction, review, storage, rules,
  archive, and context tasks.
- Opened every task family and confirmed its dedicated controls rendered. Added
  a structured GLM-OCR field, opened its object-property editor, and saved the
  resulting structured definition.
- Opened the directory browser for split output and the file browser for the
  reference CSV. Selected `reference_file/reference_file.csv` and confirmed all
  eight CSV columns were loaded into the editor.
- Modified `Standard invoice extraction`, saved and reloaded the archive
  directory to prove persistence, then restored and saved the original
  `archive_folder` value. Its published v4 remained unchanged throughout.
- Browser result: all relevant controls rendered and remained interactive, the
  saved existing-pipeline change survived reload, and the final browser console
  contained no errors. The focused Playwright pipeline workflows passed.
- Test data status: the Phase 4 QA template remains inactive. The existing
  active template's draft content was restored to match its original task list
  and archive setting.

### 2026-09-15 — Phase 5

- Application: `http://localhost:8000/app/schemas`, authenticated as an
  administrator in the Codex in-app browser at the normal desktop viewport.
- Created inactive `Codex Controller Phase 5 QA 2026-09-15`; added string and
  number fields, edited their keys and labels, reordered them, validated and
  saved the draft, then removed the number field with the confirmation dialog
  and saved the change. The form remains inactive and unpublished.
- Modified the `project_number` field label in the existing inactive
  `FTS Extraction Visual QA` form, saved and reloaded to confirm persistence,
  then restored and saved its original `Project reference` label. Its draft
  advanced to revision 4 while its published version remained v1 and its
  original content hash was restored.
- Browser result: the final native-module asset version loaded, form controls
  remained interactive, the disposable draft validated as valid, and the live
  browser console contained no errors. The focused Playwright form-editor
  workflows passed. No failed requests were observed in the tested actions.
- Evidence: inline Codex-browser screenshots of the disposable editor and its
  saved draft, including the final corrected stable-key header.
- Finding corrected: an encoding artifact in the stable-key separator was
  visible in the live editor; it was fixed and the shared asset version bumped.
- Full-suite note: 1,467 passed and 4 skipped; one unrelated runtime-health
  heartbeat timing assertion failed under suite load and passed when rerun alone.

### 2026-09-16 — Phase 6

- Application: isolated synthetic app at `http://127.0.0.1:64549`, authenticated
  as fixture administrator in the Codex in-app browser at 1280x720. The live
  administrator session was inspected read-only; no live review was changed.
- Claimed a disposable review and edited string, number, boolean, datetime,
  scalar-array, and object-array fields; confirmed the nested city field stayed
  read-only. Added and removed array rows, selected a field's PDF source page,
  previewed corrections, saved the draft, released and reclaimed the lock, and
  completed the review. The History view and completed editor showed accepted
  values read-only, and Extraction Results showed the corrected final values.
- Visually checked the shared PDF viewer in the review, extraction-results, and
  failure-detail pages. All reached PDF-ready state; the review PDF showed its
  field source navigation. Browser console errors: none. No failed requests
  were observed during the tested actions. Evidence: inline Codex-browser
  screenshots of review, extraction results, and failure detail.
- The synthetic application uses a temporary database and documents and was
  stopped after verification. Its temporary directory remained after Windows
  held the SQLite file open during teardown; workspace deletion policy blocked
  manual removal. A fixture-only supplier pattern warning was
  visible before completion; it did not prevent the server-validated flow.

### 2026-09-16 — Phase 7 implementation

- Application: live `http://localhost:8000`, authenticated administrator in a
  separate Codex in-app browser QA tab at the normal desktop viewport.
- Visually checked upload pipeline selection, processing overview and its
  failure-detail link, reports and batch detail, review queue/history,
  extraction results with PDF-ready preview, task catalog and task detail,
  watch-folder list plus unsaved Add/Edit dialogs, admin overview, validation,
  settings, audit log, and split-results empty state. No console errors were
  recorded on inspected pages; screenshots were inspected inline.
- The administrator's Superstore invoice batch using GLM-OCR version 4 showed
  extraction complete, review paused, JSON storage pending, and 62% progress.
  Its state remained unchanged on a later load. No live review or binding was
  modified by QA.
- Codex-browser file chooser did not expose the synthetic upload file to the
  automation API, so automated file selection/cancellation and live failure
  actions still need isolated end-to-end browser verification. Upload API/model
  cancellation and validation contracts passed focused synthetic tests.
- First full-suite run: 1,474 passed, 4 skipped, and two stale classic-script
  URL assertions failed. The assertions were updated for versioned feature
  entries and their focused integration files passed (5 tests). Final
  full-suite rerun: 1,476 passed, 4 skipped. The added watch-folder CSRF test
  was run separately with its feature file (4 passed).

### 2026-09-20 — Phase 7 completion

- Rechecked the authenticated upload page in the Codex in-app browser: six
  published pipeline versions rendered, the file drop target and selection
  summary were present, and processing remained disabled with no file chosen.
- Ran the isolated end-to-end cancellation flow with a synthetic 30-byte PDF.
  The selected file and pipeline remained available after cancellation, the
  cancel control hid, processing became retryable, and the page displayed
  `Transfer stopped. Acceptance is unconfirmed; retry the same files and
  pipeline safely.`
- Ran the isolated processing-failure flow with two failed and one successful
  synthetic document. Only the failed documents appeared in the failure notice
  and each provided an `Open Failure` action. Singular and empty states were
  also exercised by the same test.
- Visual evidence:
  `output/playwright/phase14/09-upload-cancelled.png` and
  `output/playwright/phase16/19-batch-failure-guidance-desktop.png`. Both were
  inspected and were non-blank. Focused result: 2 passed.
- Shared request/CSRF/notification behavior remains in `window.DocFlow`;
  feature-local API adapters own endpoint contracts, while polling and
  transient storage remain page-scoped to avoid a broad mutable global store.
  All Phase 7 checklist items and its exit criterion are complete.
- Intermediate verification: 67 relevant tests passed. An earlier full-suite
  run reported 1,472 passed, 4 skipped, and one unrelated 0.15-second
  runtime-health freshness test failure; that test passed on an isolated rerun.
  The subsequent Phase 8 verification is the authoritative final suite result.

### 2026-09-20 — Phase 8

- Measured an isolated representative upload and processing flow before adding
  further loading optimizations. Upload DOM-ready was 264 ms, load was 272 ms,
  JavaScript execution was 6.2 ms, layout was 4.6 ms, task time was 182.6 ms,
  pipeline selection was 105 ms, decoded static assets were 219,727 bytes over
  9 requests, and the page contained 166 DOM nodes. Processing decoded 223,457
  static bytes and rendered 156 DOM nodes for three rows.
- Existing route-scoped feature entries and the PDF viewer's demand import of
  the 352,645-byte PDF.js module already keep heavy code off unrelated pages.
  The measurements did not justify another lazy-loading layer, so no extra
  interaction boundary or layout shift was introduced.
- Added a visibility-aware polling service. It rejects overlapping runs,
  removes its interval while hidden, refreshes once when visible, and removes
  listeners on teardown. Its deterministic unit contract passed.
- Added `tools.frontend_release_check` to validate 16 independently versioned
  feature graphs and to bump one feature entry plus its local imports together.
  Processing overview now uses release `frontend-hardening-8` throughout.
- Added staged rollout and feature/full-artifact rollback instructions in
  `docs/frontend_deployment.md`.
- Authenticated Codex-browser sweep: upload, completed GLM-OCR processing,
  failures/PDF detail, reports, pipeline editor, and review-form editor all
  rendered successfully with no console errors. No live data was changed.
- Verification: 49 focused tests passed; release validation passed for all 16
  feature graphs; final full suite passed with 1,482 tests and 4 skipped.

## Relevant files

- `tasks/tasks-frontend-controller-modularization.md` — phased implementation,
  verification, and rollout plan.
- `web/templates/pipeline_config.html` — pipeline-editor module entry.
- `web/static/js/pipeline_config.js` — retained pipeline orchestration and
  compatibility entry point alongside the feature-local modules.
- `web/static/js/pipeline-config/index.js` — versioned native-module entry.
- `web/static/js/pipeline-config/model.js` — pure definition/model conversion
  and step classification.
- `web/static/js/pipeline-config/parameters.js` — nested parameter operations.
- `web/static/js/pipeline-config/api.js` — pipeline-editor HTTP boundary.
- `web/static/js/pipeline-config/preview.js` — redacted YAML generation.
- `web/static/js/pipeline-config/workspace-view.js` — summary, list, catalog,
  and validation rendering.
- `web/static/js/pipeline-config/task-editors.js` — shared controls and pure
  task-family property rendering.
- `web/static/js/pipeline-config/resource-browser.js` — directory/file browsing
  and CSV metadata orchestration behind injected UI callbacks.
- `test/visual/test_pipeline_controller_modules.py` — pure module behavior and
  architecture-boundary coverage.
- `test/visual/test_schema_editor_regressions.py` — structural frontend
  regression coverage affected by the module split.
- `test/integration/test_new_ui_routes.py` — production page asset coverage.
- `web/templates/schema_editor.html` — versioned review-form module entry.
- `web/static/js/schema-editor/index.js` — thin schema-editor entry.
- `web/static/js/schema-editor/controller.js` — review-form page orchestration
  and event-to-action mapping, moved from the top-level controller path.
- `web/static/js/schema-editor/model.js` — browser-independent field operations
  and client validation.
- `web/static/js/schema-editor/api.js` — review-form HTTP, CSRF, and import/export
  boundary.
- `web/static/js/schema-editor/view.js` — field rendering, outline/search,
  focus restoration, validation, and lifecycle presentation.
- `test/visual/test_schema_editor_modules.py` — model/API behavior and module
  asset-contract coverage.
- `test/visual/test_ui_performance_assets.py` — module asset regression checks.
- `test/integration/test_versioned_admin_pages.py` — versioned schema-page
  behavior and asset checks.
- `docs/design_architecture.md` — production frontend feature boundaries.
- `web/templates/human_review.html` — versioned human-review module entry.
- `web/static/js/human-review/index.js` — thin review-page entry.
- `web/static/js/human-review/controller.js` — browser event and review-action
  orchestration.
- `web/static/js/human-review/model.js` — schema/value normalization, nested
  paths, edit policy, and correction collection without a browser dependency.
- `web/static/js/human-review/api.js` — review-item request boundary.
- `web/static/js/human-review/field-view.js` — scalar, object, and array field
  controls and source/confidence presentation.
- `web/static/js/human-review/view.js` — workspace, PDF selection, pane, lock,
  and diff presentation.
- `web/static/js/pdf_viewer.js` — ignores expected PDF.js rendering cancellation
  on viewer teardown/page changes.
- `web/templates/extraction_results.html` and `web/templates/failures.html` —
  versioned shared PDF-viewer asset references.
- `test/visual/test_human_review_modules.py` — review model/API/module contracts.
- `test/visual/test_schema_review_visual.py` — synthetic full review lifecycle
  and adjacent PDF visual coverage.
- `test/visual/test_pdf_viewer_regressions.py` — shared viewer regression checks.
- `web/templates/upload_process.html`, `processing_overview.html`,
  `reports.html`, `failures.html`, `review_queue.html`,
  `extraction_results.html`, and `split_results.html` — Phase 7 operator
  feature-module entries.
- `web/templates/admin_dashboard.html`, `admin_audit.html`,
  `config_validation.html`, `settings.html`, `task_catalog.html`, and
  `watch_folders.html` — Phase 7 administrative feature-module entries.
- `web/static/js/upload-process/`, `processing-overview/`, `reports/`,
  `failures/`, `review-queue/`, `extraction-results/`, and `split-results/`
  — feature-local API/view/controller modules; upload also owns validation
  model and cancellable XHR transport.
- `web/static/js/admin-dashboard/`, `admin-audit/`,
  `config-validation/`, `settings/`, `task-catalog/`, and `watch-folders/`
  — administrative API/view/controller modules.
- `test/visual/test_operator_page_modules.py` — Phase 7 upload API/model and
  feature entry contracts.
- `web/static/js/polling.js` — non-overlapping, visibility-aware polling.
- `tools/frontend_release_check.py` — feature release validation and bump tool.
- `test/visual/test_frontend_phase8.py` — polling, release, and performance
  budget contracts.
- `docs/frontend_deployment.md` — rollout and rollback playbook.
- `test/integration/test_new_ui_routes.py`,
  `test/integration/test_upload_pipeline_selection_ui.py`, and
  `test/integration/test_watch_folder_management_api.py` — updated page asset
  route contracts.
- `test/visual/test_admin_label_clarity.py` and
  `test/visual/test_ui_performance_assets.py` — updated frontend source paths.
