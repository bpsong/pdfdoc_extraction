# Verification and Superstore walkthrough — 2026-11-09

Final verification passed: **1,975 pytest tests passed, four expected skips;
Pyright reported zero errors and warnings**. This report separates initial
failures, repairs, focused results, and final verification.

## Repairs

1. Test collection previously imported web.server against the active deployment.
   The shared pytest bootstrap now supplies a temporary synthetic configuration
   and initialized database before imports; missing/invalid inherited config
   paths have subprocess collection regressions.
2. Browser acceptance raced completion's queue redirect when opening the accepted
   review. The test now waits for that transition.
3. JSON filename templates now bind reserved `{id}` to context.document_id, then
   legacy context.id. Extracted id fields and exported business data are unchanged.
   Unit and real review/resume regressions cover conflicting IDs and two documents
   with the same invoice reference producing distinct registered artifacts.
4. The mobile review header now constrains its content width and gives its UUID
   badge sizing/truncation precedence over the general badge rule. Application
   CSS cache version is updated. Native-scrollbar tests cover active and completed
   reviews with/without business rules; table scrolling remains independent.

## Commands and outcomes

All Python commands used the repository virtual environment from the repository
root. The initial plain `pytest -v` stopped at collection with seven errors caused
by active-deployment startup verification; no test body ran in that attempt.

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/core/test_pytest_collection_isolation.py test/integration/test_new_ui_routes.py test/integration/test_api_endpoints.py test/tools/test_documentation_structure.py --tb=short
```

66 passed in 19.49 seconds.

```powershell
$env:RUN_LLAMACLOUD_SPLIT_SMOKE = '0'
.\.venv\Scripts\python.exe -m pytest -v --ignore=test/third_party/llamacloud_connection_test.py --tb=short --junitxml=output/verification-2026-11-09/full-pytest.xml
```

Initial complete run: 1 failed, 1,969 passed, 4 skipped in 426.98 seconds.
The failure was the completion navigation race described above.

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_business_validation_acceptance_visual.py --tb=short
```

After the navigation fix: 2 passed in 17.61 seconds.

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/storage/test_storage_json.py test/storage/test_storage_edge_cases.py test/integration/test_business_validation_acceptance.py test/visual/test_review_validation_visual.py test/visual/test_business_validation_acceptance_visual.py test/tools/test_documentation_structure.py --tb=short
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_review_validation_visual.py::test_review_header_fits_when_scrollbar_reserves_viewport_space --tb=short
```

53 passed in 64.40 seconds; the subsequently extended active/completed scrollbar
cases passed 2 tests in 14.44 seconds. New storage regressions were observed
failing before the JSON fix. Layout reproduction was confirmed in the native
live browser; the headless defaults had hidden the scrollbar space.

```powershell
npm run build:css
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe
git diff --check
```

CSS build passed (existing Browserslist data-age notice); 16 release graphs
validated; Pyright reported 0 errors, 0 warnings, 0 informations. Whitespace
checks passed with line-ending normalization warnings.

Final commands:

```powershell
$env:RUN_LLAMACLOUD_SPLIT_SMOKE = '0'
.\.venv\Scripts\python.exe -m pytest -v --ignore=test/third_party/llamacloud_connection_test.py --tb=short --junitxml=output/verification-2026-11-09/final-pytest.xml
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe
```

Final pytest: **1,975 passed, four skipped in 447.09 seconds**. All collected
browser cases passed. Final Pyright: **0 errors, 0 warnings, 0 informations**.
Logs: final-pytest.log, final-pytest.xml, and final-pyright.log in this directory.

Expected skips: the opt-in live LlamaCloud Split smoke and three Windows-specific
permission cases. The credentialed live LlamaCloud connection module was excluded
explicitly, following repository guidance. No credentialed cloud test was run.

After the final documentation updates:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/tools/test_documentation_structure.py --tb=short
git diff --check
```

18 documentation tests passed in 0.87 seconds; the diff check passed.

## Live operator walkthrough

Used the agent-browser skill against the actual local app, existing operator
account, and existing LiteParse Invoice Review JSON v1 pipeline (three steps:
local LiteParse/Ollama extraction, human review, JSON storage). No cloud provider,
synthetic extraction, account reset, pipeline publication, or binding change was
used. The inactive business-validation clone remains inactive.

The local database and existing journal were copied under live/pre-live.sqlite3
before startup. The app was restarted once to load the JSON fix. The model loaded
for the walkthrough was released afterward; the local application remains running.
The owned browser session was closed, and no authentication profile was saved.

Source: the existing Superstore sample invoice 36258. Tested upload/selection,
processing status, PDF preview, claim, a temporary one-cent draft edit and reload,
restoration of the printed value before acceptance, release/reclaim, completion,
read-only accepted review, desktop/narrow layout, and actual output registration.

| Run | Batch | Document | Result |
| --- | --- | --- | --- |
| Before fix | 080c937e-958f-4d1c-90d8-4b23d761c3cb | 5cb6a14d-5edf-4dd8-a074-fe4affc38daf | Completed; naming bug reproduced as unknown_8.json |
| After fix | 7ea0fb9d-b69b-4ca8-a730-1da81a18e81e | a6b21b8c-566d-4509-82ab-43f7e7eae767 | Completed; filename a6b21b8c-566d-4509-82ab-43f7e7eae767.json |

Both accepted JSON payloads match persisted final fields and the independently
checked printed invoice/line amounts. Both registered source PDFs have the same
SHA-256 as the original. The earlier export remains intact. Verified by:

```powershell
.\.venv\Scripts\python.exe output/verification-2026-11-09/live/verify_outputs.py
```

Passed. Summary: live/output-verification.local.json; no raw business payload is
printed by the verifier. No JavaScript errors were reported by the browser.

Mobile measurements at innerWidth 390: original active review clientWidth 375,
scrollWidth 379; original completed review could reach scrollWidth 407. After
the fix, active and completed views measured 375/375. The line-item table retains
its own horizontal scrolling.

Screenshots under live/:

- 03-review-desktop.png: source PDF and extracted fields before the fixes.
- 04-review-mobile-before.png: original narrow review.
- 05-review-mobile-fixed.png: completed narrow review with constrained badges.
- 06-fixed-review-desktop.png and 07-fixed-review-mobile.png: second live review.
- 08-completed-batch.png: completed second batch.
- 09-fixed-output.png: accepted values and correctly named registered JSON.

Limitations: the selected live pipeline has no R4 business-rule panel and only
exports JSON. Multi-rule validation and JSON/CSV/PDF resume are covered by the
synthetic automated acceptance suite. Live LlamaCloud tests and standalone
performance benchmarks were not run. Do not interpret this sample as an extraction
benchmark.
Private document evidence, runtime files, backups, and this report remain local.
