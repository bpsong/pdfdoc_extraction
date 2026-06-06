# Security Remediation Checklist

Date: 2026-06-06

Source report: `security_best_practices_report.md`

Legend:

- `[x]` Fixed and verified
- `[ ]` Open, not fixed yet
- `Assessed` Reviewed for likelihood/risk, but not remediated

## Current Status

- Fixed: 1
- Assessed but not fixed: 1
- Open: 14

## High Severity

- [ ] H-01: Stored XSS in Legacy Dashboard Rendering
  - Status: Open
  - Primary location: `web/templates/dashboard.html`
  - Notes: Not fixed yet.

- [x] H-02: Config-Driven `eval()` in Legacy PDF Extraction
  - Status: Fixed and verified
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
  - Primary location: `modules/api_router.py`
  - Likelihood: Medium overall; higher in exposed deployments with authenticated users or stolen tokens.
  - Impact: High if triggered because the server reads full multipart bodies into memory before parsing.
  - Notes: Upload endpoints require authentication before parsing, which reduces anonymous exposure. Client-side upload limits are bypassable and do not protect the server.

- [ ] H-04: Secrets in Local YAML and Weak Default JWT Secret
  - Status: Open
  - Primary location: `config.yaml`
  - Notes: Not fixed yet. Do not copy secret values into tickets, logs, or reports.

- [ ] H-05: Sensitive Values Written to Logs
  - Status: Open
  - Primary locations:
    - `modules/auth_utils.py`
    - `standard_step/extraction/extract_pdf.py`
    - `standard_step/extraction/extract_pdf_v2.py`
  - Notes: Not fixed yet.

## Medium Severity

- [ ] M-01: Cookie Authentication Without CSRF Protection on Mutating Endpoints
  - Status: Open
  - Primary locations:
    - `web/server.py`
    - `modules/api_router.py`
  - Notes: Not fixed yet.

- [ ] M-02: Permissive CORS With Credentials
  - Status: Open
  - Primary location: `web/server.py`
  - Notes: Not fixed yet.

- [ ] M-03: Missing Trusted Host, Security Headers, and Production Docs Controls
  - Status: Open
  - Primary locations:
    - `web/server.py`
    - `web/templates/app_base.html`
  - Notes: Not fixed yet.

- [ ] M-04: FileResponse Serves Paths From Document Metadata Without a Base-Directory Check
  - Status: Open
  - Primary location: `modules/api_router.py`
  - Notes: Not fixed yet.

- [ ] M-05: Admin Schema Names Can Resolve Outside Schema Directories
  - Status: Open
  - Primary locations:
    - `modules/services/schema_service.py`
    - `modules/api_router.py`
  - Notes: Not fixed yet.

- [ ] M-06: Dynamic Task Imports Are an Admin RCE Boundary
  - Status: Open
  - Primary locations:
    - `modules/workflow_loader.py`
    - `modules/services/pipeline_config_service.py`
  - Notes: Not fixed yet.

- [ ] M-07: No Login Rate Limiting or Account Throttling
  - Status: Open
  - Primary locations:
    - `web/server.py`
    - `modules/api_router.py`
    - `modules/auth_utils.py`
  - Notes: Not fixed yet.

- [ ] M-08: Starlette Version Has File Response DoS Advisory
  - Status: Open
  - Primary locations:
    - `requirements.txt`
    - `modules/api_router.py`
    - `web/server.py`
  - Notes: Not fixed yet. Requires compatible FastAPI/Starlette upgrade planning.

## Low Severity

- [ ] L-01: LocalStorage Token Helper Should Be Removed
  - Status: Open
  - Primary location: `web/static/js/status.js`
  - Notes: Not fixed yet.

- [ ] L-02: Development Reload Can Be Enabled by Environment
  - Status: Open
  - Primary location: `main.py`
  - Notes: Not fixed yet.

- [ ] L-03: Dependency Hygiene Needs a Dedicated Project Environment
  - Status: Open
  - Primary location: `requirements.txt`
  - Notes: Not fixed yet.

## Next Recommended Fixes

1. H-01: Stored XSS in the legacy dashboard.
2. H-03: Server-side request and upload size enforcement.
3. H-05: Remove sensitive logging.
4. H-04: Move secrets out of YAML and rotate exposed keys.
5. M-01: Add CSRF protection or split cookie-auth HTML from bearer-auth API mutations.
