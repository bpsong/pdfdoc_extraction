# Future Design: Multiple Pipeline Templates

## Purpose

Define the future implementation direction for supporting multiple published
pipeline templates. Administrators will configure pipelines for different
document-processing use cases, and the application will select a complete
pipeline when a document enters the system.

This is a future design proposal, not current runtime behavior.

## Decision

The first implementation will use explicit ingestion-time pipeline selection,
not document classification or dynamic routing between downstream tasks.

- For browser uploads, the operator selects a published pipeline before
  submitting a batch.
- For watch-folder ingestion, an administrator maps each watch folder to a
  published pipeline.
- Every batch and document records the exact published pipeline version chosen
  at ingestion.
- Split child documents inherit their source document's pipeline version and
  continue through that pipeline after the split step.

This preserves the current serial task-list execution model while allowing the
application to operate several independently configured pipelines.

## Why This Direction

Selecting a complete pipeline at ingestion is simpler and more predictable
than detecting a document type during execution and routing each document or
split child dynamically.

The selected design avoids introducing the following requirements into the
first release:

- classification-driven workflow branching;
- category-to-pipeline routing inside split or extraction tasks;
- confidence review solely to decide which pipeline should run;
- graph traversal and conditional-edge semantics;
- cross-pipeline task indexes and resume rules;
- dynamic extraction- and review-schema selection inside shared tasks.

It also makes the operator's choice, the watch-folder binding, and the exact
pipeline version used for a run visible and auditable.

## Terminology

- **Pipeline template:** A stable, named workflow definition such as
  `invoice-processing` or `delivery-order-processing`.
- **Pipeline version:** An immutable published revision of a pipeline template.
- **Pipeline draft:** An editable unpublished revision belonging to one
  template.
- **Ingress binding:** A mapping from an ingestion source, such as a watch
  folder, to a published pipeline version.
- **Pipeline run:** Execution of the pipeline version pinned to a batch or
  document.

A document type may be useful template metadata, but it must not be the
pipeline's primary identifier. More than one pipeline may legitimately process
the same document type for different business purposes.

## Target User Workflows

### Administrator

An administrator can:

1. Create, rename, clone, deactivate, and archive pipeline templates.
2. Edit an independent draft for each template.
3. Configure and order the template's approved tasks.
4. Validate and publish an immutable version.
5. See version history and a redacted configuration diff.
6. Bind one or more watch folders to published pipeline versions.
7. Change an ingress binding without changing or republishing pipeline logic.

Only published, active, valid pipeline versions may receive new documents.
Archiving or deactivating a template must not prevent existing runs from
resuming with their pinned versions.

### Operator Upload

The upload page will require the operator to select an available published
pipeline before processing begins. The initial implementation should apply one
pipeline selection to the entire uploaded batch.

The UI should show at least:

- pipeline name and description;
- intended document type or use case;
- published version;
- last-published time;
- any operator-facing instructions.

The upload API must reject a missing, unknown, inactive, unpublished, or
unauthorized pipeline version. It must not silently fall back to a default
pipeline when the submitted selection is invalid.

Per-file pipeline choices within one batch are outside the initial scope.
Operators can submit separate batches when documents require different
pipelines.

### Watch-Folder Ingestion

Watch folders are ingress bindings rather than properties embedded in pipeline
task definitions. Keeping bindings separate allows multiple folders to use the
same pipeline and allows operational folder changes without publishing a new
workflow version.

Conceptually:

```yaml
watch_folder_bindings:
  - path: watch_folder/invoices
    pipeline: invoice-processing
    version: 3
  - path: watch_folder/delivery-orders
    pipeline: delivery-order-processing
    version: 2
```

The final storage format may be SQLite-backed rather than YAML-backed, but the
same validation rules apply:

- each enabled folder has exactly one published pipeline version;
- paths are unique after Windows path normalization;
- ambiguous nested bindings are rejected or explicitly governed;
- inaccessible or invalid folders produce startup/admin validation findings;
- the resolved binding is persisted with every ingested batch and document.

## Pipeline Definition and Versioning

Each published pipeline version must contain the complete executable serial
definition required by the workflow loader:

```yaml
template:
  key: invoice-processing
  name: Invoice Processing
  document_type: invoice

pipeline:
  - split_document
  - extract_invoice
  - review_invoice
  - store_invoice_json
  - archive_invoice

tasks:
  extract_invoice:
    module: standard_step.extraction.llama_cloud_v2
    class: ExtractPdfTask
    params:
      configuration_id: invoice-config-id
    on_error: stop
```

The exact persistence schema should be finalized with the multi-template admin
work. A clean target model would provide separate records for:

- pipeline templates;
- immutable pipeline versions;
- template drafts;
- ingress bindings;
- batch/document pipeline assignments.

Published definitions must continue to use only approved task module/class
pairs. Custom tasks remain subject to the existing `custom_step.*` approval
rules.

## Execution Requirements

The current runtime reads one global `pipeline` and `tasks` configuration. The
multi-template implementation must change execution so that the selected
published definition is passed explicitly through the workflow lifecycle.

Required behavior:

1. Resolve and authorize the selected published pipeline version before
   creating or queuing the ingestion records.
2. Persist `pipeline_template_id` and `pipeline_version_id` on the batch and
   documents, or through equivalent authoritative relations.
3. Build the workflow from the pinned executable definition rather than the
   latest active configuration.
4. Record task runs against task keys and indexes from that pinned definition.
5. Make split children inherit the same pipeline version.
6. Make review resume load the same version and continue from its recorded
   position.
