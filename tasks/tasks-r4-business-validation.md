# R4: Dynamic business validation implementation plan

| Item | Value |
| --- | --- |
| Status | Complete — all five phases implemented and verified |
| Updated | 2026-11-09 |
| Scope | R4 first on SQLite; PostgreSQL is not a prerequisite |
| Verification | Complete focused tests each phase; visual validation for phases that affect visible behavior |

The completed feature's audit follow-up is tracked separately in
[R4 audit follow-up](tasks-r4-audit-follow-up.md). Its unchecked work does not
change the historical verification recorded below.

## Product contract

A published review form can carry multiple independent business rules. The
first two validators check each row's quantity multiplied by unit price against
its line total, and the sum of entered line totals against an invoice subtotal
before discount/tax. Neither rule corrects values or consumes another rule's
calculated output. Both inspect the same current snapshot.

Rules have unique IDs, explicit validator versions, enabled state, field bindings,
severity (`warning` or `blocking`), and review-trigger policy. Arithmetic rules
also configure tolerance, decimal places, and rounding. Date-order and conditional
requirements share the same snapshot and policy without arithmetic settings.
Missing inputs and evaluation failures never count as
passes. Default warnings permit completion; unresolved blocking rules prevent
it. Initially there is no blocking override; a future permitted override needs
explicit authorization, a reason, and an audit event.

Use configurable deterministic templates and an explicit code allowlist of
versioned validators. Do not execute submitted Python, JavaScript, expressions,
or dynamic import paths. Approved specialized Python validators can be added
through reviewed code with their own typed configuration and tests. Do not
reuse the task import registry as if validators were executable pipeline tasks.

## Phase 1: Contracts and shared evaluator (complete)

Prerequisites: architecture, current schema/review services, gate, and task
standards inspected. No UI or existing runtime integration is required.

- [x] Define strict, versioned multi-rule configuration and structured results.
- [x] Implement allowlisted `line_amount:v1` and `sum_equals:v1` validators with
  decimal arithmetic, explicit rounding/tolerance, and row/cell paths.
- [x] Handle missing/invalid values, empty/malformed collections, disabled rules,
  duplicate/unknown rules, numeric/resource limits, and independence of checks.
- [x] Test simultaneous rules, independent failures, precision/tolerance edges,
  missing input, nested paths, deterministic behavior, and no input mutation.
- [x] Run focused evaluator and nearby schema/versioning regression tests; check
  document links and diff. Record results before closing the phase.

Visual validation: not applicable. This phase adds an unconnected backend service
and tests; it must not imply that the review screen already runs business rules.

## Phase 2: Versioned rule authoring and publication (complete)

Prerequisite: phase 1 complete.

- [x] Add optional `business_validation` to the review-schema definition; forms
  without it keep existing behavior. Validate rule syntax and bound field types
  through schema/config validation and the supported config-check surfaces.
- [x] Preserve rules through schema normalization, import/export, draft editing,
  publication, hashes, exact-version loading, and pipeline dependency checks.
  Reject unavailable validator versions at publication/startup; retain old
  implementations for existing published versions rather than swapping behavior.
- [x] Add a Business validation section to the production schema editor for
  multiple rules, field selection, severity, tolerance, rounding, and review
  policy. Preserve rules during unrelated field edits and flag broken bindings.
- [x] Test editor serialization, version pinning, bad bindings, old forms,
  export/import, and publication. Rebuild committed CSS if utilities change.
- [x] Visually inspect create/edit/reorder/disable/delete rules, validation
  errors, small screens, and publish/reopen using a synthetic local deployment.

## Phase 3: Gate and authoritative review backend (complete)

Prerequisite: phases 1-2 complete.

- [x] Reuse the evaluator at the review gate. Combine business findings with
  existing confidence/schema reasons without losing legacy rule flags. Rules
  configured to require review must catch high-confidence inconsistent values.
- [x] Before enabling enforcement, establish a mandatory form-format/capability
  version that prevents an incompatible older release from silently ignoring
  required rules. Phase 2 authoring alone is not a release-enforcement guarantee.
- [x] Evaluate the displayed snapshot (including saved drafts) on load; provide
  an authenticated POST revalidation endpoint for current unsaved corrections.
  Reuse completion's merge/normalization rules and reject manual-split items.
- [x] Preserve CSRF, permissions, ownership, and typed review contracts. Return
  rule/schema identity and a request/value revision so stale responses cannot
  masquerade as validation of current edits. Revalidation has no save/resume
  side effects and does not rerun OCR.
- [x] At completion independently validate actual submitted values against the
  pinned form. Atomically verify current ownership/data revision and commit
  corrections, final report, audit summary, and review state before resume.
  Roll back all acceptance writes on failure. Explicitly test ownership/revision
  changes between evaluation and acceptance.
- [x] Persist gate and accepted reports with source/form/validator identities in
  authoritative SQLite state via repositories. Avoid storing a history entry
  for every page load or button click; do not log raw values or secrets.
- [x] Test gate reasons, nonblocking warnings, blocking/inconclusive findings,
  saved/unsaved values, completion bypass attempts, rollback, retries, and resume.
- [x] Visually smoke-test the existing form against the changed response
  contracts to catch load/save/claim/completion regressions before phase 4.
- [x] Persist accepted fields absent from extraction rows, preserve explicit null
  corrections, and test rollback of inserted fields alongside other acceptance writes.

## Phase 4: Review-screen findings and revalidation (complete)

Prerequisite: phase 3 complete.

- [x] Add the Revalidate action and summary, with accessible findings beside
  nested/table fields and affected rows. Explain expected/actual/difference and
  distinguish failure, cannot evaluate, evaluator error, and passing checks.
- [x] Evaluate after initial values/draft restoration; invalidate findings after
  edits and row insertion/removal. Preserve unsaved edits on revalidation and
  discard out-of-order responses. Keep draft saving possible with findings.
- [x] Present blocking completion responses with useful findings. Allow warnings
  according to policy while recording the final accepted report server-side.
- [x] Test asynchronous UI behavior, source/correction views, locked/read-only
  reviews, escaped messages, and unaffected forms. Rebuild CSS when required.
- [x] Visually verify two simultaneous rules, separate row/subtotal warnings,
  missing inputs, correction/revalidation, stale status, row changes, warning
  completion, blocked completion, and keyboard/small-screen behavior.

- [x] Keep rendering from silently replacing missing object/array values;
  verify an unedited missing list sends no implicit correction.
- [x] Preserve newer edits during delayed draft saves, prevent conflicting
  save/complete actions, and make inputs inert during completion.
- [x] Bound detailed rendering to the first 100 findings, retain complete
  report counts, and display an explicit truncation notice.

