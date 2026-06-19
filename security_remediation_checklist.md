# Security Remediation Checklist

> Authentication update: current credentials and roles are stored in SQLite for the fixed `admin` and `operator` accounts. Older YAML-credential references below are retained as remediation history, not current operating instructions.

Date: 2026-06-06

Source report: `security_best_practices_report.md`

Legend:

- `[x]` Fixed and verified
- `[ ]` Open, not fixed yet
- `Assessed` Reviewed for likelihood/risk, but not remediated
- Effort labels are rough implementation effort from the codebase perspective, not business priority.

## Current Status

- Fixed: 15
- Assessed but not fixed: 0
- Open: 1

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
  - Status: Fixed
  - Notes: Schema reads now resolve only under configured schema directories.

- M-04: Add a base-directory check before serving PDF paths.
  - Effort: Easy to medium
  - Value: Medium
  - Status: Fixed
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
  - Status: Fixed for the stated partial scope
  - Needs decision: Allowed hostnames and production environment flag.
  - Notes: Trusted hosts, production docs controls, and baseline headers are implemented. A strict CSP and self-hosting CDN assets remain a separate medium-effort improvement.

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
  - Status: Fixed
  - Notes: Legacy HTML dashboard/upload pages are retired, and the new Reports batch modal renders task-run details with escaped content.

- M-01: CSRF protection or cookie-vs-bearer auth split.
  - Effort: Medium
  - Value: Medium to high
  - Status: Fixed
  - Notes: Cookie-authenticated mutating requests now require a matching CSRF header. Bearer-token API clients remain unchanged.

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
  - Status: Fixed
  - Notes: FastAPI was upgraded and Starlette now resolves above the advisory fix floor.

- M-06: Restrict dynamic task imports.
  - Effort: Medium to high
  - Value: Medium to high
  - Status: Fixed
  - Notes: Active pipeline task imports are now limited to approved built-in tasks or deployment-registered `custom_step.*` tasks.

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
  - Status: Fixed
  - Why: The intended UI/API already uses file names like `invoice.yaml`, but pipeline config may currently reference schema paths.
  - Possible downside: Existing configs that use absolute schema paths outside configured schema directories stop loading.
  - Safer fix shape: Allow filenames, configured-relative paths, and absolute paths only when the resolved path stays under a configured schema directory.
  - Suggested test: Add tests for `invoice.yaml` success, configured-relative path success, allowed absolute path success, and outside-root absolute or `..` rejection through service calls.

- M-04: Add a base-directory check before serving PDF paths.
  - Regression risk: Low to medium
  - Status: Fixed
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

- [x] H-01: Stored XSS in Legacy Dashboard Rendering
  - Status: Fixed and verified
  - Effort: Completed
  - Primary locations:
    - `web/server.py`
    - `web/templates/reports.html`
    - `web/static/js/reports.js`
  - Fix summary: Retired the legacy dashboard/upload HTML rendering path, redirected old page routes to the unified app, removed obsolete legacy templates, and added a Reports batch-detail modal that escapes persisted task-run data before display.
  - Verification:
    - `.\.venv\Scripts\python.exe -m pytest -v`
    - `node --check web\static\js\reports.js`
    - Browser visual check on `http://127.0.0.1:8765/dashboard` confirmed redirect to `/app/reports` and a readable Recent Batches task-run detail modal.

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

- [x] M-01: Cookie Authentication Without CSRF Protection on Mutating Endpoints
  - Status: Fixed and verified
  - Effort: Completed
  - Primary locations:
    - `web/server.py`
    - `modules/api_router.py`
    - `web/static/js/app.js`
    - `web/static/js/upload_process.js`
  - Fix summary: Added double-submit CSRF protection for browser cookie authentication. Mutating requests using the `access_token` cookie must include a matching `X-CSRF-Token` header from the `csrf_token` cookie; Authorization-header bearer clients are exempt.
  - User experience: Normal browser users should not see a change. Login sets the CSRF cookie, and authenticated app pages mint it for older sessions if missing.
  - Verification:
    - `.\.venv\Scripts\python.exe -m py_compile modules\api_router.py web\server.py`
    - `.\.venv\Scripts\python.exe -m pytest -q test\integration\test_batch_upload_api.py test\integration\test_api_endpoints.py test\integration\test_new_ui_routes.py`

