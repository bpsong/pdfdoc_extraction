# Product roadmap

| Item | Value |
| --- | --- |
| Audience | Product owners, maintainers, developers and IT support |
| Owner | Application maintainers |
| Status | Eight agreed roadmap items; implementation not started under this roadmap |
| Updated | 2026-10-11 |
| Basis | Maintainer direction and repository/source review; no new live checks |

## Business aim

Extract relevant values from business documents, validate or review them as
needed, and deliver usable data and supporting documents to other systems.
Current outputs include JSON, CSV, and PDFs copied to descriptive filenames.
Pipeline versions, review forms, artifact tracking, and local/cloud extraction
are existing capabilities rather than new roadmap items.

## Agreed scope

This roadmap contains exactly eight agreed items. Their numbering identifies
them; it does not establish delivery order, release dates, or capacity promises.
R7 and R8 have lower priority than the existing R1-R6 items; no delivery order
among R1-R6 or between R7 and R8 has been agreed.
Research recommendations require a separate product decision before becoming
additional roadmap commitments.

| ID | Item | Status | Intended outcome |
| --- | --- | --- | --- |
| R1 | Optional PostgreSQL persistence alongside SQLite | Planned; detailed design required | IT support chooses the database appropriate to the deployment |
| R2 | Mixed-document pipeline routing | Planned; existing proposal to refine | Different document types within one PDF use their own downstream pipelines |
| R3 | CSV reference lookup and enrichment | Planned; detailed design required | Return matched reference values into document data for downstream outputs |
| R4 | Dynamic business-logic plugins for review forms | Planned; detailed design required | Check relationships between extracted values and show actionable operator findings |
| R5 | Reliable webhook delivery with n8n task integration | Planned; detailed design required | Hand approved values to n8n for delivery to receiving systems with traceable outcomes |
| R6 | Named users and role-based access | Planned; detailed design required | Give each person an account with appropriate permissions and attributable review/audit actions |
| R7 | Local scan-quality checks | Planned; lower priority; detailed design required | Warn about poor page quality before costly extraction and support operator rescan/review decisions |
| R8 | Azure Document Intelligence integration | Planned; lower priority; detailed design required | Optionally analyze documents through Azure, including checkbox states and signature-presence fields |

## R1: Optional PostgreSQL persistence alongside SQLite

### Outcome and deployment choice

Support either SQLite or PostgreSQL as the application's authoritative state
store. IT support selects one backend through deployment configuration during
installation or a controlled migration. SQLite remains the default for simple
local installations; PostgreSQL is an alternative for shared installations
with greater concurrent database activity or an existing managed database
service. This is a deployment choice, not a per-user or per-pipeline setting.

All operational domains use the selected backend consistently: users, batches,
documents, processing jobs, task runs, extraction results, reviews and locks,
pipeline/schema definitions and versions, settings, health, and audits.
PDFs and other large artifacts remain in registered filesystem storage.

### Required scope

- Establish a backend-neutral persistence boundary while preserving the
  route/service/repository responsibilities. Review direct SQLite connection,
  exception, SQL, trigger, and transaction dependencies throughout the app.
- Support backend-specific schema creation and ordered upgrades, connection
  lifecycle, PostgreSQL pooling, and backend-aware startup/schema checks.
- Preserve atomic job claims, review ownership and resume claims, immutable
  published versions, ingestion idempotency, and previewed retention cleanup.
  SQLite's database write lock needs an explicit PostgreSQL equivalent for
  each business invariant; translating SQL syntax alone is insufficient.
- Provide a stopped-state SQLite-to-PostgreSQL migration with row/count and
  relationship validation, preserved IDs and pinned versions, a rehearsed
  backup/restore procedure, and documented rollback before accepting new work.
  Define treatment of queued and paused work during migration.
- Document deployment settings, secret handling, connectivity, supported
  PostgreSQL versions, upgrades, database/artifact backups, and recovery for
  IT support. Do not expose connection credentials in UI, logs, or exports.
- Run the affected integration and concurrency tests against both backends,
  including conflicts, interrupted work, retries, and retention transactions.

### Acceptance and limits

A fresh deployment can run on either backend, and a representative existing
SQLite installation can migrate without losing its workflow history or
version assignments. Existing upload, review, processing, export, audit, and
recovery behavior must retain equivalent business guarantees on both.

Measure simultaneous ingestion, review, monitoring, and workflow-state writes
with synthetic data; agree on target workloads before promising capacity.
PostgreSQL support alone does not add parallel OCR, a worker pool, multi-host
processing, or shared artifact storage. Those require separate execution and
deployment decisions. Keep OCR/API resource limits distinct from database
concurrency.