## Phase 5: End-to-end acceptance and maintained documentation (complete)

Prerequisite: phases 1-4 complete.

- [x] Test a synthetic invoice from extraction through gate, draft restoration,
  correction, completion, resume, and existing JSON/CSV outputs, with multiple
  rules and no-rules compatibility. Do not call a live extraction provider.
- [x] Test retained form/validator versions after new publication, interruption,
  conflicting requests, evaluator errors, numeric limits, and safe failures.
- [x] Update user/admin/developer/schema documentation, the roadmap, and task
  guidelines where the integrated gate/context contract establishes a standard.
- [x] Reconcile the remaining roadmap R4 scope (date/conditional templates and
  approved specialized validators): implement required additions or explicitly
  agree deferral before declaring the parent roadmap item complete.
- [x] Run the relevant service/API/workflow/browser tests and full suite for
  the integrated cross-cutting change. Record skipped credentialed checks.
- [x] Perform a final visual walkthrough with synthetic invoices and capture
  evidence without credentials/customer data. Mark R4 complete only when all
  required phases and acceptance checks pass.

## Phase 1 technical contract

Optional form section (editor, authoritative backend, and operator findings are
implemented; phase 5 verifies integrated end-to-end acceptance):

```json
{
  "business_validation": {
    "format_version": 1,
    "rules": [
      {
        "id": "item_amount",
        "validator": "line_amount:v1",
        "collection": "/items",
        "quantity": "/quantity",
        "unit_price": "/unit_price",
        "line_total": "/line_total",
        "severity": "warning",
        "tolerance": "0.01",
        "decimal_places": 2
      },
      {
        "id": "invoice_subtotal",
        "validator": "sum_equals:v1",
        "collection": "/items",
        "item_value": "/line_total",
        "target": "/subtotal_before_discount",
        "severity": "blocking",
        "tolerance": "0.01",
        "decimal_places": 2
      }
    ]
  }
}
```

Bindings use non-root JSON Pointers, including `~0`/`~1` escaping. Collection
and subtotal paths are absolute; item paths are relative to each row. Finding
paths are absolute and row indices zero-based; UI labels will be one-based.
Independent rules run in configured order and rows in input order. Disabled
rules report skipped, even though their configuration must still be valid.

Arithmetic rounds expected and observed totals to configured decimal places
before comparing their absolute difference against an inclusive tolerance.
The sum rule sums entered amounts and rounds the final sum once. Defaults are
two decimal places, `ROUND_HALF_UP`, tolerance `0.01`, severity warning, and
`require_review=true`. `ROUND_HALF_EVEN` is also supported. Discounts/tax are
outside these two calculations; target the printed subtotal with that meaning.

Missing/invalid input reports `not_evaluated`; no partial sum is compared.
An empty item collection also reports `not_evaluated`. Blocking inconclusive
rules remain blocking; warning inconclusive rules remain visible. Blocking
findings require review even when `require_review=false`; that flag controls
nonblocking findings. Infrastructure errors always block and require review.
No rules yields an empty report.

Limits: at most 50 rules and 1,000 rows per rule; non-root JSON Pointers at most
256 characters and 16 segments; numeric inputs at most 128 characters, 28
significant digits and adjusted decimal exponent between -28 and 28 (zero
included). Reject booleans, nonfinite values and localized currency formatting.
Use a private decimal context independent of the caller. Numeric reports use
decimal strings; they are business data for the review response, not log text.

## Visual test access

Existing bcrypt password hashes cannot recover the admin password. Use a
temporary config/database with synthetic admin/operator accounts for visual
checks, or an existing authenticated session authorized by the maintainer.
Never reset the active deployment for test access. The documented recovery
command replaces both fixed-account passwords and is not a routine test step.
See [account setup/recovery](../docs/it-support/account-recovery.md).

## Relevant Files

- [Development requirements](../requirements-dev.txt): pins Pyright 1.1.414 for repeatable repository-environment checks.
- [Typed test assertions](../test/helpers_assertions.py): runtime checks that narrow positive optional results and mocked dependencies without weakening production types.
- [Pipeline mock tests](../test/services/test_pipeline_template_branches.py), [form mock tests](../test/services/test_review_schema_version_branches.py), and [review mock tests](../test/services/test_review_service_branches.py): explicitly narrow mocked methods; the review file's broad optional-subscript suppression was removed.
- [Upload receiver tests](../test/services/test_upload_receiver.py) and [stored-validator tests](../test/tools/config_check/test_stored_validator_complete.py): check optional path configuration and type mocked connection calls.
- [Development setup](../docs/developer/development-setup.md) and [verification guide](../docs/developer/testing-and-verification.md): supported type-check commands, scope, and regression workflow.

- [Approved registry](../modules/services/business_validation_registry.py): immutable descriptors, strict typed configuration, explicit version retention, and schema-binding metadata.
- [Extension tests](../test/services/test_business_validation_extensions.py): date/conditional semantics, typed constants, approved custom validators, isolation, result limits, and safe plugin failures.
- [Workflow acceptance helper](../test/helpers_business_validation_workflow.py): readable synthetic invoice and real pinned extraction/review/export workflow with offline provider wrappers.
- [Workflow acceptance tests](../test/integration/test_business_validation_acceptance.py): real resume/JSON/CSV/renamed PDF, no-rules compatibility, retained versions, concurrency, interruption, errors and limits.
- [Integrated browser acceptance](../test/visual/test_business_validation_acceptance_visual.py): four-template authoring, corrections, draft recovery, independent acceptance and actual exports at desktop/mobile widths.
- [Validator developer guide](../docs/developer/business-validation-plugins.md): approval, strict configuration, binding metadata, bounded pure evaluators, safe failure and deployment compatibility.
- [Developer navigation](../docs/developer/README.md) and [backend guide](../docs/developer/backend-development.md): extension ownership and documentation entry points.
- [Documentation manifest](../docs/documentation-map.json): records the new canonical developer guide.

