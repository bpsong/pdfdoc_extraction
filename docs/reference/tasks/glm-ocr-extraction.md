# GLM-OCR extraction task reference

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## GLM-OCR extraction (local Ollama)

- **Module/class:** `standard_step.extraction.glm_ocr_extract` /
  `GlmOcrExtractTask`
- **Purpose:** Extracts configured structured data from PDF document types
  through a locally reachable Ollama server and the `glm-ocr:latest` vision
  model.
- **Prerequisites:** Install Ollama separately, pull `glm-ocr:latest`, start
  Ollama, and confirm the configured HTTP endpoint is reachable. Document mode
  also requires its configured resolver model to be installed.
  The application does not install, start, stop, or pull models from Ollama.
- **Parameters:**
  - `ollama_host`: HTTP(S) base URL, normally
    `http://127.0.0.1:11434`. Embedded credentials, query strings, and fragments
    are rejected.
  - `model`: installed Ollama model name, normally `glm-ocr:latest`.
  - `document_instructions`: optional document-level extraction guidance. Do not
    place secrets in instructions.
  - `prompt_style`: `detailed` (default) repeats deterministic field descriptors
    and the schema in the text prompt for compatibility with existing
    pipelines. `compact` keeps the schema only in Ollama's native `format`
    parameter and sends the document instructions with a short extraction
    contract. Compact mode can work better with smaller local models when a
    long duplicated prompt distracts from the document's visual relationships.
    `verbatim` is an advanced option that sends non-empty
    `document_instructions` exactly as written, with no framework prompt text,
    while still enforcing the native JSON Schema. Use it only after controlled
    testing because the instructions become the complete model prompt.
  - `resolution_mode`: `document` resolves each scalar or flat object against
    the complete ordered PDF and reconciles the configured table from page-level
    GLM-OCR evidence. `page_merge` retains the first supported page value and is
    the compatibility default when an older published definition omits this
    parameter. Newly added visual-editor tasks default to `document`.
  - `resolver_model`: installed local model used in `document` mode. It is
    required in that mode; the visual editor initially suggests
    `qwen3.5:9b-q4_K_M`.
  - `resolver_max_dimension`: longest edge, in pixels, for page images sent to
    resolver calls; default `1280`, allowed range 256 through 4096. Scalar and
    object fields use all ordered pages. Each table evidence chunk uses only its
    referenced source pages so the resolver can inspect visible table and
    section boundaries without loading unrelated pages.
  - `resolver_num_ctx`: positive resolver context size; default `18000`.
  - `resolver_num_predict`: positive resolver output-token limit; default
    `10000`. The resolver context must still be large enough for the prompt and
    requested output; increase `resolver_num_ctx` separately when required.
  - `resolver_max_attempts`: maximum attempts for a field or table evidence
    chunk; default `2`, allowed range 1 through 5. A table chunk that reaches the
    resolver output limit is split into smaller evidence chunks instead of
    repeating the same oversized request.
  - `dpi`: positive integer PDF render resolution; default `216`.
  - `num_ctx`: positive integer model context size; default `8192`.
  - `num_predict`: positive integer output-token limit; default `2048`.
  - `timeout_seconds`: positive request timeout; default `300`.
  - `fields`: the same stable extraction-field mapping used by downstream
    review and storage. Scalar fields, scalar lists, flat objects, and one
    `List[Any]` table with `item_fields` are supported. Text fields may define
    `choices` to constrain the Ollama JSON schema, and may opt into the
    `iso_date` normalizer to convert a transcribed source date to `YYYY-MM-DD`
    after extraction. A field or flat child property may set a positive,
    sibling-unique `schema_order`; the GLM editor exposes this as **Schema
    position**. Explicit positions control JSON Schema property order even
    though versioned JSON mappings are stored canonically.

Configure this task from **Admin > Pipeline** by adding **Glm Ocr Extract**.
Its properties panel is separate from the LlamaCloud Extract editor. Set the
local model values, choose **Complete document** for multi-page resolution, add
scalar fields, and use **List of objects > Edit row schema** for repeated logical
rows. Add and configure **Review Gate** after extraction, pin an exact published
review-form version, then add CSV or JSON storage. Save, validate, and publish
the pipeline before assigning it to an upload or watch-folder binding.

The task does not contain invoice-specific fields or parsing rules. Field keys,
aliases, descriptions, types, constraints, and document instructions define the
document semantics for each pipeline. For example, a bill-of-lading pipeline can
request a bill-of-lading number, shipper, consignee, notify party, carrier,
vessel/voyage, ports, and one containers or cargo table. Do not submit it to an
invoice pipeline and expect those fields to change automatically; create a
dedicated pipeline and matching review form using the same GLM-OCR task.

