# R4 business-validation audit follow-up

| Item | Value |
| --- | --- |
| Status | Audit phases 2–5 planned; verification repairs complete and verified |
| Updated | 2026-11-09 |
| Scope | Retained findings from the eleven-item business-validation audit |
| Prerequisites | R4 implemented; audit checked against the current working tree |

## Intended outcome

Make evaluator failures diagnosable without exposing business data, make nested
transaction guarantees explicit, extend container-edit regressions, and measure
the evaluator's isolation cost before choosing an optimization. Preserve blocking
failure behavior, independent rules, exact published versions, and unchanged
caller data. Implement each phase with its documentation and verification.

## Audit disposition

| Finding | Decision |
| --- | --- |
| 1: broad evaluator exception catch | Retain the boundary; add safe diagnostics and regression tests. |
| 2: publication guard outside fallback | Retain the precondition; test supported callers reject missing versions through structured service errors. Do not fabricate a report with missing identity. |
| 3: discriminator tags in paths | Not reproduced: plugin models are validated directly. Add exact-path regressions before removing the obsolete two-tag filter. |
| 4: incomplete subtotal | Retain documented all-or-nothing sum behavior and its existing tests. |
| 5: copies per rule | Benchmark first; optimize only with evidence and preserved isolation. |
| 6: nested immediate transaction | Document top-level reservation versus nested rollback scope; test both. |
| 7: Pyright guidance | Correct AGENTS.md to match the intentional development pin. |
| 8: multiple format versions | Explain their independent contracts; preserve serialized names. |
| 9: supported-version set | No inconsistency found; retain existing version acceptance checks. |
| 10: container defaults | Existing browser coverage already asserts no implicit correction for a missing list. Extend the matrix rather than treating it as an established bug. |
| 11: explicit-null correction | Already uses backend has_correction plus the raw-string fallback. Retain existing service/frontend regressions. |

## Phase 1: Reconcile current documentation

Prerequisite: source review complete. This is documentation-only work.

- [x] Correct AGENTS.md's stale Pyright statement without changing dependencies.
- [x] Document per-rule copies, intentional generic evaluator errors, empty error
  paths, and the distinction between current behavior and planned diagnostics.
- [x] Document top-level immediate reservation and nested savepoint semantics.
- [x] Explain outer schema, nested configuration, and report format versions.
- [x] Run documentation structure/link checks and record the result below.

## Phase 2: Safe evaluator diagnostics and exact error paths

Prerequisite: phase 1 complete. This is the next implementation phase.

- [ ] Add module-level logging for unexpected evaluator failures while retaining
  the broad catch, generic validator_error report, blocking policy, and execution
  of subsequent independent rules. Log only approved validator/rule identifiers,
  exception type, and safe source locations if needed. Do not use str/repr of the
  exception, exc_info, traceback locals, document identifiers, values, or config.
- [ ] Add KeyError, AttributeError, and RuntimeError regressions using synthetic
  secret markers. Assert an actionable safe diagnostic, no marker in log record
  arguments/exception data or rendered logs/reports, no mutation, and continued
  evaluation of an independent valid rule. Retain arithmetic/input behavior.
- [ ] Add exact invalid-binding paths for all four validator families, then
  remove the obsolete tag filter only if the tests prove it is unnecessary.
- [ ] Verify public review/gate entry points reject unversioned rule forms with
  their structured service errors; retain or extend existing coverage as needed.
- [ ] Update the plugin developer guide to describe the implemented log fields
  and how to investigate generic errors; remove its planned-behavior wording.
- [ ] Run focused evaluator, schema, capability, review-service, and API tests.

## Phase 3: Transaction contract and regression coverage

Prerequisite: phase 1 complete; phase 2 need not change transaction behavior.

- [ ] Expand atomic_transaction's docstring to match the backend guide: immediate
  applies to a new outer transaction; nested scopes inherit the caller's lock
  state. Keep existing nested calls compatible rather than adding an assertion.
- [ ] Use temporary databases and two connections to show that top-level
  immediate reservation excludes another writer before the first write.
- [ ] Test nested savepoint success, failure rollback, preservation of earlier
  outer writes, and caller-owned final commit/rollback. Assert nesting emits a
  savepoint rather than a new BEGIN IMMEDIATE.
- [ ] Review current immediate call sites for prior transaction activity. If a
  supported caller requires a reservation it does not hold, add a concrete
  reproduction and repair the service boundary before marking this phase done.
- [ ] Run connection, review acceptance/rollback, and gate integration tests;
  update backend guidance if the call-site review changes a caller requirement.

## Phase 4: Container rendering and correction coverage

Prerequisite: phase 1 complete. Extend the existing missing-list browser test.

- [ ] Cover missing, explicit-null, and empty objects plus scalar/object arrays,
  including a nested object and both rule-bearing and no-rules forms. Exercise
  actual rendering/rerendering and claim transitions; untouched values must not
  produce a correction during revalidation, draft save, or completion where valid.