- [Implementation plan](tasks-r4-business-validation.md): phases, contracts, and verification evidence.
- [Live Superstore acceptance report](../output/superstore-business-validation-2026-11-08/report.md): local-only browser evidence, published test configuration, output checks and follow-up findings; private artifacts must not be committed.
- [Roadmap](roadmap.md): R4 progress and implementation order.
- [Business evaluator](../modules/services/business_validation.py): phase 1 strict configuration, results, and pure decimal evaluator.
- [Evaluator tests](../test/services/test_business_validation.py): phase 1 synthetic unit and contract tests.
- [Rule/schema binding validator](../modules/services/business_validation_schema.py): strict rule syntax and numeric field/collection compatibility without modifying definitions.
- [Schema service](../modules/services/schema_service.py): shared schema validation and normalization preserving optional rules.
- [Schema version service](../modules/services/review_schema_version_service.py): exact-version compatibility checks with immutable rule definitions.
- [Validation facade](../modules/services/validation_facade.py): pinned pipeline dependency checks used by publication and config-check.
- [Startup service](../modules/services/startup_service.py): read-only published-rule compatibility checks before process readiness.
- [Rule editor module](../web/static/js/schema-editor/business-rules.js): multi-rule authoring model, dropdown bindings, safe rendering, and inline findings.
- [Schema editor controller](../web/static/js/schema-editor/controller.js): rule events, validation state, focus, and safe save/publish behavior.
- [Schema editor entry](../web/static/js/schema-editor/index.js): matching feature release cache version.
- [Schema editor template](../web/templates/schema_editor.html): rule authoring controls and current runtime availability notice.
- [App styles](../web/static/css/app.css): responsive rule cards and field grids.
- [App base template](../web/templates/app_base.html): shared CSS cache version.
- [Synthetic form helper](../test/helpers_business_validation.py): reusable non-customer invoice configuration.
- [Rule/schema tests](../test/services/test_business_validation_schema.py): bindings, stored versions, portable validation, hashes, and unavailable-plugin failures.
- [Startup tests](../test/services/test_startup_service.py): rule checks in migration/verify ordering.
- [Versioned schema API tests](../test/integration/test_versioned_schema_api.py): authoring round trip and failed publication.
- [Rule editor module tests](../test/visual/test_business_rules_editor_modules.py): field preservation, broken references, ordering, deletion, and escaping.
- [Rule editor browser test](../test/visual/test_business_rules_editor_visual.py): isolated real-browser desktop/mobile authoring and publication acceptance.
- [Schema module tests](../test/visual/test_schema_editor_modules.py): matching feature asset versions.
- [Admin route tests](../test/integration/test_new_ui_routes.py): updated schema-editor entry asset expectation.
- [UI asset tests](../test/visual/test_ui_performance_assets.py): versioned schema route/asset expectation.
- [Admin form guide](../docs/admin/managing-review-forms.md): multiple-rule authoring instructions and current integration limits.
- [Schema reference](../docs/reference/review-schema-format.md): portable rule configuration, bounds, bindings, and compatibility.
- [Deployment guide](../docs/it-support/deployment-and-upgrades.md): matching assets and retention of published validator implementations.
- [Runtime report service](../modules/services/review_business_validation.py): report provenance, safe failure, gate reasons, and audit summaries without raw amounts.
- [Review service](../modules/services/review_service.py): draft/display snapshots, revalidation, revision/ownership checks, and atomic acceptance before resume.
- [Review gate](../standard_step/review/review_gate.py): persisted-value evaluation combined with existing reasons and durable gate reports.
- [Connection helpers](../modules/db/connection.py): real read snapshots and atomic/savepoint rollback scopes.
- [Repositories](../modules/db/repositories.py): explicitly materialize accepted fields absent from extraction rows.
- [Version contracts](../modules/services/versioned_config_contracts.py): mandatory format-2 business-rule capability alongside legacy format 1.
- [Pipeline definition service](../modules/services/pipeline_definition_service.py): enforce/inject the exact form capability before task execution.
- [Stored config validator](../tools/config_check/stored_validator.py): portable form formats 1 and 2.
- [API router](../modules/api_router.py): authenticated revalidation and structured review validation/conflict responses.
- [Review API module](../web/static/js/human-review/api.js): send current review revision and support the unsaved-validation endpoint.
- [Review controller](../web/static/js/human-review/controller.js): retain the current loaded revision after claim/load/save.
- [Review model](../web/static/js/human-review/model.js): preserve an explicit null correction instead of restoring its original value.
- [Review entry](../web/static/js/human-review/index.js): matching phase-3 asset graph.
- [Review template](../web/templates/human_review.html): matching review asset cache version.
- [Runtime service tests](../test/services/test_review_business_validation.py): gate policy/provenance, independent rules, no-write revalidation, conflicts, rollback/savepoints, missing fields, and commit-before-resume.
- [Capability tests](../test/services/test_business_rule_capability.py): explicit legacy republishing, retained immutable versions, and mandatory pipeline capability checks.
- [Review API tests](../test/integration/test_review_business_validation_api.py): revisions, reports, auth/CSRF, typed bodies, ownership, and manual-split rejection.
- [Review branch tests](../test/services/test_review_service_branches.py): existing defensive tests updated for repository snapshot contracts.
- [Review module tests](../test/visual/test_human_review_modules.py): revision transport, explicit null, and matching asset version.
- [Review browser test](../test/visual/test_review_business_validation_visual.py): isolated production claim/save/reload/release/reclaim/block/accept at desktop/mobile widths.
- [API reference](../docs/reference/api-contracts.md): revalidation request/response, merge, ownership, revision, and completion contracts.
- [Review gate reference](../docs/reference/tasks/review-gate.md): pinned rules, durable reports, and completion behavior.
- [Task standards](standard_task_creation_guidelines.md): persisted-value/form identity and commit-before-resume conventions.
- [Review validation lifecycle](../web/static/js/human-review/validation.js): edit/request/source/form guards, stale/error/current reports, and read-only action policy.
- [Review findings renderer](../web/static/js/human-review/validation-view.js): safe text rendering, status/counts, decimal evidence, accessible row/field annotations, and keyboard location links.
- [Review field renderer](../web/static/js/human-review/field-view.js): pointer metadata, change notifications, row operations, and render-only preservation of missing values.
- [Review presentation](../web/static/js/human-review/view.js): safe save/completion busy states and responsive scroll offsets below the sticky header.
- [Validation lifecycle tests](../test/visual/test_review_validation_modules.py): pure-module response ordering, snapshot/form identities, ownership, expiry, failures, and pointer escaping.
- [Validation browser acceptance](../test/visual/test_review_validation_visual.py): multiple independent rules, races, drafts, row renumbering, source views, readonly/no-rules/missing/nested forms, escaping, and desktop/mobile behavior.
- [Operator review guide](../docs/operator/reviewing-extracted-data.md): current/stale findings, evidence, revalidation, draft and completion workflows.
- [Vendor stylesheet](../web/static/css/vendor.css): rebuilt Tailwind/DaisyUI output, including the generated sticky utility.
- [Login template](../web/templates/login.html): matching rebuilt vendor stylesheet cache version.

## Verification evidence

