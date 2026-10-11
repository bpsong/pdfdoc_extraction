# Extraction product research and feature assessment

| Item | Value |
| --- | --- |
| Audience | Product owners, maintainers, developers and IT support |
| Owner | Application maintainers |
| Status | Research assessment; R3-R8 accepted, with scan-quality checks and Azure integration at lower priority; remaining recommendations unapproved |
| Researched | 2026-10-11 |
| Method | Official vendor documentation and current repository/source review |
| Limits | No vendor trials, price comparison, accuracy benchmark, or live integration tests |

## Decision context

The business aim is to extract relevant values and ultimately pass them to
other systems, together with supporting documents when needed. Existing JSON,
CSV, and descriptively named PDF outputs are useful delivery foundations.
Prioritize reducing the work between a reviewed extraction and a usable record
in the receiving system. Avoid adding features solely because another product
has them.

The [roadmap](roadmap.md) contains eight agreed items: a deployment choice between
SQLite and PostgreSQL, mixed-document pipeline routing, CSV reference lookup
and enrichment, dynamic review-form business validation, reliable webhook
delivery with n8n integration, named users with role-based access, local
scan-quality checks, and Azure Document Intelligence integration. On
2026-10-11, the maintainer accepted CSV lookup as R3, dynamic validation as R4,
n8n delivery as R5, named users as R6, scan-quality checks as lower-priority R7,
and Azure integration as lower-priority R8. Remaining recommendations
below are candidates for discussion. Suggested priorities are an assessment
for this app, not vendor claims or delivery commitments.

## What comparable products document

