# Frontend module deployment and rollback

The production UI uses native ES modules grouped by feature under
`web/static/js/<feature>/`. Every feature entry and each feature-local import
must use one release query value. This prevents a cached entry from importing a
controller, view, model, or API adapter from a different release.

## Release validation

From the repository root, validate all feature graphs before deployment:

```powershell
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
```

When a feature changes, assign that feature a new immutable release value:

```powershell
.\.venv\Scripts\python.exe -m tools.frontend_release_check bump processing-overview frontend-hardening-8
```

The command updates only that feature's template entry and feature-local import
graph. Shared modules such as `polling.js` carry their own release value and
must be bumped in each consumer when their public contract changes.

The pipeline entry imports `../pipeline_config.js`, whose imports point back
into `pipeline-config/`. Update those controller/parent-relative imports too;
the release command currently scans only `./` imports within the feature
directory. `test/visual/test_pipeline_controller_modules.py` verifies the entry
and controller contract in addition to the release checker.

The shared classic script `pdf_viewer.js` also needs a consistent release query
in every consumer: `human_review.html`, `extraction_results.html` and
`failures.html`. The current evidence-message release is `pdf-evidence-4`.
Update all three when viewer behavior changes, deploy the script and templates
together, and refresh already-open pages. This avoids a cached GLM-OCR-only
message on a LiteParse review. Diagnostic LiteParse citations keep page
navigation but do not produce verified field highlights; generic page-only
messages must remain provider-neutral.

Run the focused frontend tests, `npm run build:css` when utility classes or
Tailwind inputs changed, and the full pytest suite before promotion. Deploy
templates and static assets as one artifact. Static assets should be uploaded
before switching application instances so a new template never points at an
unavailable module.

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
[retention guide](pipeline_retention_admin_guide.md) and
[verification record](../tasks/tasks-pipeline-archive-cleanup.md).

## Progressive rollout

1. Build and validate the complete application artifact.
2. Deploy it to a staging instance and perform the authenticated browser sweep.
3. Replace production instances gradually while monitoring page-load errors,
   module 404s, API error rate, and processing-poll concurrency.
4. Keep the previous artifact and its release values available until the rollout
   has completed and browser caches have converged.

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