Phase 1 completed on 2026-10-29. The initial focused evaluator run passed 70
tests. After policy review and additional boundary cases, this command passed
**124 tests**, including 80 evaluator cases plus existing schema/versioning and
documentation regression tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\services\test_business_validation.py test\services\test_schema_service.py test\services\test_schema_service_edge_cases.py test\services\test_review_schema_version_service.py test\services\test_review_schema_version_branches.py test\tools\test_documentation_structure.py
```

Standalone local-link/fragment checks passed for this plan and the roadmap.
`git diff --check` passed; new files were also checked for trailing whitespace.
Review confirmed no runtime data, credentials, or unrelated source changes.
No dependencies, database migrations, task standards, or frontend assets changed.

Full-suite/Pyright checks were not run for the isolated, unconnected service.
No browser or live-provider checks were run; phase 1 has no UI changes and visual
validation is assigned to phases 2-5 above. Existing deployment credentials were
not read or changed. Phase 2 results are recorded separately below.

### Phase 2 verification — 2026-10-29

Completed optional rule/schema validation, authoring, immutable version round
trips, pipeline dependency checks, read-only startup compatibility, and production
editor controls. Legacy forms and omitted optional rule defaults are preserved.
No database migration or new dependency was required. Phase 3 is the next
unchecked phase; the editor explicitly identifies rules as authoring-only.

The focused service/API/editor/documentation regression run passed **185 tests**.
The broader final suite passed **1,802 tests with 4 skips** using an initialized
synthetic configuration/database for collection-time application startup:

```powershell
# CONFIG_PATH must identify the isolated synthetic configuration, not active state.
$env:CONFIG_PATH = 'path\to\isolated\config.yaml'
$env:APP_ENV = 'development'
$env:ENV = 'development'
$env:ENVIRONMENT = 'development'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
```

An initial unscoped full-suite attempt stopped during collection because the
default local database lacked `pipeline_cleanup_previews`. It was not migrated
or repaired for testing. Intermediate asset-version and browser-fixture failures
were corrected before the final full run. The additional omitted-defaults
regression was verified separately after suite collection: **28 rule/schema and
editor-module tests passed**. The final real-browser test passed after the final
UI changes and evidence capture:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test\visual\test_business_rules_editor_visual.py
.\.venv\Scripts\python.exe -m pytest -q test\visual\test_business_rules_editor_modules.py test\services\test_business_validation_schema.py
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
npm run build:css
```

Frontend release validation passed all 16 feature graphs. CSS rebuilding passed;
the vendor CSS content was unchanged, while scoped app CSS and its cache key were
updated. Portable review-form validation also passed through
`tools.config_check validate-file --kind review-schema --format json` with a
synthetic file. Documentation links/fragments and whitespace/diff checks passed.

Visual verification used a real production app instance with temporary state and
synthetic accounts at 1440x1000 and 390x844. It covered add/edit/reorder/disable/
delete, local and backend publication errors, saving/publishing/reloading,
retained rules after unrelated field edits, broken-binding repair, and mobile
layout with no horizontal overflow or JavaScript page errors. Desktop, mobile,
and mobile-rule screenshots were visually inspected. Local ignored evidence:
`output/playwright/r4-phase2/desktop.png`, `mobile.png`, `mobile-rule.png`, and
`full-suite.log`. Agent-browser verified initial authoring/publication; a stalled
native-dialog command was followed by the reproducible Playwright acceptance
test. Temporary browser/server/diagnostic sessions were stopped afterward.

Pyright was not run because it is not installed in the repository virtual
environment. No live extraction-provider calls or active-account credential
changes were made. Existing task standards were unchanged; phase 3 will update
them if integrated gate/context behavior establishes a new task contract.

### Phase 3 verification — 2026-10-29

Completed gate evaluation, displayed/saved-draft reports, authenticated unsaved
revalidation, and independent completion-time enforcement. Source/form/rule
identities and opaque review/value revisions accompany reports. Completion
rechecks the live owner, lease, extraction/source revision, and pinned form before
committing corrections, accepted report, task/review/document state, and audit
summary together. Resume begins after commit. Read/revalidation requests neither
save reports nor extend locks, audit each evaluation, resume, or rerun OCR.

Business-rule forms now publish using mandatory outer format 2; the rule section
still uses format 1. Legacy rule-bearing format-1 publications remain immutable
and inspectable, but execution requires explicit republishing and pipeline
repinning. No-rules forms retain format 1. The production review asset graph is
`r4-phase3`; the editor now describes active backend enforcement. Detailed inline
findings and the Revalidate button remain phase 4 work.

The final focused contract/regression run passed **60 tests**:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/services/test_review_business_validation.py test/services/test_business_rule_capability.py test/services/test_review_service_branches.py test/integration/test_review_business_validation_api.py test/visual/test_human_review_modules.py --basetemp output/pytest-r4-phase3-final-focused --tb=short
```

These cover independent rules, high-confidence mismatches, legacy gate reasons,
warning/blocking/inconclusive policy, drafts and unsaved edits, auth/CSRF, typed
review kinds, mandatory/stale revisions, lost ownership/expiry, extraction/source
races, evaluator failure, missing persisted fields, explicit null corrections,
rollback at each acceptance stage, nested savepoints, and commit-before-resume.
Earlier nearby service/gate/version/API runs also passed their unaffected cases.

The complete suite collected **1,860 tests** and finished with **1,855 passed,
4 skipped, and 1 temporary-path fixture failure**, using an isolated initialized
configuration/database, never the active deployment:

```powershell
$env:CONFIG_PATH = 'path\to\isolated\config.yaml'
$env:APP_ENV = 'development'
$env:ENV = 'development'
$env:ENVIRONMENT = 'development'
$env:R4_VISUAL_EVIDENCE_DIR = 'D:\python_code\pdfdoc_extraction\output\playwright\r4-phase3'
.\.venv\Scripts\python.exe -m pytest -q --tb=short --basetemp output/pytest-r4-phase3-full
```

The existing `test_router_remaining_nested_helpers` assumes the temporary parent
is outside the project when simulating an escaped path. The selected basetemp
was inside the project, so that simulated path was correctly allowed. No
application or test source change was needed. Rerunning its entire module with
normal external temporary paths passed **all 6 tests**, including the failed
case; all 1,856 non-skipped collected cases therefore passed across these runs.
The full command itself is recorded as having the fixture failure, not as a clean
single-run pass. Future full runs should omit the in-project basetemp override.

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/integration/test_api_router_helpers.py --tb=short
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_review_business_validation_visual.py --basetemp output/pytest-r4-phase3-visual --tb=short
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
npm run build:css
```

