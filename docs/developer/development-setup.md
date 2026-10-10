# Set up a development environment

| Item | Value |
| --- | --- |
| Audience | Developers and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

Work from the repository root in PowerShell. Python 3.13 and the repository
virtual environment are the supported baseline. Runtime application packages
are pinned in `requirements.txt`; development tools are added by
`requirements-dev.txt`. The config-check package in `pyproject.toml` does not
replace the application requirements.

## Install dependencies

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci
```

Use `.\.venv\Scripts\python.exe` for every Python command. Shell activation
does not persist reliably between tool invocations. Node/npm is needed to
rebuild assets; deployments can run the committed assets without it.

## Prepare an isolated local deployment

Create an ignored local deployment YAML and temporary test directories using
the [deployment reference](../reference/deployment-configuration.md). Prepare
watch/upload roots before startup. Set initial accounts using the
[account provisioning procedure](../it-support/account-recovery.md).
Use synthetic PDFs and a separate database; tests must not depend on your
active config or customer documents.

```powershell
.\.venv\Scripts\python.exe main.py --config-path path\to\local-config.yaml
```

Build and publish a test pipeline/form through the app. Legacy `tasks` and
`pipeline` YAML blocks are import sources, not new runtime workflow settings.
Provider installation belongs in [provider setup](../it-support/installation-and-provider-setup.md).

## Production versus prototype

Production templates/assets belong under `web/`. The React/Vite visual-editor
prototype has its own dependencies and commands. From its directory:

```powershell
Set-Location pipeline_visual_editor_prototype
npm ci
npm run build
```

Return to the repository root for Python tests. See [testing](testing-and-verification.md)
and [frontend development](frontend-development.md) before changing those surfaces.
