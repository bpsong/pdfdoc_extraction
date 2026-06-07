# Security Remediation Checklist

Date: 2026-06-06

Source report: `security_best_practices_report.md`

Legend:

- `[x]` Fixed and verified
- `[ ]` Open, not fixed yet
- `Assessed` Reviewed for likelihood/risk, but not remediated
- Effort labels are rough implementation effort from the codebase perspective, not business priority.

## Current Status

- Fixed: 4
- Assessed but not fixed: 1
- Open: 11

## Effort Highlights

### Quick Code-Only Fixes

These are the easiest from a code/effort perspective and should be low-risk to review:

- H-05, partial: Remove password hash logging and raw extraction payload logging.
  - Effort: Easy
  - Value: High
  - Status: Fixed
  - Notes: Direct sensitive log sinks were removed. A broader reusable redaction filter remains a separate medium-effort improvement.

- L-01: Remove localStorage token fallback.
  - Effort: Easy
  - Value: Low to medium
  - Status: Fixed
  - Notes: `StatusHelpers.authFetch()` was kept for compatibility, but it now uses cookie-based same-origin requests and no longer reads/writes localStorage.

- L-02: Prevent development reload in production.
  - Effort: Easy
  - Value: Low
  - Status: Fixed
  - Notes: `USE_RELOAD` is ignored when `APP_ENV`, `ENV`, or `ENVIRONMENT` is `production` or `prod`.

- M-05: Sanitize schema names for reads as well as writes.
  - Effort: Easy to medium
  - Value: Medium
  - Notes: Existing `_safe_schema_name()` gives a clear pattern.

- M-04: Add a base-directory check before serving PDF paths.
  - Effort: Easy to medium
  - Value: Medium
  - Notes: Add `Path.resolve()` and allowed-root validation plus a focused test.

### Easy With a Small Config or Deployment Decision

- M-02: Replace permissive CORS with an explicit allowlist.
  - Effort: Easy
  - Value: Medium
  - Needs decision: Which origins are allowed for local/dev/prod.

- M-03, partial: Add `TrustedHostMiddleware`, disable production docs, and basic security headers.
  - Effort: Easy to medium
  - Value: Medium
  - Needs decision: Allowed hostnames and production environment flag.
  - Notes: A strict CSP and self-hosting CDN assets is medium effort.

- H-03, minimal: Reject oversized requests before `request.body()`.
  - Effort: Easy to medium
  - Value: High
  - Needs decision: Server-side max upload size and max file count.
  - Notes: Full streaming multipart parsing is a medium-effort follow-up.

### Medium or Higher Effort

- H-01: Stored XSS in legacy dashboard.
  - Effort: Medium
  - Value: High
  - Notes: The code changes are straightforward, but the UI needs regression testing because it touches table/modal rendering.

- M-01: CSRF protection or cookie-vs-bearer auth split.
  - Effort: Medium
  - Value: Medium to high
  - Notes: Touches many mutating endpoints and frontend callers.

- M-07: Login rate limiting.
  - Effort: Medium
  - Value: Medium
  - Notes: Needs a storage decision for failed attempts if multiple workers are used.

- H-04: Move secrets out of YAML and rotate exposed keys.
  - Effort: Medium
  - Value: High
  - Notes: Code changes are modest, but rotation and local deployment migration make it operational work.

- M-08: FastAPI/Starlette upgrade for FileResponse DoS advisory.
  - Effort: Medium to high
  - Value: Medium
  - Notes: Requires dependency compatibility testing.

- M-06: Restrict dynamic task imports.
  - Effort: Medium to high
  - Value: Medium to high
  - Notes: Requires a product/security decision about whether admins are trusted as code operators.

## Regression Risk For Easiest Fixes

### Lowest Bug Risk

- H-05, partial: Remove password hash logging.
  - Regression risk: Very low
  - Status: Fixed
  - Why: These debug lines do not appear to be used by tests or application behavior.
  - Possible downside: Less diagnostic detail when debugging authentication setup.
  - Suggested test: Existing auth tests plus a simple log-capture test that confirms password hashes are not emitted.

- L-01: Remove localStorage token fallback.
  - Regression risk: Very low
  - Status: Fixed
  - Why: `web/static/js/status.js` is not referenced by templates or tests, and current auth uses an HttpOnly cookie.
  - Possible downside: Any untracked/manual page depending on `window.StatusHelpers.authFetch()` would break.
  - Suggested test: Run UI route tests and search templates for `status.js` or `StatusHelpers` before removal.

- L-02: Guard development reload in production.
  - Regression risk: Low
  - Status: Fixed
  - Why: `USE_RELOAD` only affects how `main.py` starts Uvicorn.
  - Possible downside: A developer who sets a production-like env locally may lose auto-reload unexpectedly.
  - Suggested test: Unit-test the reload decision for dev and production env values, or keep the guard small and explicit.

### Low To Medium Bug Risk

