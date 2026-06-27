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
