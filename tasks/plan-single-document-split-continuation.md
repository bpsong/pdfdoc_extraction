# Single-document split continuation implementation plan

Date: 2026-10-03

## Objective and acceptance criteria

When LlamaCloud returns exactly one segment containing every source PDF page
exactly once, continue the original document through the next pipeline task in
the same workflow. Preserve the classification decision without creating a
child record, a split PDF, or a child workflow.

- Match actual page numbers, not only `page_start` and `page_end`. Require the
  page sequence to match the original PDF order; reordered or duplicate pages
  must not silently qualify for the optimization.
- Run existing confidence/category policy and page validation before deciding
  to continue. A single segment does not bypass failure policy.
- Preserve document ID, batch ID, original filename, file path, pipeline version,
  inherited context, and continued failures.
- Persist category, confidence, pages, provider job ID, and an explicit
  `single_document` split outcome. Keep operational document status under the
  normal runner lifecycle; do not use `split_completed` for a root with no children.
- Multiple segments and a single partial/reordered segment retain existing
  child creation and fan-out behavior. Zero segments, disabled splitting, and
  child-document skipping retain their existing behavior.
- Existing persisted split children continue to be reused; no migration or
  flattening of historical parent/child records is planned.

## Relevant files

- `standard_step/split/llamacloud_split.py`: eligibility, persistence, and
  continuation context.
- `modules/db/repositories.py`: focused update for original-document
  classification using existing columns.
- `modules/services/split_result_service.py` (new): atomic decision persistence,
  context restoration, and safe split-results payload construction.
- `modules/resume_manager.py`: restore original-document classification after
  review. `modules/workflow_manager.py` was inspected; continuation needs no
  runner dispatch change.
- `modules/services/processing_state_service.py`: inspected and verified;
  existing leaf handling supports continuation without a source change.
- `modules/api_router.py`: delegate split-results payload construction and
  expose the additive outcome fields.
- `web/static/js/split-results/view.js`: single-document outcome and original
  extraction link.
- `web/templates/split_results.html`: clarify child metrics and display the
  number of originals continuing.
- `web/static/js/split-results/controller.js` and `index.js`: wire the new metric
  and invalidate cached split-results modules.
- `web/static/css/app.css` and `web/templates/app_base.html`: responsive split
  result rows and refreshed stylesheet URL.
- `test/standard_step/split/test_llamacloud_split_task.py`: task unit tests.
- `test/integration/test_llamacloud_split_fanout.py`: same-flow continuation
  and fan-out regression tests.
- `test/integration/test_split_fan_in_finalization.py`: existing terminal-state
  regressions run without file changes.
- `test/services/test_resume_manager.py`: original-document classification
  restored alongside corrected fields. Existing
  `test/integration/test_review_pause_resume.py` regressions also run.
- `test/integration/test_new_ui_routes.py`: updated split-results cache version
  expectation.
- `test/integration/test_single_document_split_results.py` (new): API contract.
- `test/visual/test_operator_page_modules.py`: focused renderer regressions.
- `test/helpers_visual.py` and `test/test_helpers_visual.py` (new): bounded
  visual-server startup, file-backed diagnostics, and process cleanup regression
  tests.
- `test/visual/test_schema_review_visual.py`: shared visual fixture now uses
  the safe server lifecycle helper.
- `test/visual/test_single_document_split_visual.py` (new): authenticated
  production browser checks and screenshot evidence.
- `docs/design_architecture.md`, `docs/user_guide.md`, and
  `tasks/standard_task_creation_guidelines.md`: continuation semantics, operator
  metrics/links, and durable task/retry contracts. These documentation updates
  were made after focused and visual tests passed.

Keep this list current during implementation; add any materially changed files.

## Implementation sequence

### 1. Confirm metadata consumers and fixtures

- [x] Trace category/confidence/pages through extraction, review, retry,
  resume, failure presentation, and cleanup. Identify the context keys that
  currently arrive only through child context construction.
- [x] Confirm existing repository columns support the original classification;
  use a repository method rather than task-local SQL.
- [x] Establish synthetic one-page, multi-page single-document, partial-page,
  and multi-document fixtures with an injected adapter and temporary SQLite DB.

