# Proposal: business-rule authoring across document types

| Item | Value |
| --- | --- |
| Status | Implemented and verified 2026-11-11 |
| Updated | 2026-11-11 |
| Scope | Neutral rule authoring, a shared catalog, and a numeric comparison pattern |
| Decision | User approved implementation; scope and compatibility contract delivered |

## Problem and intended outcome

The evaluator already binds rules to arbitrary compatible fields. It does not
select behavior by document type. However, the editor and review findings use
invoice terms, and adding a validator requires separate hardcoded frontend
definitions. The current four patterns also omit common numeric comparisons.

An administrator should select a reusable rule pattern, bind it to fields from
any suitable review form, and choose its review policy. Operators should see the
same neutral rule names and the form's actual field labels. Shipping, insurance,
and invoice forms should use the same configuration workflow.

The proposed first delivery includes the four existing patterns plus numeric
comparison. It remains a catalog of approved patterns; it does not promise every
possible business rule or a free-form programming surface.

## Proposed administrator experience

Replace the four fixed add buttons with **Add rule**, opening a searchable list:

| Pattern shown to the administrator | Configuration |
| --- | --- |
| Multiply two row fields | Repeating group, first value field, second value field, result field |
| Sum rows against a field | Repeating group, value to sum, target field |
| Compare numbers — new | Document or repeating-row scope, left field, operator, right field or constant |
| Date order | Earlier date, later date, allow the same day |
| Require fields when a condition matches | Condition field, typed equals value, required fields |

After choosing a pattern, the administrator:

1. Selects the scope/group where needed. A new rule must not silently bind to the
   first array in a form containing several unrelated repeating groups.
2. Selects compatible fields, using their form labels and paths. Incompatible
   fields cannot be selected; unavailable patterns explain missing prerequisites.
3. Configures applicable options such as allowed difference, decimal places,
   rounding, or comparison operator. Help text discusses the selected operation
   and appropriate units rather than invoice subtotal or currency assumptions.
4. Chooses Enabled, Severity, Require review on warning, and an optional message.
   The rule ID remains available as an advanced setting with a unique default.
5. Reads a plain-language summary, then saves, validates, and publishes the form.
   The administrator selects the published form version in Review Gate and
   publishes the intended pipeline version through the existing workflow.

Example comparison card for a delivery note:

```text
Pattern:          Compare numbers
Apply to:         Each row in Delivery lines
Left field:       Delivered quantity
Operator:         Less than or equal to (≤)
Compare with:     Field
Right field:      Ordered quantity [same row]
Severity:         Blocking

Summary: For each delivery line, delivered quantity must be ≤ ordered quantity.
```

Examples for the existing calculation patterns:

- Invoice: quantity × unit price must match the recorded line amount.
- Packing list: package count × weight per package must match recorded row weight.
- Shipment: sum of row weights must match the declared total weight.
- Policy: effective date must be on or before expiry date.

Administrators choose bindings explicitly; the system does not infer business
meaning or convert units from a field name or document-type label.

## One catalog drives the editor

Extend each approved validator descriptor with validated, serializable editor
metadata: display name, description, category, ordered parameters, binding scope
and allowed types, defaults, limits, choices, and supported controls.

The backend configuration model remains authoritative. Registry validation must
detect metadata referring to nonexistent parameters or incompatible bindings.
The editor consumes a deliberately small control vocabulary: field selector,
repeating-group selector, typed constant, choice, boolean, numeric/text option,
and a field-or-constant operand group. Conditional control visibility uses
bounded declarative settings rather than executable expressions.

Proposed read-only endpoint: `GET /api/admin/business-validators`, protected by
the existing administrator access checks. Its response uses `catalog_version`
and exact validator IDs. A service builds the response from the reviewed registry;
the route only authenticates and constructs the response.

The frontend renders those controls using reusable widgets. The duplicated
per-validator title, binding, initialization, and choice lists are removed from
the editor. Adding a pattern expressible through those widgets requires its
reviewed configuration, evaluator, and metadata; a genuinely new widget still
requires frontend implementation and tests.

Catalog metadata is presentation/configuration guidance, never the executable
authority. The server validates saved and imported definitions independently.
No new runtime registration, code upload, arbitrary formula, or dynamic-import
interface is introduced.

If the catalog cannot load, show Retry and disable new rule creation/type changes.
Existing rule data remains intact. Rendering or refreshing metadata must not
rewrite a draft, fill omitted defaults, or silently remove unavailable rules.
Unresolved bindings or unsupported validators continue to block publication.

