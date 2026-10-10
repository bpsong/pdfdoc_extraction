# Review gate task reference

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## review.review_gate

- **type:** `"review.review_gate"`
- **Purpose:** Pauses a document for operator review when extracted fields or configured policies indicate human review is required.
- **params:**
  - `confidence_threshold`: float from `0.0` to `1.0`. Default is `0.8`; use `0.9` for a 90% review threshold.
  - `per_document_type_thresholds`: optional map of document type or split category to threshold.
  - `field_threshold_overrides`: optional map of field key to threshold.
  - `split_confidence_levels_requiring_review`: optional list of split confidence labels such as `high`, `medium`, or `low` that should force review.
  - `require_review_when_missing_confidence`: boolean. Default is `true`. When a published review schema is selected, missing-confidence review gating applies to fields marked `required: true` in the schema and to fields explicitly listed in `field_threshold_overrides`; optional schema fields do not force review solely because confidence is missing.
  - `require_review_for_missing_required_fields`: boolean. Default is `true` when schema validation is used.
  - `always_review`: boolean. If `true`, every document entering this task requires review.
  - `schema_version_id`: exact published review-schema version selected in the
    pipeline editor. The runtime injects its immutable definition into the
    task. The task never reloads a schema draft, newest version, or filesystem
    file.
  - `schema_file`: accepted only by legacy YAML/file migration and validation
    surfaces. Import it into a review-schema draft, publish the schema, and
    select the resulting exact version before production use.
  - `queue_name`: review queue name. Defaults to `review.default_queue_name` or `default_review`.
  - `review_scope`: controls the reviewer editing scope. Use `"document"` or `"low_confidence_fields"`; it does not decide which review conditions trigger the gate.
  - `allow_operator_to_edit_high_confidence_fields`: boolean. Default is `true`.
  - `resume_policy`: fixed to `"next_task"`; the Pipeline editor does not expose it as a choice.
- **Behavior:**
  - Evaluates persisted extracted fields, confidence values, missing-confidence conditions for mandatory schema fields, schema errors, split confidence, and business rule flags.
  - For object, scalar-array, and object-array fields, the persisted field confidence uses the minimum numeric nested confidence returned by LlamaCloud Extract. For example, an invoice `items` field is gated by the lowest line-item cell confidence.
  - Marks fields requiring review and creates a review queue item in SQLite when review is required.
  - Sets document state to `review_required` and pauses the workflow.
  - Operators use **Review Queue** to claim an item, save draft corrections, preview changes, and complete review.
  - Completed corrections are persisted in SQLite and the document resumes downstream workflow steps according to `resume_policy`.
- **Locking:** Review claims use `review.lock_timeout_minutes`, defaulting to 60 minutes. Claims are atomic: the current operator can renew a claim, another operator can take over an expired claim, and an active claim cannot be overwritten.

For schema-driven review field types, validation behavior, and LlamaCloud date-format guidance, see the [review schema administrator guide](../../admin/managing-review-forms.md).

**YAML configuration example:**

```yaml
tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: { $secret: "llamacloud-primary" }
      fields:
        supplier_name: { alias: "Supplier name", type: "str" }
        invoice_amount: { alias: "Invoice Amount", type: "float" }
    on_error: stop

  review_gate:
    module: standard_step.review.review_gate
    class: ReviewGateTask
    params:
      confidence_threshold: 0.90
      queue_name: "default_review"
      review_scope: "low_confidence_fields"
      require_review_when_missing_confidence: true
      require_review_for_missing_required_fields: true
      always_review: false
      resume_policy: "next_task"
    on_error: stop

  store_metadata_json:
    module: standard_step.storage.store_metadata_as_json
    class: StoreMetadataAsJson
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}"
    on_error: continue

pipeline:
  - extract_document_data
  - review_gate
  - store_metadata_json
```


LiteParse emits `liteparse_unscored`; use document scope when the operator must
be able to correct every field. Confidence remains null and source locations
remain diagnostic. Review completion persists final values; downstream storage
uses them without rerunning extraction. See [LiteParse](liteparse-extraction.md)
and the [schema reference](../review-schema-format.md).
