# Future Design: Mixed-Document Pipeline Routing

## Purpose

Define a deferred workflow extension for processing a source PDF that contains
multiple document types requiring different downstream pipelines.

The proposed model uses a dedicated router pipeline:

```text
Source PDF -> Split -> Route -> Type-specific pipeline per child -> Fan-in
```

This is a future design proposal, not current runtime behavior.

## Prerequisite Design

This feature depends on
[Future Design: Multiple Pipeline Templates](future-multi-document-routing.md).
Multiple named templates, immutable published versions, explicit pipeline
assignments, and version-aware resume behavior must exist before mixed-document
routing is implemented.

This document extends that design; it does not replace ingestion-time pipeline
selection. Operators and watch folders select a router pipeline at ingestion,
and the router pipeline later assigns each split child to its target pipeline.

## Decision

Mixed-document routing will be represented by a built-in `RouteTask` placed
immediately after a split task in a dedicated router pipeline.

Conceptually:

```yaml
pipeline:
  - split_document
  - route_document

tasks:
  route_document:
    module: standard_step.routing.route_document
    class: RouteTask
    params:
      routes:
        invoice:
          pipeline_version_id: invoice-processing-v3
        delivery_order:
          pipeline_version_id: delivery-order-processing-v2
      unknown_category: review
      low_confidence: review
    on_error: stop
```

The exact configuration and persistence schema should be finalized during
implementation. The important contract is that every successful route resolves
to an approved, immutable published pipeline version.

## Responsibility Boundary

`RouteTask` decides and persists the route. It must not directly start another
Prefect flow.

Direct workflow launch inside a configured task would make retry behavior
unsafe: a retried task could start the same target workflow more than once.
Workflow orchestration remains the responsibility of `WorkflowManager` and
supporting services.

The boundary should be:

1. `RouteTask` validates the child document and category.
2. A routing service atomically persists the route decision and pinned target
   pipeline version.
3. `RouteTask` returns a workflow control signal such as
   `pipeline_state: routed`.
4. `WorkflowLoader` stops the current router flow at that boundary.
5. `WorkflowManager` observes the signal and starts the assigned target
   pipeline exactly once.

`RouteTask` remains a standard configured task and must inherit from
`BaseTask`, use `TaskError` plus `register_error`, preserve shared context, and
use an approved `standard_step.*` module/class pair.

## Execution Sequence

### 1. Select the Router Pipeline

An operator or watch-folder ingress binding selects a published router pipeline
using the normal multiple-template mechanism. The source batch and document
are initially pinned to that router pipeline version.

### 2. Split and Classify

The split task creates child PDF artifacts and child document rows. Each child
must have a persisted category and confidence before routing begins.

The split task retains responsibility for:

- page grouping and child PDF creation;
- deterministic parent/root lineage;
- split artifact registration;
- category and confidence persistence;
- idempotent child creation during retries.

### 3. Run the Route Boundary

Each child begins at `RouteTask` in the router pipeline. The route task reads
the category from authoritative persisted split state rather than trusting only
the mutable workflow context.

The routing service resolves the configured category mapping, validates the
target version, and persists at least:

- router pipeline version;
- matched category and confidence;
- selected target template and version;
- route status and decision time;
- applicable policy outcome;
- audit attribution and non-secret decision metadata.

### 4. Start the Target Pipeline

After the route task completes, `WorkflowManager` loads the pinned target
definition and starts that child at the first target task. The target pipeline
must not rerun the source split or route tasks.

Extraction, review, storage, and archive tasks then use the configuration in
the target pipeline version. They do not perform additional document-type
routing.

### 5. Fan In Leaf Outcomes

The source and batch remain non-terminal until all routed children become
terminal leaves. Fan-in derives aggregate status from the child document
outcomes rather than interpreting the internal steps of every target pipeline.

## Route Version Semantics

Route mappings should reference exact immutable published target versions in
the first implementation. A mapping to an implicit `latest` version would make
the same router version behave differently over time and complicate audit,
retry, and reproducibility.

Publishing a new target pipeline version does not alter existing router
versions. An administrator must update and publish a router draft when it
should send new children to the new target version.

Every child retains its selected target version even if:

- the target template is later deactivated or archived;
- a newer target version is published;
- the router mapping is later changed;
- the child pauses for review and resumes later.

Deactivation prevents assignment of new work but must not break existing
assigned work.

## Routing Policies

The router must define explicit outcomes for categories that cannot proceed
normally. Initial supported policies should be deliberately small.

### Unknown Category

- `review`: create a blocking routing-review item;
- `fail`: mark the child failed with an operator-safe reason.

An implicit default target is not recommended because it can process a document
with the wrong extraction and review configuration.

### Low Confidence

- `review`: require an operator to confirm or change the category;
- `continue`: use the mapped route and persist an explicit warning;
- `fail`: stop the child.

Confidence thresholds may be global to the router or category-specific, but
they must be validated before publication.

### Unavailable Target

An unknown, unpublished, invalid, or unauthorized target version is a routing
failure. Runtime must not substitute another version automatically.

## Routing Review

A blocking routing review should use the existing review experience and
SQLite-backed pause/resume model, while remaining distinct from extraction
field review.

The operator should see:

- the child PDF and source lineage;
- proposed category and confidence;
- available categories approved by the pinned router version;
- the target template and version for each category;
- the original decision and any correction history.

Completing routing review atomically persists the corrected category, final
route assignment, reviewer identity, and audit event before target execution
is scheduled. Repeated completion or resume requests must not create duplicate
target runs.

