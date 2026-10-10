# Monitor runtime health and logs

| Item | Value |
| --- | --- |
| Audience | IT support and deployment owners |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Distinguish liveness and readiness

`GET /health/live` confirms that the web process can respond.
`GET /health/ready` returns 503 until the current supervised run is ready.
An authenticated admin can inspect `GET /api/admin/runtime-health` for
component heartbeats, database state and watch-folder degradation.

Readiness is stronger evidence than an open browser page. A stale or failed
folder observation can indicate degraded intake without a failed worker.
Correlate observations with the current run ID and component role.

## Log Files and Troubleshooting

The configured `logging.log_file` is used as the base for role-specific logs. The
default base name `app.log` produces `app.supervisor.log`, `app.web.log`, and
`app.worker.log`.
Normal supervised startup produces separate supervisor, web, and worker log
files. Check the supervisor log for startup, shutdown, and child-process
failures; the web log for browser/API errors; and the worker log for task,
provider, retry, and artifact failures.

- `logging.log_file` supplies the base log path. The default `app.log` produces
  `app.supervisor.log`, `app.web.log`, and `app.worker.log` beside the active
  configuration file.
- To see more detailed logs, set `logging.log_level` to `DEBUG` in `config.yaml`.
- Common startup errors include:
  - Invalid YAML syntax (check your config file with a YAML validator).
  - A missing, incomplete, older, or newer SQLite schema.
  - Missing folders (create required folders like `watch_folder`, `web_upload` before starting).
  - Missing or invalid provider credentials, such as a LlamaCloud `api_key`.
  - Permission errors (ensure the system user has read/write access to all configured directories).
- Performance considerations for large files:
  - Larger PDFs require more disk, memory, network, split, and provider processing time.
  - Process unusually large documents individually and during quieter periods.
  - Monitor **Processing Overview**, the role-specific logs, Windows Task Manager, free disk space, and provider quotas.
- During runtime troubleshooting:
  - Failed tasks log detailed errors to `app.worker.log` with timestamps and context information when the default base path is used.
  - Files with processing errors may remain in the processing directory; check **Processing Overview**, **Failures**, and the worker log.
  - Use the application pages for current status and the log for technical details.
  - Use `Ctrl+C` to request an orderly shutdown, then verify any document that was processing at the time.
- Common runtime issues and solutions:
  - **High memory usage**: Reduce batch size and process large PDFs individually.
  - **Slow processing**: Check internet connectivity for cloud extraction providers.
  - **Files stuck in processing**: Verify API credentials and rate limits with your extraction provider.
  - **Permission errors**: Ensure all configured directories have proper read/write permissions.
- Log monitoring tips:
  - Look for "CRITICAL" messages that indicate startup failures.
  - "ERROR" messages show task failures with specific details.
  - "WARNING" messages indicate non-fatal issues that may affect performance.
  - Use the web interface to monitor processing status through its periodic refreshes.


## Routine checks and escalation

Check free disk space for the database, working files, artifacts and backups;
check memory, provider availability/quotas, and the oldest queued/review items.
Use [incident runbooks](incident-runbooks.md) when observations stop changing.
No automatic application-wide log rotation or all-artifact retention policy is
defined by this implementation. Establish deployment-specific monitoring and
maintenance with the operational owner.

Share identifiers, times, roles and safe diagnostic messages. Review logs and
validation output before sending them: redact credentials, customer values and
unneeded absolute paths through the approved support channel.