## Operator findings use the same names

Remove the separate invoice-oriented title mapping from the review findings UI.
Provide a small server-derived display-label map alongside review-detail and
revalidation responses, separate from the persisted acceptance report. Operator
pages consume that map without calling an administrator-only endpoint.

An unavailable label falls back to the rule ID/validator ID, preserving findings
and completion enforcement. Display metadata cannot turn an error into a pass.
Existing field and row paths continue to locate affected inputs. A later label
change does not rewrite historical accepted reports or alter evaluation semantics.

## Numeric comparison contract

Add an approved, separately versioned validator, provisionally
`compare_number:v1`, with these first-release semantics:

- Operators: equal, not equal, less than, less than or equal, greater than,
  greater than or equal.
- Left operand: a numeric field. Right operand: a numeric field or bounded
  decimal constant. No implicit text/boolean comparisons or unit conversion.
- Document scope compares document fields. Repeating scope evaluates each row
  independently; a field operand explicitly selects the current row or document
  scope. Multiple unrelated collections cannot be joined in this release.
- Extend shared collection preflight to respect the new rule's explicit
  document/row mode; today a descriptor declaring a collection always triggers
  collection validation. Preserve that behavior for the existing row validators.
- Field bindings are validated against the selected scope and numeric types.
  The existing binding metadata must be extended for nested operand descriptors
  and conditional field/constant choices; flat attribute bindings alone are
  insufficient. Keep this logic with approved configuration/binding validation.
- Use the existing bounded Decimal conversion; reject booleans and nonfinite
  values. Compare ordering operators exactly, without implicit rounding.
- Optional allowed difference defaults to zero and applies only to equal/not
  equal: equality means absolute difference ≤ tolerance; inequality means it is
  greater. Hide this option for ordering operators and reject irrelevant saved
  parameters. Existing arithmetic rounding/tolerance behavior stays unchanged.
- Missing/invalid operands yield Cannot evaluate, never Passed. Empty/malformed
  collections and resource limits retain the established inconclusive/error
  policies. Return bounded evidence and absolute field paths, including the row
  index where applicable, through the existing check/report contract.
- Blocking inconclusive/failed results and every evaluator error prevent
  completion. Warning routing and acceptance retain their existing policy.

## Compatibility and persistence

Keep `line_amount:v1`, `sum_equals:v1`, `date_order:v1`, and `required_if:v1` and
their serialized parameter names unchanged. For example, the UI can label
`unit_price` as Second value field while preserving the saved key and algorithm.
Do not auto-rename user-authored rule IDs, field keys, or messages.

Changing presentation must leave existing draft content, published hashes,
report contracts, pinned versions, and accepted values unchanged. No database
migration or bulk republishing is expected: definitions already live in versioned
JSON. The new comparison is a new validator ID, not a reinterpretation of v1
rules. Older releases must continue to reject unsupported published validators;
test that compatibility behavior rather than assuming it.

The catalog's schema version is separate from form and validator versions.
Metadata is not copied into the canonical published form just to render controls.

## Delivery sequence and acceptance criteria

The user approved implementation on 2026-11-11. The catalog, comparison,
documentation, and combined regression checks are complete. The implementation preserves the existing registry,
strict configurations, shared evaluator, and versioned publication boundaries.

- [x] Define and validate catalog metadata and the read-only API; add descriptor
  and access-control tests before replacing the editor's duplicated definitions.
- [x] Define the comparison operand contract before wiring the shared editor
  widgets; this supplies the scope/constant types used by the next two items.
- [x] Render all four existing patterns from metadata with neutral labels and
  operation-specific help. Verify loading existing drafts causes no mutation.
- [x] Add the numeric comparison configuration, evaluator, nested binding
  validation, metadata, reusable operand controls, and parameterized tests.
- [x] Use shared neutral titles in operator findings without changing accepted
  report payloads or granting operator access to administrator endpoints.
- [x] Test malformed/imported configurations, catalog failures/retry, unavailable
  validators, renamed fields, explicit null/missing values, and preserved versions.
- [x] Run shipping/packing-list, insurance, and invoice acceptance scenarios
  through authoring, publication, pipeline binding, gate, correction/revalidation,
  completion, and persisted outputs. Verify blocking bypass attempts fail.
- [x] Prove a small test-only plugin using supported widgets appears from its
  descriptor without adding another validator-ID branch to the generic editor.
- [x] Verify desktop/mobile layout, keyboard operation, escaped metadata, clear
  field scope, and existing warning/blocking/stale-response behavior.
