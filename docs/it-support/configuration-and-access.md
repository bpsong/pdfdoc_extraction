# Configure deployment access and filesystem permissions

| Item | Value |
| --- | --- |
| Audience | IT support and deployment owners |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Select the intended deployment

Runtime YAML is selected by `--config-path`, then `CONFIG_PATH`, then the
repository-root `config.yaml`. Resolve relative paths beside that file. Confirm
the actual database, log, upload and processing paths before making changes.
YAML edits require coordinated parent/web/worker restart. SQLite-backed app
settings and publication have separate behaviour.

Use the [deployment settings reference](../reference/deployment-configuration.md)
for keys and defaults. Pipelines and review forms live in the application;
new workflows are authored and published by the application administrator.

## Prepare directories and account access

The startup-compatible `watch_folder.dir` and `web.upload_dir` must already
exist. Each bound incoming directory must also exist. Grant the deployment
account the listing, reading, moving and writing access needed by the actual
pipeline. Task output directories are configured in published task parameters.
Check permissions under the account running the app, including network shares;
interactive-user access alone does not prove service-account access.

Use **Test access** or **Check now** to diagnose listing access, then a synthetic
ingestion test to verify the actual file lifecycle. Those UI checks do not test
all destructive permissions and do not enqueue a document.

## Manage secret aliases

Store provider credentials in deployment-owned `pipeline_secrets`, outside Git.
Published definitions contain `$secret` aliases. Agree alias names with admins
without sending resolved credentials through descriptions, exports or support
screenshots. Protect the YAML, database, backups and log paths using the
organisation's account and storage policies.

## Production Web Hardening

Set `APP_ENV=production` (or `ENV`/`ENVIRONMENT`) and configure every hostname
that clients or a reverse proxy will send in the HTTP `Host` header:

```yaml
web:
  allowed_hosts:
    - app.example.com
  production_docs_enabled: false
```

Production startup rejects an empty or wildcard host allowlist. Include the
public application hostname and, only when applicable, the hostname forwarded
by a trusted reverse proxy. OpenAPI endpoints (`/docs`, `/redoc`, and
`/openapi.json`) are disabled in production unless
`production_docs_enabled` is explicitly enabled. The application also sends
baseline anti-framing, MIME-sniffing, referrer, and browser-permission headers.
Production startup also requires `web.secret_key` to be at least 32 characters
and rejects common placeholders. Generate a unique random key and keep it out
of version control. Changing it invalidates existing login sessions.
Production login and CSRF cookies use the `Secure` attribute, so serve the
browser-facing app over HTTPS (directly or through a trusted TLS proxy).
Local development without a production environment flag can still use HTTP.
Tailwind and DaisyUI are bundled locally; run `npm ci` and
`npm run build:css` after changing frontend utility classes or package versions.
- Do not commit password hashes or secret-bearing config files to version control.
- Rotate passwords and audit access regularly.


## Validate changes before returning service

```powershell
.\.venv\Scripts\python.exe -m tools.config_check validate --config path\to\config.yaml --import-checks
```

Exit code 2 means warnings only, not a clean result. Read findings before
restart. The checker does not migrate or repair the database. After restart,
verify [readiness and logs](monitoring-and-logs.md), then coordinate resuming intake.