- [ ] Test deliberate object child edits, array add/remove, empty-array results,
  and draft restoration: intended corrections must be sent and persisted.
- [ ] Retain explicit-null correction coverage with has_correction and exercise
  the raw corrected_value_json fallback. Avoid changing the response contract.
- [ ] Update developer frontend guidance with the render-without-mutation rule;
  update operator instructions only if visible behavior changes.
- [ ] Run review module, browser, and relevant API tests with synthetic fixtures.
  Rebuild committed CSS only if templates, utility classes, or packages change.

## Phase 5: Measure isolation cost and decide optimization

Prerequisite: correctness regressions above pass before any optimization.

- [ ] Add a repeatable synthetic benchmark for 1, 10, and 50 enabled rules at
  small sizes and 1,000 rows, including a payload with large unrelated nested
  fields. Record document size, interpreter/machine, warmup/repeats, median/tail
  duration, and peak memory. Measure copying separately from total evaluation.
- [ ] Measure a synthetic review-save path to establish whether copying is a
  material part of operator latency. Do not use the active config/database or
  call a provider. Keep timing thresholds out of ordinary correctness tests.
- [ ] Record the evidence and decision in developer performance guidance. If
  copying is not material, close the investigation with the measured limits.
- [ ] If warranted, choose and document an approach before implementing it.
  Preserve nested mutation detection, untouched original values, independent
  rule snapshots, list/mapping compatibility, Decimal behavior, limits, and
  retained validator versions. A shared mutable copy or hash alone is insufficient.
- [ ] For any optimization, add regressions for nested dict/list mutation and
  mutation followed by an exception, compare reports with the baseline, rerun
  the benchmark, and update the plugin isolation contract in the same change.

## Relevant Files

- [AGENTS.md](../AGENTS.md): corrected Pyright toolchain instructions.
- [R4 task record](tasks-r4-business-validation.md): link to this follow-up.
- [Evaluator](../modules/services/business_validation.py): planned safe diagnostics.
- [Schema binding](../modules/services/business_validation_schema.py): exact error paths.
- [Report builder](../modules/services/review_business_validation.py): retained prerequisites and fallback.
- [Review service](../modules/services/review_service.py): public version guards and acceptance transaction callers.
- [Connection helpers](../modules/db/connection.py): transaction docstring and scope contract.
- [Evaluator tests](../test/services/test_business_validation_extensions.py): plugin fault and isolation tests.
- [Schema tests](../test/services/test_business_validation_schema.py): exact binding-error paths.
- [Capability tests](../test/services/test_business_rule_capability.py): version enforcement regressions.
- [Review tests](../test/services/test_review_business_validation.py): pinned rules and acceptance regressions.
- [Connection tests](../test/db/test_managed_connection.py): transaction reservation/rollback tests.
- [Review browser tests](../test/visual/test_review_validation_visual.py): existing missing-list case and planned container matrix.
- [Review module tests](../test/visual/test_human_review_modules.py): explicit-null and correction semantics.
- [Review API tests](../test/integration/test_review_business_validation_api.py): request/persistence contracts.
- [Plugin guide](../docs/developer/business-validation-plugins.md): diagnostics and isolation requirements.
- [Backend guide](../docs/developer/backend-development.md): nested transaction semantics.
- [Schema reference](../docs/reference/review-schema-format.md): independent format versions.
- [Frontend guide](../docs/developer/frontend-development.md): planned render/correction invariant.
- [Performance guide](../docs/developer/performance.md): planned benchmark method, evidence, and decision.
- [Testing guide](../docs/developer/testing-and-verification.md): verification command reference.

Add benchmark tools and new tests here when their implementation paths are chosen.

## Completion and verification

### Additional verification repair

The requested full-suite run on 2026-11-09 stopped during collection: importing
`web.server` used the active deployment and its database failed read-only startup
verification. Fix the test bootstrap before continuing the full checks.

- [x] Give collection a synthetic temporary configuration and initialized database
  through `test/conftest.py`, preserving production startup checks.
- [x] Verify regressions for missing/invalid inherited CONFIG_PATH and rerun the
  affected integration tests, full pytest, and Pyright.
- [x] Perform the requested Superstore invoice/operator visual walkthrough with
  a suitable existing pipeline; record findings and fixes without credentials.
- [x] Fix the full-suite browser acceptance navigation race by waiting for the
  successful completion redirect before reopening the accepted review; verify
  the focused browser test and final full suite.
- [x] Fix the live-reproduced JSON filename placeholder defect. Cover workflow
  identity precedence, unchanged extracted IDs, repeated invoice references,
  registered artifact paths, and actual review/resume exports.
- [x] Fix the live-reproduced four-pixel mobile review overflow. Reproduce reserved
  scrollbar space in browser regressions and compare scrollWidth with clientWidth.