### Multiline field extraction guidance

Use field-level **Extraction guidance** when one text value occupies several
printed lines or sits next to a visually similar field. Typical examples include
addresses, consignee blocks, notify-party details, cargo descriptions, payment
instructions, and free-text notes. The guidance is part of that pipeline's
document schema; it does not change the generic GLM-OCR task for other document
types.

Configure the field in the visual editor:

1. Open **Admin > Pipeline**, select the intended pipeline template, and select
   its **Glm Ocr Extract** task.
2. Under **Extraction fields**, expand the text field that needs adjustment.
3. In **Extraction guidance**, identify the printed label or visual anchor,
   state that the value may span multiple lines, define where extraction must
   stop, say which lines must be retained, and exclude nearby fields that must
   not be copied.
4. Review **Document instructions** in the same task. Make its field definition
   consistent with the field-level rule. For example, do not describe `billTo`
   as a name and address at document level while its field guidance requests a
   name only.
5. Select **Save Draft**, then **Validate**. Resolve every blocking finding and
   publish a new immutable pipeline version.
6. Submit representative PDFs against the new version one at a time. At Review
   Gate, compare the entire field value with the source PDF, including embedded
   line breaks, and check every other field for prompt regressions before
   completing review.

Use this general pattern and replace each placeholder with document-specific
semantics:

> Extract the complete `<value>` block directly under the `<printed label>`
> label. The value may span multiple lines. Continue until `<clear stopping
> boundary>`. Preserve `<required line types>` and join the lines with `, `.
> Do not include `<adjacent or unrelated fields>`.

For a shipping destination printed over several lines:

> Extract the complete shipping destination block directly under the "Ship To"
> label. The value may span multiple lines. Continue reading until the next
> labelled field or document section. Preserve every visible address line,
> including repeated city or region lines and the country, and join the lines
> with ", ". Do not substitute the Bill To customer or customer name.

When an adjacent field must contain a name only, use a separate and explicit
boundary rule:

> Extract only the person name directly beneath the "Bill To" label. Do not
> include any address, city, region, country, or values from the adjacent "Ship
> To" block. Stop after the name.

Do not copy literal names, addresses, invoice numbers, or other sample values
into production guidance. Describe the label, role, layout boundary, and value
shape instead. Keep the rule as short as the document permits; local models can
degrade unrelated fields when prompts become repetitive or contradictory. If a
field legitimately contains both a name and address and downstream systems need
them separately, prefer an **Object with defined fields** containing `name` and
`address` rather than forcing both into one scalar string.

The review form's `multiline: true` option only displays a larger editing box.
It does not make extraction capture additional lines. Configure extraction in
the GLM-OCR field guidance, and configure `multiline` separately in the matching
review form when operators need to inspect or edit a long value comfortably.

Treat every guidance change as model-affecting configuration. Keep a fixed
regression set that includes short values, long multiline values, repeated
city/region lines, adjacent labelled blocks, and documents where the optional
field is absent. A successful result from one PDF or one invocation is not
sufficient evidence for production use.

The current task supports at most 100 top-level fields, flat structured objects,
and one logical array-of-objects table. Documents requiring separate container,
cargo, and charges tables do not fit that schema in one extraction task. Keep
only the business-critical repeated section as the table and model other values
as supported scalar or flat-object fields, or reassess the task boundary before
production use.

Use an **Object with defined fields** when several values must come from the
same visual block. This is important for documents that contain multiple
organizations or addresses. For example, configure the insured or billed
customer as one `customer` object with `name` and `address` properties, while
keeping `insurance_company` as a separate scalar. The object tells GLM-OCR that
the customer name and address belong together; two independent scalar fields
can otherwise be selected from different parties on the page. Objects are flat:
their properties may be text, integer, number, or yes/no fields, but cannot
contain another object or list. The same technique can group a coverage
period's `start_date` and `end_date` when both must come from one labelled date
range rather than from unrelated issue or due dates elsewhere on the page.

The task renders pages locally in memory and makes schema-directed vision calls.
GLM-OCR first produces scalar/object candidates and table rows per page. In
`document` mode, the resolver then evaluates one scalar or flat object at a time
against bounded copies of all ordered page images; it reconciles a table from
bounded structured row-evidence chunks. This field isolation helps prevent a
prominent value from one page or party from replacing a differently labelled
role elsewhere in the document. Results are normalized under `context["data"]`,
persisted to SQLite with provider `glm_ocr_ollama`, and are available to every
downstream task. The task does not provide field confidence, citations, or
PP-DocLayout output. Confidence therefore remains null; no score is invented.

