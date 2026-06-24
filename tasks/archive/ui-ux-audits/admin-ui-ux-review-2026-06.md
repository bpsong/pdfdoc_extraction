# Admin UI/UX Review Report

**Pages reviewed:** `/app/schemas`, `/app/settings/validation`, `/app/admin/pipeline`, `/app/admin/tasks`, `/app/admin/audit`, `/app/admin/dry-run`

**Date:** June 2026
**Scope:** UI layout, information architecture, usability, functional completeness, and first-timer clarity for the admin role

---

## Executive Summary

The admin section is structurally complete and the DaisyUI/Tailwind shell is consistent across all pages. Most pages deliver the right data. The recurring problems are:
layout whitespace that signals emptiness or incompleteness even when the page has loaded correctly; buttons and actions with no contextual explanation that confuse first-time admins; missing confirmation on destructive actions; and pages that operate as isolated islands with no cross-links to related workflows. The dry run page has a deeper problem: what it actually does is fundamentally different from what its name implies, and the current form makes it nearly useless without prior knowledge of the internal mock JSON format.

---

## 1. `/app/schemas` — Schema Editor

### What works well
- Three-column layout (list / edit / YAML preview) maps well to the schema-editing mental model.
- Field type toolbar buttons make adding fields fast.
- YAML preview updates live as you edit.
- Duplicate action with name prompt is practical.

### Layout and whitespace issues

The schema detail panel and the YAML preview panel are both set to `min-height: calc(100vh - 8rem)` via `.schema-editor-workspace`. When a schema has few fields the centre panel has a large, empty field-tree area below the last field row, with the "No fields" dashed empty-panel placeholder visible even after loading. Visually this looks like loading failed. The fix is to let the field-tree area grow naturally with content rather than filling the full viewport height.

The YAML preview panel has a fixed `min-height: 26rem`. For a newly created schema with only two or three fields, the YAML content is four or five lines long and the remaining 20+ rem below it is just a grey background (`oklch(var(--b2))`). This empty grey block looks like a broken code editor. The preview should size to its content with a reasonable minimum.

### Button and action confusion

- The page header has a single **New Schema** button. The detail panel has **Duplicate** and **Save**. There is no label hierarchy or tooltip explaining the difference. A first-time admin does not know that "New Schema" creates a blank schema and "Duplicate" copies the current one — both are creation flows that look visually equivalent.
- The field type buttons in the toolbar (String / Number / Boolean / Enum / Object / Array) have no label or tooltip explaining they add a field *at the top level*. When an admin is editing a nested object, clicking "String" adds the field to the root, not to the nested object they were looking at. Nothing communicates this scope ambiguity.
- **Validate** and **Save** are in the detail panel header, but validation results appear at the bottom of the rightmost panel (the YAML preview column). After clicking Validate there is no scroll or focus shift, so the admin must manually scroll to see what happened.
- Saving an invalid schema is allowed. There is no interlock between Validate and Save. The design intent was to gate Save on a clean validation result.

### Form and field editing issues

- Changing a field `key` on blur silently renames the field. If the new key conflicts with an existing key, the rename is silently dropped — no error message is shown.
- Enum `Choices` is a comma-delimited plain text input. There is no way to add, reorder, or remove individual values without editing the raw string. This is error-prone for schemas with many choices.
- The `help`, `default`, `min_value`, `max_value`, `min_length`, and `max_length` field properties defined in the canonical field definition are not exposed in the UI at all.
- The schema list panel (18 rem fixed width) has no search, no sort, and no grouping. With many schemas, finding a specific one requires visually scanning a long list.

### Responsiveness

Below the 900 px breakpoint the three columns collapse to one. The field row grid also collapses to a single column, so every field row stacks Key / Label / Type / Required vertically. Editing a schema with many fields on a narrow screen becomes very cumbersome.

---

## 2. `/app/settings/validation` — Configuration Validation Center

