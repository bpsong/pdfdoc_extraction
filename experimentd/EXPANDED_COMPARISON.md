# Expanded local invoice comparison

Compared 40 invoices: 20 fts, 20 superstore.
The reference set contains 87 item rows and 635 expected structured fields.

The original six results are reused only after verifying source/model digests, pages, prompts and settings. The additional samples use the same frozen extraction configuration. References were independently transcribed/visually checked before their inference, and never entered model requests.

## All samples

| Group | Method | Headers | Line fields including extra-row penalties | All fields | Complete invoices |
|---|---|---:|---:|---:|---:|
| fts | liteparse | 83/100 (83.0%) | 265/335 (79.1%) | 348/435 (80.0%) | 4/20 (20.0%) |
| fts | glm_task | 97/100 (97.0%) | 241/350 (68.86%) | 338/450 (75.11%) | 6/20 (30.0%) |
| superstore | liteparse | 100/100 (100.0%) | 100/100 (100.0%) | 200/200 (100.0%) | 20/20 (100.0%) |
| superstore | glm_task | 99/100 (99.0%) | 65/110 (59.09%) | 164/210 (78.1%) | 0/20 (0.0%) |
| overall | liteparse | 183/200 (91.5%) | 365/435 (83.91%) | 548/635 (86.3%) | 24/40 (60.0%) |
| overall | glm_task | 196/200 (98.0%) | 306/460 (66.52%) | 502/660 (76.06%) | 6/40 (15.0%) |

## Additional samples only

These samples were not used to tune the prompts. FTS selection was based on source-page eligibility/readability rather than model output; it is not random production sampling.

| Group | Method | All fields | Same reference fields | Complete invoices | Mean elapsed seconds (successful samples) |
|---|---|---:|---:|---:|---:|
| fts | liteparse | 298/380 (78.42%) | 298/380 (78.42%) | 3/17 (17.65%) | 54.97 |
| fts | glm_task | 288/395 (72.91%) | 288/380 (75.79%) | 4/17 (23.53%) | 79.62 |
| superstore | liteparse | 170/170 (100.0%) | 170/170 (100.0%) | 17/17 (100.0%) | 23.41 |
| superstore | glm_task | 139/170 (81.76%) | 139/170 (81.76%) | 0/17 (0.0%) | 69.94 |
| overall | liteparse | 468/550 (85.09%) | 468/550 (85.09%) | 20/34 (58.82%) | 39.19 |
| overall | glm_task | 427/565 (75.58%) | 427/550 (77.64%) | 4/34 (11.76%) | 74.78 |

## Row counts, timing and field weighting

| Method | Same reference fields (all samples) | Extra rows | Missing rows | Mean per-invoice field accuracy | Mean elapsed seconds | Model calls | Load seconds | Inference seconds excluding load |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| liteparse | 548/635 (86.3%) | 0 | 0 | 91.05% | 39.75 | 40 | 49.88 | 1378.17 |
| glm_task | 502/635 (79.06%) | 5 | 2 | 79.68% | 74.74 | 323 | 876.57 | 1170.48 |

All-field accuracy counts missing fields/rows and adds five error slots per extra row. Same-reference accuracy uses identical expected-field denominators for both methods; extra rows remain reported separately. Complete-invoice accuracy requires every scored field correct and no extra rows. The mean per-invoice score weights each invoice equally; field-level accuracy gives larger invoices more weight.

Timings combine cached original-six measurements and fresh additional runs, not 40 freshly repeated measurements. Additional-only timings above are preferable for the expanded comparison. Single-run wall timings include model switches and loads; inference-only times sum Ollama durations excluding load. Failed samples count as incorrect in accuracy; successful-only timing means do not conceal the listed failures.

## Accuracy by structured field

These counts use expected fields only; extra rows are penalized separately in the all-field score.

| Field | LiteParse + Qwen | GLM task |
|---|---:|---:|
| customer_name | 33/40 | 39/40 |
| description | 60/87 | 42/87 |
| invoice_date | 37/40 | 38/40 |
| invoice_number | 34/40 | 40/40 |
| invoice_total | 39/40 | 40/40 |
| line_total | 83/87 | 81/87 |
| quantity | 69/87 | 68/87 |
| supplier_name | 40/40 | 39/40 |
| unit_of_measure | 70/87 | 34/87 |
| unit_price | 83/87 | 81/87 |

## Resolution and location diagnostics

Raw GLM-arm Qwen decisions before production table grounding: 543/660 (82.27%).
Diagnostic completed samples: 40.
Postprocessing correctness changes: {'correct_to_wrong': 65, 'wrong_to_correct': 24}.

