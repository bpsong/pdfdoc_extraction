# GLM-OCR + Qwen Page Vision Experiment

This experiment tests whether table and document extraction improves when Qwen
receives each rendered PDF page together with a verbatim GLM-OCR transcription.
It does not modify the production pipeline.

The runner performs three stages:

1. Render every PDF page and ask GLM-OCR for a layout-preserving transcription.
2. Send each page image and its GLM-OCR text to Qwen for structured page analysis.
3. Ask Qwen to reconcile all page results into one document-level result.

Run from the repository root with the project virtual environment:

```powershell
.\.venv\Scripts\python.exe experimenta\run_glm_qwen_vision_experiment.py
```

Use `--think` to test Qwen thinking mode as a separate variable. The default is
thinking disabled so the first run differs from production mainly in the table
resolver's access to page images and page-specific OCR text.

Thinking mode automatically raises Qwen's generation budget from 3072 to 22000
tokens and the context window from 16384 to 32768 because reasoning tokens share
the same budget as the final JSON. Override these explicitly with
`--qwen-num-predict` and `--qwen-num-ctx` when testing other limits.

Use `--resume` after an interrupted run to reuse completed GLM transcriptions and
Qwen page-result files from the selected output directory.

Use `--qwen-only` for a vision-only control run. This skips GLM-OCR completely
and sends each page image directly to Qwen before the same final reconciliation:

```powershell
.\.venv\Scripts\python.exe experimenta\run_glm_qwen_vision_experiment.py `
  --qwen-only `
  --output-dir experimenta\results\S268588_1781061_qwen_only
```

Generated customer data is written under `experimenta/results/`, which is
ignored by Git.

## Reproducible 40-PDF comparison

The batch harness freezes a seeded sample of 10 FTS PDFs and 30 Superstore PDFs,
then runs both non-thinking methods with page- and document-level checkpoints:

```powershell
.\.venv\Scripts\python.exe experimenta\run_batch_40_comparison.py --stage all
.\.venv\Scripts\python.exe experimenta\analyze_batch_40_comparison.py
```

`run_batch_40_comparison.py` resumes from completed artifacts automatically.
Use `--stage glm`, `--stage glm_qwen`, or `--stage qwen_only` to run or resume a
single stage. The analysis command writes the Markdown report, a paired
comparison index, and one aggregate JSON file per method under
`experimenta/results/batch_40_comparison/`.