- [x] Verify forms with no business rules still publish, claim, validate fields,
  save/reload drafts, complete, resume, and export without needing the catalog.
- [x] Update maintained docs and examples alongside implementation; run focused
  tests, CSS build if required, frontend release checks, Pyright, and full pytest
  before declaring the combined change complete. Record opt-in checks not run.

Success means the same editor configures those patterns for different document
types, all existing invoice versions behave identically, and numeric comparison
can be added and enforced entirely through the normal form configuration flow.

## Documentation and expected files

### Relevant Files

- `modules/services/business_validation_metadata.py`: validated reusable editor controls and safe descriptor paths.
- `modules/services/business_validation_registry.py`: neutral metadata for existing patterns and approved numeric comparisons.
- `modules/services/business_validation_catalog_service.py`: JSON catalog and nonpersistent review labels.
- `modules/services/business_validation.py`: exact Decimal comparisons, operands, scopes, and conditional collection preflight.
- `modules/services/business_validation_schema.py`: nested operand and dynamic scope binding validation.
- `modules/api_router.py`: authenticated administrator catalog endpoint.
- `modules/services/review_service.py`: operator display labels outside saved reports.
- `web/static/js/schema-editor/business-rules.js`: catalog-driven models, reusable widgets, picker, summaries, and findings.
- `web/static/js/schema-editor/controller.js` and `api.js`: catalog loading/retry and picker interaction.
- `web/templates/schema_editor.html`: searchable Add rule dialog and catalog status.
- `web/static/js/human-review/validation.js` and `validation-view.js`: shared titles with stable fallback.
- `web/static/css/app.css`, `vendor.css`, feature entry imports, and affected app/login templates: responsive controls and versioned release assets.
- `test/services/test_business_validation_catalog.py` and `test_compare_number_validation.py`: descriptor safety and comparison behavior.
- `test/integration/test_versioned_schema_api.py`: catalog permissions and existing publication regressions.
- `test/integration/test_new_ui_routes.py` and `test/visual/test_ui_performance_assets.py`: current versioned frontend entry assertions.
- `test/helpers_visual.py` and affected editor/review module/browser tests: visible picker actions and neutral findings.
- `test/helpers_generic_business_validation.py`: synthetic shipping, insurance, and invoice fixtures with real published workflows and artifacts.
- `test/integration/test_generic_business_validation_acceptance.py`: exact-version gating, correction, resume, exports, and older-release refusal.
- The same generic acceptance suites cover no-rules publication, required-field validation, saved drafts, completion and exports, including a catalog outage in the browser.
- `test/visual/test_generic_business_rules_modules.py`: generic descriptor extension, typed choices, scopes/constants, and preserved unavailable configurations.
- `test/visual/test_generic_business_rules_visual.py`: desktop/mobile keyboard authoring, publication, catalog retry, operator gating, and actual downstream exports.
- `docs/admin/managing-review-forms.md`, `docs/operator/reviewing-extracted-data.md`: generic authoring and operator guidance.
- `docs/reference/review-schema-format.md`, `docs/reference/api-contracts.md`: comparison and catalog/display response contracts.
- `docs/developer/business-validation-plugins.md`: reviewed metadata and reusable widget extension contract.
- `docs/it-support/deployment-and-upgrades.md`: catalog rollout and comparison downgrade guard.
- `tasks/tasks-r4-business-validation.md`: links this delivery to the existing implementation record.

The table below records the original expected implementation areas. The Relevant
Files list above records the actual delivery.

| Area | Expected files and purpose |
| --- | --- |
| Catalog | `modules/services/business_validation_registry.py`: validated editor metadata; proposed `business_validation_catalog_service.py`: safe catalog projection |
| New pattern | `modules/services/business_validation.py`: comparison contract/evaluation; `business_validation_schema.py`: scope-aware operand bindings |
| API | `modules/api_router.py`: authenticated catalog route; `review_service.py`: nonpersistent operator display metadata |
| Editor | `web/static/js/schema-editor/business-rules.js`, `api.js`, `controller.js`, `web/templates/schema_editor.html`: picker, catalog loading, reusable controls |
| Review UI | `web/static/js/human-review/validation-view.js` and affected callers: shared neutral titles and safe fallback |
| Tests | Existing business-validation service/schema/extension suites, review/schema APIs, editor/review module and visual suites; new catalog/comparison tests as needed |
| Assets | Affected styles and asset graph versions; regenerate committed CSS when required |
| Documentation | Admin review-form guide, operator review guide, schema/API references, plugin developer guide, and R4 task record |

