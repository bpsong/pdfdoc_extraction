# Test and verify changes

| Item | Value |
| --- | --- |
| Audience | Developers and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Testing and verification

Tests live under `test/` and are organized by the layer or behavior they cover;
the test tree is the authoritative inventory. Prototype tests are isolated under
`test/pipeline_visual_editor_prototype/`. Use the focused checks below, then
select neighboring tests from the relevant area when changing a boundary.

Live LlamaCloud checks are opt-in because they require credentials and external
resources. Browser tests may require Playwright Chromium. Pyright has
configuration but is not pinned in the project dependency files. Ruff is not a
supported project check. Pytest, pytest-cov, and Playwright are pinned in
`requirements-dev.txt`; production installs use `requirements.txt`.

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