Prompt style does not select the resolution strategy. Every mode first makes one
scalar/object GLM call per page; a required null may cause one focused recovery
call, and a configured array-of-objects table adds one table call per page.
`page_merge` stops after deterministic page merging. `document` additionally
runs isolated resolver calls for configured scalars/objects and one or more
bounded evidence-resolution calls for the table. In compact mode the same JSON
Schema is still enforced through Ollama; it is simply not duplicated inside the
text prompt. Put precise, document-specific selection rules in
`document_instructions`, and avoid literal example values that a small model
could copy into its answer.

### Prompt and schema-order sensitivity

GLM-OCR is a small local vision-language model and can be highly sensitive to
both prompt construction and JSON Schema property order. Do not assume that two
schemas containing the same fields are equivalent for model behaviour. Changing
the order of top-level fields or object properties can change which visual value
the model assigns to a field. Adding, removing, or renaming a field can also
change the effective order of the generated schema and affect unrelated values.

More instructions are not always better. A longer prompt, repeated schema
descriptions, or an additional rule for one field can distract the model and
degrade other fields that previously extracted correctly. Start with concise,
meaning-based instructions. Add only the disambiguation needed for the tested
document type, avoid repeating the same rule in several forms, and avoid literal
example values. Try `compact` prompt style when the detailed prompt is too long
or repeats information already enforced by Ollama's native schema parameter.
Use `verbatim` only when a concise prompt has been tested as a complete unit and
the compact framework wrapper itself changes model behaviour.

Treat field order, object grouping, prompt style, and document instructions as
model-affecting configuration. Before publishing a changed pipeline:

1. Set **Schema position** for every top-level field and structured child whose
   order matters, then inspect the YAML preview or exported definition to
   confirm the effective order. Positions must be positive and unique among
   siblings.
2. Change one variable at a time so that a regression can be attributed to a
   schema-order, field, object, or prompt change.
3. Test several representative PDFs for the document type using the same model
   tag, DPI, context size, and output-token limit as production.
4. Repeat important samples because a successful result from one invocation is
   not sufficient evidence that the configuration is stable.
5. Compare every extracted field with the source PDF, not only the field whose
   rule changed. Keep a known-good result as a regression baseline.
6. Publish the change as a new immutable pipeline version and retain a Review
   Gate when operators must verify local-model output. GLM-OCR supplies no field
   confidence, so the review workflow should treat all extracted values as
   requiring human confirmation.

Objects remain useful for keeping values from one visual block together, but
their child-property order must also be tested. If reordering fixes one field
while degrading another, restore the last known-good version and simplify the
prompt or schema in a separate draft instead of accumulating more instructions.

When a review gate follows GLM extraction, the task's structured unscored-output
flag makes every configured top-level field reviewable. Use document review
scope when the operator must inspect all scalar values and every line-item cell.
The queue displays missing confidence instead of a percentage. The operator
compares values with the PDF, corrects them, and completes review; resume then
reconstructs `context["data"]` from final SQLite values before CSV/JSON storage.
If no review gate is present, the flag is inert and the pipeline continues.

For portal ingestion, select the published GLM pipeline on **Upload & Process**.
For watch-folder ingestion, create an enabled binding to that exact published
version. Use a unique output filename such as `{id}`. CSV storage expands an
array-of-objects field to one row per item and repeats document-level scalar
values on each row.

```yaml
tasks:
  glm_extract:
    module: standard_step.extraction.glm_ocr_extract
    class: GlmOcrExtractTask
    params:
      ollama_host: http://127.0.0.1:11434
      model: glm-ocr:latest
      document_instructions: Extract only values visibly supported by the document.
      resolution_mode: document
      resolver_model: qwen3.5:9b-q4_K_M
      resolver_max_dimension: 1280
      resolver_num_ctx: 18000
      resolver_num_predict: 10000
      resolver_max_attempts: 2
      dpi: 216
      num_ctx: 8192
      num_predict: 2048
      timeout_seconds: 300
      fields:
        invoice_number: { alias: Invoice number, type: str }
        customer:
          alias: Customer
          type: Dict[str, Any]
          object_fields:
            name: { alias: Customer name, type: str }
            address: { alias: Customer address, type: str }
        note_type:
          alias: Note type
          type: str
          choices: [debit, credit]
        coverage_period:
          alias: Coverage period
          type: Dict[str, Any]
          object_fields:
            start_date:
              alias: Coverage start date
              type: str
              normalizer: iso_date
            end_date:
              alias: Coverage end date
              type: str
              normalizer: iso_date
        total: { alias: Total, type: float }
        line_items:
          alias: Line items
          type: List[Any]
          is_table: true
          item_fields:
            description: { alias: Description, type: str }
            quantity: { alias: Quantity, type: int }
            unit_price: { alias: Unit price, type: float }
pipeline:
  - glm_extract
```