Current reference: [Persistence and artifacts](../docs/architecture/persistence-and-artifacts.md).

## R2: Mixed-document pipeline routing

### Outcome

Process a source PDF containing different business document types through a
router pipeline: split and classify the source, route each child to its
configured type-specific pipeline, then aggregate the child outcomes.
For example, an invoice and delivery order in one PDF can use different
extraction schemas, review forms, and output rules.

### Required scope

- Configure category-to-published-version mappings in a dedicated router
  pipeline, retaining normal upload/watch-folder selection at ingestion.
- Persist each child's category, confidence, route decision, original router
  version, and exact immutable target version with complete lineage.
- Send unknown, ambiguous, or low-confidence routing decisions to explicit
  review or failure policies; allow an audited correction before dispatch.
- Keep routing decisions in the task/service layer and workflow dispatch in
  orchestration. Retries and recovery must prevent duplicate child creation
  and dispatch and handle interrupted side effects explicitly.
- Make review, resume, failures, artifacts, and source/batch status correct
  across children running different pinned pipelines.
- Show the router and each child's target pipeline accurately in processing
  pages; validate mappings, ordering, target eligibility, and cycles before
  publication.

### Acceptance and limits

A mixed PDF produces at least two child categories routed to different
immutable published versions. Each child completes its own extraction,
review policy, and outputs; routing review, retry, interruption, and aggregate
status tests preserve the business guarantees.

The first release excludes arbitrary workflow graphs, recursive routing, and
silent switching to newer target versions. It does not require a node-canvas
editor or depend on R1; preserve the selected backend's transaction guarantees.

Detailed proposal: [Mixed-document pipeline routing](future-mixed-document-routing.md).
The proposal remains a design input; finalize its schema and recovery contracts
before implementation.

## R3: CSV reference lookup and enrichment

### Outcome

Build on the existing CSV reference-matching capability by looking up reference
records and returning selected column values into workflow data. For example,
match an extracted supplier tax number against a CSV and populate
`supplier_id` for the outgoing JSON or CSV. Preserve the extracted tax number
and supplier name alongside the resolved ID.

The existing `UpdateReferenceTask` matches rows and writes a configured value
back to the reference CSV. Retain that behavior for existing pipelines; define
lookup/enrichment as an explicit capability that reads reference data and
enriches the document without modifying the source CSV.

### Required scope

- Configure the reference CSV, one or more match clauses, comparison types,
  and mappings from returned CSV columns to workflow field keys through the
  production pipeline editor. Validate missing columns, conflicting output
  keys, and incompatible types before publication or execution as appropriate.
- Begin with deterministic exact matching, including documented text and
  numeric normalization. Preserve identifier formatting such as leading zeros
  unless numeric comparison is explicitly selected.
- Define explicit outcomes for zero, one, and multiple matching rows. A unique
  match returns the configured values. Missing or ambiguous matches follow
  configured review, failure, or optional continuation policies; required
  unresolved values block downstream release. Never silently select the first
  row when several records match.
- Present the match basis, outcome, and returned values in review. Allow an
  audited resolution or correction and revalidate affected values before
  resuming downstream tasks.
- Persist enough provenance to explain and reproduce the decision, including
  the pinned lookup configuration and reference-file fingerprint or retained
  snapshot identity. Define retry and review-resume behavior when the CSV
  changes so accepted results are not silently replaced.
- Make enriched values available to existing JSON/CSV outputs and PDF filename
  templates while preserving extraction results and the shared task context.
- Cover unique, absent, and ambiguous matches, missing columns/values, type
  conversion, leading-zero IDs, conflicting output fields, changed reference
  files, and review/retry/resume behavior with focused and integration tests.

### Acceptance and limits

A configured pipeline resolves a supplier ID from a synthetic reference CSV,
retains the original extracted values, and includes the resolved ID in its
output. No-match and multiple-match cases visibly follow their policies and
cannot silently produce a required destination identifier. Existing CSV-update
pipelines retain their behavior, and lookup leaves reference files unchanged.

The initial scope is CSV lookup with exact matching. A managed reference-data
hub, API/database sources, scheduled synchronization, fuzzy matching, and
chained lookups remain separate future extensions. R3 does not depend on
PostgreSQL or mixed-document routing.

