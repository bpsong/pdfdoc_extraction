# LiteParse production pipeline validation

On 4 October 2026, the generic `LiteParseExtractTask` was tested through the
running application's admin and review interfaces with local LiteParse 2.15.1,
Tesseract and Ollama `qwen3.5:9b-q4_K_M`. PDF contents stayed on this computer.
The implementation has no invoice-specific schema or postprocessing; the
invoice field definitions and instructions are published pipeline parameters.

## Published configuration

The active upload pipeline is **LiteParse Invoice Review JSON**, stable key
`liteparse-invoice-review-json`, published version **1**. Its template ID is
`678e5812-5173-4140-ac60-522a8e70a47b`. The editor validated it without blocking
issues or warnings before publication and activation.

Its three steps are **Lite Parse Extract → Review Gate → Store Metadata As Json**.
Extraction uses localhost Ollama, 300 DPI, local English OCR, all submitted
pages, a 32,768-token context, a 4,096-token output allowance and a 600-second
timeout. Review is always required at document scope, uses the published
**LiteParse invoice review** form version 1 (`liteparse-invoice-review`) and
resumes at the next task. JSON output is `data/liteparse_invoice_json/{id}.json`.

The configured fields are customer name, supplier name, invoice date, invoice
number, invoice total and line items containing description, unit of measure,
quantity, unit price and printed line total. Date normalization uses ISO format;
identifiers remain strings. Missing units remain null. Printed amounts are not
silently replaced by a computed quantity-times-price value.

## Inputs and scoring

Three generated Superstore invoices and three scanned FTS invoices were selected
from the original private experiment references. Superstore page 1 and FTS
invoice page 2 were saved as single-page test PDFs, preserving embedded text or
the original scan respectively. This tests extraction, review and export; it
does not test splitting mixed-document bundles.

References were independently transcribed before these production runs and were
not changed to match model output. Text comparison ignores case, punctuation
and layout whitespace while retaining words, digits and row order. Numeric
comparison uses the existing experiment scorer's two-decimal rounding. Missing
or additional rows count as errors. Correct null units contribute three checks
to the Superstore denominator. Location accuracy was not scored.

| Original extraction, before review | Superstore | FTS |
|---|---:|---:|
| Invoices | 3 | 3 |
| Header fields | 15/15 (100%) | 13/15 (86.67%) |
| Line-item fields | 15/15 (100%) | 38/40 (95%) |
| All checked fields | **30/30 (100%)** | **51/55 (92.73%)** |
| Completely correct invoices | 3/3 | 2/3 |
| Correct row counts | 3/3 | 3/3 |

Quantity times unit price, rounded half up to two decimals, matches the printed
line total in 10 of the 11 extracted rows. One Superstore row has a one-cent
discrepancy between the printed rate calculation and printed total. The task
preserves those source values; arithmetic validation or a computed total belongs
in a separately configured business rule, rather than an OCR correction.

All four FTS errors were in the third invoice: the date, the invoice number,
one description word and an omitted model code in another description. These
were corrected against the source PDF through the review UI. The original
extraction remains stored separately. After review, the six approved outputs
matched all **85/85** reference checks. This post-review result measures the
combined human workflow, not model accuracy.

All six invoices were visually inspected beside their source PDFs. The History
view shows six completed reviews for this pipeline. SQLite and registered
artifacts confirm six completed documents and six JSON exports, each equal to
the final approved field values. Review resume did not rerun extraction.

These six purposively selected samples support better extraction on clean native
PDFs in this test. They do not establish an accuracy rate across all invoices or
document types, or replace the larger experiment's results.

## Issues found and resolved

The initial six submissions failed before inference because LiteParse requires
an isolated worker pool for its parser timeout. The adapter now uses one worker
and a hard parser deadline; a real synthetic PDF regression covers this path.

On the next run, five documents completed, while FTS 2 extracted successfully
after an Ollama retry but retained its earlier error in the shared context.
The task now clears only its own previous error after a successful retry,
preserves other tasks' errors and leaves historical failure records intact.
The task creation guidelines and regression tests document this behavior.

FTS 2 was then uploaded again through the UI. Its first inference returned HTTP
500 with a CUDA out-of-memory error in the local Ollama log; the automatic retry
recovered, correctly paused for review and completed after approval. Its raw
extraction was correct without edits. Failed setup attempts and the earlier
failed FTS 2 workflow are retained in application history, rather than counted
as completed documents. The accuracy table selects the latest supplied attempt
for each of the six samples and reports raw extraction separately from review.

Requests now use `keep_alive: 0`, releasing model memory before operator review;
`ollama ps` was empty after the final extraction. This adds model-loading time
and does not guarantee that a 32K context fits the machine's 8 GB GPU. Larger
scanned documents can require CPU offloading, take much longer, or need a retry.
There is one Qwen inference per normal attempt; retries can make additional
calls. No general speed advantage was established by this validation.

