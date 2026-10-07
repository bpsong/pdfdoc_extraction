# LiteParse + Ollama extraction

`standard_step.extraction.liteparse_extract.LiteParseExtractTask` is an approved
standard task for configurable local PDF extraction. It follows the shared task
contract, persists provider-neutral results and fields in SQLite, and works with
the existing review gate and JSON/CSV storage tasks. It does not import code from
the `experimentd` benchmark.

LiteParse reads embedded text from generated PDFs and uses local Tesseract OCR
for scanned pages. One Ollama request structures the selected document's text
and word coordinates. The default model is `qwen3.5:9b-q4_K_M`; another installed
instruction model may be configured. The model must be a downloaded local GGUF;
cloud-backed Ollama models are rejected before document text is submitted.
PDF content is not sent to a cloud service.
Only credential-free HTTP loopback Ollama endpoints are accepted; redirects,
environment proxies and remote OCR servers are disabled.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `fields` | Required | Shared extraction definitions with aliases, types and guidance |
| `document_instructions` | Empty | Guidance for this document type; no built-in invoice assumptions |
| `ollama_host` | `http://127.0.0.1:11434` | Local Ollama base URL |
| `model` | `qwen3.5:9b-q4_K_M` | Installed Ollama model |
| `ocr_enabled` | `true` | Enable local OCR when needed |
| `ocr_language` | `eng` | Tesseract language(s); corresponding data must be installed |
| `target_pages` | Empty | All source pages, or one-based ranges such as `1-3,5` |
| `dpi` | `300` | Local OCR rendering resolution, 72–600 |
| `num_ctx` | `32768` | Ollama context allowance |
| `num_predict` | `4096` | Output-token allowance, smaller than `num_ctx` |
| `timeout_seconds` | `600` | Hard parser deadline in an isolated worker and HTTP timeouts |
| `max_input_characters` | `60000` | Upper bound for parsed document evidence |

Supported fields follow the existing extraction contract: typed scalars,
optional scalars, typed primitive lists, flat objects and one array-of-objects
table. Up to 100 top-level fields are supported. String choices, schema ordering
and ISO date normalization use shared validation and normalization helpers.
Aliases describe labels/output names; configured field keys remain stable for
review and downstream tasks.

## Visual setup

Install runtime dependencies with the repository virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Check that local Ollama is running and the configured model is installed:

```powershell
ollama list
```

If the model is absent, download it once during setup:

```powershell
ollama pull qwen3.5:9b-q4_K_M
```

Model installation can require Internet access; invoice/document contents are
not involved in that download. Start Ollama with its desktop application or
`ollama serve` if no server is already running. This application does not start
Ollama or pull models automatically. Scanned pages also need working local OCR
and the language data named by `ocr_language`.

In **Admin → Pipeline**, create a
new template and add **Lite Parse Extract**, **Review Gate**, then **Store Metadata
As Json**. Configure fields in the LiteParse step, including table row fields
through the schema drawer. Configure the review step with an exact published
review form version whose keys match the extraction fields. Set its review scope
to document if every field should remain editable. Configure a JSON output
directory and `{id}` filename; JSON preserves table rows and corrected values.
Save, validate, publish, activate, then select that pipeline version at upload.

The task is generic. For example, a shipping manifest can configure a reference,
destination object and package table; a contract can configure parties, dates,
amounts and a list of obligations. Invoice-specific instructions belong in the
pipeline, rather than the task implementation.

### Generic parameter example

The following is a **task parameter fragment** for **Advanced params JSON** in
the LiteParse step, not deployment YAML or a complete portable pipeline. It
extracts a manifest reference, destination and package table. Use identical keys
and compatible types in the separately published review form:

```json
{
  "model": "qwen3.5:9b-q4_K_M",
  "document_instructions": "Extract the manifest reference, destination and every package row in source order. Preserve printed identifiers and quantities.",
  "fields": {
    "reference": {
      "type": "str",
      "alias": "Manifest reference",
      "description": "Printed manifest reference, including leading zeros."
    },
    "destination": {
      "type": "Dict[str, Any]",
      "alias": "Destination",
      "object_fields": {
        "name": {"type": "str", "alias": "Name"},
        "city": {"type": "Optional[str]", "alias": "City"}
      }
    },
    "packages": {
      "type": "List[Any]",
      "is_table": true,
      "alias": "Packages",
      "item_fields": {
        "description": {"type": "str", "alias": "Description"},
        "quantity": {"type": "Optional[float]", "alias": "Quantity"},
        "unit": {"type": "Optional[str]", "alias": "Unit"}
      }
    }
  }
}
```

Omitted runtime parameters use the defaults above. Configure the review gate
and storage as separate steps, then save, validate and publish the pipeline.
For a wholly local workflow, choose local tasks for the other steps too; adding
a LlamaCloud extraction or split task sends its own input to that service.

## Review and source evidence

No numeric confidence is supplied or invented. Fields initially have null
confidence; the task emits `liteparse_unscored` with configured top-level keys.
When a review gate follows extraction, that structured flag sends all configured
fields for review. Without a gate, extraction and storage still run normally.

Model-selected element IDs resolve only to coordinates returned by LiteParse.
Field sources retain pages, nested field paths, word boxes and citation findings
in SQLite. Boxes use top-left PDF points and are marked `diagnostic_only`.
They are not promoted to verified approval highlights. A valid citation does not
establish that the extracted value or selected location is correct.

Selecting a LiteParse field shows **diagnostic citations** with a reminder to
verify against the PDF; it does not draw an approval highlight. Generic
page-only evidence messages do not name GLM-OCR. After a viewer update, refresh
already-open review, extraction-result and failure pages to load the current
script. Completing review retains the original extraction separately and JSON
storage uses final approved values without repeating extraction on review resume.

## Limits and failure handling

The task sends a complete selected document and does not silently truncate text,
discard pages, or merge partial model responses. It rejects page errors, invalid
page selections, oversized evidence, estimated context overflow, incomplete or
token-limited output, malformed JSON and schema/type violations. Error messages
omit source text and provider payloads. The character-based context estimate is
conservative guidance, not an exact model tokenizer.

Normal extraction makes one Qwen inference request per attempt. The workflow's
existing Prefect retry can repeat an attempt after a transient failure. A
successful retry clears only this task's previous transient error.
The request releases model memory after completion (`keep_alive: 0`) so a large
resident model does not occupy GPU memory while the operator reviews the PDF.
The next extraction may therefore include model-loading time.

For larger documents, use the selection criteria below before increasing
context/input/output allowances. Selecting relevant pages can reduce input when
excluded pages contain no required fields or items. Splitting mixed-document
bundles is a separate pipeline responsibility. Output amounts remain what was printed;
arithmetic calculations should be configured as a separate business task rather
than replacing extracted values.

Larger context settings can move model layers from GPU to CPU and slow inference
substantially. Use a smaller context that still fits complete evidence when the
machine's memory is limited; the task fails clearly rather than truncating it.

### Choosing LiteParse or GLM-OCR for larger documents

GLM-OCR is better positioned to handle larger documents because its initial
extraction processes each page separately. LiteParse currently sends all selected
pages' parsed evidence to one Ollama request, so both the input evidence and the
complete extracted item list must fit that request's context and output limits.
There is no universal page-count cutoff: text density, item count, schema size,
model settings, and available GPU/system memory determine the practical limit.

LiteParse has a potential processing-speed advantage because a normal attempt
uses one Ollama inference request for all selected pages. GLM-OCR uses separate
per-page requests for configured scalar/object fields and tables, with additional
calls for recovery or document resolution. Fewer calls reduce request overhead
and repeated prompt processing, so LiteParse can be faster when the complete
input and output fit comfortably in one request. Actual elapsed time still
depends on parsing/OCR, model choice, document size, and GPU/system memory;
context-driven CPU offloading can outweigh this advantage.

