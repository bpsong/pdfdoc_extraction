# Future Design: Multi-Document Routing and Split Review

## Purpose

Define a future workflow extension for processing multiple document types and
handling uncertain split results without hard-coding invoice-specific behavior
into the shared pipeline.

This is a future design proposal, not current runtime behavior.

## Current Limitation

The configured pipeline is linear after splitting. A split child continues
through the same downstream task sequence regardless of its detected document
type. Extraction and review schemas are therefore selected by configuration,
not dynamically per child document.

The runtime does not currently provide:

- document-type-specific downstream task routing;
- extraction-schema selection based on split category;
- review-schema selection based on split category;
- an operator workflow for approving or correcting uncertain split segments
  before extraction continues.

## Proposed Capabilities

### Document-Type Routing

- Map each supported split category to an approved downstream pipeline or
  extraction configuration.
- Persist the selected route and document type on the child document.
- Reject unknown or unapproved routes rather than importing arbitrary task
  classes.
- Preserve the current serial pipeline as the default route.

### Schema Selection

- Select extraction fields or configuration IDs by document type.
- Select the review schema by document type.
- Validate that configured category, extraction, and review-schema mappings are
  complete before publishing the pipeline.
- Keep field keys aligned between extraction output and review schemas.

### Split Confidence Review

- Make confidence handling configurable by category and confidence level.
- Support policies such as:
  - stop the source workflow;
  - create a source-document split review item;
  - continue with an explicit warning;
  - reject an unknown category.
- Allow an operator to correct page grouping and category before child
  extraction starts.
- Record the original split result, operator correction, and final approved
  segments in SQLite audit data.

## State and Workflow Requirements

- SQLite remains authoritative for source documents, child documents, routing
  decisions, review state, and audit history.
- The source workflow must not start child extraction until a blocking split
  review is completed.
- Corrected segments must produce deterministic child lineage and artifact
  records.
- Fan-in must continue to derive source and batch status from terminal leaf
  documents.
- Resume behavior must be idempotent and must not create duplicate child
  documents.

## UI Direction

- Add split-review work to the existing review experience rather than creating
  a disconnected legacy page.
- Show the source PDF, proposed page groups, category, confidence, and editable
  corrections.
- Clearly distinguish extraction-field review from source split review.
- Show which downstream route and schemas each approved segment will use.

## Configuration Direction

Prefer an explicit mapping rather than embedding routing logic in task code.
The eventual schema could conceptually resemble:

```yaml
document_routes:
  invoice:
    pipeline: invoice_pipeline
    review_schema: schemas/invoice.yaml
  delivery_order:
    pipeline: delivery_order_pipeline
    review_schema: schemas/delivery_order.yaml
```

The exact format should be finalized together with pipeline-builder work so the
same model can be validated and edited safely in the admin UI.

## Non-Goals

- Arbitrary graph execution in the first release.
- User-authored Python routing expressions.
- Automatic rewriting of historical extraction or review records.
- Replacing the existing fan-out/fan-in state model.

## Acceptance Criteria for Future Implementation

- At least two document categories can select different approved downstream
  extraction and review configurations.
- Unknown categories follow an explicit configured policy.
- Low-confidence split results can create a blocking operator review item.
- Corrected split decisions resume exactly once and create deterministic child
  records.
- Route, schema, review, and correction decisions are auditable.
- Configuration validation detects missing routes and schema mappings before
  publication.