- H-05, partial: Stop logging raw extracted data.
  - Regression risk: Low
  - Status: Fixed
  - Why: The log line is not part of core data flow.
  - Possible downside: Harder to debug extraction mapping problems from logs alone.
  - Safer fix shape: Log document ID, job ID, field keys, and counts instead of raw payload values.
  - Suggested test: Existing extraction tests should pass unchanged; add a log-capture test if redaction behavior is important.

- M-02: Replace wildcard CORS with explicit allowed origins.
  - Regression risk: Low to medium
  - Why: Same-origin browser usage should keep working, but any separate frontend host, alternate localhost port, or browser automation using cross-origin requests may fail.
  - Possible downside: Development workflows break if allowed origins are too strict.
  - Safer fix shape: Default to no CORS in production, allow common localhost origins in dev, and read extra origins from config.
  - Suggested test: Add a TestClient CORS preflight test for an allowed origin and a disallowed origin.

- M-05: Sanitize schema names for reads as well as writes.
  - Regression risk: Low to medium
  - Why: The intended UI/API already uses file names like `invoice.yaml`, but pipeline config may currently reference schema paths.
  - Possible downside: Existing configs that use absolute schema paths or subdirectory paths stop loading.
  - Safer fix shape: Apply strict file-name validation only to web/API-supplied schema names first; handle pipeline config separately if path-based schemas are a supported feature.
  - Suggested test: Add tests for `invoice.yaml` success and absolute path, `..`, slash, and backslash rejection through API/service calls.

- M-04: Add a base-directory check before serving PDF paths.
  - Regression risk: Low to medium
  - Why: Normal uploaded documents should live under configured processing/storage directories, but older records or custom tasks may store paths elsewhere.
  - Possible downside: Existing documents with source files outside allowed roots become unavailable through the PDF endpoint.
  - Safer fix shape: Start with an allowlist including current configured upload, processing, watch, and app storage roots; log rejected paths without returning the raw path.
  - Suggested test: One allowed-path PDF response test, one outside-root rejection test, and one missing-file test.

### Medium Bug Risk Despite Easy-Looking Code

- H-03, minimal: Reject oversized requests before `request.body()`.
  - Regression risk: Medium
  - Why: The check is simple, but request-size semantics are tricky for multipart batches, missing `Content-Length`, reverse proxies, and clients that use chunked transfer.
  - Possible downside: Legitimate batch uploads may be rejected if the limit is per-request but users expect it to be per-file. Tests may also need to set or account for generated multipart overhead.
  - Safer fix shape: Define both `max_upload_mb_per_file` and `max_upload_request_mb`; reject clearly with 413; keep the existing UI limit in sync with server config.
  - Suggested test: Batch upload under limit succeeds, over-limit request returns 413 before parsing, missing or invalid `Content-Length` behavior is explicit.

- M-03, partial: Add trusted hosts, production docs controls, and basic headers.
  - Regression risk: Medium
  - Why: Host validation can reject local aliases, LAN IP access, reverse proxy hostnames, or TestClient requests if not configured carefully.
  - Possible downside: Deployed app appears down behind a proxy even though Uvicorn is running.
  - Safer fix shape: Add middleware only when configured or in production mode; include `localhost`, `127.0.0.1`, and the configured `web.host` for dev.
  - Suggested test: Test allowed host succeeds, unknown host returns 400, docs are available in dev and disabled/protected in production.

## High Severity

- [ ] H-01: Stored XSS in Legacy Dashboard Rendering
  - Status: Open
  - Effort: Medium
  - Primary location: `web/templates/dashboard.html`
  - Notes: Not fixed yet.

- [x] H-02: Config-Driven `eval()` in Legacy PDF Extraction
  - Status: Fixed and verified
  - Effort: Completed
  - Primary locations:
    - `standard_step/extraction/extract_pdf.py`
    - `tools/llamacloud_extract_smoke.py`
    - `test/extraction/test_extraction.py`
  - Fix summary: Replaced `eval()` with an allowlisted parser for supported field type strings and added a regression test proving malicious type strings are rejected without execution.
  - Verification:
    - `C:\Python313\python.exe -m pytest -v test\extraction\test_extraction.py`
    - `C:\Python313\python.exe -m py_compile standard_step\extraction\extract_pdf.py tools\llamacloud_extract_smoke.py`
    - `rg -n "eval\(" . --glob "!security_best_practices_report.md"`

- [ ] H-03: Upload and Request Body Memory Exhaustion
  - Status: Assessed, not fixed
  - Effort: Easy to medium for a minimal limit; medium for streaming parser refactor
  - Primary location: `modules/api_router.py`
  - Likelihood: Medium overall; higher in exposed deployments with authenticated users or stolen tokens.
  - Impact: High if triggered because the server reads full multipart bodies into memory before parsing.
  - Notes: Upload endpoints require authentication before parsing, which reduces anonymous exposure. Client-side upload limits are bypassable and do not protect the server.

- [ ] H-04: Secrets in Local YAML and Weak Default JWT Secret
  - Status: Open
  - Effort: Medium
  - Primary location: `config.yaml`
  - Notes: Not fixed yet. Do not copy secret values into tickets, logs, or reports.

