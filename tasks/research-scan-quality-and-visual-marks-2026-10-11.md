# Scan-quality and visual-mark feasibility

| Item | Value |
| --- | --- |
| Audience | Product owners, maintainers, developers and IT support |
| Owner | Application maintainers |
| Status | Local scan-quality checks and Azure integration accepted as lower-priority R7/R8; detailed design and implementation remain pending |
| Researched | 2026-10-11 |
| Method | Official library/provider documentation, repository inspection, installed-package inspection, and an in-memory synthetic experiment |
| Limits | No customer documents, live AI/provider calls, model accuracy benchmark, dependency changes, or production implementation |

## Assessment

Local scan-quality checks are feasible with existing Python libraries. Start
with page-level advisory measurements using PyMuPDF and OpenCV/NumPy. The app
already pins PyMuPDF; OpenCV and NumPy would need explicit runtime dependency
decisions before production use. More demanding checks such as glare, missing
content, and unreadable handwriting require further evaluation.

AI can detect checkbox states and signature presence. Azure documents dedicated
capabilities; a local vision model is another approach to evaluate. Image input
alone does not establish adequate accuracy for the app's specific documents.
Use explicit uncertainty and review evidence. Signature presence is a visual
extraction result, not verification of signer identity or authenticity.

Named users have been accepted separately as [roadmap R6](roadmap.md#r6-named-users-and-role-based-access).
Local scan-quality checks are accepted as lower-priority
[roadmap R7](roadmap.md#r7-local-scan-quality-checks), and optional Azure analysis
including checkbox/signature-presence fields as lower-priority
[roadmap R8](roadmap.md#r8-azure-document-intelligence-integration).
Alternative local visual-mark detectors remain research candidates.

## Current repository and environment

- `requirements.txt` pins `PyMuPDF==1.28.0`, already used to render PDF pages in
  [the GLM adapter](../standard_step/extraction/glm_ocr_adapter.py).
- NumPy is installed locally (`2.3.5`) but not explicitly pinned as a direct
  runtime dependency. Pillow is pinned in `requirements-dev.txt` (`12.3.0`),
  not in the runtime manifest; production features cannot assume dev packages.
- OpenCV imports successfully here. Package metadata reports
  `opencv-python-headless==5.0.0.93`, while `cv2.__version__` reports `4.10.0`.
  Neither OpenCV distribution is explicitly pinned in the runtime manifest.
  A clean, supported Python 3.13 install must resolve this environment mismatch
  and verify the chosen package before shipping; this experiment establishes
  only local feasibility.
- `pytesseract` is not installed. Its native Tesseract executable was not
  inspected. Adding it is optional, not a prerequisite for basic image checks.
- The GLM adapter sends rendered page images to Ollama. The current
  [LiteParse adapter's structured extraction call](../standard_step/extraction/liteparse_adapter.py)
  sends parsed text without an image array. Parsed text might retain some marks,
  but this path cannot be relied on to inspect handwriting or visual marks
  omitted by parsing.

## Scan-quality checks with Python

The proposed measurements below are engineering options inferred from library
primitives, not claims that those libraries provide a complete document-quality
classifier.

| Check | Libraries and approach | Practical limit |
| --- | --- | --- |
| PDF readability and bounded rendering | PyMuPDF opens the PDF and renders pages/crops in grayscale at a controlled DPI | Rendering success does not establish legibility; impose page/pixel/time limits |
| Effective scan resolution | PyMuPDF image dimensions and placement transform estimate pixels per displayed inch | Render DPI is not source scan DPI; account for rotation, scaling, tiles, and mixed text/image pages |
| Blur/sharpness | OpenCV Laplacian or gradient measurements, summarized with NumPy over content regions | Resolution, contrast, noise, graphics, and text size affect scores; no universal cutoff |
| Faint text/low contrast | NumPy grayscale histograms and local contrast; Pillow ImageStat is an alternative | Global statistics can conceal a faded field on an otherwise clear page |
| Near-blank pages | Thresholded foreground coverage and content-region checks | Blank separators and sparse signature pages may be valid; do not delete automatically |
| Small skew | OpenCV line detection or text-region angle estimates | Table borders/photos can dominate; distinguish small skew from upside-down text |
| 90/180-degree orientation | Optional pytesseract orientation/script detection, or an evaluated existing OCR result | Requires Tesseract plus language/OSD data; sparse pages can be inconclusive |
| Glare, shadows, cutoff, perspective | Local brightness/region geometry can flag candidates; richer models may help | A white background is not glare, and an apparently clean crop cannot prove nothing is missing |

Primary references: PyMuPDF [page rendering](https://pymupdf.readthedocs.io/en/latest/recipes-images.html)
and [image metadata/placement](https://pymupdf.readthedocs.io/en/latest/page.html#Page.get_image_info),
OpenCV [Laplacian](https://docs.opencv.org/4.x/d5/db5/tutorial_laplace_operator.html),
[thresholding](https://docs.opencv.org/4.x/d7/d4d/tutorial_py_thresholding.html),
and [line detection](https://docs.opencv.org/4.x/d9/db0/tutorial_hough_lines.html),
Pillow [image statistics](https://pillow.readthedocs.io/en/stable/reference/ImageStat.html),
and pytesseract [orientation and OCR data](https://github.com/madmaze/pytesseract).
Tesseract is an external executable; installing its Python wrapper alone is
insufficient. OCR confidence is a useful additional signal, not a calibrated
probability of extraction correctness.

### Local feasibility experiment

Ran an inline PowerShell here-string through `.\.venv\Scripts\python.exe -`.
Created an in-memory 595-by-842-point PDF with 24 synthetic invoice text lines,
rendered grayscale at 150 DPI, then compared the original render with Gaussian
blur (15-by-15 kernel, sigma 3), faded contrast (`0.15 * pixels + 215`, rounded),
and a white page. No files, external services, or customer content were used.

| Synthetic image | Laplacian variance | Grayscale standard deviation |
| --- | ---: | ---: |
| Sharp render | 3344.877 | 38.307 |
| Blurred render | 1.865 | 19.776 |
| Faded render | 75.018 | 5.701 |
| Blank page | 0.000 | 0.000 |

Assertions confirmed blur reduced the sharpness metric, fading reduced contrast,
and a white page had zero Laplacian variance. This verifies the local render and
measurement path, not real-world detection accuracy. Both fading and blur lower
the sharpness score, illustrating why a single metric cannot identify the cause
or decide whether a page should be rejected.

### Suggested initial implementation

1. Run an optional preflight before costly extraction, reusing suitable rendered
   pages where possible and bounding memory/time. Evaluate each page and relevant
   content regions; report unavailable/inconclusive checks explicitly. Do not
   treat a born-digital text page as a low-resolution scan because of its logo.
2. Record page number, warning code, measured values, evaluation version, and
   actionable guidance. Show a warning or route to review under configured
   policy; preserve the original. Register any durable derivative artifacts.
3. Calibrate profiles using synthetic degradations and approved representative
   documents at consistent render settings. Measure false alarms and missed
   unreadable fields, including faint stamps, small print, table-heavy pages,
   sparse pages, and mixed scans. Agree latency/memory limits before release.
4. Introduce blocking/rescan policies only after evidence supports them. Quality
   checks cannot reconstruct absent information. Deskew/contrast enhancement is
   a separate opt-in transformation and must preserve source-page lineage.

## Checkbox and signature-presence detection

### Documented AI capabilities

Azure's [layout model](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0#selection-marks)
returns selection marks with selected/unselected states, bounding polygons, and
confidence. Associating a mark with the correct question/option remains a field
mapping/layout problem. Crossed-out options and conflicting marks need policy
and review.

Azure's [custom neural model](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/train/custom-neural?view=doc-intel-4.0.0#signature-detection)
documents signature detection in v4.0, with signature regions labelled during
training. It specifies at least five signature-labelled samples with variation
to start training. This is a custom model capability, not a promise that the
generic layout endpoint detects every signature without training. Training
minimums do not establish sufficient accuracy for this app's documents.

The [model overview](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/model-overview?view=doc-intel-4.0.0)
explicitly distinguishes signature presence from signer identity. A copied
signature image can appear present. Cryptographic PDF signature validation is
a separate capability from detecting handwritten-looking ink on a scanned page.

### Local AI feasibility and current adapters

[Ollama vision](https://docs.ollama.com/capabilities/vision) supports image inputs
for visual questions. A candidate implementation can render/crop the relevant
region and request a structured mark result from an evaluated vision model.
This is a feasible experiment, not a measured capability of every model.

The official [GLM-OCR model card](https://huggingface.co/zai-org/GLM-OCR) documents
text/formula/table parsing and structured information extraction, with constrained
prompt formats. It does not document a dedicated checkbox-state or signature
detector in the reviewed card. The current image-capable adapter is a useful
starting point, but validate GLM-OCR on labelled examples before relying on it.
A different locally hosted vision model or specialized detector may be needed.
No local model inference or cloud-provider calls were performed for this report.

For fixed forms, a simpler OpenCV approach can locate known checkbox regions and
compare interior ink/connected components after alignment. This is an engineering
option to evaluate; variable positions, handwriting crossing borders, and erased
marks reduce reliability. Signature-region ink alone cannot reliably distinguish
a signature from a stamp, printed name, or incidental scribble.

For interactive PDFs, inspect [PDF widgets](https://pymupdf.readthedocs.io/en/latest/widget.html)
first: checkbox form fields expose values and on/off states without visual AI.
Scans/flattened forms require visual analysis. A signature field's existence
alone does not establish a visible signature or a valid digital signature.

### Output and review design

- Bind each result to a semantic field, such as `terms_accepted` or
  `recipient_signature`, and preserve the original page/region reference.
- Use explicit `selected / unselected / uncertain` and
  `present / absent / uncertain` states. Track not-applicable separately;
  missing, unreadable, and detector failure must not become false/absent.
  Export accepted booleans only after resolving required uncertainty, with a
  documented null/status contract for optional unresolved fields.
- Record model/configuration version, source artifact, region, provider scores
  where available, and audited reviewer corrections. Do not present an LLM's
  invented numeric confidence as calibrated probability. Expose the source crop
  to reviewers; do not release a required result based only on a signature label
  or an extracted person's name.
- Let configured R4 rules check required selections/signature presence and let
  R5 deliver the accepted result. The detection itself belongs in extraction;
  the business requirement belongs in validation/review.
- Evaluate marked/unmarked/ambiguous boxes, tick and X styles, faint ink, multiple
  options, skew, small regions, unsigned lines, printed names, stamps, typed
  signatures, and signature images. Define which forms of signature count for
  the business. Measure false-present and false-absent rates on held-out examples.

## Product decision and recommendation

The maintainer accepted local scan-quality checks and optional Azure Document
Intelligence integration into the roadmap on 2026-10-11, both at lower priority
than R1-R6. The findings below guide their detailed design; no runtime integration
or detector has been implemented by this documentation work.

Scan-quality warnings are a practical local addition if poor scans regularly
consume operator time. PyMuPDF plus an explicitly supported OpenCV/NumPy runtime
is a reasonable first option; an external AI service is not required for the
initial checks. Treat richer quality classification as a separate evaluation.

Checkbox/signature presence is useful when actual target documents require
those fields. Start with a labelled proof of concept on those document types,
comparing the local vision path with a documented specialist provider if cloud
use is appropriate. Keep signature authenticity and digital-signature validation
outside this presence-detection proposal.

Return to the [feature assessment](research-extraction-product-features-2026-10-11.md)
or [agreed roadmap](roadmap.md) for prioritization.
