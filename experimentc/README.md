# PaddleOCR-VL-1.6 invoice experiment

## Qianfan-OCR via Ollama

`extract_invoice_qianfan.py` is standalone and uses the local Ollama API with
`maternion/Qianfan-OCR:4b`. It renders the SuperStore PDF to page images and
requests invoice fields and line items directly from Qianfan, without a second
model. No PyTorch or PaddlePaddle is required for this script; dependencies are
covered by `experimentc/requirements.txt`.

```powershell
ollama pull maternion/Qianfan-OCR:4b
.\.venv\Scripts\python.exe experimentc\extract_invoice_qianfan.py
.\.venv\Scripts\python.exe experimentc\extract_invoice_qianfan.py --mode markdown --output experimentc\output\qianfan-markdown
```

Default results go to `output/qianfan/`: raw Ollama responses, per-page invoice
JSON, `invoice.json` for a single page and run metadata. Multi-page documents
produce `page_invoices.json`; pages are not automatically combined into one
invoice. Missing fields use null; printed values use strings. Validation checks
JSON shape, not accuracy. Thinking is disabled and the context is set to 8192
tokens to limit memory use. Options include PDF path, `--mode`, `--output`,
`--model`, `--host`, `--dpi`, `--timeout` and `--max-tokens`.
Use separate output folders for modes/runs to avoid mixing old results.
`run.json` includes `page_timings` (Ollama total, loading, prompt/image processing
and generation in seconds) and `inference_excluding_load_seconds` across pages.
These are single-run measurements, not warm-up/averaged benchmarks.