## Fan-In Model

Basic fan-in does not need to merge or understand target pipeline graphs. It
continues to operate on terminal leaf document status:

```text
Source document
  |-- Invoice child ------> Invoice pipeline ------> completed
  |-- Delivery child -----> Delivery pipeline -----> review_required
  `-- Unknown child ------> Routing review --------> review_required

Source and batch aggregate status: review_required
```

Expected aggregate rules remain:

- any non-terminal leaf keeps the source and batch non-terminal;
- any routing or extraction review produces `review_required` aggregation;
- all successful leaves produce `completed`;
- mixed successful and failed leaves produce `completed_with_errors`;
- all failed leaves produce `failed`.

The additional complexity is execution identity and presentation. One child
executes a route step from one pipeline and downstream steps from another.
Task runs therefore need enough identity to distinguish workflow runs and
pipeline versions.

## Persistence Requirements

The final schema should support the following concepts, either as columns or
normalized relations:

- a workflow-run identity;
- the pipeline version used by each workflow run;
- a source/router pipeline assignment;
- a final target pipeline assignment per routed child;
- a route-decision record with category, confidence, policy, and status;
- an idempotency key or uniqueness constraint preventing duplicate target
  workflow starts;
- task runs associated with both a document and workflow run.

Adding a `workflow_runs` entity is preferable to relying only on task key and
task index. Those fields are ambiguous once one document executes portions of
more than one pipeline.

SQLite remains authoritative for route assignment, launch state, review state,
and fan-in status. Workflow context only carries execution signals and cached
identifiers.

## Idempotency and Recovery

Routing and launch must be safe under task retries, process interruption, and
duplicate resume requests.

Required invariants:

- one child has at most one final active target assignment;
- persisting the same route decision repeatedly is harmless;
- target launch is claimed transactionally before execution starts;
- a completed launch claim is not recreated by a retried `RouteTask`;
- recovery can detect an assigned child whose target workflow was not started;
- review completion resumes the target pipeline exactly once;
- split retry does not create replacement children with different identities.

The route decision and launch claim should be separate states so recovery can
distinguish "route selected" from "target workflow started."

## Validation Rules

Router-pipeline publication must reject:

- a route task without a preceding split task;
- tasks between split and route that make the child boundary ambiguous;
- extraction, storage, or archive tasks after route in the router pipeline;
- missing category mappings;
- references to unknown or unpublished pipeline versions;
- target versions that cannot accept routed documents;
- duplicate normalized categories;
- invalid confidence thresholds or policy values;
- direct or indirect routing cycles.

For the first implementation, target pipelines should be prohibited from
containing another route task. Nested routing can be reconsidered separately if
a demonstrated use case justifies recursive execution and more complex fan-in.

## UI Direction

The pipeline administration UI should identify router pipelines explicitly and
show the split-to-route relationship. Route configuration should use a mapping
editor rather than raw JSON for normal administration.

The editor should show:

- split categories available from the preceding task;
- target template and immutable published version per category;
- confidence and unknown-category policies;
- blocking validation findings;
- warnings when a target version has a newer published replacement.

Processing pages must render pipeline state per document. A single batch-level
snapshot is insufficient when children use different target versions. The UI
should show the router decision before the target pipeline steps without
presenting them as one misleading task index sequence.

## Security and Audit

The route task selects only approved published definitions. It must not import
arbitrary classes, evaluate user-authored expressions, or accept pipeline IDs
from extracted document text.

Audit history should record:

- router draft and publication changes;
- category-to-version mapping changes;
- automatic route decisions;
- routing-review corrections;
- target launch and recovery actions;
- the original and final category and target version.

Audit payloads, APIs, and logs must not expose secrets from either the router or
target pipeline definition.

## Non-Goals for the First Release

- Arbitrary conditional workflow graphs.
- Nested or recursive routing.
- Routing based on user-authored Python expressions.
- Selecting unpublished or mutable target drafts.
- Silently switching target versions after assignment.
- Combining extraction outputs from different children into one shared schema.
- Replacing leaf-derived fan-in with a configurable join task.
- Running target pipelines in parallel across multiple hosts.

## Acceptance Criteria

- An administrator can publish a router pipeline containing an approved split
  task followed immediately by `RouteTask`.
- At least two split categories route to different immutable published pipeline
  versions.
- Each child persists its original category, confidence, route decision, and
  final target version.
- `RouteTask` never launches a workflow directly.
- Each successfully routed child starts its target pipeline exactly once.
- Target extraction uses only its target pipeline configuration and contains no
  category-to-extraction routing logic.
- Unknown and low-confidence categories follow explicit configured policies.
- A blocking routing review can correct a category and resume exactly once.
- Retry and recovery tests demonstrate that route decisions, target launches,
  children, task runs, and artifacts are not duplicated.
- Fan-in produces correct source and batch status across completed, failed, and
  review-required children running different pipelines.
- Processing UI identifies both the router pipeline and each child's target
  pipeline version.
- Validation rejects missing targets, invalid ordering, unpublished versions,
  and routing cycles before publication.

## Related Future Design

- [Future Design: Multiple Pipeline Templates](future-multi-document-routing.md)
  is the required foundation for template identity, publishing, version
  pinning, ingestion selection, and simple target extraction tasks.
- [Future Design Direction: Visual Pipeline Builder](future-design-visual-pipeline-builder.md)
  describes the serial authoring model that a future route-mapping editor would
  extend.