7. Make retries and recovery use the same version even when an administrator
   has since published a newer version.
8. Display processing state using a safe snapshot derived from the pinned
   version.

The existing display-only pipeline snapshot is not sufficient for execution
because it intentionally omits task parameters. The application must retain an
immutable executable definition while continuing to expose only redacted,
non-secret data through APIs, audit events, logs, and UI snapshots.

## Simpler Extraction Task

Each pipeline template owns its extraction configuration. The extraction task
therefore performs extraction using the parameters already supplied by its
pinned pipeline version.

The extraction task should not:

- classify the document to select another pipeline;
- map split categories to extraction configurations;
- choose between document-type schemas at runtime;
- import or dispatch to other workflow tasks;
- mutate the document's pinned pipeline assignment.

An invoice pipeline can configure an invoice extraction provider/configuration,
while a delivery-order pipeline configures a delivery-order extraction
provider/configuration. Review schemas and downstream storage rules are also
configured directly in their respective templates.

This keeps extraction focused on one responsibility: validate its configured
inputs, extract data from the current document, persist normalized extraction
results, and return the shared workflow context.

Optional validation may detect that a document appears incompatible with the
operator-selected pipeline, but that must produce an explicit validation or
review outcome. It must not silently switch pipelines.

## Split Behavior

Splitting remains a task within a selected pipeline. When enabled:

- the source document runs through the split step;
- created child documents inherit the source's pinned pipeline version;
- each child continues at the next task in that same version;
- fan-in continues to derive source and batch status from terminal leaves;
- retries must not create duplicate child documents.

The initial implementation assumes a split source contains documents that can
all be processed by the selected pipeline. Routing different split categories
to different pipelines is a separate future capability and should be added
only when mixed-document bundles are a demonstrated requirement.

## Persistence, Audit, and Security

SQLite remains authoritative for template identity, published versions,
ingress bindings, pipeline assignments, task runs, review state, and audit
history. The filesystem continues to hold PDFs and other large business
artifacts.

Audit events should cover at least:

- template creation, rename, clone, activation, deactivation, and archive;
- draft save, validation, publication, and published-version diff;
- watch-folder binding creation and change;
- operator pipeline selection at upload;
- the template and version assigned to each ingestion.

Pipeline read APIs and audit payloads must redact secret-like task parameters.
Published versions should reference secrets through the application's approved
configuration mechanism rather than expose secret values in browser-editable
definitions.

## Validation Requirements

Validation must run per template draft and across ingress bindings. It must
detect at least:

- duplicate or invalid template keys;
- missing, empty, or invalid task lists;
- unapproved module/class pairs;
- invalid task ordering and task parameters;
- missing extraction or review configuration required by that template;
- secret values that would be exposed through an unsafe configuration surface;
- watch folders with missing or invalid published-version bindings;
- attempts to assign new work to inactive or archived templates;
- incompatible changes that would make a published version non-immutable.

Publishing one template must not overwrite or change another template.

## Migration Direction

The existing single configured pipeline becomes the first template and its
initial published version. Existing behavior can remain compatible by treating
that migrated template as the configured ingress binding for the current watch
folder.

Migration must not rely on the mutable current configuration when resuming
documents already in review or processing. The implementation plan must define
how pre-migration runs retain or reconstruct a safe executable definition.

## Non-Goals for the First Release

- Automatic document-type classification for pipeline selection.
- Dynamic post-split routing to different pipelines.
- Arbitrary graph execution or conditional edges.
- Per-file pipeline selection inside one upload batch.
- User-authored Python routing expressions.
- Changing a document's pipeline after execution has started.
- Rewriting historical extraction, review, or task-run records.
- Replacing the existing split fan-out/fan-in model.

## Acceptance Criteria

- An administrator can manage at least two independent pipeline templates.
- Each template can be drafted, validated, published, and versioned without
  changing another template.
- An operator can select a published pipeline for an uploaded batch.
- At least two watch folders can ingest documents into different pipelines.
- Every new batch and document records its selected template and immutable
  published version.
- Processing, split children, review resume, retry, and recovery use the pinned
  version rather than the latest published version.
- Extraction and review configuration is defined directly in each template;
  extraction performs no document-type routing.
- Inactive, unpublished, unknown, or unauthorized selections are rejected.
- Admin and processing APIs expose redacted pipeline information without task
  secrets.
- Audit history identifies who selected or changed a pipeline or ingress
  binding and which version each ingestion used.
- Existing fan-out, fan-in, artifact registration, task approval, and SQLite
  workflow-state contracts remain intact.

## Deferred Mixed-Document Routing

If future evidence shows that one source PDF regularly contains document types
requiring different pipelines, design that feature separately. It would need
persisted split classification, confidence policy, operator correction,
category-to-pipeline mappings, child-specific pinned versions, and resume/fan-in
rules across those versions.

That complexity should not be part of the initial multiple-pipeline-template
implementation. The deferred design is documented in
[Future Design: Mixed-Document Pipeline Routing](future-mixed-document-routing.md),
which depends on the template and immutable-version model defined here.

## Related Future Design

- [Future Design: Mixed-Document Pipeline Routing](future-mixed-document-routing.md)
  extends this model with a split-and-route pipeline after multiple versioned
  pipeline templates are available.
- [Future Design: Lightweight Pipeline Visualization](future-lightweight-pipeline-visualization.md)
  records optional split and serial-flow presentation improvements while the
  production list editor remains the accepted authoring experience.