Additional relevant files:

- [Test bootstrap](../test/conftest.py): isolated import-time app startup.
- [Collection regressions](../test/core/test_pytest_collection_isolation.py): subprocess collection with missing/invalid external configuration.
- [Browser acceptance](../test/visual/test_business_validation_acceptance_visual.py): wait for the completion redirect before reopening the accepted report.
- [JSON storage](../standard_step/storage/store_metadata_as_json.py): reserve the filename ID for workflow identity without changing exported data.
- [JSON tests](../test/storage/test_storage_json.py): document/legacy identity precedence and unchanged business IDs.
- [Workflow helper](../test/helpers_business_validation_workflow.py): configurable filename template for real resume/export coverage.
- [Acceptance regressions](../test/integration/test_business_validation_acceptance.py): repeated invoice references produce distinct registered outputs.
- [Review browser regressions](../test/visual/test_review_validation_visual.py): active/completed headers with native scrollbar space.
- [Application CSS](../web/static/css/app.css): constrain the mobile header and badge without clipping the table scroll area.
- [Application shell](../web/templates/app_base.html): invalidate cached application CSS after the layout fix.
- [Storage reference](../docs/reference/tasks/storage-and-archiving.md): reserved JSON filename identity contract.
- [Task standards](standard_task_creation_guidelines.md): separate workflow identity from extracted business IDs.
- [Frontend guide](../docs/developer/frontend-development.md): completion-navigation waits and native scrollbar layout checks.

### Final checks

Mark each checkbox only after its implementation, associated documentation, and
required checks pass. Preserve existing uncommitted work. Record exact commands,
outcomes, and omitted checks. Use the repository interpreter for all Python work.

Run focused tests for each phase before broader checks. Before closing the
combined runtime follow-up, run the full pytest suite and the pinned Pyright
command from the testing guide. Browser changes require Chromium verification;
install it through the repository environment if missing. Live provider checks
are outside this work. Documentation checks are:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/tools/test_documentation_structure.py
```

Planning baseline: the preceding audit review ran seven focused service/module
test files: 244 passed in 10.59 seconds. It did not run full pytest, Pyright,
browser rendering tests, or performance benchmarks. That result does not verify
the runtime work proposed here.

Documentation verification on 2026-11-09:

- `.\.venv\Scripts\python.exe -m pytest -q test/tools/test_documentation_structure.py`:
  18 passed in 0.81 seconds.
- `git diff --check`: passed; Git emitted line-ending normalization warnings.
- Reviewed the plan and current-contract documentation for unsupported behavior
  claims and sensitive content. No runtime code, dependency, or schema changes.
- Full pytest, Pyright, browser rendering, and benchmarks were not run for this
  documentation-only change; they remain required at the applicable phases.

### Requested verification and live follow-up — 2026-11-09

The first complete run after collection isolation reported 1 failed, 1,969 passed,
and four expected skips in 426.98 seconds. The only test failure was a browser
navigation race: the accepted-review reload started before completion's queue
redirect finished. Waiting for the redirect fixed both focused acceptance cases
(2 passed in 17.61 seconds).

The live operator walkthrough used the existing LiteParse Invoice Review JSON
v1 pipeline with the local Ollama model and one Superstore invoice submitted
twice, before/after the fixes. Both documents completed. It reproduced the JSON
`{id}` defect and narrow-window header overflow; both were repaired and retested.
The JSON name now matches the authoritative document UUID, accepted values match
the exported JSON, and uploaded source hashes match the original. The initial
export remains intact. The mobile page measured clientWidth/scrollWidth 375/375
at innerWidth 390, including the completed review. Existing pipeline/form versions,
accounts, and watch-folder bindings were unchanged.

Focused storage/integration/browser/documentation verification passed 53 tests
in 64.40 seconds; the extended active/completed native-scrollbar cases subsequently
passed both cases in 14.44 seconds. Pyright reported no errors or warnings after
the source/test changes. CSS rebuilt successfully, and all 16 frontend release
graphs validated. Final full pytest passed 1,975 tests with four expected skips
in 447.09 seconds; final Pyright reported 0 errors, 0 warnings, 0 informations.
The skips are the opt-in live LlamaCloud Split smoke and three Windows permission
cases. The separate credentialed LlamaCloud connection module was excluded.
All collected browser cases passed in the final run.
The closing documentation check passed all 18 tests in 0.87 seconds, and the
final diff whitespace check passed.

Exact commands, screenshots, read-only output verification, and test logs are
recorded in [the local verification report](../output/verification-2026-11-09/report.md).
No cloud extraction or credentialed live-provider test was run. The selected live
pipeline has no R4 business-rule panel; automated acceptance covers the business
templates. These repairs do not implement the planned safe evaluator diagnostics,
transaction tests, expanded container matrix, or performance investigation.
