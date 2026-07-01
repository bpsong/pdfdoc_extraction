# Schema Editor QA Report

| Field | Value |
|---|---|
| Date | 2026-06-30 |
| URL | `http://localhost:8000/app/schemas` |
| Account | `admin` |
| Scope | Visual and functional QA of schema creation, field editing, validation, saving, reload persistence, and responsive layout |
| Test schema | `fts_extraction_visual_qa.yaml` |

## Summary

The core workflow works: a new schema can be created from the extraction fields in `fts_config org.yaml`, validated, saved, reloaded, edited, saved again, and reloaded with the edit intact. The editor exposes appropriate type-specific controls, including Pattern/length controls for strings and numeric controls for floats.

Four gaps were found: three validation defects and one responsive-layout defect.

| Severity | Count |
|---|---:|
| Critical | 0 |
| High | 0 |
| Medium | 3 |
| Low | 1 |
| Total | 4 |

## Flow coverage

1. **Open and authenticate — Healthy.** The admin account reached the Schema Editor without errors. Baseline: [01-schema-list-baseline.png](screenshots/01-schema-list-baseline.png).
2. **Create schema metadata — Healthy.** Name, title, and description updated the draft and YAML preview.
3. **Add primitive fields — Healthy with validation gaps.** Added `supplier_name`, `purchase_order_number`, `project_number`, and `invoice_amount`; string and float controls changed with the selected type.
4. **Add nested array fields — Healthy.** Added `line_items` as an array of objects with `item_description`, `item_quantity`, `unit_price`, `discount`, and `total_amount`. Full draft: [05-complete-schema-valid.png](screenshots/05-complete-schema-valid.png).
5. **Validate — Partially healthy.** Normal schema validation succeeds, but malformed regex and contradictory constraints are accepted; duplicate-key state also conflicts with the global result.
6. **Save and reload — Healthy.** `fts_extraction_visual_qa.yaml` appeared in the list and all tested fields survived reload: [06-schema-saved-reloaded.png](screenshots/06-schema-saved-reloaded.png).
7. **Edit and reload — Healthy.** `project_number` was relabeled to `Project reference`, saved, and persisted after reload: [07-schema-edited-before-save.png](screenshots/07-schema-edited-before-save.png).
8. **Empty required metadata — Healthy with a UX caveat.** Save and Validate become disabled when Name and Title are blank, but no explanatory message is shown: [10-empty-metadata-validation.png](screenshots/10-empty-metadata-validation.png).
9. **Responsive layout — Needs improvement.** At 390×844, the page overflows horizontally and editing requires two-axis scrolling: [11-mobile-390x844.png](screenshots/11-mobile-390x844.png).
10. **Browser errors — Healthy.** No JavaScript console exceptions were observed during the tested flow.

## Findings

### ISSUE-001: Invalid regular expressions are reported as valid

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Functional / validation |
| URL | `http://localhost:8000/app/schemas` |

**Expected:** Pattern should compile as a regular expression, or validation should return a clear field-level error.

**Actual:** A Pattern value of `[` is included in YAML and the result remains green `Valid`.

**Reproduction:**

1. Enter a valid string field with length constraints: [issue-001-step-1.png](screenshots/issue-001-step-1.png).
2. Replace Pattern with `[`: [issue-001-step-2.png](screenshots/issue-001-step-2.png).
3. Select Validate; observe `Valid`: [issue-001-result.png](screenshots/issue-001-result.png).

**Recommendation:** Compile Pattern during field editing and during full-schema validation. Show the regex parser message next to Pattern, set `aria-invalid`, associate the error with `aria-describedby`, and prevent Save while invalid.

### ISSUE-002: Contradictory string-length constraints pass validation

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Functional / validation |

**Expected:** `min_length` must be less than or equal to `max_length`.

**Actual:** `min_length: 201` and `max_length: 200` are serialized and reported as `Valid`.

Evidence: [09-contradictory-length-validation.png](screenshots/09-contradictory-length-validation.png).