| Product | Documented capabilities | Implication for this app |
| --- | --- | --- |
| Docparser | HTTP delivery with configurable request method, headers, JSON/XML/form payloads, payload templates, document/row delivery, and payload preview. See [Advanced Webhooks](https://help.docparser.com/hc/en-us/articles/16254950012308-How-do-Advanced-Webhooks-work). | A generic destination adapter and previewable field mapping can connect many receiving systems. |
| Nanonets | Export destinations include cloud storage, accounting/CRM systems, webhooks, FTP, and API integration. See [Exports](https://docs.nanonets.com/docs/exports). Webhook delivery can follow processing, validation, or approval. See [Webhook export](https://docs.nanonets.com/docs/webhook-export). | Start with one reusable delivery method and explicit release conditions; add named connectors only for actual customers. |
| Rossum | Matches extracted supplier/customer information against reference datasets and can link purchase orders. See [Master Data Hub](https://knowledge-base.rossum.ai/docs/master-data-hub). Identifies identical uploaded documents. See [Duplicate detection](https://knowledge-base.rossum.ai/docs/duplicate-detection-in-rossum). | Correct destination IDs and duplicate controls are distinct from recognizing document text. |
| Docsumo | Configurable field and cross-field validation, including checks that totals reconcile. See [Field-level validation](https://support.docsumo.com/docs/field-level-validation). | Deterministic business checks can stop plausible but incorrect values reaching another system. |

These sources establish advertised/documented features, not their accuracy,
availability in every subscription, or comparative quality. Integration
reliability requirements below are our proposed design, not assumptions about
the vendors' retry or delivery guarantees.

## Existing capabilities to build on

Repository review found:

- [JSON, CSV, and PDF storage](../docs/reference/tasks/storage-and-archiving.md),
  including field aliases, table-row expansion, and filename templates.
- [Review schemas](../docs/reference/review-schema-format.md) and human review,
  with typed values and existing field validation. Extend these rather than
  proposing human review as a missing feature.
- [Reference CSV updates](../docs/reference/tasks/rules-context-housekeeping.md),
  which match extracted values and update existing rows. This is narrower than
  resolving a supplier/customer ID from a maintained master-data source.
- [ReportsService](../modules/services/reports_service.py), which reports basic
  document outcomes, review counts, and average processing time.
- [Upload submission fingerprints](../modules/services/upload_submission_service.py)
  and idempotency receipts. These protect upload retries; they are not a
  general business-duplicate policy across separate submissions and sources.
- [The approved task catalog](../modules/services/task_registry_service.py),
  which has local storage tasks but no built-in generic outbound HTTP delivery
  task. The existing web APIs are not a documented downstream delivery contract.

## Candidate assessment

| Candidate | Recommendation | Business value and initial scope |
| --- | --- | --- |
| Reliable outbound delivery with delivery status | Accepted as [roadmap R5](roadmap.md#r5-reliable-webhook-delivery-with-n8n-task-integration) | Queue approved data for authenticated n8n handoff; track retries, callbacks, destination acceptance, and receiving-system IDs independently of extraction. |
| Versioned output mapping and payload preview | Stable app-to-n8n contract in R5; destination mapping delegated to n8n | Transform canonical values into each receiving system's fields in n8n. A separate general-purpose mapping engine in this app remains unapproved. |
| Business validation before release | Accepted as [roadmap R4](roadmap.md#r4-dynamic-business-logic-plugins-for-review-forms) | Run configured row/cross-field rules on form load, explicit revalidation, and completion; show warnings and enforce configured blocking checks. Extend existing schema validation. |
| Master-data lookup and enrichment | CSV exact-match lookup accepted as [roadmap R3](roadmap.md#r3-csv-reference-lookup-and-enrichment); broader sources deferred | Return configured reference columns into document data, preserving existing CSV-update behavior. Define explicit no-match and multiple-match policies. API/database sources and a full reference-data hub remain future extensions. |
| Duplicate detection across submissions | High when repeat imports can create duplicate records | Exact file hashes before extraction and configurable business keys after extraction; surface existing records and allow audited exceptions for corrections. |
| Delivery and extraction quality metrics | Medium; basic delivery visibility belongs in the first delivery release | Extend current reports with delivery backlog, failed attempts, review correction rates, validation failures, and time to accepted delivery. |
| Email, SFTP, or cloud-folder intake | Conditional | Add the source that users actually receive documents through; retain explicit pipeline selection, provenance, and duplicate handling. Existing uploads/watch folders may already suffice. |
| Additional file formats and named ERP/CRM connectors | Conditional | Add images, XML/XLSX, or a specific connector only when a receiving system or intake workflow requires it. JSON/CSV remain sufficient for many integrations. |

## Delivery design notes and agreed n8n boundary

R5 selects n8n as the first receiving integration. The app keeps a stable,
versioned approved-data payload and reliable handoff; n8n owns destination field
mapping, credentials, and connector workflows. The generic options below are
research context, not additional commitments to build an in-app mapping engine
or file-delivery transport. R4 supplies the dynamic review-validation capability.

The [n8n Webhook node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/)
supports authenticated requests and different response stages. The integration
must distinguish workflow acceptance from final destination success and define
duplicate prevention and callbacks. See R5 for the agreed implementation scope.

Treat output mapping, release checks, reliable transport, and delivery status as
one coherent capability. A useful first implementation would:

1. Let an administrator configure an approved n8n webhook destination with a
   versioned payload contract, synthetic-data preview, and a test action. Keep
   app-to-n8n credentials in deployment-owned secret aliases. Configure
   destination-specific mappings and credentials in n8n; prefer deterministic
   transformations over arbitrary executable templates in this app.
2. Release only a final accepted data revision after required validation and
   review. Preserve the approved payload and contract version for reproducible
   retries. A subsequent correction creates a new revision with an explicit
   update/replacement policy.
3. Persist a delivery record together with the accepted revision, then dispatch
   it separately. This durable outbox prevents a successful extraction from
   losing its handoff when the process stops between saving and sending.
4. Support bounded retries, backoff, timeouts, destination rate limits, and
   manual retry of failed deliveries without rerunning OCR. Retry transient
   failures; show permanent payload/authentication errors for correction.
5. Give every delivery a stable idempotency key and record destination IDs or
   receipts. Network ambiguity means a request can arrive more than once;
   require receiving-system deduplication or reconciliation before promising
   duplicate-free records. HTTP acceptance may precede business acceptance, so
   define whether a callback or status check is necessary.
6. Show separate extraction/review and delivery outcomes: a document can be
   extracted successfully while its destination is unavailable. Record safe
   status/error summaries without placing secrets or raw business payloads in
   routine logs or audit events.
7. Associate the delivery with registered PDF/JSON/CSV artifacts. If a remote
   recipient needs a PDF, transfer the file or offer an authenticated retrieval
   mechanism; a Windows local path is not a usable remote document reference.

For file-based receiving systems, the equivalent is a configurable output
package and manifest with correlation IDs and an atomic ready marker, plus
receipt/reconciliation if supported. Choose HTTP or file delivery according to
the first real receiving system. Keep existing standalone JSON/CSV/PDF outputs.

An illustrative target outcome: a reviewed invoice yields a receiver-compatible
record, an attached or retrievable renamed PDF, and a recorded receiver ID.
If the receiver is down, the same accepted payload remains pending and can be
retried without another extraction or duplicate business record.

This capability can work with SQLite; it does not need to wait for PostgreSQL.
Persistence and job-claim contracts must support either backend when R1 lands.
If mixed routing lands first, delivery identity must include each child and
its accepted revision rather than only the source batch.

## Validation, matching, and duplicates

Business checks should be provider-independent and explainable: for example,
line totals equal the header amount within a configured currency tolerance,
and an end date is not earlier than its start date. A high OCR confidence score
does not prove these relationships. Keep extracted, normalized, matched, and
manually corrected values distinguishable, and revalidate after review edits.

Reference matching should preserve both the extracted supplier name and the
resolved target-system supplier ID, with reference version/freshness and match
basis. Never silently select an uncertain fuzzy match. Read-only reference
access is different from changing records in the receiving system.

Duplicate detection needs two levels: byte-identical input and business identity
(for example, supplier ID plus invoice number). A rescan can have different
bytes, and a corrected invoice can legitimately reuse a business key. Configure
scope, pipeline/use case, retention, and audited override behavior rather than
globally discarding every repeat. Resolve concurrency races with authoritative
constraints/transactions, not only a preflight UI check.

## Secondary opportunities and boundaries

Docparser documents [email attachment intake](https://help.docparser.com/hc/en-us/articles/16254793860756-Can-I-import-documents-through-email).
This is useful if staff currently download attachments and upload them again;
it is less valuable when watch folders already cover intake. Confirm mailbox
ownership, supported attachments, and pipeline binding before selecting it.

Rossum's [usage reporting dashboard](https://knowledge-base.rossum.ai/docs/exploring-usage-reporting-dashboard)
documents processing/review measures, including corrections. For this app,
prefer metrics that reveal field correction effort and downstream acceptance.
Correction rate is a proxy; extraction accuracy needs labelled expected values,
including unreviewed documents. Use synthetic or approved anonymized regression
fixtures before changing extraction models, prompts, or schemas.

Keep chat-with-document features, a full document-management platform, payment
execution, broad ERP functionality, and a large connector marketplace outside
the immediate product direction. They have a weaker connection to the stated
extraction-and-handoff aim or require substantial domain-specific ownership.
Retain the serial pipeline editor unless approved routing usability needs
justify further visualization work.

## Follow-on research: additional product features

This second pass, researched on 2026-10-11, considered additional features;
named users, scan-quality checks, and Azure integration have since been accepted
as R6-R8. Sources are official documentation
for UiPath Document Understanding, Automation Anywhere Document Automation, Nanonets, Google
Document AI, and Azure AI Document Intelligence. These are proposals for this
app; only explicitly accepted R6-R8 scope is committed in the roadmap. The
remaining proposals are candidates, and none is a claim of vendor parity.

### Extraction evaluation and regression comparison

Automation Anywhere documents expected-value datasets and comparison across
extraction versions, including field/table-level differences. See
[document evaluation](https://docs.automationanywhere.com/r/da-introduction/da-get-started/learning-instances-overview/da-doc-eval-overview).
UiPath also documents [model-version comparison and field metrics](https://docs.uipath.com/document-understanding/automation-cloud/latest/user-guide/measure).

**Recommendation: high priority.** Maintain approved sample PDFs with expected
values and compare candidate pipeline/model/prompt configurations before
publication. Show scalar differences, missing/extra table rows, cell differences,
runtime, and available cost measures, with defined row-alignment and numeric/date
comparison rules. Isolate evaluation from production and disable external
delivery/reference updates. Use synthetic or approved anonymized fixtures.
Code tests and throughput benchmarks do not establish extraction accuracy.

### Individual users and role-based access

Nanonets documents distinct [user roles](https://docs.nanonets.com/docs/user-role),
including administrators, developers, reviewers, and operators.

**Accepted as R6: named users and role-based access.** This app currently has
two fixed accounts, admin and operator; see
[account administration](../docs/admin/accounts-and-settings.md). Named accounts
would make review claims and audit attribution meaningful for individual people.
Begin with user lifecycle and a small permission model for configuration,
review, and read-only monitoring; add pipeline/queue scope where necessary.
SSO can follow an IT requirement. PostgreSQL alone does not add user management.

### Document-quality checks before extraction

Google Document AI documents rotation correction and page-level quality metrics,
including blur and glare. See [Enterprise Document OCR](https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr).

**Accepted as lower-priority R7: local scan-quality checks.** Explain unreadable pages and
rescan needs before consuming extraction time. Start with inexpensive local
checks and operator warnings; add richer scoring where supported and measured.
Preserve the original PDF and register derivative artifacts. Good image quality
does not establish correct values. Google's detectors do not imply equivalent
capabilities already exist in the local stack. Follow-up
[Python feasibility research](research-scan-quality-and-visual-marks-2026-10-11.md#scan-quality-checks-with-python)
identifies local libraries, a synthetic measurement experiment, and calibration
limits. Richer quality models and automatic image enhancement remain separate
extensions beyond the initial roadmap scope.

### Curated reuse of review corrections

UiPath collects validated documents as retraining candidates and requires review
before admitting them to training. See [retrain extractors](https://docs.uipath.com/document-understanding/automation-cloud/latest/user-guide/retrain-models).

**Recommendation: start with examples, not automatic retraining.** Let an
authorized maintainer promote a corrected document into a labelled regression
set after checking expected values. Group recurring failures by field/document
type to guide prompt/schema changes. Retraining is provider-specific; form edits
do not themselves train current models. Keep holdout samples separate from
training/prompt examples, and require approval before reusing customer data.

### Operational quality and review-effort analytics

UiPath documents validation waiting/handling time, straight-through processing,
field correction trends, and estimated consumption cost. See
[Monitor](https://docs.uipath.com/document-understanding/automation-cloud/latest/user-guide/monitor).

**Recommendation: extend existing reports.** Show queue age, review effort,
frequently corrected fields, outcomes by pipeline version, and n8n delivery
backlog. Instrument actual activity before reporting human effort; elapsed time
with an open review is not necessarily work time. Label cost estimates and
their basis. Correction/automation rates are not accuracy estimates without
representative labelled checks. Basic delivery status already belongs in R5.

### Reviewer groups, assignment, and delegation

Nanonets documents group-based review assignment and delegation while a reviewer
is away. See [user groups and delegated approvals](https://docs.nanonets.com/docs/adding-user-groups-and-delegating-approvals).

**Recommendation: conditional on team scale.** Build on named users and existing
queues with assignment by pipeline/category, priority, and explicit reassignment.
Overdue reminders or second-person approval should follow business policy.
Distinguish verification of extraction from business authorization. R4 warnings
do not establish approval authority. n8n can send notifications while review
ownership and completion remain authoritative in this app.

### Checkboxes and signature-presence fields

Azure AI Document Intelligence documents selection marks and signature detection
in custom neural models. See [model capabilities](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/train/custom-neural?view=doc-intel-4.0.0).

**Azure integration accepted as lower-priority R8.** Signed delivery orders or
insurance forms may need selected options or signature-present results with
page/region evidence. Existing boolean fields do not establish a dedicated
visual detector. Signature presence does not establish signer identity or
authenticity. Confirm provider support and evaluate marked/unmarked samples.
Follow-up [AI feasibility research](research-scan-quality-and-visual-marks-2026-10-11.md#checkbox-and-signature-presence-detection)
distinguishes documented provider capabilities from unverified local-model
behavior. R8 covers optional Azure analysis, including selection marks and
configured trained signature models; alternative local detectors remain
research candidates.

## Recommended discussion order

Named users are now agreed as R6, with scan-quality checks and Azure integration
accepted as lower-priority R7/R8. From the remaining follow-on research,
extraction regression evaluation is the strongest new candidate. Existing business-duplicate proposals
remain valuable before automated delivery creates downstream records. Curated
corrections can feed evaluation first; richer analytics, delegation, and special
local form-mark detection follow measured operational needs.

The eight agreed roadmap items now include CSV enrichment, dynamic review
validation, reliable n8n delivery, named users, scan-quality checks, and Azure
integration. Before scheduling R5, identify
the first receiving system and its acceptance contract. Broader master-data matching
beyond CSV lookup and business-duplicate controls remain candidates according
to that system's requirements. Add intake channels and formats only where
users have an unmet need.

Before promoting candidates into the roadmap, identify the first receiving
system, its API/file contract, required IDs and validations, PDF requirements,
acceptance/acknowledgement behavior, correction policy, and acceptable manual
review effort. Those facts determine a useful first integration far better
than matching another product's feature count.
