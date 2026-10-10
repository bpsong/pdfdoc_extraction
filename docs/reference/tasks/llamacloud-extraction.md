# LlamaCloud extraction task reference

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## extraction

- **Current module/class:** `standard_step.extraction.extract_pdf` / `ExtractPdfTask`
- **Purpose:** Extracts structured data and confidence information from PDF documents through LlamaCloud Extract v2.
- **params:**
  - `api_key`: required secret reference in a versioned pipeline, for example
    `{ $secret: "llamacloud-primary" }`. Resolved credentials exist only in
    deployment `pipeline_secrets`.
  - `configuration_id`: optional saved Extract v2 configuration ID from the LlamaCloud UI. If omitted, the task builds an inline schema from `fields`.
  - `tier`: optional inline Extract v2 tier. Supported values are `"agentic"` and `"cost_effective"`; the default is `"agentic"`.
  - `parse_tier`: optional Parse tier for inline extraction.
  - `extraction_target`: optional target, default `"per_doc"`.
  - `cite_sources`: optional boolean to request citation metadata.
  - `confidence_scores`: optional boolean to request confidence metadata. Default is `true`.
  - `project_id` / `organization_id`: optional advanced provider-scoping values.
  - `poll_interval_seconds`: optional advanced polling interval. Default is `2.0`.
  - `timeout_seconds`: optional advanced timeout. Default is `1800.0`.
  - `fields`: map of field keys to alias and type, e.g.:

    ```yaml
    fields:
      name: { alias: "Name", type: "str" }
      amount: { alias: "Amount", type: "float" }
    ```

- **Behavior:**
  - Sends the PDF to the extraction provider.
  - Validates returned data against configured fields and types.
  - Normalizes extracted output to workflow field keys in `context["data"]`. Saved LlamaCloud configurations may return either field keys or aliases; both are accepted.
  - Storage tasks can transform workflow field keys only when their own
    task-specific `extraction.fields` mapping defines output aliases.
- **Notes:**
  - Use `configuration_id` when you want LlamaCloud to use a saved Extract v2 configuration. Omit it when you want the application to build the extraction schema from the YAML `fields` block.
  - In saved-configuration mode, `tier`, `parse_tier`, `extraction_target`,
    `cite_sources`, and `confidence_scores` come from the saved LlamaCloud
    configuration. Local `fields` normalize provider keys/aliases into stable
    workflow keys. Configure any CSV/JSON output aliases separately on that
    storage task.
  - Do not use `agent_id` for new configurations. It is a legacy Extract v1/LlamaExtract-era parameter and is not required by the current Extract v2 runtime.
  - Field names and types must match the provider's schema.
  - Internet access over HTTPS is required.

**Inline YAML configuration example:**

```yaml
tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: { $secret: "llamacloud-primary" }
      tier: "agentic"
      extraction_target: "per_doc"
      fields:
        supplier_name:        { alias: "Supplier name",       type: "str" }
        client_name:          { alias: "Client name",         type: "str" }
        client_address:       { alias: "Client",              type: "str" }
        purchase_order_number: { alias: "Purchase order",     type: "str" }
        invoice_amount:       { alias: "Invoice amount",      type: "float" }
        insurance_start_date: { alias: "Insurance Start Date",type: "str" }
        insurance_end_date:   { alias: "Insurance End Date",  type: "str" }
        policy_number:        { alias: "Policy Number",       type: "str" }
        serial_numbers:       { alias: "Serial Numbers",      type: "Optional[List[str]]" }
        invoice_type:         { alias: "Invoice type",        type: "str" }
    on_error: stop

pipeline:
  - extract_document_data
```

## LlamaCloud Extract v2 Structured Data Support

### Flat objects

Use `Dict[str, Any]` with `object_fields` when one extracted field contains a
fixed object whose properties have different primitive types. The Pipeline
properties editor exposes this as **Object with defined fields**.

```yaml
summary:
  alias: "Summary"
  type: "Dict[str, Any]"
  object_fields:
    customer_name:
      alias: "Customer name"
      type: "str"
    invoice_count:
      alias: "Invoice count"
      type: "int"
    total_amount:
      alias: "Total amount"
      type: "float"
    approved:
      alias: "Approved"
      type: "bool"
    notes:
      alias: "Notes"
      type: "Optional[str]"
```

`object_fields` is intentionally flat. Its properties support text, integer,
number, and yes/no values; nested objects and lists are not supported. The
normalized workflow context uses the configured stable property keys.

Review schemas are configured separately. To display the same value in the
review gate, define a matching review field with `type: object` and matching
keys under `properties`.

### Scalar lists

The Pipeline properties editor supports lists containing one primitive value
type. Use the corresponding extraction type:

| Editor option | Extraction type | Review schema item type |
| --- | --- | --- |
| List of text | `List[str]` | `string` |
| List of integers | `List[int]` | `integer` |
| List of numbers | `List[float]` | `number` |
| List of yes/no | `List[bool]` | `boolean` |

For human review, configure the matching field as `type: array` and set
`items.type` to the review-schema item type shown above. Extraction and review
schemas remain separate configurations, so their field keys and item types
must stay aligned.

