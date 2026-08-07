# Bug Report: Pipeline Editor — Focus Jumps When Editing Field Properties

## Summary

When editing any field property in the production pipeline editor (adding a new task,
then editing its field names, aliases, types, etc.), focus jumps away after each
`change` event. The edited value is saved to state correctly, but the input element
the user was typing in is destroyed and recreated from scratch, causing:

- Focus to land on `<body>` or the next focusable element
- Scroll position to reset
- Partial edits in adjacent fields to be discarded

This affects **all task types** in the production editor (`web/static/js/pipeline_config.js`),
not just GLM-OCR. GLM-OCR is more noticeable because it has more interactive fields per entry.

---

## Root Cause

**File:** `web/static/js/pipeline_config.js`

Every user interaction that changes a parameter calls `markDirty()`, which
unconditionally calls `render()`, which calls `renderEditor()`, which sets:

```js
editorBody.innerHTML = `...`;  // ← destroys ALL DOM nodes in the editor panel
```

The entire right-hand editor panel is rebuilt as an HTML string on every single
`change` event — including selecting a type dropdown, checking a checkbox, or
renaming a field. All `<input>` elements the user is interacting with are destroyed
and recreated, causing the browser to lose focus.

```
User edits an input
  → `change` event fires
  → handleParamActionChange() or updateParamControl() or updateSelectedField()
  → markDirty()
  → render()
  → renderEditor()
  → editorBody.innerHTML = `...`   ← input is destroyed
  → focus returns to <body>
```

The same problem exists in **`schema_editor.js`** for the schema field editor, where
`markDirty()` → `render()` → `fieldTree.innerHTML = renderFieldRows(...)`.

---

## Affected Interactions (All Task Types)

The table below lists every editor interaction that currently triggers the full
`innerHTML` replacement, grouped by task type and input category.

### Universal (all tasks) — `data-step-field` inputs

These are the top-level step fields in the Properties panel header:

| Input | Event Path | Effect |
|-------|-----------|--------|
| Label text input | `change` → `updateSelectedField("label", ...)` → `markDirty()` | Full re-render |
| Key text input | `change` → `updateSelectedField("key", ...)` → `markDirty()` | Full re-render; key is also deduplicated |
| "If this task fails" select | `change` → `updateSelectedField("on_error", ...)` → `markDirty()` | Full re-render |
| "Enabled" toggle | `change` → `updateSelectedField("enabled", ...)` → `markDirty()` | Full re-render |

### Universal (all tasks) — `data-param-path` inputs

Any parameter field using `data-param-path` (text inputs, selects, number inputs,
checkboxes, textarea) goes through `updateParamControl()` → `markDirty()` on `change`.

### Extract (LlamaCloud) — `extractControls()`

Uses `extractionFieldControls()` which renders `data-param-action` inputs per field.
Every action below calls `markDirty()`:

| Input | Action |
|-------|--------|
| Field key text input | `rename-extract-field` |
| Field type select | `field-type` |
| Allowed values text input | `field-choices` |
| Value normalizer select | `field-normalizer` |
| Required checkbox | `field-required` |
| "Add field" button | `add-extract-field` |
| "Remove field" button | `remove-extract-field` |
| Provider mode select | `provider-mode` |
| Row schema field add/remove | `add-schema-draft-field`, `remove-schema-draft-field` |

**Focus jump severity: HIGH** — renaming a field key causes the field key input to be
destroyed; a new input with the new key is rendered in its place. The name in the input
seems to "disappear" even though it was saved.

### GLM-OCR — `glmOcrExtractControls()`

Uses the same `extractionFieldControls()` as Extract, plus additional controls
(`ollama_host`, `model`, `document_instructions`, `dpi`, `num_ctx`, `num_predict`,
`timeout_seconds`). Every `data-param-path` change on these fields also triggers a
full re-render.

**Focus jump severity: HIGH** — same as Extract. More inputs per task means more
surface area for the bug. The stats summary panel at the top (field count, table
status) also changes on every field edit, which makes the re-render visually jarring.

### Split — `splitControls()`

| Input | Trigger |
|-------|---------|
| API key input | `data-param-path` → `markDirty()` |
| Configuration mode select | `provider-mode` → `markDirty()` |
| Configuration ID input | `data-param-path` → `markDirty()` |
| Category name text inputs | `data-param-path` → `markDirty()` |
| Category description textarea | `data-param-path` + blur → `markDirty()` |
| "Add category" button | `add-split-category` → `markDirty()` |
| "Remove category" button | `remove-split-category` → `markDirty()` |
| Confidence level checkboxes | `split-confidence-level` → `markDirty()` |
| Allowed categories input | `data-param-path` → `markDirty()` |
| Split dir input | `data-param-path` → `markDirty()` |