Prerequisite: architecture/task guidelines and existing split paths inspected.

### 2. Implement continuation and durable decision reuse

- [x] Add the exact full-document eligibility check after existing validation.
- [x] Persist a single-document outcome and classification atomically. Keep
  source artifact registration, but create no `split_pdf` artifact.
- [x] Return context with classification and split outcome, without setting
  `fan_out`, `split_children`, or `fan_out_start_task_index`.
- [x] Rehydrate the saved outcome when the same split task is retried or the
  root workflow is recovered. Attribute reuse to the configured task key and
  pinned pipeline/input so a different split step cannot reuse the wrong result.
  Avoid duplicate audit events and unnecessary repeat provider calls.
- [x] Preserve legacy child reuse and restore the persisted classification
  through review/resume and workflow context reconstruction where needed.
- [x] Complete unit tests below before marking this section complete.

### 3. Verify workflow, artifacts, and finalization

- [x] Prove downstream tasks run once on the original ID in the original flow,
  with no child dispatch, and task-run ordering is split -> downstream -> cleanup.
- [x] Prove successful, failed, and review-paused/resumed originals reach the
  correct document/batch state and count as one leaf.
- [x] Verify real cleanup/archive behavior preserves registered durable artifacts.
- [x] Run existing multi-child fan-out/fan-in regressions and partial-segment tests.

### 4. Present the outcome in production UI

- [x] Add explicit split outcome and root classification fields to the
  split-results response through a service; keep route responsibilities thin.
- [x] Keep `documents_created` as actual child count (zero for continuation).
  Add a separately named count for documents continuing on the original if
  needed; do not silently redefine existing API fields.
- [x] Show "No split needed" with category, confidence, and pages, and provide
  an extraction link to the original document. Do not infer this outcome just
  because a source has no children.
- [x] Keep split outcome separate from downstream processing status; a later
  extraction failure must still display as failed.
- [x] Distinguish zero segments, skipped splitting, and pending results. Verify
  batch progress remains visible for an original document without children.
- [x] Add API and renderer tests; rebuild CSS if utility classes/templates change.

### 5. Visual verification, successful tests, then documentation

- [x] Run authenticated browser tests against an isolated production app with
  synthetic data, fake provider responses, and temporary runtime paths.
- [x] Inspect screenshots at desktop (1440 x 900) and mobile (390 x 844),
  checking readable text, wrapping, usable links, and layout overflow.
- [x] After successful focused, integration, and visual testing, update architecture split behavior and task guidelines for durable
  single-document decisions, retries, and preserved context.
- [x] Review the diff and run the relevant regression suite; run full pytest
  before handoff because this affects state, workflow, API, and UI together.

## Unit and integration test matrix

| Scenario | Required evidence |
| --- | --- |
| One segment, one-page PDF | Original identity/path preserved; no child/PDF/fan-out; decision persisted |
| One segment, all pages in order | Same behavior for a multi-page PDF; category/confidence available downstream |
| One partial segment | Existing child PDF contains only selected pages; fan-out retained |
| Duplicate/reordered pages | No incorrect original-file continuation; preserve existing validation/fan-out semantics |
| Invalid page numbers | Existing failure contract; no durable partial decision or children |
| Low confidence/unknown category | Existing configured policy still applies before continuation |
| No segments/disabled/child input | Existing skip behavior; no false single-document outcome |
| Repeated execution/recovery | Persisted decision reused; no duplicate classification audit/artifacts/provider call |
| Existing historical child | Continue existing child workflow rather than flattening it |
| Downstream success/failure | Original task runs and final document/batch status/counts correct |
| Review pause/resume | Same document ID; classification/context preserved; correct next task |
| API with mixed batch | Root continuation and children distinguishable; child counts unchanged |
| API security | Auth unchanged; no raw provider responses or secrets exposed in new fields |

## Browser/visual test matrix

- Single-document split-results: "No split needed", classification, zero new
  children, original extraction link; clicking it opens the original result.
- Processing page: original row advances past split, displays review/failure/
  completion accurately, and does not remain waiting for nonexistent children.
