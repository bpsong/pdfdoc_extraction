# Security Best Practices Report

Date: 2026-06-06

Scope: Static review of the Python/FastAPI PDF processing application after the recent refactor. I reviewed the web server, API routes, authentication utilities, workflow loading, extraction tasks, templates, static JavaScript, configuration handling, and dependency metadata. I did not make code changes.

## Executive Summary

The refactor has several good security foundations: authentication is centralized, most SQLite access is parameterized, runtime settings redact secret-looking values in several admin paths, and configuration files are ignored by Git. The highest-priority gaps are in browser-facing and config-driven execution surfaces.

Recommended priority order:

1. Fix stored XSS in the legacy dashboard template.
2. Remove `eval()` from config-driven extraction schema handling.
3. Enforce upload/request size limits and keep FastAPI/Starlette on a patched compatible path.
4. Move runtime secrets out of YAML, rotate any exposed API keys, and stop logging password hashes or extracted document contents.
5. Add CSRF protection or require bearer headers for mutating API endpoints when cookie authentication is accepted.

No confirmed unauthenticated remote code execution path was found, but several issues become high impact if an admin account, local config, pipeline draft, or document metadata can be influenced by an attacker.

## Findings

### H-01: Stored XSS in Legacy Dashboard Rendering

Severity: High

Locations:

- `web/templates/dashboard.html:643`
- `web/templates/dashboard.html:646`
- `web/templates/dashboard.html:648`
- `web/templates/dashboard.html:327`
- `web/templates/dashboard.html:516`

Evidence:

The legacy dashboard builds table rows and modal content with `innerHTML` and interpolates values such as `file_id`, `original_name`, timestamps, status text, and error messages. `original_name` originates from uploaded filenames, and errors can contain task or parser output. These values are persisted and later rendered into HTML without escaping.

Impact:

An authenticated user, or any workflow that stores attacker-controlled filenames/errors, can inject script into the dashboard. Because the application uses HttpOnly cookie authentication, script cannot directly read the cookie, but it can still perform same-origin authenticated actions, read API responses, alter admin forms, publish pipeline changes, or exfiltrate visible document data.

Recommended fix:

Replace `innerHTML` interpolation with DOM construction using `textContent`, `setAttribute`, and event listeners. Remove inline `onclick` handlers. If templated HTML must be used, pass every interpolated value through a central escaping helper before insertion.

Mitigation example:

```javascript
const td = document.createElement("td");
td.textContent = f.original_name || "";
tr.appendChild(td);
```

False-positive notes:

Newer static JavaScript files already use `escapeHtml()` in several places. This finding is specific to the legacy dashboard template.

### H-02: Config-Driven `eval()` in Legacy PDF Extraction

Severity: High

Locations:

- `standard_step/extraction/extract_pdf.py:205`
- `standard_step/extraction/extract_pdf.py:208`
- `tools/llamacloud_extract_smoke.py:220`

Evidence:

The legacy extraction task reads a field type string from configuration and passes it to `eval()`. The supplied globals map includes expected type names, but Python still exposes builtins unless they are explicitly removed. A malicious type string in configuration can execute Python code if this legacy task is selected.

Impact:

If an attacker can modify pipeline configuration, publish an admin draft, or influence a config file used by this task, this becomes code execution in the application process. The smoke tool has the same pattern but is lower risk if it is only run manually by trusted operators.

Recommended fix:

Delete `eval()` and use an allowlisted parser. The newer `standard_step/extraction/extract_pdf_v2.py` already uses a safer parsing approach and should be the model for this fix. Add a regression test where a malicious type string is rejected and does not execute.

Mitigation example:

```python
ALLOWED_TYPES = {
    "str": str,
    "float": float,
    "int": int,
    "Any": Any,
}
```

False-positive notes:

This is config-driven, not raw request-body-driven. The severity is high because the application exposes admin pipeline editing and dynamic task configuration.

### H-03: Upload and Request Body Memory Exhaustion

Severity: High

Locations:

- `modules/api_router.py:430`
- `modules/api_router.py:441`
- `modules/api_router.py:615`
- `modules/api_router.py:675`
- `web/server.py:231`
- `modules/api_router.py:400`
- `modules/api_router.py:483`

Evidence:

The custom multipart parser reads the full request body with `await request.body()` before parsing uploads. Server-side enforcement for the configured maximum upload size was not found. The login and JSON parsing helpers also read full bodies into memory.

Impact:

An authenticated user, or an unauthenticated user on endpoints that parse request bodies before authentication, can send large requests and consume application memory. This can degrade availability or crash the worker process.

Recommended fix:

Enforce `Content-Length` before body reads, reject bodies above a configured limit, set a maximum file count, and prefer Starlette/FastAPI `UploadFile` streaming primitives with explicit file size checks. Add equivalent limits at the reverse proxy if one is used.