- [x] H-05: Sensitive Values Written to Logs
  - Status: Fixed and verified
  - Effort: Completed
  - Primary locations:
    - `modules/auth_utils.py`
    - `standard_step/extraction/extract_pdf.py`
    - `standard_step/extraction/extract_pdf_v2.py`
  - Fix summary: Removed password-hash logging and replaced raw extraction-result logging with non-sensitive job/field-count summaries.
  - Verification:
    - `C:\Python313\python.exe -m pytest -v test\security\test_security_logging.py test\test_main_reload.py test\extraction\test_extraction.py test\extraction\test_extraction_v2.py`
    - `C:\Python313\python.exe -m pytest -v`
    - Static search for removed sensitive patterns.

## Medium Severity

- [ ] M-01: Cookie Authentication Without CSRF Protection on Mutating Endpoints
  - Status: Open
  - Effort: Medium
  - Primary locations:
    - `web/server.py`
    - `modules/api_router.py`
  - Notes: Not fixed yet.

- [ ] M-02: Permissive CORS With Credentials
  - Status: Open
  - Effort: Easy
  - Primary location: `web/server.py`
  - Notes: Not fixed yet.

- [ ] M-03: Missing Trusted Host, Security Headers, and Production Docs Controls
  - Status: Open
  - Effort: Easy to medium
  - Primary locations:
    - `web/server.py`
    - `web/templates/app_base.html`
  - Notes: Not fixed yet.

- [ ] M-04: FileResponse Serves Paths From Document Metadata Without a Base-Directory Check
  - Status: Open
  - Effort: Easy to medium
  - Primary location: `modules/api_router.py`
  - Notes: Not fixed yet.

- [ ] M-05: Admin Schema Names Can Resolve Outside Schema Directories
  - Status: Open
  - Effort: Easy to medium
  - Primary locations:
    - `modules/services/schema_service.py`
    - `modules/api_router.py`
  - Notes: Not fixed yet.

- [ ] M-06: Dynamic Task Imports Are an Admin RCE Boundary
  - Status: Open
  - Effort: Medium to high
  - Primary locations:
    - `modules/workflow_loader.py`
    - `modules/services/pipeline_config_service.py`
  - Notes: Not fixed yet.

- [ ] M-07: No Login Rate Limiting or Account Throttling
  - Status: Open
  - Effort: Medium
  - Primary locations:
    - `web/server.py`
    - `modules/api_router.py`
    - `modules/auth_utils.py`
  - Notes: Not fixed yet.

- [ ] M-08: Starlette Version Has File Response DoS Advisory
  - Status: Open
  - Effort: Medium to high
  - Primary locations:
    - `requirements.txt`
    - `modules/api_router.py`
    - `web/server.py`
  - Notes: Not fixed yet. Requires compatible FastAPI/Starlette upgrade planning.

## Low Severity

- [x] L-01: LocalStorage Token Helper Should Be Removed
  - Status: Fixed and verified
  - Effort: Completed
  - Primary location: `web/static/js/status.js`
  - Fix summary: Removed localStorage token access while keeping `StatusHelpers.authFetch()` as a cookie-auth compatible helper.
  - Verification:
    - `C:\Python313\python.exe -m pytest -v`
    - Browser smoke test on `http://127.0.0.1:8765/login` and protected route redirect.

- [x] L-02: Development Reload Can Be Enabled by Environment
  - Status: Fixed and verified
  - Effort: Completed
  - Primary location: `main.py`
  - Fix summary: Added `_should_use_reload()` and disabled reload when production environment markers are present.
  - Verification:
    - `C:\Python313\python.exe -m pytest -v test\test_main_reload.py`
    - `C:\Python313\python.exe -m pytest -v`

- [ ] L-03: Dependency Hygiene Needs a Dedicated Project Environment
  - Status: Open
  - Effort: Medium
  - Primary location: `requirements.txt`
  - Notes: Not fixed yet.

## Next Recommended Fixes

If optimizing for lowest effort:

1. M-02: Replace wildcard CORS with an explicit allowlist.
2. M-05: Apply safe schema-name validation to reads.
3. M-04: Add PDF base-directory checks.
4. H-03 minimal: Enforce request size and file count before body reads.
5. M-03 partial: Add deployment hardening controls with careful host config.

If optimizing for risk reduction:

1. H-01: Stored XSS in the legacy dashboard.
2. H-03: Server-side request and upload size enforcement.
3. H-04: Move secrets out of YAML and rotate exposed keys.
4. M-01: Add CSRF protection or split cookie-auth HTML from bearer-auth API mutations.
5. M-02: Replace wildcard CORS with an explicit allowlist.

## Latest Verification

- Date: 2026-06-06
- Full suite: `C:\Python313\python.exe -m pytest -v`
- Result: 496 passed, 4 skipped, 41 warnings
- Note: A Prefect temporary-server logging cleanup message appeared after pytest completed, but the pytest run exited successfully.
- Visual smoke test:
  - Started Uvicorn on `http://127.0.0.1:8765`.
  - Verified `/login` rendered with username/password fields and submit button.
  - Verified `/app/upload` redirected unauthenticated users back to `/login`.
  - Browser console errors: none observed.
