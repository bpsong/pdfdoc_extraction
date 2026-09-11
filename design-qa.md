# Pipeline Properties Design QA

- Source visual truth: `C:\tmp\pipeline-properties-qa\phase1-split-prototype-desktop.png` through `phase9-archive-prototype-mobile.png`
- Implementation evidence: matching `phase*-production-desktop.png` and `phase*-production-mobile.png` files in `C:\tmp\pipeline-properties-qa`
- Viewports: 1440 x 900 desktop and 390 x 900 mobile
- States: Split, Extraction, Nanoid, CSV/JSON/PDF storage, Update Reference, Review Gate, Archive, extraction row-schema drawer, file picker, invalid advanced JSON, duplicate/remove confirmation

## Full-View Comparison

Production preserves its existing application shell and ordered-list editor while matching the prototype properties pane's information order, grouping, labels, control types, helper text, and task-specific builders. Differences outside the properties pane are intentional production navigation and workflow controls.

## Focused Comparison

- Extraction: provider settings, advanced disclosure, field cards, one-table constraint, required state, Python type guidance, and staged row-schema drawer match the prototype behavior.
- Storage and rules: directory/file pickers, filename preview/token insertion, CSV override disclosure, CSV column loading, clause builder, and rule outcome are present and functional.
- Review: confidence percentage/slider, threshold priority, field/document maps, schema picker, review scope, and toggles follow the prototype structure.
- Mobile: production initially overflowed because grid children retained desktop intrinsic widths. Grid items, header actions, and draft actions were constrained; final production measurement is `scrollWidth == clientWidth == 375`.

## Findings

No actionable P0, P1, or P2 differences remain. Production uses its own typography and application chrome by design; properties-pane control hierarchy and behavior remain equivalent to the prototype.

## Patches Made

- Added all task-specific property builders and shared property actions.
- Added secure directory/file browsing and CSV-header metadata loading.
- Removed runtime-managed housekeeping from editor models and catalogs.
- Corrected mobile workspace and header overflow found during comparison.

## Final Result

final result: passed

---

# Review state and split-pane design QA

- Source visual truth: `C:/Users/bpson/.codex/visualizations/2026/09/11/01a08df9-ff28-7db3-9bae-9b4b89885cda/ui-feedback-audit/05-completed-review.png`
- Implementation screenshot: `output/playwright/phase16/10-completed-review-audit-viewport.png`
- Combined comparison: `output/playwright/phase16/design-comparison.png`
- Additional states: `output/playwright/phase16/06-review-independent-panes.png`, `07-completed-review-vocabulary.png`, `08-extraction-reviewed-vocabulary.png`, and `09-review-stacked-mobile.png`
- Desktop comparison viewport: 1265 × 712 CSS pixels at device scale factor 1
- Source pixels: 1265 × 712
- Implementation pixels: 1265 × 712
- Mobile verification viewport: 390 × 900 CSS pixels at device scale factor 1
- State: completed human review, pending review with the editor scrolled, completed extraction results, and stacked mobile review

## Findings

No actionable P0, P1, or P2 differences remain for the two requested changes.

The source and implementation use different synthetic documents, so PDF content and field counts are not fidelity targets. The comparison is limited to the review-state vocabulary, action/header placement, pane proportions, independent scrolling, and responsive structure.

## Required fidelity surfaces

- Fonts and typography: the existing application font family, weights, sizes, and hierarchy are unchanged. New explanatory copy uses the existing small-body scale and wraps without truncation.
- Spacing and layout rhythm: desktop panes fill the available viewport, retain their panel headers, and use a narrow separator. The editor and PDF scroll independently. At 390 pixels the separator is removed, panels stack, the field header no longer overlaps its controls, and review actions wrap into complete rows.
- Colors and visual tokens: the completed-review message uses the existing success token with a light background and border. Confidence badges retain their original semantic colors as historical extraction evidence.
- Image quality and asset fidelity: no product images, logos, illustrations, or custom icons were added or replaced. The existing PDF.js canvas remains the source-document surface.
- Copy and content: `Review complete`, `Human review complete`, `Reviewed`, and `No model confidence` distinguish completed human work from the original extraction confidence. The completed message explicitly states that no further review action is required.

## Full-view comparison evidence

The combined before/after image shows that the top review actions remain visible, the two-panel hierarchy is preserved, and completed review state now has one clear success message instead of repeated attention styling. The new divider is visible between the PDF and fields without consuming meaningful content width.

## Focused interaction evidence

- Scrolling `.review-editor-scroll` to its end leaves `#review-complete-button` within the viewport and keeps the PDF panel bounded to the viewport.
- The separator exposes `role="separator"`, a current percentage, Left/Right/Home/End keyboard controls, pointer dragging, and double-click reset.
- Completed review fields have no attention highlight or client-validation error styling.
- Completed extraction fields that originally required review render as `Reviewed`, while the persisted extraction confidence remains visible.
- At 390 pixels, the page has no document-level horizontal overflow, all review actions fit inside the viewport, and the field-panel header remains within its bounds.

## Comparison history

1. The first 1366 × 900 render exposed a stale validation message and yellow attention borders on a completed review. Constraint styling and review highlighting were disabled for completed records; the revised completed screenshot confirms both are gone.
2. The first 390 × 900 render exposed overlapping field-header controls and a clipped Complete Review action. The field header now stacks, its identifier truncates safely, and actions use a two-column grid with Complete Review spanning the row. The revised mobile screenshot confirms no page-level horizontal overflow.
3. The final 1265 × 712 comparison and focused desktop/mobile screenshots contain no remaining P0, P1, or P2 issue within scope.

## Primary interactions and console checks

Automated Chromium tests loaded the review and extraction pages, scrolled the editor, moved the separator by keyboard, verified completed-state vocabulary, and checked the stacked mobile layout. The shared page fixture fails on browser console errors; none were reported.

## Follow-up polish

- P3: consider a slightly wider separator hit area if touch-enabled desktop testing shows the current target is difficult to grab. The keyboard alternative is already available.

final result: passed