### What works well
- Four summary metric cards (Errors / Warnings / Info / Readiness) are the right first thing to see.
- Active config is auto-validated on page load, which is genuinely useful.
- Raw JSON panel can be hidden, reducing noise when focusing on findings.

### Layout and whitespace issues

This page has the most significant whitespace problem in the admin section. The layout is a CSS grid with two columns: the controls panel on the left (`minmax(20rem, 0.42fr)`) and the four summary cards on the right. Below them, the findings table and raw JSON span the full width.

**The controls panel is dominated by the draft YAML textarea.** The textarea has `min-height: 14rem`, which means roughly 300 px of empty resizable box is always visible even when the admin has not typed anything and has no intention of validating a draft. This pushes the Strict mode and Import checks toggles out of view on most laptop screens (the viewport is approximately 900–1000 px tall after the sidebar and header). An admin arriving on the page for the first time sees: some toggles, a large empty textarea, and an info alert — but the actual action buttons (Validate Active / Validate Draft / Validate Schemas) are scattered across three different locations (page header, page header, panel header) without any introductory text.

**After a validation run that returns zero findings**, the summary cards show 0/0/0/Ready and the findings table shows "Validation passed" in a single centred row. The table still renders with its full 62 rem minimum width, the thead, and a single centred success row — leaving a large horizontal scroll zone and white space that makes the "passed" state feel underwhelming. A compact, prominently-placed success banner would serve better than an empty wide table.

**The Raw Details panel renders `{}` on load** with `min-height: 12rem` and `max-height: 28rem` of grey background. Before any validation has run, this is 12 rem of grey that communicates nothing. It should be collapsed by default with a "Show raw details" toggle.

### Button and action confusion — the core first-timer problem

The three action buttons are the biggest UX failure on this page:

| Button | Location | What it actually does |
|--------|----------|----------------------|
| **Validate Active** | Page header, right | Validates the currently running `config.yaml` |
| **Validate Draft** | Page header, right | Validates YAML pasted into the textarea below |
| **Validate Schemas** | Controls panel header | Validates all schema YAML files on disk |

A first-time admin sees two visually identical buttons in the top-right corner and a third button buried inside the panel. Nothing explains the difference between them until you read the small subtitle text "Active configuration" which updates after a run. The spatial separation of **Validate Draft** (header, top-right) from the **Draft config YAML** textarea (controls panel, left side, below the fold on many screens) means these two elements that belong together are as far apart as possible on the page.

**Recommended labelling improvements:**
- Rename **Validate Active** → **Validate Config File** with a sub-label "Checks the running config.yaml"
- Rename **Validate Draft** → **Validate Pasted YAML** with a sub-label "Checks YAML you paste below"
- Move **Validate Schemas** into the page header alongside the others, or add a section heading "Run Validation" above all three buttons with short descriptions of each scope.
- Add a short paragraph at the top of the controls panel: *"Choose what to validate. 'Config File' checks your running configuration. 'Pasted YAML' checks a draft you type below without saving. 'Schemas' checks all schema files on disk."*

### Missing pipeline validation

The design document specifies a **Validate Pipeline** button calling `POST /api/pipeline/validate`. This is not present. A complete validation story needs all three scope types: config, pipeline, and schemas. Without it, an admin who validates config and schemas and sees "Ready" may publish a broken pipeline.

### Findings table

- Six columns with `min-width: 62rem` forces horizontal scrolling on most laptop screens. The most important columns — Message and Suggestion — are in positions 4 and 5 and are hidden off-screen on the initial view.
- There is no row-level expansion or click-to-expand detail. The six columns need to be visible simultaneously to be actionable.
- No filtering by level (errors only), by code prefix, or by path. With many findings the admin cannot focus on blockers first.
- Consider: Level, Path, Message as the three always-visible columns, with Code, Suggestion, Location available via row expansion.

---

## 3. `/app/admin/pipeline` — Pipeline Configuration