The production-app browser smoke passed standalone after fixture corrections
and again in the full suite. At 1440x1000 and 390x844 it verified claim, blocked
completion with edits retained, draft save/reload, release/reclaim, and completion
with an allowed warning. Desktop and mobile/form screenshots were visually
inspected, with no page errors or page-level horizontal overflow. The visual
fixture stubs only downstream resume to avoid Prefect/provider activity; separate
service tests verify that resume sees committed values and the accepted report.
An initial visual fixture used a PDF outside allowed preview roots and attempted
real Prefect continuation; its fixture was corrected without changing production
preview or resume behavior. Its owned ephemeral process was stopped.

Ignored evidence is retained under `output/playwright/r4-phase3/`:
`review-desktop.png`, `review-mobile.png`, `review-mobile-form.png`, and
`full-suite.log`. Temporary synthetic test folders are retained there for
diagnostics rather than included as source. Frontend release validation passed
all 16 feature graphs; CSS rebuilding passed with unchanged vendor CSS content.
Documentation/link and whitespace checks are recorded in the completion checks
below. No dependencies or database migrations were added. Pyright was not run
because it is not installed in the repository virtual environment. No live
extraction-provider calls or active-database/account credential changes were made.

#### Completion checks

The final combined service/API/browser-module/documentation check passed **84
tests** in a fresh external temporary directory. An immediately preceding run
passed 83 tests and encountered one SQLite disk I/O error during temporary API
fixture setup; rerunning the entire set in fresh state passed without any source
change. No active database was involved.

```powershell
$r4CompletionBase = Join-Path ([System.IO.Path]::GetTempPath()) ('r4-phase3-completion-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q test/services/test_review_business_validation.py test/services/test_business_rule_capability.py test/services/test_review_service_branches.py test/integration/test_review_business_validation_api.py test/visual/test_human_review_modules.py test/integration/test_api_router_helpers.py test/tools/test_documentation_structure.py --basetemp $r4CompletionBase --tb=short
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
git -c core.safecrlf=false diff --check
git ls-files --others --exclude-standard output
```

All 16 frontend graphs and the final diff check passed. Maintained documentation
tests, standalone plan/roadmap local-link/fragment checks, and whitespace checks
for new source files passed. No untracked runtime/output data remains outside
ignored diagnostic folders. Phase 3 is complete; phase 4 is the next unchecked
phase, and the parent R4 roadmap item remains in progress. Nothing was staged or
committed.

### Phase 4 verification — 2026-10-29

Completed the production Business checks summary and Revalidate action, with
separate warning/blocking outcomes, cannot-evaluate/error states, decimal
expected/actual/difference evidence, and findings beside nested fields and table
rows. Keyboard location buttons and field descriptions connect the summary to
the affected inputs. Passing and disabled outcomes are aggregated by rule;
large reports retain full counts and explicitly limit detailed annotations/list
entries to the first 100 findings. Messages are inserted as text, never HTML.

Edits and row insertion/removal clear old annotations and mark results stale.
Replies must match the current request, edit generation/value snapshot, review
revision, and exact form/hash/document identity. Late replies/errors are ignored.
Checks preserve input nodes, focus, source display mode, and unsaved values.
Draft-save responses preserve any newer local edits and leave them stale;
conflicting actions are disabled during the save. Completion makes inputs inert
while accepting the submitted snapshot, and structured blocking replies restore
useful findings without discarding edits. Completed items show their accepted
report; unavailable claims/forms and no-rules forms keep the appropriate read-only
or hidden controls. The server remains responsible for completion enforcement.

Rendering no longer silently replaces a missing object/array with an empty value.
The missing-list browser regression confirms an untouched form sends no implicit
correction. Programmatic finding navigation accounts for the mobile sticky
header and nested scroll containers, with an observed responsive header offset.

The focused service/API/module/asset/documentation command passed **128 tests**
after using a fresh, short external temporary directory. An earlier run passed
126 tests and hit one temporary SQLite setup/open failure; another shell command
reported Windows error 1450 (insufficient system resources). No production fix
was made for those host errors. The fresh complete focused run passed.

```powershell
$env:CONFIG_PATH = 'D:\python_code\pdfdoc_extraction\output\playwright\r4-phase4\bootstrap\config.yaml'
$env:APP_ENV = 'development'
$env:ENV = 'development'
$env:ENVIRONMENT = 'development'
$r4CheckBase = Join-Path ([System.IO.Path]::GetTempPath()) ('r4-p4-check-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_review_validation_modules.py test/visual/test_human_review_modules.py test/services/test_review_business_validation.py test/integration/test_review_business_validation_api.py test/integration/test_new_ui_routes.py test/visual/test_ui_performance_assets.py test/tools/test_documentation_structure.py --basetemp $r4CheckBase --tb=short
```

Real production-app browser checks passed for the new multi-rule workflow,
nested findings/another operator's read-only view, forms without rules, an
initially missing item collection, and the existing phase-3 claim/save/complete
smoke. Two existing rich-form desktop/mobile/claim/draft/completion tests also
passed. These seven distinct scenarios were verified across focused runs.
The main multi-rule workflow passed again after the final mobile navigation fix.

```powershell
$env:R4_PHASE4_EVIDENCE_DIR = 'D:\python_code\pdfdoc_extraction\output\playwright\r4-phase4'
$r4VisualBase = Join-Path ([System.IO.Path]::GetTempPath()) ('r4-p4-visual-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_review_validation_visual.py test/visual/test_review_business_validation_visual.py --basetemp $r4VisualBase --tb=short
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_schema_review_visual.py::test_modular_review_editor_saves_reclaims_and_completes_synthetic_item test/visual/test_schema_review_visual.py::test_review_visual_schema_driven_fields_desktop_and_mobile --tb=short
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
npm run build:css
```

The acceptance checks exercise real rule evaluation plus controlled response
ordering/outages: two simultaneous failures, stale clearing, out-of-order replies,
retained focus/edits, row renumbering/empty lists/missing inputs, independent
passing checks, fresh blocking completion, draft restoration and edits made during
a delayed save, evaluator errors, disabled rules, keyboard navigation, mobile
wrapping, warning acceptance, and accepted/read-only reports. HTML-like messages
remain literal text. Tests retain existing CSP, CSRF/auth, and same-origin PDF
preview restrictions; an early wait/assertion was adapted to the installed
Playwright API and strict CSP instead of changing production security headers.

The agent-browser skill was used for a separate disposable-app walkthrough:
claim, edit subtotal, observe stale findings, revalidate unsaved values, and
inspect the current one-pass/one-warning report. The owned browser and server
were closed afterward. Automated tests stub only downstream resume; no live
provider calls, production documents, active database edits, or account recovery
were involved.

Desktop and mobile captures were visually inspected. Ignored evidence lives in
`output/playwright/r4-phase4/`: `two-rules-desktop.png`,
`warning-mobile-summary.png`, `warning-mobile-row.png`, and `manual-warning.png`.
The final mobile captures show the heading and wrapped row evidence below the
sticky header, with no page-level horizontal overflow or JavaScript page errors.

