# Manual split validation: 2026-10-07

| Item | Value |
| --- | --- |
| Audience | Readers investigating historical evidence |
| Owner | Application maintainers |
| Status | Historical record |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Original checkpoint or snapshot documented below |

This is a historical record from **2026-10-07**. Its observations,
test counts, model choices and deployment identifiers describe that checkpoint,
not a newly verified run. Use [reference/tasks/splitting.md](../../reference/tasks/splitting.md)
for current instructions. The [exact original](../archive/2026-10-10/docs/manual_split_validation.md)
is retained in the snapshot; navigation links in this reading copy are updated.

## Manual split validation — 2026-10-07

### Automated checks

- Full suite: `.\.venv\Scripts\python.exe -m pytest -q --tb=short`:
  **1,586 passed, 4 skipped**, 304.61 seconds.
- Final focused checks:
  `.\.venv\Scripts\python.exe -m pytest -q test/integration/test_manual_split.py test/visual/test_manual_split_ui.py test/standard_step/split/test_llamacloud_split_task.py test/integration/test_llamacloud_split_fanout.py --tb=short`:
  **41 passed**, 18.31 seconds. Includes malformed approval actions and the
  isolated manual browser test added after the full suite was collected.
- `npm run build:css`: passed. Browserslist reported its existing outdated
  compatibility-data warning.
- `.\.venv\Scripts\python.exe -m tools.frontend_release_check check`:
  **17 feature graphs validated**.
- `git diff --check`: passed.
- Pyright was unavailable and was not run. No live LlamaCloud check was run.

Synthetic tests cover migration from version 7, one-page skip, operator skip,
strict boundaries/actions, locked drafts, stale revisions, source mismatch,
immutable/idempotent approvals, API writes, failed-launch recovery,
undispatched-child recovery, preserved upstream context, artifact registration,
correct child pages, duplicate dispatch prevention, and completed fan-in.
The isolated browser test exercises actual local PDF.js rendering, vertical
pages, matching markers, keyboard selection, draft reload, mobile width, and
same-origin viewer requests. Cloud split regression tests remain passing.

### Admin pipeline and real browser walkthrough

Created, published, and activated **Manual Split Invoice Review JSON** through
the authenticated admin API in the browser. Template:
`88d81417-2d6d-44d7-b373-c0264888a81a`.

Steps: Manual Split → LiteParse/Ollama field extraction → Review Gate → JSON
export. Uses the existing local `qwen3.5:9b-q4_K_M` model and published invoice
review schema. Split PDFs use `data/manual_split_pdfs`; exports use
`data/manual_split_invoice_json`.

The following full walkthroughs used published version 1
(`c903f6f6-3ff9-4bac-a1ff-dde017eedf70`):

| Scenario | Result |
| --- | --- |
| One-page Superstore invoice | `single_page` skip; no split review or children; field review completed; one JSON artifact |
| `random_merged_invoices_16jun26.pdf`, four pages | Boundaries 1, 2, 3; four one-page children; each extracted/reviewed/exported; root and batch completed |
| `random_merged_invoices_31May26.pdf`, four pages | No boundaries; `operator_no_split` skip; original document continued; no children; field review and one JSON export completed |

The split walkthrough also saved and reloaded a draft and inspected matching
numbered checkbox/plan markers. The field review PDF previews were usable for
both split children and the unsplit original. Six registered JSON artifacts
were parsed and their invoice number, total, and supplier compared with the
reviewed SQLite final values; all matched. No documents were sent to a cloud
split or extraction provider.

Completed batches:

- `a7fca8fa-ad8a-42c4-93c6-1b8352ab9a31`: one original invoice plus four child leaves.
- `b461c64a-695c-4599-acff-7025396c4a78`: one unsplit original leaf.

After the walkthrough, published version 2
(`7c45e3ea-c106-4c11-8569-d75c4003966c`) changes only the export filename to
`invoice_{invoice_number}`. The inherited version-1 `{id}` template looked
for a missing extracted field and generated collision-safe `unknown*.json`
names; their artifact-to-document mapping remains correct. Version 2 passed
pipeline validation; the full browser walkthrough was on version 1.

Local screenshots and the pre-migration SQLite backup are under
`qa_artifacts/manual_split/`, which is ignored by Git. Runtime configuration,
documents, extracted values, credentials, and database backups are excluded
from source changes. Operational recovery limits are documented in
[Manual PDF split task](../../reference/tasks/splitting.md).

### Synthetic two-page invoice: operator chooses no split

On 2026-10-07, uploaded a synthetic single invoice continued across two pages
through published version 2. In the browser, claimed the manual review, left
the boundary checkbox unchecked, and selected **Continue without splitting**.
Reviewed the extracted fields against both source pages and completed review.

- Batch `f851c361-d465-46ec-8daa-428c03d9724f` completed.
- Decision: page count 2, boundaries `[]`, action `skip`, reason
  `operator_no_split`, phase `applied`.
- SQLite contains one original document and one processing job for the batch;
  zero child documents and zero split PDF artifacts. Every task run belongs to
  the original document. The manual split result has `children: []` and no
  fan-out pipeline state.
- Prefect contains three completed runs for that original document: initial
  processing, continuation after manual review, and continuation after field
  review. All have no parent task run; no split child workflows were spawned.