- [x] M-02: Permissive CORS With Credentials
  - Status: Fixed and verified
  - Effort: Completed
  - Primary location: `web/server.py`
  - Fix summary: Removed wildcard credentialed CORS as the default. CORS middleware is now installed only when `web.cors_allowed_origins` is explicitly configured.
  - User experience: No visible change for normal users accessing the webapp directly in the browser from the same origin.
  - Verification:
    - `C:\Python313\python.exe -m py_compile web\server.py`
    - `C:\Python313\python.exe -m pytest -v test\integration\test_new_ui_routes.py test\integration\test_api_endpoints.py`

- [x] M-03: Missing Trusted Host, Security Headers, and Production Docs Controls
  - Status: Partial fix completed and verified
  - Effort: Completed for stated partial scope
  - Primary locations:
    - `web/server.py`
    - `web/templates/app_base.html`
    - `tools/config_check/schema.py`
  - Fix summary: Added `TrustedHostMiddleware` with explicit production host validation, disabled OpenAPI documentation by default in production, and added baseline `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy` headers.
  - Remaining defense-in-depth: A strict Content Security Policy is not yet enabled because Tailwind and DaisyUI are loaded from CDNs. Self-hosting compiled CSS and removing runtime CDN dependencies should be handled as a separate CSP-enabling change.
  - Verification:
    - `C:\Python313\python.exe -m pytest -q test\integration\test_new_ui_routes.py test\tools\config_check\test_schema_validation.py`
    - Result: 53 passed, 33 warnings

- [x] M-04: FileResponse Serves Paths From Document Metadata Without a Base-Directory Check
  - Status: Fixed and verified
  - Effort: Completed
  - Primary location: `modules/api_router.py`
  - Fix summary: Added resolved-path validation before PDF previews are served. Candidate document paths must be inside configured artifact roots such as upload, watch, processing, split, files, data, or archive directories before `FileResponse` is used.
  - Verification:
    - `.\.venv\Scripts\python.exe -m py_compile modules\api_router.py`
    - `.\.venv\Scripts\python.exe -m pytest -v test\integration\test_extraction_results_api.py`

- [x] M-05: Admin Schema Names Can Resolve Outside Schema Directories
  - Status: Fixed and verified
  - Effort: Completed
  - Primary locations:
    - `modules/services/schema_service.py`
    - `config.yaml`
    - `dev_config.yaml`
    - `dev_config fts.yaml`
    - `fts_config org.yaml`
  - Fix summary: Schema reads now resolve candidate paths and load only files under configured schema directories. Absolute paths and relative traversal outside those roots are rejected. Main app configs now explicitly set `schema.directories`.
  - User experience: Admin schema editor behavior is unchanged for schemas in the configured schema directory. Arbitrary filesystem paths are no longer accepted unless they resolve under a configured schema root.
  - Verification:
    - `.\.venv\Scripts\python.exe -m py_compile modules\services\schema_service.py`
    - `.\.venv\Scripts\python.exe -m pytest -q test\services\test_schema_service.py test\integration\test_schema_api.py test\standard_step\review\test_review_gate.py`