All 16 feature release graphs passed. The human-review graph is `r4-phase4` and
shared app CSS is `r4-business-validation-4`; CSS rebuilding passed. Generated
vendor CSS adds the sticky utility and uses cache value
`tailwind-3.4.17-daisyui-4.12.10-r4-phase4` in both app and login templates. Operator,
admin, schema, API, and deployment documentation and the roadmap were updated.
No dependency, database migration, backend API, or task standard changed in this
phase. Pyright was not run because it is absent from the repository environment.
The full suite was not repeated for this UI-scoped phase; phase 3's full-suite
record is above, and phase 5 includes the integrated full-suite/export acceptance.
The next unchecked phase is phase 5. R4 itself remains in progress.

Closing verification repeated the complete **128-test** focused command after
the final UI changes and passed. After the vendor CSS cache update, the route,
asset, and documentation subset passed **58 tests**. Final feature-release,
diff/whitespace, and plan/roadmap link/fragment checks passed. No untracked runtime
output is included as source, and nothing was staged or committed.

## Phase 5 implementation and verification record — 2026-10-30

The remaining agreed R4 scope is implemented, with no deferral:

- `date_order:v1` compares explicit ISO calendar dates with configurable equality.
- `required_if:v1` compares a typed scalar condition and requires 1–20 bound
  values when it matches. False/zero are present; absent conditions are
  inconclusive; nonmatching conditions are Not applicable, separate from Disabled.
- The immutable approved-validator registry declares strict frozen configuration,
  exact version, schema bindings and a pure evaluator. Each rule receives isolated
  copies. Exceptions, mutations and invalid/unbounded result contracts become
  blocking errors while independent rules continue. Existing implementations
  remain available alongside a new version. This is reviewed in-process Python,
  with bounded algorithms and data, not an untrusted-code sandbox or hard timeout.
- Production authoring supports all four templates, typed conditions, multiple
  required fields, publication and reopening. The review screen shows date and
  conditional outcomes and distinguishes a non-applicable condition.

Synthetic end-to-end tests run the actual pinned pipeline, gate, review service,
ResumeManager and JSON/CSV/PDF tasks. Only extraction, local orchestration wrappers
and destructive input cleanup are substituted. They cover multiple/no rules,
saved-draft recovery, completion bypass attempts, accepted values in real exports,
retained form and validator versions, acceptance-before-resume interruption,
simultaneous completions, evaluator errors, row/numeric limits and safe recovery.
The renamed PDF preserves the synthetic input bytes. No live provider is called.

The final focused command passed **309 tests**. An earlier focused run found the
new guide missing from the documentation manifest; that entry was added before
the clean focused run and full suite.

```powershell
$env:CONFIG_PATH = 'D:\python_code\pdfdoc_extraction\output\playwright\r4-phase4\bootstrap\config.yaml'
$env:APP_ENV = 'development'
$env:ENV = 'development'
$env:ENVIRONMENT = 'development'
$r4FocusedBase = Join-Path ([IO.Path]::GetTempPath()) ('r4-p5-final-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q test/services/test_business_validation.py test/services/test_business_validation_extensions.py test/services/test_business_validation_schema.py test/services/test_business_rule_capability.py test/services/test_review_business_validation.py test/integration/test_business_validation_acceptance.py test/integration/test_review_business_validation_api.py test/integration/test_versioned_schema_api.py test/integration/test_new_ui_routes.py test/visual/test_business_rules_editor_modules.py test/visual/test_review_validation_modules.py test/visual/test_human_review_modules.py test/visual/test_schema_editor_modules.py test/visual/test_ui_performance_assets.py test/tools/test_documentation_structure.py --basetemp $r4FocusedBase --tb=short
```

All **eight browser scenarios passed** across the new integrated acceptance and
existing authoring/review regressions. The new integration was repeated with an
explicit wait for the source PDF canvas and passed. It includes real completion,
resume and exports, four-rule initial findings, non-applicable conditions,
independent blocking completion, corrected drafts, accepted reports, typed/multiple
field authoring and retained published versions. Desktop/mobile captures were
visually inspected, including the readable source PDF and no page-level overflow.

```powershell
$env:R4_PHASE5_EVIDENCE_DIR = 'D:\python_code\pdfdoc_extraction\output\playwright\r4-phase5'
$r4VisualBase = Join-Path ([IO.Path]::GetTempPath()) ('r4-p5-v-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_business_validation_acceptance_visual.py test/visual/test_business_rules_editor_visual.py test/visual/test_review_validation_visual.py test/visual/test_review_business_validation_visual.py --basetemp $r4VisualBase --tb=short
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_business_validation_acceptance_visual.py::test_four_rule_templates_correct_save_accept_resume_and_export --basetemp $r4VisualBase --tb=short
```

The full suite collected **1,946 cases** and finished with **1,941 passed,
4 skipped and 1 setup error** in 3,109 seconds. Chromium exited during launch
(native exit code 3221225626), before
`test_pipeline_availability_preserves_unsaved_draft[False]` could run its body.
The application was not exercised by that failed setup. No source change was
made for the native browser crash. The entire affected module passed **all four
tests** in a fresh external temporary directory (205.11 seconds), including the
affected parameter case. All **1,942 non-skipped collected cases passed across
the full run and retry**. The full command itself is not recorded as a clean
single-run pass.

```powershell
$env:R4_PHASE5_EVIDENCE_DIR = 'D:\python_code\pdfdoc_extraction\output\playwright\r4-phase5\full-suite'
$r4FullBase = Join-Path ([IO.Path]::GetTempPath()) ('r4-p5-full-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q --basetemp $r4FullBase --tb=short --junitxml output/playwright/r4-phase5/full-suite.xml
$r4RetryBase = Join-Path ([IO.Path]::GetTempPath()) ('r4-p5-retry-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_pipeline_metadata_visual.py --basetemp $r4RetryBase --tb=short --junitxml output/playwright/r4-phase5/browser-retry.xml
```

The four skips are the opt-in credentialed live LlamaCloud Split smoke test and
three existing Windows permission cases. No live extraction/provider check or
active-deployment verification was performed. Pyright was not run because it is
absent from the repository environment. No dependency or database migration was
added; active configuration, users and runtime data were not changed.

The agent-browser skill was used for an independent disposable-app walkthrough:
claim, correct values against the readable synthetic invoice, observe stale
findings, revalidate all five checks, save/reopen the draft, complete, inspect
the accepted report, and verify all three real exports. A stale CLI session had
connection timeouts; a fresh named session worked. Native date fields were set
with input events after the CLI's date fill left them blank. The working browser
session and disposable server were closed. These were tool interactions, not
application changes.