### What works well
- Active / Draft / Parameters three-column comparison is the right mental model.
- Type badges (Extract / Split / Review / Optional) give instant visual scan.
- Enable/disable, move up/down, and remove are in-row and discoverable.
- YAML preview auto-updates on every change.
- Publish is correctly disabled when there are blocking findings or unsaved changes.

### Layout and whitespace issues

The grid layout is:
```
active | draft | editor        ← row 1
yaml   | yaml  | validation    ← row 2
yaml   | yaml  | diff          ← row 3
```

**Row 2 and row 3 always render at full height regardless of content.** The YAML preview has `min-height: 18rem` and `max-height: 34rem`. The diff panel also has `min-height: 18rem`. On a 1080p screen with a typical 5–6 step pipeline, the YAML content fills roughly 10–12 lines, then there is 15+ rem of grey padding below it. Below that sits the validation panel (also `min-height` padded) and the diff panel. The page is routinely 2.5× the viewport height before any user interaction, requiring significant scrolling to reach the diff and validation results.

**Practical fix:** Remove `min-height` from the YAML preview, validation, and diff panels. Let them shrink to content. Use `max-height` with overflow scroll to cap growth instead.

The empty draft panel shows a dashed empty box (`min-height: 14rem`) reading "No draft pipeline loaded". On first load the draft is a copy of active, so this state should rarely occur — but while loading, the empty box flashes briefly, making the page feel broken during the API call.

### Button and action confusion

The publish workflow has five steps spread across three UI zones:

1. **Add / edit steps** — Draft panel body
2. **Save Draft** — Draft panel header
3. **Validate** — Draft panel header
4. **Diff** — Validation panel header
5. **Publish** — Page header (top-right)

There is no sequence indicator, no numbered steps, no disabled-state explanation for why Publish is greyed out. An admin who adds a step and immediately tries to Publish sees a disabled button with no explanation. They must discover through trial and error that Save Draft → Validate is the required sequence.

**Save Draft** and **Validate** are placed together in the draft panel header, which implies they are peers. They are not: Save Draft must come before Validate in the workflow. Their visual equality is misleading.

**Publish** is the most important and most consequential action but it lives in the far top-right corner, visually detached from the validation result that gates it.

### Step parameter editor

- Parameters are edited as raw JSON in a textarea. This is a high barrier for non-technical admins and contradicts the design document which specified form-based parameter editing.
- Module and Class are editable free-text inputs but should be read-only display fields for existing tasks (only a developer would change a class path). Accidental edits silently corrupt the step definition until the next validation run.
- When params JSON is invalid the inline error appears, but Save Draft remains enabled. The last-valid parsed params are silently sent on save, not the in-progress text the admin is editing.

### Visual / content issues

- The diff output is a raw unified text patch in a `<pre>` block. For a YAML change, a line-by-line text diff is hard to parse quickly. Even simple colour coding (red removed, green added) would help significantly.
- The `on_error` field offers "Default", "Stop", "Continue" with no explanation of what "Default" means in the runtime context.
- "Reset to Active" is missing. There is no way to discard draft edits and revert to the active pipeline without a full page reload.

---

## 4. `/app/admin/tasks` — Task Catalog

### What works well
- Summary cards (Total / Configured / Importable / Import Issues) are an accurate health snapshot.
- Search + category + status filters work together and update the table immediately.
- The detail panel comprehensively shows inputs, outputs, parameters, and configured params.
- Import errors appear as inline alerts in the detail panel.

### Layout and whitespace issues

The task catalog detail panel uses `.empty-panel` with `min-height: 14rem` when no task is selected. On load the first task is auto-selected, so this state is visible only briefly. But the detail panel has `min-height: calc(100vh - 18rem)`, which means on a tall viewport the detail area below the last section has a large empty white block.

The expected inputs and expected outputs sections render as badge groups. When a task has no declared inputs or outputs the sections render as empty flex containers with no height, no empty-state text, and no divider — the section headings ("Expected Inputs", "Expected Outputs") appear next to nothing, making them look broken.

### IA / workflow issues

