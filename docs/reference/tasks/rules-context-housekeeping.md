# Rules, context and housekeeping task reference

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-11-25 — repository/source review; no live deployment check. CSV lookup source review and synthetic acceptance |
| Applies to | Production application; SQLite schema 11 |

## CSV reference lookup

The **CSV reference lookup** task uses
`standard_step.rules.csv_reference_lookup` / `CsvReferenceLookupTask`.
It reads a CSV and copies text from a matching row to new document-level keys.
**Update Reference** writes a configured value to matched rows in its CSV and
uses a separate parameter and comparison contract.

| Parameter | Contract |
| --- | --- |
| `reference_file` | Required literal CSV path. A relative path is resolved beside the deployment YAML. |
| `clauses` | One to five ordered objects with `field`, `column`, and optional `mode`. Every comparison must match the same record. `field` names a top-level extraction field from an earlier task. |
| `returns` | One or more objects with `column` and `field`. The field must be a new top-level key. Each lookup commits its returned values together. |
| `required` | Defaults to `true`. A required lookup must return a complete match before release. |
| `on_no_match`, `on_multiple_matches` | Independent policies. Both default to `review`. Each also accepts `fail` or, for an optional lookup, `continue`. |
| `on_error` | Set `stop` on the task. A malformed or inaccessible register stops execution even for an optional lookup. |

Place the lookup after extraction and before business outputs and CSV updates.
If either policy is `review`, put a Review Gate between the lookup and those
tasks. Independent lookups may use distinct return keys. A return key cannot
overwrite an extraction field, another lookup's output, or a reserved workflow
key such as `id` or `nanoid`. Match clauses take extraction fields as inputs.

### Comparison and release behavior

| Mode | Comparison |
| --- | --- |
| `case_sensitive` | Default. Trim surrounding whitespace from both strings and compare exactly. |
| `case_insensitive` | Trim both strings and apply Unicode case folding. Internal spaces, punctuation and leading zeros still matter. |
| `numeric` | Compare finite decimals. Text accepts an optional sign and a period as decimal separator, including `1.`. Booleans, grouping separators, currency and exponent notation in text are invalid. |

Return values preserve the cell text, including case, whitespace and leading
zeros. Match input cleanup changes only the comparison keys. A missing, blank,
or invalid input follows the no-match policy. A blank CSV key cannot match. A
nonblank invalid numeric key in a configured numeric column stops the task.

Use comma-delimited UTF-8 with an optional BOM, exact unique nonblank headers,
and standard CSV quoting. Every record must have the header's column count.
The built-in task reads at most 8 MiB and retains at most 50 candidates per
evaluation. It counts all matches. A candidate number starts at 1 after the
header and identifies a CSV record, including quoted multiline records.

