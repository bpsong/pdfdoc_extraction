# Security and trust boundaries

| Item | Value |
| --- | --- |
| Audience | Software architects and technical leads |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## API, authentication, and trust boundaries

`modules/api_router.build_router()` composes APIs for authentication, uploads,
batches, documents, extraction, review, split results, failures, reports,
administrator settings, schemas, pipeline administration, users, audit, and
legacy compatibility.

Endpoints should validate requests, enforce authorization, call services, and
construct responses. Cross-table invariants belong in services. A router-wide
dependency protects cookie-authenticated mutations with CSRF checks;
Bearer-token callers are exempt from the cookie-specific check.

The current identity model has fixed `admin` and `operator` accounts. SQLite
stores role, bcrypt password hash, token version, and password timestamps.
JWT validation compares subject, role, and token version with the current user
row, so password changes can revoke sessions. Login throttling is in-memory
and therefore process-local.

The route surface uses two roles. `operator` can use processing, upload, and
review workflows; `admin` can additionally manage users, settings, pipelines,
review schemas, watch folders, and audit data. Cookie-authenticated mutations
require CSRF validation; GET requests do not. Bearer-token callers are exempt
from the cookie-specific CSRF check. Representative route groups:

| Route group | Operator | Admin | CSRF for cookie auth |
| --- | --- | --- | --- |
| `/api/batches/*`, `/api/documents/*`, `/api/processing-state` | Yes, subject to document authorization | Yes | Mutations only |
| `/api/review/*` | Yes, subject to item/lock rules | Yes, subject to item/lock rules | Mutations only |
| `/api/batches/upload`, `/api/upload-submissions/*` | Yes, owner-scoped receipt | Yes, owner-scoped receipt | Upload mutation |
| `/api/admin/*`, `/api/schemas/*` | No | Yes | Mutations only |
| `/api/config/validation` | No | Yes | Mutations only |
| `/api/pipeline/validate` | Authenticated | Authenticated | Mutations only |
| `/api/login`, `/api/session/refresh` | Public/session flow | Public/session flow | Endpoint-specific session protections |
| Legacy `/api/files`, `/api/status/*` | Authenticated compatibility surface | Authenticated compatibility surface | Mutations not supported |

This is a route-family guide, not a substitute for endpoint dependencies and
document-level checks. Confirm exact behavior in `modules/api_router.py` when
changing a route; preserve its authorization and CSRF dependencies.

Principal trust boundaries are:

- Uploaded PDFs are untrusted and receive only minimal signature validation.
- Dynamic task imports must match approved registrations.
- Schema paths must remain under configured roots.
- Extracted values are untrusted when rendered or used in filenames/exports.
- Provider credentials and responses require redaction.
- Protected document files must be resolved through authorized APIs.

## Browser security

- JWT access tokens use an HTTP-only cookie.
- Login and CSRF cookies use `Secure` in production; development HTTP remains
  available without the production environment flag.
- Cookie-authenticated mutations require a CSRF cookie and matching
  `X-CSRF-Token` header.
- Page routes and APIs enforce roles server-side; hidden navigation is not an
  authorization control.
- Deployment-config validation APIs require an administrator and redact deployment
  secrets before serializing results; the CLI retains full validation data.
- API requests are same-origin by default; CORS requires explicit trusted
  origins.
- Trusted-host, CSP, content-type, referrer, permissions, and frame headers
  are applied globally.
- Normal pages deny framing; the review workspace fetches same-origin PDF
  responses for its local PDF.js viewer.


## Local-provider boundary

LiteParse accepts credential-free HTTP loopback Ollama endpoints, rejects
cloud-backed models, redirects and environment proxies, and isolates parsing
behind a deadline. These checks apply to this provider; a later cloud task is
still a separate egress decision. Preserve provider-specific restrictions when
changing adapters. See [LiteParse](../reference/tasks/liteparse-extraction.md).

## Review and split decisions

Claims and revision checks protect concurrent edits. A manual split decision
commits before continuation is dispatched. Continuation is an in-process
background task with bounded recovery, not a durable exactly-once dispatch
guarantee. The browser cannot choose output paths or child identities.
See [split contracts](../reference/tasks/splitting.md).
