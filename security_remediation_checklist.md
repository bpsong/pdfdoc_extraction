# Security Remediation Checklist

Date: 2026-06-06

Source report: `security_best_practices_report.md`

Legend:

- `[x]` Fixed and verified
- `[ ]` Open, not fixed yet
- `Assessed` Reviewed for likelihood/risk, but not remediated
- Effort labels are rough implementation effort from the codebase perspective, not business priority.

## Current Status

- Fixed: 8
- Assessed but not fixed: 0
- Open: 8

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
  - Status: Fixed
  - Needs decision: Which origins are allowed for local/dev/prod.
  - Notes: CORS is now disabled by default for same-origin browser use. Explicit origins can still be configured for a future trusted separate frontend.

- M-03, partial: Add `TrustedHostMiddleware`, disable production docs, and basic security headers.
  - Effort: Easy to medium
  - Value: Medium
  - Needs decision: Allowed hostnames and production environment flag.
  - Notes: A strict CSP and self-hosting CDN assets is medium effort.

- H-03, minimal: Reject oversized requests before `request.body()`.
  - Effort: Easy to medium
  - Value: High
  - Status: Fixed
  - Needs decision: Server-side max upload size and max file count.
  - Notes: Minimal server-side request, per-file, and file-count limits are implemented. Full streaming multipart parsing remains a medium-effort follow-up.

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
  - Status: Fixed
  - Notes: Implemented in-memory throttling for repeated failed logins. Distributed deployments still need shared storage such as Redis.

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
  - Status: Fixed
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
  - Status: Fixed
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

- [x] H-03: Upload and Request Body Memory Exhaustion
  - Status: Fixed and verified
  - Effort: Completed for minimal fix; medium for future streaming parser refactor
  - Primary location: `modules/api_router.py`
  - Likelihood: Medium overall; higher in exposed deployments with authenticated users or stolen tokens.
  - Impact: High if triggered because the server reads full multipart bodies into memory before parsing.
  - Fix summary: Added server-side upload limits before multipart body reads when `Content-Length` is available, plus post-read request-size validation, per-file size validation, and max file-count validation.
  - Default limits:
    - `web.max_upload_mb`: 50 MB per file
    - `web.max_upload_files`: 20 files
    - `web.max_upload_request_mb`: 125% of per-file limit times max file count, unless explicitly configured
  - Verification:
    - `C:\Python313\python.exe -m py_compile modules\api_router.py`
    - `C:\Python313\python.exe -m pytest -v test\integration\test_batch_upload_api.py test\integration\test_input_processing.py`

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

- [x] M-02: Permissive CORS With Credentials
  - Status: Fixed and verified
  - Effort: Completed
  - Primary location: `web/server.py`
  - Fix summary: Removed wildcard credentialed CORS as the default. CORS middleware is now installed only when `web.cors_allowed_origins` is explicitly configured.
  - User experience: No visible change for normal users accessing the webapp directly in the browser from the same origin.
  - Verification:
    - `C:\Python313\python.exe -m py_compile web\server.py`
    - `C:\Python313\python.exe -m pytest -v test\integration\test_new_ui_routes.py test\integration\test_api_endpoints.py`

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

- [x] M-07: No Login Rate Limiting or Account Throttling
  - Status: Fixed and verified
  - Effort: Completed for single-process in-memory throttling
  - Primary locations:
    - `web/server.py`
    - `modules/api_router.py`
    - `modules/auth_utils.py`
  - Fix summary: Added shared in-memory failed-login throttling keyed by username and client address. Both `/login` and `/api/login` return 429 after repeated failed attempts, and successful login clears prior failures.
  - Default limits:
    - `auth.login_rate_limit_enabled`: true
    - `auth.login_max_failed_attempts`: 5
    - `auth.login_window_seconds`: 600
    - `auth.login_cooldown_seconds`: 600
  - Verification:
    - `.\.venv\Scripts\python.exe -m pytest -v test\security\test_security_logging.py test\integration\test_api_endpoints.py test\integration\test_new_ui_routes.py`
    - `.\.venv\Scripts\python.exe -m pytest -v`

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