- The page is read-only. There is no "Add to Pipeline" action despite the design document specifying one. Without it this is a reference page only and an admin must navigate to Pipeline Configuration, find the task by name in a plain dropdown with no search, and add it blind.
- The table auto-selects the first task on load. If that task has an import error, the red error alert appears before the admin has done anything — which may cause alarm unnecessarily.
- Import failures should sort to the top of the table by default. Currently there is no sort affordance at all.
- The "Configured As" column shows a dash for unconfigured tasks. A soft "Not in pipeline" badge would be more readable and consistent with the badge-based visual language used elsewhere.

---

## 5. `/app/admin/audit` — Admin Audit

### What works well
- Two-panel layout (list + detail) is the right model for audit browsing.
- Clicking a row immediately updates the detail panel.
- Date range, user, and event type filters cover the main search dimensions.
- Apply and Clear are explicit and correctly positioned.

### Layout and whitespace issues

The admin audit layout splits the viewport into two columns: the event table (roughly 2/3 width) and the detail panel (roughly 1/3 width). The detail panel has a `min-height: 24rem` and `max-height: 34rem` `<pre>` block. When an event has a small JSON payload the `pre` renders a few lines of JSON in a fixed-height grey container, with the remainder being empty grey background. For a typical admin action event this is 20+ rem of empty grey.

The filter bar at the top uses a 5-column grid: Event Type / User / From / To / Apply+Clear. On a 1920 px monitor this renders comfortably. On a 1280 px laptop each column is quite narrow and the datetime-local inputs clip their placeholder text.

When there are no audit events (fresh install), the table shows "No admin audit events" in a row with `py-10`. The detail panel still shows `{}` in the `<pre>` block. The combination of empty table and empty JSON panel with no explanatory text looks like a loading failure rather than a genuine empty state.

### IA / workflow issues

- The event type filter is a free-text input. An admin must know the exact event type string (`admin_pipeline_published`, `admin_schema_saved`, `admin_pipeline_dry_run`). There is no dropdown, no typeahead, and no list of valid values anywhere on the page. The placeholder `admin_pipeline_published` is a single example that implies these are the only events, when in fact there are many.
- The detail panel renders the entire event object as `JSON.stringify(event, null, 2)` including internal IDs, timestamps, and raw nested `event_json`. For pipeline publish events the payload contains a full before/after YAML model — this can be hundreds of lines. The panel maxes out at 34 rem and scrolls, but there is no structured view, no diff rendering, and no way to copy just the before or after state.
- The table hard-caps at 100 events with no pagination UI, no "showing X of Y" counter, and no "load more" control. On a busy system with many events per day, relevant history disappears with no way to retrieve it except a date filter.
- The "Target" column values like `document doc_abc123` are plain text with no links. There is no way to navigate from an audit event to the entity it describes.

---

## 6. `/app/admin/dry-run` — Pipeline Dry Run

### Is this feature actually useful in its current form?

**The short answer is: not really, as currently implemented.** Here is why.

The dry run backend (`PipelineDryRunService.run()`) does the following:
1. Reads the pipeline step configuration (which tasks are in the pipeline, their params).
2. Runs pipeline-level validation against those steps.
3. Evaluates mock JSON that *you* hand it against the ReviewGateTask threshold configuration.
4. Returns a summary saying whether the review gate *would* trigger given that mock input.
5. Skips all exports.
6. Records an audit event.

It does **not**:
- Actually process any PDF.
- Call LlamaCloud for extraction.
- Call LlamaCloud for split decisions.
- Run any actual task logic.
- Use a real document's data.

The "extraction" row in the results table shows `mock_field_count` — the number of fields in the JSON you manually typed, not fields that were actually extracted. The "split" row shows the split_decisions list from your mock JSON. The "review gate" row evaluates your mock confidence values against the configured threshold.