Mitigation example:

```python
content_length = request.headers.get("content-length")
if content_length is None or int(content_length) > settings.max_upload_bytes:
    raise HTTPException(status_code=413, detail="Request body too large")
```

False-positive notes:

Client-side/UI display of a maximum upload size is useful but is not a security control.

### H-04: Secrets in Local YAML and Weak Default JWT Secret

Severity: High

Locations:

- `config.yaml:34`
- `config.yaml:42`
- `config.yaml:51`
- `.gitignore:1`

Evidence:

The active YAML config contains a weak/default web signing secret, a password hash, and a LlamaCloud API key value. The config file is ignored by Git, which reduces accidental repository exposure, but the runtime secret material is still stored in a local plaintext file.

Impact:

A weak JWT signing key allows token forgery if the value is known or guessed. A plaintext third-party API key can be leaked through local backups, support bundles, logs, or machine compromise. A leaked password hash enables offline cracking.

Recommended fix:

Load `web.secret_key`, API keys, and password hashes from environment variables or a local secret store. Reject startup if `web.secret_key` is missing, short, or set to a known placeholder such as `your_secret_key`. Rotate the LlamaCloud key if it may have been copied outside the intended local environment.

False-positive notes:

I intentionally did not copy secret values into this report.

### H-05: Sensitive Values Written to Logs

Severity: High

Locations:

- `modules/auth_utils.py:98`
- `modules/auth_utils.py:210`
- `standard_step/extraction/extract_pdf.py:184`
- `standard_step/extraction/extract_pdf_v2.py:310`
- `modules/logging_config.py:104`

Evidence:

The authentication helper logs the loaded password hash and logs the hash again during verification at debug level. Extraction tasks log raw extracted document data at info level. Logs are written to rotating `app.log` files.

Impact:

Password hashes in logs can be used for offline cracking if logs are exposed. Extracted invoice/document data may contain personal, business, or financial information. Logging it broadly increases the blast radius of a compromise.

Recommended fix:

Remove password hash logging entirely. Replace raw extraction logging with counts, schema names, document IDs, field names, or redacted summaries. Add a logging redaction filter for key names such as `password`, `token`, `secret`, `api_key`, `authorization`, and domain-specific sensitive fields.

False-positive notes:

Some admin settings paths already redact secret-looking values; extend that discipline to authentication and extraction logs.

### M-01: Cookie Authentication Without CSRF Protection on Mutating Endpoints

Severity: Medium

Locations:

- `web/server.py:291`
- `modules/api_router.py:75`
- `modules/api_router.py:589`
- `modules/api_router.py:667`
- `modules/api_router.py:841`
- `modules/api_router.py:911`
- `modules/api_router.py:952`
- `modules/api_router.py:1063`
- `modules/api_router.py:1110`
- `modules/api_router.py:1155`
- `modules/api_router.py:1442`
- `modules/api_router.py:1454`
- `modules/api_router.py:1467`
- `modules/api_router.py:1489`

Evidence:

The authentication dependency accepts either an `Authorization` header or the `access_token` cookie. The login flow sets an HttpOnly cookie with `SameSite=Lax`. Multiple upload, admin, schema, pipeline, and review endpoints mutate server state without a CSRF token or an origin check.

Impact:

`SameSite=Lax` reduces common cross-site POST attacks but is not a complete CSRF strategy, especially if browser behavior changes, same-site subdomains are introduced, or any same-origin XSS exists. The XSS issue in the legacy dashboard makes this more important.

Recommended fix:

Either require bearer-token headers for API mutations and reserve cookies for HTML navigation, or add CSRF protection for cookie-authenticated state-changing requests. Also set `secure=True` for cookies in production HTTPS deployments.

False-positive notes:

If this app is strictly localhost-only and not exposed to browsers outside a trusted machine, the operational risk is lower. The code should still be hardened before network deployment.

### M-02: Permissive CORS With Credentials

Severity: Medium

Location:

- `web/server.py:65`

Evidence:

The app configures CORS with wildcard origins, all methods, all headers, and credentials enabled.

Impact:

Credentialed wildcard CORS is unsafe as a deployment default. Depending on framework behavior and future configuration changes, it can allow browser-based cross-origin access to authenticated API responses or create confusing security assumptions.

Recommended fix:

Disable CORS unless needed. If needed, read an explicit allowlist from configuration and use exact HTTPS origins. Keep `allow_credentials=True` only for trusted origins.

### M-03: Missing Trusted Host, Security Headers, and Production Docs Controls

Severity: Medium

Locations:

- `web/server.py:53`
- `web/server.py:61`
- `web/templates/app_base.html:8`
- `web/templates/app_base.html:9`

