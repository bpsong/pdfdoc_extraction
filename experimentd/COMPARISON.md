# Local extraction comparison — 4 October 2026

This report covers the original six invoices. See
[the expanded comparison](EXPANDED_COMPARISON.md) for twenty invoices per type.

LiteParse + Qwen produced better final structured output on these six samples.
On the three FTS scans, however, the two methods tied: both got 50/55 fields
correct, with different errors. This does not establish that LiteParse's OCR is
generally more accurate than GLM-OCR.

Both methods processed the same three Superstore invoices and three FTS invoice
pages locally, using the same installed `qwen3.5:9b-q4_K_M` model. No invoice
content was sent to an internet service. The GLM arm uses the existing production
`GlmOcrAdapter` in document mode, including its image resolver and table handling.
Production files, workflow configuration and databases were unchanged.

| Samples | LiteParse + Qwen | Existing GLM-OCR + Qwen task |
|---|---:|---:|
| Superstore (3) | 30/30 — 100% | 25/40 — 62.5% |
| FTS (3) | 50/55 — 90.91% | 50/55 — 90.91% |
| Combined | 80/85 — 94.12% | 75/95 — 78.95% |

The different denominators are deliberate: GLM returned two extra rows for
discount/shipping in one Superstore invoice's totals section. They were outside
the reference item table and add ten incorrect field slots. On the **same 85
reference fields**, GLM got 75/85 (88.24%) correct before the extra-row penalty.
Paired results were 72 fields correct in both, eight correct only with LiteParse,
three correct only with GLM, and two wrong in both. No samples failed.

## What differed

GLM got all 30 header fields correct, versus LiteParse's 28/30. On FTS it recovered
the date, invoice number and unit that LiteParse missed. However, GLM omitted
continuation/OFFER lines from five descriptions in the six-row FTS sample and
included row numbers in those descriptions. LiteParse preserved more of that
text, but still had two incorrect descriptions. Both methods got quantity,
unit price and printed line total correct for all eleven reference item rows.

The GLM task's postprocessing also affected accuracy. Recorded raw Qwen decisions
scored 78/95 (82.11%), including the same two extra rows. Subsequent normalization/
table grounding changed **five correct fields to incorrect and two incorrect
fields to correct**. The regressions were Superstore descriptions and invented
units: the grounding step shortened descriptions and filled null units from
GLM candidates. The two improvements restored FTS units. The FTS description
omissions were already present in raw Qwen output in this final run.

Therefore, the result supports LiteParse as a useful local alternative and
identifies the existing GLM task's table-grounding behavior as a separate issue
to investigate. It does not justify replacing the production task based on six
samples alone.

## Bounding boxes and latency

LiteParse's correct-value-plus-location score was 74/82 present fields (90.24%):
26/27 for Superstore and 48/55 for FTS. Pure location accuracy was 78/82 (95.12%).
These are actual parser word rectangles selected through source IDs. The metric
checks containment within manually reviewed regions; it does not measure tight
pixel IoU or complete word coverage. Overlays remain useful review aids, but this
result does not support treating every highlight as verified evidence.

The existing GLM adapter supplies page references rather than word boxes. Its
word-box accuracy is unavailable, so there is no direct geometry comparison.

| Timing across six invoices | LiteParse | GLM task |
|---|---:|---:|
| Total elapsed | 257.57 s | 446.91 s |
| Mean elapsed per invoice | 42.93 s | 74.49 s |
| Model calls | 6 | 48 |
| Total Ollama model-load time | 16.40 s | 130.48 s |
| Total Ollama inference excluding load | 215.37 s | 177.72 s |

LiteParse was about 42% faster in measured wall time. GLM's repeated model
switches/loading contributed substantially; its summed inference time excluding
load was lower. These are single runs on this machine, not averaged benchmarks.

## Controls, scripts and verification

References were frozen before comparison and were unchanged afterward. FTS tax
invoice pages were selected manually from mixed document bundles. Text scoring
ignores case, punctuation and layout whitespace; numbers use exact decimal
equality. Complete description continuations, absent units, missing/extra rows
and failures count toward accuracy. Printed amounts are preserved separately
from calculated quantity × price, including the original 0.01 discrepancy.

This compares practical pipelines with different input/prompt paths: LiteParse
uses local OCR at 300 DPI and text/coordinates; GLM uses 216-DPI OCR images and
Qwen images limited to 1280 pixels. Context/output limits are 16384/4096 for
LiteParse's Qwen and 8192/2048 plus 18000/10000 for the GLM/Qwen stages.
Temperature is zero, thinking is disabled for Qwen and seed 42 is supplied.
GLM numeric fields use `float`/`Optional[float]`. An initial string-typed numeric
trial was preserved privately and excluded from these results.

New comparison scripts are `compare_methods.py` (runner/scorer),
`glm_comparison.py` (production-adapter wrapper/recording client),
`trace_glm_stages.py` (raw versus final diagnostic) and `test_comparison.py`
(synthetic tests). See [README.md](README.md) for commands. Private model calls,
values, frozen references, mismatches, timings and overlays are in ignored
`output/comparison/`; its `SUMMARY.md` contains the generated detailed report.

Commands run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m experimentd.compare_methods
.\.venv\Scripts\python.exe -m experimentd.compare_methods --methods glm_task --resume
.\.venv\Scripts\python.exe -m experimentd.compare_methods --report-only
.\.venv\Scripts\python.exe experimentd\render_overlays.py --output experimentd\output\comparison\liteparse
.\.venv\Scripts\python.exe -m pytest -v experimentd\test_comparison.py experimentd\test_experiment.py test\extraction\test_glm_ocr_adapter.py test\extraction\test_glm_ocr_adapter_complete.py
```

All twelve final method/sample extractions completed without token-limit
termination. The focused experiment and adjacent adapter tests passed:
**103 passed**. Full application tests, frontend build, Ruff and Pyright were
not run for this isolated experiment. Private invoice artifacts are ignored by
Git; no production files were changed.

These are deliberately selected samples and tuned prompts, not a held-out or
random production benchmark. Rotated/multipage invoices and automatic document
classification were not tested.