**Focus jump severity: MEDIUM** — category `name` and `description` fields are the
worst affected, as each one destroys and recreates all other category inputs too.

### Storage (CSV / PDF) — `storageControls()`

| Input | Trigger |
|-------|---------|
| Directory path input | `data-param-path` → `markDirty()` |
| Filename template input | `data-param-path` → `markDirty()` |
| Token insert button | `insert-filename-token` → `markDirty()` |
| Nested storage toggle | `toggle-nested-storage` → `markDirty()` |
| Extraction override toggle | `toggle-storage-extraction` → `markDirty()` |
| Object JSON textarea (apply) | `apply-object-json` → `markDirty()` |
| Directory browser selection | `loadDirectoryBrowser()` → `markDirty()` |

**Focus jump severity: LOW–MEDIUM** — less dense than extract/split.
The filename template input loses focus on every character change that triggers `change`.

### Review — `reviewControls()`

| Input | Trigger |
|-------|---------|
| Confidence % number input | `confidence-percent` → `markDirty()` |
| Confidence range slider | `confidence-percent` → `markDirty()` |
| Field threshold overrides (key rename) | `rename-threshold-key` → `markDirty()` |
| Field threshold number inputs | `data-param-path` → `markDirty()` |
| "Add threshold" button | `add-threshold` → `markDirty()` |
| "Remove threshold" button | `remove-threshold` → `markDirty()` |
| Document-type threshold key (text input) | `rename-threshold-key` → `markDirty()` |
| Split confidence level checkboxes | `review-split-level` → `markDirty()` |
| Schema version select | `data-param-path` → `markDirty()` |
| Queue name input | `data-param-path` → `markDirty()` |
| Review scope select | `data-param-path` → `markDirty()` |
| Condition checkboxes (4×) | `data-param-path` → `markDirty()` |

**Focus jump severity: MEDIUM** — the "document-type threshold" key text input is a
rename that suffers the same total-DOM-replacement problem as the extract field key input.

### Rules — `rulesControls()`

| Input | Trigger |
|-------|---------|
| Reference CSV file input | `data-param-path` → `markDirty()` + CSV load |
| Update field select | `data-param-path` → `markDirty()` |
| Write value input | `data-param-path` → `markDirty()` |
| "Add clause" button | `add-rule-clause` → `markDirty()` |
| "Remove clause" button | `remove-rule-clause` → `markDirty()` |
| Clause column select | `data-param-path` → `markDirty()` |
| Clause from-context select | `data-param-path` → `markDirty()` |
| Clause comparison select | `rule-comparison` → `markDirty()` |
| Backup checkbox | `data-param-path` → `markDirty()` |

**Focus jump severity: LOW** — mostly selects, which do not suffer as badly since the
browser selects commit on change anyway. The "Write value" text input loses focus on change.

### Schema Editor — `schema_editor.js`

A separate but identical bug:

| Input | Trigger |
|-------|---------|
| Field key input (`data-field-prop="key"`) | `change` → `updateField()` → `markDirty()` → `fieldTree.innerHTML = renderFieldRows(...)` |
| Any other field prop input | `change` → `updateField()` → `markDirty()` → full `fieldTree` re-render |
| Schema name input | `change` → `markDirty()` → full `render()` |
| Schema description input | `change` → `markDirty()` → full `render()` |

---

## Fix Strategy

### Approach: Restore Focus After Re-render (Minimal, Low-Risk)

This is the safest fix: keep the existing `markDirty()` → `render()` architecture
entirely intact, but save the active element's identity before the re-render and
restore focus to the equivalent new element afterwards.

Implement a `preserveFocus()` helper that:
1. Before `renderEditor()` runs: records which element has focus and a stable
   selector to find it again (e.g. `data-param-action` + `data-field-key`, or
   `data-param-path`, or `data-step-field`).
2. After `renderEditor()` runs: queries `editorBody` for the matching element and
   calls `.focus()` on it, optionally restoring caret position for text inputs.