- [x] L-03: Dependency Hygiene Needs a Dedicated Project Environment
  - Status: Fixed and verified
  - Effort: Completed
  - Primary location: `requirements.txt`
  - Fix summary: Created a project-local `.venv`, installed dependencies from `requirements.txt`, and added missing explicit `pytest-mock` test dependency so the suite no longer relies on globally installed packages.
  - Verification:
    - `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
    - `.\.venv\Scripts\python.exe -m pytest -v`
    - Venv-backed browser smoke test on `http://127.0.0.1:8765/login` and authenticated `/app/upload`.

## Next Recommended Fixes

If optimizing for lowest effort:

1. M-05: Apply safe schema-name validation to reads.
2. M-04: Add PDF base-directory checks.
3. M-03 partial: Add deployment hardening controls with careful host config.

If optimizing for risk reduction:

1. H-01: Stored XSS in the legacy dashboard.
2. H-04: Move secrets out of YAML and rotate exposed keys.
3. M-01: Add CSRF protection or split cookie-auth HTML from bearer-auth API mutations.
4. M-05: Apply safe schema-name validation to reads.

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

## Latest H-03 Verification

- Date: 2026-06-09
- Targeted upload tests: `C:\Python313\python.exe -m pytest -v test\integration\test_batch_upload_api.py test\integration\test_input_processing.py`
- Result: 13 passed, 2 warnings
- Full suite attempt: `C:\Python313\python.exe -m pytest -v`
- Result: 511 passed, 4 skipped, 1 failed, 41 warnings
- Full-suite failure note: The failing test was `test/third_party/llamacloud_connection_test.py::test_llamacloud_connection`, caused by a live LlamaCloud configuration lookup returning 404. The failure is unrelated to the H-03 upload-limit changes.

## Latest M-02 Verification

- Date: 2026-06-09
- Targeted CORS/UI tests: `C:\Python313\python.exe -m pytest -v test\integration\test_new_ui_routes.py test\integration\test_api_endpoints.py`
- Result: 26 passed, 29 warnings
- Config/docs follow-up: Added `web.cors_allowed_origins: []` to all YAML config files with a `web:` section, documented the setting under the admin guide, and added config-check schema validation for explicit origins and wildcard rejection.
- Config/docs focused tests: `C:\Python313\python.exe -m pytest -v test\tools\config_check\test_schema_validation.py test\integration\test_new_ui_routes.py test\tools\config_check\test_integration.py`
- Result: 58 passed, 28 warnings
- Full suite attempt: `C:\Python313\python.exe -m pytest -v`
- Result: 517 passed, 4 skipped, 1 failed, 41 warnings
- Full-suite failure note: The failing test was `test/third_party/llamacloud_connection_test.py::test_llamacloud_connection`, caused by a live LlamaCloud configuration lookup returning 404. The failure is unrelated to the M-02 CORS changes.

## Latest L-03 Verification

- Date: 2026-06-10
- Environment setup: `C:\Python313\python.exe -m venv .venv`
- Dependency install: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Full suite: `.\.venv\Scripts\python.exe -m pytest -v`
- Result: 518 passed, 4 skipped, 40 warnings
- Dependency note: The first isolated run exposed missing `pytest-mock`; it is now declared in `requirements.txt`.
- Visual smoke test:
  - Started Uvicorn from `.venv\Scripts\python.exe` on `http://127.0.0.1:8765`.
  - Verified `/login` rendered, logged in as `admin`, and confirmed `/app/upload` loaded.
  - Screenshot artifact: `output/playwright/l03-venv-upload-smoke.png`

## Latest M-07 Verification

- Date: 2026-06-10
- Focused tests: `.\.venv\Scripts\python.exe -m pytest -v test\security\test_security_logging.py test\integration\test_api_endpoints.py test\integration\test_new_ui_routes.py`
- Result: 31 passed, 32 warnings
- Full suite: `.\.venv\Scripts\python.exe -m pytest -v`
- Result: 522 passed, 4 skipped, 43 warnings
- Note: No visual test was run because the normal successful login flow and page rendering are unchanged; behavior is verified through endpoint and AuthUtils tests.