Current reference: [CSV reference updates](../docs/reference/tasks/rules-context-housekeeping.md#rulesupdate_reference).

## R4: Dynamic business-logic plugins for review forms

### Outcome

Attach configurable runtime business checks to versioned review forms. Evaluate
relationships across fields and table rows, then show warnings at the affected
rows/cells so operators can check the PDF and correct extracted values.

For example, each invoice-item row checks `unit_price * quantity` against its
`line_total`. A finding explains the row, expected amount, observed amount, and
difference. The configured calculation must account for the document's meaning,
including any discounts or tax that affect line totals.

### Required scope

- Configure rules, field bindings, severity, messages, and calculation settings
  in the production review-form editor. Start with deterministic rule templates
  for arithmetic, totals, date comparisons, and conditional requirements;
  support approved server-side validator plugins for specialized logic.
- Pin rules, parameters, and validator implementation/version identity to the
  published review-form contract. Existing reviews retain their assigned rules;
  define deployment compatibility when a plugin implementation changes.
- Invoke the same backend evaluator when the form loads, when the operator
  clicks **Revalidate**, and when review is completed. Revalidation checks the
  current unsaved form values without implicitly saving them or rerunning OCR.
- Mark findings stale after relevant edits, row insertion, or row deletion.
  Identify the evaluated form revision so a delayed response cannot overwrite
  newer findings. Review completion checks the actual submitted values.
- Show a summary and findings on affected rows/cells with accessible text.
  Distinguish passing, warning, blocking error, missing/invalid input, and
  evaluator failure; inability to evaluate must not silently count as a pass.
- Use decimal arithmetic and configurable rounding/tolerance for monetary
  checks. Treat missing values explicitly rather than substituting zero.
- Default the example line-total rule to an operator warning. Allow separately
  configured blocking rules; any permitted override requires an audited reason.
  Validation reports findings and does not silently correct extracted values.
- Reuse the rules before review-gate selection where needed so inconsistent
  high-confidence extractions can still require review. Revalidate after
  corrections and enforce required release checks before downstream outputs.
- Keep business evaluation in a service and plugin registry, with bounded
  execution and explicit approval of custom validators. Preserve the existing
  schema checks, review ownership, authentication, and resume contracts.
- Test arithmetic/tolerance boundaries, nested rows, missing values, discounts,
  edits, stale responses, revalidation, completion, severity/override behavior,
  plugin failures, and version pinning using synthetic documents.

### Acceptance and limits

A synthetic invoice row with quantity 3, unit price 10.00, and line total 300.00
shows a warning on load identifying the expected 30.00. Correcting the total
and clicking **Revalidate** clears the current finding; completion independently
evaluates the submitted values. Configured blocking rules prevent release until
resolved or explicitly overridden under policy.

This extends existing field/schema validation. Runtime evaluation executes
configured rules, not unrestricted code supplied through a form. A generic
workflow scripting platform and automatic AI correction are outside initial
scope. R4 can be implemented independently of PostgreSQL and n8n.

Current references: [Review gate](../docs/reference/tasks/review-gate.md) and
[review schema format](../docs/reference/review-schema-format.md).

## R5: Reliable webhook delivery with n8n task integration

### Outcome

Add a configured pipeline task that queues accepted document values for reliable
HTTP/webhook delivery, with n8n as the first supported integration. The app owns
extraction, reference matching, validation, review, and the accepted data revision.
n8n owns receiving-system field mapping, credentials, connector workflows, and
destination API calls.

The intended flow is extraction, matching/validation, review when required,
durable handoff, n8n processing, and receiving-system acknowledgement. Retain
standalone JSON/CSV and renamed-PDF outputs. Keep the webhook contract reusable
for other integration platforms; a custom n8n node is not required initially.

### Required scope

- Expose the task in the approved built-in task catalog and production pipeline
  editor. Use the shared task/context/error standards, and validate placement
  and release eligibility so required review/validation cannot be bypassed.
- Persist a durable outbox request with the accepted payload snapshot before
  dispatch. Include stable delivery ID, document/child identity, pipeline
  version, accepted data revision, payload-contract version, and artifact
  references. Make request creation idempotent across task retry and recovery.
- Send through a separate dispatcher so n8n downtime or long workflows do not
  occupy the extraction worker. Support timeouts, bounded retry/backoff, safe
  error summaries, and manual handoff retry without rerunning OCR.
- Use a configured n8n production webhook and deployment-owned authentication
  secrets. Keep destination-specific mappings and credentials in n8n; preserve
  a documented, previewable app-to-n8n data contract and synthetic test workflow.
- Distinguish queued, handed-off, destination-confirmed, and failed outcomes.
  Define n8n's durable acceptance contract; an immediate HTTP response only
  indicates the agreed handoff stage, not final receiving-system success.
- Provide an authenticated, idempotent n8n callback for destination success or
  failure, correlation IDs, and receiving-system record IDs. Handle missing,
  repeated, delayed, and out-of-order callbacks without false success or
  regression of a terminal outcome; define reconciliation for unknown results.
- Carry the same delivery ID across app handoff retries and n8n retries. Provide
  a persistent duplicate ledger or receiving-system idempotency/reconciliation
  contract. Do not promise exactly-once remote effects solely from HTTP retries.
- Define explicit correction/replacement behavior: newly accepted values create
  a new revision, while retry of an existing delivery preserves its payload.
- Transfer or provide authenticated retrieval of registered PDFs when required.
  Do not use a Windows local path as a remote file reference; align payload/file
  limits, access expiry, and retention with the chosen n8n deployment.
- Document IT ownership of n8n hosting, workflow changes, credentials, backups,
  connectivity, monitoring, and recovery. The n8n deployment has its own state
  and configuration; R1's application database choice is independent.
- Test with synthetic receivers: n8n unavailable, timeout after acceptance,
  duplicate attempts, downstream rejection, callback authentication/reordering,
  restarts, payload revisions, and file retrieval. Use an explicitly configured
  n8n environment for end-to-end acceptance.

### Acceptance and limits

A synthetic accepted document reaches an n8n workflow and a test destination;
the app records the final receiver ID. During n8n or destination downtime, the
approved revision remains traceable and retryable. Recovery tests demonstrate
the selected duplicate-prevention contract without another extraction. Operators
can distinguish successful extraction from pending or failed external delivery.

Direct ERP/CRM connectors in this app, a connector marketplace, and a custom
n8n node are outside initial scope. R5 can use SQLite and does not depend on R1;
it must honor any configured R3/R4 requirements before release.

Integration references: [n8n Webhook node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/)
and [n8n error handling](https://docs.n8n.io/flow-logic/error-handling/).

## R6: Named users and role-based access

### Outcome

Support individual accounts for administrators and operators/reviewers, replacing
shared day-to-day use of the two fixed accounts. Attribute review claims,
corrections, completion, configuration changes, and other audited actions to
the person who performed them.

### Required scope

- Provide administrator-managed account creation, display names, unique login
  names, role changes, password reset, and disabling/reactivation. Use stable
  user IDs so renaming or disabling an account preserves historical attribution.
- Define a small permission matrix for administration, pipeline/form configuration,
  document submission/processing, review, and read-only monitoring. Preserve
  existing admin/operator capabilities during migration; enforce permissions
  in backend services/APIs as well as production UI controls.
- Bind review ownership, locks, corrections, and completion to individual user
  identities. Specify audited takeover/reassignment and what happens to active
  claims when a user is disabled, without losing accepted work.
- Preserve password hashing, session revocation, CSRF protections, and recovery
  safeguards. Disabling a user or removing permissions must affect existing
  sessions; prevent accidental removal of the last usable administrator.
- Define migration/bootstrap and IT recovery for existing installations. Keep
  historical actions under their original shared identities; do not attribute
  older admin/operator actions to a newly created individual.
- Keep n8n/service authentication separate from human logins. Store user state
  in the selected authoritative database, with equivalent behavior on supported
  backends; R6 must also work with SQLite independently of R1.
- Test account lifecycle, permission enforcement, session invalidation, concurrent
  claims, disabled-user claim recovery, audit attribution, existing-account
  migration, and administrator recovery with synthetic users and documents.

### Acceptance and limits

Two named reviewers can sign in independently and claim different review items.
An active claim cannot be completed by another user without an allowed, audited
ownership change. History identifies who corrected and completed each review.
A monitoring-only user cannot edit reviews or configuration, including by direct
API calls. A disabled account cannot continue using an existing session, and its
historical actions remain attributable.

Initial scope is local named accounts and defined roles. SSO, directory sync,
reviewer groups, fine-grained pipeline/queue scopes, and multiple-person approval
are separate extensions driven by deployment needs.

Current reference: [Account administration](../docs/admin/accounts-and-settings.md).

## R7: Local scan-quality checks

**Priority: lower than R1-R6.**

### Outcome

Provide optional local page-quality checks before costly extraction. Explain
potentially blurred, faint, near-blank, skewed, or low-resolution scan regions
so operators can decide whether review or a replacement scan is needed.

### Required scope

- Use PyMuPDF rendering and image metadata with evaluated OpenCV/NumPy
  measurements. Explicitly pin required runtime dependencies and verify a clean
  Windows/Python 3.13 installation rather than relying on locally installed tools.
- Configure checks, render limits, thresholds/profiles, and warning/review policy
  per pipeline. Start with advisory findings, not automatic document rejection
  or removal of apparently blank pages.
- Distinguish source scan resolution from render DPI and account for mixed
  image/text pages. Bound page/pixel counts, memory, and execution time; reuse
  suitable page renders where practical.
- Persist page/region references, measurement values, finding codes, and check
  version. Show actionable warnings and distinguish unavailable/inconclusive
  checks from passes. Preserve original PDFs and register durable derivatives.
- Calibrate against representative approved samples and synthetic degradations;
  measure false alarms, missed unreadable fields, and runtime/resource use.
  Include sparse pages, faint marks, table-heavy pages, and born-digital text.

### Acceptance and limits

A configured pipeline flags relevant synthetic blur/contrast degradations with
page-specific findings and retains the source document. Representative clear,
sparse, and mixed-content documents meet agreed false-alarm and resource limits.
Quality results remain traceable through review and retries.

Initial scope is calibrated local heuristics. Reliable glare/cutoff detection,
automatic image enhancement, and blocking rescan requirements need separate
evidence and policy decisions. Quality measurements do not establish extraction
correctness. R7 does not depend on Azure or PostgreSQL.

Design input: [Python scan-quality feasibility](research-scan-quality-and-visual-marks-2026-10-11.md#scan-quality-checks-with-python).

## R8: Azure Document Intelligence integration

**Priority: lower than R1-R6.**

### Outcome

Offer an optional configured Azure Document Intelligence task/provider, called
directly from Python. Map supported document fields into workflow data and
review, including checkbox states and signature-presence results when required.
A pipeline can retain local extraction and invoke Azure for selected analysis;
n8n is not required for this extraction integration.

### Required scope

- Integrate the official Python SDK or REST API through the task/service
  boundaries and production pipeline editor. Pin dependencies and supported
  API versions, and validate configuration before publication where possible.
- Configure deployment-owned endpoint/credentials and permitted model IDs.
  Explain that selected documents are sent to Azure; document IT ownership of
  the resource, region, quotas, metered use, connectivity, and credential setup.
- Support a scoped initial model set: layout selection marks and configured
  custom extraction models for required fields/signature presence. Custom
  signature detection requires a trained model and representative evaluation;
  the generic layout call must not be assumed to provide that capability.
- Map semantic field keys, states, page/region evidence, and available provider
  confidence into the shared workflow/review contract. Preserve uncertain,
  missing, and failed outcomes; do not silently turn them into false/absent.
- Record the selected model/API identity, analysis operation, and source artifact
  for provenance. Bound submission/polling time, handle throttling and failures,
  and define retry/recovery without silently duplicating submissions or charges.
- Apply existing task approval, error, artifact, and pinned-pipeline standards.
  Allow R4 validation to require a mark/signature and R5 to deliver accepted
  results; keep detection distinct from business release decisions.
- Test mapping, uncertain results, authentication failures, timeouts, throttling,
  and retry/recovery with synthetic fixtures and mocked Azure responses. Run
  explicitly authorized live acceptance against the configured resource and
  labelled checkbox/signed/unsigned/ambiguous examples before release.

### Acceptance and limits

A configured pipeline sends a synthetic PDF to Azure and presents mapped
checkbox results with page evidence in review. A configured trained model can
provide evaluated signature-presence fields. Required uncertain outcomes route
to review or failure policy; accepted values reach existing output contracts.
Pipelines without Azure configuration retain their selected local providers.

Initial scope is an optional document-analysis integration, not every Azure
model or automatic model training. Signature presence does not verify identity,
authenticity, or cryptographic PDF signatures. R8 does not depend on R1 or R7.

Design input: [Visual-mark feasibility](research-scan-quality-and-visual-marks-2026-10-11.md#checkbox-and-signature-presence-detection).
Integration reference: [Azure Python SDK](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-documentintelligence-readme?view=azure-python).

## Research and future prioritization

See [Comparable extraction products and feature assessment](research-extraction-product-features-2026-10-11.md)
for sourced recommendations aligned with downstream data delivery. CSV lookup,
dynamic review validation, n8n handoff, named users, scan-quality checks, and
Azure integration are agreed as R3-R8;
the remaining recommendations are candidates for discussion, not additional
agreed items.

See [Scan-quality and visual-mark feasibility](research-scan-quality-and-visual-marks-2026-10-11.md)
for local Python options and AI checkbox/signature-presence detection. R7/R8
are agreed at lower priority; alternative local visual-mark detectors and other
extensions remain research candidates.

Before scheduling any agreed item, prepare a scoped design and implementation
checklist, confirm prerequisites, and define measurable acceptance criteria.
Update this roadmap when a decision or implementation status changes, and move
completed implementation plans into the archive.
