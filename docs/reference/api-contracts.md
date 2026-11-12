# API contracts and compatibility

| Item | Value |
| --- | --- |
| Audience | Developers and IT support |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-11-11 — repository/source review; no live deployment check; catalog permissions, separate review labels, and isolated API/browser regressions |
| Applies to | Production application; SQLite schema 9 |

## Discovery, authentication and request safety

The [router](../../modules/api_router.py) is the source for implemented request
and response models. Non-production deployments normally expose `/docs`,
`/redoc` and `/openapi.json`; production disables them unless explicitly enabled.
Use an isolated deployment for API exploration, not production credentials/data.

Browser authentication uses signed cookies and fixed admin/operator roles.
Cookie-authenticated protected writes require the CSRF cookie and matching
`X-CSRF-Token` header. Preserve existing role/CSRF checks and same-origin preview
restrictions. Authentication failures and service/domain conflicts remain
distinct; inspect the endpoint model before treating an error as retryable.

## Primary API families

| Area | Implemented surface |
| --- | --- |
| Upload acceptance | `POST /api/batches/upload` and upload-submission receipts |
| Processing | Batch/document state, task timelines and registered artifacts |
| Review | Review items, claims, corrections, completion and split decisions |
| Reports/failures | Processing summaries and failure investigation |
| Administration | Pipeline templates/drafts/versions, review forms, bindings and audit |
| Health | `/health/live`, `/health/ready`, `/api/admin/runtime-health` |

Follow [execution walkthroughs](../developer/execution-walkthroughs.md) for
request-to-service ownership. OpenAPI/source models are authoritative for
endpoints not expanded below; this page is not a substitute for those models.

## Approved business-rule catalog

`GET /api/admin/business-validators` requires authentication and the admin role
(unauthenticated: 401; operator: 403). It returns `catalog_version: 1`,
`common_controls`, and `validators`. Each validator has an exact `id`, neutral
`title`, `description`, `category`, optional collection/condition metadata, and
`controls`. Controls describe supported widget kinds, names, defaults, field
types/scopes, choices, bounds, and literal visibility conditions. This read-only
projection contains no Python module paths, executable expressions, or user data.
It does not publish forms or change saved rule content. See the
[descriptor contract](../developer/business-validation-plugins.md#describe-generic-editor-controls).

## Business validation on extraction reviews

`GET /api/review/items/{id}` includes `review_revision` and a
`business_validation` report for current displayed values, including saved drafts.
Completed items return the durable accepted report. Report identities include
the exact form version/hash/format, validator versions, document, extraction,
source artifacts, and values revision. Forms without rules return a null report.
Extraction detail and revalidation responses also include top-level
`business_validation_labels`, an identifier-to-title map for operator display.
It is separate from the report and is never included in accepted report evidence,
form hashes, or saved rules. Operators need no access to the admin catalog.
Clients fall back to an identifier when its label is absent.

`POST /api/review/items/{id}/revalidate` accepts `corrections` (a JSON object),
`expected_revision` (from detail), and optional `request_revision` (string or
integer, at most 128 characters). It returns `review_revision`, the echoed
`request_revision`, `business_validation`, and `schema_errors`. Corrections are
top-level replacements, using the same merge/defaults as completion; include all
current edits, including restored draft values. This operation requires a live
claim owned by the authenticated user, preserves CSRF protection, and rejects
manual-split/closed reviews. It does not save, extend a lock, audit each read,
rerun OCR, or resume the workflow.

The production review screen applies replies only when the request tag, local
edit generation/value snapshot, review revision, and exact form ID/hash still
match. Value and row changes clear stale annotations. Revalidation leaves the
inputs in place; draft saving retains any newer edits made during the save.
Completion remains an independent server check regardless of browser findings.

`/draft` and `/complete` also accept `expected_revision`. It is mandatory for
business-rule forms and optional for legacy forms; a supplied stale token always
fails. Missing/stale revisions return HTTP 409 with a structured `detail` containing
`message`, `code` (`review_revision_required` or `stale_review`), and
`current_revision`. Reload before retrying. Completion independently evaluates the
submitted values and returns HTTP 422 with `business_validation` for blocking or
schema findings. Incompatible or structurally invalid pinned forms return HTTP
422 with `code: review_schema_unavailable`. Other ownership/state conflicts
retain the existing 409 contract. Accepted corrections/report, task/review/
document state, and audit summary commit atomically before resume.

## Manual split decisions

`POST /api/review/items/{id}/split/draft` accepts `boundaries` and
`expected_revision`. Completion at `/split/complete` also requires `action`
(`split` or `skip`). `/split/retry` has bounded continuation semantics.
All are authenticated and CSRF-protected; the first two require the current
claim/revision. The browser cannot supply output paths or child identities.

Completion returns HTTP 202 with `resume_scheduled: true` after committing the
decision. Background continuation is in-process and follows the pinned split
task. Acceptance is not completed downstream processing; see
[split recovery contracts](tasks/splitting.md).

## API contract

All routes below require the fixed `admin` role. Cookie-authenticated POSTs
require the existing CSRF cookie and matching `X-CSRF-Token` header. The prefix is
`/api/admin/pipeline-templates/{template_id}`.

| Method and suffix | JSON request | Successful response |
| --- | --- | --- |
| `GET /archive-preview` | None | `template`, `counts`, `bindings`, `blockers`, `can_archive` |
| `POST /archive` | `{"confirmation_name":"Exact pipeline name"}` | `template` with archived status |
| `POST /cleanup-preview` | `{"cutoff_date":"2026-01-01"}` | `preview_id`, `expires_at`, `template_name`, `cutoff_date`, `counts`, `excluded` |
| `POST /cleanup` | `{"preview_id":"UUID from preview","confirmation_name":"Exact pipeline name"}` | `deleted`, `excluded`, `audit_event_id`, `receipts_tombstoned`, `files_deleted: 0`, `compacted: false` |

Archive `counts` includes `pipeline_versions`, `batches`, `documents`,
`active_jobs`, and `pending_reviews`; its binding entries include ID, folder path,
enabled state, and retirement timestamp.

Cleanup `counts` uses table names: `batches`, `documents`, `processing_jobs`, `task_runs`,
`extraction_results`, `extracted_fields`, `review_items`, `review_locks`,
`manual_split_decisions`, `document_files`, and `upload_submissions`. Receipts
are trimmed, not deleted; the result reports them separately from `deleted`.
`excluded` has `pending_review`, `active_work`, `recent_activity`, and
`inconsistent_history`, each with `batches` and `documents` counts.

Errors return `400` for invalid cutoff/name/input, `401` for missing/invalid
authentication, `403` for role/CSRF denial, `404` for an unknown pipeline, and
`409` for archive blockers, stale/expired/unavailable previews, no eligible
history, or retained record references. No delete endpoint exists for pipelines.

`GET /api/admin/pipeline-templates` excludes archived templates unless
`include_archived=true`. `GET /api/upload-submissions/{submission_id}` returns
`{"status":"purged"}` for a cleaned receipt. Reusing that identity does not
create another batch; start a new upload with a new idempotency key.


## Compatibility surfaces

`/api/files` and `/api/status/{file_id}` are SQLite-backed compatibility
response shapes. New workflow/UI features use the current primary APIs and
`/app/*` pages. Legacy `/app/admin/review-gate` and `/app/admin/split` links
redirect to Pipeline; they do not represent separate configurable workflows.
Compatibility timestamps without offsets are treated as UTC before Singapore
display; explicit source offsets are preserved for conversion.