Evidence:

The FastAPI app uses default docs/OpenAPI exposure, mounts public static files, and does not configure `TrustedHostMiddleware` or security headers. The base template loads Tailwind and DaisyUI from third-party CDNs.

Impact:

Missing host validation can contribute to host-header issues. Missing browser security headers weakens defense-in-depth against XSS, content sniffing, clickjacking, and referrer leakage. Public API docs can expose operational details in production.

Recommended fix:

Add `TrustedHostMiddleware` with configured hostnames. Disable or protect `/docs`, `/redoc`, and `/openapi.json` in production. Add headers such as `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Content-Security-Policy`, and `frame-ancestors`. Prefer self-hosted frontend assets or use pinned assets with integrity controls.

### M-04: FileResponse Serves Paths From Document Metadata Without a Base-Directory Check

Severity: Medium

Location:

- `modules/api_router.py:1379`

Evidence:

The PDF-serving endpoint reads file paths from SQLite document metadata and returns a `FileResponse` for any existing local file. There is no resolved-path check that restricts the file to configured application storage roots.

Impact:

If a document record can be created or modified with an arbitrary path, an authenticated user can retrieve local files readable by the application process. This risk is amplified by dynamic pipeline tasks and admin-controlled workflows that can register artifacts.

Recommended fix:

Resolve the path and require it to be under one of the configured storage roots before serving. Reject symlinks if they are not required. Consider serving as an attachment and limiting MIME types.

Mitigation example:

```python
resolved = path.resolve()
storage_root = settings.processing_dir.resolve()
if not resolved.is_relative_to(storage_root):
    raise HTTPException(status_code=404, detail="File not found")
```

### M-05: Admin Schema Names Can Resolve Outside Schema Directories

Severity: Medium

Locations:

- `modules/services/schema_service.py:183`
- `modules/services/schema_service.py:197`
- `modules/api_router.py:1139`
- `modules/api_router.py:1155`

Evidence:

Schema writes use a `_safe_schema_name()` helper, but reads allow absolute paths and join external schema names directly to schema directories. API routes expose schema loading and updating to admins.

Impact:

An admin or compromised admin session may read or target unexpected files via absolute paths or traversal-like names. Even if normal path parameters limit forward slashes, Windows backslashes and encoded values should not be trusted as a boundary.

Recommended fix:

Use `_safe_schema_name()` for every externally supplied schema name, including reads and validation. Resolve paths and require them to remain under configured schema directories.

Remediation status: Fixed and verified in `security_remediation_checklist.md` under M-05.

### M-06: Dynamic Task Imports Are an Admin RCE Boundary

Severity: Medium

Locations:

- `modules/workflow_loader.py:64`
- `modules/workflow_loader.py:151`
- `modules/services/pipeline_config_service.py:292`
- `tools/config_check/task_validator.py:177`

Evidence:

Pipeline configuration includes arbitrary `module` and `class` strings. The workflow loader imports the module and instantiates the class if it subclasses `BaseTask`. Admin draft normalization preserves module and class values.

Impact:

This is powerful by design, but it means the admin pipeline editor is effectively a code-execution control plane if arbitrary modules on `PYTHONPATH` can be selected. A compromised admin account can pivot from configuration changes to application code execution.

Recommended fix:

Restrict UI-publishable tasks to an explicit allowlist or catalog generated from approved packages such as `standard_step.*`. For custom tasks, require local filesystem deployment plus an explicit trusted registry entry, not arbitrary module/class strings from the web UI.

Remediation status: Fixed and verified in `security_remediation_checklist.md` under M-06. The workflow loader now blocks unapproved task pairs before import, startup fails with a critical log for unapproved active pipeline tasks, and admin validation rejects unapproved draft task pairs.

False-positive notes:

If administrators are intentionally trusted as code operators, document that trust boundary clearly and protect admin access accordingly.

### M-07: No Login Rate Limiting or Account Throttling

Severity: Medium

Locations:

- `web/server.py:253`
- `web/server.py:314`
- `modules/api_router.py:560`
- `modules/auth_utils.py:183`

Evidence:

Login endpoints validate credentials and return generic errors, but no rate limit, lockout, backoff, or failed-login audit control was found.

Impact:

Online password guessing is practical if the app is reachable over a network, especially because configuration supports password-hash based authentication.

Recommended fix:

Add per-IP and per-username login throttling, preferably backed by a shared store if multiple workers are used. Log failed attempts without logging supplied passwords or password hashes.

### M-08: Starlette Version Has File Response DoS Advisory

Severity: Medium

Locations:

- Reviewed runtime dependency: `starlette 0.46.2` before remediation
- `modules/api_router.py:1379`
- `web/server.py:61`

Evidence:

