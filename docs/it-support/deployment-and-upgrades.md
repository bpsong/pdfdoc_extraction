# Deploy, upgrade and roll back the application

| Item | Value |
| --- | --- |
| Audience | IT support and deployment owners |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Prepare a compatible release

1. Obtain the approved code/static/template artifact and its verification
   record. Developers prepare assets using [frontend development](../developer/frontend-development.md).
2. Record the current artifact, schema, configuration and a verified consistent
   [backup](backup-and-restore.md). Plan how to handle work accepted afterward.
3. Exercise the upgrade on an isolated staging database with synthetic input.
   Validate the configuration, normal parent startup, both roles, processing,
   review and outputs. Do not point regression checks at production state.
4. Pause intake, stop the current supervised deployment, and deploy matching
   server code, templates and static assets. Make referenced assets available
   before serving templates that need them.
5. Start through `main.py`. The parent owns migration; web/worker children
   verify the exact schema and essential tables before readiness.
6. Check readiness, logs, role access and representative work; coordinate
   resuming intake and monitor errors, queued work and folder health.

This app's default topology is one local supervised deployment sharing SQLite.
Release planning must preserve its single worker/migration ownership; a staged
rollout does not establish multi-host database or worker support.

## Pipeline archive and cleanup release

Deploy these cache values with the matching server/API artifact:

- Pipeline template entry, controller, and feature imports: `pipeline-lifecycle-2`.
- Upload entry and feature imports: `pipeline-cleanup-1`, including purged
  upload-receipt recovery.
- Shared committed CSS query:
  `tailwind-3.4.17-daisyui-4.12.10-pipeline-cleanup`.

The server requires schema **9**. Back up the database consistently before the
upgrade. Start through normal `main.py` migration ownership so the parent applies
the upgrade before web/worker children verify the exact schema. A standalone web
process remains verification-only unless explicitly started in migration mode.
The migration preserves all audit history and adds expiring cleanup previews;
it does not automatically clean processing history or physical files.

Use an isolated synthetic configuration/database for regression checks rather
than a developer or production database. Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test\db\test_pipeline_cleanup_migration.py test\services\test_pipeline_cleanup_service.py test\integration\test_pipeline_cleanup_api.py test\visual\test_pipeline_cleanup_visual.py test\visual\test_pipeline_metadata_visual.py test\visual\test_pipeline_controller_modules.py --tb=short
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
npm run build:css
```

Also run the full pytest suite before promotion. In staging, inspect desktop and
mobile archive blockers, archived visibility/read-only controls, preview counts,
name confirmation, stale-preview recovery, and success results. See the
[retention guide](../admin/archiving-and-retention.md) and
[verification record](../../tasks/tasks-pipeline-archive-cleanup.md).

## Rollback

For a feature-only frontend regression, restore that feature directory and its
template from the previous artifact, preserving their previous shared release
value. Include any controller outside the feature directory, such as
`pipeline_config.js`, and its matching imports. Other feature entries do not
need to change. For a shared-module,
template-shell, CSS, or server/API regression, restore a complete compatible
artifact. Check database schema compatibility before starting it.

Schema 9 has no supported downgrade. An older schema-8 artifact must not be
started against the upgraded database. Recover a schema-changing deployment
using a matching artifact and verified consistent database backup, with a plan
for any work accepted since that backup. Restoring static assets does not undo
confirmed processing-data cleanup; that action has no in-app undo. Keep database
backup/restore planning separate from frontend asset rollback.

After rollback, run the release checker and smoke-test the affected route in a
fresh browser context. A rollback is complete only when the template entry and
every feature-local import resolve to the same release value and no module 404s
appear in the browser console or network log.


For operator/admin smoke procedures use their [reading paths](../README.md).
Record release-specific compatibility and required action under
[change records](../history/README.md), rather than extending every guide's history.