**What the admin actually gets:** a re-statement of what they typed back to them, plus pipeline validation results (which are also available on the Pipeline Configuration page). The only genuinely unique output is seeing whether the review gate *would* trigger given a specific set of mock confidence values — but this requires the admin to manually construct valid mock JSON, know the exact field keys from the active schema, and understand the confidence value format. There is no schema-aware helper, no prefill from the active configuration, and no guidance.

**The fundamental problem:** the page is labelled and positioned as "test a sample PDF through the pipeline before publishing." The backend simulation confirms the pipeline structure is valid and re-evaluates thresholds on mock data. The two mental models are very different. An admin expecting to upload a PDF and see it run through the pipeline will be confused and disappointed.

### What would make this genuinely useful

**Option A — Keep as a threshold simulator, rebrand it clearly.** Rename the page to "Review Gate Simulator" or "Threshold Preview". Integrate it with the Pipeline review-gate task settings as a "Test current settings" panel. Remove the PDF upload and document ID fields entirely since the backend ignores them. Add a schema-aware mock fields generator that pre-populates field keys from the configured schema. Label the output as "Given these confidence values, the review gate would: [pass / trigger review]".

**Option B — Implement a genuine dry run.** This requires the backend to actually run the split adapter (with a test mode flag), actually call the extraction API (with a test document), and walk through the configured pipeline tasks. This is a much larger investment but matches what the page name implies.

**Option C — Remove the Dry Run page.** The pipeline validation functionality already exists on the Pipeline Configuration page. The review gate threshold evaluation is better served inside Pipeline task configuration. If neither Option A nor Option B is feasible in the near term, removing the page is better than leaving an ineffective tool that erodes admin trust in the system.

### Layout and whitespace issues

The layout uses two columns: controls panel (left, `minmax(18rem, 0.5fr)`) and results panel (right). Below them the raw JSON panel spans full width.

**The controls panel.** The three inputs (Sample PDF / Document ID / Mock Results JSON) appear as peer form fields. There is no indication that Sample PDF and Document ID are mutually exclusive. The mock JSON textarea has `min-height: 14rem`, which renders approximately 11 lines of the pre-populated JSON. Because the JSON barely fills the textarea, there is white space below it — and below the controls panel itself on a tall viewport, further empty white space appears.

**The results panel before a run.** On load, the four stat boxes show `-` and the decision table shows "No dry-run result" with `py-10`. The full-width raw JSON panel shows `{}`. The combined effect is: four boxes with dashes, an empty table, and a large grey block — all on a page that has not done anything yet. This communicates failure, not "ready to run".

**The Run Dry Run button is in the page header.** After clicking, results appear in the middle of the page. On a shorter viewport (< 900 px height) the admin must scroll down past the controls panel to see the results. There is no auto-scroll or focus shift.

### Button and action confusion

- The Run button label "Run Dry Run" is redundant ("dry run" once would be enough).
- There is no explanation anywhere on the page of what a dry run does, what inputs it needs, or what the results mean. The only description is the tiny subtitle under the panel header: "Draft pipeline input". This tells the admin nothing.
- The mock JSON textarea has no schema reference, no format documentation, and no generated example based on the configured pipeline. The hardcoded default shows `"field_key": "supplier"` which is a placeholder that may not match any real schema field.

---

## Cross-Cutting Issues

### 1. Pervasive whitespace on empty/pre-run states

Almost every page has one or more fixed-height panels (`min-height` in rem or `calc(100vh - X)`) that render large grey or white empty areas before content loads or before the admin has taken any action. The pattern across pages:

| Page | Whitespace source |
|------|------------------|
| Schemas | Field tree empty-panel, YAML preview below content |
| Validation | Draft textarea (14 rem), Raw JSON panel (12 rem), findings table header with no results |
| Pipeline | YAML preview and diff panel below content (18 rem each) |
| Task Catalog | Detail panel bottom on tall viewports |
| Audit | Detail JSON panel below content |
| Dry Run | Controls panel, results panel, raw JSON panel all have fixed minimum heights before first run |