LiteParse's retained word-box check covers only the original independently marked reference regions: 74/82 (90.24%) correct value plus location. The 34 additional samples contribute to value accuracy and retain extraction boxes, but have no independently marked geometry references. GLM supplies page evidence, so word-box accuracy is unavailable.

## Selection, scoring and privacy

Superstore eligible nonempty templates randomly sampled with seed 42. FTS first seventeen additional identifiable and legibly transcribable tax invoices in filename order, excluding DO/PO-only bundles and one ambiguous handwritten invoice before inference. Includes one two-page invoice. Not random FTS sampling.

Text matching ignores case, punctuation and layout whitespace. Numeric comparisons use decimal equality after rounding to two places. Full descriptions include relevant codes/continuations in the description column; separate item/code columns, accounting/project section headings and unrelated delivery notes are excluded. Null units remain null when unprinted. Printed discounted line amounts are scored against the source, separately from calculated quantity × unit price.

Before additional FTS inference, the shared scorer was corrected to deny null-cell credit for entirely missing rows and ignore CJK line-wrap spaces without ignoring character changes. Both corrections apply equally to both methods; original-six accuracy and all extraction prompts/settings are unchanged.

LiteParse uses 300-DPI local OCR and one text/coordinate Qwen request; GLM uses the existing document-mode adapter, 216-DPI OCR and Qwen images capped at 1280 pixels. Context/output settings remain 16384/4096 and 8192/2048 plus 18000/10000 respectively. Numeric GLM fields remain float/Optional[float]. Both use the same Qwen digest, temperature zero and seed 42; Qwen thinking is disabled.

Failures: {'liteparse': [], 'glm_task': []}.

All invoice content, references, requests, outputs and detailed mismatches remain local in ignored files. No production application files or state were changed. Full private details are in output/comparison_expanded/comparison.json, SUMMARY.md, glm_stage_comparison.json and method/sample directories.

The scripts/tests and exact execution commands are documented in README.md. Twenty invoices per type broaden this experiment, but related layouts, nonrandom FTS selection and a small invoice count still limit generalization.

## Interpretation of this run

LiteParse + Qwen was faster in the fresh additional cohort: 39.19 seconds per invoice versus 74.78 seconds, about 48% less elapsed time. For FTS alone the means were 54.97 versus 79.62 seconds. The eleven-row, two-page invoice was slower with LiteParse (132.36 versus 112.65 seconds), so fewer model calls do not guarantee a faster individual invoice. Model loading/switching is a substantial part of the GLM pipeline's wall time; its summed inference time excluding loading was actually lower.

LiteParse matched all structured fields on all twenty Superstore invoices. FTS remains mixed: LiteParse scored 80.00% versus GLM's 75.11% including extra rows, but over the same 435 expected FTS fields GLM scored 338/435 (77.70%). The difference on identical fields is therefore 2.30 percentage points. GLM extracted FTS headers more accurately (97% versus 83%) and produced more fully correct FTS invoices (6/20 versus 4/20). This does not establish a general FTS accuracy advantage for LiteParse.

Both methods mishandled quantity/unit separation in the two-page invoice despite returning all eleven rows. LiteParse retained combined quantity-and-unit text in the quantity field and left units empty; the final GLM task substituted currency markers for units and amounts for quantities. Raw Qwen in the GLM arm scored 94.29% on Superstore and 76.67% on FTS before postprocessing, compared with final scores of 78.10% and 75.11%. Pipeline postprocessing contributes materially to the observed difference, especially on Superstore.

These results support keeping a review gate for FTS extraction. The expanded value comparison supplies no new independently checked box references, so it does not establish that bounding boxes are reliable enough to guide approval.

## Verification for this run

```powershell
.\.venv\Scripts\python.exe -m pytest -q experimentd\test_expansion.py experimentd\test_comparison.py experimentd\test_experiment.py test\extraction\test_glm_ocr_adapter.py test\extraction\test_glm_ocr_adapter_complete.py
.\.venv\Scripts\python.exe -m experimentd.report_expanded
```

Focused verification: 110 tests passed; report generation succeeded. All 80 saved method/invoice runs passed source hash, page, model digest, prompt/settings and applicable adapter/version cache checks. All 363 recorded inference responses ended with `stop`, rather than an output-token-limit termination; this is not a claim that input context truncation was independently ruled out. The frozen expanded reference checksum and original-six references remained unchanged. Private manifests, source evidence and raw outputs are Git-ignored; repository changes are confined to `experimentd/`.

The full application suite, frontend build, Pyright and Ruff were not run for this standalone experiment.
