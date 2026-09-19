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

Run the focused frontend tests, `npm run build:css` when utility classes or
Tailwind inputs changed, and the full pytest suite before promotion. Deploy
templates and static assets as one artifact. Static assets should be uploaded
before switching application instances so a new template never points at an
unavailable module.

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
value. Other feature entries do not need to change. For a shared-module,
template-shell, CSS, or server/API regression, roll back the complete artifact.

After rollback, run the release checker and smoke-test the affected route in a
fresh browser context. A rollback is complete only when the template entry and
every feature-local import resolve to the same release value and no module 404s
appear in the browser console or network log.