The reviewed runtime used Starlette 0.46.2 through FastAPI 0.115.12. A current Starlette advisory covers versions from 0.39.0 through 0.49.0 for CPU exhaustion through crafted Range headers in `FileResponse` and `StaticFiles`. This application uses both.

Impact:

An attacker can cause disproportionate CPU usage by requesting static files or PDF responses with crafted Range headers.

Recommended fix:

Upgrade FastAPI and Starlette together on a compatible path. The installed FastAPI metadata constrains Starlette to `<0.47.0`, so patching this specific issue requires a FastAPI upgrade as well. As a short-term mitigation, strip or reject multi-range `Range` headers at a reverse proxy or middleware for static/PDF routes.

Remediation status: Fixed and verified in `security_remediation_checklist.md` under M-08. FastAPI is now pinned to `0.136.3`, `requirements.txt` requires `starlette>=0.49.1,<1.0.0`, and the installed environment resolves Starlette to `0.52.1`.

Source:

- GitHub Security Advisory GHSA-7f5h-v6xp-fcq8: https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8

### L-01: LocalStorage Token Helper Should Be Removed

Severity: Low

Location:

- `web/static/js/status.js:7`

Evidence:

The status helper checks `localStorage.access_token` and sends it as a bearer token. The current login flow uses an HttpOnly cookie, and no active token write to localStorage was found.

Impact:

If future code starts writing tokens to localStorage, any XSS can steal bearer tokens directly. Leaving this helper in place can encourage insecure token storage.

Recommended fix:

Remove the localStorage token fallback and rely on HttpOnly cookies plus CSRF protection, or use in-memory bearer tokens only for explicit API clients.

### L-02: Development Reload Can Be Enabled by Environment

Severity: Low

Locations:

- `main.py:162`
- `main.py:189`

Evidence:

`USE_RELOAD` can enable Uvicorn reload mode. This is appropriate for local development but should not be enabled in production.

Impact:

Reload mode watches files and is not intended for hardened production deployments.

Recommended fix:

Document that `USE_RELOAD` must be unset or false in production. Consider rejecting reload mode when `APP_ENV=production`.

### L-03: Dependency Hygiene Needs a Dedicated Project Environment

Severity: Low

Locations:

- `requirements.txt`
- Local Python environment

Evidence:

`pip check` reports conflicts in the active global Python environment. Some conflicts are unrelated packages, but one conflict involves `python-jose` dependency constraints. `pip-audit` and `bandit` are not installed in the active interpreter.

Impact:

Global environment drift makes vulnerability and compatibility status harder to trust. Dependency conflicts can cause runtime security fixes to be absent or broken.

Recommended fix:

Use a project virtual environment or lockfile. Add CI jobs for `pip check`, `pip-audit`, and `bandit` or an equivalent security scanner. Keep dependency versions current and test upgrades in the project environment.

## Positive Observations

- SQLite usage is mostly parameterized; I did not find obvious request-driven SQL injection in the reviewed API paths.
- `config.yaml` and other YAML config files are ignored by Git.
- Several admin settings and task catalog services already redact secret-looking values before exposing or auditing configuration.
- `main.py` launches Uvicorn through a list argument subprocess call with `shell=False`.
- Login responses avoid revealing whether the username or password was wrong.

## Verification Notes

Commands used:

```powershell
C:\Python313\python.exe -c "import fastapi, starlette, uvicorn, pydantic; print(...)"
C:\Python313\python.exe -m pip show fastapi
C:\Python313\python.exe -m pip index versions fastapi
C:\Python313\python.exe -m pip check
C:\Python313\python.exe -m pip show pip-audit
C:\Python313\python.exe -m bandit --version
git status --short
git ls-files -- config.yaml dev_config.yaml local_config.yaml
```

Scanner status:

- `pip-audit` was not installed.
- `bandit` was not installed.
- `pip check` ran, but the active global environment contains unrelated package conflicts, so dependency conclusions should be rechecked in a project-specific environment.

External sources checked:

- Starlette Range header DoS advisory: https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8
- Starlette Host header advisory: https://github.com/Kludex/starlette/security/advisories/GHSA-86qp-5c8j-p5mr

## Suggested Remediation Plan

1. Patch H-01 and H-02 first because they are direct browser/code execution risks.
2. Add upload size enforcement and a regression test for oversized multipart uploads.
3. Rotate runtime secrets, move them to environment-backed configuration, and remove sensitive logging.
4. Add CSRF protection or split cookie-auth HTML from bearer-auth API mutation endpoints.
5. Add deployment hardening: trusted hosts, explicit CORS allowlist, security headers, protected docs, and production cookie `secure=True`.
6. Keep FastAPI and Starlette on patched compatible versions, then add `pip-audit`, `pip check`, and `bandit` to CI.