Ignored evidence is in `output/playwright/r4-phase5/`, including
`integrated-failures-desktop.png`, `integrated-passing-mobile.png`,
`integrated-accepted-desktop.png`, `conditional-authoring-mobile.png`,
`manual-accepted-desktop.png`, `synthetic-invoice.png`, and full/retry JUnit files.
Screenshots and fixtures contain synthetic data only.

Portable form validation passed without findings. The stored form check with
import checks passed with zero errors and two legacy-root-YAML migration warnings;
its warning-only exit code **2** was verified. The disposable browser fixture's
empty legacy tasks were first rejected by deployment preflight; a separate CLI
config containing the real synthetic extraction task was used for the stored
check. Neither config is application source or an active deployment.

```powershell
.\.venv\Scripts\python.exe -m tools.config_check validate-file --file output/playwright/r4-phase5/invoice-form.json --kind review-schema
.\.venv\Scripts\python.exe -m tools.config_check validate --config C:/Users/bpson/AppData/Local/Temp/r4-p5-manual-ffbycvf4/cli-config.yaml --review-schema invoice-acceptance --version 1 --import-checks
npm run build:css
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
git -c core.whitespace=cr-at-eol diff --check
```

All 16 feature release graphs and the CSS build passed. Both schema-editor and
human-review graphs use `r4-phase5`, shared CSS uses `r4-business-validation-5`,
and app/login vendor CSS uses `tailwind-3.4.17-daisyui-4.12.10-r4-phase5`.
Admin/operator/schema/API/deployment documentation, developer navigation and
manifest, plugin development guidance, task standards and roadmap were updated.

Closing documentation/asset tests passed **23 tests** after retaining the required
source-review metadata wording. The final implementation-plan/roadmap link and
fragment checks, tracked diff check, and untracked source whitespace check passed.
Nothing was staged or committed. All five phases and R4 are complete.

## Post-implementation type and regression audit — 2026-10-31

Prerequisites: phases 1–5 complete. Preserve the existing uncommitted work and
use the repository Python 3.13 environment throughout the audit.

The initial Pyright 1.1.414 scan reported 116 errors across 323 files. An
isolated tracked-HEAD snapshot, using the same virtual environment and basic
configuration, reported 67 existing test errors across 304 files. Comparing
file/rule/message diagnostics identified 49 introduced errors: two in production
and 47 in tests. All 116 were addressed. The final scan covers 324 files and
reports **zero errors, zero warnings, zero information diagnostics**. The
configuration's includes, exclusions and basic checking mode were not weakened.

Production code explicitly handles an unavailable row-binding scope and a
non-object pinned review form. The latter returns the existing structured
`review_schema_unavailable` failure without persisting review changes. Positive
tests now check optional results before indexing them and verify mock boundaries
at runtime. One pre-existing file-wide optional-subscript suppression was removed.
The readonly-registry negative test deliberately crosses that one type boundary
locally; ordinary evaluator and service calls remain typed.

The code review confirmed conditional-enum defects: the binder ignored the
supported `enum` alias, rejected label-only choices, and treated integer/float
equivalent choices differently from the evaluator. The editor also failed to flag
unoffered enum constants before saving. The binder and editor now use both aliases,
the existing `value`/`label` fallback, and typed scalar equality. Booleans remain
distinct from numbers. Twenty parameterized service cases, two API publication
cases, two module cases, and desktop/mobile browser cases cover these paths.
The new editor tests failed against the previous behavior and passed after the
fix. The first focused post-fix run passed **280 tests**.

Pyright is a development-only pin. The packaged config-check runtime dependencies
and production requirements were not changed. Historical phase records above
correctly record that Pyright was not run in those earlier phases.

- [x] Pin and run Pyright using the existing basic-mode project configuration;
  compare any existing diagnostics against HEAD before attributing them to R4.
- [x] Correct introduced type errors without weakening diagnostics or masking
  them with broad ignores; review runtime and browser changes for new bugs.
- [x] Add focused regression tests for confirmed bugs and run affected tests,
  integration/visual checks where appropriate, and type checking after fixes.
- [x] Update relevant development/operator/contract documentation and record
  exact checks, results, and remaining pre-existing limitations.

```powershell
$env:CONFIG_PATH = 'D:\python_code\pdfdoc_extraction\output\playwright\r4-phase4\bootstrap\config.yaml'
$env:APP_ENV = 'development'
$env:ENV = 'development'
$env:ENVIRONMENT = 'development'
.\.venv\Scripts\python.exe -m pip install pyright==1.1.414
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe --outputjson
$env:RUN_LLAMACLOUD_SPLIT_SMOKE = '0'
$r4BackendBase = Join-Path ([IO.Path]::GetTempPath()) ('r4-audit-backend-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q --ignore=test/visual --basetemp $r4BackendBase --tb=short --junitxml output/r4-type-audit/backend-suite.xml
$env:R4_AUDIT_EVIDENCE_DIR = 'D:\python_code\pdfdoc_extraction\output\r4-type-audit\visual'
$env:R4_PHASE5_EVIDENCE_DIR = $env:R4_AUDIT_EVIDENCE_DIR
$r4VisualBase = Join-Path ([IO.Path]::GetTempPath()) ('r4-audit-visual-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_business_rules_editor_modules.py test/visual/test_schema_editor_modules.py test/visual/test_human_review_modules.py test/visual/test_review_validation_modules.py test/visual/test_ui_performance_assets.py test/visual/test_business_rules_editor_visual.py test/visual/test_business_validation_acceptance_visual.py test/visual/test_review_validation_visual.py test/visual/test_review_business_validation_visual.py --basetemp $r4VisualBase --tb=short --junitxml output/r4-type-audit/visual-suite.xml
$r4DocsBase = Join-Path ([IO.Path]::GetTempPath()) ('r4-audit-docs-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q test/tools/test_documentation_structure.py --basetemp $r4DocsBase --tb=short
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
```

The complete nonvisual suite passed **1,811 tests with four expected skips** in
226.53 seconds. All **55 selected module/asset/browser tests passed** in 116.08
seconds, including ten real-browser cases. Two exercise the enum aliases through
invalid-value feedback, blocked publication, correction, publish/reopen, and
desktop/mobile layouts. The others cover existing multi-rule authoring, real
resume and JSON/CSV/renamed-PDF outputs, saved drafts, stale asynchronous replies,
claim/read-only behavior, blocking/warning completion and no-rules compatibility.
The closing documentation check passed **18 tests** after the documentation edits.

