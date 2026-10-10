# API contracts and compatibility

| Item | Value |
| --- | --- |
| Audience | Developers and IT support |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
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