- Mixed batch: single-document continuation alongside two-child split; counts,
  statuses, grouping, and extraction links remain accurate.
- Empty/skipped split response: no misleading "No split needed" classification.
- Desktop/mobile: capture and inspect screenshots; assert visible content,
  correct link targets, keyboard access, and no unexpected console/page errors.

Screenshots are evidence in addition to DOM/behavior assertions; nonblank-image
checks alone are insufficient. Use only synthetic PDFs and temporary databases.

## Verification commands

Run from the repository root using PowerShell and the repository interpreter.

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\standard_step\split\test_llamacloud_split_task.py
.\.venv\Scripts\python.exe -m pytest -v test\integration\test_llamacloud_split_fanout.py test\integration\test_split_fan_in_finalization.py test\integration\test_review_pause_resume.py test\integration\test_single_document_split_results.py
.\.venv\Scripts\python.exe -m pytest -v test\visual\test_operator_page_modules.py test\visual\test_single_document_split_visual.py
npm run build:css
.\.venv\Scripts\python.exe -m pytest -v
```

Run `npm run build:css` when frontend utility/template changes require it. If
Chromium is missing, install it with the repository interpreter's
`-m playwright install chromium`. Do not run live LlamaCloud smoke tests.

## Handoff requirements

Report changed files, exact commands/results, screenshot evidence, and any
checks not run. Preserve existing unrelated work; do not stage or commit unless
requested. This plan does not require new runtime dependencies or a schema
migration unless implementation uncovers a concrete missing persistence field.


## Implementation and verification record

Implemented on 2026-10-03. No schema migration, new dependency, staging, or
commit was needed. Existing unrelated `experimentc/` and its test were preserved.
Checkboxes above indicate the implementation/verification work was carried out;
the full-suite invocation was not wholly green, as detailed below.

Final focused command (95 passed):

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short test/standard_step/split test/standard_step/test_standard_task_edge_cases.py test/integration/test_llamacloud_split_fanout.py test/integration/test_split_fan_in_finalization.py test/integration/test_single_document_split_results.py test/integration/test_review_pause_resume.py test/services/test_resume_manager.py test/services/test_fan_in_service.py test/services/test_processing_state_service.py test/integration/test_new_ui_routes.py test/visual/test_operator_page_modules.py
```

Final browser/API/auth recheck command (11 passed):

```powershell
$env:DOCFLOW_VISUAL_BROWSER_CHANNEL='chrome'
$env:PLAYWRIGHT_NODEJS_PATH=(Get-Command node).Source
$env:DOCFLOW_VISUAL_SINGLE_PDF=(Resolve-Path 'sample stock invoices from internet/invoice_Steven Roelle_14184.pdf').Path
$env:DOCFLOW_VISUAL_BUNDLE_PDF=(Resolve-Path 'sample stock invoices from internet/random_merged_invoices_16jun26.pdf').Path
.\.venv\Scripts\python.exe -m pytest -q --tb=short test/visual/test_single_document_split_visual.py test/visual/test_operator_page_modules.py test/integration/test_single_document_split_results.py test/core/test_auth_edge_cases.py::test_login_reports_setup_unknown_user_and_invalid_password
```

The operator password was provided privately through a process environment
variable for the isolated test account; its value is absent from source and
this document. Without that variable, tests use their existing synthetic
operator credential. Supplied sample PDFs were copied into the isolated
configured processing directory, preserving the production PDF-preview roots.
Provider classification responses and extracted values were controlled test
fixtures. No live LlamaCloud call was made.

Desktop (1440 x 900) and mobile (390 x 844) screenshots were inspected under
`output/playwright/single-document-split/`: results, original PDF extraction,
and processing overview. Screenshot inspection exposed a narrow-table status
wrapping issue; scoped responsive CSS and a badge-height browser assertion
fixed it. The original extraction link, PDF canvas, keyboard focus, page width,
classification, zero-child continuation, and four-child result were verified.
An additional interactive operator session used agent-browser and confirmed
both result paths and the original PDF preview.

`npm run build:css` succeeded; committed vendor CSS did not change.
`git diff --check` passed. Pyright and live-provider checks were not run.