These commands cover the entire backend and affected UI; unrelated browser
modules were not rerun in this audit. The previous phase-5 full-suite record is
preserved above and is not claimed as a new all-browser full run. The four skips
remain the opt-in live LlamaCloud Split check and three Windows permission cases.
No live provider calls, active configuration/account changes or runtime-data
migrations were performed.

Code review covered strict parsing/bindings, plugin isolation/failure handling,
pinned version compatibility, snapshot/claim/revision checks, atomic acceptance
and resume, report/audit handling, and stale-response/editor behavior. Regression
coverage was added for the confirmed enum issues and malformed pinned schemas.
No additional confirmed R4 defect was found in the reviewed paths.

Development setup/testing guidance now includes the pinned checker and typed
test boundaries. Admin/schema/API/plugin/deployment guidance describes enum
choices, safe invalid-form failures and upgrade preflight. The schema-editor
graph is `r4-audit1`; human-review remains `r4-phase5`. All 16 release graphs pass.
No Tailwind utility, CSS input or frontend dependency changed, so a CSS rebuild
was not required for this audit. Earlier phase-5 CSS build evidence remains above.

Ignored audit evidence is under `output/r4-type-audit/`: initial/current/HEAD and
final Pyright JSON, backend/visual JUnit files, and synthetic desktop/mobile
captures under `visual/`. The captured enum authoring and accepted-review screens
were visually inspected. The audit is complete; no changes were staged or committed.

## Live Superstore visual acceptance — 2026-11-08

Prerequisites: all five phases and the type audit complete. This walkthrough used
the real local application, its existing administrator account and local model;
it did not substitute a synthetic extractor or edit database workflow state.
The user signed in. A local SQLite backup preceded the normal startup migration
from schema 8 to 9; credentials and runtime YAML were unchanged.

- [x] Clone the existing LiteParse invoice pipeline, add a printed-subtotal field,
  and publish matching numeric review fields and two rules through the UI.
- [x] Process three real one-page Superstore PDFs using local LiteParse/Ollama;
  visually compare original extracted values with their source pages.
- [x] Verify initial evaluation, stale findings, independent row/subtotal failures,
  explicit revalidation, saving/reopening drafts, empty and multiple rows,
  release/reclaim, and server rejection of stale blocking completion.
- [x] Restore printed values before approval; verify passing acceptance and
  warning-only acceptance retaining a real one-cent printed discrepancy.
- [x] Inspect desktop/narrow-window layouts, stored accepted reports, completed
  batch state, document navigation and all nine registered exports.
- [x] Compare JSON/CSV values against independent source references and verify
  source PDF copies by SHA-256; record findings and verification limits.

Published configuration: **Superstore Invoice Business Validation v1**, key
`superstore-business-validation`, cloned from **LiteParse Invoice Review JSON
v1**; exact review form **superstore-business-review v1**. Line arithmetic is a
review-required warning with zero tolerance, two decimal places and half-up
rounding. This intentionally exposes a verified source rounding discrepancy.
The subtotal rule is blocking with inclusive 0.01 tolerance and sums printed
line amounts against subtotal before discount/shipping/tax. The two rules do
not validate the final discount/shipping calculation. Every document requires
full review before JSON, CSV and renamed source-PDF output.

All three documents reached **Completed / 100%**, with completion requests
returning 200. Accepted reports retain two passes for the exact-arithmetic
samples and one pass plus one accepted warning for the discrepant source. A
deliberately stale blocking completion returned 422 without acceptance/exports.
An empty added row produced cannot-evaluate findings and form errors; filled
multiple-row errors remained independent. Temporary values/rows were removed
before approval. Read-only completed reports and released reviews were checked.

Data-integrity checks passed for all nine exports, including identical source
PDF hashes. Filename checking found a separate defect: JSON resolves `{id}` as
`unknown` while CSV/PDF correctly use the document UUID. It repeats on all three
documents and is visible in the Extraction file lists. The read-only comparison
script deliberately exits 1 because naming failed; it is not a wholly passing
check. A narrow headed Windows Chrome review page also has four CSS pixels of
horizontal overflow (clientWidth 375 / scrollWidth 379 at innerWidth 390).
The form editor measured 375/375. Business checks and completion remained usable.

The clone was made **inactive after testing**, pending the JSON naming fix;
its published version and active review form are retained. Original pipelines,
form versions and watch-folder assignments were preserved. The application
remains running. No application-source change or bug fix was made during this
walkthrough; the findings below are outstanding follow-up work, not failed
arithmetic-rule acceptance checks.

- [x] Fix JSON `{id}` filename resolution using the authoritative document ID;
  add a real review-resume regression and verify repeated invoice references
  produce distinct registered export paths without overwriting earlier results.
- [x] Remove the narrow-window review page's four-pixel horizontal overflow;
  check against clientWidth as well as innerWidth and retain readable findings
  with the table's independent horizontal scrolling.

Both follow-ups were repaired on 2026-11-09 and retested with focused regressions
and a live operator Superstore run. JSON now reserves `{id}` for workflow identity
without changing business values; the mobile header fits the actual client width.
See the [verification follow-up](tasks-r4-audit-follow-up.md#requested-verification-and-live-follow-up--2026-11-09)
for current test results and the final full-suite status. The 2026-11-08 findings
and evidence below remain a historical record of the original walkthrough.

Local evidence, exact runtime identifiers and reproduction details are in
[the acceptance report](../output/superstore-business-validation-2026-11-08/report.md).
The report includes screenshots of failed/passing/accepted checks, form authoring,
registered filenames and completed batch state. References, outputs, logs and
the backup remain local. Browser recording failed under memory pressure;
no successful video is claimed. Native viewport commands sometimes returned
EOF despite applying the resize, so actual DOM dimensions and images were checked.
The machine briefly reported 3 MB available physical memory during the first
extraction; unused owned browser sessions were closed and the run completed.

```powershell
.\.venv\Scripts\python.exe output\superstore-business-validation-2026-11-08\verify_outputs.py
.\.venv\Scripts\python.exe -m tools.config_check validate --config config.yaml --import-checks
.\.venv\Scripts\python.exe -m pytest -q test\tools\test_documentation_structure.py --basetemp $ssDocBase --tb=short
```

The output check passed data integrity and failed the three JSON filename
checks as described above. Post-migration config validation reported zero errors
and one existing filesystem-schema migration/import warning. Documentation
structure checks passed all 18 tests. The backend/browser regression suite,
Pyright and CSS build were not repeated for this live configuration/documentation
walkthrough; no application source, utility classes or dependencies changed.
The earlier audit's results remain separate. This acceptance covers three
one-page native-text invoices and the two arithmetic templates; it is not a
general extraction benchmark or a new scan/cloud/multi-user/date/conditional test.