**Recommendation:** Add cross-field constraint checks for string lengths and numeric ranges. Apply equivalent checks to array sizes and date ranges if those controls are introduced.

### ISSUE-003: Duplicate-key error conflicts with the global Valid result

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Functional / UX / accessibility |

**Expected:** A duplicate key should make the schema invalid, disable Save, and produce one consistent summary linked to the affected input.

**Actual:** The editor shows a red message (`Field key "supplier_name" already exists at this level.`), while the YAML pane simultaneously shows green `Valid`. The preview retains the prior key, so it does not represent the visible draft.

Evidence: [08-duplicate-key-validation.png](screenshots/08-duplicate-key-validation.png).

**Recommendation:** Use one validation state for inline errors, preview generation, Save eligibility, and the global result. Replace `Valid` with an error summary and focus the first invalid field when Validate is selected.

### ISSUE-004: Narrow screens use a desktop canvas with horizontal overflow

| Field | Value |
|---|---|
| Severity | Low |
| Category | Visual / responsive / accessibility |

**Expected:** At 390 px, panels should stack or switch to an explicit list/editor/preview navigation without page-level horizontal scrolling.

**Actual:** The sidebar, schema list, editor, and preview remain on one wide canvas. The viewport shows clipped text and a horizontal scrollbar, making field editing and preview comparison difficult. Even at 1280 px, metadata and field values truncate because the three working columns are narrow.

Evidence: [11-mobile-390x844.png](screenshots/11-mobile-390x844.png) and [06-schema-saved-reloaded.png](screenshots/06-schema-saved-reloaded.png).

**Recommendation:** Below a defined breakpoint, collapse the sidebar and present Schemas, Editor, and YAML Preview as tabs or stacked sections. At desktop widths, allow resizable panels or give the editor more minimum width. Provide tooltips or full-value display for truncated names.

## Additional improvements

- When Save/Validate is disabled for blank Name or Title, display persistent inline guidance explaining why; disabled controls alone are weak feedback for keyboard and assistive-technology users.
- Add unsaved-change protection when selecting another schema, creating a new schema, or leaving the page.
- Add a field outline or collapse/expand controls for long nested schemas. The current single long form makes it hard to understand parent-child relationships and requires extensive scrolling.
- Keep the validation summary visible and include error count, affected field path (for example `line_items[].unit_price`), and links that scroll/focus each field.
- Consider a tested-pattern helper with an example value so users can verify regex behavior before saving.

### Implementation status — 2026-06-30

All recommended additional improvements have now been implemented:

- Missing Name or Title produces persistent, specific guidance and linked validation findings.
- Unsaved-change protection covers schema selection, New Schema, duplication, navigation, and browser close.
- Long schemas include a field outline that focuses the selected field without changing field order.
- Validation results appear above the YAML preview with an error count, compact nested paths such as `line_items[].unit_price`, and links that focus affected controls.
- String Pattern controls include an Example value and server-backed **Test pattern** action. Match, non-match, and invalid-regex results are announced without storing example data in the schema.

## Confirmed strengths

- The field palette covers primitive, enum, object, and array types.
- Type-specific controls update correctly; string fields expose Pattern, min/max length, placeholder, and multiline controls, while floats expose range, step, decimal-place, and format controls.
- Nested object fields inside an array can be added and retain their hierarchy after saving.
- The YAML preview updates with the draft and is useful for technical users.
- Save and subsequent edit persistence both passed.
- Empty Name/Title disables Save and Validate.
- Form controls expose accessible names in the browser accessibility tree.
- No browser console errors were observed.

## Evidence limits

- This was a visual and browser-interaction audit, not a full WCAG conformance assessment. Screen-reader announcements, contrast ratios, zoom/reflow beyond the tested viewport, and complete keyboard order still require dedicated testing.
- Reproduction video capture was attempted, but the local browser runner could not finalize video because `ffmpeg` is not installed. Step-by-step screenshots are included instead.
- The audit did not process a live PDF or test downstream review rendering against this schema.