The fix is consistent: use `min-height` only where absolutely necessary (typically to prevent panels from collapsing to 0), keep values small (4–6 rem), and let content drive height. Use `max-height` with overflow scroll to cap tall panels instead.

### 2. No contextual help on any page

Every admin page has at least one concept that requires prior knowledge to use correctly:
- Validation: what is the difference between Validate Active vs Validate Draft vs Validate Schemas?
- Pipeline: what is the correct sequence to publish?
- Dry Run: what does the mock JSON need to contain, and what does the result mean?

None of these pages have tooltips, `?` help icons, inline explainers, or links to documentation. Adding a single sentence of contextual help per section would remove the majority of first-timer confusion.

### 3. No unsaved-changes warnings on navigation

Schema editor and Pipeline track `dirty` state in JavaScript but do not intercept sidebar navigation. Clicking any sidebar link while editing silently discards all changes.

### 4. No confirmation for consequential actions

- **Publish pipeline**: overwrites the live configuration. No confirmation.
- **Remove a step from the draft pipeline**: immediate with no undo.

### 5. No cross-page navigation links

Pages are isolated. Missing connections that an admin would naturally follow:
- Pipeline → Task Catalog (to look up a task before adding it)
- Pipeline → Validation Center (to check findings after publish)
- Dry Run → Audit (the page shows an audit event ID badge but it is not a link)
- Audit → Document/Batch detail (Target column values are plain text, not links)

### 6. Silent loading and toast-only error handling

All pages call `apiGet` or `apiPost` on load with no loading spinner. If the call fails, a toast appears briefly then disappears. The panel remains in its empty/placeholder state with no inline error or retry button. A failed page load looks identical to a slow page load from the admin's perspective.

### 7. Flat admin sidebar navigation

Seven admin items with equal visual weight. No grouping. Consider:

- **Configuration**: Pipeline, Tasks
- **Quality / Compliance**: Schemas, Validation, Audit
- **Tools**: Dry Run (or remove if not implemented as a genuine run)

---

## Priority Summary

| Priority | Issue | Pages |
|----------|-------|-------|
| **Critical** | Dry Run does not run the pipeline — rebrand, move, or remove | Dry Run |
| **High** | Validation: 3 buttons with no explanation of scope difference | Validation |
| **High** | Validation: Validate Draft button far from the draft textarea | Validation |
| **High** | Validation: No Validate Pipeline button | Validation |
| **High** | Pipeline: Publish workflow order is not communicated | Pipeline |
| **High** | Pipeline: Params editor is raw JSON, not forms | Pipeline |
| **High** | No unsaved-changes warning on navigation | Schemas, Pipeline |
| **High** | No confirmation on destructive / consequential saves | Pipeline |
| **Medium** | Whitespace: fixed min-heights inflate all pages before content | All |
| **Medium** | Draft YAML textarea is always open and dominates controls panel | Validation |
| **Medium** | Raw Details panel shows `{}` on load, should be collapsed | Validation |
| **Medium** | Task Catalog is read-only — no Add to Pipeline action | Tasks |
| **Medium** | Schema save not gated on validation result | Schemas |
| **Medium** | Schema field properties (help, min, max, default) missing | Schemas |
| **Medium** | Audit: Event type filter is free-text only | Audit |
| **Medium** | Audit: 100-event hard cap with no pagination | Audit |
| **Medium** | No contextual help on any admin page | All |
| **Medium** | No cross-page navigation links | All |
| **Low** | Pipeline: YAML diff is raw text with no colour coding | Pipeline |
| **Low** | Pipeline: No Reset-to-Active button | Pipeline |
| **Low** | Task Catalog: Import failures not sorted to top | Tasks |
| **Low** | Audit: Detail panel is raw JSON dump, no structured diff view | Audit |
| **Low** | Audit: No export or copy-to-clipboard | Audit |
| **Low** | Silent loading states — no spinner or skeleton | All |
| **Low** | Toast-only error handling — no inline error state | All |
| **Low** | Admin sidebar items not grouped semantically | All |
