# Local LiteParse + Ollama invoice experiment

The benchmark is a standalone experiment. It does not import the application's
workflows, read its configuration, write its database, or use LlamaCloud.
The separate production-validation audit described below reads application
configuration and SQLite strictly read-only. LiteParse 2.15.1
parses embedded text and runs its bundled English Tesseract OCR for scans. Qwen
`qwen3.5:9b-q4_K_M` receives only parsed text and source element IDs through the
loopback Ollama API. The scripts reject remote inference endpoints, redirects
and environment proxies. Installing packages may download software; invoice
content is processed locally. With dependencies/model assets installed, the
experiment can run without an internet connection.

Official references: [LiteParse Python API](https://github.com/run-llama/liteparse/tree/main/packages/python)
and [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

Run these commands from the repository root, using its virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r experimentd\requirements.txt
.\.venv\Scripts\python.exe experimentd\extract_invoice.py 'path\invoice.pdf' --pages 1 --output experimentd\output\single
.\.venv\Scripts\python.exe experimentd\run_benchmark.py --resume
.\.venv\Scripts\python.exe experimentd\evaluate.py
.\.venv\Scripts\python.exe experimentd\render_overlays.py
.\.venv\Scripts\python.exe -m pytest -v experimentd\test_experiment.py
```

Ollama must already be running and the exact requested model must be installed.
The scripts do not automatically pull a model. Options on `extract_invoice.py`
include `--model`, `--host`, `--pages`, `--dpi`, `--timeout`, `--context` and
`--max-tokens`. Select the pages belonging to one invoice. Unrelated documents
in a mixed bundle must be separated before extraction.

`samples.local.json` contains the six manually reviewed sample selections,
printed expected values and normalized reference rectangles. It is present
locally and ignored by Git. The three FTS samples use their tax invoice on page
2; surrounding delivery/purchase orders are excluded. These are purposively
selected samples, including a rounding discrepancy and a multirow scanned
invoice with a negative discount row. They are not a random production benchmark.
The references are never included in a model request.

For another machine or sample set, copy `samples.example.json` to
`samples.local.json`, replace the synthetic references by independently reviewing
the original PDFs, and supply PDF paths relative to the repository root. Each
sample has `id`, `group`, `pdf`, `pages`, `fields` and `line_items`. Each reference
field has a string/null `value` and `regions` with one-based `page` plus
`bbox_normalized: [x0,y0,x1,y1]` in the range 0..1. Null fields have no regions.
Names/paths and reference values belong only in the ignored local manifest.

## Output and scoring

Each sample directory under `output/benchmark/` contains:

- `parsed.json`: LiteParse text, native result, word boxes, page dimensions and
  source SHA-256.
- `request.json` and `ollama_response.json`: reproducible private model input
  and raw response; never commit these files.
- `invoice.json`: structured fields and line items. Each field contains `value`,
  model-selected `source_ids`, per-word `boxes`, per-page union `bounding_boxes`,
  and a grounding status. Unknown/missing citations are flagged without repair.
- `run.json`: model digest, parser version, parameters, token counts and timings.
- `overlay_page_N.png`: red source-word boxes over the original PDF page; blue
  rectangles are independently reviewed reference regions. Source PDFs are
  never modified.

Header fields: customer name, supplier name, invoice date (ISO YYYY-MM-DD),
invoice number and final invoice total. Row fields: complete description,
unit of measure, quantity, unit price and printed line total. Missing values
remain null. Amounts and quantities are decimal strings. A row also contains
`computed_line_total = quantity * unit_price`, rounded half up to two decimals,
and `printed_minus_computed`. Calculation does not overwrite a printed amount;
that difference may already exist in the original invoice.

Boxes are `[x0,y0,x1,y1]` in top-left PDF viewport coordinates, 72 points per
inch. OCR DPI does not change this coordinate system. The model selects text
IDs; Python resolves their actual LiteParse coordinates. Boxes are not model
guesses. Union rectangles may cover whitespace between description lines;
the per-word boxes give the more precise source locations.

`accuracy.json` records every field comparison, missing/extra rows, partial
description token F1, arithmetic, and separate value/location scores.
`SUMMARY.md` gives aggregate results. Text equality ignores case, punctuation
and layout whitespace; numbers compare as decimals rounded to two places. Descriptions
include printed continuation/OFFER/code lines. Rows are compared in printed
order. Failed samples remain in the denominators. Null-value accuracy and
present-value accuracy are reported separately.

Bounding-box evaluation is **coarse localization**, not tight pixel IoU:
every cited word box must have at least 80% of its area inside an independently
marked value region on the correct page. Citing labels, neighbouring cells or
table headers fails when they lie outside that region. The joint score requires
both the correct value and correct location. This does not verify exhaustive
word coverage, character-level geometry or performance on rotated/multipage
invoices. The parser and overlay synthetic integration test covers a normal page.

Reference regions were marked before inference, then checked against the source
in overlay QA. Two FTS reference rectangles were corrected for placement/width;
the manually transcribed expected values were unchanged.

The first experimental pass used a verbose coordinate payload; longer prompts
were truncated and produced incorrect fields. That pass is preserved locally
in `output/initial_run/`. The current version uses compact element arrays and
a smaller generation allowance. Do not interpret the initial pass as a valid
accuracy result. Raw artifacts permit checking token counts and local failures.

`--resume` skips successful outputs only when source digest, selected pages,
model name/digest, parser version, OCR DPI, inference options and prompt digest
agree. Failed outputs are
rerun. Use a new output directory for a different experimental setup. Results,
references, renderings and extraction content are ignored by Git. No application
dependencies or production files are changed.

## Side-by-side comparison with the existing GLM task

See [COMPARISON.md](COMPARISON.md) for the completed six-sample comparison and
the distinction between raw Qwen decisions and final task output.

`compare_methods.py` runs both methods against the same six selected invoice
pages and frozen references. `glm_comparison.py` calls the existing
`standard_step.extraction.glm_ocr_adapter.GlmOcrAdapter` in document mode;
it does not recreate that task's extraction/recovery/table-resolution logic.
The experiment supplies the requested business fields and renders only the
selected invoice pages. It uses a recording loopback client rather than starting
an application workflow or accessing the live database/configuration.

```powershell
.\.venv\Scripts\python.exe -m experimentd.compare_methods --resume
.\.venv\Scripts\python.exe -m experimentd.compare_methods --report-only
.\.venv\Scripts\python.exe -m experimentd.trace_glm_stages
.\.venv\Scripts\python.exe -m experimentd.glm_comparison 'path\invoice.pdf' --pages 2 --output experimentd\output\glm_single
.\.venv\Scripts\python.exe experimentd\render_overlays.py --output experimentd\output\comparison\liteparse
.\.venv\Scripts\python.exe -m pytest -v experimentd\test_comparison.py experimentd\test_experiment.py test\extraction\test_glm_ocr_adapter.py test\extraction\test_glm_ocr_adapter_complete.py
```

Default output is `output/comparison/`. `liteparse/<sample>/` and
`glm_task/<sample>/` contain raw responses, structured JSON and timings. For the
GLM method, `calls/NN/` records every request/response privately and
`adapter_result.json` retains the task's normalized data, findings and page
references. `comparison.json` contains all field-level disagreements, paired
wins/losses, per-field accuracy and per-invoice timing; `SUMMARY.md` is readable.
These outputs and the copied reference manifest remain Git-ignored.

Both methods use the same installed Qwen model digest. GLM uses the documented
task parameters: OCR 216 DPI, Qwen image maximum 1280 pixels, context limits
8192/18000, generation allowances 2048/10000, and up to two resolver attempts.
LiteParse retains its 300-DPI local OCR and text-only Qwen prompt with context
16384/output allowance 4096. The GLM transport adds seed 42 for reproducibility.
Previous benchmark models are unloaded when changing models to avoid GPU
contention; wall timings include this policy and model loading. Ollama inference
times excluding load are reported separately.

This compares two practical extraction pipelines, not just their OCR engines:
the GLM task's Qwen resolver can inspect images, whereas the LiteParse arm gives
Qwen text and word coordinates. The GLM adapter returns page evidence rather
than word boxes, so its bounding-box metric is **not available**, never zero.
Full field accuracy uses the identical scorer and counts missing/extra rows and
failed samples. The references are unchanged from the first experiment and
never enter either method's model requests. No production behavior is changed.

Numeric task fields use `float`/`Optional[float]`; only names, identifiers,
descriptions and units use strings. All results are converted to the scorer's
decimal-string representation after extraction. This avoids treating numeric
columns as delimited text during the production adapter's row repair.

`trace_glm_stages.py` reconstructs raw Qwen resolver decisions from recorded
calls and compares them with the final task data. It makes no additional model
requests. The stage diagnostic distinguishes OCR/model errors from subsequent
table-grounding changes; it is separate from the main final-output score.
An initial trial with string-typed numeric columns is preserved privately in
`output/comparison/string_field_trial/` and excluded from the final comparison.

## Expanded comparison: twenty invoices per type

See [EXPANDED_COMPARISON.md](EXPANDED_COMPARISON.md) for the measured results.

The expanded manifest is `samples_expanded.local.json`, kept private and ignored
by Git. It retains the original six references and adds seventeen invoices per
type. `cohort` distinguishes `original` and `additional`; original values and
regions remain unchanged. Superstore additions are sampled with seed 42 from
nonempty invoice templates. FTS additions use reviewed invoice pages in filename
order, excluding bundles without invoices and one ambiguous handwritten invoice
before inference. One selected FTS invoice spans pages 1 and 2.

`prepare_expansion.py` exports native source evidence and Poppler-rendered pages
for independent reference review. It requires `fts_pages.local.json`, a private
filename-to-invoice-pages map established by inspecting the source bundles; it
does not assume that page 2 is an invoice. The selection JSON alone is not a
completed reference manifest. Populate and visually check the expected fields
using `samples.example.json` as the contract before running extraction.

```powershell
.\.venv\Scripts\python.exe -m experimentd.prepare_expansion --per-type 20
.\.venv\Scripts\python.exe -m experimentd.compare_methods --manifest experimentd\samples_expanded.local.json --output experimentd\output\comparison_expanded --resume
.\.venv\Scripts\python.exe -m experimentd.report_expanded
.\.venv\Scripts\python.exe -m pytest -v experimentd\test_expansion.py experimentd\test_comparison.py experimentd\test_experiment.py test\extraction\test_glm_ocr_adapter.py test\extraction\test_glm_ocr_adapter_complete.py
```

`report_expanded.py` writes `EXPANDED_COMPARISON.md` containing aggregate results
only. It reports the additional cohort separately, whole-invoice correctness,
missing/extra rows, accuracy over identical reference fields and a per-invoice
average so large invoices do not dominate every metric, plus an aggregate
field-by-field accuracy table. Raw Qwen versus final
GLM task decisions remain a separate diagnostic.

The prompts, OCR settings, numeric types, context and generation allowances are
unchanged from the six-sample comparison. Verified original outputs are reused;
their timings are earlier measurements. Additional-only timings are reported
separately. `--previous-model` may identify the last model used by this benchmark
when continuing a staged run, so its first switch unloads that model consistently.

New references explicitly set `geometry_reviewed: false`: their value accuracy
is scored, and LiteParse retains word boxes, but no box-accuracy claim is made
for unmarked regions. Box metrics therefore cover the original six references.
Printed discounted line amounts remain separate from quantity × price; original
rounding differences are not corrected to improve a score. Failed extractions
and missing/extra rows remain part of the accuracy result.

The expanded scorer also fixes missing-row handling: an entirely missing row
receives no credit for cells whose expected value is null. This applies to both
methods. The original six scores are unchanged because neither method missed a
reference row on that set.
For CJK text, matching ignores inserted line-wrap spaces while retaining each
character; this fixes layout sensitivity in the stated whitespace-normalization
rule. Both scorer fixes were made before additional FTS inference and apply to
both methods. Model prompts and settings were unchanged.

## Audit of the production LiteParse pipeline

`inspect_standard_task.py` is a separate read-only validation helper. It reads
the application's deployment configuration to locate SQLite, opens the database
with `mode=ro`, and compares raw extraction, final approved fields and registered
JSON exports with independently transcribed private references. It does not
submit PDFs, call a model or alter workflow/review state. When multiple batches
are supplied, the latest supplied attempt per sample is selected and all supplied
attempt status counts are retained. Human corrections cannot inflate raw model
accuracy, and missing or mismatched exports fail verification.

```powershell
.\.venv\Scripts\python.exe -m experimentd.inspect_standard_task --batch BATCH_ID --batch REPLAY_BATCH_ID
.\.venv\Scripts\python.exe -m pytest -q experimentd\test_inspect_standard_task.py
```

Replace the placeholders with actual batch IDs. Detailed customer values stay
in ignored `output/liteparse_pipeline_validation/*.local.json`; the synthetic
audit tests require no live database or customer files. See the
[production validation report](../docs/liteparse_pipeline_validation.md) for the
six-invoice UI run and [task guide](../docs/liteparse_extract_task.md) for the
generic standard task. The benchmark reports above describe their original
experiment configurations, separately from that production validation.