| Selection criterion | Preferred starting point |
| --- | --- |
| Selected text and all required output fit comfortably in one request | LiteParse + Ollama, particularly for PDFs with reliable embedded text; fewer Ollama calls can improve processing speed. |
| Many pages or a long item table make one complete-document request impractical | GLM-OCR, with page extraction and a resolution mode chosen for the document. |
| Independent pages can be combined without semantic reconciliation | GLM-OCR `page_merge`, which stops after deterministic merging. |
| Header roles or table content need reconciliation across pages | GLM-OCR `document`, subject to the resolver limits below. |

GLM-OCR is not unlimited. In `document` mode, table resolution partitions
structured candidate evidence into approximately 12,000-character chunks
(characters, not tokens) and supplies the corresponding page images. Scalar and
flat-object resolution still supplies all ordered page images in each field's
request; reduced image dimensions do not bound the number of pages. The task
also renders all PDF pages into memory upfront. These stages can become memory
or context bottlenecks on very large documents.

In `page_merge` mode, the first nonempty scalar value is retained and conflicts
are flagged. Identical complete table rows are deduplicated, so configure a
printed line number or other distinguishing reference when legitimate repeated
items must remain separate. GLM-OCR makes multiple model calls per page and may
take longer; page-based processing does not establish better accuracy or speed.

This recommendation reflects the current task architecture, not a comparative
GLM-OCR versus LiteParse accuracy benchmark. Validate representative documents,
including cross-page tables and repeated items, on the deployment hardware and
retain a matching Review Gate before production use. See the
[GLM-OCR operating guidance](user_guide.md#glm-ocr-extraction-local-ollama).

Results retain safe model/version, source fingerprint, page and timing metadata,
plus nullable-confidence field rows. The task creates no durable files itself;
the existing storage task registers exported JSON as a document artifact. Review
resume uses the pinned pipeline/form versions and final persisted values.

## Troubleshooting

| Symptom | Action |
|---|---|
| LiteParse is not installed | Install the pinned runtime requirements with the repository virtual environment; use that environment for application startup too. |
| Local Ollama is unavailable or timed out | Check the separately running server, loopback host, installed model and timeout. |
| Model is missing or cloud-backed | Use `ollama list` to confirm the exact downloaded local GGUF tag. The task rejects cloud tags before submitting parsed text. |
| PDF parse/OCR fails | Check that the selected pages exist, the PDF is readable and local OCR/language data work. A missing text layer with OCR disabled cannot produce scanned-page evidence. |
| Input or context budget exceeded | Select the relevant pages or raise limits within available memory. The task does not silently discard evidence. |
| Incomplete/token-limited output | Increase `num_predict` while keeping it below `num_ctx`, or select fewer relevant pages. |
| HTTP 500 or GPU out of memory | Inspect the local Ollama log and memory use. Reduce context only if the full input still fits; release other GPU workloads. Memory release after requests does not guarantee a request will fit. |
| Old GLM-OCR wording in a LiteParse review | Refresh the page and deploy templates/static assets together. All viewer consumers use the same release query; the extraction provider remains recorded in SQLite. |

The existing automatic workflow retry can recover transient failures; a durable
retry and review resume keep the original pinned pipeline/form versions. Edit
and publish a new pipeline version, then make a new upload when testing changed
extraction parameters. See [config-check troubleshooting](config_check_troubleshooting.md#liteparse-local-provider-configuration-errors)
for validation finding codes and constraints.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q test\extraction\test_liteparse_extract.py test\integration\test_liteparse_pipeline.py test\visual\test_liteparse_pipeline_editor.py
```

The integration tests use synthetic documents and mock inference while retaining
real SQLite pipeline publication, review pause/resume and JSON artifact handling.

See [production pipeline validation](liteparse_pipeline_validation.md) for the
six-invoice visual run, original extraction accuracy, manual review corrections
and the runtime limitations observed on this machine.