```js
function renderEditorWithFocusRestore() {
    // 1. Capture focus state before re-render
    const active = document.activeElement;
    let focusSelector = null;
    let selectionStart = null;
    let selectionEnd = null;
    if (active && editorBody.contains(active)) {
        // Build the most specific stable selector available
        if (active.dataset.paramAction && active.dataset.fieldKey) {
            focusSelector = `[data-param-action="${CSS.escape(active.dataset.paramAction)}"][data-field-key="${CSS.escape(active.dataset.fieldKey)}"]`;
        } else if (active.dataset.paramPath) {
            focusSelector = `[data-param-path="${CSS.escape(active.dataset.paramPath)}"]`;
        } else if (active.dataset.stepField) {
            focusSelector = `[data-step-field="${CSS.escape(active.dataset.stepField)}"]`;
        }
        // Preserve caret position for text inputs
        if (typeof active.selectionStart === "number") {
            selectionStart = active.selectionStart;
            selectionEnd = active.selectionEnd;
        }
    }

    // 2. Perform the full re-render (unchanged)
    renderEditor();

    // 3. Restore focus to the matching element in the new DOM
    if (focusSelector) {
        const restored = editorBody.querySelector(focusSelector);
        if (restored) {
            restored.focus();
            // Restore caret position for text inputs
            if (selectionStart !== null && typeof restored.setSelectionRange === "function") {
                try {
                    restored.setSelectionRange(selectionStart, selectionEnd);
                } catch (_) { /* ignore for inputs that don't support it */ }
            }
        }
    }
}
```

Then in `render()`, replace the `renderEditor()` call with `renderEditorWithFocusRestore()`.

Apply the same pattern to `schema_editor.js` for `fieldTree.innerHTML = renderFieldRows(...)`.

### Why This Approach

- **No architectural change**: `markDirty()` → `render()` → `renderEditor()` chain
  is untouched. Risk of breaking anything else is minimal.
- **Covers all task types**: The focus restore runs for every re-render regardless of
  which task or input type triggered it.
- **Handles the rename case**: For `rename-extract-field`, the new input has a new
  `data-field-key` value. The selector won't match after a rename — focus will land
  on the first focusable element in the form, which is acceptable. A more targeted
  fix for the rename case specifically is noted below.

### Rename-specific improvement (optional but recommended)

For `rename-extract-field` and `rename-threshold-key`, after `markDirty()` returns,
the calling handler knows the `newKey`. It can pass that as a hint so the focus-
restore logic targets the new key instead of the old one:

```js
// In the rename-extract-field handler, after markDirty():
const nextInput = editorBody.querySelector(
    `[data-param-action="rename-extract-field"][data-field-key="${CSS.escape(newKey)}"]`
);
if (nextInput) nextInput.focus();
```

### Same fix for `schema_editor.js`

In `schema_editor.js`, `render()` sets `fieldTree.innerHTML = renderFieldRows(...)`.
The same `preserveFocus` pattern applies: capture the focused element's
`data-field-path` + `data-field-prop` before `fieldTree.innerHTML = ...`, then
re-query and refocus after.

---

## Files to Change

| File | Change |
|------|--------|
| `web/static/js/pipeline_config.js` | Add `renderEditorWithFocusRestore()` helper; call it from `render()` instead of `renderEditor()` |
| `web/static/js/schema_editor.js` | Add focus-save/restore around the `fieldTree.innerHTML = renderFieldRows(...)` line inside `render()` |

No other files need to change. No backend changes. No new dependencies.

---

## Testing Guidance

After the fix, verify manually:

1. **GLM-OCR / Extract — field key rename**: Type a new field key, press Enter → focus
   stays in the field area (acceptable if it moves to first field; must not jump to `<body>`).
2. **GLM-OCR / Extract — field type dropdown**: Change type → focus returns to the
   same dropdown.
3. **GLM-OCR / Extract — alias text input**: Type in the alias field, press Enter →
   focus returns to the alias input of the same field.
4. **Split — category name**: Type in a category name, press Enter → focus returns
   to the same category name input.
5. **Review — document-type threshold key**: Rename a key, press Enter → focus returns
   near the renamed key.
6. **Schema editor — field key**: Rename a field key, press Enter → focus stays in
   field area.
7. **Schema editor — field description**: Edit a description, press Enter → focus
   returns to the same description input.
8. **Step label / key**: Edit label or key at the top of Properties, press Enter →
   focus returns to the same input.

Automated test coverage (existing tests in `test/visual/`) should be re-run after
the change to confirm no regressions.