The full invocation `.\.venv\Scripts\python.exe -m pytest -q` completed with
1,515 passed, 4 skipped, 4 failed, and 4 setup errors. Three failures used
assertions collected before the singular/plural wording update during the run;
all passed on the final file rechecks. One unrelated authentication test had a
temporary SQLite file-open error and passed on recheck. Three browser setup
errors were Windows `spawn EPERM` errors for bundled Chromium; the fourth
was a test-server startup timeout. The detailed investigation below corrects
the initial grouping of all four as browser launch errors. Using installed
Chrome through a temporary runtime-only launcher, the affected existing visual
modules passed (8 tests) with:

```powershell
.\.venv\Scripts\python.exe output/recheck_visual_regressions.py
```

That temporary diagnostic launcher ran
`test/visual/test_frontend_phase8.py::test_frontend_performance_budget` and
`test/visual/test_operator_feedback_visual.py` with the installed Chrome channel;
it changed no production or maintained test code and was removed after use.
The temporary server launcher and state manifest were also removed, and the
isolated server/browser were stopped. Screenshots remain in the ignored output
folder. A second complete full-suite
run was not performed. All originally failing/erroring cases passed in the
focused or browser rechecks. Windows access-violation diagnostics also appeared
intermittently during dependency imports; the reported successful runs completed
with exit code zero.


## Failure investigation follow-up (2026-10-03)

- [x] Reproduce all originally failing/erroring cases against final sources.
- [x] Exercise SQLite user initialization repeatedly using independent temp DBs.
- [x] Reproduce and fix unread startup-output pipe backpressure; add lifecycle tests.
- [x] Recheck the affected browser tests with default bundled Chromium after the fixture fix.
- [x] Document observed resource pressure and limits of the root-cause evidence.

| Original issue | Investigation finding |
| --- | --- |
| Three singular/plural assertions | Tests had been collected before the wording changed during the earlier full run. Current assertions and UI agree; all pass. |
| One SQLite file-open error | Did not reproduce in the original test or 20 repeated user-initialization exercises using independent temporary databases. No application change justified. |
| Three Chromium `spawn EPERM` setup errors | Did not reproduce in the new run using default bundled Chromium. Browser binaries are present; no reinstall or permanent installed-Chrome workaround was needed. |
| One visual-server startup timeout | Shared fixture had an unread stderr pipe and a 30-second startup deadline. Pipe backpressure was reproduced independently; the historical log does not prove whether that or slow startup caused this particular timeout. |

The user reported gaming during the full run with memory under pressure. A
subsequent read-only measurement showed approximately 0.8 GB free out of
15.9 GB total physical memory. Resource pressure is a plausible contributor to
the transient failures and startup delay, but historical peak-memory telemetry
was not available to prove each failure's cause.

A synthetic child writing 128 KiB to stderr could not open its listening socket
until the parent drained the old pipe. This confirms a real fixture weakness.
The shared fixture now writes stdout/stderr to a temporary log, waits up to
60 seconds with a monotonic deadline, and reaps the child on normal teardown,
startup timeout, early exit, and test failure. It reports the log path without
copying potentially sensitive child output into the error message.

Verification was sequential; no full-suite run was repeated under the observed
memory pressure. First, all affected regressions passed before the fixture
change (12 passed, default Chromium). After the change:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short test/test_helpers_visual.py
# 4 passed

.\.venv\Scripts\python.exe -m pytest -q --tb=short test/core/test_auth_edge_cases.py::test_login_reports_setup_unknown_user_and_invalid_password test/visual/test_operator_page_modules.py::test_split_results_links_original_and_escapes_classification test/visual/test_single_document_split_visual.py test/visual/test_frontend_phase8.py::test_frontend_performance_budget test/visual/test_operator_feedback_visual.py
# 12 passed, default bundled Chromium, no temporary launch override
```

The four helper regressions cover noisy startup beyond pipe capacity, early
exit without echoing output, startup-timeout cleanup, and cleanup after a test
exception. `git diff --check` also passed. No production application changes,
new dependencies, credential changes, or commits were made for this follow-up.