### Arrays of objects

The canonical extraction and storage tasks handle LlamaCloud Extract v2 responses containing arrays of objects, such as invoice line items or multiple entries that need to be processed individually.

#### Overview

The canonical tasks allow extraction of structured data where certain fields return lists of sub-objects. For example, an invoice might have an "Items" field containing multiple line items with descriptions, quantities, and prices.

#### Configuration

To configure array-of-objects extraction, edit a pipeline draft visually or
import a portable definition containing the following task parameters:

1. Use the canonical extraction task:
   ```yaml
   extract_document_data:
     module: standard_step.extraction.extract_pdf
     class: ExtractPdfTask
     params:
       api_key: { $secret: "llamacloud-primary" }
       configuration_id: "YOUR-EXTRACT-V2-CONFIGURATION-ID"
       project_id: "YOUR-PROJECT-ID"  # optional advanced scope
       organization_id: "YOUR-ORGANIZATION-ID"  # optional advanced scope
       poll_interval_seconds: 2       # optional
       timeout_seconds: 1800          # optional
   ```

   The current runtime uses the `llama-cloud` SDK and `LlamaCloud` client. New configurations should use `configuration_id` or inline `fields`; `agent_id` is legacy.

2. Mark array fields with `is_table: true`:
   ```yaml
   items:
     alias: "Items"
     type: "List[Any]"
     is_table: true
     item_fields:
       Description:
         alias: "description"
         type: "str"
       Quantity:
         alias: "quantity"
         type: "str"
   ```

#### Storage Behavior

Storage remains isolated to the selected pipeline version. Add a task-specific
`extraction.fields` mapping to the CSV/JSON task when aliases or explicit table
metadata are required.

#### Confidence Persistence

- Scalar fields persist the provider's numeric confidence when available.
- Object, scalar-array, and object-array fields persist an aggregate confidence using the minimum nested numeric confidence.
- Nested confidence details are stored under each field's existing `source_json.confidence_details` payload, including per-cell paths such as `0.itemName` or `0.quantity`.
- No database migration is required; the existing `extracted_fields.confidence` and `source_json` columns are used.
- This behavior applies to new extraction runs only. Existing completed extraction/review records are not rewritten automatically.

#### JSON Storage

- Preserves the list-of-objects structure for table fields.
- Task-specific configured fields are written under their aliases when present;
  otherwise workflow field keys are preserved.
- Maintains backward compatibility with scalar-only data.

#### CSV Storage

- **Row-per-item mode**: Creates one CSV row for each item in the array, repeating invoice-level fields.
- **Column naming**: Scalar and item columns use task-specific configured
  aliases when present. Item columns are prefixed with `item_` (e.g.,
  `item_description`, `item_quantity`).
- **Fallback**: If no table field is configured or the list is empty, falls back to single-row format.
- **Example CSV output**:
  ```csv
  supplier_name,invoice_amount,item_description,item_quantity
  ALLIGATOR SINGAPORE PTE LTD,44.62,ELECTRODE G-300 3.2MM 5KG,4.0 PKT
  ALLIGATOR SINGAPORE PTE LTD,44.62,QUICK COUPLER SOCKET,2.0 PCS
  ```

### Migration Guide

To use the canonical array-of-objects tasks:

1. Configure the canonical extraction task:
   ```yaml
   module: standard_step.extraction.extract_pdf
   class: ExtractPdfTask
   ```

2. Add `is_table: true` to array fields in your extraction configuration.

3. Configure the canonical storage tasks:
   ```yaml
   # JSON
   module: standard_step.storage.store_metadata_as_json
   class: StoreMetadataAsJson

   # CSV
   module: standard_step.storage.store_metadata_as_csv
   class: StoreMetadataAsCsv
   ```

4. After the LlamaCloud UI configuration is ready, test with a small set of documents before full deployment.

5. With explicit authorisation and supplied credentials, validate a saved
   LlamaCloud configuration with the manual smoke checker. A live check consumes
   external provider resources; use a synthetic or approved test PDF.
   The script reads a YAML task definition; it does not load SQLite or resolve
   `pipeline_secrets`. Export/copy the selected pipeline definition to an
   ignored local smoke-input file and supply the credential through the current
   PowerShell process:

   ```powershell
   $env:LLAMA_CLOUD_API_KEY = "set-locally"
   .\.venv\Scripts\python.exe tools\llamacloud_extract_smoke.py --config smoke-pipeline.yaml --file sample_invoice.pdf --configuration-id "cfg-..."
   ```

   If `configuration_id` is already in the task definition, omit the override.
   Use `--raw-json path\to\result.json` for an offline fit check without a cloud
   call. The checker writes `raw_extract_result.json`,
   `workflow_normalized_data.json`, and `workflow_fit_report.json` under its
   output directory. Do not commit those files or the smoke input.

### Current Limitations

- Only one `is_table: true` field is supported per extraction.
- `object_fields` supports flat primitive properties only; nested objects and lists are not supported.
- Items must be simple dictionaries (no nested arrays or objects).
- Complex nested structures may require additional processing logic.

---
