# Future Review: Multi-Document Type Workflow and Split Confidence Handling

## Current State

The active workflow is configured for a single document type: invoice.

- `config.yaml` defines one split category: `invoice`.
- `extract_document_data` uses invoice-specific fields such as `invoiceNumber`, `invoiceDate`, `items`, and `totalAmount`.
- `review_gate` uses `schemas/invoice_config_review.yaml`, which is also invoice-specific.
- The pipeline is linear after splitting: `split_document`, `extract_document_data`, `review_gate`, storage tasks.

This means document-type-specific routing, different extraction schemas per document type, and different review schemas per document type are not currently implemented in the active workflow.

## Split Confidence Behavior

The split task currently treats low-confidence split results as a blocking failure.

- `LlamaCloudSplitTask` defaults `fail_on_confidence_levels` to `["low"]`.
- If any split segment has a confidence level of `low`, the task records a `fatal_failure` with `failure_type: split_policy_failed`.
- Because `split_document` is configured with `on_error: stop`, the workflow stops instead of continuing to extraction or review.

This behavior is intentional for the current workflow because an uncertain split can mean the system is unsure which pages belong together or what category the segment belongs to.

## For Future Consideration

These capabilities are not currently implemented in the active workflow and should be considered separately:

- Support multiple document types in one workflow, such as invoices, delivery orders, receipts, or statements.
- Route each split child document to a document-type-specific extraction task or schema.
- Route review to a document-type-specific review schema.
- Decide whether low split confidence should always stop the workflow, or whether it should create a human review item for source-document review.
- Add configurable handling for medium or low split confidence by document type.
- Define how operators should correct or approve uncertain split results before extraction continues.

## UI Configuration Follow-Up

The active `ui` configuration is partially used by the application.

Currently used:

- `ui.app_name` is used for the web app title and sidebar branding.
- `ui.page_size` is exposed in runtime/admin settings and shown on the settings page.
- `ui.admin_enabled` controls whether admin access is available.

Not currently wired into visible UI behavior:

- `ui.operator_sidebar` is present in `config.yaml` and `ConfigManager` defaults, but the sidebar links are hardcoded in `web/templates/app_base.html`. Changing this list does not currently control which operator sidebar items appear.

Compatibility or fallback behavior:

- `ui.max_upload_mb` is not present in the active config, but upload limits can fall back to it if `web.max_upload_mb` is not configured. Consider standardizing upload limit settings under `web` to avoid confusion.

For future consideration:

- Decide whether `ui.operator_sidebar` should become the source of truth for visible operator navigation.
- If sidebar configuration is required, implement route validation and role-aware hiding so config changes cannot expose invalid or unauthorized links.
- Remove unused UI config keys if they are not intended to become configurable behavior.
