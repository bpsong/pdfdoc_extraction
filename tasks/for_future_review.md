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

## PDF Viewer Fit Controls Follow-Up

The human review PDF viewer previously exposed `Fit width` and `Fit page` buttons while using the browser-native iframe PDF viewer.

The implementation appended PDF.js-style URL fragments:

- `#zoom=page-width`
- `#zoom=page-fit`

This is misleading for Chromium-based native PDF viewers. Chromium parses numeric `zoom` values and uses `view=FitH` for fit width and `view=Fit` for fit page. PDF.js supports `zoom=page-width` and `zoom=page-fit`, but the current viewer is not a PDF.js viewer.

For future consideration:

- Decide whether the review PDF pane should stay as a browser-native iframe fallback or be upgraded to PDF.js.
- If staying with the native iframe viewer, reintroduce fit controls using `#view=FitH` and `#view=Fit`, then verify behavior in Chrome, Edge, and Firefox.
- If moving to PDF.js, implement controlled fit modes with PDF.js scale values such as `page-width` and `page-fit`.
- Add visual or browser-level tests that verify actual rendered page scale, not only the iframe URL fragment.

## Config Checker Schema-Key Follow-Up

The config checker currently reports the top-level `schema` key as unknown even
though the application uses `schema.directories` to constrain schema-file
resolution. This produces a non-blocking warning for otherwise valid runtime
configurations such as `config_split_invoice.yaml`.

For future consideration:

- Decide whether `schema.directories` is part of the supported configuration contract.
- If supported, add the top-level `schema` section and `directories` field to the config-check schema.
- Validate that each entry is a non-empty path and retain runtime containment checks in `SchemaService`.
- Add config-check tests for valid directories, invalid value types, and unknown nested keys.

## Workflow Artifact Retention and Purge Follow-Up

`CleanupTask` removes transient paths after a workflow but deliberately preserves
files registered in SQLite `document_files`. Registered internal artifacts such
as `source_original` and `split_pdf` therefore have no current retention policy
and may consume increasing disk space over the lifetime of the application.

There is also a classification risk to review: when a UUID-named working PDF in
the processing directory is registered as `source_original`, Cleanup preserves
that exact path. A temporary processing copy may consequently be retained as if
it were a durable business artifact.

For future consideration:

- Audit ingestion and split flows to distinguish temporary working files from
  durable source artifacts. Temporary processing copies should not be registered
  as durable unless this is an explicit product requirement.
- Add a configurable retention/purge service for completed and failed workflow
  transactions, using age, workflow status, and artifact type as policy inputs.
- Allow the purge service to delete managed internal artifacts such as
  `source_original` and `split_pdf` while preserving task-produced exports and
  archives, including `export_pdf`, `export_csv`, `export_json`, and
  `source_archive`.
- Restrict deletion to approved managed directories and resolved paths. Never
  delete arbitrary paths taken directly from database records.
- Provide a dry-run report showing affected workflows, files, database rows,
  estimated reclaimed space, missing files, and excluded artifacts.
- Define transactional or recoverable handling for partial filesystem/database
  failures so records and files do not silently diverge.
- Record purge activity in the audit log and support configurable retention
  periods, scheduled execution, and an administrator-triggered purge.
- Add tests covering active workflows, review-paused workflows, registered
  exports/archives, shared or duplicate paths, missing files, path traversal,
  partial failures, and idempotent reruns.

## Update Reference `task_slug` Follow-Up

`UpdateReferenceTask` accepts `task_slug` and defaults it to
`update_csv_reference`, but the current implementation only assigns the value to
`self.task_slug`. It is not subsequently used, written into workflow context,
included in an artifact record, or consumed by downstream tasks such as
`StoreMetadataAsCsv`.

For future consideration:

- Confirm whether external configurations or integrations rely on accepting the
  parameter, even though it currently has no runtime effect.
- Decide whether `task_slug` should be implemented for a defined status or audit
  purpose, or removed from `UpdateReferenceTask`, configuration validation,
  documentation, and the visual pipeline editor.
- If removing it, define a compatibility/deprecation path for existing YAML
  files and add tests confirming that downstream task behavior is unchanged.
