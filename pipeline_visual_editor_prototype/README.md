# Visual pipeline editor prototype

This React/Vite application is a standalone design prototype. Production pages
live under `../web/` and use SQLite-backed pipeline/form versions. Prototype
Save writes a local sample YAML file; it does not publish a production version,
create processing jobs, or run extraction.

## Run locally

From this directory in PowerShell:

```powershell
npm ci
npm run dev
```

Before opening the editor, create the ignored file
`public/config_sample_invoice.yaml`. It is not included in a fresh checkout.
An empty starting definition is:

```yaml
tasks: {}
pipeline: []
```

The dev server's `/api/prototype/*` middleware in `vite.config.js` loads/saves
that file, checks basic shape and configured paths, browses project files/CSV
headers, and offers a Windows directory picker. Save creates a `.bak` copy and
replaces the YAML through a temporary file. These local developer APIs do not
implement production authentication, versioning or publication validation.
Keep the loopback default and use synthetic settings without provider credentials
or customer documents. The API can create project directories when requested.

Path browsing generally uses the parent repository as its root; the Windows
picker can select an absolute path. A successful prototype validation is not
production pipeline acceptance. Task choices and parameters can differ from the
current production catalog.

## Verify changes

```powershell
npm test
npm run build
```

`npm run preview` serves the built frontend; the prototype APIs are installed by
Vite's development-server hook and are unavailable in static preview. Use
`npm run dev` to exercise file loading, saving and browsing.

Additional Python browser checks live in
`../test/pipeline_visual_editor_prototype/`; run them from the repository root
with `.\.venv\Scripts\python.exe`. Design QA reports and `tasks/*/notes.md`
record their original checkpoints; they do not establish current production
feature parity. See [frontend development](../docs/developer/frontend-development.md)
for production release rules.