The admin guide should lead with reusable operations and include invoice and
non-invoice examples. The plugin guide should explain metadata/widget support and
version retention. The schema/API references should specify comparison operands,
scope, exact ordering, equality tolerance, and the two catalog/display responses.
Operator guidance should explain the neutral names, actual field labels, and
unchanged warning/blocking policy. Mark these docs implemented only with the code.

## Deliberately outside the first delivery

Nested AND/OR condition groups, arbitrary formulas, cross-document queries,
reference-data fetching, unit/currency conversion, and document-specific custom
policy engines need separate requirements. Adding a lookup inside the pure
evaluator would violate its existing contract; persisted enrichment belongs in
an upstream pipeline task. The registry remains extensible through reviewed code.

## Original proposal verification

At the proposal stage, this document was the only new authored file. No application,
test, dependency, runtime configuration, database, or pipeline changes were made.
The proposal was checked against the current registry, schema binder, editor,
review findings UI, and architecture documentation. Documentation link/structure
verification passed: 18 tests in 0.87 seconds, using:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/tools/test_documentation_structure.py --tb=short
```

Runtime/type/browser checks were not run for this proposal and are not claimed
as evidence that the proposed design has been implemented.

## Implementation verification — 2026-11-11

The catalog-driven editor, five approved patterns, operator titles, comparison
semantics, and maintained guides are implemented. Existing rule IDs, saved keys,
hashes, accepted-report evidence, and pinned versions retain their contracts.
There is no database migration or automatic republishing.

Focused verification passed **135 tests** in 12.81 seconds. The new integrated
browser suite passed **4 tests** in 41.31 seconds. Those browser tests author and
publish shipping/insurance forms, bind exact versions, render synthetic PDFs,
reject blocked completion, correct/revalidate/save/reload, accept, resume, and
verify JSON/CSV/PDF exports. They also prove no-rules forms can publish while the
catalog is unavailable, keep required-field validation, hide Business checks and
Revalidate, restore drafts, complete, and export normally. The service acceptance
suite covers shipping, insurance, and invoice workflows both with and without rules.

Browser checks include keyboard search/selection, explicit row/document scopes,
field/constant switching, equality tolerance, catalog failure/retry, administrator
and operator permissions, and 390-pixel layouts with native scrollbar space.
Screenshots were inspected after transitions settled. Provider extraction is
stubbed; publication, SQLite services, workflow resume, and exporters are real.

```powershell
.\.venv\Scripts\python.exe -m pytest -q test/services/test_business_validation_catalog.py test/services/test_compare_number_validation.py test/integration/test_generic_business_validation_acceptance.py test/integration/test_versioned_schema_api.py test/integration/test_new_ui_routes.py test/visual/test_generic_business_rules_modules.py test/visual/test_ui_performance_assets.py test/tools/test_documentation_structure.py --tb=short
$env:GENERIC_RULES_EVIDENCE_DIR = 'D:\python_code\pdfdoc_extraction\output\generic-business-rules-2026-11-11\visual'
.\.venv\Scripts\python.exe -m pytest -q test/visual/test_generic_business_rules_visual.py --tb=short
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe
npm run build:css
.\.venv\Scripts\python.exe -m tools.frontend_release_check check
git diff --check
```

Pyright returned **0 errors, 0 warnings**; the CSS build, all **16 frontend
release graphs**, and whitespace checks passed. A subsequent cache-version check
of route/asset/documentation tests passed **58 tests**. The first full run exposed
three old asset-version assertions; those were corrected before the final run.

The final full non-live suite passed **2,051 tests**, with **4 expected skips**, in
507.50 seconds (8 minutes 27 seconds):

```powershell
$env:RUN_LLAMACLOUD_SPLIT_SMOKE = '0'
.\.venv\Scripts\python.exe -m pytest -v --ignore=test/third_party/llamacloud_connection_test.py --tb=short --junitxml output\generic-business-rules-2026-11-11\full-suite.xml
```

The four skips are the opt-in live LlamaCloud Split smoke test and three
Windows permission tests. The credentialed live connection module was excluded
as documented in the repository's testing guide. The final suite includes the
new no-rules workflows, all prior invoice acceptance checks, and existing
review/editor/workflow regressions. No test failures remain.

Local evidence lives under `output/generic-business-rules-2026-11-11/` and is
excluded through `.git/info/exclude`. No live provider checks were requested or
run, and the supplied application credentials are absent from changed source
and evidence. No changes were staged or committed.
