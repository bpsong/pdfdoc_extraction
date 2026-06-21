# Production parameter parity audit

## Audit scope

- Surface: Visual Pipeline Builder task properties.
- Goal: expose every production built-in task parameter without making the
  common path harder to scan.
- Accessibility target: labelled controls, visible state, keyboard-reachable
  native inputs, responsive reflow, and clear validation recovery.

## Phase evidence

1. `06-final-review-top.png` — Phase 0/final overview. Healthy hierarchy,
   consistent task palette, and no horizontal overflow at 1260px.
2. `02-review-gate-controls.png` — Phases 1–2. Field and document thresholds,
   split-confidence review levels, optional schema, and production-only resume
   behavior are visible and grouped by decision.
3. `03-split-controls.png` — Phase 3. Multiple-category structure, confidence
   policy, allowed-category input, polling, and timeout fit without clipping.
4. `04-extraction-controls.png` — Phase 4. Advanced provider settings are
   disclosed progressively. The initial multiline guidance treatment was too
   tall; it was replaced with a compact field before this screenshot.
5. `05-cleanup-controls.png` — Phase 5. Cleanup is addable from the palette and
   clearly warns that it removes a working file before asking for its directory.
6. Reference matching was exercised through the live DOM. Both existing clauses
   exposed Auto/Text/Numeric choices. The OS fallback twice focused an unrelated
   Chrome window, so those captures were rejected and removed.

## Strengths

- Common settings remain visible while uncommon provider and compatibility
  settings use disclosure sections.
- Review threshold precedence is stated next to the controls.
- Runtime split enablement is clearly separate from pipeline inclusion.
- Destructive cleanup behavior is explained before configuration.
- Native selects, inputs, checkboxes, and details elements preserve familiar
  keyboard behavior.

## UX and accessibility risks

- Long task-property pages still require substantial vertical scrolling. This
  is acceptable for the prototype but could later benefit from section anchors.
- Screenshots confirm visible labels and reflow, not full screen-reader output,
  focus order, or contrast ratios.
- The sample Split task is intentionally blocked until an API key is supplied;
  its task Issues tab identifies that production precondition.

## Verification

- Browser DOM checks covered Review, Split, Extraction, Cleanup, and Reference
  controls.
- Computed layout checks reported no page-level horizontal overflow.
- Frontend production build passed.
- Prototype tests: 11 passed.
- Production Review Gate and parameter-validator tests: 43 passed.