- [x] M-06: Dynamic Task Imports Are an Admin RCE Boundary
  - Status: Fixed and verified
  - Effort: Completed
  - Primary locations:
    - `modules/workflow_loader.py`
    - `modules/services/task_registry_service.py`
    - `modules/services/pipeline_validation_service.py`
    - `modules/services/task_catalog_service.py`
    - `web/server.py`
    - `main.py`
  - Fix summary: Added a startup task trust gate, a shared approved task registry, runtime import blocking before `importlib`, and blocking admin pipeline validation for unapproved task pairs. Built-in `standard_step.*` task classes are approved in code; customer steps require deployment YAML under `custom_steps.registry` and must use the `custom_step.` module prefix.
  - Verification:
    - `.\.venv\Scripts\python.exe -m py_compile modules\services\task_registry_service.py modules\workflow_loader.py modules\services\pipeline_validation_service.py modules\services\task_catalog_service.py main.py web\server.py tools\config_check\schema.py`
    - `.\.venv\Scripts\python.exe -m pytest -q test\services\test_task_registry_service.py test\workflow\test_workflow_loader_task_approval.py test\services\test_config_validation_service.py test\integration\test_config_validation_api.py test\services\test_task_catalog_service.py`

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

- [x] M-08: Starlette Version Has File Response DoS Advisory
  - Status: Fixed and verified
  - Effort: Completed
  - Primary locations:
    - `requirements.txt`
    - `test/security/test_dependency_versions.py`
  - Fix summary: Upgraded FastAPI to `0.136.3` and added an explicit `starlette>=0.49.1,<1.0.0` requirement. The installed environment now resolves Starlette to `0.52.1`, above the fixed advisory floor. Added a regression test so affected Starlette versions are not reintroduced.
  - User experience: PDF preview and static assets should behave the same for browser users.
  - Verification:
    - `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
    - `.\.venv\Scripts\python.exe -m pip check`
    - `.\.venv\Scripts\python.exe -m pytest -q test\security\test_dependency_versions.py test\integration\test_extraction_results_api.py test\integration\test_new_ui_routes.py test\integration\test_api_endpoints.py`
    - `.\.venv\Scripts\python.exe -m pytest -q`
    - Browser visual check on `http://127.0.0.1:8765/app/review/849252d0-bdcb-42b9-bd60-cffa11015ade` confirmed the PDF viewer loaded with a 200 PDF response.

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

1. H-04: Move secrets out of YAML and rotate exposed keys.
2. Self-host frontend assets and add a strict Content Security Policy.

If optimizing for risk reduction:

1. H-04: Move secrets out of YAML and rotate exposed keys.
2. Self-host frontend assets and add a strict Content Security Policy.

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

## Latest M-06 Verification

- Date: 2026-06-13
- Focused tests: `.\.venv\Scripts\python.exe -m pytest -q test\tools\config_check\test_schema_validation.py test\tools\config_check\test_integration.py test\services\test_task_registry_service.py test\workflow\test_workflow_loader_task_approval.py test\services\test_config_validation_service.py test\integration\test_config_validation_api.py test\services\test_task_catalog_service.py`
- Result: 66 passed, 2 warnings
- Full suite: `.\.venv\Scripts\python.exe -m pytest -q`
- Result: 552 passed, 5 skipped, 44 warnings
- Note: A Prefect temporary-server logging cleanup message appeared after pytest completed, but pytest exited successfully.

## Latest M-08 Verification

- Date: 2026-06-13
- Dependency install: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Dependency check: `.\.venv\Scripts\python.exe -m pip check`
- Installed versions: FastAPI `0.136.3`, Starlette `0.52.1`
- Focused tests: `.\.venv\Scripts\python.exe -m pytest -q test\security\test_dependency_versions.py test\integration\test_extraction_results_api.py test\integration\test_new_ui_routes.py test\integration\test_api_endpoints.py`
- Result: 36 passed, 33 warnings
- Full suite: `.\.venv\Scripts\python.exe -m pytest -q`
- Result: 557 passed, 4 skipped, 49 warnings
- Visual smoke test: verified the pending human-review PDF viewer on `http://127.0.0.1:8765/app/review/849252d0-bdcb-42b9-bd60-cffa11015ade`; the PDF iframe requested `/api/documents/82e69aac-abed-4bbc-ae76-300976f66b77/file/pdf` and received HTTP 200.
- Screenshot artifact: `output/playwright/m08-pdf-viewer-smoke.png`
- Note: A Prefect temporary-server logging cleanup message appeared after pytest completed, but pytest exited successfully.