A three-page scanned FTS document completed in 51.16 seconds end to end and
47.186 seconds of Ollama request time excluding loading. Results demonstrated
table-row extraction but missing quantities, misread identifiers, and incorrect
document-role mapping when purchase/delivery orders were forced into the invoice
schema. This script keeps pages separate and does not classify document types or
deduplicate repeated items across related documents. Such classification and
reconciliation are needed before using mixed-document batches operationally.
The [community Ollama package](https://ollama.com/maternion/Qianfan-OCR:4b)
includes Q8_0 weights and an F16 vision projector, about 5.3 GB in total.

## TeleOCR native experiment

`extract_invoice_teleocr.py` runs the original TeleOCR weights with Transformers
on CUDA in FP16, using the model card's text-recognition prompt. It renders PDF
pages with PyMuPDF and saves raw page JSON, OCR text and timing/memory metadata.
This is full-page recognition, not TeleOCR's official layout-and-region pipeline,
and does not perform named invoice-field extraction.

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu126
.\.venv\Scripts\python.exe -m pip install -r experimentc\requirements-teleocr.txt
.\.venv\Scripts\python.exe experimentc\extract_invoice_teleocr.py
```

Installed in the repository environment: torch 2.8.0+cu126, torchvision
0.23.0+cu126, Transformers 4.57.1 and Accelerate 1.14.0. This replaced CPU-only
torch 2.13.0, torchvision 0.28.0 and Transformers 5.15.0; huggingface-hub was
changed from 1.27.0 to 0.36.2. `pip check` passed afterward.

The model revision is pinned to `e92585356c0d0b7b7a65938f3da035c6593cc9a6`.
Loading uses the repository's custom model code (`trust_remote_code=True`).
First run downloads model weights. Options include PDF path, `--output`,
`--dpi`, `--max-pixels`, `--max-tokens` and `--prompt`.

### Observed SuperStore result

The initial live run on RTX 2060 SUPER completed in 290.23 seconds including
52.68 seconds of loading, with 237.12 seconds of generation and 3172.2 MB peak
allocated GPU memory. Raw output is in `output/teleocr/`. Recognition failed:
invoice number 36258 appeared 192 times, the address was repeated, and the
customer name, date, item code, item amount, total and order ID were absent.
This shows runtime compatibility for this test, not useful invoice accuracy.
The script now flags obvious repeated-line loops as invalid while preserving
raw output. The quality-check change is unit-tested; the failed initial raw
generation was not rerun after adding that check.

The [official model card](https://huggingface.co/XingChen-AGI/TeleOCR) provides
element-recognition prompts and links to the separate full parsing pipeline.
Its [pipeline package](https://github.com/caipeng328/TeleOCR/blob/main/pyproject.toml)
excludes Python 3.13 and includes vLLM dependencies, so that package was not
installed. The linked [community GGUF conversion](https://huggingface.co/nandraj/NaviDC-OCR-GGUF)
requires patched llama.cpp; stock Ollama compatibility remains unverified.

## Full native PDF pipeline

`extract_invoice_pipeline.py` is a second, standalone experiment using
`PaddleOCRVL(pipeline_version="v1.6")`. It performs layout analysis and region
recognition, exports each page, then consumes and saves the restructured results
with cross-page table merging and page concatenation enabled. It uses neither
Ollama nor Qwen. Its JSON contains document blocks and tables, not a named
invoice-field schema.

The optional pipeline packages were installed in the repository environment
(PaddleOCR 3.7.0, PaddleX 3.7.2, PaddlePaddle GPU 3.2.2). PaddlePaddle's GPU
self-check passed on the RTX 2060 SUPER, and `pip check` reported no broken
requirements. The following commands describe installation on a fresh environment.
Install either the GPU or CPU PaddlePaddle package, then the experiment extras.
The following GPU version is listed in PaddlePaddle's Windows installation guide:

```powershell
.\.venv\Scripts\python.exe -m pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
.\.venv\Scripts\python.exe -m pip install -r experimentc\requirements-pipeline.txt
.\.venv\Scripts\python.exe -c "import paddle; paddle.utils.run_check()"
.\.venv\Scripts\python.exe experimentc\extract_invoice_pipeline.py
```

For CPU, install `paddlepaddle==3.3.0` using
`https://www.paddlepaddle.org.cn/packages/stable/cpu/` instead of the GPU package,
then run the script with `--device cpu`. Do not install both PaddlePaddle variants.
These install commands modify the target environment; a dedicated environment is
preferable for a longer experiment to avoid application dependency conflicts.
The standalone manifest pins the tested PaddleOCR and PaddleX versions.
Transitive packages are not fully locked.

The default PDF is the existing SuperStore sample. An explicit PDF path works
when this folder is moved elsewhere. First execution downloads native pipeline
models independently of the Ollama GGUF and may take extra time.

```powershell
.\.venv\Scripts\python.exe experimentc\extract_invoice_pipeline.py "path\to\invoice.pdf" --output experimentc\output\pipeline-other
```

Results are saved under `experimentc/output/pipeline/pages/` and `merged/`, with
runtime metadata in `run.json`. Use a fresh output directory for each comparison
to avoid retaining files from an earlier, longer document. Optional flags:
`--orientation`, `--unwarp`, `--no-merge-tables`, and `--device cpu`.
Native GPU inference completed on this machine after disabling worker queues
(`use_queues=False`). The initial default queued run failed with a cuBLAS
execution error; the CPU fallback was stopped to retry GPU serially. The runtime
still warns that its compiled cuDNN version is 9.9 while the package dependency
installs 9.5. The successful one-page run does not resolve that warning or
establish reliability on other documents.

Markdown header filtering is disabled (`markdown_ignore_labels=[]`) so seller
names classified as headers remain in the export. The first successful sample
recognized the item table and financial totals, but omitted Ship Mode and
Balance Due from raw JSON. It also combined Bill To/Ship To into a text block.
Inspect raw page JSON as well as Markdown when judging field accuracy. Tests
use synthetic pipeline results and do not download models.

## Ollama recognition experiment

This standalone script imports no application modules and reads no application
configuration or database. It renders PDF pages to PNG with PyMuPDF, sends each
page to your local Ollama PaddleOCR model with `OCR:`, saves the raw recognition,
then uses the already-installed `qwen3.5:9b-q4_K_M` to structure invoice JSON.
The JSON is therefore a **PaddleOCR + Qwen** result, not PaddleOCR alone.
Use `--ocr-only` to evaluate PaddleOCR independently. Neither stage reads the
PDF's embedded text layer. No cloud API or credentials are required.

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe experimentc\extract_invoice.py
.\.venv\Scripts\python.exe experimentc\extract_invoice.py "path\to\invoice.pdf" --output experimentc\output\another
.\.venv\Scripts\python.exe experimentc\extract_invoice.py --ocr-only
```

The default input is the existing SuperStore invoice
`sample stock invoices from internet/invoice_Aaron Bergman_36258.pdf`.
It is referenced, not copied. When moving this folder elsewhere, supply a PDF
path explicitly. The folder's requirements.txt documents its standalone
dependencies; these packages are already present in the repository environment.
Ollama must be running with the OCR model installed; the JSON stage also needs
the extraction model (override with `--extract-model`).

Outputs under ignored `experimentc/output/`:

- `ocr.md`: raw OCR, with page boundaries.
- `page_001_response.json` etc.: complete Ollama OCR responses and timing data.
- `extraction_response.json`: complete structuring response.
- `invoice.json`: schema-validated fields and line items, printed values as
  strings, missing fields as null.
- `run.json`: models, source path, rendering DPI, page count and elapsed time.

Output is overwritten on repeated runs; use a different `--output` for comparisons.
Options include `--dpi`, `--timeout` (seconds per HTTP request), `--max-tokens`,
`--model`, `--host`, and `--ocr-prompt`. Truncated generations fail rather than
being accepted as complete. Completed raw responses remain available on failure.
JSON schema validation verifies shape, not recognition accuracy. Review against
the original invoice, especially totals and item count. Multi-page PDFs are
recognized page by page and structured together; very long documents may exceed
the structuring model's context window.

## Qianfan targeted prompt experiment

`extract_invoice_qianfan_prompt.py` is standalone and sends page images with a
natural-language field/column extraction prompt, without a JSON schema or a
second model. It defaults to the SuperStore sample and supports multi-page PDFs.

```powershell
.\.venv\Scripts\python.exe experimentc\extract_invoice_qianfan_prompt.py
.\.venv\Scripts\python.exe experimentc\extract_invoice_qianfan_prompt.py "path\to\invoice.pdf" --prompt "OCR the image and extract Description, Quantity, Rate and Amount columns."
```

Results go to `output/qianfan-prompt/`: `extraction.md`, per-page Markdown,
complete raw API responses and `run.json` containing the exact prompt and
timings. Output text is preserved even when the model returns HTML tables instead
of requested Markdown. Use `--output` to retain separate runs. Timings excluding
load subtract Ollama's reported load duration; they are not a separate warmed run.
No PDF text layer is supplied to the model.

The initial sample run recovered quantity and printed monetary amounts, but had
identifier errors, invented an absent tax value, and split category/product-code
text into an extra row. Review the raw output before using it as structured data.

## FTS targeted prompt experiment

`extract_fts_qianfan_prompt.py` is a standalone variant for mixed invoice,
delivery-order and purchase-order pages. It defaults to the existing three-page
FTS sample. Its prompt requests document types, separately labelled references,
supplier/customer roles and all line-item columns. Each page is processed
independently; results are not merged or deduplicated across document types.

```powershell
.\.venv\Scripts\python.exe experimentc\extract_fts_qianfan_prompt.py
.\.venv\Scripts\python.exe experimentc\extract_fts_qianfan_prompt.py "path\to\another.pdf" --output experimentc\output\fts-another
```

Outputs are saved under `output/qianfan-fts-prompt-short/` with the same raw response,
Markdown and timing files as the SuperStore prompt experiment. The script imports
no other experiment or application modules. `--prompt` overrides the default
prompt. Output columns and values still require source-image verification.

The completed three-page run took 33.02 seconds end to end and 29.375 seconds
after subtracting reported model loading. All ten quantities, unit prices and
amounts were correct on each of the two item-table pages. Totals and party roles
were recovered, but references, postcode and delivery-order product codes still
had errors. The first, longer prompt returned empty text on the last page and
misaligned weight/price columns; its partial outputs remain in the separate
`output/qianfan-fts-prompt/` folder. The current shorter prompt includes Weight
explicitly to preserve the delivery-order table's column alignment.

## Qianfan layout-thinking experiment

`extract_invoice_qianfan_layout.py` defaults to SuperStore and uses the Ollama
package's documented `OCR the image and output in Markdown.<think>` prompt with
`think: true`. It preserves the complete API response, including the separate
thinking channel, in `output/qianfan-layout/page_001_response.json`.
`page_001_boxes.json` reports explicit `<box>...</box>` coordinate entries found
in either response channel. This detector does not count arbitrary invoice
numbers as coordinates. Raw responses remain available for other box formats.
Coordinates are checked against the paper's 0-999 convention, not assumed to
be pixels. Detection does not establish geometric accuracy or field-level boxes.

```powershell
.\.venv\Scripts\python.exe experimentc\extract_invoice_qianfan_layout.py
```

Both SuperStore tests returned thinking and OCR content but no layout boxes:
the documented prompt and a second prompt explicitly requesting normalized
coordinates. The documented-prompt run took 113.95 seconds with a 32768 context
that caused CPU offload. The explicit-prompt run took 27.54 seconds overall,
13.998 seconds excluding model loading, using an 8192 context. The script now
defaults to 8192 context and a 4096 output-token limit. The second run is preserved
under `output/qianfan-layout-explicit/`. This does not confirm bounding-box
functionality in this Ollama conversion; it also does not disprove the native
model's documented layout capability.

## Research

- [Official model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF):
  documents Ollama installation and element recognition prompts including
  `OCR:` and `Table Recognition:`. This model is a specialized recognizer;
  arbitrary invoice JSON prompting is not its documented interface.
- [Ollama chat API](https://docs.ollama.com/api/chat): supports image-bearing
  messages, nonstreaming responses and JSON schema output.
- [PaddleOCR pipeline documentation](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PaddleOCR-VL.html):
  the full PaddleOCR pipeline adds layout analysis and region recognition.
  This lightweight full-page Ollama experiment does not reproduce that pipeline
  or its benchmark performance. If small text or tables are weak, compare a
  dedicated table crop using `Table Recognition:` or the official pipeline next.
