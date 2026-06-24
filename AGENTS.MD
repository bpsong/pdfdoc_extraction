# AGENTS.md Guide for AI Agents

This repository is a Windows-first Python 3.13 application for configurable PDF
processing. Work from the repository root unless a command explicitly targets a
subproject.

## Development Environment

- Use PowerShell command syntax.
- Use the repository virtual environment for every Python command. Do not use a
  hardcoded global interpreter such as `C:\Python313\python.exe`, and do not
  assume that activating the environment persists between tool calls.
- The canonical interpreter path is:

  ```powershell
  .\.venv\Scripts\python.exe
  ```

- If the virtual environment does not exist, create and initialize it with:

  ```powershell
  py -3.13 -m venv .venv
  .\.venv\Scripts\python.exe -m pip install --upgrade pip
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  ```

- `requirements.txt` is the dependency manifest for the full application.
  `pyproject.toml` currently packages the `tools.config_check` CLI and does not
  replace the application requirements file.
- Add or change Python dependencies in `requirements.txt`. Update
  `pyproject.toml` too only when the packaged config-check CLI needs the same
  dependency.
- The production frontend uses the root `package.json`. Install its dependencies
  with `npm ci`.
- `pipeline_visual_editor_prototype` is a separate React/Vite prototype with its
  own `package.json` and lock file. Run its npm commands from that directory.

## Current Project Structure

- `main.py`: Application entry point. Starts the watch-folder workflow and,
  unless disabled, the FastAPI server.
- `modules/`: Core application code.
  - `modules/db/`: SQLite connections, migrations, schema, and repositories.
  - `modules/services/`: Application use cases and business orchestration.
  - `modules/api_router.py`: HTTP API composition and request handling.
  - `modules/workflow_loader.py` and `modules/workflow_manager.py`: Configured
    pipeline loading and execution.
- `standard_step/`: Built-in pipeline tasks for extraction, split, review,
  rules, storage, archiving, context, and housekeeping.
- `web/`: Production FastAPI templates and browser assets.
- `tools/config_check/`: Configuration validation CLI.
- `tools/`: Administrative and smoke-test scripts.
- `test/`: Pytest unit, integration, workflow, security, visual, and tool tests.
- `docs/`: Maintained architecture, operations, and user documentation.
- `tasks/`: PRDs, implementation task lists, and future-work documents.
- `pipeline_visual_editor_prototype/`: Standalone design prototype; it is not
  the production web application.
- `schemas/`: Review and extraction schemas used by configured workflows.
- Runtime folders such as `data/`, `files/`, `processing*/`, `archive_folder/`,
  `output/`, `web_upload/`, and `watch_folder/` contain local state or generated
  artifacts, not application source.

## Architecture Rules

- SQLite is the authoritative workflow-state store for batches, documents, task
  runs, extraction results, review items, artifacts, settings, and audit data.
- Put table-specific persistence in `modules/db/repositories.py` and coordinate
  cross-table business operations through `modules/services/`.
- Keep route handlers focused on authentication, request validation, service
  calls, and response construction. Do not move new business logic into
  `modules/api_router.py` when it belongs in a service.
- `StatusManager`, status text files, `/api/files`, and `/api/status/{file_id}`
  are legacy compatibility surfaces. Do not use them for new workflow state or
  new UI features.
- Production UI work belongs under `web/`. Do not implement production behavior
  only in `pipeline_visual_editor_prototype/`.
- New browser workflows should use the current `/app/*` pages and primary
  SQLite-backed APIs. Do not restore removed legacy pages.
- Configured standard tasks must inherit from `modules.base_task.BaseTask`,
  preserve the shared workflow context contract, and use `TaskError` plus
  `register_error` for task failures.
- Durable files created by tasks must be registered with
  `modules.services.artifact_service.register_document_artifact` when a
  `document_id` is available.
- Built-in tasks use approved `standard_step.*` module/class pairs. Custom tasks
  must use the `custom_step.*` namespace and be explicitly approved in
  `custom_steps.registry`.