The review viewer suppresses highlights for LiteParse's `diagnostic_only`
citations, retains page navigation and identifies citations as unverified. No
model confidence or verified box accuracy is claimed.

## Verification and evidence

Implementation changes are grouped as follows:

- `standard_step/extraction/liteparse_adapter.py` and `liteparse_extract.py`:
  local parsing/inference, source diagnostics and the standard task contract.
- `modules/services/task_registry_service.py`, `pipeline_template_service.py`
  and `tools/config_check/parameter_validator.py`: approved task registration,
  published review dependencies and parameter/schema validation.
- `modules/services/failure_service.py`: local extraction failures retain
  redacted local-provider messages instead of a LlamaCloud label.
- `web/static/js/pipeline_config.js` and `pipeline-config/task-editors.js`:
  generic field editing and local extraction controls.
- `web/static/js/pdf_viewer.js`, `web/templates/human_review.html`,
  `extraction_results.html` and `failures.html`: diagnostic citation handling
  and a consistent browser cache version on all shared viewer pages.
- `requirements.txt`: pinned LiteParse dependency.
- `test/extraction/test_liteparse_extract.py`,
  `test/integration/test_liteparse_pipeline.py`,
  `test/visual/test_liteparse_pipeline_editor.py`,
  `test/visual/test_pdf_viewer_regressions.py` and
  `test/visual/test_schema_review_visual.py`: focused regression coverage.
- `README.md`, `docs/liteparse_extract_task.md`, `docs/user_guide.md`,
  `docs/design_architecture.md`, `docs/review_schema_admin_guide.md`,
  `docs/frontend_deployment.md`, this report and
  `tasks/standard_task_creation_guidelines.md`: setup, operator and task author
  guidance.
- `docs/config_check_troubleshooting.md`, `tools/config_check/README.md` and
  `tools/config_check/examples/ERROR_CODES.md`: LiteParse validation findings,
  constraints and shared field-check codes.
- `experimentd/inspect_standard_task.py` and `test_inspect_standard_task.py`:
  read-only private audit and synthetic scoring safeguards.

The full suite passed **1,565 tests, with 4 skipped**:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
```

After the final memory-release and diagnostic-citation UI refinements, the
following focused suite passed **75 tests**:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test\extraction\test_liteparse_extract.py test\integration\test_liteparse_pipeline.py test\services\test_failure_service.py test\visual\test_liteparse_pipeline_editor.py test\visual\test_glm_ocr_pipeline_editor.py test\visual\test_pdf_viewer_regressions.py test\visual\test_schema_review_visual.py --tb=short
```

The tests cover generic shipping data, configured typing and normalization,
local-only model validation, parser deadlines, malformed/nonfinite output,
redacted failures, retry recovery, real SQLite publication/review/resume/export,
editor controls and diagnostic highlight suppression. `npm run build:css` and
`git diff --check` passed. Pyright and Ruff were not run; neither is installed as
a pinned project tool.

The read-only audit helper is `experimentd/inspect_standard_task.py`. Synthetic
audit regressions verify that corrected values cannot inflate raw accuracy,
failed attempts remain counted and absent/mismatched exports cannot pass.
All **4** synthetic audit tests passed:

```powershell
.\.venv\Scripts\python.exe -m pytest -q experimentd\test_inspect_standard_task.py
.\.venv\Scripts\python.exe -m experimentd.inspect_standard_task --batch 8341f206-7a6e-417a-b0bd-0a79ac007a6f --batch 7f8ee5ac-f32f-433c-b4d9-1edc2ea0fd18
```

Following a report of the old GLM-OCR label, all three viewer templates were
aligned to `pdf-evidence-4`. The FTS 3 review was refreshed and selecting its
customer field displayed diagnostic citations without a GLM-OCR label or a
bounding-box highlight. The following **8** tests passed, including a real
browser assertion that page-only evidence messages remain provider-neutral:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test\visual\test_pdf_viewer_regressions.py test\visual\test_schema_review_visual.py::test_review_visual_schema_driven_fields_desktop_and_mobile --tb=short
```

Customer PDFs, references, detailed raw/final results, local runtime logs and
screenshots stay in ignored local storage. The combined audit is
`experimentd/output/liteparse_pipeline_validation/validation.local.json`;
the published-editor screenshot is `07-published-pipeline.png` in that folder.
This maintained report contains only aggregate results and configuration.

The documentation completion pass updated the README, user guide version 3.9,
provider guide, architecture, review-form and frontend deployment guides,
task creation guidelines, troubleshooting and CLI finding references. The
generic manifest parameter example passed the real parameter and citation
schema validators without errors or warnings. All 21 newly added local links
resolved, including section anchors. The following checks passed; no invoice
processing or application restart was required for this documentation pass:

```powershell
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
git diff --check
```

The release checker validated all 16 frontend feature graphs. The full pytest
suite and CSS build were not repeated for these documentation-only changes;
the earlier code verification results remain recorded above.
