# Test and verify changes

| Item | Value |
| --- | --- |
| Audience | Developers and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-11-09 — repository/source review; no live deployment check; Pyright, isolated collection and API regressions |
| Applies to | Production application; SQLite schema 9 |

## Testing and verification

Tests live under `test/` and are organized by the layer or behavior they cover;
the test tree is the authoritative inventory. Prototype tests are isolated under
`test/pipeline_visual_editor_prototype/`. Use the focused checks below, then
select neighboring tests from the relevant area when changing a boundary.

Live LlamaCloud checks are opt-in because they require credentials and external
resources. Browser tests may require Playwright Chromium. Pyright 1.1.414,
pytest, pytest-cov, and Playwright are pinned in `requirements-dev.txt`;
production installs use `requirements.txt`. Ruff is not a supported project check.

The shared visual-app fixture uses `test/helpers_visual.py` to launch an
isolated server with a 60-second readiness deadline. Startup stdout/stderr go
to `visual-server.log` in the temporary fixture directory, so a large diagnostic
cannot fill an unread pipe and block startup. Failure messages identify the
log instead of copying child output into pytest errors. The helper terminates
and reaps the server on startup failure, test failure, and normal teardown.

Run browser suites sequentially when host memory is constrained. Transient
browser launch or database file errors should be reproduced with adequate
headroom before changing application behavior. Use `--tb=short` for diagnostic
runs to avoid displaying credentials or other sensitive local values from
third-party traceback frames.

Useful focused checks from the repository root are:

```powershell
# Configuration and process startup
.\.venv\Scripts\python.exe -m pytest -q test\core\test_configuration_boundaries.py

# Database migration boundaries
.\.venv\Scripts\python.exe -m pytest -q test\db\test_migration_boundaries.py

# Upload, workflow, and review integration
.\.venv\Scripts\python.exe -m pytest -q test\integration\test_batch_upload_api.py test\integration\test_review_ui_api.py

# Browser smoke coverage
.\.venv\Scripts\python.exe -m pytest -q test\visual\test_configuration_boundaries_visual.py

# Full suite without opt-in live provider checks
$env:RUN_LLAMACLOUD_SPLIT_SMOKE = '0'
.\.venv\Scripts\python.exe -m pytest -v --ignore=test/third_party/llamacloud_connection_test.py
```

Changes to templates, JavaScript, CSS, or browser behavior require a visual
test decision; backend-only changes normally do not. Changes to startup,
migrations, workflow execution, review resume, or artifact registration should
include the corresponding focused integration tests before the full suite.


## Select the verification scope

Every feature/fix needs meaningful tests. Start with the owning unit tests and
nearby integration or browser tests, then run the full suite for broad changes.
Keep all fixtures independent of the active deployment YAML/database and use
synthetic data. Tests are named `test_*.py` or `*_test.py`; functions start `test_`.

Before collection, `test/conftest.py` creates a temporary synthetic configuration
and initialized database, and points the test process's `CONFIG_PATH` at them.
This isolates import-time construction of `web.server:app` from the active
deployment, even when the inherited configuration path is invalid or missing.
The previous environment is restored when pytest exits. Individual tests should
still inject their own fixtures; process-startup tests explicitly pass their
intended configuration to subprocesses.

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\path\to\test_file.py
.\.venv\Scripts\python.exe -m pytest -v --ignore=test/third_party/llamacloud_connection_test.py
```

The second command excludes the credentialed live LlamaCloud module. Run live
provider checks only when specifically requested and credentials are supplied.
If Chromium is missing for visual tests:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

After a change, review the diff for accidental edits, generated data and secrets.
Report exact commands, outcomes and checks omitted. Do not stage, commit or
discard existing user changes without a request.

## Static type checking

Run the pinned checker from the repository environment, using the existing
Python 3.13/basic-mode [configuration](../../pyrightconfig.json):

```powershell
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe
```

The configured scope includes `main.py`, `modules`, `standard_step`, `test`,
`tools`, and Python code in `web`. JavaScript uses the project's module and
browser tests. Keep diagnostics enabled and fix annotations or real control-flow
gaps rather than excluding failing files. When reviewing a change, compare the
same checker, configuration and environment against an isolated HEAD snapshot
to distinguish introduced diagnostics from existing ones. The R4 audit cleared
both sets; see the [verification record](../../tasks/tasks-r4-business-validation.md#post-implementation-type-and-regression-audit--2026-10-31).

Positive tests should check optional results before using them. The
[test assertion helpers](../../test/helpers_assertions.py) check existence and
verify mocked dependencies at runtime while narrowing their static types.
Keep a real service typed as its service class; narrow its mocked methods when
configuring `return_value` or checking calls. Deliberate invalid-input tests can
cross a type boundary locally and explicitly, without suppressing checks for an
entire file. Pyright needs no production dependency or runtime database access.
See the [official CLI reference](https://github.com/microsoft/pyright/blob/main/docs/command-line.md).