- Preserve the distinction between operational state in SQLite and large
  business artifacts on disk.

Read `docs/design_architecture.md` before changing architectural boundaries.
Read `tasks/standard_task_creation_guidelines.md` before adding or substantially
changing a pipeline task.

## Configuration and Sensitive Data

- Runtime configuration is YAML, normally `config.yaml` or a path supplied by
  `--config-path`/`CONFIG_PATH`.
- Local YAML files, databases, PDFs, logs, generated outputs, and virtual
  environments are intentionally ignored by Git because they may contain
  credentials or customer data.
- Never commit API keys, password hashes, session secrets, customer documents,
  runtime databases, or raw extraction output.
- Do not log secrets or include them in API responses, audit payloads, fixtures,
  screenshots, or test failure messages.
- Prefer temporary-path fixtures and synthetic data in tests. Do not make tests
  depend on the developer's active `config.yaml` or runtime database.
- Validate configuration changes with:

  ```powershell
  .\.venv\Scripts\python.exe -m tools.config_check validate --config path\to\config.yaml --import-checks
  ```

  The config-check CLI uses exit code `2` for warning-only results.

## Coding Conventions

- Follow PEP 8 and the established style in the surrounding module.
- Add type hints to new and changed function signatures and to complex data
  structures.
- Write concise Google-style docstrings for public modules, classes, and
  non-obvious functions. Avoid docstrings that merely repeat the name.
- Keep functions focused and move reusable business logic into the appropriate
  service or helper.
- Use f-strings for interpolation.
- Catch specific exception types. Preserve useful context when logging or
  translating an exception, without exposing secrets.
- Use `pathlib.Path` where practical and keep Windows path behavior in mind.
- Avoid unrelated formatting or refactoring while implementing a scoped change.
- Preserve existing user changes in a dirty worktree. Do not commit, stage, or
  discard changes unless the user asks.

## Frontend Conventions

- Production templates are in `web/templates`; production JavaScript and CSS
  are in `web/static`.
- Preserve authentication, role checks, CSRF handling, security headers, and
  same-origin PDF-preview restrictions when changing web routes or requests.
- After changing Tailwind input, utility classes in templates/JavaScript, or
  frontend package versions, rebuild the committed CSS:

  ```powershell
  npm run build:css
  ```

- For changes scoped to the visual editor prototype:

  ```powershell
  Set-Location pipeline_visual_editor_prototype
  npm ci
  npm run build
  ```

## Testing and Verification

Every feature or bug fix requires tests. Test files must be named `test_*.py` or
`*_test.py`, and test functions must start with `test_`.

Run focused tests first:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\path\to\test_file.py
```

Run the full suite when the change is broad or before declaring a substantial
refactor complete:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Additional rules:

- Run commands from the repository root so `pytest.ini` and project imports are
  applied correctly.
- Include nearby unit tests plus integration tests for affected API, database,
  workflow, or UI behavior.
- Live LlamaCloud checks require explicit credentials and may consume external
  resources. Do not run them unless the task specifically requires a live check.
- Browser-based visual tests may require Playwright Chromium. If the environment
  reports that it is missing, install it with:

  ```powershell
  .\.venv\Scripts\python.exe -m playwright install chromium
  ```

- `pyrightconfig.json` is the current type-checker configuration, but Pyright is
  not pinned in `requirements.txt`. Run `pyright` only when it is available or
  the task explicitly adds it to the supported toolchain; report honestly when
  it was not run.
- Ruff and pytest-cov are not currently project dependencies. Do not claim or
  require those checks without first adding and documenting the tooling.

## Completion Checklist

Before handing off a change:

1. Review the diff for accidental edits, generated runtime data, credentials,
   and customer content.
2. Run the most relevant focused tests and any required frontend build.
3. Run the full pytest suite for cross-cutting changes when practical.
4. Update maintained documentation when behavior, configuration, API contracts,
   or operator workflows change.
5. Report the files changed, exact verification commands, outcomes, and any
   checks not run.
