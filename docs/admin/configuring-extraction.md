# Configure document extraction

| Item | Value |
| --- | --- |
| Audience | Application administrators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

Extraction reads information from a PDF into named fields. The Admin decides
which facts matter, how to describe them, and which method suits the documents.
IT/support prepares provider connections, local models and machine capacity.
Configure extraction under **Pipeline**, then add a matching review form and
output steps. Changing the review form alone does not change extraction.

Go directly to [method selection](#choose-the-extraction-method),
[field configuration](#define-the-fields),
[the invoice example](#worked-example-invoice-fields),
[LiteParse setup](#configure-liteparse--ollama), [GLM-OCR setup](#configure-glm-ocr),
[LlamaCloud setup](#configure-llamacloud-extraction), or [testing](#test-a-change).

## Choose the extraction method

Start with representative documents and the required output, rather than a
method's name. The following advice reflects how the current tasks work; it
is not a measured speed or accuracy guarantee.

| Method / task in the catalog | Suitable starting point | Tradeoffs and preparation |
| --- | --- | --- |
| **Extract Pdf** — LlamaCloud | Approved cloud processing, including confidence-based review | IT supplies an approved secret alias/connection. PDFs go to the provider, with provider cost and availability to consider. Request confidence if the gate uses it. |
| **Lite Parse Extract** — LiteParse + Ollama | Short or moderate documents whose complete text and item output fit one model request; especially reliable embedded PDF text | Often fewer model calls and potentially faster. Local OCR reads scans. All selected pages and all output must fit together; a long/dense PDF can exceed limits. |
| **Glm Ocr Extract** — GLM-OCR + Ollama | Longer documents or substantial tables where one complete LiteParse request is impractical; visual relationships need checking | Processes pages separately and can reconcile across the document. Usually more model calls and potentially slower. Requires the OCR model and, for Complete document, an installed resolver model. Large PDFs still encounter memory and resolution limits. |

### LiteParse versus GLM-OCR for larger documents

LiteParse normally makes one model request per attempt with all selected pages'
parsed evidence. This can reduce repeated instructions and request overhead,
making it faster when both the input and complete output fit comfortably.
Scanned-page OCR, model loading and limited machine memory can remove that
advantage. A PDF with many item rows can exceed the output allowance even when
its text fits the input allowance.

GLM-OCR initially reads pages separately and makes additional requests for
fields, tables, recovery and document resolution. This makes it a better
starting point for larger documents that do not fit LiteParse's single request,
at the cost of longer processing in many cases. It has no unlimited-document
guarantee: all pages are rendered into memory; **Complete document** still
considers all page images for each scalar/grouped field, and its table resolver
works through chunks of evidence. Machine memory and model limits still matter.

There is no reliable page-count cutoff. Compare dense text, row counts, scanned
pages, cross-page tables and the actual machine. Do not promise operators that
every ten-page document will behave alike. Do not lower limits until processing
appears faster while required evidence is excluded.

For independent pages, GLM-OCR's **Page merge (legacy)** avoids document
resolution but keeps the first supported value when the same field occurs on
several pages. It flags conflicts and deduplicates identical table rows.
For a header whose correct meaning depends on later pages, or a table needing
cross-page reconciliation, start with **Complete document (recommended)**.
Retain printed line numbers or distinguishing references so legitimate repeated
items can be checked. Page merge can otherwise collapse identical rows.

Local extraction does not make later cloud tasks local. Inspect the whole
pipeline, including cloud splitting, before promising local-only processing.

## Define the fields

1. Open **Pipeline**, select the pipeline draft and its extraction task.
2. Under **Extraction fields**, select **Add field** and expand its card.
3. Replace the temporary **Field key** with a stable name such as
   `invoice_number`. Use the same spelling, case and grouping in the review form.
4. Set **Alias** to a recognisable name and select **Type** using the table below.
   An alias does not replace the field key. Output aliases also depend on each
   storage task's configuration; inspect a real export.
5. Set **Required field** only when extraction must return that field. This
   is separate from the review form's **Required** setting, which blocks review
   completion when blank. Test missing values; a required extraction/type failure
   can stop processing before an operator receives a review.
6. Write **Extraction guidance** describing the printed label, the value's role,
   boundaries and exceptions. Add **Document instructions** for rules shared by
   fields, such as `Transcribe printed values. Do not calculate missing totals.`
7. Configure structured fields and provider settings below. Select **Save Draft**,
   **Validate**, then publish only after resolving blocking findings.

| Extraction Type | Choose it for | Matching review control |
| --- | --- | --- |
| **Text** | Names, references, addresses, dates before normalization | `string`, or `date` when extraction supplies `YYYY-MM-DD` |
| **Integer** | Whole-number counts | `integer` |
| **Number** | Amounts and fractional measurements | `number` or `float` |
| **Yes / No** | A true/false fact | `boolean` |
| **List of text/integers/numbers/yes-no** | Repeated simple values | `array` with the corresponding **Items** type |
| **Object with defined fields** | Related values from one block | `object` with matching child keys |
| **List of objects** | Repeated rows with columns | `array`, **Items** `object`, matching child keys |

An extraction task allows at most 100 top-level fields and one table of objects.
Object properties and table columns are flat: use text, integer, number or
yes/no values, without another nested object/list. A review form can express
more groups than this; it cannot extend the extraction task's capabilities.

For local extraction, **Allowed values** constrains text to a comma-separated
list. Use it only when the list covers all valid outputs. **Value normalization**
can convert a transcribed date to `YYYY-MM-DD`; check ambiguous dates explicitly.
**Schema position** controls field order for the local model. Use positive,
distinct positions among sibling fields. Field order can change GLM-OCR results,
so treat reordering as a change requiring sample testing.

### Write useful guidance

For an invoice reference: `Read the reference printed beside Invoice No. Keep
leading zeros. Do not use the purchase order number.`

For an address: `Read the complete Bill To address below the customer name until
the next labelled block. Retain street, city, postal code and country. Do not
substitute Ship To. Join the address lines with commas.`

Describe the rule, not the answer from a sample. Do not paste a particular
customer's address into the instructions. Keep field and document instructions
consistent and concise. Repetitive rules can reduce the accuracy of other fields.
When a customer name and address must come from the same party, group them in
one object rather than two unrelated top-level fields.

## Worked example: invoice fields

Create the following fields to match the
[worked review form](managing-review-forms.md#worked-invoice-field-list).
These are example choices, not built-in invoice behaviour.

| Field key | Alias | Type | Guidance / settings |
| --- | --- | --- | --- |
| `invoice_number` | Invoice number | Text | Invoice reference, preserve leading zeros; exclude purchase order. |
| `invoice_date` | Invoice date | Text | Printed issue date, not due date. For local extraction, choose date normalization; verify `YYYY-MM-DD` before using a review date control. |
| `currency` | Currency | Text | Printed currency. For local extraction, allowed values `SGD, USD, EUR` only if these cover your accepted documents. |
| `invoice_total` | Invoice total | Number | Final printed amount payable, not subtotal; do not calculate a replacement. |
| `customer` | Billed customer | Object with defined fields | Read the name and address from the same Bill To block. |
| `line_items` | Invoice lines | List of objects | Read every actual item row across pages. Exclude repeated headings and totals. |

For `customer`, select **Edit object properties**, use **Add field** for `name`
and `address`, choose **Text**, enter aliases and clear guidance, then select
**Done**. The child keys are `name` and `address`, not `customer.name`.

For `line_items`, select **Edit row schema**, then **Add field** for
`line_number` (Text), `description` (Text), `quantity` (Number) and `unit_price`
(Number). Add guidance for wrapped descriptions, continuations and printed
line numbers. Select **Done**. Leave line number optional when it is absent on
valid documents. Set other required fields according to your document policy;
do not force the model to invent a value that is missing.

**Done** applies the object/row edits to the browser's pipeline draft. You still
need **Save Draft**, validation and publication for the whole pipeline.

## Configure LiteParse + Ollama

Add **Lite Parse Extract** and select it. Use the values prepared by IT/support;
the app does not install or start the model service.

| Screen control | How to configure it |
| --- | --- |
| **Ollama host** | Use the supplied local address, normally `http://127.0.0.1:11434`. LiteParse permits only the local computer; remote addresses and embedded credentials are rejected. |
| **Model** | Enter the exact installed local model name. The editor starts with `qwen3.5:9b-q4_K_M`; ask IT to confirm it is installed and appropriate. Cloud-backed models are rejected. |
| **Enable local OCR** | Keep enabled for scans or mixed PDFs. OCR means reading text from page images. Disable only when all accepted PDFs have usable embedded text and testing supports this. |
| **OCR language** | `eng` for English; for example `eng+chi_sim` for English and simplified Chinese only when IT has installed both language packages. |
| **Selected pages** | Empty means all pages. `1-3,5` selects pages 1, 2, 3 and 5. Exclude pages only if they contain none of the required facts or item rows. |
| **PDF render DPI** | Starts at 300; permitted 72–600. Higher resolution can help small print but increases processing and memory. Test any change. |
| **Document instructions / Extraction fields** | Configure the business meaning using the procedures above. |

**Local runtime settings** starts with **Context length** 32768, **Prediction
length** 4096, **Timeout (seconds)** 600 and **Parsed input character limit**
60000. Context is the model's allowance for instructions, evidence and response;
prediction is the maximum response size. Prediction must be smaller than context.
These are allowances, not promises that a machine can run that size.

If the input is too large, the task fails clearly rather than silently removing
evidence. First check whether page selection is appropriate or GLM-OCR is a
better fit. If output is incomplete, reducing requested business fields or
increasing prediction allowance may help, but retain every required row/value
and arrange memory checks with IT. Increasing all limits can cause much slower
processing or memory failures. Model memory is released between requests; the
next document can include model-loading time.

## Configure GLM-OCR

Add **Glm Ocr Extract**, select it, and configure these controls:

| Screen control | How to configure it |
| --- | --- |
| **Ollama host / Model** | Use the prepared endpoint and exact installed OCR model; the editor starts with `glm-ocr:latest`. IT must confirm the service and model. |
| **Document instructions** | Short document-wide guidance consistent with field instructions. |
| **Prompt construction** | Start with **Detailed (compatibility default)**. Compare **Compact (schema sent once)** when repeated instructions distract the model. **Verbatim instructions (advanced)** makes your instructions the full prompt; use only with controlled testing/support. |
| **Resolution mode** | Start with **Complete document (recommended)** for cross-page meaning. **Page merge (legacy)** keeps first supported values and does not perform semantic reconciliation. |
| **Resolver model** | Required for Complete document. IT must install a suitable vision-capable model; the editor suggests `qwen3.5:9b-q4_K_M`. |
| **Extraction fields** | Configure scalars, flat grouped values and at most one table; review field and child order. |

Newly added tasks default to Complete document. Older definitions that omit
the setting use Page merge; inspect the selected value when cloning/importing.

**Local runtime settings** starts at DPI 216, context length 8192, prediction
length 2048 and request timeout 300 seconds. **Resolver runtime settings**
starts at image max dimension 1280, context 18000, prediction 10000 and two
attempts. These are separate stages: changing OCR prediction does not change
the resolver's response allowance. Work with IT on capacity/timeouts; a timeout
is not an expected end-to-end completion time for the whole PDF.

Keep a known-good sample set before changing prompt style, object grouping,
field order or runtime allowances. Change one thing at a time, compare every
field and table row, and repeat important samples. A fix to one address can
degrade another field. Revert the draft approach when needed rather than piling
on contradictory instructions.

## Configure LlamaCloud extraction

Add **Extract Pdf**. In **API key secret alias**, use the alias supplied by IT;
keep credentials out of descriptions and field guidance.

With **Define extraction here**, choose **Tier** (**Agentic** or **Cost
effective**), normally **Target** **Per document**, and define the fields.
Start with **Request confidence scores** enabled when using confidence-based
review. **Per page** and **Per table row** change the shape of provider results;
use only when you have tested the intended downstream form and outputs.
Compare tiers on your samples and approved provider costs.

With **Use saved LlamaCloud configuration**, enter the supplied **LlamaCloud
configuration ID**. Still define the local field mapping used by review/output;
a saved provider configuration does not remove that requirement. Verify field
names and types with the configuration's owner. Publishing the pipeline does
not create the saved configuration at the provider.

Leave **Advanced inline extraction settings** and **Advanced provider settings**
at their prepared values unless a specific need is understood. Citations are
source pointers, not proof a result is correct. Ask IT about project/organisation
IDs or connection/timeouts; ask the document owner about what facts to extract.

## Add review and output steps

Put **Review Gate** after extraction, choose the exact published form and use
[the gate settings](managing-review-forms.md#connect-the-form-and-configure-review-routing).
LiteParse and GLM-OCR have no numeric confidence; their unscored output makes
every configured field reviewable at a following gate. Select **Entire document**
when operators must check all values and line-item cells. Lowering a threshold
does not turn these methods into confidence-scored extraction.

Place CSV/JSON export, meaningful PDF naming and reference-file updates after
review if they must use approved values. Use
[the task guide](task-guide.md#configure-output-files) to set destinations and
filenames. A PDF output task copies the PDF; it does not write corrected values
back onto the original page image.

## Test a change

Use a fixed set of approved or synthetic PDFs covering normal text, scans,
missing optional values, missing required values, long addresses, cross-page
tables and repeated items. Include the largest realistic document, not just the
shortest successful one. Record pipeline version, method/model, elapsed time,
original errors and operator corrections.

Check the original extraction before correcting it. Then correct values in
review, complete review, and inspect saved outputs. Compare row counts and all
business-critical fields with the PDF. Diagnostic citations or page links do
not establish accuracy, and local methods may lack precise highlights.

Validation is a configuration check, not a provider call or accuracy test.
Publish changes and use a new submission against that version for comparison;
an old document's retry keeps its pinned version. Do not treat the previous
[LiteParse validation](../history/validation/liteparse-pipeline-2026-10-04.md)
as a promise for your document types or hardware.

| Problem | First Admin check / next action |
| --- | --- |
| Wrong party or address | Clarify the printed label and stopping boundary; group related fields; test adjacent blocks. |
| Missing rows | Check selected pages, table guidance, output limits and repeated-row behaviour. Compare extraction and export separately. |
| Large document rejected | Read the input/context/output message; consider GLM-OCR or a justified page selection, then ask IT about capacity. |
| Slow local extraction | Record document size/rows and timings; compare methods on the same machine. IT checks memory, model loading and service health. |
| Date fails review | Align normalized date text with the form's date control. |
| Connection or installed-model error | Give IT the task, model name, pipeline version and safe error message; changing labels will not fix the connection. |

Detailed implementation limits are in the [task reference](../reference/tasks/README.md).
