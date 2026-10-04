# Observed results: 4 October 2026

This report covers the original six invoices. See
[the expanded comparison](EXPANDED_COMPARISON.md) for twenty invoices per type.

LiteParse 2.15.1 and local Ollama `qwen3.5:9b-q4_K_M` completed all six invoices
without sending PDFs or parsed content to a cloud service. This is promising for
local extraction, but the scanned FTS results still require review.

| Invoice type | Samples | Header fields | Line item fields | All structured fields | Correct value AND location, present fields |
|---|---:|---:|---:|---:|---:|
| Superstore | 3 | 15/15 (100%) | 15/15 (100%) | 30/30 (100%) | 26/27 (96.3%) |
| FTS scans | 3 | 13/15 (86.7%) | 37/40 (92.5%) | 50/55 (90.9%) | 48/55 (87.3%) |
| Combined | 6 | 28/30 (93.3%) | 52/55 (94.5%) | 80/85 (94.1%) | 74/82 (90.2%) |

All eleven priced rows were found, including the negative discount row in the
longer FTS invoice. Customer name, supplier name and invoice total were correct
for every sample. Quantities, unit prices and printed line amounts were correct
for every extracted row. The three absent Superstore units of measure remained
null instead of being guessed.

The five FTS field errors were:

- One missing `CAN` unit of measure, although LiteParse recognized it.
- One invoice number containing an extra numeral already present in OCR text.
- One incorrect and invalid ISO date; OCR misread the year, and Qwen's date
  normalization introduced another error. JSON/schema validity alone does not
  establish semantic correctness.
- One description preserving an OCR word error (`REEFER` versus `REFER`).
- One description omitting a printed model code that LiteParse itself did not
  recognize. Reviewing the saved raw text and word elements clarified this
  attribution; the field-accuracy score is unchanged.

Six of eight FTS descriptions matched after ignoring case, punctuation and
layout whitespace; their average token F1 was 0.991. Partial description
similarity does not excuse losing a product/model code.

Pure location accuracy was 26/27 (96.3%) for Superstore and 52/55 (94.5%) for
FTS. Four location failures involved a date label, an address word, a neighbouring
currency cell, or a missing unit citation. The joint metric above additionally
requires the extracted value to be correct. Bounding boxes come from actual
LiteParse word coordinates selected by Qwen; no fuzzy search or coordinate
guessing repairs the output.

The box metric requires every selected word rectangle to have at least 80% of
its area inside a manually reviewed value region on the correct page. It is a
coarse localization check, not tight pixel IoU or exhaustive character coverage.
Source-page overlays were reviewed locally. Two mispositioned reference
rectangles were corrected against the original scan during overlay QA; expected
values were unchanged.

The calculated line total is stored separately from the printed line amount.
One Superstore row's printed amount differs from rounded multiplication by
0.01; the script preserves and flags that original invoice discrepancy.

Final per-invoice elapsed times were 23.1-24.5 seconds for Superstore and
29.4-106.8 seconds for FTS; the six successful runs totalled 241.73 seconds.
These are single runs with a warmed model, not averaged latency benchmarks.
Settings: OCR 300 DPI, temperature 0, seed 42, thinking disabled, context 16384,
generation allowance 4096 tokens. The largest final prompt had 11054 tokens and
generated 2759 output tokens. Final requests completed without prompt truncation.

Three Superstore native-text invoices and three scanned FTS tax invoices were
selected deliberately to include missing units, rounding, multiline descriptions
and a discount. FTS invoice pages were selected manually from mixed bundles;
purchase/delivery-order classification was not tested. This small set does not
establish general production accuracy or rotated/multipage-invoice performance.

The initial verbose prompt overflowed the context on longer scans and produced
incorrect fields; one initial Superstore request also failed. That pass is retained
in ignored `output/initial_run/`. All six were rerun with the final compact prompt,
and the figures here include every final sample. They describe a tuned prompt on
this small set, not a held-out evaluation.

## Files and verification

All new files are under `experimentd/`: `extract_invoice.py` (local extraction),
`run_benchmark.py` (sample runner/checkpoints), `evaluate.py` (accuracy metrics),
`render_overlays.py` (box previews), `test_experiment.py` (synthetic tests),
`requirements.txt`, `samples.example.json`, `README.md`, `RESULTS.md`,
`__init__.py` and `.gitignore`. Private expected values are in ignored
`samples.local.json`; raw inputs, outputs, metrics and images are in ignored
`output/`. Production application files were unchanged.

Commands run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install liteparse==2.15.1
.\.venv\Scripts\python.exe experimentd\run_benchmark.py
.\.venv\Scripts\python.exe experimentd\evaluate.py
.\.venv\Scripts\python.exe experimentd\render_overlays.py
.\.venv\Scripts\python.exe -m pytest -v experimentd\test_experiment.py
.\.venv\Scripts\python.exe experimentd\run_benchmark.py --resume
.\.venv\Scripts\python.exe -m pip check
```

All six final extractions succeeded. All 26 focused tests passed, including real
LiteParse parsing and PNG overlay generation on a synthetic PDF, local HTTP proxy/
redirect isolation, missing/extra-row scoring, Decimal arithmetic and model-digest
checkpoint invalidation. Dependency checks passed. No full application suite,
frontend build, Ruff or Pyright check was run for this isolated experiment.