A unique match needs a nonblank value in each return cell. Multiple matching
records remain ambiguous even if they return the same values. **Send to review**
holds the document at the gate. **Fail the task** stops the pipeline.
**Continue** for an optional outcome records a skip and omits all of its return
keys. A reviewer can choose a complete candidate from an untruncated set or
skip an optional lookup with a reason. See the [operator procedure](../../operator/reviewing-extracted-data.md#resolve-a-csv-reference-lookup).

### Synthetic supplier example

Save this register as `suppliers.csv` beside the deployment YAML. Use a test
invoice with extracted text `tax: "00123"` and `supplier: "acme"`.

```csv
Tax,Name,Code
00123,Acme,00042
123,Acme,00999
```

Publish and activate a review form with text fields `tax`, `supplier`, and
`supplier_id`. This minimal form can be imported into a form draft.

```yaml
# supplier-review.yaml
title: Synthetic supplier review
fields:
  tax: {type: string, label: Tax ID}
  supplier: {type: string, label: Supplier}
  supplier_id: {type: string, label: Supplier ID}
```

Use the following definition as a configuration recipe in **Pipeline**.
Replace the form ID, output directory and extraction secret alias with the
values approved for your test deployment. The extract task uses an approved
LlamaCloud alias for actual extraction. The verification suite supplies these
synthetic extraction values offline. To transfer the complete definition, use
the [portable bundle procedure](../pipeline-definition-format.md#stored-versus-portable-configuration).

```yaml
# supplier-lookup.yaml
schema_version: 1
pipeline: [extract, lookup, gate, output, csv, pdf]
tasks:
  extract:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: { $secret: "supplier-extract" }
      fields:
        tax: {type: str, alias: Tax ID}
        supplier: {type: str, alias: Supplier}
    on_error: stop
  lookup:
    module: standard_step.rules.csv_reference_lookup
    class: CsvReferenceLookupTask
    params:
      reference_file: suppliers.csv
      clauses:
        - {field: tax, column: Tax, mode: case_sensitive}
        - {field: supplier, column: Name, mode: case_insensitive}
      returns:
        - {column: Code, field: supplier_id}
      required: true
      on_no_match: review
      on_multiple_matches: review
    on_error: stop
  gate:
    module: standard_step.review.review_gate
    class: ReviewGateTask
    params:
      schema_version_id: REPLACE-WITH-PUBLISHED-FORM-ID
    on_error: stop
  output:
    module: standard_step.storage.store_metadata_as_json
    class: StoreMetadataAsJson
    params: {data_dir: "C:/DocFlow/test-exports", filename: "{supplier_id}_{id}"}
    on_error: stop
  csv:
    module: standard_step.storage.store_metadata_as_csv
    class: StoreMetadataAsCsv
    params: {data_dir: "C:/DocFlow/test-exports", filename: "{supplier_id}_{id}"}
    on_error: stop
  pdf:
    module: standard_step.storage.store_file_to_localdrive
    class: StoreFileToLocaldrive
    params: {files_dir: "C:/DocFlow/test-exports", filename: "{supplier_id}_{id}"}
    on_error: stop
```

The expected JSON is `{"tax":"00123","supplier":"acme","supplier_id":"00042"}`.
The CSV has the same three values, including `00042`. The PDF copy is named
`00042_<document-id>.pdf` on its first release to an empty directory. To
exercise ambiguity on a fresh document, insert `00123,ACME,00041` as the first
data record, choose the record returning `00042`, and complete review. Verify
the same values in the outputs and a filename tied to the new document ID.
Open CSV exports with identifier columns treated as text if a spreadsheet
application would otherwise remove the leading zeros.

For the stored draft and portable-bundle checks, see the
[config-check examples](../../../tools/config_check/README.md#validate-a-supplier-lookup).

## rules.update_reference

- **type:** `"rules.update_reference"`
- **Purpose:** Update a reference CSV file using extracted data.
- **params:**
  - `reference_file`: string (required). Path to the CSV file to update.
  - `update_field`: string (required). The name of the column to write the `write_value` into.
  - `write_value`: string (required). The value to write into the `update_field` for matched rows.
  - `backup`: boolean (optional). If `true`, creates a `.backup` file before writing (default `true`).
  - `csv_match`: dictionary (required). Defines the matching criteria:
    - `type`: string, must be `"column_equals_all"`.
    - `clauses`: list of 1 to 5 dictionaries, each defining a comparison:
      - `column`: string (required). The CSV column name to compare.
      - `from_context`: string (required). A field path to resolve the comparison value from the pipeline context (e.g., `"invoice_number"`).
      - `number`: boolean (optional). If `true`, forces numeric comparison; if `false`, forces string comparison; if `null` or omitted, auto-detects based on context value.
- **Behavior:**
  - Loads the configured CSV file.
  - Updates matching rows only; it does not append new rows.
  - Creates the configured `update_field` column at runtime if it is missing from the loaded CSV.
  - Saves the CSV, creating a backup if enabled.
- **Notes:**
  - Use workflow field keys in `from_context` (for example, `purchase_order_number`). Use CSV `column` names to match the external reference file headers.
  - If a comparison value is absent, no rows match; this is not itself a task
    failure, regardless of `on_error`.

**YAML configuration example:**

```yaml
tasks:
  update_reference:
    module: standard_step.rules.update_reference
    class: UpdateReferenceTask
    params:
      reference_file: "reference_file/reference_file.csv"
      update_field: "MATCHED"
      write_value: "match_all"
      backup: true
      csv_match:
        type: "column_equals_all"
        clauses: # List of 1 to 5 clauses for matching
          - column: "P/O NO."
            from_context: "purchase_order_number"
            number: false
          - column: "AMOUNT"
            from_context: "invoice_amount"
            number: true
    on_error: continue

pipeline:
  - update_reference
```

> **Migration Note:** Update Reference Configuration Update: Bare field names (e.g., 'purchase_order_number') are now preferred over dotted paths (e.g., 'data.purchase_order_number'). The dotted format is still supported for backward compatibility but will be deprecated in future releases. Deprecation warnings are logged when the old format is used.

## Assign Nanoid (standard_step/context)

- **type:** `"context.assign_nanoid"`
- **Purpose:** Assigns a short, URL-safe unique identifier to the shared task context for downstream use in filename construction (e.g., `{nanoid}_{purchase_order_number}_{supplier_name}`).
- **params:**
  - `length`: int (optional). Desired ID length. Valid range is 5–21. Default is 10.
- **Behavior:**
  - Generates a secure, URL-friendly ID using the Python `nanoid` package.
  - Validates `length` is an integer within 5–21; initialization fails with a configuration error otherwise.
  - Writes the generated ID to `context["data"]["nanoid"]`.
  - Downstream tasks can reference `{nanoid}` in their filename/rename templates.
  - Each invocation generates a new value, replacing any existing `data.nanoid`.
    It does not change workflow document/batch identity or provide a stable
    idempotency key across retries.

**YAML configuration example:**
```yaml
tasks:
  assign_nanoid:
    module: standard_step.context.assign_nanoid
    class: AssignNanoidTask
    params:
      length: 10
    on_error: stop

pipeline:
  - extract_document_data
  - assign_nanoid
  - store_metadata_json
  - store_file_to_localdrive
```

**Usage notes and migration:**

- Update existing filename templates to include `{nanoid}` where a short unique prefix is desired; for example:
  - `{nanoid}_{purchase_order_number}_{supplier_name}`
- This change ensures filenames are unique and traceable while remaining short.

## housekeeping.cleanup

- **Current module/class:** `standard_step.housekeeping.cleanup_task` / `CleanupTask`
- **type:** `"housekeeping.cleanup"`
- **Purpose:** Removes workflow-owned transient paths at terminal cleanup.
- **params:**
  - `processing_dir`: string (optional), default `processing`. Retained for
    compatibility; it does not confine deletion to that directory.
- **Behavior:**
  - Uses nonempty `context["cleanup_paths"]` when supplied, otherwise
    `context["file_path"]`. It deletes existing paths directly, without checking
    that they are beneath `processing_dir`; producers must supply only owned
    transient files.
  - Preserves paths registered in the current document's `document_files`
    records when the lookup succeeds. Without `document_id`, or if lookup fails,
    that protection is unavailable. It does not check all documents' artifacts.
  - Logs successes and warnings for missing files.
  - Raises exceptions on critical delete failures.
  - Executes after configured tasks finish or stop on an ordinary failure. Review pause and split fan-out return before cleanup.
  - Records a completed or failed internal task run under the reserved `cleanup_task` key without changing the document's configured pipeline cursor.
- **Notes:**
  - This task is automatically invoked by the WorkflowLoader when a flow reaches its cleanup phase.
  - It does not require definition in the portable `tasks` registry or
    inclusion in the `pipeline` list.
  - This is not a directory sweep or a retention policy.

## Validation and Failure Behavior

- The administrator Pipeline editor validates drafts before publication:
  - Each draft/version may contain at most one split task, one extraction task,
    and one review-gate task.
  - Extract tasks support at most one table field. A field is a table when `is_table: true` or its type is `List[Any]`, including the optional form.
  - Task parameter constraints, including the Nanoid length range of 5-21, are blocking findings.
  - Publish performs server-side validation again and atomically creates the
    next immutable SQLite version. A rejected publish creates no version and
    leaves the draft unchanged.
- Config validation happens at startup via the `ConfigManager`:
  - Validates that `web.upload_dir` exists and is a directory.
  - Validates that `watch_folder.dir` exists and is a directory; if missing/invalid, logs CRITICAL and exits. This path is NOT auto-created.
  - Pre-creates directories for deployment YAML keys ending with `_dir` when
    possible, excluding `watch_folder.dir`. SQLite task output paths are
    validated with the draft; storage/split/archive execution creates destinations
    when needed if permissions allow.
  - Validates all `_dir` paths exist and are directories; all `_file` paths exist and are files; exits on critical failure.
- At runtime, tasks validate their own required parameters.
- On validation failure or error:
  - The system logs the error.
  - Task-run and document state are updated in SQLite when document context exists; pipeline flow may continue or stop per each task’s `on_error`.
- **Tip:** Set `logging.log_level = DEBUG` in `config.yaml` for detailed diagnostics.

## Housekeeping and the Processing Folder

- The `processing_dir` contains temporary working files during processing. Workflow state is stored in SQLite.
- The workflow attempts housekeeping after the configured pipeline, including
  ordinary failures. It uses the context paths and current-document artifact
  checks described above; `processing_dir` is not a deletion boundary.
- An interrupted process or cleanup error can leave a working file behind. Check document state and logs before removing it manually.
- Any old text status files are legacy diagnostics only and are not required for current workflow state.

---