- One JSON artifact was exported with invoice number
  `DEMO-NOSPLIT-20261007`, total SGD 1,650.00, and all six line items across
  both pages. Version 2's invoice-number filename was also confirmed.

Read-only assertions against SQLite, Prefect flow records, and the exported
JSON passed. Local evidence and browser screenshots are saved under the ignored
`qa_artifacts/manual_split/` directory (`synthetic-no-split-evidence.json`,
`synthetic-no-split-before.png`, and `synthetic-field-review-page2.png`).

### Source review and operator validation — 2026-10-07

Reviewed the manual task, persistence, review APIs, resume/fan-out, shared
materializer, migration, task configuration, and browser changes. Fixed:

- Recovery could reset an already-claimed original continuation before its
  first task run existed, allowing a duplicate launch.
- Child documents were claimed before workflow loading; an unavailable loader
  left otherwise unstarted children stuck in processing.
- Recovery dispatch omitted the parent document and batch IDs, so downstream
  preflight failures could not be attributed or persisted.
- Successful runner cleanup blocked retrying failed split materialization.
  Recovery now allows that case, retains failed attempts in history, and
  prevents those recovered errors from contaminating child outcomes. Failed
  cleanup and any started downstream business work still block retry.
- Renewing a claim with unsaved boundaries could adopt another session's newer
  draft revision and overwrite its draft. The form now requires a reload when
  the saved revision changes. Browser assets were advanced to `manual-split-2`.

Verification after the fixes:

- `.\.venv\Scripts\python.exe -m pytest -q test/integration/test_manual_split.py --tb=short`:
  **29 passed**. Includes injected disk/loader failures and replay guards.
- `.\.venv\Scripts\python.exe -m pytest -q --tb=short`:
  **1,598 passed, 4 skipped**, 329.50 seconds. Includes the real browser test
  for conflicting drafts after claim renewal and existing cloud split tests.
- `.\.venv\Scripts\python.exe -m tools.frontend_release_check check`:
  **17 feature graphs validated**.
- `git diff --check`: passed. No CSS classes changed during this review;
  the previous CSS build remains applicable. Pyright was not run.

Restarted the local application and completed an additional live walkthrough
as **operator**, using **Manual Split Invoice Review JSON, version 2**:

1. Uploaded `synthetic_two_page_invoice.pdf` and claimed it from the queue.
2. Selected the boundary after page 1, inspected matching numbered markers,
   saved a draft, reloaded, and verified the boundary persisted.
3. Cleared the checkbox; the plan returned to one document, pages 1–2.
   Selected **Continue without splitting**.
4. Reviewed all six extracted line items and the total against both PDF pages,
   then completed field review as operator.
5. Verified batch `6c5335bd-c5ee-4e99-b39b-025bc1a7909d` completed with one
   original document, no children or split PDFs, and one JSON artifact.
   The saved decision is `skip` / `operator_no_split`, decided by `operator`.
   JSON contains invoice `DEMO-NOSPLIT-20261007`, SGD 1,650.00, and six items.
6. Queried Prefect: three completed runs, all on that original document,
   with no parent task run. These are initial processing and the two normal
   review continuations; no split fan-out occurred. No browser errors appeared.

No further known defects were found in the reviewed and exercised paths.
This conclusion is limited to the code review and checks described here;
documented crash/recovery limits still apply. The application was left running.

Ignored local evidence: `qa_artifacts/manual_split/review-full-pytest.log`,
`operator-evidence.json`, `operator-queue.png`,
`operator-boundary-selected.png`, `operator-no-split.png`,
`operator-field-review.png`, and `operator-completed-batch.png`.

### Submission waiting for child workflows — 2026-10-07

An operator subsequently reported **Applying decision…** remaining visible
after split children started. The completion endpoint awaited the entire
resume/fan-out call. Moving that call into a thread pool had kept the server
responsive, but had not released the browser's HTTP request. Earlier checks
verified eventual completion without asserting response timing during child
execution, so they missed this defect.

The endpoint now commits the decision, returns HTTP 202 with
`resume_scheduled: true`, and runs continuation in a server background task.
The form shows **Decision saved**, offers **View processing**, clears unsaved
state on acceptance, and refreshes application phase separately. Active
original continuations do not offer a retry action. Asset version is
`manual-split-3`. Accepted decisions still use the existing recovery rules;
background dispatch is not a durable queue.

Verification:

- `.\.venv\Scripts\python.exe -m pytest -q test/integration/test_manual_split.py test/visual/test_manual_split_ui.py test/services/test_resume_manager.py test/integration/test_review_pause_resume.py test/integration/test_new_ui_routes.py test/visual/test_operator_page_modules.py --tb=short`:
  **75 passed**, 22.45 seconds.
- A regression test executes the real resume and child flow through ASGI,
  blocks downstream work on an event, and asserts that the complete HTTP 202
  response has already been sent while the child remains blocked.
- The browser regression leaves an accepted decision pending and checks that
  the form shows **Decision saved** and **View processing**, rather than an
  indefinite saving state.
- Restarted the idle local app and opened the operator's submitted review
  `80450087-7dcb-41d9-b118-ea560c96cbb6`. It correctly shows the applied decision
  and processing link; its four child documents are completed. No resubmission
  was needed. Screenshot: `qa_artifacts/manual_split/async-decision-saved.png`.
- Frontend release graph and diff whitespace checks passed. The full suite
  was not repeated for this targeted fix; its prior result is recorded above.
